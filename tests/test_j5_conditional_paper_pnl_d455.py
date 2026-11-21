"""D455: owner-only J5 browser consumes canonical D454 PAPER PnL safely."""
from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

from test_j5_persisted_paper_mobile_d407 import example

ROOT = Path(__file__).resolve().parents[1]

NODE = r"""
const assert = require("node:assert/strict");
const fs = require("node:fs");
const report = JSON.parse(fs.readFileSync(0, "utf8"));
const view = require("./web/app/persisted-paper.js");
const valid = view.validateReport(report);
assert.equal(valid, report);
const first = report.positions[0];
assert.equal(first.conditional_paper_pnl.conditional_realized_before_funding_quote, "-0.32");
const fake = (change) => {
  const copy = structuredClone(report);
  change(copy, copy.positions[0].conditional_paper_pnl);
  assert.throws(() => view.validateReport(copy), /PAPER inválido/);
};
fake((r,p)=>p.true_realized_net_pnl_available=true);
fake((r,p)=>p.funding_settlement_unknown=false);
fake((r,p)=>p.venue_fill_verified=true);
fake((r,p)=>p.orders_sent=true);
fake((r,p)=>p.conditional_realized_before_funding_quote="Infinity");
fake((r,p)=>p.conditional_realized_before_funding_quote="<img>");
fake((r,p)=>p.priced_entry_units="900");
fake((r,p)=>p.realized_exit_units="1");
fake((r,p)=>p.leverage_at_open=201);
fake((r,p)=>p.priced_fill_events=-1);
fake((r,p)=>p.exit_fee_quote="-0.001");
fake((r,p)=>p.extra_value="secret");
fake((r,p)=>p.conditional_realized_before_funding_quote="-0.31");
fake((r,p)=>p.gross_realized_reference_quote="9000000");
fake((r,p)=>r.financial_pnl_available=true);
const legacy = structuredClone(report);
legacy.positions[0].conditional_paper_pnl = {
  status:"legacy_paper_position_without_priced_strategy",
  true_realized_net_pnl_available:false
};
view.validateReport(legacy);
legacy.positions[0].conditional_paper_pnl.venue_fill_verified = true;
assert.throws(() => view.validateReport(legacy), /PAPER inválido/);
const old = structuredClone(report);
delete old.positions[0].conditional_paper_pnl;
view.validateReport(old);

const boxes = new Map();
function element(tag) {
  return {tag, hidden:false, children:[], textContent:"",
    append(...items){ this.children.push(...items); },
    replaceChildren(){ this.children=[]; }};
}
global.document = {
  getElementById(id) {
    if (!boxes.has(id)) boxes.set(id, element("div"));
    return boxes.get(id);
  },
  createElement: element,
};
view.install(report);
const rows=boxes.get("persisted-paper-rows");
assert.equal(rows.children.length, 1);
const text=rows.children[0].children.map(x=>x.textContent).join(" | ");
assert.match(text,/Resultado PAPER parcial estimado: -0.32 USDT/);
assert.match(text,/NÃO é lucro real/);
assert.doesNotMatch(text,/Infinity/);
console.log("D455_OWNER_PAPER_CONDITIONAL_VIEW_PASS");
"""


class D455PaperPnLBrowserTests(unittest.TestCase):
    def test_local_owner_paper_has_optional_consistent_conditional_projection(self):
        sample = example()
        p = sample["positions"][0]
        p["conditional_paper_pnl"] = {
            "schema_version": "d454-paper-conditional-priced-fills-v1",
            "status": "conditional_paper_reference_before_unverified_funding",
            "priced_entry_units": "100",
            "realized_exit_units": "30",
            "gross_realized_reference_quote": "-0.28",
            "entry_fee_allocated_quote": "0.01",
            "exit_fee_quote": "0.01",
            "entry_slippage_allocated_quote": "0.01",
            "exit_slippage_quote": "0.01",
            "conditional_realized_before_funding_quote": "-0.32",
            "outstanding_entry_cost_quote": "0.03",
            "leverage_at_open": 50,
            "priced_fill_events": 2,
            "funding_calendar_verified": False,
            "funding_settlement_unknown": True,
            "true_realized_net_pnl_available": False,
            "source_is_hypothetical_post_latency_bbo": True,
            "venue_fill_verified": False,
            "venue_fee_schedule_verified": False,
            "liquidation_verified": False,
            "orders_sent": False,
            "approved_for_live_use": False,
        }
        p["margin_intent_requested"] = {
            "leverage_at_intent": 50,
            "requested_margin_quote": "5",
            "quote_currency": "USDT",
            "quality": "synthetic_requested_margin_at_intent_only",
            "opening_order_cross_checked": False,
            "actual_position_margin_verified": False,
            "venue_leverage_verified": False,
            "orders_sent": False,
        }
        if not shutil.which("node"):
            self.skipTest("Node required for front-end contract")
        run = subprocess.run(
            ["node", "-e", NODE], input=json.dumps(sample),
            text=True, cwd=ROOT, capture_output=True, timeout=20,
        )
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("D455_OWNER_PAPER_CONDITIONAL_VIEW_PASS", run.stdout)

    def test_loopback_uses_optional_financial_projection_without_new_endpoint(self):
        source = (ROOT / "scripts/serve_j5_local_readonly.py").read_text()
        self.assertIn("include_conditional_pnl=True", source)
        self.assertIn('"/api/owner-paper-positions"', source)
        self.assertNotIn('"/api/live-financial-trading"', source)


if __name__ == "__main__":
    unittest.main()
