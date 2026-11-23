"""D407: persisted AUTO4 PAPER summary -> isolated mobile read-only visualization."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


def example():
    return {
        "schema_version": "paper_positions_snapshot_v1",
        "mode": "offline_paper",
        "quality": "synthetic_journal_replay_only",
        "source_provenance": "local_sqlite_digest_not_exchange_authenticated",
        "selection": "explicit_ids_same_sqlite_read_transaction",
        "no_cross_instrument_quantity_aggregation": True,
        "orders_sent": False,
        "live_trading_authorized": False,
        "approved_for_live_use": False,
        "financial_pnl_available": False,
        "positions": [{
            "position_id": "fixture_multi_position_B",
            "venue_candidate": "bybit_v5",
            "symbol_fixture": "ETHUSDT",
            "side": "LONG",
            "checkpoint_utc": "2026-11-16T13:00:00.002Z",
            "initial_confirmed_units": "100",
            "filled_exit_units": "30",
            "reserved_unfilled_units": "20",
            "confirmed_remaining_units": "70",
            "unreserved_units": "50",
            "runner_floor_units": "6",
            "runner_filled_units": "0",
            "runner_reserved_unfilled_units": "0",
            "runner_unallocated_units": "6",
            "runner_readiness": "PENDING_EXIT_RECONCILIATION",
            "trailing_stop_active": False,
            "native_stop_verified": False,
            "recovered_runner": None,
            "margin_intent_requested": None,
            "opening_order_cross_checked": False,
            "pending_or_unknown_orders": 1,
            "unknown_order_count": 1,
        }]
    }


NODE_SCRIPT = r"""
const assert=require("node:assert/strict");
const mod=require("./web/app/persisted-paper.js");
const report=JSON.parse(process.stdin.read?.()||'null');
"""
# process.stdin.read() can be null unless stream is primed; use Node stdin file:
NODE = r"""
const assert = require("node:assert/strict");
const fs = require("node:fs");
const mod = require("./web/app/persisted-paper.js");
const sample = JSON.parse(fs.readFileSync(0, "utf8"));
assert.equal(mod.validateReport(sample), sample);
function bad(mutate) {
  const copy = structuredClone(sample);
  mutate(copy, copy.positions[0]);
  assert.throws(() => mod.validateReport(copy), /PAPER inválido/);
}
bad(r => {r.orders_sent=true});
bad(r => {r.live_trading_authorized=true});
bad(r => {r.financial_pnl_available=true});
bad(r => {r.market_price_live="9999999"});
bad(r => {r.positions.push(structuredClone(r.positions[0]))});
bad((r,p) => {p.confirmed_remaining_units="71"});
bad((r,p) => {p.reserved_unfilled_units="30"});
bad((r,p) => {p.unknown_order_count=2});
bad((r,p) => {p.unknown_order_count=-1});
bad((r,p) => {p.native_stop_verified=true});
bad((r,p) => {p.trailing_stop_active=true});
bad((r,p) => {p.position_id="<img src=x onerror=alert(1)>"});
bad((r,p) => {p.symbol_fixture="BTCUSDT<img>"});
bad((r,p) => {p.margin_intent_requested={leverage_at_intent:50}});
bad((r,p) => {p.runner_readiness="LIVE_STOP_CONFIRMED"});
bad((r,p) => {p.initial_confirmed_units="Infinity"});
bad((r,p) => {p.filled_exit_units="3e1"});
bad((r,p) => {p.venue_candidate="live_bybit"});
bad((r,p) => {p.recovered_runner={state:"TRACKING",native_stop_verified:true}});
assert.equal(sample.positions[0].unknown_order_count,1);
console.log("D407_PAPER_PERSISTED_VIEW_VALIDATE_PASS");
"""


class PersistedPaperMobileD407Tests(unittest.TestCase):
    def test_static_source_contains_no_network_or_browser_persistence(self):
        source=(ROOT / "web/app/persisted-paper.js").read_text(encoding="utf-8")
        self.assertIn("paper_positions_snapshot_v1",source)
        self.assertIn("market-pulse-row",source)
        self.assertIn('global.fetch("/api/owner-paper-positions"', source)
        self.assertIn('credentials: "omit"', source)
        self.assertIn('redirect: "error"', source)
        self.assertIn("isLocal()", source)
        for forbidden in (
            "localStorage.", "sessionStorage.", "indexedDB.",
            "XMLHttpRequest", "new WebSocket", "innerHTML", "document.write",
            "sendBeacon", "eval(",
        ):
            self.assertNotIn(forbidden,source)

    def test_app_routes_existing_persisted_snapshot_without_mutating_lab(self):
        app=(ROOT / "web/app/app.js").read_text(encoding="utf-8")
        html=(ROOT / "web/app/index.html").read_text(encoding="utf-8")
        self.assertIn('payload.schema_version === "paper_positions_snapshot_v1"',app)
        self.assertIn("globalThis.CIAPersistedPaper.install(payload)",app)
        self.assertIn('id="persisted-paper-status"',html)
        self.assertIn('src="./persisted-paper.js"',html)
        self.assertIn("não alteram o laboratório PAPER",html)

    @unittest.skipUnless(shutil.which("node"), "Node needed for JS contract")
    def test_node_rejects_fake_financial_proofs_and_inconsistent_balances(self):
        completed=subprocess.run(
            ["node","-e",NODE],input=json.dumps(example()),
            text=True,cwd=ROOT,capture_output=True,timeout=12,
        )
        self.assertEqual(completed.returncode,0,completed.stderr)
        self.assertIn("D407_PAPER_PERSISTED_VIEW_VALIDATE_PASS",completed.stdout)


if __name__ == "__main__":
    unittest.main()
