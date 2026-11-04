"""OPS29: 30-hour fake-transport WS lease and transitive journal soak tests.

No Bybit network, service activation, owner REST journal, trade or live order.
The test SQLite is a synthetic tempfile and is removed by its test fixture.
"""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.bybit_closed_stream_cache import (
    HOUR_MS, SQLiteOfflineClosedStreamJournal,
)
from crypto_intelligence_agent.bybit_ws_supervisor import (
    WSRunBudget, supervise_ws_research,
)
from crypto_intelligence_agent.j1_ws_hourly_continuity import (
    checkpoint_from_audit,
)
from crypto_intelligence_agent.j1_ws_multihour_soak import (
    audit_ws_multihour_soak,
)
from test_j1_bybit_closed_stream_cache import (
    DECISION, scope, message,
)
from test_j1_ws_supervisor import FakeClock, Session

SYMBOLS = ("BTCUSDT", "ETHUSDT")
ACK = {
    "op": "subscribe", "success": True, "ret_msg": "subscribe",
    "conn_id": "offline", "req_id": "cia-ws-1",
}
FIRST = DECISION - 24 * HOUR_MS


class MultihourSoakTests(unittest.TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.journal = SQLiteOfflineClosedStreamJournal.create(
            Path(self.folder.name) / "multihour-fixture.sqlite")
        self.scope = scope()

    def lease(self, hour, *, early=(), post=SYMBOLS, disconnect=False,
              bad_ack=False, malformed=None, budget=None):
        start = FIRST + hour * HOUR_MS
        received = start + HOUR_MS + 2000
        fake = FakeClock()
        fake.utc = received
        responses = [
            (message(symbol, start), received) for symbol in early
        ]
        responses.append(
            dict(ACK, req_id="bad") if bad_ack else dict(ACK))
        if disconnect:
            responses.append(OSError("transport dropped after ACK"))
            first = Session(fake, responses=responses)
            recovered = Session(fake, responses=[
                dict(ACK),
                *[(message(symbol, start), received) for symbol in post],
            ])
            sessions = [first, recovered]
        else:
            responses.extend(
                (message(symbol, start), received) for symbol in post)
            if malformed is not None:
                responses.append(malformed)
            sessions = [Session(fake, responses=responses)]
        queue = list(sessions)
        with patch("socket.create_connection", side_effect=AssertionError("no network")):
            result = supervise_ws_research(
                session_factory=lambda: queue.pop(0),
                scope=self.scope, journal=self.journal,
                budget=budget or WSRunBudget(2 if disconnect else 1, 100, 25),
                clock=fake.clock, wall_ms=fake.wall_ms, sleeper=fake.sleep,
            )
        self.assertTrue(all(x.closed for x in sessions))
        self.assertEqual(len(queue), 0)
        self.assertEqual(result.sanitized_report()["http_gets"], 0)
        self.assertFalse(result.sanitized_report()["orders_sent"])
        return result

    def audit(self, decision_hour):
        decision = FIRST + (decision_hour + 1) * HOUR_MS
        audit = self.journal.audit(
            scope=self.scope, decision_at_ms=decision,
            as_of_ms=decision + 3000)
        return audit, checkpoint_from_audit(
            audit=audit, decision_at_ms=decision,
            observed_at_ms=decision + 3000,
            expected_contracts=2, scope=self.scope,
        )

    def complete_30_hours(self, *, recovery_hour=None, preack_hour=None):
        checkpoints = []
        reports = []
        for hour in range(30):
            result = self.lease(
                hour,
                early=("BTCUSDT",) if hour == preack_hour else (),
                disconnect=hour == recovery_hour,
            )
            self.assertEqual(result.status, "ws_budget_ended_research_only")
            self.assertEqual(result.closed_events_appended, 2)
            self.assertEqual(result.identical_replays, 0)
            if hour >= 23:
                audit, checkpoint = self.audit(hour)
                self.assertEqual(audit.missing_24h_symbols, 0)
                self.assertEqual(audit.complete_24h_symbols, 2)
                checkpoints.append(checkpoint)
                reports.append(result)
        return tuple(checkpoints), tuple(reports)

    def test_30_hour_warmup_seven_consecutive_closed_windows(self):
        checkpoints, reports = self.complete_30_hours(
            recovery_hour=25, preack_hour=27)
        output = audit_ws_multihour_soak(
            checkpoints=checkpoints, leases=reports)
        self.assertEqual(output.status,
                         "local_multihour_soak_consistent_unverified")
        self.assertEqual(output.consecutive_closed_hours, 7)
        self.assertEqual(output.expected_contracts, 2)
        self.assertEqual(output.observed_closed_events, 14)
        self.assertEqual(output.acknowledged_leases, 7)
        self.assertEqual(output.recovered_connections, 1)
        self.assertEqual(output.preack_frames_discarded, 1)
        final_audit, _ = self.audit(29)
        self.assertEqual(final_audit.persisted_rows, 60)
        assert_report = output.sanitized_report()
        self.assertTrue(assert_report["local_fixture_soak_consistent"])
        for key in (
            "source_authenticated", "marketwide_top50_verified",
            "continuous_collector_authorized", "worker_running_verified",
            "canonical_ohlcv_approved", "live_trading_authorized",
        ):
            self.assertFalse(assert_report[key])
        self.assertEqual(assert_report["network_requests"], 0)
        serialized = json.dumps(assert_report)
        for secret in ("BTCUSDT", "ETHUSDT", str(FIRST), "10.00", "2.50"):
            self.assertNotIn(secret, serialized)

    def test_preack_close_does_not_fill_missing_hour(self):
        for hour in range(23):
            self.assertEqual(self.lease(hour).closed_events_appended, 2)
        last = self.lease(23, early=("ETHUSDT",), post=("BTCUSDT",))
        self.assertEqual(last.preack_frames_discarded, 1)
        self.assertEqual(last.closed_events_appended, 1)
        audit, cp = self.audit(23)
        self.assertEqual(audit.missing_24h_symbols, 1)
        self.assertEqual(audit.complete_24h_symbols, 1)
        self.assertEqual(audit_ws_multihour_soak(
            checkpoints=(cp,) * 7, leases=(last,) * 7).status,
            "local_multihour_soak_abstain")

    def test_replay_is_idempotent_but_not_fresh_closed_hour(self):
        self.assertEqual(self.lease(0).closed_events_appended, 2)
        replay = self.lease(0)
        self.assertEqual(replay.closed_events_appended, 0)
        self.assertEqual(replay.identical_replays, 2)
        self.assertEqual(replay.status, "ws_budget_ended_research_only")
        self.assertFalse(replay.sanitized_report()["marketwide_top50_verified"])

    def test_candle_conflict_timestamp_and_malformed_fail_stop(self):
        f = message("BTCUSDT", FIRST)
        f["data"][0]["turnover"] = "2.51"
        self.assertEqual(self.lease(0).closed_events_appended, 2)
        # Even a schema-compatible replay with changed OHLCV is forbidden.
        fake = FakeClock()
        fake.utc = FIRST + HOUR_MS + 2000
        session = Session(fake, responses=[
            dict(ACK), (f, fake.utc),
        ])
        with patch("socket.create_connection",
                   side_effect=AssertionError("no network")):
            result = supervise_ws_research(
                session_factory=lambda: session, scope=self.scope,
                journal=self.journal, budget=WSRunBudget(1, 20, 25),
                clock=fake.clock, wall_ms=fake.wall_ms, sleeper=fake.sleep,
            )
        self.assertEqual(result.status, "ws_fail_closed_abstain")
        self.assertEqual(result.closed_events_appended, 0)
        self.assertEqual(result.sessions_attempted, 1)
        self.assertEqual(self.lease(1, bad_ack=True).status,
                         "ws_fail_closed_abstain")
        f = message("BTCUSDT", FIRST + 2 * HOUR_MS)
        f["data"][0]["timestamp"] = f["data"][0]["end"] + 100
        fake = FakeClock()
        at = FIRST + 3 * HOUR_MS + 2000
        fake.utc = at
        session = Session(fake, responses=[dict(ACK), (f, at)])
        with patch("socket.create_connection",
                   side_effect=AssertionError("no network")):
            bad = supervise_ws_research(
                session_factory=lambda: session, scope=self.scope,
                journal=self.journal, budget=WSRunBudget(1, 20, 25),
                clock=fake.clock, wall_ms=fake.wall_ms, sleeper=fake.sleep,
            )
        self.assertEqual(bad.status, "ws_fail_closed_abstain")
        self.assertEqual(bad.closed_events_appended, 0)

    def test_missing_hour_cannot_be_hidden_by_subsequent_reconnection(self):
        for hour in range(23):
            self.lease(hour)
        self.lease(23, post=("BTCUSDT",))
        # At the next closed UTC hour, ETH has a gap and must not fill
        # itself retroactively. Explicit gap mode is not enabled here.
        z = self.lease(24, post=("ETHUSDT",))
        self.assertEqual(z.status, "ws_fail_closed_abstain")
        self.assertEqual(z.sessions_attempted, 1)
        audit, _ = self.audit(23)
        self.assertEqual(audit.missing_24h_symbols, 1)

    def test_tampered_or_nonconsecutive_checkpoints_fail_atomic(self):
        cps, reports = self.complete_30_hours()
        cases = (
            tuple(list(cps[:3]) + [replace(cps[3],
                private_scope_fingerprint=("other",))] + list(cps[4:])),
            tuple(list(cps[:3]) + [replace(cps[3],
                decision_at_ms=cps[3].decision_at_ms + HOUR_MS)] + list(cps[4:])),
            tuple(list(cps[:3]) + [replace(cps[3],
                missing_contracts=1)] + list(cps[4:])),
            tuple(list(cps[:3]) + [replace(cps[3],
                rank_digest_sha256=None)] + list(cps[4:])),
        )
        for changed in cases:
            out = audit_ws_multihour_soak(
                checkpoints=changed, leases=reports)
            self.assertEqual(out.status, "local_multihour_soak_abstain")
            self.assertEqual(out.consecutive_closed_hours, 0)
            self.assertEqual(out.observed_closed_events, 0)
        for change in (
            {"status": "ws_fail_closed_abstain", "failure_category": "integrity"},
            {"sessions_fully_acknowledged": 0},
            {"closed_events_appended": 1},
            {"early_frames_buffered": 1},
            {"identical_replays": 2},
            {"reconnects": 99},
        ):
            with self.subTest(change=change):
                broken = list(reports)
                broken[3] = replace(broken[3], **change)
                out = audit_ws_multihour_soak(
                    checkpoints=cps, leases=tuple(broken))
                self.assertEqual(out.status, "local_multihour_soak_abstain")
                self.assertEqual(out.consecutive_closed_hours, 0)

    def test_input_budgets_and_no_ack_fail_closed(self):
        cps, reports = self.complete_30_hours()
        self.assertEqual(audit_ws_multihour_soak(
            checkpoints=cps[:6], leases=reports[:6]).status,
            "local_multihour_soak_abstain")
        self.assertEqual(audit_ws_multihour_soak(
            checkpoints=cps, leases=reports[:-1]).status,
            "local_multihour_soak_abstain")
        self.assertEqual(audit_ws_multihour_soak(
            checkpoints=cps, leases=reports,
            minimum_hours=True).status,
            "local_multihour_soak_abstain")
        self.assertEqual(audit_ws_multihour_soak(
            checkpoints=cps * 11, leases=reports * 11).status,
            "local_multihour_soak_abstain")
        self.assertEqual(self.lease(31, bad_ack=True).status,
                         "ws_fail_closed_abstain")


if __name__ == "__main__":
    unittest.main()
