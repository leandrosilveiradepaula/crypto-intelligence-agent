"""J1/WU48: private, untrusted Bybit JSON research; zero network."""
from __future__ import annotations
from dataclasses import replace
from copy import deepcopy
from hashlib import sha256
from io import StringIO
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.bybit_local_json_audit import (
    LocalBybitCaptureManifest, audit_local_bybit_json,
)
from crypto_intelligence_agent.market_data import MarketDataError
from scripts.audit_private_bybit_json import (
    PrivateLocalInputError, inspect_private_inputs, main, _read_private_file,
)
from test_bybit_instrument_volume_contract import NOW, START, END, instrument, kline


def raw(value):
    return json.dumps(value, separators=(",", ":")).encode("utf8")


def claim(**changes):
    data = dict(symbol="BTCUSDT", interval="1h", registry_variant="expanded-10",
                start_open_ms=START, end_open_ms=END,
                capture_started_ms=NOW-200, instrument_received_ms=NOW,
                kline_received_ms=NOW+500, capture_finished_ms=NOW+650)
    data.update(changes)
    return LocalBybitCaptureManifest(**data)


def inspect(meta=None, bars=None, manifest=None):
    return audit_local_bybit_json(
        instrument_raw=raw(instrument() if meta is None else meta),
        kline_raw=raw(kline() if bars is None else bars),
        manifest=claim() if manifest is None else manifest)


class LocalBybitAuditTests(unittest.TestCase):
    def test_exact_btc_schema_no_market_values_or_live_flags(self):
        a, b = raw(instrument()), raw(kline())
        result = audit_local_bybit_json(instrument_raw=a, kline_raw=b, manifest=claim())
        self.assertEqual(result["status"], "offline_schema_conformance_passed_origin_unverified")
        self.assertEqual(result["closed_candle_count"], 3)
        self.assertEqual(result["documented_base_volume_unit"], "BTC")
        self.assertEqual(result["documented_quote_turnover_unit"], "USDT")
        self.assertEqual(result["instrument_bytes_sha256"], sha256(a).hexdigest())
        self.assertEqual(result["kline_bytes_sha256"], sha256(b).hexdigest())
        for key in ("actual_provider_origin_authenticated", "actual_capture_timestamps_verified",
                    "canonical_ohlcv_approved", "historical_top50_approved",
                    "live_public_schema_observed", "public_or_commercial_rights_authorized",
                    "real_financial_backtest_approved", "live_trading_authorized",
                    "orders_sent", "data_stored", "financial_quote_is_usd"):
            self.assertIs(result[key], False)
        self.assertEqual(result["network_requests"], 0)
        summary = json.dumps(result)
        for value in ("100.0000000000001", "1.123456789123456789",
                      "99.987654321987654321"):
            self.assertNotIn(value, summary)
        self.assertEqual(result, inspect())

    def test_usdc_is_quote_stablecoin_not_usd(self):
        x = inspect(instrument(symbol="BTCUSDC"), kline(symbol="BTCUSDC"),
                    claim(symbol="BTCUSDC"))
        self.assertEqual(x["documented_quote_turnover_unit"], "USDC")
        self.assertFalse(x["financial_quote_is_usd"])

    def test_bad_tradfi_metadata_and_symbol(self):
        for field, value in (("symbolType", "stock"), ("marketRegion", "US"),
                             ("underlyingTicker", "STOCK"), ("isPreListing", True),
                             ("status", "Closed"), ("baseCoin", "AAPL")):
            m = deepcopy(instrument())
            m["result"]["list"][0][field] = value
            with self.subTest(field=field), self.assertRaises(MarketDataError):
                inspect(meta=m)
        with self.assertRaises(MarketDataError):
            inspect(manifest=claim(symbol="AAPLUSDT"))

    def test_manifest_rejects_bad_clock_window_and_version(self):
        for values in (dict(capture_started_ms=NOW+600),
                       dict(instrument_received_ms=NOW+600),
                       dict(capture_finished_ms=NOW+31_000),
                       dict(capture_started_ms=True),
                       dict(kline_received_ms=1.5),
                       dict(end_open_ms=END+1),
                       dict(end_open_ms=START+2*3_600_000),
                       dict(interval="4h"),
                       dict(registry_variant="expanded-13")):
            with self.subTest(values=values), self.assertRaises(MarketDataError):
                inspect(manifest=claim(**values))

    def test_clock_and_kline_integrity_fail_closed(self):
        m = instrument()
        m["time"] = NOW-60_000
        with self.assertRaises(MarketDataError):
            inspect(meta=m)
        for mutation in ("missing", "duplicate", "float", "nan", "other_symbol"):
            k = kline()
            rows = k["result"]["list"]
            if mutation == "missing": rows.pop()
            if mutation == "duplicate": rows[1][0] = rows[0][0]
            if mutation == "float": rows[0][5] = 1.5
            if mutation == "nan": rows[0][6] = "NaN"
            if mutation == "other_symbol": k["result"]["symbol"] = "ETHUSDT"
            with self.subTest(mutation=mutation), self.assertRaises(MarketDataError):
                inspect(bars=k)

    def test_exact_bytes_duplicate_keys_oversize_and_type(self):
        valid = raw(kline())
        for payload in (b'', b'[]', b'{"x":NaN}', b'{"a":0,"a":1}',
                        b' ' * 131073):
            with self.subTest(size=len(payload)), self.assertRaises(MarketDataError):
                audit_local_bybit_json(instrument_raw=payload,
                                       kline_raw=valid, manifest=claim())
        with self.assertRaises(MarketDataError):
            audit_local_bybit_json(instrument_raw="text",
                                   kline_raw=valid, manifest=claim())
        with self.assertRaises(MarketDataError):
            LocalBybitCaptureManifest.from_json_bytes(b'{"a":0,"a":1}')

    def test_manifest_no_extra_keys_and_no_file_read_without_optin(self):
        self.assertEqual(LocalBybitCaptureManifest.from_json_bytes(raw(vars(claim()))), claim())
        with self.assertRaises(MarketDataError):
            LocalBybitCaptureManifest.from_json_bytes(raw({**vars(claim()), "api_key":"hidden"}))
        with patch("scripts.audit_private_bybit_json._read_private_file",
                   side_effect=AssertionError("should not read")):
            with self.assertRaises(PrivateLocalInputError):
                inspect_private_inputs(manifest_path="/missing/a",
                                       instrument_path="/missing/b", kline_path="/missing/c")
        from contextlib import redirect_stdout
        output = StringIO()
        with redirect_stdout(output):
            code = main(["--manifest","/missing/account.json",
                         "--instrument","/missing/api_token",
                         "--kline","/missing/12345"])
        self.assertEqual(code,1)
        self.assertEqual(json.loads(output.getvalue())["status"],"offline_input_rejected")
        self.assertNotIn("account",output.getvalue())

    @unittest.skipUnless(os.name=="posix","private 0600/0700 checks require POSIX")
    def test_private_local_input_and_reject_unsafe_permissions_links(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); root.chmod(0o700)
            names = ("manifest.json","instrument.json","kline.json")
            blobs = (raw(vars(claim())),raw(instrument()),raw(kline()))
            paths = []
            for name,blob in zip(names,blobs):
                path = root/name; path.write_bytes(blob); path.chmod(0o600); paths.append(path)
            result = inspect_private_inputs(
                manifest_path=str(paths[0]),instrument_path=str(paths[1]),
                kline_path=str(paths[2]),allow_private_offline_input=True)
            self.assertEqual(result["closed_candle_count"],3)
            paths[1].chmod(0o644)
            with self.assertRaises(PrivateLocalInputError):
                _read_private_file(str(paths[1]),max_bytes=131072)
            paths[1].chmod(0o600)
            alias=root/"alias"; alias.symlink_to(paths[1])
            with self.assertRaises(PrivateLocalInputError):
                _read_private_file(str(alias),max_bytes=131072)
            with self.assertRaises(PrivateLocalInputError):
                _read_private_file(str(paths[1]),max_bytes=4)
            root.chmod(0o755)
            with self.assertRaises(PrivateLocalInputError):
                _read_private_file(str(paths[1]),max_bytes=131072)

    def test_no_network_and_failure_sanitization(self):
        from contextlib import redirect_stdout
        with patch("urllib.request.urlopen",side_effect=AssertionError("no net")):
            with patch("socket.create_connection",side_effect=AssertionError("no net")):
                self.assertEqual(inspect()["network_requests"],0)
        output=StringIO()
        with redirect_stdout(output):
            status=main(["--manifest","/missing/private_account.json",
                         "--instrument","/missing/key_abc",
                         "--kline","/missing/price_123",
                         "--allow-private-offline-input"])
        self.assertEqual(status,1)
        for token in ("private_account","key_abc","price_123"):
            self.assertNotIn(token,output.getvalue())


if __name__=="__main__":
    unittest.main()
