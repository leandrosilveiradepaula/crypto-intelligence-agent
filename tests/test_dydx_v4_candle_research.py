"""J1/WU40 — dYdX Chain v4 schema, volume units and one-shot transport OFFLINE."""
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

from crypto_intelligence_agent.dydx_v4_candle_research import (
    DydxV4PerpCandleResearch, HOUR_MS, SOURCE,
    stage_dydx_v4_btc_hourly,
)
from crypto_intelligence_agent.market_data import (
    ClosedCandle, DataGapError, DataValidationError,
)
from scripts.probe_dydx_private_base_usd import (
    MARKETS_URL, CANDLES_URL, PrivateProbeError, _get, inspect_once,
)

NOW = 1_792_970_000_000
TOP = NOW // HOUR_MS * HOUR_MS
START, END = TOP - 4 * HOUR_MS, TOP - HOUR_MS


def market_payload():
    return {"markets": {"BTC-USD": {
        "ticker": "BTC-USD", "status": "ACTIVE", "marketType": "CROSS",
    }}}


def candle_payload():
    return {"candles": [
        {
            "startedAt": datetime.fromtimestamp((TOP - i * HOUR_MS) / 1000,
                                                timezone.utc)
                .isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "ticker": "BTC-USD", "resolution": "1HOUR",
            "open": "100.000000000000000001", "high": "110.0",
            "low": "90.0001", "close": "105.000000000000000002",
            "baseTokenVolume": "4.123456789123456789",
            "usdVolume": "421.987654321987654321", "trades": 5,
        }
        for i in range(6)
    ]}


class Response:
    def __init__(self, content, *, status=200, url=None,
                 mime="application/json; charset=utf-8"):
        self.body = BytesIO(content if isinstance(content, bytes)
                            else json.dumps(content).encode())
        self.status = status
        self.url = url
        self.headers = {"Content-Type": mime}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def getcode(self):
        return self.status

    def geturl(self):
        return self.url or self.request_url

    def read(self, length):
        return self.body.read(length)


class FakeOpen:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, request, *, timeout):
        self.calls.append(request)
        assert request.get_method() == "GET"
        assert request.full_url in (MARKETS_URL, CANDLES_URL)
        assert timeout == 8
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        value.request_url = request.full_url
        return value


def probe(opener, times=(NOW, NOW + 40, NOW + 75)):
    clock = iter(times)
    return inspect_once(
        allow_public_network=True, allow_private_dydx_probe=True,
        opened=opener, clock_ms=lambda: next(clock),
    )


def stage(markets=None, candles=None):
    return stage_dydx_v4_btc_hourly(
        market_payload() if markets is None else markets,
        candle_payload() if candles is None else candles,
        market_observed_at_ms=NOW + 40,
        observed_at_ms=NOW + 75, start_open_ms=START, end_open_ms=END,
    )


class DydxV4UnitContractTests(unittest.TestCase):
    def test_real_registry_and_documented_units_are_exact_not_canonical(self):
        page = stage()
        self.assertEqual(len(page.candles), 3)
        self.assertEqual(tuple(x.open_time_ms for x in page.candles),
                         (START, START + HOUR_MS, START + 2 * HOUR_MS))
        self.assertEqual(page.registry_sha256.__len__(), 64)
        first = page.candles[0]
        self.assertEqual(first.base_token_volume, Decimal("4.123456789123456789"))
        self.assertEqual(first.usd_volume, Decimal("421.987654321987654321"))
        self.assertEqual(first.open, Decimal("100.000000000000000001"))
        self.assertEqual(first.trade_count, 5)
        self.assertEqual(first.source, SOURCE)
        self.assertFalse(first.canonical_ohlcv)
        self.assertFalse(page.canonical_ohlcv)
        self.assertFalse(page.public_or_commercial_rights_authorized)
        self.assertFalse(page.live_provider_authenticated)
        self.assertNotIsInstance(first, ClosedCandle)
        self.assertFalse(hasattr(first, "quote_volume"))
        self.assertFalse(hasattr(first, "volume_usdc"))

    def test_wrong_market_status_and_tradfi_cannot_pass(self):
        for field, value in (
            ("status", "PAUSED"), ("ticker", "AAPL-USD"),
            ("marketType", "UNKNOWN"),
        ):
            obj = market_payload()
            obj["markets"]["BTC-USD"][field] = value
            with self.subTest(field=field), self.assertRaises(DataValidationError):
                stage(markets=obj)
        with self.assertRaises(DataValidationError):
            stage(markets={"markets": {"AAPL-USD": {
                "ticker": "AAPL-USD", "status": "ACTIVE"}}})

    def test_price_or_volume_non_exact_cannot_be_recovered_from_float(self):
        changes = [
            ("baseTokenVolume", 4.1), ("baseTokenVolume", "NaN"),
            ("baseTokenVolume", True), ("usdVolume", "Infinity"),
            ("usdVolume", "-0.1"), ("open", 100), ("high", "0"),
            ("close", "110.0001"), ("low", "101"),
            ("trades", 4.2), ("trades", True),
        ]
        for field, value in changes:
            payload = candle_payload()
            payload["candles"][2][field] = value
            with self.subTest(field=field), self.assertRaises(DataValidationError):
                stage(candles=payload)

    def test_zero_trades_and_volumes_must_agree(self):
        for trades, base, usd, valid in (
            (0, "0", "0", True), (0, "2", "0", False),
            (1, "0", "0", False), (1, "2", "0", False),
            (2, "0", "3", False),
        ):
            payload = candle_payload()
            row = payload["candles"][2]
            row.update({"trades": trades, "baseTokenVolume": base, "usdVolume": usd})
            with self.subTest(case=(trades, base, usd)):
                if valid:
                    self.assertEqual(stage(candles=payload).candles[2].trade_count, 0)
                else:
                    with self.assertRaises(DataValidationError):
                        stage(candles=payload)

    def test_duplicate_missing_misaligned_and_future_rows_are_rejected(self):
        payload = candle_payload()
        payload["candles"][3]["startedAt"] = payload["candles"][2]["startedAt"]
        with self.assertRaises(DataGapError):
            stage(candles=payload)
        payload = candle_payload()
        del payload["candles"][3]
        with self.assertRaises(DataGapError):
            stage(candles=payload)
        payload = candle_payload()
        payload["candles"][3]["startedAt"] = payload["candles"][3]["startedAt"].replace(
            ":00.000Z", ":01.000Z")
        with self.assertRaises(DataValidationError):
            stage(candles=payload)
        payload = candle_payload()
        payload["candles"][3]["ticker"] = "ETH-USD"
        with self.assertRaises(DataValidationError):
            stage(candles=payload)

    def test_invalid_timing_fails_closed(self):
        for parameters in (
            {"market_observed_at_ms": NOW + 100, "observed_at_ms": NOW + 50},
            {"market_observed_at_ms": NOW + 40, "observed_at_ms": NOW + 40_000},
            {"start_open_ms": START + 1, "end_open_ms": END + 1},
            {"start_open_ms": START, "end_open_ms": END + HOUR_MS},
            {"observed_at_ms": END - 1},
        ):
            args = {
                "market_observed_at_ms": NOW + 40,
                "observed_at_ms": NOW + 75,
                "start_open_ms": START, "end_open_ms": END,
            }
            args.update(parameters)
            with self.subTest(parameters=parameters), self.assertRaises(DataValidationError):
                stage_dydx_v4_btc_hourly(market_payload(), candle_payload(), **args)


class DydxV4OneShotTests(unittest.TestCase):
    def test_two_public_gets_and_sanitized_report(self):
        opener = FakeOpen(Response(market_payload()), Response(candle_payload()))
        result = probe(opener)
        self.assertEqual(result["status"], "private_dydx_base_usd_schema_observed")
        self.assertEqual(result["validated_closed_candles"], 3)
        self.assertEqual(result["requests_attempted"], 2)
        self.assertTrue(result["base_and_usd_volume_fields_seen"])
        self.assertEqual([r.full_url for r in opener.calls],
                         [MARKETS_URL, CANDLES_URL])
        for flag in ("canonical_ohlcv_approved", "historical_top50_approved",
                     "public_or_commercial_rights_authorized",
                     "credentials_used", "orders_sent", "responses_persisted",
                     "market_data_published", "ready_for_trading"):
            self.assertFalse(result[flag])
        self.assertNotIn("421.987654321987654321", json.dumps(result))
        self.assertNotIn("100.000000000000000001", json.dumps(result))
        self.assertEqual(len(result["markets_response_sha256"]), 64)
        self.assertEqual(len(result["candles_response_sha256"]), 64)

    def test_double_optin_prevents_all_io(self):
        opener = FakeOpen()
        for a, b in ((False, False), (True, False), (False, True)):
            with self.subTest(a=a, b=b), self.assertRaises(PrivateProbeError):
                inspect_once(allow_public_network=a,
                             allow_private_dydx_probe=b,
                             opened=opener, clock_ms=lambda: NOW)
        self.assertEqual(opener.calls, [])

    def test_inactive_market_stops_before_candle_get(self):
        obj = market_payload()
        obj["markets"]["BTC-USD"]["status"] = "PAUSED"
        opener = FakeOpen(Response(obj))
        result = probe(opener)
        self.assertEqual(result["status"], "inactive_or_mismatched_btc_market")
        self.assertEqual(result["requests_attempted"], 1)
        self.assertEqual(len(opener.calls), 1)

    def test_http_restriction_and_redirect_never_retry(self):
        for code in (403, 418, 429, 451):
            opener = FakeOpen(HTTPError(MARKETS_URL, code, "untrusted", {}, None))
            with self.subTest(http=code):
                result = probe(opener)
                self.assertEqual(result["status"], "access_or_geographic_restriction")
                self.assertEqual(len(opener.calls), 1)
        opener = FakeOpen(Response(market_payload(), url="https://other.invalid/"))
        self.assertEqual(probe(opener)["status"], "redirect_or_changed_origin_rejected")

    def test_duplicate_json_and_wrong_content_type_rejected(self):
        raw = b'{"markets":{},"markets":{}}'
        self.assertEqual(probe(FakeOpen(Response(raw)))["status"], "invalid_exact_json")
        self.assertEqual(probe(FakeOpen(Response(market_payload(), mime="text/html")))["status"],
                         "unexpected_content_type")

    def test_finite_response_size_and_unknown_url_fail(self):
        report = {"requests_attempted": 0}
        with self.assertRaises(PrivateProbeError):
            _get("https://unauthorized.invalid/api", opened=FakeOpen(),
                 report=report, hash_field="hash")
        self.assertEqual(report["requests_attempted"], 0)
        self.assertEqual(
            probe(FakeOpen(Response(b"x" * 131_073)))["status"],
            "response_size_invalid",
        )

    def test_clock_regression_or_expiry_without_chart(self):
        opener = FakeOpen(Response(market_payload()))
        self.assertEqual(
            probe(opener, times=(NOW, NOW - 1))["status"],
            "metadata_capture_window_expired",
        )
        self.assertEqual(len(opener.calls), 1)

    def test_module_cli_import_offline(self):
        root = Path(__file__).resolve().parent.parent
        process = subprocess.run(
            [sys.executable, "-m", "scripts.probe_dydx_private_base_usd", "--help"],
            cwd=root, capture_output=True, text=True, timeout=10, check=False,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertIn("--allow-private-dydx-probe", process.stdout)


if __name__ == "__main__":
    unittest.main()
