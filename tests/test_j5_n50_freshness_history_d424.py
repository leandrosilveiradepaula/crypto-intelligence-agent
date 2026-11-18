"""D424: local N50 health history must be bounded, monotonic and read-only."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import unittest

from test_j5_local_public_health_d422 import sample

ROOT = Path(__file__).resolve().parents[1]

NODE = r"""
const assert = require("node:assert/strict");
const fs = require("node:fs");
const base = JSON.parse(fs.readFileSync(0, "utf8"));
const ids = ["paper-ws-health-empty", "paper-ws-health-loaded",
  "paper-ws-health-status", "paper-ws-health-rows",
  "paper-ws-history-box", "paper-ws-history-summary", "paper-ws-history-rows"];
const els = {};
for (const id of ids) {
  els[id] = {hidden: true, textContent: "", children: [],
    append(v){this.children.push(v)},
    replaceChildren(){this.children = []}};
}
global.document = {
  getElementById: key => els[key] || null,
  createElement: tag => ({tag, textContent:"", className:""})
};
const panel = require("./web/app/paper-ws-health.js");
const history = els["paper-ws-history-rows"];
const summary = els["paper-ws-history-summary"];
assert.equal(els["paper-ws-history-box"].hidden, true);
function report(i, fresh=49) {
  const r = structuredClone(base);
  r.sampled_at_ms = base.sampled_at_ms + i * 1000;
  r.fresh_at_sample_end = fresh;
  r.expired_at_sample_end = 50 - fresh;
  r.status = fresh === 50 ? "finite_sample_all_fresh_at_end" :
    "finite_sample_degraded_or_partial";
  return r;
}
panel.installLocal(report(0));
assert.equal(history.children.length, 1);
assert.equal(els["paper-ws-history-box"].hidden, false);
panel.installLocal(report(0)); // same sample is idempotent
assert.equal(history.children.length, 1);
assert.throws(() => panel.installLocal(report(0, 48)), /inválido/);
assert.throws(() => panel.installLocal(report(-1)), /inválido/);
panel.installLocal(report(1, 48));
assert.equal(history.children.length, 2);
assert.ok(summary.textContent.includes("48–49 contratos"));
assert.ok(history.children.every(x => !x.textContent.includes("BTCUSDT")));
panel.clearLocal();
assert.equal(els["paper-ws-health-loaded"].hidden, true);
assert.equal(els["paper-ws-history-box"].hidden, false);
assert.ok(summary.textContent.includes("Leitura atual indisponível"));
panel.installLocal(report(2, 50));
assert.equal(history.children.length, 3);
assert.ok(summary.textContent.includes("48–50 contratos"));
assert.ok(!summary.textContent.includes("Leitura atual indisponível"));
for (let i = 3; i <= 25; i++) panel.installLocal(report(i, 49));
assert.equal(history.children.length, 24);
assert.ok(history.children[0].textContent.includes(
  new Date(base.sampled_at_ms + 2000).toISOString().slice(0,16).replace("T", " ")));
const gap = report(26, 48);
gap.sampled_at_ms += 200000;
panel.installLocal(gap);
assert.equal(history.children.length, 24);
assert.ok(summary.textContent.includes("intervalos acima de 3 min: 1"));
panel.install(report(26));
assert.equal(els["paper-ws-history-box"].hidden, true);
panel.clearLocal();
assert.equal(els["paper-ws-health-loaded"].hidden, false);
console.log("D424_HISTORY_MONOTONIC_PASS");
"""


class N50FreshnessHistoryD424Tests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node required for dashboard history")
    def test_history_replay_reject_and_manual_priority(self):
        source, _ = sample()
        check = subprocess.run(
            ["node", "-e", NODE],
            input=json.dumps(source), text=True, cwd=ROOT,
            capture_output=True, timeout=20,
        )
        self.assertEqual(check.returncode, 0, check.stderr)
        self.assertIn("D424_HISTORY_MONOTONIC_PASS", check.stdout)

    def test_no_extra_market_fetch_or_persistent_storage(self):
        src = (ROOT / "web/app/paper-ws-health.js").read_text(encoding="utf-8")
        html = (ROOT / "web/app/index.html").read_text(encoding="utf-8")
        self.assertEqual(src.count('global.fetch("/api/n50-public-health"'), 1)
        self.assertIn("MAX_LOCAL_HISTORY = 24", src)
        for forbidden in ("new WebSocket", "localStorage.", "sessionStorage.",
                          "indexedDB.", "innerHTML", "eval("):
            self.assertNotIn(forbidden, src)
        for key in ("paper-ws-history-box", "paper-ws-history-summary",
                    "paper-ws-history-rows"):
            self.assertIn('id="' + key + '"', html)


if __name__ == "__main__":
    unittest.main()
