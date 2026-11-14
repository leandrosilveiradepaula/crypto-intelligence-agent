"""J5/MVP1: actual local PAPER math plus offline web contract.

The node tests use only built-in APIs; no JavaScript packages, broker, REST,
SQLite or live market data. Browser interaction is covered by Playwright QA.
"""
from __future__ import annotations

from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "web" / "app"

class _Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
    def handle_starttag(self, name, attrs):
        self.tags.append((name, dict(attrs)))

class AppLayoutContractTests(unittest.TestCase):
    def test_local_app_entrypoint_csp_and_accessible_navigation(self):
        html = (APP / "index.html").read_text(encoding="utf-8")
        parser = _Page()
        parser.feed(html)
        parser.close()
        tags = parser.tags
        self.assertTrue(any(t=="html" and a.get("lang")=="pt-BR" for t,a in tags))
        self.assertTrue(any(t=="meta" and a.get("name")=="viewport" for t,a in tags))
        csp = [a["content"] for t,a in tags
               if t=="meta" and a.get("http-equiv")=="Content-Security-Policy"]
        self.assertEqual(len(csp), 1)
        for rule in ("default-src 'none'", "connect-src 'self'",
                     "script-src 'self'", "form-action 'none'", "base-uri 'none'"):
            self.assertIn(rule, csp[0])
        scripts = [a.get("src") for t,a in tags if t=="script"]
        self.assertEqual(scripts, ["./engine.js", "./app.js"])
        self.assertTrue(any(t=="link" and a.get("href")=="./style.css"
                            for t,a in tags))
        self.assertTrue(any(t=="a" and a.get("href")=="#conteudo"
                            for t,a in tags))
        for section in ("resumo", "mercado", "posicoes", "configuracoes"):
            self.assertTrue(any(t=="section" and a.get("id")==section
                                for t,a in tags))
        self.assertIn('data-live-orders="disabled"', html)
        self.assertIn('PAPER · OFFLINE', html)
        self.assertIn('Não conectado', html)
        self.assertIn("50x", html)
        self.assertNotIn("api.bybit.com", html)

    def test_browser_code_has_no_transport_or_dynamic_html_execution(self):
        for filename in ("engine.js", "app.js"):
            data=(APP / filename).read_text(encoding="utf-8")
            for dangerous in (
                "XMLHttpRequest(", "WebSocket(", "sendBeacon(",
                "eval(", "new Function(", ".innerHTML", "localStorage.clear()",
                "sessionStorage.clear()",
            ):
                self.assertNotIn(dangerous, data, f"{filename}: {dangerous}")
            self.assertNotIn("api.bybit.com", data)
        js = (APP / "app.js").read_text(encoding="utf-8")
        self.assertEqual(js.count('window.fetch("/api/n50-progress"'), 1)
        self.assertEqual(js.count('window.fetch("/api/j2-research"'), 1)
        self.assertIn('researchOrigin === "manual"', js)
        self.assertIn('window.setInterval(() => { void refreshLocalResearch(); }, 300_000);', js)
        self.assertIn('loc.protocol === "http:"', js)
        self.assertIn('loc.port === "8765"', js)
        self.assertIn('loc.hostname === "127.0.0.1"', js)
        self.assertIn('loc.hostname === "localhost"', js)
        self.assertIn('feedOrigin === "manual"', js)
        # Manual JSON has priority even if an earlier local GET resolves later.
        self.assertEqual(js.count('if (researchOrigin === "manual") return;'), 2)
        self.assertEqual(js.count('if (feedOrigin === "manual") return;'), 2)
        self.assertIn('if (researchOrigin === "manual") return; // Import may complete during GET.', js)
        self.assertIn('if (feedOrigin === "manual") return; // Import may complete during GET.', js)
        self.assertLess((APP / "app.js").stat().st_size, 50_000)
        self.assertLess((APP / "style.css").stat().st_size, 40_000)

    @unittest.skipUnless(shutil.which("node"), "optional Node.js offline PAPER arithmetic")
    def test_bigint_paper_partial_and_fixed_leverage_after_settings_change(self):
        script=r"""
const assert = require("node:assert/strict");
const E = require("./web/app/engine.js");
const s = E.emptyState();
const a = E.openPosition(s, {
  symbol:"BTCUSDT",side:"LONG", entry:"100",
  margin:"3", leverage:50, runner:"6",
}, "2026-11-13T18:00:00.000Z");
assert.equal(a.initialUnits,"150000000");
assert.equal(E.grossEntryExposureCents(a),15000n);
for (const [p,quantity] of [["50",75000000n],["60",45000000n],["70",21000000n]]) {
  assert.equal(E.partialExit(a,{basis:"REMAINING_BALANCE",percent:p}),quantity);
  assert.deepEqual(E.validateState(JSON.parse(JSON.stringify(s))),s);
}
assert.equal(a.remainingUnits,"9000000");
assert.equal(a.leverageAtOpen,50);
assert.equal(E.format(a.remainingUnits,8),"0,09");
assert.equal(E.grossEntryExposureCents(a),900n);
assert.equal(E.grossMarkPnlCents(a,"101"),9n);
assert.throws(()=>E.partialExit(a,{basis:"REMAINING_BALANCE",percent:"1"}),/runner/);
s.config.leverage=20;
const b=E.openPosition(s,{
  symbol:"ETHUSDT",side:"SHORT",entry:"100",
  margin:"2",leverage:s.config.leverage,runner:"0"
},"2026-11-13T18:01:00.000Z");
assert.equal(a.leverageAtOpen,50);
assert.equal(b.leverageAtOpen,20);
assert.equal(E.grossMarkPnlCents(b,"99"),40n);
E.closeRunner(a);
assert.equal(a.remainingUnits,"0");
assert.equal(a.status,"CLOSED");
assert.equal(E.validateState(JSON.parse(JSON.stringify(s))).positions.length,2);
s.config.paused = true;
assert.throws(()=>E.openPosition(s,{
  symbol:"XRPUSDT",side:"LONG",entry:"1",
  margin:"1",leverage:50,runner:"0"
}),/Trava local/);
s.config.paused = false;
assert.throws(()=>E.openPosition(s,{
  symbol:"BTCUSDT",side:"LONG",entry:"0",
  margin:"3",leverage:50,runner:"6"
}),/Preço/);
const c=E.openPosition(s,{
  symbol:"SOLUSDT",side:"LONG",entry:"100",
  margin:"1",leverage:10,runner:"0"
});
E.partialExit(c,{basis:"INITIAL_POSITION",percent:"100"});
assert.equal(c.status,"CLOSED");
assert.equal(c.remainingUnits,"0");
assert.equal(E.validateState(JSON.parse(JSON.stringify(s))).positions.length,3);
const corrupted=JSON.parse(JSON.stringify(s));
corrupted.positions[0].remainingUnits="1";
assert.throws(()=>E.validateState(corrupted),/não conservado|inconsistente/);
console.log("J5_MVP1_BIGINT_PAPER_PASS");
"""
        result = subprocess.run(
            [shutil.which("node"), "-e", script],
            cwd=ROOT, text=True, capture_output=True, timeout=15,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("J5_MVP1_BIGINT_PAPER_PASS", result.stdout)


if __name__ == "__main__":
    unittest.main()
