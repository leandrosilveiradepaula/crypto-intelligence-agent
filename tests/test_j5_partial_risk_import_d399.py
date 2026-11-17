"""J5/D399: strict, nonfinancial display of an imported D398 PAPER risk report."""
from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "web" / "app"


class _Ids(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids: list[str] = []

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key == "id":
                self.ids.append(value)


class J5PartialRiskReportD399Tests(unittest.TestCase):
    def test_accessible_mobile_panel_and_import_are_separate_from_positions(self):
        html = (APP / "index.html").read_text(encoding="utf-8")
        css = (APP / "style.css").read_text(encoding="utf-8")
        js = (APP / "app.js").read_text(encoding="utf-8")
        parser = _Ids()
        parser.feed(html)
        parser.close()
        ids = (
            "risk-audit-title", "risk-audit-status",
            "risk-audit-empty", "risk-audit-loaded",
            "risk-leverage", "risk-ticks", "risk-fills", "risk-baseline",
            "risk-decision", "risk-value",
        )
        self.assertEqual(len(parser.ids), len(set(parser.ids)))
        for name in ids:
            self.assertIn(name, parser.ids)
        self.assertIn('aria-labelledby="risk-audit-title"', html)
        self.assertIn('role="status" aria-live="polite"', html)
        self.assertIn("não são posições ou preços reais", html)
        self.assertIn("NÃO é", js)
        self.assertIn("let partialRiskReport = null;", js)
        self.assertIn("partialRiskReport = E.validatePaperPartialRiskReport(payload)", js)
        self.assertIn("renderPaperRisk();", js)
        self.assertIn('payload.schema_version === "paper-partial-derisk-risk-d398-v1"', js)
        self.assertIn('set("risk-value", conditional ?', js)
        self.assertIn('risk-decision").dataset.tone = conditional', js)
        self.assertIn(".risk-audit-panel", css)
        self.assertIn("@media(max-width: 720px)", css)
        self.assertNotIn(".innerHTML", js)
        self.assertNotIn("WebSocket(", js)
        self.assertNotIn("api.bybit.com", js)
        # This is a report imported only in memory, distinct from local PAPER
        # scenario persistence and their unrelated gross mark calculator.
        self.assertEqual(js.count("localStorage.setItem(KEY, JSON.stringify(state))"), 1)
        self.assertNotIn("localStorage.setItem(KEY, JSON.stringify(partialRiskReport))", js)

    @unittest.skipUnless(shutil.which("node"), "Node.js D398 display validator")
    def test_strict_d398_schema_veto_and_conditional_never_claim_real_pnl(self):
        code = r"""
const assert = require("node:assert/strict");
const E = require("./web/app/engine.js");
const R = {
  schema_version:"paper-partial-derisk-risk-d398-v1",
  status:"conditional_closed_after_observed_partial_derisk_proxy",
  leverage_at_open_intent:50,mark_ticks_checked:4,
  confirmed_paper_fills_applied:2,
  full_notional_proxy_vetoed:true,has_discrete_terminal:false,
  conditional_net_after_partial_risk_quote:"3.394",
  partial_derisking_applies_after_explicit_fill_only:true,
  liquidation_checked_before_same_tick_fill:true,
  no_unobserved_intrabar_ticks_assumed:true,
  margin_added_from_fills:false,funding_calendar_complete:false,
  risk_tiers_authenticated_by_venue:false,venue_leverage_verified:false,
  venue_liquidation_verified:false,liquidation_formula_verified:false,
  net_pnl_verified:false,orders_sent:false,
  order_submission_enabled:false,approved_for_live_use:false
};
assert.strictEqual(E.validatePaperPartialRiskReport(R),R);
assert.equal(E.validatePaperPartialRiskReport(
  {...R,conditional_net_after_partial_risk_quote:"-2.4500"}
).conditional_net_after_partial_risk_quote,"-2.4500");
const B = {...R,status:"abstain_partial_risk_liquidation_proxy",
  mark_ticks_checked:2,confirmed_paper_fills_applied:0,
  has_discrete_terminal:true,conditional_net_after_partial_risk_quote:null};
assert.equal(E.validatePaperPartialRiskReport(B).status,
             "abstain_partial_risk_liquidation_proxy");
const M = {...B,status:"abstain_immutable_open_margin_receipt_missing",
  leverage_at_open_intent:null,mark_ticks_checked:0,has_discrete_terminal:false};
assert.equal(E.validatePaperPartialRiskReport(M).leverage_at_open_intent,null);
const U = {...B,status:"abstain_position_open_or_pending_reconciliation",
  mark_ticks_checked:0,has_discrete_terminal:false};
assert.equal(E.validatePaperPartialRiskReport(U).conditional_net_after_partial_risk_quote,null);
for (const bad of [
  {...R,account_id:"private"},
  {...R,orders_sent:true},
  {...R,net_pnl_verified:true},
  {...R,venue_liquidation_verified:true},
  {...R,venue_leverage_verified:true},
  {...R,margin_added_from_fills:true},
  {...R,liquidation_checked_before_same_tick_fill:false},
  {...R,partial_derisking_applies_after_explicit_fill_only:false},
  {...R,leverage_at_open_intent:0},
  {...R,leverage_at_open_intent:NaN},
  {...R,mark_ticks_checked:0},
  {...R,mark_ticks_checked:2,confirmed_paper_fills_applied:3},
  {...R,mark_ticks_checked:2049},
  {...R,confirmed_paper_fills_applied:129},
  {...R,conditional_net_after_partial_risk_quote:"NaN"},
  {...R,conditional_net_after_partial_risk_quote:"Infinity"},
  {...R,conditional_net_after_partial_risk_quote:3.394},
  {...R,conditional_net_after_partial_risk_quote:null},
  {...R,has_discrete_terminal:true},
  {...R,status:"real_net_profit_verified"},
  {...R,source_authenticated:true},
  {...B,conditional_net_after_partial_risk_quote:"3.394"},
  {...B,has_discrete_terminal:false},
  {...B,status:"abstain_pit_maintenance_tiers_missing",has_discrete_terminal:true},
  {...M,conditional_net_after_partial_risk_quote:"0"}
]) assert.throws(()=>E.validatePaperPartialRiskReport(bad));
const copy=JSON.parse(JSON.stringify(R));
assert.equal(E.validatePaperPartialRiskReport(copy).status,R.status);
console.log("J5_D399_RISK_REPORT_CONTRACT_PASS");
"""
        r = subprocess.run(
            [shutil.which("node"), "-e", code],
            cwd=ROOT, text=True, capture_output=True, timeout=20,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("J5_D399_RISK_REPORT_CONTRACT_PASS", r.stdout)


if __name__ == "__main__":
    unittest.main()
