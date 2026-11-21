"""D456 browser status never makes local PAPER a live exchange position."""
from __future__ import annotations
import json
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[1]
NODE=r"""
const assert=require("node:assert/strict");
const fs=require("node:fs");
const status=JSON.parse(fs.readFileSync(0,"utf8"));
const view=require("./web/app/resident-paper.js");
assert.equal(view.accept(status),status);
const fake=(mutate)=>{
  const copy=structuredClone(status);
  mutate(copy);
  assert.throws(()=>view.accept(copy),/inválido/);
};
fake(x=>x.native_stop_verified=true);
fake(x=>x.venue_position_verified=true);
fake(x=>x.lease_now_guaranteed_active=true);
fake(x=>x.uninterrupted_market_coverage_verified=true);
fake(x=>x.real_orders_sent=true);
fake(x=>x.source_mode="authenticated_venue");
fake(x=>x.status="<img>");
fake(x=>x.cycle_attempts=-1);
fake(x=>x.held_only_fallbacks=9999);
fake(x=>x.extra_private_token="abc");
const output={};
const ids=new Map();
global.document={
  getElementById(id) {
    if(!ids.has(id))ids.set(id,{textContent:""});
    return ids.get(id);
  }
};
view.refreshLocal; // no DOM injection; module initialized before DOM.
console.log("D456_RESIDENT_PAPER_BROWSER_PASS");
"""


class D456ResidentPaperBrowserTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"),"Node required for UI contract")
    def test_private_status_browser_rejects_live_claims(self):
        report={
          "schema_version":"j5-resident-paper-readonly-d456-v1",
          "status":"held_only_fallback","sampled_at_ms":1_800_000_000_000,
          "last_reported_at_ms":1_800_000_000_000-1200,
          "cycle_attempts":5,"primary_leases_completed":2,
          "held_only_fallbacks":2,
          "source_mode":"public_research_unverified",
          "lease_now_guaranteed_active":False,
          "uninterrupted_market_coverage_verified":False,
          "native_stop_verified":False,
          "venue_position_verified":False,
          "real_orders_sent":False,
          "approved_for_live_use":False,
        }
        result=subprocess.run(
          ["node","-e",NODE],cwd=ROOT,input=json.dumps(report),
          text=True,capture_output=True,timeout=12,
        )
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn("D456_RESIDENT_PAPER_BROWSER_PASS",result.stdout)
    def test_app_loads_resident_operator_ui(self):
        html=(ROOT/"web/app/index.html").read_text(encoding="utf-8")
        script=(ROOT/"web/app/resident-paper.js").read_text(encoding="utf-8")
        server=(ROOT/"scripts/serve_j5_local_readonly.py").read_text(encoding="utf-8")
        self.assertIn('src="./resident-paper.js"',html)
        self.assertIn('id="resident-paper-status"',html)
        self.assertIn('"/resident-paper.js"',server)
        for unsafe in ("innerHTML","localStorage.","new WebSocket","eval("):
            self.assertNotIn(unsafe,script)

if __name__=="__main__":
    unittest.main()
