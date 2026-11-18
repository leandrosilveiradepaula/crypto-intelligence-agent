"""D422: private D421 health -> LOOPBACK-only GET -> local-only browser updates.

No real sockets to exchanges, account credentials or order endpoints. This
suite checks POSIX file ownership, symlinks, freshness, HTTP restrictions,
manual import priority, and suppression of old health after a failed poll.
"""
from __future__ import annotations

from contextlib import closing
from http.client import HTTPConnection
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
from threading import Thread
import time
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.j2_public_n50_health_cycles_d421 import (
    project_public_health, publish_private_health,
)
from crypto_intelligence_agent.j5_local_health_reader_d422 import (
    HealthUnavailable, read_local_health, validate_local_health,
)
from scripts import serve_j5_local_readonly as server
from test_j2_public_n50_health_cycles_d421 import source

ROOT = Path(__file__).resolve().parents[1]


def sample(*, age_ms=5_000, fresh=49):
    now = time.time_ns() // 1_000_000
    report = project_public_health(
        source(fresh=fresh), sampled_at_ms=now - age_ms, cycle=1,
    )
    return report, now


class HealthReaderContractTests(unittest.TestCase):
    def test_strict_present_degraded_sample_and_old_age_rejected(self):
        report, now = sample()
        actual = validate_local_health(report, now_ms=now)
        self.assertEqual(actual["fresh_at_sample_end"], 49)
        self.assertEqual(actual["expired_at_sample_end"], 1)
        self.assertFalse(actual["signals_authorized"])
        self.assertFalse(actual["continuous_24x7_verified"])
        for delta in (180_001, -5_001):
            with self.subTest(delta=delta), self.assertRaises(HealthUnavailable):
                validate_local_health(report, now_ms=report["sampled_at_ms"] + delta)

    def test_noncausal_counts_flags_and_hidden_fields_rejected(self):
        report, now = sample()
        changes = (
            {"orders_sent": True},
            {"signals_authorized": True},
            {"source_authenticated": True},
            {"continuous_24x7_verified": True},
            {"requested_contracts": 49},
            {"fresh_at_sample_end": 50},
            {"expired_at_sample_end": 0},
            {"received_ineligible": 2},
            {"source_secret": "BTCUSDT"},
            {"data_mode": "injected_offline_fixture"},
            {"status": "source_unavailable"},
            {"status": "finite_sample_all_fresh_at_end"},
            {"heartbeat_pongs": 3},
            {"subscription_acks": 0},
            {"frames_accepted": 0},
            {"sample_seconds": float("nan")},
            {"cycle": True},
        )
        for altered in changes:
            with self.subTest(altered=altered), self.assertRaises(HealthUnavailable):
                validate_local_health({**report, **altered}, now_ms=now)
        self.assertNotIn("BTCUSDT", json.dumps(validate_local_health(report, now_ms=now)))

    def test_full_sample_still_no_trading_or_live_assertion(self):
        report, now = sample(fresh=50)
        result = validate_local_health(report, now_ms=now)
        self.assertEqual(result["status"], "finite_sample_all_fresh_at_end")
        for flag in ("orders_sent", "source_authenticated",
                     "signals_authorized", "continuous_24x7_verified"):
            self.assertFalse(result[flag])


@unittest.skipUnless(os.name == "posix", "owner DAC reader is POSIX-only")
class OwnerFileSecurityTests(unittest.TestCase):
    def test_atomic_owner_snapshot_is_visible_without_secret_and_mtime_fresh(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            folder.chmod(0o700)
            report, now = sample()
            publish_private_health(folder, report)
            result = read_local_health(directory=folder, now_ms=now)
            self.assertEqual(result, report)
            self.assertFalse(result["source_authenticated"])
            self.assertNotIn("/home/", json.dumps(result))
            self.assertEqual(stat.S_IMODE((folder / "latest-n50-public-health.json").stat().st_mode), 0o600)

    def test_refuses_world_readability_symlinks_and_expired_file(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            folder.chmod(0o700)
            report, now = sample()
            publish_private_health(folder, report)
            file = folder / "latest-n50-public-health.json"
            file.chmod(0o644)
            with self.assertRaises(HealthUnavailable):
                read_local_health(directory=folder, now_ms=now)
            file.chmod(0o600)
            folder.chmod(0o755)
            with self.assertRaises(HealthUnavailable):
                read_local_health(directory=folder, now_ms=now)
            folder.chmod(0o700)
            file.unlink()
            secret = folder / "some_other_private_file"
            secret.write_text("never leak")
            file.symlink_to(secret)
            with self.assertRaises(HealthUnavailable):
                read_local_health(directory=folder, now_ms=now)
            file.unlink()
            publish_private_health(folder, report)
            old = now - 240_000
            os.utime(file, ns=(old*1_000_000, old*1_000_000))
            with self.assertRaises(HealthUnavailable):
                read_local_health(directory=folder, now_ms=now)
            self.assertEqual(secret.read_text(), "never leak")


class LoopbackHealthHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = server.LoopbackPanelHandler
        cls.previous = cls.app.public_health_directory
        cls.httpd = server.HTTPServer((server.HOST, server.PORT), cls.app)
        cls.worker = Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.worker.start()

    @classmethod
    def tearDownClass(cls):
        cls.app.public_health_directory = cls.previous
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.worker.join(timeout=3)

    def request(self, method, path, host=None, origin=None):
        headers = {}
        if host is not None:
            headers["Host"] = host
        if origin is not None:
            headers["Origin"] = origin
        with closing(HTTPConnection(server.HOST, server.PORT, timeout=5)) as con:
            con.request(method, path, headers=headers)
            response = con.getresponse()
            return response.status, dict(response.getheaders()), response.read()

    def test_endpoint_disabled_by_default_and_no_remote_hosts(self):
        self.app.public_health_directory = None
        with patch.object(server, "read_local_health",
                          side_effect=AssertionError("no DAC access")):
            s, _, body = self.request("GET", "/api/n50-public-health")
        self.assertEqual(s, 503)
        self.assertEqual(json.loads(body)["status"], "local_public_health_disabled")
        self.assertEqual(self.request("POST", "/api/n50-public-health")[0], 405)
        self.assertEqual(self.request("GET", "/api/n50-public-health?secret=1")[0], 404)
        self.assertEqual(self.request("GET", "/api/n50-public-health",
                                      host="external.example:8765")[0], 403)
        self.assertEqual(self.request("GET", "/api/n50-public-health",
                                      origin="https://external.example")[0], 403)

    def test_endpoint_returns_only_validated_0600_projection(self):
        report, _ = sample()
        self.app.public_health_directory = Path("/owner/health")
        try:
            with patch.object(server, "read_local_health", return_value=report) as f:
                status, headers, body = self.request("GET", "/api/n50-public-health")
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body), report)
            self.assertEqual(headers["Cache-Control"], "no-store, max-age=0")
            self.assertEqual(headers["X-Frame-Options"], "DENY")
            self.assertEqual(headers["Cross-Origin-Resource-Policy"], "same-origin")
            self.assertNotIn("Access-Control-Allow-Origin", headers)
            self.assertNotIn("Set-Cookie", headers)
            f.assert_called_once()
            with patch.object(server, "read_local_health",
                              side_effect=HealthUnavailable("private hint")):
                status, _, body = self.request("GET", "/api/n50-public-health")
            self.assertEqual(status, 503)
            self.assertNotIn(b"private hint", body)
        finally:
            self.app.public_health_directory = None

    def test_cli_optins_never_bind_without_directory_owner_permission(self):
        with patch.object(server, "HTTPServer",
                          side_effect=AssertionError("must not bind")):
            for argv in (
                ["--allow-loopback-readonly-http", "--allow-private-health-loopback"],
                ["--allow-loopback-readonly-http", "--private-health-directory", "/nonexistent"],
                ["--allow-loopback-readonly-http", "--allow-private-health-loopback",
                 "--private-health-directory", "/nonexistent"],
            ):
                with self.subTest(argv=argv):
                    self.assertEqual(server.main(argv), 65)


@unittest.skipUnless(shutil.which("node"), "Node needed for browser-local fetch contract")
class MobilePollingD422Tests(unittest.TestCase):
    def test_loopback_only_autorefresh_and_manual_priority(self):
        report, _ = sample()
        js = r"""
const assert = require("node:assert/strict");
const fs = require("node:fs");
const r = JSON.parse(fs.readFileSync(0, "utf8"));
const els = {};
for (const id of ["paper-ws-health-empty", "paper-ws-health-loaded",
                  "paper-ws-health-status", "paper-ws-health-rows"]) {
  els[id] = {hidden:false,textContent:"",children:[],
    append(v){this.children.push(v)},replaceChildren(){this.children=[]}};
}
global.document = {
  getElementById: k => els[k] || null,
  createElement: tag => ({tag,textContent:"",className:""})
};
let fetches = 0;
global.fetch = async () => {
  fetches++;
  return {
    ok:true,status:200,
    headers:{get:()=> "application/json; charset=utf-8"},
    text:async()=> JSON.stringify(r)
  };
};
const health = require("./web/app/paper-ws-health.js");
(async()=>{
  global.location = {protocol:"file:",hostname:"",port:""};
  await health.refreshLocal();
  assert.equal(fetches,0);
  global.location = {protocol:"https:",hostname:"example.net",port:"443"};
  await health.refreshLocal();
  assert.equal(fetches,0);
  global.location = {protocol:"http:",hostname:"127.0.0.1",port:"8766"};
  await health.refreshLocal();
  assert.equal(fetches,0);
  global.location = {protocol:"http:",hostname:"localhost",port:"8765"};
  await health.refreshLocal();
  assert.equal(fetches,1);
  assert.equal(health.hasManualPriority(),false);
  assert.equal(els["paper-ws-health-empty"].hidden,true);
  let text = els["paper-ws-health-rows"].children.map(x=>x.textContent).join("\n");
  assert.ok(text.includes("49 de 50 contratos"));
  assert.ok(text.includes("Servidor local de leitura"));
  assert.ok(!text.includes("BTCUSDT"));
  global.fetch = async()=>{fetches++;throw new Error("source failed with secret");};
  await health.refreshLocal();
  assert.equal(els["paper-ws-health-loaded"].hidden,true);
  assert.equal(els["paper-ws-health-status"].textContent,"Saúde local indisponível");
  assert.ok(!els["paper-ws-health-status"].textContent.includes("secret"));
  health.install(r); // Manual import must win for this tab.
  assert.equal(health.hasManualPriority(),true);
  await health.refreshLocal();
  assert.equal(fetches,2);
  assert.equal(els["paper-ws-health-loaded"].hidden,false);
  health.clearLocal();
  assert.equal(els["paper-ws-health-loaded"].hidden,false);
  global.location = {protocol:"http:",hostname:"127.0.0.1",port:"8765"};
  assert.equal(health.hasManualPriority(),true);
  // A stale server sample cannot be accepted as a fresh automatic status.
  const past = structuredClone(r); past.sampled_at_ms -= 185000;
  assert.throws(()=>health.installLocal(past),/inválido/);
  const forged = structuredClone(r); forged.signals_authorized=true;
  assert.throws(()=>health.installLocal(forged),/inválido/);
  console.log("D422_LOOPBACK_AUTO_POLL_PASS");
})().catch(error=>{console.error(error);process.exitCode=1});
"""
        p = subprocess.run(
            ["node", "-e", js], input=json.dumps(report),
            cwd=ROOT, capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("D422_LOOPBACK_AUTO_POLL_PASS", p.stdout)

    def test_no_new_browser_order_or_external_ws_code(self):
        js = (ROOT / "web/app/paper-ws-health.js").read_text(encoding="utf-8")
        html = (ROOT / "web/app/index.html").read_text(encoding="utf-8")
        self.assertIn('global.fetch("/api/n50-public-health"', js)
        self.assertIn('loc.port === "8765"', js)
        self.assertIn('hasManualPriority()', js)
        self.assertIn('global.setInterval(() => { void refreshLocal(); }, 30000)', js)
        for unsafe in ("new WebSocket", "api.bybit.com", "innerHTML", "eval(",
                       "localStorage.", "sessionStorage.", "POST /v5/order"):
            self.assertNotIn(unsafe, js)
        self.assertIn("servidor local de leitura autorizado", html)


if __name__ == "__main__":
    unittest.main()
