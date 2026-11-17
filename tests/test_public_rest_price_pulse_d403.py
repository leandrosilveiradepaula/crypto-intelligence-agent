"""D403: one public Bybit REST snapshot -> strictly read-only mobile import."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from crypto_intelligence_agent.bybit_public_j1_transport import (
    BoundedBybitPublicClient,
    tickers_url,
)
from crypto_intelligence_agent.bybit_public_rest_price_pulse_d403 import (
    capture_public_rest_price_pulse,
)
from crypto_intelligence_agent.market_data import DataGapError, DataValidationError

ROOT = Path(__file__).resolve().parents[1]
NOW = 1_800_000_000_000


def quote(symbol, *, bid="99.9", ask="100.1", size="2", mark="100"):
    return {
        "symbol": symbol, "lastPrice": "100.0", "markPrice": mark,
        "bid1Price": bid, "ask1Price": ask,
        "bid1Size": size, "ask1Size": "3", "turnover24h": "456789.0123",
    }


def payload(*, data=None, at=NOW):
    return {
        "retCode": 0, "retMsg": "OK",
        "time": at,
        "result": {"category": "linear", "list": data if data is not None
                   else [quote("BTCUSDT"), quote("ETHUSDT")]},
    }


def run(rows=None, *, at=NOW, symbols=("BTCUSDT", "ETHUSDT")):
    wire = json.dumps(payload(data=rows, at=at)).encode("utf-8")
    gets = []
    def transport(url, limit):
        gets.append((url, limit))
        return wire
    client = BoundedBybitPublicClient(transport=transport)
    result = capture_public_rest_price_pulse(
        symbols=symbols, client=client, clock_ms=lambda: NOW + 200,
    )
    return result, gets


class PublicRestPricePulseD403Tests(unittest.TestCase):
    def test_one_real_transport_path_reused_no_position_or_signals(self):
        r, calls = run([quote("ETHUSDT"), quote("BTCUSDT"),
                        quote("AAAUSDT")])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], tickers_url())
        self.assertEqual(r["observed_symbol_count"], 2)
        self.assertEqual([x["symbol"] for x in r["quotes"]],
                         ["BTCUSDT", "ETHUSDT"])
        self.assertEqual(r["quotes"][0]["mark_price"], "100")
        self.assertEqual(r["quotes"][0]["bid_price"], "99.9")
        self.assertEqual(r["quotes"][0]["turnover_24h"], "456789.0123")
        self.assertEqual(r["network_gets_in_this_capture"], 1)
        for key in ("crypto_only_membership_verified",
                    "continuous_websocket_verified",
                    "imported_report_authenticated_by_browser",
                    "paper_positions_linked", "orders_sent",
                    "approved_for_signals", "approved_for_live_use"):
            self.assertFalse(r[key])
        self.assertNotIn("AAAUSDT", json.dumps(r))

    def test_max_fifty_reviewed_symbols_plus_extra_provider_rows(self):
        selected = tuple(f"A{i:02d}USDT" for i in range(50))
        r, calls = run([quote(s) for s in selected] +
                       [quote("XYZUSDT")], symbols=selected)
        self.assertEqual(r["observed_symbol_count"], 50)
        self.assertEqual(len(calls), 1)

    def test_missing_duplicate_bad_book_or_decimal_abstains(self):
        bads = (
            [quote("BTCUSDT")],
            [quote("BTCUSDT"), quote("BTCUSDT"), quote("ETHUSDT")],
            [quote("BTCUSDT", bid="101", ask="100"), quote("ETHUSDT")],
            [quote("BTCUSDT", mark="NaN"), quote("ETHUSDT")],
            [quote("BTCUSDT", size="0"), quote("ETHUSDT")],
            [quote("BTCUSDT", bid="<script>"), quote("ETHUSDT")],
        )
        for rows in bads:
            with self.subTest(rows=len(rows)), self.assertRaises(
                (DataGapError, DataValidationError)
            ):
                run(rows)

    def test_stale_or_future_server_time_never_delivers_price(self):
        for at in (NOW - 60_000, NOW + 20_000):
            with self.subTest(at=at), self.assertRaises(DataGapError):
                run(at=at)

    def test_invalid_membership_abstains_before_any_network(self):
        for symbols in ((), ("BTCUSDT", "BTCUSDT"),
                        ("BTCUSD",), ("BTCUSDT", 123),
                        tuple(f"A{i:02d}USDT" for i in range(51))):
            with self.subTest(count=len(symbols)):
                calls = []
                client = BoundedBybitPublicClient(
                    transport=lambda url, n: calls.append(url))
                with self.assertRaises(DataValidationError):
                    capture_public_rest_price_pulse(
                        symbols=symbols, client=client,
                        clock_ms=lambda: NOW,
                    )
                self.assertEqual(calls, [])

    def test_no_order_endpoint_or_private_position_imports(self):
        from crypto_intelligence_agent import bybit_public_rest_price_pulse_d403
        code = Path(bybit_public_rest_price_pulse_d403.__file__).read_text()
        self.assertIn("tickers_url()", code)
        self.assertNotIn("/v5/order", code)
        self.assertNotIn("api_key", code)
        self.assertNotIn("sqlite3", code)
        self.assertNotIn("import websockets", code)

    def test_cli_help_does_not_contact_market(self):
        completed = subprocess.run(
            [sys.executable, "-m",
             "scripts.capture_bybit_rest_price_pulse_d403", "--help"],
            cwd=ROOT, capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("--symbols", completed.stdout)
        self.assertIn("--output", completed.stdout)

    @unittest.skipUnless(shutil.which("node"), "Node.js required for UI validator")
    def test_node_validates_exact_decimal_public_rest_report(self):
        script = r"""
const assert=require('node:assert/strict');
const m=require('./web/app/public-market.js');
const R={
  schema_version:"bybit-public-rest-price-pulse-d403-v1",
  status:"rest_snapshot_display_only", source:"bybit_v5_public_linear_tickers",
  server_at_ms:1800000000000,captured_at_ms:1800000000100,
  observed_symbol_count:1, network_gets_in_this_capture:1,
  quotes:[{symbol:"BTCUSDT",last_price:"100.000000000000000000000001",
    mark_price:"100",bid_price:"99.9",ask_price:"100.1",
    bid_size:"1",ask_size:"2",turnover_24h:"0"}],
  crypto_only_membership_verified:false,continuous_websocket_verified:false,
  imported_report_authenticated_by_browser:false,paper_positions_linked:false,
  orders_sent:false,approved_for_signals:false,approved_for_live_use:false
};
assert.strictEqual(m.validateReport(R),R);
for(const bad of [
  {...R,orders_sent:true},
  {...R,approved_for_signals:true},
  {...R,imported_report_authenticated_by_browser:true},
  {...R,continuous_websocket_verified:true},
  {...R,network_gets_in_this_capture:0},
  {...R,observed_symbol_count:2},
  {...R,server_at_ms:0},
  {...R,captured_at_ms:R.server_at_ms+60000},
  {...R,quotes:[{...R.quotes[0],mark_price:"NaN"}]},
  {...R,quotes:[{...R.quotes[0],bid_price:"100.2"}]},
  {...R,quotes:[{...R.quotes[0],symbol:"<img src=x>"}]},
  {...R,quotes:[{...R.quotes[0],ask_size:"0"}]},
  {...R,quotes:[{...R.quotes[0],secret:"foo"}]},
  {...R,source:"authenticated_exchange"},
  {...R,live_account:true},
]) assert.throws(()=>m.validateReport(bad));
console.log("D403_PUBLIC_REST_MOBILE_SCHEMA_PASS");
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT, capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("D403_PUBLIC_REST_MOBILE_SCHEMA_PASS", completed.stdout)


if __name__ == "__main__":
    unittest.main()
