"""D417: finite public Bybit N50 probe -> mobile JS, without live network."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]

NODE = r"""
const assert = require("node:assert/strict");
const fs = require("node:fs");
const keys = ["paper-ws-health-empty", "paper-ws-health-loaded",
              "paper-ws-health-status", "paper-ws-health-rows"];
const elements = {};
for (const key of keys) {
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
assert.equal(panel.acceptsSchema(report.schema_version), true);
assert.equal(panel.acceptsSchema("j2-j4-current-n50-paper-lease-d410-v1"), true);
assert.equal(panel.acceptsSchema("unknown_report"), false);
assert.equal(panel.validateReport(report), report);
panel.install(report);
assert.equal(elements["paper-ws-health-status"].textContent,
  "Amostra N50 com frescor incompleto");
assert.equal(elements["paper-ws-health-empty"].hidden, true);
assert.equal(elements["paper-ws-health-loaded"].hidden, false);
const rendered = elements["paper-ws-health-rows"].children.map(e=>e.textContent).join("\n");
assert.ok(rendered.includes("46 de 50 contratos"));
assert.ok(rendered.includes("Antes elegíveis, agora expirados: 4"));
assert.ok(rendered.includes("Contratos sem cotação validada pós-ACK: 0"));
assert.ok(rendered.includes("Recebidos sem cotação elegível: 0"));
assert.ok(rendered.includes("Callbacks com atraso da exchange superior a 3 s: 0"));
assert.ok(rendered.includes("Posições e stops PAPER: Não avaliados"));
assert.ok(rendered.includes("Dados sintéticos de testes offline"));
assert.ok(rendered.includes("não liberar entradas"));
assert.ok(rendered.includes("não está conectado à VPS nem à Bybit"));
for (const secret of ["BTCUSDT", "sensitive-account", "<script>"])
  assert.ok(!rendered.includes(secret));
function bad(change) {
  const value = structuredClone(report);
  change(value);
  assert.throws(()=>panel.validateReport(value), /inválido/);
}
bad(x=>x.orders_sent=true);
bad(x=>x.approved_for_signals=true);
bad(x=>x.approved_for_live_use=true);
bad(x=>x.continuous_24x7_verified=true);
bad(x=>x.marketwide_top50_verified=true);
bad(x=>x.paper_position_state_changed=true);
bad(x=>x.private_state_modified=true);
bad(x=>x.fresh_contracts_at_end=50);
bad(x=>x.eligible_quote_expired_at_end_contracts=0);
bad(x=>x.never_received_validated_quote_contracts=1);
bad(x=>x.exchange_lagged_quote_callbacks=x.market_frames_accepted+1);
bad(x=>x.ranked_scope_sha256="invalid");
bad(x=>x.owner_scope_members=49);
bad(x=>x.preack_frames_bootstrapped_after_ack=999);
bad(x=>x.finite_coverage_fresh_at_end=true);
bad(x=>x.real_market_frames_verified=true);
bad(x=>x.network_attempted=true);
bad(x=>x.extra_private_id="sensitive-account");
bad(x=>x.schema_version="j2-j4-current-n50-paper-lease-d410-v1");
const liveDeclared = structuredClone(report);
liveDeclared.data_mode = "real_public_websocket";
liveDeclared.network_attempted = true;
liveDeclared.real_market_frames_verified = true;
assert.equal(panel.validateReport(liveDeclared), liveDeclared);
panel.install(liveDeclared);
const declared = elements["paper-ws-health-rows"].children.map(x=>x.textContent).join("\n");
assert.ok(declared.includes("origem do arquivo não autenticada"));
assert.ok(!declared.includes("Origem autenticada"));
console.log("D417_N50_PUBLIC_MOBILE_PASS");
"""

def sample() -> dict:
    """Synthetic count-only contract: 50 delivered, 4 expired, none missing."""
    return {
        "schema_version": "j2-current-owner-n50-ws-probe-d406-v1",
        "status": "lease_completed",
        "failure_category": None,
        "data_mode": "injected_offline_fixture",
        "scope_source": "owner_j1_revalidated_provisional_n50_not_marketwide",
        "ranked_scope_sha256": "a" * 64,
        "metadata_sha256": "b" * 64,
        "elapsed_seconds": 32.003,
        "requested_contracts": 50,
        "ranked_input_count": 50,
        "position_input_count": 0,
        "owner_scope_members": 50,
        "received_distinct_contracts": 50,
        "received_ranked_input_count": 50,
        "received_position_input_count": 0,
        "validated_quote_contracts": 50,
        "never_received_validated_quote_contracts": 0,
        "received_no_eligible_quote_contracts": 0,
        "eligible_quote_expired_at_end_contracts": 4,
        "fresh_contracts_at_end": 46,
        "exchange_lagged_quote_callbacks": 0,
        "exchange_lagged_quote_contracts": 0,
        "freshness_evaluated_by_exchange_timestamp": True,
        "finite_coverage_observed_once": True,
        "finite_coverage_fresh_at_end": False,
        "frames_seen": 5627,
        "market_frames_accepted": 5388,
        "preack_frames_discarded": 237,
        "preack_frames_bootstrapped_after_ack": 237,
        "sessions_attempted": 1,
        "subscription_acks": 1,
        "reconnects": 0,
        "ping_frames": 1,
        "pong_frames": 1,
        "p95_event_lag_bucket": "0_to_100ms",
        "p99_event_lag_bucket": "101_to_1000ms",
        "network_attempted": False,
        "real_market_frames_verified": False,
        "no_service_installed": True,
        "private_state_read": True,
        "private_state_modified": False,
        "quotes_persisted": False,
        "paper_position_state_changed": False,
        "scope_independently_verified": False,
        "crypto_identity_independently_verified": False,
        "marketwide_top50_verified": False,
        "continuous_24x7_verified": False,
        "orders_sent": False,
        "approved_for_signals": False,
        "approved_for_live_use": False,
    }


class J5PublicN50HealthD417Tests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node needed for JS contract test")
    def test_synthetic_d406_report_mobile_and_rejected_frauds(self):
        check = subprocess.run(
            ["node", "-e", NODE], input=json.dumps(sample()), text=True,
            cwd=ROOT, capture_output=True, timeout=20,
        )
        self.assertEqual(check.returncode, 0, check.stderr)
        self.assertIn("D417_N50_PUBLIC_MOBILE_PASS", check.stdout)

    def test_same_local_file_selector_accepts_d406_without_remote_feed(self):
        html = (ROOT / "web/app/index.html").read_text(encoding="utf-8")
        script = (ROOT / "web/app/app.js").read_text(encoding="utf-8")
        display = (ROOT / "web/app/paper-ws-health.js").read_text(encoding="utf-8")
        self.assertIn('src="./paper-ws-health.js"', html)
        self.assertIn('id="paper-ws-health-rows"', html)
        self.assertIn('id="import-file"', html)
        self.assertIn("j2-current-owner-n50-ws-probe-d406-v1", display)
        self.assertIn("globalThis.CIAPaperWSHealth.install(payload)", script)
        self.assertIn("globalThis.CIAPaperWSHealth.acceptsSchema(payload.schema_version)", script)
        # Preserve the 50 KiB-ish Windows source budget even if checkout CRLF
        # expands each LF into two bytes.
        self.assertLess(len(script.encode("utf-8")) + script.count("\n"), 50_000)
        self.assertIn("j2-j4-current-n50-paper-lease-d410-v1", display)
        self.assertIn("j2-j4-current-n50-paper-lease-d410-v1", display)
        self.assertIn("validatePublicProbe", display)
        self.assertIn("fetch(", script)  # unrelated existing browser market read
        self.assertEqual(display.count('global.fetch("/api/n50-public-health"'), 1)
        self.assertIn('loc.port === "8765"', display)
        # The only permitted new fetch is same-origin read-only D421 health.
        for forbidden in (
            "innerHTML", "document.write", "XMLHttpRequest",
            "localStorage.", "sessionStorage.", "indexedDB.",
            "new WebSocket", "sendBeacon", "eval(",
        ):
            self.assertNotIn(forbidden, display)
        self.assertNotIn("POST /v5/order", display)
        self.assertIn("O celular não está conectado à VPS", display)
        self.assertNotIn("<script>", display)


if __name__ == "__main__":
    unittest.main()
