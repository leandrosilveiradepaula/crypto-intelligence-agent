"""D444: repeated D443 durable PAPER leases with real backoff/state logic.

No public network, J1, account API or exchange order in CI.
"""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.j4_continuous_paper_worker_d444 import (
    PaperWorkerPolicy, PrivateWorkerStatus, _safe_lease,
    drive_paper_cycles, run_owner_continuous_paper_worker,
)
from crypto_intelligence_agent.market_data import DataValidationError

GOOD = {
    "status": "finite_held_paper_quote_observed_unverified",
    "data_mode": "injected_offline_protocol_replay",
    "held_quote_fresh_at_lease_end": True,
    "held_quote_frames_forwarded": 2,
    "orders_sent": False, "order_submission_enabled": False,
    "approved_for_live_use": False, "new_paper_position_created": False,
    "synthetic_fill_inferred_from_ticker": False, "j1_state_accessed": False,
}


class ContinuousPaperWorkerD444Tests(unittest.TestCase):
    def drive(self, outcomes, *, max_cycles=None, failures=8):
        sequence = iter(outcomes)
        states, sleeps = [], []
        clock = {"t": 1_800_000_000_000}
        def advance(t):
            clock["t"] += int(t * 1000)
            sleeps.append(t)
        def lease():
            clock["t"] += 45_000
            nxt = next(sequence)
            if isinstance(nxt, BaseException):
                raise nxt
            return nxt
        result = drive_paper_cycles(
            policy=PaperWorkerPolicy(max_cycles=(
                max_cycles if max_cycles is not None else len(outcomes)),
                max_consecutive_failures=failures),
            lease_once=lease, now_ms=lambda: clock["t"],
            sleeper=advance, publish=lambda x: states.append(dict(x)),
            should_stop=lambda: False,
        )
        return result, states, sleeps

    def test_successive_leases_preserve_progress_and_restart_without_fake_fill(self):
        end, states, sleeps = self.drive([GOOD, GOOD, GOOD])
        self.assertEqual(end["phase"], "completed_finite_cycles")
        self.assertEqual(end["lease_attempts"], 3)
        self.assertEqual(end["healthy_lease_count"], 3)
        self.assertEqual(end["accepted_quote_events_total"], 6)
        self.assertEqual(sleeps, [1, 1])
        self.assertFalse(end["native_stop_active"])
        self.assertFalse(end["uninterrupted_coverage_verified"])
        self.assertFalse(end["orders_sent"])
        self.assertTrue(any(x["phase"] == "lease_started" for x in states))
        self.assertTrue(all("BTCUSDT" not in json.dumps(x) for x in states))

    def test_backoff_recovery_after_bad_lease_without_counting_fake_coverage(self):
        bad = {**GOOD, "status": "finite_held_paper_degraded_abstain",
               "held_quote_fresh_at_lease_end": False}
        end, states, waits = self.drive([bad, RuntimeError("secret"), GOOD, GOOD])
        self.assertEqual(end["phase"], "completed_finite_cycles")
        self.assertEqual(end["healthy_lease_count"], 2)
        self.assertEqual(end["consecutive_lease_failures"], 0)
        self.assertEqual(waits, [2, 4, 1])
        self.assertNotIn("secret", json.dumps(states))

    def test_stops_after_repeated_degradation_without_endless_retry(self):
        end, _, waits = self.drive([None] * 9, max_cycles=0, failures=3)
        self.assertEqual(end["phase"], "stopped_after_repeated_degradation")
        self.assertEqual(end["lease_attempts"], 3)
        self.assertEqual(waits, [2, 4])

    def test_contradictory_order_or_live_claim_fails_closed_immediately(self):
        for value in ({"orders_sent": True}, {"order_submission_enabled": True},
                      {"approved_for_live_use": True},
                      {"new_paper_position_created": True},
                      {"j1_state_accessed": True},
                      {"synthetic_fill_inferred_from_ticker": True}):
            with self.subTest(value=value):
                end, _, waits = self.drive([{**GOOD, **value}], max_cycles=0)
                self.assertEqual(end["phase"], "failed_closed")
                self.assertEqual(waits, [])

    def test_rejects_missing_or_wrong_source_without_healthy_claim(self):
        for v in ({"data_mode": "public_ws_observed_unverified"},
                  {"held_quote_frames_forwarded": 0},
                  {"held_quote_fresh_at_lease_end": False},
                  {"orders_sent": None}):
            with self.subTest(case=v):
                healthy, unsafe, _ = _safe_lease({**GOOD, **v},
                                                "injected_offline_protocol_replay")
                self.assertFalse(healthy)
        self.assertEqual(_safe_lease(None, "injected_offline_protocol_replay"),
                         (False, False, 0))

    def test_stop_between_leases_does_not_open_extra_network_connection(self):
        states, calls = [], []
        stop = {"value": False}
        end = drive_paper_cycles(
            policy=PaperWorkerPolicy(max_cycles=0),
            lease_once=lambda: (calls.append(1), GOOD)[1],
            now_ms=lambda: 1_800_000_000_000, sleeper=lambda t: None,
            publish=lambda d: states.append(d.copy()),
            should_stop=lambda: stop.update(value=True) is None if calls else False,
        )
        self.assertEqual(end["phase"], "stopped_by_operator")
        self.assertEqual(len(calls), 1)

    def test_optins_deny_before_owner_files_or_network(self):
        with patch("crypto_intelligence_agent.j4_continuous_paper_worker_d444._owner_directory",
                   side_effect=AssertionError("file access without gate")):
            with patch("crypto_intelligence_agent.j4_continuous_paper_worker_d444.observe_existing_held_paper_once",
                       side_effect=AssertionError("network without gate")):
                output = run_owner_continuous_paper_worker(
                    private_paper_directory=Path("/not/read"),
                    status_directory=Path("/not/read"),
                    policy=PaperWorkerPolicy(max_cycles=1))
        self.assertEqual(output["network_attempted"], False)
        self.assertEqual(output["orders_sent"], False)

    def test_invalid_policy_rejected_before_any_lease(self):
        for bad in (PaperWorkerPolicy(max_cycles=1).__dict__ | {"max_retry_seconds": 0},
                    PaperWorkerPolicy(max_cycles=1).__dict__ | {"lease_seconds": 61},
                    PaperWorkerPolicy(max_cycles=1).__dict__ | {"max_consecutive_failures": 0}):
            with self.subTest(bad=bad), self.assertRaises(DataValidationError):
                PaperWorkerPolicy(**bad)

    def test_status_reader_rejects_stale_or_false_protection(self):
        import os
        from crypto_intelligence_agent.j4_continuous_paper_worker_d444 import (
            read_private_worker_status, WorkerStatusUnavailable,
        )
        if os.name != "posix" or os.geteuid() == 0:
            self.skipTest("POSIX nonroot owner only")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            path.chmod(0o700)
            report = self.drive([GOOD])[0]
            with PrivateWorkerStatus(path) as writer:
                writer.publish(report)
            now = report["updated_at_ms"]
            loaded = read_private_worker_status(directory=path, now_ms=now)
            self.assertEqual(loaded["healthy_lease_count"], 1)
            self.assertFalse(loaded["native_stop_active"])
            with self.assertRaises(WorkerStatusUnavailable):
                read_private_worker_status(
                    directory=path, now_ms=now + 86_400_001)
            bad = {**report, "orders_sent": True}
            file = path / "paper-monitor-state.json"
            file.write_text(json.dumps(bad), encoding="ascii")
            file.chmod(0o600)
            with self.assertRaises(WorkerStatusUnavailable):
                read_private_worker_status(directory=path, now_ms=now)

    def test_status_file_atomic_owner_only_when_unprivileged_linux(self):
        import os
        if os.name != "posix" or os.geteuid() == 0:
            self.skipTest("POSIX nonroot only")
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            directory.chmod(0o700)
            with PrivateWorkerStatus(directory) as writer:
                sample = self.drive([GOOD])[0]
                writer.publish(sample)
                raw = directory.joinpath("paper-monitor-state.json").read_bytes()
                self.assertEqual(json.loads(raw)["healthy_lease_count"], 1)
                self.assertEqual(directory.joinpath("paper-monitor-state.json").stat().st_mode & 0o777,
                                 0o600)
                with self.assertRaises(Exception):
                    PrivateWorkerStatus(directory)
            self.assertFalse(any(p.name.startswith(".paper-monitor-")
                                 and p.name != ".paper-monitor-worker.lock"
                                 for p in directory.iterdir()))
