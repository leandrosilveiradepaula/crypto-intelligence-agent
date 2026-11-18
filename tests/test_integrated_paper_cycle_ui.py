"""D431: actual offline PRE9 lifecycle -> strict J5 browser renderer contract."""
from pathlib import Path
import json
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
NODE = r"""
const assert = require("node:assert/strict");
const input = JSON.parse(require("node:fs").readFileSync(0, "utf8"));
const box = {
  hidden: true, children: [],
  append(...items){ this.children.push(...items); },
  replaceChildren(){ this.children = []; }
};
global.document = {
  getElementById: id => id === "integrated-cycle" ? box : null,
  createElement: tag => ({tag, textContent:""})
};
require("./web/app/integrated-paper-cycle.js");
const renderer = global.CIAIntegratedPaperCycle;
renderer.install(input);
assert.equal(box.hidden, false);
assert.equal(box.children.length, 3);
assert.match(box.children[0].textContent, /somente simulação/);
assert.match(box.children[1].textContent, /1.88/);
assert.match(box.children[2].textContent, /bloqueadas/);
function bad(change) {
  const report = structuredClone(input);
  change(report);
  assert.throws(() => renderer.install(report), /inválido/);
  assert.equal(box.hidden, true);
  assert.equal(box.children.length, 0);
}
bad(x => x.orders_sent = true);
bad(x => x.live_trading_authorized = true);
bad(x => x.market_data_real = true);
bad(x => x.financial_pnl_available = true);
bad(x => x.native_stop_verified = true);
bad(x => x.network_requests = 1);
bad(x => x.restart_duplicate_orders = 1);
bad(x => x.confirmed_remaining_units = "9999");
bad(x => x.partial_exit_units = "NaN");
bad(x => x.opening_units = "<script>injection</script>");
bad(x => x.stop_outage_research.hypothetical_only = false);
bad(x => x.stages[0] = "forged");
bad(x => x.extra_claim = "BTCUSDT");
console.log("D431_INTEGRATED_PAPER_UI_PASS");
"""


class IntegratedPaperCycleUiTests(unittest.TestCase):
    def test_console_has_local_read_only_renderer(self):
        html = (ROOT / "web/app/index.html").read_text(encoding="utf-8")
        app = (ROOT / "web/app/app.js").read_text(encoding="utf-8")
        renderer = (ROOT / "web/app/integrated-paper-cycle.js").read_text(encoding="utf-8")
        self.assertIn('src="./integrated-paper-cycle.js"', html)
        self.assertIn('j6_full_offline_paper_lifecycle_v1', app)
        self.assertIn("CIAIntegratedPaperCycle.install(payload)", app)
        for required in (
            "orders_sent === false", "live_trading_authorized === false",
            "market_data_real === false", "financial_pnl_available === false",
            "restart_duplicate_orders === 0", "Ciclo integrado reproduzido",
        ):
            self.assertIn(required, renderer)
        self.assertIn('"/api/integrated-paper-cycle"', renderer)
        self.assertNotIn("innerHTML", renderer)

    @unittest.skipUnless(shutil.which("node"), "Node is required for DOM-only import")
    def test_actual_pre9_report_renders_and_forged_variants_fail_closed(self):
        from scripts.demo_full_offline_paper_lifecycle import run_full_offline_paper_lifecycle
        report = run_full_offline_paper_lifecycle()
        result = subprocess.run(
            ["node", "-e", NODE], cwd=ROOT, text=True,
            input=json.dumps(report), capture_output=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("D431_INTEGRATED_PAPER_UI_PASS", result.stdout)



    @unittest.skipUnless(shutil.which("node"), "Node required for local polling")
    def test_local_poll_revokes_previous_result_and_ignores_late_response(self):
        from scripts.demo_full_offline_paper_lifecycle import run_full_offline_paper_lifecycle
        report = run_full_offline_paper_lifecycle()
        code = r"""
const assert = require("node:assert/strict");
const base = JSON.parse(require("node:fs").readFileSync(0, "utf8"));
const box = {hidden:true,children:[],append(...xs){this.children.push(...xs)},
  replaceChildren(){this.children=[]}};
global.document = {
  getElementById: id => id === "integrated-cycle" ? box : null,
  createElement: tag => ({tag, textContent:""})
};
require("./web/app/integrated-paper-cycle.js");
const view = global.CIAIntegratedPaperCycle;
global.location = { protocol:"http:", hostname:"127.0.0.1", port:"8765" };
let requested = [];
global.fetch = async (url,opts) => {
  requested.push({url,opts});
  return {ok:true,headers:{get:()=> "application/json; charset=utf-8"},
    text:async()=>JSON.stringify(base)};
};
(async()=>{
  await view.refreshLocal();
  assert.equal(box.children.length,3);
  assert.equal(box.hidden,false);
  assert.equal(requested[0].url,"/api/integrated-paper-cycle");
  assert.equal(requested[0].opts.credentials,"omit");
  assert.equal(requested[0].opts.redirect,"error");
  global.fetch=async()=>({ok:false,headers:{get:()=> "application/json"}});
  await view.refreshLocal();
  assert.equal(box.children.length,1);
  assert.match(box.children[0].textContent,/indisponível/);
  global.fetch=async()=>({ok:true,headers:{get:()=> "application/json"},
    text:async()=>JSON.stringify({...base,orders_sent:true})});
  await view.refreshLocal();
  assert.equal(box.children.length,1);
  assert.match(box.children[0].textContent,/indisponível/);
  let release;
  global.fetch=()=>new Promise(resolve=>{release=resolve});
  const delayed=view.refreshLocal();
  global.fetch=async()=>({ok:false,headers:{get:()=> "application/json"}});
  await view.refreshLocal();
  release({ok:true,headers:{get:()=> "application/json"},text:async()=>JSON.stringify(base)});
  await delayed;
  assert.equal(box.children.length,1);
  assert.match(box.children[0].textContent,/indisponível/);
  global.location={protocol:"file:",hostname:"",port:""};
  global.fetch=()=>{throw Error("file previews must not fetch")};
  await view.refreshLocal();
  console.log("D432_POLL_FAIL_CLOSED_PASS");
})().catch(e=>{console.error(e);process.exit(1)});
"""
        result = subprocess.run(
            ["node", "-e", code], cwd=ROOT, text=True,
            input=json.dumps(report), capture_output=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("D432_POLL_FAIL_CLOSED_PASS", result.stdout)

if __name__ == "__main__":
    unittest.main()
