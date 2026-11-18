"""D421: safe count-only Bybit sample projection and bounded cycle publisher."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest

from crypto_intelligence_agent.j2_public_n50_health_cycles_d421 import (
    exclusive_private_health_lock, project_public_health,
    publish_private_health, run_readonly_health_cycles,
)
from crypto_intelligence_agent.market_data import DataValidationError

NOW = 1_800_000_000_000
ROOT = Path(__file__).resolve().parents[1]


def source(*, fresh=45, mode="real_public_websocket") -> dict:
    expired = 50 - fresh
    return {
        "schema_version": "j2-current-n50-sustained-market-observation-d418-v1",
        "status": "sustained_market_observed_once",
        "data_mode": mode,
        "source_authenticated": False, "no_service_installed": True,
        "private_state_modified": False,
        "paper_position_state_changed": False,
        "paper_reservations_enabled": False,
        "quotes_persisted": False, "orders_sent": False,
        "approved_for_signals": False, "approved_for_live_use": False,
        "continuous_24x7_verified": False,
        "marketwide_top50_verified": False,
        "owner_scope_unchanged_after_lease": True,
        "full_finite_duration_observed": True,
        "finite_current_owner_scope_observed_once": True,
        "finite_coverage_fresh_at_end": fresh == 50,
        "real_market_frames_verified": mode == "real_public_websocket",
        "requested_distinct_contracts": 50,
        "unique_distinct_contracts_observed": 50,
        "validated_quote_contracts": 50,
        "fresh_distinct_contracts_at_end": fresh,
        "eligible_quote_expired_at_end_contracts": expired,
        "never_received_validated_quote_contracts": 0,
        "received_no_eligible_quote_contracts": 0,
        "subscriptions_acknowledged": 1, "reconnects": 0,
        "heartbeat_pings": 2, "heartbeat_pongs": 2,
        "ticker_frames_accepted": 12_006,
        "exchange_lagged_quote_callbacks": 0,
        "observation_elapsed_seconds": 62.107,
        # Only the upstream D418 report carries these sensitive identifiers.
        "ranked_scope_sha256": "a" * 64,
        "metadata_sha256": "b" * 64,
        "arbitrary_future_private_field": "secret-account",
    }


class PublicHealthProjectionD421Tests(unittest.TestCase):
    def test_d418_producer_uses_subscriptions_acknowledged_not_d406_alias(self):
        # The first real pilot of D421 failed closed because the new adapter
        # accidentally expected D406's subscription_acks. D418 actually
        # produces subscriptions_acknowledged; this is the exact producer key.
        raw = source()
        self.assertIn("subscriptions_acknowledged", raw)
        self.assertNotIn("subscription_acks", raw)
        report = project_public_health(raw, sampled_at_ms=NOW, cycle=1)
        self.assertEqual(report["subscription_acks"], 1)
        wrong = dict(raw)
        wrong["subscription_acks"] = wrong.pop("subscriptions_acknowledged")
        with self.assertRaises(DataValidationError):
            project_public_health(wrong, sampled_at_ms=NOW, cycle=1)

    def test_real_45_of_50_degraded_not_approved(self):
        r = project_public_health(source(), sampled_at_ms=NOW, cycle=1)
        self.assertEqual(r["status"], "finite_sample_degraded_or_partial")
        self.assertEqual(r["observed_contracts"], 50)
        self.assertEqual(r["fresh_at_sample_end"], 45)
        self.assertEqual(r["expired_at_sample_end"], 5)
        self.assertEqual(r["freshness_limit_ms"], 3000)
        for name in ("signals_authorized", "orders_sent",
                     "continuous_24x7_verified", "source_authenticated"):
            self.assertIs(r[name], False)
        self.assertTrue(r["finite_sample_only"])
        serialized = json.dumps(r, sort_keys=True)
        for secret in ("secret-account", "aaaaaaaaaaaa", "bbbbbbbbbbbb",
                       "BTCUSDT", "mark_price", "/home/cia-probe"):
            self.assertNotIn(secret, serialized)

    def test_full_sample_does_not_claim_continuous_or_signals(self):
        r = project_public_health(source(fresh=50), sampled_at_ms=NOW, cycle=2)
        self.assertEqual(r["status"], "finite_sample_all_fresh_at_end")
        self.assertEqual(r["fresh_at_sample_end"], 50)
        self.assertTrue(r["finite_sample_only"])
        self.assertFalse(r["continuous_24x7_verified"])
        self.assertFalse(r["signals_authorized"])

    def test_injected_fixture_is_never_real_full_fresh(self):
        r = project_public_health(
            source(fresh=50, mode="injected_offline_fixture"),
            sampled_at_ms=NOW, cycle=1,
        )
        self.assertEqual(r["data_mode"], "injected_offline_fixture")
        self.assertEqual(r["status"], "finite_sample_degraded_or_partial")

    def test_hostile_flags_and_broken_count_partitions_rejected(self):
        bad = (
            {"approved_for_signals": True},
            {"orders_sent": True},
            {"private_state_modified": True},
            {"paper_position_state_changed": True},
            {"continuous_24x7_verified": True},
            {"source_authenticated": True},
            {"no_service_installed": False},
            {"requested_distinct_contracts": 49},
            {"unique_distinct_contracts_observed": 49},
            {"fresh_distinct_contracts_at_end": 49},
            {"eligible_quote_expired_at_end_contracts": 0},
            {"validated_quote_contracts": 49},
            {"observation_elapsed_seconds": float("nan")},
            {"subscriptions_acknowledged": 0},
            {"heartbeat_pongs": 3},
            {"finite_coverage_fresh_at_end": True},
            {"status": "trading_enabled"},
            {"data_mode": "private_account_api"},
        )
        for change in bad:
            with self.subTest(change=change), self.assertRaises(DataValidationError):
                project_public_health({**source(), **change},
                                      sampled_at_ms=NOW, cycle=1)
        for clock in (True, 0, NOW+3_000_000_000_000):
            with self.subTest(clock=clock), self.assertRaises(DataValidationError):
                project_public_health(source(), sampled_at_ms=clock, cycle=1)

    def test_unavailable_sample_supersedes_previous_healthy_sample(self):
        values = []
        attempts = iter((source(fresh=50), OSError("private path inside error"),
                         source(fresh=45)))
        sleeps = []
        def probe():
            x = next(attempts)
            if isinstance(x, Exception):
                raise x
            return x
        result = run_readonly_health_cycles(
            cycles=3, probe=probe, publisher=values.append,
            clock_ms=lambda: NOW, sleeper=sleeps.append, gap_seconds=4,
        )
        self.assertEqual(result["cycles_published"], 3)
        self.assertEqual(result["degraded_samples"], 2)
        self.assertEqual(sleeps, [4, 4])
        self.assertEqual([r["status"] for r in values],
                         ["finite_sample_all_fresh_at_end",
                          "source_unavailable", "finite_sample_degraded_or_partial"])
        self.assertEqual(values[1]["fresh_at_sample_end"], 0)
        self.assertNotIn("private path inside error", json.dumps(values))
        self.assertFalse(result["orders_sent"])

    def test_publisher_failure_is_not_masked_as_success(self):
        def publisher(_):
            raise OSError("write failed")
        with self.assertRaises(OSError):
            run_readonly_health_cycles(
                cycles=2, probe=lambda: source(), publisher=publisher,
                clock_ms=lambda: NOW, sleeper=lambda _: None,
            )

    def test_invalid_limits_rejected_before_any_probe(self):
        for n in (0, 25, True, "forever"):
            with self.subTest(n=n), self.assertRaises(DataValidationError):
                run_readonly_health_cycles(
                    cycles=n, probe=lambda: self.fail("unexpected probe"),
                    publisher=lambda _: self.fail("unexpected write"),
                    clock_ms=lambda: NOW,
                )

    def test_missing_cli_optins_abstain_before_state_or_network(self):
        with tempfile.TemporaryDirectory() as dirpath:
            proc = subprocess.run(
                [sys.executable, "-m",
                 "scripts.observe_j2_public_n50_health_cycles_d421",
                 "--state-directory", str(Path(dirpath) / "private-absent"),
                 "--output-directory", str(Path(dirpath) / "private-absent")],
                cwd=ROOT, capture_output=True, text=True, timeout=20,
            )
        self.assertEqual(proc.returncode, 77, proc.stderr)
        report = json.loads(proc.stdout)
        self.assertFalse(report["network_attempted"])
        self.assertFalse(report["health_file_written"])
        self.assertFalse(report["orders_sent"])


@unittest.skipUnless(shutil.which("node"), "Node required for mobile JS renderer test")
class MobileHealthImportD421Tests(unittest.TestCase):
    def test_same_mobile_import_displays_finite_health_and_rejects_fraud(self):
        js = r"""
const assert = require("node:assert/strict");
const fs = require("node:fs");
const ids = ["paper-ws-health-empty", "paper-ws-health-loaded",
             "paper-ws-health-status", "paper-ws-health-rows"];
const el = {};
for (const key of ids) {
  el[key] = {textContent:"", hidden:false, children:[],
    replaceChildren(){this.children=[]},
    append(x){this.children.push(x)}};
}
global.document = {
  getElementById:key=>el[key]||null,
  createElement:tag=>({tag,textContent:"",className:""})
};
const health = require("./web/app/paper-ws-health.js");
const r = JSON.parse(fs.readFileSync(0, "utf8"));
assert.equal(health.acceptsSchema(r.schema_version), true);
assert.equal(health.acceptsSchema("j2-current-owner-n50-ws-probe-d406-v1"), true);
assert.equal(health.acceptsSchema("j2-j4-current-n50-paper-lease-d410-v1"), true);
assert.equal(health.acceptsSchema("not-a-contract"), false);
assert.equal(health.validateReport(r), r);
health.install(r);
assert.equal(el["paper-ws-health-empty"].hidden, true);
assert.equal(el["paper-ws-health-loaded"].hidden, false);
assert.ok(el["paper-ws-health-status"].textContent.includes("frescor insuficiente"));
const display = el["paper-ws-health-rows"].children.map(x=>x.textContent).join("\n");
for(const phrase of [
  "Cobertura observada: 50 de 50 contratos",
  "Frescos no encerramento: 45 de 50 contratos",
  "Antes elegíveis, agora expirados: 5",
  "Estado das entradas: Não autorizadas",
  "não é dado ao vivo", "não está conectado à VPS",
  "Posições e saídas PAPER: Não avaliadas"
]) assert.ok(display.includes(phrase), phrase);
for(const secret of ["secret-account", "BTCUSDT", "aaaaaaaaaaaa", "mark_price"])
  assert.ok(!display.includes(secret));
function bad(change) {
  const sample = structuredClone(r); change(sample);
  assert.throws(()=>health.validateReport(sample), /inválido/);
}
bad(x=>x.orders_sent=true);
bad(x=>x.signals_authorized=true);
bad(x=>x.continuous_24x7_verified=true);
bad(x=>x.source_authenticated=true);
bad(x=>x.sampled_at_ms=0);
bad(x=>x.fresh_at_sample_end=50);
bad(x=>x.expired_at_sample_end=0);
bad(x=>x.status="finite_sample_all_fresh_at_end");
bad(x=>x.heartbeat_pongs=100);
bad(x=>x.data_mode="private_account");
bad(x=>x.owner_extra_field="secret-account");
bad(x=>delete x.source_authenticated);
console.log("D421_MOBILE_IMPORT_PASS");
"""
        report = project_public_health(source(), sampled_at_ms=NOW, cycle=1)
        run = subprocess.run(
            ["node", "-e", js], input=json.dumps(report), text=True,
            cwd=ROOT, capture_output=True, timeout=20,
        )
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("D421_MOBILE_IMPORT_PASS", run.stdout)

    def test_existing_file_import_route_needs_no_extra_network_or_bundles(self):
        app = (ROOT / "web" / "app" / "app.js").read_text(encoding="utf-8")
        display = (ROOT / "web" / "app" / "paper-ws-health.js").read_text(encoding="utf-8")
        self.assertIn("globalThis.CIAPaperWSHealth.acceptsSchema(payload.schema_version)", app)
        self.assertIn("j2-public-n50-finite-health-d421-v1", display)
        self.assertEqual(display.count('global.fetch("/api/n50-public-health"'), 1)
        self.assertIn('loc.port === "8765"', display)
        for forbidden in ("innerHTML", "new WebSocket", "XMLHttpRequest",
                          "localStorage.", "sessionStorage.", "eval("):
            self.assertNotIn(forbidden, display)


@unittest.skipUnless(os.name == "posix", "owner-only file privacy needs POSIX")
class PrivateHealthFileD421Tests(unittest.TestCase):
    def test_atomic_private_publication_replaces_snapshot(self):
        with tempfile.TemporaryDirectory() as d:
            directory = Path(d)
            directory.chmod(0o700)
            first = project_public_health(source(fresh=50),
                                          sampled_at_ms=NOW, cycle=1)
            second = project_public_health(source(fresh=45),
                                           sampled_at_ms=NOW+65_000, cycle=2)
            publish_private_health(directory, first)
            publish_private_health(directory, second)
            target = directory / "latest-n50-public-health.json"
            self.assertTrue(target.is_file())
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
            self.assertEqual(json.loads(target.read_text()), second)
            self.assertEqual(set(p.name for p in directory.iterdir()),
                             {"latest-n50-public-health.json"})
            self.assertNotIn("secret-account", target.read_text())

    def test_refuses_public_output_directory_and_preexisting_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            report = project_public_health(source(), sampled_at_ms=NOW, cycle=1)
            folder.chmod(0o755)
            with self.assertRaises(DataValidationError):
                publish_private_health(folder, report)
            folder.chmod(0o700)
            victim = folder / "victim"
            victim.write_text("untouched")
            (folder / "latest-n50-public-health.json").symlink_to(victim)
            with self.assertRaises(DataValidationError):
                publish_private_health(folder, report)
            self.assertEqual(victim.read_text(), "untouched")

    def test_file_lock_blocks_second_writer(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            folder.chmod(0o700)
            first = exclusive_private_health_lock(folder)
            try:
                with self.assertRaises(BlockingIOError):
                    exclusive_private_health_lock(folder)
            finally:
                os.close(first)
            again = exclusive_private_health_lock(folder)
            os.close(again)
            self.assertEqual(
                stat.S_IMODE((folder / ".n50-public-health.lock").stat().st_mode),
                0o600,
            )


if __name__ == "__main__":
    unittest.main()
