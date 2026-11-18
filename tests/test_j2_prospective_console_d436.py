"""D436 integrated proof: supervised fake WS, SQLite, terminal J5 and browser."""
from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import unittest

from crypto_intelligence_agent.bybit_closed_stream_cache import (
    HOUR_MS, SQLiteOfflineClosedStreamJournal,
)
from crypto_intelligence_agent.bybit_ws_supervisor import WSRunBudget
from crypto_intelligence_agent.j2_prospective_bybit_research_d436 import (
    ProspectiveResearchUpdate, consume_confirmed_close_batch,
    publish_projection, read_projection, supervise_prospective_research,
)
from crypto_intelligence_agent.market_data import DataValidationError
from scripts.demo_j2_prospective_bybit_research_d436 import (
    CONFIG, FIRST, SYMBOL, FakeClock, FakeSession,
    _fake_ack, _frame, _opened_frame, _scope, run_supervised_cycle,
)

ROOT = Path(__file__).resolve().parents[1]
NODE = r"""
const assert = require("node:assert/strict");
const examples = JSON.parse(require("node:fs").readFileSync(0, "utf8"));
const label={textContent:""}, detail={textContent:""};
global.document={getElementById:id=>({"live-research-status":label,
  "live-research-detail":detail})[id]};
global.location={protocol:"http:",hostname:"127.0.0.1",port:"8765"};
require("./web/app/prospective-research.js");
const view = global.CIAProspectiveResearch;
const original = examples.research, terminal = examples.terminal;
function ok(v) {
 return {ok:true,status:200,headers:{get:()=> "application/json; charset=utf-8"},
   text:async()=>JSON.stringify(v)};
}
function unavailable(){return {ok:false,status:503,headers:{get:()=> "application/json"}};}
function bad(update){
 const v = structuredClone(original); update(v);
 assert.equal(view.valid(v), false);
 view.render(v);
 assert.equal(label.textContent,"Indisponível");
}
assert.equal(view.valid(original),true);
view.render(original);
assert.match(label.textContent,/LONG/);
assert.match(detail.textContent,/Replay offline/);
assert.equal(view.valid(terminal),true);
view.render(terminal);
assert.match(label.textContent,/Sessão encerrada/);
assert.doesNotMatch(detail.textContent,/oportunidade atual/);
bad(x=>x.orders_sent=true);
bad(x=>x.auto2_called=true);
bad(x=>x.auto4_called=true);
bad(x=>x.risk_gate_called=true);
bad(x=>x.approved_for_signals=true);
bad(x=>x.live_trading_authorized=true);
bad(x=>x.network_attempted=true);
bad(x=>x.source="another_source");
bad(x=>x.status="live_profit_confirmed");
bad(x=>x.session_ended=true);
bad(x=>x.journal_digest_sha256="unsafe");
bad(x=>x.private_token="sensitive");
bad(x=>x.latest_closed_end_ms=x.evaluated_at_ms+1);
(async()=>{
 let count=0;
 global.fetch=async (url,opts)=>{
  count++;
  assert.equal(url,"/api/j2-prospective-research");
  assert.equal(opts.credentials,"omit");
  assert.equal(opts.redirect,"error");
  return ok(original);
 };
 await view.refreshLocal();
 assert.equal(count,1);
 assert.match(label.textContent,/LONG/);
 global.fetch=async()=>ok(terminal);
 await view.refreshLocal();
 assert.equal(label.textContent,"Sessão encerrada");
 global.fetch=async()=>unavailable();
 await view.refreshLocal();
 assert.equal(label.textContent,"Indisponível");
 // A response from an older GET cannot restore stale data after a new 503.
 let release;
 global.fetch=()=>new Promise(resolve=>{release=resolve});
 const old=view.refreshLocal();
 global.fetch=async()=>unavailable();
 await view.refreshLocal();
 release(ok(original));
 await old;
 assert.equal(label.textContent,"Indisponível");
 // An invalid or oversized 200 is also a fail-closed status.
 global.fetch=async()=>ok({...original,orders_sent:true});
 await view.refreshLocal();
 assert.equal(label.textContent,"Indisponível");
 global.fetch=async()=>({
  ok:true,status:200,headers:{get:()=> "application/json"},
  text:async()=> " ".repeat(5000)
 });
 await view.refreshLocal();
 assert.equal(label.textContent,"Indisponível");
 global.location={protocol:"file:",hostname:"",port:""};
 global.fetch=()=>{throw Error("file previews must never make requests")};
 await view.refreshLocal();
 console.log("D436_SUPERVISED_J5_BROWSER_PASS");
})().catch(error=>{console.error(error);process.exit(1)});
"""


class D436SupervisedSessionTests(unittest.TestCase):
    def seed(self, journal_path):
        scope = _scope()
        SQLiteOfflineClosedStreamJournal.create(journal_path)
        ack = (json.dumps(_fake_ack()), FIRST+1)
        consume_confirmed_close_batch(
            frames=(ack,) + tuple(_frame(i) for i in range(24)),
            journal_path=journal_path, scope=scope, symbol=SYMBOL,
            decision_at_ms=FIRST + 24*HOUR_MS,
            as_of_ms=FIRST + 24*HOUR_MS + 2000, config=CONFIG,
        )
        return scope

    def supervise(self, journal_path, scope, frames, clock, directory=None):
        session = FakeSession(clock, frames)
        report, latest = supervise_prospective_research(
            session_factory=lambda: session, journal_path=journal_path,
            scope=scope, symbol=SYMBOL, config=CONFIG,
            budget=WSRunBudget(1, 25, 3),
            projection_directory=directory,
            clock=clock.clock, wall_ms=clock.wall_ms, sleeper=clock.sleeper,
        )
        self.assertTrue(session.closed)
        self.assertTrue(session.sent and session.sent[0]["op"] == "subscribe")
        return report, latest

    def test_preack_open_confirm_duplicate_restart(self):
        with TemporaryDirectory() as root:
            path = Path(root) / "research.sqlite"
            scope = self.seed(path)
            frame, received = _frame(24)
            payload = json.loads(frame)
            clock = FakeClock(received)
            report, latest = self.supervise(path, scope, (
                (payload, received),  # pre-ACK close is ignored
                (_fake_ack(), received),
                _opened_frame(24),   # never stored as a closed candle
                (payload, received),
                (payload, received), # duplicate is idempotent
            ), clock)
            self.assertEqual(report.preack_frames_discarded, 1)
            self.assertEqual(report.open_updates, 1)
            self.assertEqual(report.closed_events_appended, 1)
            self.assertEqual(report.identical_replays, 1)
            self.assertEqual(latest.status,
                             "observed_long_hypothesis_not_authorized")
            self.assertFalse(latest.sanitized_report()["network_attempted"])
            again, next_result = self.supervise(path, scope, (
                (_fake_ack(), received), (payload, received),
            ), clock)
            self.assertEqual(again.closed_events_appended, 0)
            self.assertEqual(again.identical_replays, 1)
            self.assertIsNone(next_result)

    def test_unacknowledged_or_gapped_session_abstains(self):
        with TemporaryDirectory() as root:
            path = Path(root) / "research.sqlite"
            SQLiteOfflineClosedStreamJournal.create(path)
            scope = _scope()
            frame, received = _frame(24)
            payload = json.loads(frame)
            clock = FakeClock(received)
            report, latest = self.supervise(path, scope, (
                (payload, received), # no ACK and no downstream append
            ), clock)
            self.assertEqual(report.closed_events_appended, 0)
            self.assertIsNone(latest)
            report, latest = self.supervise(path, scope, (
                (_fake_ack(), received), (payload, received),
            ), clock)
            self.assertEqual(report.closed_events_appended, 1)
            self.assertEqual(latest.status, "observed_data_insufficient")
            self.assertFalse(latest.sanitized_report()["approved_for_signals"])

    def test_bad_ack_and_conflicting_duplicate_fail_closed(self):
        with TemporaryDirectory() as root:
            path = Path(root) / "research.sqlite"
            scope = self.seed(path)
            frame, received = _frame(24)
            payload = json.loads(frame)
            clock = FakeClock(received)
            bad_ack = {**_fake_ack(), "success": False}
            report, latest = self.supervise(path, scope, (
                (bad_ack, received), (payload, received),
            ), clock)
            self.assertEqual(report.closed_events_appended, 0)
            self.assertIsNone(latest)
            changed = json.loads(frame)
            changed["data"][0]["close"] = "104"
            report, latest = self.supervise(path, scope, (
                (_fake_ack(), received), (payload, received),
                (changed, received),
            ), clock)
            self.assertEqual(report.closed_events_appended, 1)
            self.assertEqual(report.status, "ws_fail_closed_abstain")


@unittest.skipUnless(os.name == "posix" and os.geteuid() != 0,
                     "owner-only projection requires nonroot POSIX")
class D436OwnerProjectionTests(unittest.TestCase):
    def test_projection_ttl_and_unsafe_files(self):
        with TemporaryDirectory() as root:
            directory = Path(root) / "owner"
            directory.mkdir(mode=0o700)
            directory.chmod(0o700)
            closed_at = FIRST + 25*HOUR_MS
            update = ProspectiveResearchUpdate(
                "observed_no_hypothesis", closed_at,
                closed_at-1, "a"*64, 1, 0, None,
                "offline_protocol_replay", closed_at+2000,
            )
            publish_projection(directory, update)
            self.assertEqual(
                read_projection(directory, now_ms=closed_at+2000)["status"],
                "observed_no_hypothesis",
            )
            with self.assertRaises(DataValidationError):
                read_projection(directory, now_ms=closed_at+122001)
            with self.assertRaises(DataValidationError):
                read_projection(directory, now_ms=closed_at+1999)
            target = directory / "latest-j2-prospective-research.json"
            content = json.loads(target.read_text())
            for key, value in (("orders_sent", True),
                               ("auto4_called", True),
                               ("status", "trading_live"),
                               ("network_attempted", True)):
                with self.subTest(key=key):
                    mutated = dict(content, **{key:value})
                    target.write_text(json.dumps(mutated), encoding="ascii")
                    target.chmod(0o600)
                    with self.assertRaises(DataValidationError):
                        read_projection(directory, now_ms=closed_at+2000)
            target.write_text(json.dumps(content) + "\n" +
                              json.dumps(content), encoding="ascii")
            target.chmod(0o600)
            with self.assertRaises((ValueError, DataValidationError)):
                read_projection(directory, now_ms=closed_at+2000)
            target.write_text('{"status":"safe","status":"unsafe"}')
            target.chmod(0o600)
            with self.assertRaises(DataValidationError):
                read_projection(directory, now_ms=closed_at+2000)
            target.chmod(0o644)
            with self.assertRaises(DataValidationError):
                read_projection(directory, now_ms=closed_at+2000)
            target.unlink()
            target.symlink_to(directory / "missing")
            with self.assertRaises((OSError, DataValidationError)):
                read_projection(directory, now_ms=closed_at+2000)
            with self.assertRaises(DataValidationError):
                publish_projection(directory, update)

    def test_terminal_readable_briefly_never_active(self):
        proof = run_supervised_cycle()
        self.assertEqual(proof["terminal"]["status"], "observed_session_ended")
        self.assertTrue(proof["terminal"]["session_ended"])
        self.assertFalse(proof["terminal"]["orders_sent"])


class D436BrowserTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node required for browser contract QA")
    def test_browser_polls_without_manual_json_and_revokes_stale(self):
        result = run_supervised_cycle()
        terminal = result["terminal"]
        if terminal is None:
            terminal = {
                **result["research"], "status": "observed_session_ended",
                "session_ended": True, "session_ended_at_ms":
                result["research"]["last_frame_received_ms"],
                "failure_category": "session_finished",
            }
        run = subprocess.run(
            ["node", "-e", NODE], text=True, cwd=ROOT, timeout=30,
            input=json.dumps({"research":result["research"], "terminal":terminal}),
            capture_output=True,
        )
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("D436_SUPERVISED_J5_BROWSER_PASS", run.stdout)
        html = (ROOT / "web/app/index.html").read_text(encoding="utf-8")
        app = (ROOT / "web/app/app.js").read_text(encoding="utf-8")
        self.assertIn('src="./prospective-research.js"', html)
        self.assertIn("CIAProspectiveResearch.refreshLocal()", app)


if __name__ == "__main__":
    unittest.main()
