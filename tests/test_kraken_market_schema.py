"""Bounded live market-data schema probe is tested without network."""
from __future__ import annotations

from contextlib import redirect_stderr
import io
import json
from urllib.error import HTTPError, URLError
import unittest
from unittest.mock import patch

from scripts.probe_kraken_market_schema import ROOT, PATHS, MAX_CALLS, make_report, main


class Response:
    def __init__(self, payload, *, status=200):
        self.body = json.dumps(payload).encode("utf-8")
        self.code = status

    def getcode(self):
        return self.code

    def read(self, size):
        return self.body[:size]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class OpenSequence:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.requests = []

    def __call__(self, request, *, timeout):
        self.requests.append((request.full_url, request.get_method(), timeout))
        if not self.outcomes:
            raise AssertionError("probe made more requests than authorized")
        candidate = self.outcomes.pop(0)
        if isinstance(candidate, Exception):
            raise candidate
        return candidate


INSTRUMENTS = {
    "result": "success",
    "instruments": [
        {"symbol": "PF_XBTUSD", "type": "flexible_futures",
         "tickSize": "0.5", "tradeable": True},
        {"symbol": "PF_AAPLXUSD", "type": "flexible_futures",
         "tickSize": "0.01", "tradeable": True},
    ],
}
TICKERS = {"result": "success", "tickers": [
    {"symbol": "PF_XBTUSD", "tag": "perpetual", "volumeQuote": 12345678.8, "suspended": False},
]}
CANDLES = {"candles": [
    {"time": 1710000000000, "open": "65000", "high": "65010", "low": "64990", "close": "65002", "volume": 22},
    {"time": 1710003600000, "open": "65002", "high": "65030", "low": "65001", "close": "65022", "volume": 30},
], "more_candles": True}


class KrakenSchemaProbeTests(unittest.TestCase):
    def test_two_flags_required_without_any_network(self):
        for flags in ([], ["--allow-public-network"], ["--allow-kraken-schema-probe"]):
            with self.subTest(flags=flags):
                with patch("scripts.probe_kraken_market_schema._default_open",
                           side_effect=AssertionError("network forbidden")):
                    with redirect_stderr(io.StringIO()):
                        with self.assertRaises(SystemExit) as error:
                            main(flags)
                    self.assertEqual(error.exception.code, 2)

    def test_exact_three_gets_with_safe_summary_and_no_auth(self):
        opening = OpenSequence(Response(INSTRUMENTS), Response(TICKERS), Response(CANDLES))
        result = make_report(opener=opening)
        self.assertEqual(result["status"], "ok")
        self.assertFalse(result["auth_used"])
        self.assertFalse(result["orders_enabled"])
        self.assertFalse(result["raw_response_persisted"])
        self.assertFalse(result["instrument_eligibility_validated"])
        self.assertEqual(result["requests_attempted"], 3)
        self.assertLessEqual(result["requests_attempted"], MAX_CALLS)
        self.assertEqual([req[0] for req in opening.requests],
                         [ROOT + PATHS[k] for k in ("instruments", "tickers", "candles")])
        self.assertTrue(all(method == "GET" and timeout <= 8 for _, method, timeout in opening.requests))
        self.assertTrue(result["btc_metadata"]["found"])
        self.assertTrue(result["tokenized_asset_metadata"]["found"])
        self.assertTrue(result["btc_ticker"]["found"])
        self.assertEqual(result["btc_ticker"]["selected"]["tag"], "perpetual")
        self.assertEqual(result["btc_ticker"]["selected"]["volumeQuote"], 12345678.8)
        self.assertEqual(result["candles"]["count"], 2)
        self.assertIn("time", result["candles"]["field_names"])

    def test_missing_btc_instruments_never_queries_chart(self):
        opener = OpenSequence(Response({"result": "success", "instruments": [
            {"symbol": "PF_SOLUSD"},
        ]}), Response({"tickers": []}))
        report = make_report(opener=opener)
        self.assertEqual(report["status"], "missing_btc_instrument")
        self.assertEqual(len(opener.requests), 2)

    def test_first_endpoint_block_stops_immediately(self):
        for http_status in (403, 418, 451):
            with self.subTest(http_status=http_status):
                opener = OpenSequence(HTTPError(
                    ROOT + PATHS["instruments"], http_status, "restricted", None, None,
                ))
                report = make_report(opener=opener)
                self.assertEqual(report["status"], "blocked")
                self.assertEqual(report["routes"][0]["status"], "policy_or_access_restriction")
                self.assertEqual(report["routes"][0]["http_status"], http_status)
                self.assertEqual(report["requests_attempted"], 1)

    def test_second_endpoint_error_stops_before_candles(self):
        opener = OpenSequence(Response(INSTRUMENTS), URLError("private-location"))
        report = make_report(opener=opener)
        self.assertEqual(report["status"], "partial")
        self.assertEqual(report["requests_attempted"], 2)
        self.assertNotIn("private-location", json.dumps(report))

    def test_incomplete_payloads_are_reported_and_not_marked_valid(self):
        for instrument_payload in ([], {}, {"instruments": []}, {"result": "error", "instruments": []}):
            with self.subTest(payload=instrument_payload):
                opener = OpenSequence(Response(instrument_payload))
                report = make_report(opener=opener)
                self.assertEqual(report["status"], "invalid_instruments")
                self.assertEqual(len(opener.requests), 1)

    def test_missing_candle_data_is_not_conformance_success(self):
        opener = OpenSequence(Response(INSTRUMENTS), Response(TICKERS), Response({"candles": []}))
        report = make_report(opener=opener)
        self.assertEqual(report["status"], "empty_candles")
        self.assertEqual(report["requests_attempted"], 3)


if __name__ == "__main__":
    unittest.main()
