"""D453 runnable owner config: no accidental orders or writable policy."""
from __future__ import annotations

from decimal import Decimal
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.market_data import DataValidationError
from scripts.run_j2_j4_public_paper_resident_d453 import (
    main, read_owner_paper_policy,
)


SAMPLE = (
    Path(__file__).resolve().parents[1] / "docs" / "examples" /
    "d453_public_paper_policy.example.json"
)


@unittest.skipUnless(os.name == "posix" and hasattr(os, "geteuid")
                     and os.geteuid() != 0, "owner POSIX only")
class OwnerPaperConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="cia-d453-policy-")
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.home.chmod(0o700)
        self.policy = self.home / "policy.json"
        shutil.copyfile(SAMPLE, self.policy)
        self.policy.chmod(0o600)

    def test_exact_decimal_margin_and_leverage_and_two_partials(self):
        config = read_owner_paper_policy(self.policy)
        self.assertEqual(config.margin_quote, Decimal("5"))
        self.assertEqual(config.leverage.for_new_positions, 50)
        self.assertEqual(config.exits.runner_floor_percent, Decimal(50))
        self.assertEqual(config.exits.target_distances_bps,
                         (Decimal(200), Decimal(300)))
        self.assertEqual(config.entry.first_tranche_fraction, Decimal("0.3"))
        self.assertEqual(config.limits.max_pending_open_orders, 5)

    def test_d485_separate_optin_only_for_experimental_paper_profile(self):
        data = json.loads(self.policy.read_text())
        data["research"]["max_atr_ratio"] = "1.5"
        data["research"]["min_quote_volume_ratio"] = "0.7"
        self.policy.write_text(json.dumps(data))
        with self.assertRaises(DataValidationError):
            read_owner_paper_policy(self.policy)
        data["research"]["experimental_paper_relaxation"] = True
        self.policy.write_text(json.dumps(data))
        experimental = read_owner_paper_policy(self.policy)
        self.assertTrue(experimental.research.experimental_paper_relaxation)
        self.assertEqual(experimental.research.max_atr_ratio, Decimal("1.5"))
        self.assertEqual(experimental.research.min_quote_volume_ratio, Decimal("0.7"))
        self.assertEqual(experimental.limits.max_market_age_ms, 3000)
        self.assertEqual(experimental.leverage.for_new_positions, 50)
        for invalid in ("true", 1, None):
            data["research"]["experimental_paper_relaxation"] = invalid
            self.policy.write_text(json.dumps(data))
            with self.subTest(invalid=invalid), self.assertRaises(DataValidationError):
                read_owner_paper_policy(self.policy)

    def test_long_finite_lease_reserves_enough_bounded_public_frames(self):
        with patch(
            "scripts.run_j2_j4_public_paper_resident_d453."
            "run_resident_paper_observer",
            return_value={"status": "bounded_run_completed", "orders_sent": False},
        ) as runner:
            code = main([
                "--j2-directory", str(self.home / "j2"),
                "--paper-directory", str(self.home / "paper"),
                "--policy-file", str(self.policy),
                "--lease-seconds", "1500", "--max-cycles", "1",
                "--allow-public-network", "--allow-public-websocket",
                "--confirm-personal-readonly-research",
                "--confirm-region-eligible", "--confirm-public-data-rights",
                "--enable-hypothetical-paper-cycle",
                "--auto-capture-rest-warmup",
            ])
        self.assertEqual(code, 0)
        budget = runner.call_args.kwargs["policy"].budget
        self.assertEqual(budget.kline.max_frames, 96_000)
        self.assertEqual(budget.kline.max_sessions, 3)
        self.assertEqual(budget.ticker.max_sessions, 3)
        self.assertEqual(budget.ticker.max_frames, 1_500_000)
        self.assertEqual(budget.ticker.max_seconds, 1500)
        self.assertTrue(runner.call_args.kwargs["auto_capture_rest_warmup"])
        self.assertFalse((self.home / "paper").exists())

    def test_hour_long_kline_budget_reaches_safe_supervisor_cap(self):
        # D476 cycles 3 and 5 hit the old 50k kline limit before close.
        # Preserve the upstream 200k hard cap; no network or journal writes.
        with patch(
            "scripts.run_j2_j4_public_paper_resident_d453."
            "run_resident_paper_observer",
            return_value={"status": "bounded_run_completed", "orders_sent": False},
        ) as runner:
            code = main([
                "--j2-directory", str(self.home / "j2"),
                "--paper-directory", str(self.home / "paper"),
                "--policy-file", str(self.policy),
                "--lease-seconds", "3580", "--max-cycles", "1",
                "--allow-public-network", "--allow-public-websocket",
                "--confirm-personal-readonly-research",
                "--confirm-region-eligible", "--confirm-public-data-rights",
                "--enable-hypothetical-paper-cycle",
            ])
        self.assertEqual(code, 0)
        budget = runner.call_args.kwargs["policy"].budget
        self.assertEqual(budget.kline.max_frames, 200_000)
        self.assertEqual(budget.kline.max_seconds, 3580)
        self.assertEqual(budget.ticker.max_frames, 3_580_000)
        self.assertFalse((self.home / "paper").exists())

    def test_unbounded_public_ws_reconnect_rejected_before_network(self):
        with patch(
            "scripts.run_j2_j4_public_paper_resident_d453."
            "run_resident_paper_observer",
        ) as runner, self.assertRaises(DataValidationError):
            main([
                "--j2-directory", str(self.home / "j2"),
                "--paper-directory", str(self.home / "paper"),
                "--policy-file", str(self.policy),
                "--public-ws-sessions", "4",
                "--allow-public-network", "--allow-public-websocket",
                "--confirm-personal-readonly-research",
                "--confirm-region-eligible", "--confirm-public-data-rights",
                "--enable-hypothetical-paper-cycle",
            ])
        runner.assert_not_called()

    def test_denied_cli_makes_no_network_or_paper_state(self):
        self.assertEqual(main([
            "--j2-directory", str(self.home / "j2"),
            "--paper-directory", str(self.home / "paper"),
            "--policy-file", str(self.policy),
        ]), 2)
        self.assertFalse((self.home / "paper").exists())

    def test_unsafe_permissions_symlink_floats_duplicate_keys_and_unknown_field(self):
        self.policy.chmod(0o644)
        with self.assertRaises(DataValidationError):
            read_owner_paper_policy(self.policy)
        self.policy.chmod(0o600)
        shortcut = self.home / "linked.json"
        shortcut.symlink_to(self.policy)
        with self.assertRaises(DataValidationError):
            read_owner_paper_policy(shortcut)
        saved = self.policy.read_text()
        for mutated in (
            saved.replace('"margin_quote": "5"', '"margin_quote": 5.0'),
            saved.replace('"margin_quote": "5"', '"margin_quote": "5", "margin_quote": "10"'),
            saved.replace('"leverage": 50', '"leverage": 250'),
            saved.replace('"schema_version": "d453-public-paper-research-policy-v1"',
                          '"schema_version": "d453-public-paper-research-policy-v2"'),
        ):
            self.policy.write_text(mutated)
            self.policy.chmod(0o600)
            with self.subTest(case=mutated[:80]), self.assertRaises(DataValidationError):
                read_owner_paper_policy(self.policy)


if __name__ == "__main__":
    unittest.main()
