"""D412: actual D411 PAPER/WS health report -> mobile dashboard; no network."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import unittest

from test_j2_j4_current_n50_paper_lease_d410 import (
    J2J4CurrentN50PaperD410Tests, N50, ack, ticker,
)

ROOT = Path(__file__).resolve().parents[1]

NODE = r"""
const assert = require("node:assert/strict");
const fs = require("node:fs");
const elements = {};
for (const key of ["paper-ws-health-empty", "paper-ws-health-loaded",
                   "paper-ws-health-status", "paper-ws-health-rows"]) {
  elements[key] = {hidden:false, textContent:"", children:[],
    append(child){this.children.push(child)},
    replaceChildren(){this.children=[]}};
}
global.document = {
  getElementById: key => elements[key] || null,
  createElement: tag => ({tag, textContent:"", className:""})
};
const panel = require("./web/app/paper-ws-health.js");
const report = JSON.parse(fs.readFileSync(0, "utf8"));
assert.equal(panel.validateReport(report),report);
panel.install(report);
assert.equal(elements["paper-ws-health-status"].textContent,"Amostra degradada");
assert.equal(elements["paper-ws-health-empty"].hidden,true);
assert.equal(elements["paper-ws-health-loaded"].hidden,false);
const rendered = elements["paper-ws-health-rows"].children.map(x=>x.textContent).join("\n");
assert.ok(rendered.includes("Dados sintéticos de testes offline"));
assert.ok(rendered.includes("Degradada ou incompleta"));
assert.ok(rendered.includes("Cotações da posição avaliadas: 1"));
assert.ok(rendered.includes("Posições fora do Top 50: 1"));
assert.ok(rendered.includes("O navegador não está conectado"));
assert.ok(!rendered.includes("BTCUSDT"));
function bad(change){
  const data=structuredClone(report);
  change(data);
  assert.throws(()=>panel.validateReport(data),/inválido/);
}
bad(x=>x.orders_sent=true);
bad(x=>x.native_stop_verified=true);
bad(x=>x.source_authenticated=true);
bad(x=>x.approved_for_signals=true);
bad(x=>x.universe_health_sufficient_for_new_entries=true);
bad(x=>x.data_mode="live_order_execution");
bad(x=>x.real_market_frames_verified=true);
bad(x=>x.preack_frames_bootstrapped_after_ack=999);
bad(x=>x.preack_frames_bootstrapped_after_ack=-1);
bad(x=>{x.subscriptions_acknowledged=0; x.preack_frames_bootstrapped_after_ack=1});
const legacy=structuredClone(report);
delete legacy.preack_frames_bootstrapped_after_ack;
assert.equal(panel.validateReport(legacy),legacy);
bad(x=>x.paper_coverage_gate.full_universe_required_for_existing_exits=true);
bad(x=>x.paper_coverage_gate.mode="complete_fresh_scope_current_ws_session_only");
bad(x=>x.paper_coverage_gate.quote_frames_delivered_to_paper=999);
bad(x=>x.fresh_distinct_contracts_at_end=999);
bad(x=>x.unique_distinct_contracts_observed=999);
bad(x=>x.finite_coverage_fresh_at_end=true);
bad(x=>x.paper_monitoring.orders_sent=true);
bad(x=>x.paper_monitoring.decision_counts.paper_stop_reserved=-5);
bad(x=>x.paper_monitoring.configured_positions=99);
bad(x=>x.some_private_symbol="BTCUSDT");
console.log("D412_WS_PAPER_HEALTH_PANEL_PASS");
"""


class PaperWSHealthMobileD412Tests(unittest.TestCase):
    def make_report(self):
        case = J2J4CurrentN50PaperD410Tests(
            "test_missing_unrelated_n50_contract_does_not_block_valid_paper_partial"
        )
        case.setUp()
        try:
            result, _, _ = case.run_once([ack(), ticker("BTCUSDT", bid="101")])
        finally:
            case.doCleanups()
        self.assertEqual(result["paper_coverage_gate"]["quote_frames_delivered_to_paper"],1)
        self.assertFalse(result["finite_coverage_observed_once"])
        return result

    @unittest.skipUnless(shutil.which("node"), "Node required for JS renderer")
    def test_actual_paper_auto4_report_renders_without_fabricated_market_health(self):
        report = self.make_report()
        check = subprocess.run(
            ["node","-e",NODE],input=json.dumps(report),text=True,
            cwd=ROOT,capture_output=True,timeout=20,
        )
        self.assertEqual(check.returncode,0,check.stderr)
        self.assertIn("D412_WS_PAPER_HEALTH_PANEL_PASS",check.stdout)

    def test_view_has_no_network_or_browser_storage_primitives(self):
        src = (ROOT/"web/app/paper-ws-health.js").read_text(encoding="utf-8")
        for forbidden in (
            "innerHTML", "document.write", "XMLHttpRequest",
            "localStorage.", "sessionStorage.", "indexedDB.",
            "new WebSocket", "sendBeacon", "eval(",
        ):
            self.assertNotIn(forbidden,src)
        html=(ROOT/"web/app/index.html").read_text(encoding="utf-8")
        # D422 permits exactly one SAME-ORIGIN readonly loopback GET.
        self.assertEqual(src.count('global.fetch("/api/n50-public-health"'), 1)
        self.assertIn('loc.port === "8765"', src)
        app=(ROOT/"web/app/app.js").read_text(encoding="utf-8")
        self.assertIn('id="paper-ws-health-status"',html)
        self.assertIn('id="paper-ws-health-rows"',html)
        self.assertIn('src="./paper-ws-health.js"',html)
        self.assertIn("globalThis.CIAPaperWSHealth.install(payload)",app)
        self.assertNotIn("Live stop confirmado",src)


if __name__=="__main__":
    unittest.main()
