"""D470 browser local-only last lease: historical market != current PAPER."""
from __future__ import annotations
import json
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=r"""
const assert=require('node:assert/strict');
const fs=require('node:fs');
const fixture=JSON.parse(fs.readFileSync(0,'utf8'));
const ui=require('./web/app/last-public-paper-lease.js');
assert.equal(ui.accept(fixture),fixture);
const changed=(mutate)=>{
  const value=structuredClone(fixture);
  mutate(value);
  assert.throws(()=>ui.accept(value),/inválida/);
};
changed(v=>v.current_kline_coverage_verified=true);
changed(v=>v.current_ticker_coverage_verified=true);
changed(v=>v.native_stop_verified=true);
changed(v=>v.orders_sent=true);
changed(v=>v.last_lease_recent='true');
changed(v=>v.paper_pending_open_count=-1);
changed(v=>v.public_ticker_callbacks_reported='500');
changed(v=>v.paper_close_callbacks_reported=51);
changed(v=>v.status='<img>');
changed(v=>v.private_token='TEST');
const nodes=new Map();
global.document={getElementById:(id)=>{
  if(!nodes.has(id))nodes.set(id,{textContent:''});
  return nodes.get(id);
}};
ui.view(ui.accept(fixture));
const get=id=>nodes.get(id).textContent;
assert.match(get('last-public-paper-status'),/degradada/);
assert.match(get('last-public-paper-market'),/50/);
assert.match(get('last-public-paper-ticker'),/causa não registrada/);
assert.match(get('last-public-paper-summary'),/Não representa conexão atual/);
assert.doesNotMatch(get('last-public-paper-market'),/stop nativo instalado/);
ui.view(null);
assert.match(get('last-public-paper-status'),/Sem diagnóstico/);
assert.match(get('last-public-paper-ticker'),/indisponível/);
console.log('D470_LAST_LEASE_LOCAL_BROWSER_PASS');
"""

class LastLeaseBrowserTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node required for browser contract")
    def test_legacy_real_d466_projection_is_not_a_live_status(self):
        report = {
            "schema_version": "j5-last-public-paper-lease-d470-v1",
            "status": "finite_public_paper_research_degraded",
            "primary_returned": True,
            "sampled_at_ms": 1_800_000_000_000,
            "last_lease_observed_at_ms": 1_799_999_500_000,
            "last_lease_recent": False,
            "historical_rest_candles_reported": 1200,
            "confirmed_ws_closes_reported": 50,
            "paper_close_callbacks_reported": 50,
            "public_ticker_callbacks_reported": 51045,
            "kline_lease_status": "ws_budget_ended_research_only",
            "ticker_lease_status": "not_reported",
            "kline_failure_category": "none_or_unknown",
            "ticker_failure_category": "none_or_unknown",
            "paper_research_cohort_complete": None,
            "paper_relative_btc_hypotheses": None,
            "paper_pending_open_count": None,
            "paper_cohort_researched_count": None,
            "is_historical_lease_report": True,
            "same_hour_ws_cohort_integrity_independently_verified": False,
            "current_ticker_coverage_verified": False,
            "current_kline_coverage_verified": False,
            "native_stop_verified": False,
            "real_fills_verified": False,
            "orders_sent": False,
            "approved_for_live_use": False,
        }
        result=subprocess.run(
            ["node","-e",SCRIPT],cwd=ROOT,
            input=json.dumps(report),capture_output=True,text=True,timeout=12,
        )
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn("D470_LAST_LEASE_LOCAL_BROWSER_PASS",result.stdout)

    def test_html_asset_is_local_only_and_does_not_inject_markup(self):
        html=(ROOT/"web/app/index.html").read_text(encoding="utf-8")
        server=(ROOT/"scripts/serve_j5_local_readonly.py").read_text(encoding="utf-8")
        script=(ROOT/"web/app/last-public-paper-lease.js").read_text(encoding="utf-8")
        self.assertIn('src="./last-public-paper-lease.js"',html)
        self.assertIn('id="last-public-paper-status"',html)
        self.assertIn('"/last-public-paper-lease.js"',server)
        for banned in ("innerHTML","localStorage.", "new WebSocket", "eval(", "document.cookie"):
            self.assertNotIn(banned,script)


if __name__=="__main__":
    unittest.main()
