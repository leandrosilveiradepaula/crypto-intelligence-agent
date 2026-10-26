"""J1/WU44: offline fake transport for one-shot real Bybit V5 unit probe."""
from __future__ import annotations

from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys
import unittest
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse

from crypto_intelligence_agent.market_data import DataValidationError
from test_bybit_instrument_volume_contract import (
    HOUR, NOW, START, END, instrument, kline,
)
from scripts.probe_bybit_private_ohlcv import (
    INSTRUMENT_URL, _kline_url, PrivateBybitProbeError, inspect_once,
)


class FakeResponse:
    def __init__(self, obj, *, mime="application/json; charset=UTF-8",
                 code=200, url=None):
        self.payload = BytesIO(obj if type(obj) is bytes else json.dumps(obj).encode())
        self.mime = mime
        self.code = code
        self.url = url
        self.actual_url = None
        self.headers = {"Content-Type": mime}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def getcode(self):
        return self.code

    def geturl(self):
        return self.actual_url if self.url is None else self.url

    def read(self, max_bytes):
        return self.payload.read(max_bytes)


class FakeOpen:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, request, *, timeout):
        self.calls.append((request, timeout))
        assert request.get_method() == "GET"
        assert not request.has_header("Authorization")
        assert timeout == 8
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        response.actual_url = request.full_url
        return response


def run(reader, *, clocks=(NOW, NOW + 150, NOW + 250)):
    clock = iter(clocks)
    return inspect_once(
        allow_public_network=True, allow_private_bybit_probe=True,
        opened=reader, clock_ms=lambda: next(clock),
    )


class BybitRealProbeTests(unittest.TestCase):
    def test_fixed_two_get_btc_usdt_volume_units_no_prices_or_rights_in_output(self):
        reader = FakeOpen(FakeResponse(instrument()), FakeResponse(kline()))
        result = run(reader)
        self.assertEqual(result["status"], "private_real_bybit_base_btc_quote_usdt_observed")
        self.assertEqual(result["requests_attempted"], 2)
        self.assertEqual(result["max_get_requests"], 2)
        self.assertEqual(result["validated_closed_candles"], 3)
        self.assertTrue(result["live_public_schema_observed"])
        self.assertEqual(result["documented_base_unit"], "BTC")
        self.assertEqual(result["documented_turnover_quote_unit"], "USDT_not_USD")
        self.assertEqual(len(result["registry_sha256"]), 64)
        self.assertEqual(len(result["instrument_response_sha256"]), 64)
        self.assertEqual(len(result["kline_response_sha256"]), 64)
        self.assertEqual(reader.calls[0][0].full_url, INSTRUMENT_URL)
        self.assertEqual(reader.calls[1][0].full_url, _kline_url(START, END))
        parsed = parse_qs(urlparse(reader.calls[1][0].full_url).query)
        self.assertEqual(parsed["category"], ["linear"])
        self.assertEqual(parsed["symbol"], ["BTCUSDT"])
        self.assertEqual(parsed["interval"], ["60"])
        self.assertEqual(parsed["start"], [str(START)])
        self.assertEqual(parsed["end"], [str(END - 1)])
        self.assertEqual(parsed["limit"], ["3"])
        for field in ("data_stored", "raw_prices_or_volumes_logged",
                      "credentials_used", "orders_sent",
                      "canonical_ohlcv_approved", "historical_top50_approved",
                      "public_or_commercial_rights_authorized",
                      "ready_for_trading"):
            self.assertFalse(result[field])
        output = json.dumps(result)
        self.assertNotIn("1.123456789123456789", output)
        self.assertNotIn("100.0000000000001", output)
        self.assertNotIn("99.987654321987654321", output)

    def test_double_optin_no_network_and_no_urls_exposed(self):
        reader = FakeOpen()
        for a, b in ((False, False), (True, False), (False, True)):
            with self.subTest(a=a, b=b), self.assertRaises(PrivateBybitProbeError):
                inspect_once(allow_public_network=a,
                             allow_private_bybit_probe=b,
                             opened=reader, clock_ms=lambda: NOW)
        self.assertEqual(reader.calls, [])

    def test_403_451_429_and_geo_retcode_abort_without_retry(self):
        for code in (401, 403, 418, 429, 451):
            reader = FakeOpen(HTTPError(INSTRUMENT_URL, code, "untrusted", {}, None))
            report = run(reader)
            with self.subTest(code=code):
                self.assertEqual(report["status"], "bybit_access_or_region_restricted_no_retry")
                self.assertEqual(report["requests_attempted"], 1)
                self.assertEqual(len(reader.calls), 1)
        for code in (10009, 10024):
            response = instrument()
            response["retCode"] = code
            reader = FakeOpen(FakeResponse(response))
            report = run(reader)
            self.assertEqual(report["status"], "bybit_access_or_region_restricted_no_retry")
            self.assertEqual(len(reader.calls), 1)

    def test_inactive_or_tradfi_or_wrong_contract_stops_before_chart(self):
        for changed in (
            ("status", "Settling"), ("contractType", "InversePerpetual"),
            ("baseCoin", "AAPL"), ("symbolType", "stock"),
            ("marketRegion", "US"), ("quoteCoin", "USD"),
            ("preListingInfo", {"isPreListing": True}),
        ):
            payload = instrument()
            payload["result"]["list"][0][changed[0]] = changed[1]
            reader = FakeOpen(FakeResponse(payload))
            report = run(reader)
            with self.subTest(case=changed):
                self.assertEqual(report["status"], "instrument_or_kline_contract_rejected")
                self.assertEqual(len(reader.calls), 1)

    def test_bad_kline_gaps_units_and_numeric_types_are_rejected(self):
        for mutation in ("missing", "duplicate", "float", "nan", "bad_quote"):
            payload = kline()
            rows = payload["result"]["list"]
            if mutation == "missing":
                rows.pop()
            elif mutation == "duplicate":
                rows[1][0] = rows[0][0]
            elif mutation == "float":
                rows[1][5] = 1.5
            elif mutation == "nan":
                rows[1][6] = "NaN"
            elif mutation == "bad_quote":
                payload["result"]["symbol"] = "ETHUSDT"
            reader = FakeOpen(FakeResponse(instrument()), FakeResponse(payload))
            with self.subTest(mutation=mutation):
                report = run(reader)
                self.assertEqual(report["status"], "instrument_or_kline_contract_rejected")
                self.assertEqual(report["requests_attempted"], 2)
                self.assertEqual(len(reader.calls), 2)

    def test_redirect_json_mime_oversize_and_duplicate_keys_never_retry(self):
        cases = (
            FakeResponse(instrument(), url="https://attacker.invalid/"),
            FakeResponse(instrument(), mime="text/html"),
            FakeResponse(b"a" * 131073),
            FakeResponse(b'{"retCode":0,"retCode":0}'),
        )
        statuses = (
            "redirect_or_origin_changed",
            "unexpected_content_type",
            "unexpected_response_length",
            "nonexact_or_invalid_json_rejected",
        )
        for response, status in zip(cases, statuses):
            reader = FakeOpen(response)
            with self.subTest(status=status):
                report = run(reader)
                self.assertEqual(report["status"], status)
                self.assertEqual(report["requests_attempted"], 1)
                self.assertEqual(len(reader.calls), 1)

    def test_invalid_registry_time_preflight_zero_network(self):
        # A registry version cannot be used before its observed timestamp or
        # more than 7 days later. Real BTC-ETH remains unchanged.
        reader = FakeOpen()
        with self.assertRaises(DataValidationError):
            inspect_once(
                allow_public_network=True, allow_private_bybit_probe=True,
                opened=reader, clock_ms=lambda: 1792000000000,
            )
        with self.assertRaises(DataValidationError):
            inspect_once(
                allow_public_network=True, allow_private_bybit_probe=True,
                opened=reader, clock_ms=lambda: 1793900000000,
            )
        self.assertEqual(reader.calls, [])

    def test_clock_expired_after_metadata_skips_chart(self):
        reader = FakeOpen(FakeResponse(instrument()))
        report = run(reader, clocks=(NOW, NOW + 30001))
        self.assertEqual(report["status"], "instrument_capture_clock_invalid")
        self.assertEqual(report["requests_attempted"], 1)
        self.assertEqual(len(reader.calls), 1)
        reader = FakeOpen(FakeResponse(instrument()), FakeResponse(kline()))
        report = run(reader, clocks=(NOW, NOW + 150, NOW + 30001))
        self.assertEqual(report["status"], "kline_capture_clock_invalid")
        self.assertEqual(report["requests_attempted"], 2)

    def test_cli_disabled_offline_and_help(self):
        root = Path(__file__).resolve().parent.parent
        run_cli = subprocess.run(
            [sys.executable, "-m", "scripts.probe_bybit_private_ohlcv"],
            cwd=root, text=True, capture_output=True, timeout=10, check=False,
        )
        self.assertEqual(run_cli.returncode, 1)
        report = json.loads(run_cli.stdout)
        self.assertEqual(report["status"], "offline_or_registry_preflight_rejected")
        self.assertEqual(report["requests_attempted"], 0)
        help_cli = subprocess.run(
            [sys.executable, "-m", "scripts.probe_bybit_private_ohlcv", "--help"],
            cwd=root, text=True, capture_output=True, timeout=10, check=False,
        )
        self.assertEqual(help_cli.returncode, 0, help_cli.stderr)
        self.assertIn("--allow-private-bybit-probe", help_cli.stdout)


if __name__ == "__main__":
    unittest.main()
