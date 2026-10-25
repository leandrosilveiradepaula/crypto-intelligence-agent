"""No-network tests for Kraken public raw-volume diagnostic (WU12)."""
from __future__ import annotations

from contextlib import redirect_stderr
import io
import json
from pathlib import Path
import subprocess
import sys
from urllib.error import HTTPError, URLError
import unittest
from unittest.mock import patch

from scripts.probe_kraken_volume_units import (
    CANDLES_URL, HOUR_MS, SYMBOL, TICKERS_URL,
    main, make_report, summarize_closed_chart, summarize_public_ticker,
)


HOUR = HOUR_MS
NOW = 27 * HOUR + 1000


def chart_payload(*, count=27):
    return {
        "candles": [{
            "time": i * HOUR, "open": "65000.0", "high": "65001.0",
            "low": "64999.0", "close": "65000.1", "volume": i + 1,
        } for i in range(count)],
        "more_candles": True,
    }


def ticker_payload():
    return {
        "result": "success",
        "tickers": [
            {"symbol": SYMBOL, "tag": "perpetual",
             "vol24h": 4130.4136, "volumeQuote": 331016603.1374,
             "apiSecret": "SHOULD_NOT_APPEAR"},
            {"symbol": "PF_AAPLXUSD", "tag": "perpetual",
             "vol24h": 999, "volumeQuote": 999},
        ],
    }


class Response:
    def __init__(self, data, *, status=200):
        self.data = json.dumps(data).encode()
        self.status = status

    def read(self, size):
        return self.data[:size]

    def getcode(self):
        return self.status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class Opener:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.requests = []

    def __call__(self, request, *, timeout):
        self.requests.append((request.full_url, request.get_method(), timeout))
        if not self.outcomes:
            raise AssertionError("more than two requests!")
        x = self.outcomes.pop(0)
        if isinstance(x, Exception):
            raise x
        return x


class KrakenVolumeResearchTests(unittest.TestCase):
    def test_one_24h_closed_window_has_unverified_volume_units(self):
        report = summarize_closed_chart(chart_payload(), observed_at_ms=NOW)
        self.assertEqual(report["closed_candles_used"], 24)
        self.assertEqual(report["window_start_open_time_ms"], 3 * HOUR)
        self.assertEqual(report["window_end_open_exclusive_ms"], 27 * HOUR)
        self.assertEqual(report["sum_24_closed_hours_raw_volume_unverified"], "372")
        self.assertEqual(report["raw_volume_unit"], "unverified")
        self.assertIn("not_exact", report["rolling_24h_alignment"])

    def test_candle_still_open_is_excluded_not_used_as_complete(self):
        report = summarize_closed_chart(chart_payload(), observed_at_ms=27 * HOUR - 1)
        self.assertEqual(report["closed_candles_used"], 24)
        self.assertEqual(report["window_end_open_exclusive_ms"], 26 * HOUR)
        with self.assertRaises(ValueError):
            summarize_closed_chart(chart_payload(), observed_at_ms=23 * HOUR)

    def test_chart_gap_order_volume_and_timezone_are_rejected(self):
        for field, value in (
            ("time", 3 * HOUR + 1000),
            ("time", True),
            ("volume", -1),
            ("volume", 1.25),
            ("volume", True),
            ("volume", 2 ** 63),
        ):
            with self.subTest(field=field, value=value):
                body = chart_payload()
                body["candles"][3][field] = value
                with self.assertRaises(ValueError):
                    summarize_closed_chart(body, observed_at_ms=NOW)
        for count in (0, 23, 28):
            with self.subTest(count=count):
                with self.assertRaises(ValueError):
                    summarize_closed_chart(chart_payload(count=count), observed_at_ms=NOW)

    def test_bad_payload_and_clock_rejected(self):
        for body in ({}, {"candles": [], "more_candles": "true"}):
            with self.subTest(body=body):
                with self.assertRaises(ValueError):
                    summarize_closed_chart(body, observed_at_ms=NOW)
        for timestamp in (0, True, 2.5):
            with self.subTest(timestamp=timestamp):
                with self.assertRaises(ValueError):
                    summarize_closed_chart(chart_payload(), observed_at_ms=timestamp)

    def test_ticker_only_outputs_public_volume_sample_not_raw_payload(self):
        report = summarize_public_ticker(ticker_payload())
        self.assertEqual(report["ticker_symbol"], "PF_XBTUSD")
        self.assertEqual(report["ticker_tag"], "perpetual")
        self.assertEqual(report["ticker_volume_unit_validation"], "not_established")
        self.assertNotIn("SHOULD_NOT_APPEAR", json.dumps(report))
        self.assertEqual(report["ticker_volumeQuote_as_reported"], "331016603.1374")

    def test_no_ticker_or_nonfinite_volumes_fail(self):
        for ticket in (
            {"tickers": []}, {"tickers": [{"symbol": SYMBOL, "tag": "spot"}]},
            {"tickers": [{"symbol": SYMBOL, "tag": "perpetual",
                          "vol24h": "NaN", "volumeQuote": 1}]},
            {"tickers": [{"symbol": SYMBOL, "tag": "perpetual",
                          "vol24h": 1, "volumeQuote": 0}]},
        ):
            with self.subTest(ticker=ticket):
                with self.assertRaises(ValueError):
                    summarize_public_ticker(ticket)

    def test_exact_two_read_only_gets_with_sanitized_report(self):
        opener = Opener(Response(chart_payload()), Response(ticker_payload()))
        result = make_report(opener=opener, clock_ms=lambda: NOW)
        self.assertEqual(result["status"], "observed_aggregates_not_unit_proof")
        self.assertEqual(result["requests_attempted"], 2)
        self.assertFalse(result["unit_proof"])
        self.assertFalse(result["orders_enabled"])
        self.assertFalse(result["auth_used"])
        self.assertFalse(result["raw_response_persisted"])
        self.assertNotIn("SHOULD_NOT_APPEAR", json.dumps(result))
        self.assertEqual(opener.requests, [
            (CANDLES_URL, "GET", 8),
            (TICKERS_URL, "GET", 8),
        ])
        self.assertFalse("base_volume" in json.dumps(result))
        self.assertFalse("quote_volume" in json.dumps(result))

    def test_http451_from_first_request_stops_without_retry(self):
        opener = Opener(HTTPError(CANDLES_URL, 451, "restricted", None, None))
        result = make_report(opener=opener, clock_ms=lambda: NOW)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["routes"][0]["status"], "access_or_policy_restriction")
        self.assertEqual(result["requests_attempted"], 1)
        self.assertEqual(len(opener.requests), 1)

    def test_second_request_network_error_does_not_disclose_details(self):
        opener = Opener(Response(chart_payload()), URLError("SECRET_PROBE_LOCATION"))
        result = make_report(opener=opener, clock_ms=lambda: NOW)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["requests_attempted"], 2)
        self.assertNotIn("SECRET_PROBE_LOCATION", json.dumps(result))

    def test_first_endpoint_invalid_payload_does_not_call_second(self):
        opener = Opener(Response({"candles": [], "more_candles": True}))
        result = make_report(opener=opener, clock_ms=lambda: NOW)
        self.assertEqual(result["status"], "invalid_chart_or_insufficient_data")
        self.assertEqual(len(opener.requests), 1)

    def test_no_network_on_invalid_utc_clock(self):
        opener = Opener()
        with self.assertRaisesRegex(ValueError, "runner clock"):
            make_report(opener=opener, clock_ms=lambda: 0)
        self.assertEqual(opener.requests, [])

    def test_default_cli_must_not_open_public_network(self):
        with patch("scripts.probe_kraken_volume_units._default_open",
                   side_effect=AssertionError("unexpected network")):
            for args in (
                [], ["--allow-public-network"], ["--allow-volume-diagnostic"],
            ):
                with self.subTest(args=args):
                    with redirect_stderr(io.StringIO()):
                        with self.assertRaises(SystemExit) as exit_code:
                            main(args)
                    self.assertEqual(exit_code.exception.code, 2)

    def test_module_mode_entrypoint_has_no_network_by_default(self):
        root = Path(__file__).resolve().parent.parent
        result = subprocess.run(
            [sys.executable, "-m", "scripts.probe_kraken_volume_units"],
            cwd=root, text=True, capture_output=True, check=False, timeout=10,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("both explicit public-network", result.stderr)
        self.assertNotIn("ModuleNotFoundError", result.stderr)


if __name__ == "__main__":
    unittest.main()
