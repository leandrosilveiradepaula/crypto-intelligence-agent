"""D427: terminal, count-only PAPER watch for local mobile J5.

Never connects Bybit or modifies a position journal. The example source is
a strict D410-shaped PAPER REPORT, not a venue trade confirmation.
"""
from __future__ import annotations

from contextlib import closing
from http.client import HTTPConnection
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
from threading import Thread
import time
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout

from crypto_intelligence_agent.j5_paper_watch_d427 import (
    PaperWatchUnavailable, project_finite_paper_lease,
    unavailable_finite_paper_lease, publish_paper_watch,
    read_paper_watch, validate_paper_watch,
)
from crypto_intelligence_agent.market_data import DataValidationError
from scripts import serve_j5_local_readonly as server
from scripts import run_j4_current_paper_ws_once_d425 as operator

ROOT = Path(__file__).resolve().parents[1]


def fake_source(*, reserved=1, reconcile=241):
    return {
        "schema_version": "j2-j4-current-n50-paper-lease-d410-v1",
        "status": "finite_paper_lease_degraded_or_incomplete",
        "data_mode": "real_public_websocket",
        "underlying_ws_status": "lease_completed",
        "orders_sent": False,
        "approved_for_live_use": False, "native_stop_verified": False,
        "continuous_24x7_verified": False,
        "universe_health_sufficient_for_new_entries": False,
        "owner_scope_unchanged_after_lease": True,
        "real_market_frames_verified": True,
        "subscriptions_acknowledged": 1,
        "ticker_frames_accepted": 243,
        "paper_monitoring": {
            "schema_version": "paper-intrahour-quote-router-d391-v1",
            "configured_positions": 1,
            "orders_sent": False, "native_stop_verified": False,
            "approved_for_live_use": False,
            "decision_counts": {
                "paper_stop_reserved": reserved,
                "paper_stop_reconciliation_required": reconcile,
            },
            # Deliberate private data in producer MUST NOT be re-exported.
            "private_position_id": "fixture_secret_123",
        },
        "paper_coverage_gate": {
            "mode": "fresh_held_position_quote_independent_of_n50",
            "quote_frames_delivered_to_paper": 242,
            "quote_frames_deferred": 0,
            "full_universe_required_for_existing_exits": False,
            "orders_sent": False, "approved_for_live_use": False,
        },
        "another_hidden_field": "BTCUSDT",
    }


def sample(*, delta_ms=1500):
    now = time.time_ns() // 1_000_000
    return project_finite_paper_lease(
        fake_source(), sampled_at_ms=now-delta_ms,
    ), now


class D427ProjectionTests(unittest.TestCase):
    def test_real_market_paper_reservation_is_count_only_not_protection(self):
        report, now = sample()
        self.assertEqual(report, validate_paper_watch(report, now_ms=now))
        self.assertEqual(report["hypothetical_reservations_observed"], 1)
        self.assertEqual(report["reconciliation_events_observed"], 241)
        self.assertEqual(report["quote_events_forwarded"], 242)
        self.assertTrue(report["finite_lease_ended"])
        self.assertFalse(report["continuous_supervision_verified"])
        self.assertFalse(report["native_stop_verified"])
        self.assertFalse(report["full_position_coverage_verified"])
        self.assertFalse(report["orders_sent"])
        self.assertNotIn("BTCUSDT", json.dumps(report))
        self.assertNotIn("fixture_secret", json.dumps(report))

    def test_malicious_projection_flags_and_frames_fail_closed(self):
        source = fake_source()
        now = time.time_ns() // 1_000_000
        mutated = (
            {"orders_sent": True},
            {"approved_for_live_use": True},
            {"data_mode": "injected_offline_fixture"},
            {"real_market_frames_verified": "true"},
            {"underlying_ws_status": "fabricated_complete"},
            {"ticker_frames_accepted": 1},
            {"subscriptions_acknowledged": 0},
            {"paper_monitoring": {**source["paper_monitoring"],
                                  "configured_positions": 0}},
            {"paper_monitoring": {**source["paper_monitoring"],
                                  "decision_counts": {"unknown": 1}}},
            {"paper_coverage_gate": {**source["paper_coverage_gate"],
                                     "quote_frames_delivered_to_paper": 1}},
        )
        for change in mutated:
            with self.subTest(change=change), self.assertRaises(DataValidationError):
                project_finite_paper_lease({**source, **change}, sampled_at_ms=now)

    def test_strict_file_status_fails_when_old_or_forged(self):
        sample_report, now = sample()
        bad = (
            {"native_stop_verified": True},
            {"orders_sent": True},
            {"continuous_supervision_verified": True},
            {"finite_lease_ended": False},
            {"configured_position_routes": True},
            {"configured_position_routes": 200},
            {"hypothetical_reservations_observed": 99},
            {"status": "active_protection_verified"},
            {"private_symbol": "BTCUSDT"},
            {"market_lease_completed": "true"},
        )
        for change in bad:
            with self.subTest(change=change), self.assertRaises(PaperWatchUnavailable):
                validate_paper_watch({**sample_report, **change}, now_ms=now)
        with self.assertRaises(PaperWatchUnavailable):
            validate_paper_watch(sample_report,
                                 now_ms=sample_report["sampled_at_ms"] + 180001)
        with self.assertRaises(PaperWatchUnavailable):
            validate_paper_watch(sample_report,
                                 now_ms=sample_report["sampled_at_ms"] - 5001)

    def test_failed_closed_writer_never_claims_coverage(self):
        now = time.time_ns() // 1_000_000
        value = unavailable_finite_paper_lease(sampled_at_ms=now)
        self.assertEqual(value["status"], "finite_paper_lease_failed_closed")
        self.assertEqual(value["configured_position_routes"], 0)
        self.assertFalse(value["market_lease_completed"])
        self.assertFalse(value["orders_sent"])
        self.assertEqual(validate_paper_watch(value, now_ms=now), value)


@unittest.skipUnless(os.name == "posix" and hasattr(os, "geteuid")
                     and os.geteuid() != 0, "owner 0700/0600 POSIX only")
class D427OwnerFileTests(unittest.TestCase):
    def test_owner_output_is_atomic_0600_and_read_only(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            home.chmod(0o700)
            report, now = sample()
            publish_paper_watch(home, report)
            target = home / "latest-paper-watch.json"
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
            self.assertEqual(read_paper_watch(directory=home, now_ms=now), report)
            # Replace with an explicit fail-closed status after an exception.
            failure = unavailable_finite_paper_lease(sampled_at_ms=now)
            publish_paper_watch(home, failure)
            self.assertEqual(read_paper_watch(directory=home, now_ms=now), failure)

    def test_dac_symlink_hardlink_and_stale_target_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            home.chmod(0o700)
            report, now = sample()
            publish_paper_watch(home, report)
            target = home / "latest-paper-watch.json"
            target.chmod(0o644)
            with self.assertRaises(PaperWatchUnavailable):
                read_paper_watch(directory=home, now_ms=now)
            target.chmod(0o600)
            home.chmod(0o755)
            with self.assertRaises(PaperWatchUnavailable):
                read_paper_watch(directory=home, now_ms=now)
            home.chmod(0o700)
            target.unlink()
            secret = home / "unrelated-private-file"
            secret.write_text("do-not-serve")
            target.symlink_to(secret)
            with self.assertRaises(PaperWatchUnavailable):
                read_paper_watch(directory=home, now_ms=now)
            with self.assertRaises(DataValidationError):
                publish_paper_watch(home, report)
            target.unlink()
            publish_paper_watch(home, report)
            hardlink = home / "another-link"
            os.link(target, hardlink)
            with self.assertRaises(PaperWatchUnavailable):
                read_paper_watch(directory=home, now_ms=now)
            target.unlink()
            hardlink.unlink()
            publish_paper_watch(home, report)
            old = now - 240001
            os.utime(target, ns=(old*1_000_000, old*1_000_000))
            with self.assertRaises(PaperWatchUnavailable):
                read_paper_watch(directory=home, now_ms=now)


class D427LoopbackEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = server.LoopbackPanelHandler
        cls.old = cls.app.paper_watch_directory
        cls.httpd = server.HTTPServer((server.HOST, server.PORT), cls.app)
        cls.thread = Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.app.paper_watch_directory = cls.old
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=3)

    @staticmethod
    def http(method="GET", path="/api/paper-watch", host=None, origin=None):
        headers = {}
        if host is not None:
            headers["Host"] = host
        if origin is not None:
            headers["Origin"] = origin
        with closing(HTTPConnection(server.HOST, server.PORT, timeout=5)) as connection:
            connection.request(method, path, headers=headers)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()

    def test_optout_hosts_and_wrong_methods_are_closed(self):
        self.app.paper_watch_directory = None
        with patch.object(server, "read_paper_watch",
                          side_effect=AssertionError("watch should not read")):
            status, _, body = self.http()
        self.assertEqual(status, 503)
        self.assertEqual(json.loads(body)["status"], "paper_watch_not_enabled")
        self.assertEqual(self.http("POST")[0], 405)
        self.assertEqual(self.http(path="/api/paper-watch?x=1")[0], 404)
        self.assertEqual(self.http(host="remote.example:8765")[0], 403)
        self.assertEqual(self.http(origin="https://remote.example")[0], 403)

    def test_strict_200_only_or_sanitized_503(self):
        report, _ = sample()
        self.app.paper_watch_directory = Path("/owner/private/watch")
        try:
            with patch.object(server, "read_paper_watch", return_value=report) as reader:
                status, headers, body = self.http()
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body), report)
            self.assertEqual(headers["Cache-Control"], "no-store, max-age=0")
            self.assertEqual(headers["X-Frame-Options"], "DENY")
            self.assertNotIn("Access-Control-Allow-Origin", headers)
            reader.assert_called_once()
            with patch.object(server, "read_paper_watch",
                              side_effect=PaperWatchUnavailable("private path")):
                status, _, body = self.http()
            self.assertEqual(status, 503)
            self.assertNotIn(b"private path", body)
        finally:
            self.app.paper_watch_directory = None

    def test_missing_cli_pair_never_binds_or_reads_directory(self):
        with patch.object(server, "HTTPServer",
                          side_effect=AssertionError("should not bind")):
            self.assertEqual(server.main([
                "--allow-loopback-readonly-http",
                "--allow-paper-watch-loopback",
            ]), 65)
            self.assertEqual(server.main([
                "--allow-loopback-readonly-http",
                "--paper-watch-directory", "/never-read",
            ]), 65)

    def test_paper_operator_requires_explicit_export_pair(self):
        argv = [
            "--state-directory", "/not-readable",
            "--private-paper-directory", "/not-readable",
            "--allow-private-pointer-read", "--allow-public-websocket",
            "--confirm-personal-readonly-research", "--confirm-region-eligible",
            "--allow-synthetic-paper-reservations",
        ]
        if os.name != "posix" or (hasattr(os, "geteuid") and os.geteuid() == 0):
            self.skipTest("POSIX nonroot CLI")
        with redirect_stdout(io.StringIO()), patch.object(
            operator, "observe_existing_paper_positions_once",
            side_effect=AssertionError("must not observe"),
        ):
            self.assertEqual(operator.main(argv + [
                "--allow-local-paper-watch-output",
            ]), 65)
            self.assertEqual(operator.main(argv + [
                "--paper-watch-directory", "/never-read",
            ]), 65)


@unittest.skipUnless(shutil.which("node"), "Node needed for PAPER client QA")
class D427MobileClientTests(unittest.TestCase):
    def test_no_false_green_and_failed_poll_clears_last_session(self):
        r, _ = sample()
        js = r"""
const assert = require("node:assert/strict");
const fs = require("node:fs");
const base = JSON.parse(fs.readFileSync(0, "utf8"));
const now = base.sampled_at_ms + 2000;
Date.now = () => now;
const elements = {};
for (const id of ["paper-watch-empty", "paper-watch-loaded",
  "paper-watch-status", "paper-watch-rows",
  "paper-watch-summary", "paper-watch-warning"]) {
  elements[id] = {hidden:true,textContent:"",children:[],
    append(x){this.children.push(x)},replaceChildren(){this.children=[]}};
}
global.document = {
  getElementById: id => elements[id] || null,
  createElement: tag => ({tag,textContent:"",className:"",
    children:[],append(...args){this.children.push(...args)}})
};
global.location = {protocol:"file:",hostname:"",port:""};
const panel = require("./web/app/paper-watch.js");
assert.equal(elements["paper-watch-loaded"].hidden, true);
panel.installLocal(base);
assert.equal(elements["paper-watch-loaded"].hidden, false);
assert.ok(elements["paper-watch-status"].textContent.includes("encerrada"));
assert.ok(elements["paper-watch-summary"].textContent.includes("não existe proteção contínua"));
assert.ok(elements["paper-watch-warning"].textContent.includes("reconciliação"));
assert.equal(elements["paper-watch-rows"].children.length, 6);
assert.throws(()=>panel.validateReport({...base,native_stop_verified:true}));
assert.throws(()=>panel.validateReport({...base,secret:"BTCUSDT"}));
assert.throws(()=>panel.validateReport({...base,quote_events_forwarded:1}));
assert.throws(()=>panel.validateReport(base,base.sampled_at_ms+180001));
let requests=0;
global.location = {protocol:"http:",hostname:"localhost",port:"8765"};
global.fetch = async (url,opts)=>{
  requests++;
  assert.equal(url,"/api/paper-watch");
  assert.equal(opts.method,"GET");
  assert.equal(opts.credentials,"omit");
  return {ok:false,status:503,headers:{get:()=>"application/json"},text:async()=>""};
};
(async()=>{
  await panel.refreshLocal();
  assert.equal(requests,1);
  assert.equal(elements["paper-watch-loaded"].hidden,true);
  assert.ok(elements["paper-watch-status"].textContent.includes("Sem supervisão"));
  assert.ok(!elements["paper-watch-summary"].textContent);
  console.log("D427_PAPER_WATCH_FAIL_CLOSED_PASS");
})().catch(e=>{console.error(e);process.exitCode=1});
"""
        result = subprocess.run(
            ["node", "-e", js], cwd=ROOT, text=True,
            input=json.dumps(r), capture_output=True, timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("D427_PAPER_WATCH_FAIL_CLOSED_PASS", result.stdout)

    def test_no_injected_trading_or_browser_storage(self):
        src = (ROOT / "web/app/paper-watch.js").read_text(encoding="utf-8")
        html = (ROOT / "web/app/index.html").read_text(encoding="utf-8")
        service = (ROOT / "scripts/serve_j5_local_readonly.py").read_text(
            encoding="utf-8")
        self.assertEqual(src.count('global.fetch("/api/paper-watch"'), 1)
        for forbidden in ("new WebSocket", "localStorage.", "sessionStorage.",
                          "innerHTML", "eval(", "create_order"):
            self.assertNotIn(forbidden, src)
        self.assertIn('src="./paper-watch.js"', html)
        self.assertIn('id="paper-watch-status"', html)
        self.assertIn('"/paper-watch.js":', service)
        self.assertIn('self.path == "/api/paper-watch"', service)


if __name__ == "__main__":
    unittest.main()
