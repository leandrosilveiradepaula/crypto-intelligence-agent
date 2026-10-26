"""J1/WU42 CandleFeed Free research: offline provider/UTC/Decimal/rights gates."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys
import unittest
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse

from crypto_intelligence_agent.candlefeed_ohlcv_research import (
    HOUR_MS, WINDOW_HOURS, CandleFeedResearchCandle,
    stage_candlefeed_btc_24h,
)
from crypto_intelligence_agent.crypto_asset_registry import load_registry_json
from crypto_intelligence_agent.decimal_json import decode_public_market_json_exact
from crypto_intelligence_agent.market_data import ClosedCandle, DataGapError, DataValidationError
from scripts.probe_candlefeed_private_ohlcv import (
    ENV_KEY, HOST_AND_PATH, CandleFeedPrivateError, inspect_once, _url,
)

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = load_registry_json(
    (ROOT / "registries" / "crypto-btc-eth-20261025-v1.json").read_bytes())
NOW = REGISTRY.observed_at_ms + 2 * HOUR_MS
TOP = NOW // HOUR_MS * HOUR_MS
START = TOP - 25 * HOUR_MS
END = TOP - HOUR_MS
KEY = "cf_live_OFFLINE_TEST_KEY_ABC123"


def iso(t):
    return datetime.fromtimestamp(t / 1000, timezone.utc).isoformat(
        timespec="seconds").replace("+00:00", "Z")


def candles_payload():
    return {
        "status": "ok",
        "symbol": "BTCUSDT", "exchange": "binance",
        "count": 24, "has_more": False, "next_cursor": None,
        "data": [
            {
                "time": iso(START + i * HOUR_MS),
                "open": "100.000000000000000001",
                "high": "110.0000", "low": "90.0000",
                "close": "101.000000000000000002",
                "volume": "0.123456789012345678",
                "quote_volume": "12.345678901234567890",
            }
            for i in range(WINDOW_HOURS)
        ],
    }


def exact_json_bytes():
    # Source numerics are JSON numbers, not Python float conversions.
    text = json.dumps(candles_payload(), separators=(",", ":"))
    for token in (
        "100.000000000000000001", "110.0000", "90.0000",
        "101.000000000000000002", "0.123456789012345678",
        "12.345678901234567890",
    ):
        text = text.replace('"' + token + '"', token)
    return text.encode()


def stage(payload=None, **changes):
    opts = dict(
        start_open_ms=START, end_open_ms=END,
        observed_at_ms=NOW + 50, requested_at_ms=NOW,
    )
    opts.update(changes)
    return stage_candlefeed_btc_24h(candles_payload() if payload is None else payload, **opts)


class Response:
    def __init__(self, payload, *, url=None, content_type="application/json", status=200):
        self.payload = BytesIO(payload)
        self.url = url
        self.status = status
        self.headers = {"Content-Type": content_type}
        self.request_url = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def getcode(self):
        return self.status

    def geturl(self):
        return self.request_url if self.url is None else self.url

    def read(self, limit):
        return self.payload.read(limit)


class FakeOpen:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def __call__(self, req, *, timeout):
        self.calls.append((req, timeout))
        if isinstance(self.result, Exception):
            raise self.result
        self.result.request_url = req.full_url
        return self.result


def run(opener, *, start=NOW, end=NOW + 150):
    clock = iter((start, end))
    return inspect_once(
        allow_public_network=True, allow_private_research=True,
        api_key=KEY, opened=opener, clock_ms=lambda: next(clock),
    )


class CandleFeedVolumeContractTests(unittest.TestCase):
    def test_full_day_is_base_btc_reported_usd_not_usdt_or_closedcandle(self):
        result = stage()
        self.assertEqual(len(result.candles), 24)
        self.assertEqual(result.origin_exchange, "binance")
        self.assertEqual(result.origin_quote_currency, "USDT")
        self.assertEqual(result.reported_quote_currency, "USD")
        self.assertEqual(result.candles[0].open_time_ms, START)
        self.assertEqual(result.candles[-1].open_time_ms, END - HOUR_MS)
        self.assertEqual(result.candles[0].reported_base_volume_btc,
                         Decimal("0.123456789012345678"))
        self.assertEqual(result.candles[0].reported_quote_volume_usd,
                         Decimal("12.345678901234567890"))
        self.assertFalse(result.canonical_ohlcv)
        self.assertFalse(result.public_or_commercial_redistribution_authorized)
        self.assertFalse(result.live_exchange_origin_verified)
        self.assertFalse(result.candles[0].canonical_ohlcv)
        self.assertNotIsInstance(result.candles[0], ClosedCandle)
        self.assertFalse(hasattr(result.candles[0], "quote_volume"))
        self.assertFalse(hasattr(result.candles[0], "settlement_usdt_volume"))

    def test_real_decimal_json_parser_never_goes_through_binary_float(self):
        decoded = decode_public_market_json_exact(exact_json_bytes(), max_bytes=131072)
        result = stage(decoded)
        self.assertEqual(result.candles[0].open, Decimal("100.000000000000000001"))
        self.assertEqual(result.candles[0].reported_quote_volume_usd,
                         Decimal("12.345678901234567890"))
        self.assertTrue(all(type(x.reported_base_volume_btc) is Decimal for x in result.candles))

    def test_status_symbol_exchange_wrong_count_or_cursor_rejected(self):
        for field, value in (
            ("status", "error"), ("symbol", "AAPLUSDT"),
            ("exchange", "bybit"), ("count", 23),
            ("count", True), ("has_more", True),
            ("has_more", 0), ("next_cursor", "other_page"),
        ):
            bad = candles_payload()
            bad[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(DataValidationError):
                stage(bad)

    def test_missing_duplicate_ghost_hour_and_future_fail_closed(self):
        cases = []
        bad = candles_payload(); bad["data"].pop(); bad["count"] = 23; cases.append(bad)
        bad = candles_payload()
        bad["data"][6]["time"] = bad["data"][5]["time"]; cases.append(bad)
        bad = candles_payload()
        bad["data"][3]["time"] = iso(START + 25 * HOUR_MS); cases.append(bad)
        bad = candles_payload()
        bad["data"][0]["time"] = iso(START + 1234); cases.append(bad)
        for payload in cases:
            with self.subTest(first=payload["data"][0]["time"]), self.assertRaises(
                (DataGapError, DataValidationError)):
                stage(payload)

    def test_ohlc_float_bool_nonfinite_and_inconsistent_volume_fail(self):
        for field, value in (
            ("open", 100.0), ("high", Decimal("NaN")),
            ("low", "-1"), ("close", False),
            ("volume", 0.0), ("volume", False),
            ("volume", Decimal("Infinity")),
            ("quote_volume", 12.5), ("quote_volume", True),
            ("volume", "0"), ("quote_volume", "0"),
            ("high", "99"), ("low", "102"),
        ):
            payload = candles_payload()
            payload["data"][7][field] = value
            with self.subTest(field=field, value=repr(value)), self.assertRaises(
                DataValidationError):
                stage(payload)
        payload = candles_payload()
        payload["data"][7].update({"volume": "0.000", "quote_volume": "0.0"})
        self.assertEqual(stage(payload).candles[7].reported_base_volume_btc, Decimal(0))

    def test_calendar_time_requires_utc_and_exact_millisecond(self):
        for value in (
            "2026-10-24T00:00:00",
            "2026-10-24T00:00:00-03:00",
            "2026-10-24T00:00:00.000001Z",
            "not-a-timestamp",
            1792970000000,
        ):
            payload = candles_payload()
            payload["data"][2]["time"] = value
            with self.subTest(value=value), self.assertRaises(DataValidationError):
                stage(payload)

    def test_registry_revisions_and_capture_timestamps_fail_closed(self):
        for kwargs in (
            {"observed_at_ms": NOW - 1},
            {"observed_at_ms": NOW + 30_001},
            {"start_open_ms": START + 1, "end_open_ms": END + 1},
            {"start_open_ms": START, "end_open_ms": END + HOUR_MS},
            {"requested_at_ms": REGISTRY.observed_at_ms - 1},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(DataValidationError):
                stage(**kwargs)


class CandleFeedPrivateProbeTests(unittest.TestCase):
    def test_one_private_get_exact_fixed_url_and_safe_report(self):
        opener = FakeOpen(Response(exact_json_bytes(), content_type="application/json; charset=utf-8"))
        result = run(opener)
        self.assertEqual(result["status"], "private_provider_schema_validated_not_venue_verified")
        self.assertEqual(result["valid_closed_candles"], 24)
        self.assertTrue(result["full_requested_window"])
        self.assertEqual(result["requests_attempted"], 1)
        self.assertEqual(len(opener.calls), 1)
        request, timeout = opener.calls[0]
        self.assertEqual(timeout, 8)
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.get_header("X-api-key"), KEY)
        self.assertEqual(request.full_url, _url(START, END))
        self.assertEqual(urlparse(request.full_url).hostname, "candlefeed.ai")
        params = parse_qs(urlparse(request.full_url).query)
        self.assertEqual(params["symbol"], ["BTCUSDT"])
        self.assertEqual(params["exchange"], ["binance"])
        self.assertEqual(params["interval"], ["1h"])
        self.assertEqual(params["limit"], ["24"])
        self.assertEqual(params["end"], [iso(END - HOUR_MS)])
        for field in (
            "credentials_in_output", "raw_data_in_output",
            "provider_data_persisted", "canonical_ohlcv_approved",
            "financial_backtest_approved",
            "commercial_or_public_redistribution_authorized",
            "upstream_venue_rights_verified",
            "top50_historical_approved", "orders_sent",
        ):
            self.assertFalse(result[field])
        serialized = json.dumps(result)
        for forbidden in (KEY, "0.123456789012345678", "12.345678901234567890", "cf_live_"):
            self.assertNotIn(forbidden, serialized)

    def test_without_double_optin_or_valid_key_zero_network(self):
        opener = FakeOpen(Response(exact_json_bytes()))
        for allow_network, allow_private in (
            (False, False), (True, False), (False, True),
        ):
            with self.subTest(flags=(allow_network, allow_private)), self.assertRaises(
                CandleFeedPrivateError):
                inspect_once(
                    allow_public_network=allow_network,
                    allow_private_research=allow_private,
                    api_key=KEY, opened=opener, clock_ms=lambda: NOW,
                )
        for key in (None, "", "bad", "cf_live_", "cf_live_ with spaces", False, 5):
            # Injecting None falls back to ambient env; isolate explicitly.
            from unittest.mock import patch
            with patch.dict("os.environ", {ENV_KEY: ""}), self.subTest(key=key):
                with self.assertRaises(CandleFeedPrivateError):
                    inspect_once(allow_public_network=True,
                                 allow_private_research=True,
                                 api_key=key, opened=opener,
                                 clock_ms=lambda: NOW)
        self.assertEqual(opener.calls, [])

    def test_auth_access_and_redirect_fail_without_repeat_or_leak(self):
        for status in (401, 403, 418, 429, 451):
            opener = FakeOpen(HTTPError(HOST_AND_PATH, status, KEY, {}, None))
            with self.subTest(status=status):
                result = run(opener)
                self.assertEqual(result["status"], "provider_auth_or_access_blocked")
                self.assertEqual(result["requests_attempted"], 1)
                self.assertNotIn(KEY, json.dumps(result))
                self.assertEqual(len(opener.calls), 1)
        opener = FakeOpen(Response(exact_json_bytes(), url="https://attacker.invalid/"))
        self.assertEqual(run(opener)["status"], "redirect_or_origin_change_rejected")

    def test_unexpected_provider_exception_cannot_exfiltrate_key_to_log(self):
        opener = FakeOpen(RuntimeError("remote failed for " + KEY))
        result = run(opener)
        self.assertEqual(result["status"], "unexpected_provider_failure_sanitized")
        self.assertEqual(result["requests_attempted"], 1)
        self.assertNotIn(KEY, json.dumps(result))
        self.assertEqual(len(opener.calls), 1)

    def test_wrong_content_type_oversized_and_duplicate_json_rejected(self):
        self.assertEqual(
            run(FakeOpen(Response(exact_json_bytes(), content_type="text/html")))["status"],
            "invalid_json_content_type",
        )
        self.assertEqual(
            run(FakeOpen(Response(b"x" * 131073)))["status"],
            "invalid_json_response_size",
        )
        self.assertEqual(
            run(FakeOpen(Response(b'{"status":"ok","status":"ok"}')))["status"],
            "provider_hourly_schema_or_completeness_rejected",
        )

    def test_clock_regression_and_stale_registry_no_network(self):
        opener = FakeOpen(Response(exact_json_bytes()))
        with self.assertRaises(DataValidationError):
            inspect_once(
                allow_public_network=True, allow_private_research=True,
                api_key=KEY, opened=opener,
                clock_ms=lambda: REGISTRY.observed_at_ms - 1)
        self.assertEqual(opener.calls, [])
        expired = REGISTRY.observed_at_ms + 8 * 86_400_000
        with self.assertRaises(DataValidationError):
            inspect_once(
                allow_public_network=True, allow_private_research=True,
                api_key=KEY, opened=opener, clock_ms=lambda: expired)
        self.assertEqual(opener.calls, [])
        expired_opener = FakeOpen(Response(exact_json_bytes()))
        result = run(expired_opener, end=NOW - 1)
        self.assertEqual(result["status"], "capture_clock_expired_or_reversed")
        self.assertEqual(len(expired_opener.calls), 1)

    def test_disabled_cli_never_uses_key_or_network(self):
        out = subprocess.run(
            [sys.executable, "-m", "scripts.probe_candlefeed_private_ohlcv"],
            cwd=ROOT, capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(out.returncode, 1)
        data = json.loads(out.stdout)
        self.assertEqual(data["status"], "private_preflight_rejected_no_network")
        self.assertEqual(data["requests_attempted"], 0)
        self.assertNotIn(KEY, out.stdout)
        out = subprocess.run(
            [sys.executable, "-m", "scripts.probe_candlefeed_private_ohlcv", "--help"],
            cwd=ROOT, capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(out.returncode, 0)
        self.assertIn("--allow-private-research", out.stdout)


if __name__ == "__main__":
    unittest.main()
