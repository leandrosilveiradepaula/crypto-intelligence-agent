"""D430 isolated out-of-process observer tests; never contacts market APIs."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import time
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.j4_paper_bounded_trial_d428 import (
    PaperTrialBudget, _result,
)
from crypto_intelligence_agent.j5_paper_watch_d427 import (
    unavailable_finite_paper_lease,
)
from crypto_intelligence_agent.j6_paper_child_watchdog_d430 import (
    _valid_child_result, supervise_finite_paper_child,
)
from crypto_intelligence_agent.market_data import DataValidationError

_BUDGET = PaperTrialBudget(max_leases=2, lease_seconds=10, max_total_seconds=30)
_NOW = 1_794_995_000_000


def _successful_child() -> bytes:
    result = _result(
        "bounded_trial_completed_no_live_protection",
        attempted=2, completed=2, forwarded=20, last_watch_at_ms=_NOW,
    )
    return json.dumps(result).encode("ascii")


def _owner_watch():
    return {
        "status": "finite_paper_lease_ended",
        "sampled_at_ms": _NOW,
        "configured_position_routes": 1,
        "quote_events_forwarded": 20,
        "market_lease_completed": True,
        "owner_cohort_unchanged": True,
    }


def _args():
    return {
        "state_directory": Path("/owner/j1"),
        "private_paper_directory": Path("/owner/positions"),
        "watch_directory": Path("/owner/watch"),
        "budget": _BUDGET,
        "clock": lambda: _NOW,
        "allow_private_pointer_read": True,
        "allow_public_websocket": True,
        "confirm_personal_readonly_research": True,
        "confirm_region_eligible": True,
        "allow_synthetic_paper_reservations": True,
        "allow_multiple_finite_leases": True,
        "allow_paper_watch_output": True,
        "allow_child_process_watchdog": True,
    }


class D430ChildValidationTests(unittest.TestCase):
    def test_strict_child_success_validation(self):
        result = _valid_child_result(_successful_child(), _BUDGET)
        self.assertEqual(result["leases_with_fresh_position_quotes"], 2)
        self.assertFalse(result["orders_sent"])

    def test_rejects_fake_success_unfinished_and_malformed(self):
        base = json.loads(_successful_child())
        mutations = (
            {"orders_sent": True},
            {"approved_for_live_use": True},
            {"finite_trial_ended": False},
            {"leases_attempted": 1},
            {"leases_with_fresh_position_quotes": 1},
            {"last_terminal_watch_at_ms": True},
            {"quotes_forwarded_to_paper": -1},
            {"unknown_private_symbol": "BTCUSDT"},
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.assertIsNone(_valid_child_result(
                    json.dumps({**base, **mutation}).encode(), _BUDGET,
                ))
        for raw in (
            b'{"status":"ok","status":"ok"}',
            b'{"price": NaN}',
            b'{"status":"ok"}\n{"status":"ok"}',
            b'\xff',
            b'x' * 9000,
        ):
            self.assertIsNone(_valid_child_result(raw, _BUDGET))

    def test_no_optin_prevents_child_and_writes(self):
        args = _args()
        args["allow_child_process_watchdog"] = False
        with patch(
            "crypto_intelligence_agent.j6_paper_child_watchdog_d430.subprocess.run"
        ) as launch, patch(
            "crypto_intelligence_agent.j6_paper_child_watchdog_d430.publish_paper_watch"
        ) as publish:
            report = supervise_finite_paper_child(**args)
        self.assertEqual(report["status"], "eight_explicit_owner_optins_required")
        launch.assert_not_called()
        publish.assert_not_called()
        self.assertFalse(report["orders_sent"])

    def test_bad_gate_type_refused(self):
        args = _args()
        args["confirm_region_eligible"] = 1
        with self.assertRaises(DataValidationError):
            supervise_finite_paper_child(**args)


@unittest.skipUnless(
    os.name == "posix" and hasattr(os, "geteuid") and os.geteuid() != 0,
    "D430 subprocess owner proof runs only on nonroot POSIX",
)
class D430POSIXSupervisorTests(unittest.TestCase):
    def run_case(self, *, result=None, err=None, owner_watch=None):
        args = _args()
        result = result if result is not None else subprocess.CompletedProcess(
            args=["python"], returncode=0, stdout=_successful_child(),
        )
        published = []
        with patch(
            "crypto_intelligence_agent.j6_paper_child_watchdog_d430._validate_separate_directories"
        ), patch(
            "crypto_intelligence_agent.j6_paper_child_watchdog_d430.publish_paper_watch",
            side_effect=lambda path, report: published.append(report),
        ), patch(
            "crypto_intelligence_agent.j6_paper_child_watchdog_d430.subprocess.run",
            side_effect=err if err is not None else None,
            return_value=result,
        ) as launched, patch(
            "crypto_intelligence_agent.j6_paper_child_watchdog_d430.read_paper_watch",
            return_value=owner_watch if owner_watch is not None else _owner_watch(),
        ):
            verdict = supervise_finite_paper_child(**args)
        return verdict, published, launched

    def test_parent_observes_success_but_never_claims_active_protection(self):
        report, published, child = self.run_case()
        self.assertEqual(report["status"], "finite_child_ended_without_live_protection")
        self.assertTrue(report["independent_parent_process_observed"])
        self.assertFalse(report["active_position_supervision_verified"])
        self.assertFalse(report["approved_for_signals"])
        self.assertFalse(report["orders_sent"])
        self.assertEqual(len(published), 1)
        self.assertEqual(published[0]["status"], "finite_paper_lease_failed_closed")
        argv = child.call_args.args[0]
        self.assertIn("scripts.run_j4_paper_bounded_trial_d428", argv)
        self.assertFalse(child.call_args.kwargs["shell"])
        self.assertTrue(child.call_args.kwargs["start_new_session"])
        self.assertEqual(child.call_args.kwargs["timeout"], 40)

    def test_timeout_is_fail_closed_and_no_retry(self):
        report, published, child = self.run_case(
            err=subprocess.TimeoutExpired(["python"], 40),
        )
        self.assertEqual(report["status"], "child_timeout_failclosed")
        self.assertEqual(len(published), 2)
        self.assertEqual(child.call_count, 1)
        self.assertFalse(report["orders_sent"])

    def test_crash_is_fail_closed_and_no_retry(self):
        child = subprocess.CompletedProcess(args=["python"], returncode=9, stdout=b"")
        report, published, launched = self.run_case(result=child)
        self.assertEqual(report["status"], "child_exited_abnormally")
        self.assertEqual(len(published), 2)
        self.assertEqual(launched.call_count, 1)

    def test_exit_zero_without_owner_confirmation_is_not_success(self):
        stale = {**_owner_watch(), "sampled_at_ms": _NOW-1000}
        report, published, _ = self.run_case(owner_watch=stale)
        self.assertEqual(report["status"], "child_terminal_watch_unverified")
        self.assertEqual(len(published), 2)

    def test_exit_zero_with_forged_child_output_fails(self):
        invalid = subprocess.CompletedProcess(args=["python"], returncode=0, stdout=b"{}")
        report, published, _ = self.run_case(result=invalid)
        self.assertEqual(report["status"], "child_output_unverified")
        self.assertEqual(len(published), 2)

    def test_start_failure_fails_closed(self):
        report, published, launched = self.run_case(err=FileNotFoundError("python"))
        self.assertEqual(report["status"], "child_start_failed_closed")
        self.assertEqual(len(published), 2)
        self.assertEqual(launched.call_count, 1)


if __name__ == "__main__":
    unittest.main()
