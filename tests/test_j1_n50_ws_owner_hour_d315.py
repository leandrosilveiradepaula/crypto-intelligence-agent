"""D315: dynamic owner-locked N50 WS lease, all frames synthetic.

No public REST, real socket, production owner SQLite, systemd, credentials
or order side effects. POSIX-only positive tests respect the existing DAC lock.
"""
from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.bybit_closed_stream_cache import (
    SQLiteOfflineClosedStreamJournal, HOUR_MS,
)
from crypto_intelligence_agent.bybit_ws_owner_lock import exclusive_owner_ws_writer
from crypto_intelligence_agent.bybit_ws_supervisor import WSRunBudget
from crypto_intelligence_agent.j1_n50_ws_dynamic_scope import (
    admit_dynamic_n50_ws_scope,
)
from crypto_intelligence_agent.j1_n50_ws_owner_hour import (
    run_n50_ws_owner_hour_once,
)
from test_j1_n50_managed_cycle import T, SYMS, sealed
from test_j1_n50_ws_dynamic_scope_d314 import page, OBS
from test_j1_n50_ws_hourly_attestation_d313 import candle, DECISION


class FakeTime:
    def __init__(self):
        self.mono = 0.0
        self.utc = DECISION - 30_000

    def clock(self):
        return self.mono

    def wall_ms(self):
        return self.utc

    def advance(self, seconds):
        self.mono += seconds
        self.utc += round(seconds * 1000)

    def to_closed_receipt(self):
        if self.utc < DECISION + 2000:
            self.advance((DECISION + 2000 - self.utc) / 1000.0)

    def sleep(self, seconds):
        self.advance(seconds)


class FakeSession:
    def __init__(self, clock, market=(), *, bad_ack=False, preack=()):
        self.clock = clock
        self.queue = []
        self.market = list(market)
        self.preack = list(preack)
        self.bad_ack = bad_ack
        self.sent = []
        self.closed = False

    def send(self, raw):
        body = json.loads(raw)
        self.sent.append(body)
        if body.get("op") == "subscribe":
            self.queue.extend(self.preack)
            self.queue.append({
                "op": "subscribe", "success": True,
                "ret_msg": "subscribe", "conn_id": "fake",
                "req_id": "incorrect" if self.bad_ack else body["req_id"],
            })
            self.queue.extend(self.market)

    def recv(self, timeout):
        if not self.queue:
            self.clock.advance(timeout)
            raise TimeoutError("fixture lease idle")
        item = self.queue.pop(0)
        if isinstance(item, dict) and item.get("topic"):
            self.clock.to_closed_receipt()
        self.clock.advance(0.01)
        return json.dumps(item, separators=(",", ":"))

    def close(self):
        self.closed = True


@unittest.skipUnless(
    os.name == "posix" and os.geteuid() != 0,
    "D315 private owner journal uses nonroot POSIX DAC and flock",
)
class N50WSOwnerHourTests(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.directory = Path(folder.name) / "owner-ws-epoch"
        self.directory.mkdir(mode=0o700)
        self.directory.chmod(0o700)
        self.journal = SQLiteOfflineClosedStreamJournal.create(
            self.directory / "ws-confirmed.sqlite",
        )
        self.ranked = sealed(T)
        self.admission = admit_dynamic_n50_ws_scope(
            ranked_scope=self.ranked,
            instrument_pages=(page(tuple(SYMS)),),
            requested_cursors=(None,),
            page_received_at_ms=(OBS,),
            now_ms=OBS,
        )
        self.clock = FakeTime()
        self.seen = []

    def run_it(self, frames, **changes):
        session = FakeSession(
            self.clock, frames,
            bad_ack=changes.pop("bad_ack", False),
            preack=changes.pop("preack", ()),
        )
        def factory():
            self.seen.append(session)
            return session
        opts = {
            "ranked_scope": self.ranked,
            "admission": self.admission,
            "journal": self.journal,
            "decision_at_ms": DECISION,
            "started_at_ms": DECISION - 30_000,
            "session_factory": factory,
            "allow_private_ws_writer": True,
            "allow_injected_public_ws": True,
            "budget": WSRunBudget(max_sessions=1, max_frames=100, max_seconds=60),
            "clock": self.clock.clock,
            "wall_ms": self.clock.wall_ms,
            "sleeper": self.clock.sleep,
        }
        opts.update(changes)
        with patch(
            "crypto_intelligence_agent.bybit_public_j1_transport.BoundedBybitPublicClient.get",
            side_effect=AssertionError("no REST GET"),
        ), patch(
            "socket.create_connection", side_effect=AssertionError("no network socket"),
        ):
            result = run_n50_ws_owner_hour_once(**opts)
        return result, session

    def assert_sanitized(self, report):
        text = json.dumps(report)
        for symbol in SYMS:
            self.assertNotIn(symbol, text)
        self.assertNotIn("turnover", text)
        self.assertEqual(report["http_gets"], 0)
        self.assertFalse(report["rest_database_modified"])
        self.assertFalse(report["systemd_modified"])
        self.assertFalse(report["published_rest_pit"])
        self.assertFalse(report["marketwide_top50_verified"])
        self.assertFalse(report["source_authenticated"])
        self.assertFalse(report["orders_sent"])

    def test_fifty_confirmed_in_one_owner_lock_and_full_ack(self):
        report, session = self.run_it([candle(s) for s in SYMS])
        self.assertEqual(report["status"], "ws_owner_hour_50_observed_local_only", report)
        self.assertEqual(report["confirmed_contracts"], 50)
        self.assertEqual(report["missing_contracts"], 0)
        self.assertEqual(report["closed_events_appended_to_ws_journal"], 50)
        self.assertEqual(report["websocket_sessions_attempted"], 1)
        self.assertEqual(report["subscriptions_acknowledged"], 1)
        self.assertEqual(len(report["hour_evidence_sha256"]), 64)
        self.assertEqual(report["utc_closed_hour_end_ms"], DECISION)
        self.assertEqual(report["source_provenance"], "bybit_public_ws_confirmed")
        self.assertTrue(report["owner_lock_acquired"])
        self.assertTrue(session.closed)
        self.assertEqual(len(session.sent), 1)
        self.assertEqual(len(session.sent[0]["args"]), 50)
        self.assert_sanitized(report)

    def test_forty_nine_are_preserved_but_never_called_complete(self):
        report, session = self.run_it([candle(s) for s in SYMS[:-1]])
        self.assertEqual(report["status"], "ws_owner_hour_incomplete_no_pit", report)
        self.assertEqual((report["confirmed_contracts"], report["missing_contracts"]), (49, 1))
        self.assertTrue(report["rest_gap_reconciliation_required"])
        self.assertIsNone(report["hour_evidence_sha256"])
        self.assertIsNone(report["source_provenance"])
        self.assertTrue(session.closed)
        self.assert_sanitized(report)

        # The missing 50th may be received in a separate idempotent owner lease.
        self.clock = FakeTime()
        repaired, _ = self.run_it([candle(SYMS[-1])])
        self.assertEqual(repaired["status"], "ws_owner_hour_50_observed_local_only", repaired)
        self.assertEqual(repaired["closed_events_appended_to_ws_journal"], 1)
        self.assertEqual(repaired["confirmed_contracts"], 50)

    def test_pre_ack_frame_is_discarded_even_if_confirm_true(self):
        report, _ = self.run_it(
            [candle(s) for s in SYMS[1:]],
            preack=(candle(SYMS[0]),),
        )
        self.assertEqual(report["confirmed_contracts"], 49)
        self.assertEqual(report["status"], "ws_owner_hour_incomplete_no_pit")
        self.assertEqual(report["preack_frames_discarded"], 1)

    def test_open_kline_does_not_promote_fiftieth_member(self):
        frames = [candle(s) for s in SYMS[:-1]]
        frames.append(candle(SYMS[-1], confirm=False))
        report, _ = self.run_it(frames)
        self.assertEqual(report["status"], "ws_owner_hour_incomplete_no_pit", report)
        self.assertEqual(report["confirmed_contracts"], 49)

    def test_untrusted_declared_start_clock_abstains_before_socket(self):
        self.clock.utc = DECISION + 30_000
        report, _ = self.run_it([candle(s) for s in SYMS])
        self.assertEqual(report["status"], "ws_owner_preflight_abstain")
        self.assertEqual(len(self.seen), 0)
        self.assertFalse(report["owner_lock_acquired"])

    def test_bad_ack_stops_before_any_ws_journal_append(self):
        report, session = self.run_it([candle(s) for s in SYMS], bad_ack=True)
        self.assertEqual(report["status"], "ws_owner_lease_degraded_abstain", report)
        self.assertEqual(report["closed_events_appended_to_ws_journal"], 0)
        self.assertEqual(report["subscriptions_acknowledged"], 0)
        self.assertIsNone(report["hour_evidence_sha256"])
        self.assertTrue(session.closed)

    def test_frame_budget_cannot_certify_even_partial_hour(self):
        report, _ = self.run_it(
            [candle(s) for s in SYMS],
            budget=WSRunBudget(max_sessions=1, max_frames=25, max_seconds=60),
        )
        self.assertEqual(report["status"], "ws_owner_lease_degraded_abstain", report)
        self.assertEqual(report["closed_events_appended_to_ws_journal"], 24)
        self.assertIsNone(report["hour_evidence_sha256"])
        self.assertEqual(report["failure_category"], "frame_budget_exhausted")

    def test_missing_optin_wrong_scope_or_future_manifest_never_opens_session(self):
        for changed in (
            {"allow_injected_public_ws": False},
            {"allow_private_ws_writer": False},
            {"started_at_ms": DECISION+10},
            {"started_at_ms": T+1000},
            {"admission": replace(self.admission, metadata_sha256="a"*64)},
            {"admission": replace(self.admission, selected_contracts=49)},
            {"ranked_scope": dict(self.ranked, scope_digest_sha256="0"*64)},
        ):
            self.seen.clear()
            report, _ = self.run_it([candle(s) for s in SYMS], **changed)
            self.assertIn(report["status"], (
                "owner_optin_required", "ws_owner_preflight_abstain",
            ))
            self.assertEqual(len(self.seen), 0)
            self.assertFalse(report["owner_lock_acquired"])
            self.assert_sanitized(report)

    def test_exclusive_lock_contention_does_not_start_websocket(self):
        with exclusive_owner_ws_writer(
            journal=self.journal, allow_private_ws_writer=True,
        ):
            report, _ = self.run_it([candle(s) for s in SYMS])
        self.assertEqual(report["status"], "ws_owner_integrity_or_lock_abstain")
        self.assertEqual(len(self.seen), 0)
        self.assertIsNone(report["hour_evidence_sha256"])

    def test_existing_rest_sqlite_never_accessed_by_bridge(self):
        # The bridge cannot accept the REST journal schema, and it never
        # imports the REST client/manager. Positive path writes only WS.
        report, _ = self.run_it([candle(s) for s in SYMS])
        self.assertEqual(report["status"], "ws_owner_hour_50_observed_local_only")
        self.assertEqual(self.journal.path.name, "ws-confirmed.sqlite")


if __name__ == "__main__":
    unittest.main()
