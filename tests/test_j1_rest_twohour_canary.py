"""Offline tests for finite REST 2-hour canary; no HTTP, systemd or market data."""
from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.run_j1_rest_twohour_canary import HOUR, run_canary

class FakeClock:
    def __init__(self, now: float):
        self.now = now
        self.sleeps = []
    def clock(self):
        return self.now
    def sleep(self, delta: float):
        assert delta > 0
        self.sleeps.append(delta)
        self.now += delta


@unittest.skipUnless(os.name == "posix", "owner only POSIX")
class CanaryTests(unittest.TestCase):
    def setUp(self):
        t = TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = Path(t.name)
        self.root.chmod(0o700)
        self.frozen = self.root / "frozen"
        self.frozen.mkdir(mode=0o700)
        self.output = self.root / "canary"

    def runner(self, clock, worker, audit=lambda *args: (2, 50), **options):
        return run_canary(
            frozen=self.frozen, output=self.output,
            allow_public_network=True, allow_private_storage=True,
            confirm_region_and_personal_research=True,
            owner_ok=True, clock=clock.clock, sleep=clock.sleep,
            worker=worker, audit=audit, **options,
        )

    def test_two_successes_and_no_automatic_trading_or_marketwide(self):
        fake = FakeClock(HOUR * 1000 + 100)
        calls = []
        def worker(**kwargs):
            calls.append(kwargs)
            return {
                "status": "research_sample_closed_hour_persisted",
                "decision_end_ms": int(fake.clock() // HOUR) * HOUR * 1000,
                "selected_research_contracts": 2,
                "contracts_at_decision": 2,
                "requests_attempted": 2,
            }
        result = self.runner(fake, worker)
        self.assertEqual(result["status"], "two_hour_research_canary_verified")
        self.assertEqual((result["rounds_completed"], result["published_hours"],
                          result["closed_candles"], result["requests_attempted"]), (2, 2, 50, 4))
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(fake.sleeps), 2)
        self.assertEqual(calls[0]["max_assets"], 2)
        for flag in ("orders_sent", "marketwide_top50_verified",
                     "continuous_collector_verified", "live_trading_authorized"):
            self.assertFalse(result[flag])

    def test_first_failure_aborts_second_and_never_forges_audit(self):
        fake = FakeClock(HOUR * 1000 + 20)
        calls = []
        def worker(**kwargs):
            calls.append(kwargs)
            return {"status": "research_provider_fail_stop", "requests_attempted": 1}
        result = self.runner(fake, worker, audit=lambda *args: self.fail("audit"))
        self.assertEqual(result["status"], "abstain")
        self.assertEqual(result["failure_category"], "one_shot_failed")
        self.assertEqual((len(calls), result["rounds_completed"]), (1, 0))

    def test_wrong_decision_hour_fails_closed(self):
        fake = FakeClock(HOUR * 1000 + 20)
        def worker(**kwargs):
            return {"status": "research_sample_closed_hour_persisted",
                    "decision_end_ms": 0, "requests_attempted": 2}
        result = self.runner(fake, worker)
        self.assertEqual(result["failure_category"], "second_hour_not_sequential")
        self.assertFalse(result["two_hour_canary_verified"])

    def test_reused_output_abstains_before_worker(self):
        self.output.mkdir(mode=0o700)
        fake = FakeClock(HOUR * 1000 + 20)
        result = self.runner(fake, lambda **kw: self.fail("network"))
        self.assertEqual(result["failure_category"], "existing_journal")

    def test_default_without_optin_has_no_io(self):
        result = run_canary(frozen=self.frozen, output=self.output,
                            clock=lambda: self.fail("clock"),
                            sleep=lambda d: self.fail("sleep"),
                            worker=lambda **kw: self.fail("worker"))
        self.assertEqual(result["status"], "optin_required")
        self.assertFalse(self.output.exists())

    def test_sqlite_audit_failure_never_claims_success(self):
        fake = FakeClock(HOUR * 1000 + 20)
        def worker(**kwargs):
            return {"status": "research_sample_closed_hour_persisted",
                    "decision_end_ms": int(fake.clock() // HOUR)*HOUR*1000,
                    "selected_research_contracts": 2,
                    "contracts_at_decision": 2, "requests_attempted": 2}
        result = self.runner(fake, worker, audit=lambda *args: (_ for _ in ()).throw(ValueError("bad")))
        self.assertEqual(result["failure_category"], "sqlite_or_replay_invalid")
        self.assertFalse(result["two_hour_canary_verified"])


if __name__ == "__main__":
    unittest.main()
