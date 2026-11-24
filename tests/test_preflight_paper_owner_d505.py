"""D505: owner-only readback before release; no simulated brokerage or writes."""
from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.paper_order_store import SQLitePaperOrderJournal
from crypto_intelligence_agent.paper_intrahour_proof_d392 import (
    _new_position, POSITION_ID, PLAN_VERSION,
)
from scripts.preflight_paper_owner_d505 import preflight_paper_owner, main

SOURCE = (
    Path(__file__).resolve().parents[1] / "docs" / "examples"
    / "d453_public_paper_policy.example.json"
)


@unittest.skipUnless(os.name == "posix" and hasattr(os, "geteuid")
                     and os.geteuid() != 0, "nonroot POSIX journal owner required")
class PaperOwnerPreflightD505Tests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="cia-d505-preflight-")
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.paper = self.base / "paper"
        self.paper.mkdir(mode=0o700)
        self.policy = self.base / "policy.json"
        shutil.copyfile(SOURCE, self.policy)
        self.policy.chmod(0o600)
        positions = self.paper / "paper-positions.sqlite"
        _new_position(positions, short=False)
        positions.chmod(0o600)
        orders = self.paper / "paper-orders.sqlite"
        SQLitePaperOrderJournal(orders)
        orders.chmod(0o600)
        manifest = self.paper / "paper-routes.json"
        manifest.write_text(json.dumps({
            "schema_version": "j4-private-paper-routes-d425-v1",
            "positions": [{
                "position_id": POSITION_ID,
                "plan_version": PLAN_VERSION,
                "stop_mark_price": "99",
                "target_prices": ["101", "103"],
                "max_spread_bps": "30",
                "runner": None,
            }],
        }), encoding="ascii")
        manifest.chmod(0o600)

    def test_legacy_paper_journals_profile_and_page_without_writing(self):
        before = {
            x.name: x.read_bytes() for x in self.paper.iterdir()
            if x.is_file()
        }
        with patch("socket.create_connection",
                   side_effect=AssertionError("preflight used network")):
            result = preflight_paper_owner(
                paper_directory=self.paper, policy_file=self.policy,
            )
        self.assertEqual(result["status"], "private_owner_paper_readback_consistent")
        self.assertEqual(result["historical_position_count"], 1)
        self.assertEqual(result["owner_history_page_checked"], 1)
        self.assertEqual(result["current_session_open_positions"], 1)
        self.assertEqual(result["current_session_closed_positions"], 0)
        self.assertEqual(result["next_session_entry_mode"], "breakout")
        self.assertFalse(result["orders_sent"])
        self.assertTrue(result["read_only"])
        self.assertFalse(result["vps_release_executed"])
        self.assertEqual(before, {
            x.name: x.read_bytes() for x in self.paper.iterdir()
            if x.is_file()
        })

    def test_manual_ema_10_30_60_is_future_only(self):
        data = json.loads(self.policy.read_text())
        data["research"]["entry_mode"] = "ema_cross"
        data["research"]["ema_cross_periods"] = [10, 30, 60]
        self.policy.write_text(json.dumps(data), encoding="ascii")
        self.policy.chmod(0o600)
        result = preflight_paper_owner(
            paper_directory=self.paper, policy_file=self.policy,
        )
        self.assertEqual(result["next_session_entry_mode"], "ema_cross")
        self.assertEqual(result["next_session_ema_cross_periods"], [10, 30, 60])
        self.assertEqual(result["current_session_open_positions"], 1)
        self.assertFalse(result["orders_sent"])

    def test_custom_sma_selection_preserves_open_position(self):
        data = json.loads(self.policy.read_text())
        data["research"]["entry_mode"] = "indicator_combo"
        selection = {
            "ema": [{"enabled": False, "period": x} for x in (10, 30, 60)],
            "sma": [{"enabled": x == 10, "period": x} for x in (10, 30, 60)],
            "pivot_supertrend": {"enabled": False, "pivot_period": 2,
                                 "atr_period": 10, "atr_factor": "3"},
        }
        data["research"]["indicators"] = selection
        self.policy.write_text(json.dumps(data), encoding="ascii")
        before = (self.paper / "paper-positions.sqlite").read_bytes()
        result = preflight_paper_owner(paper_directory=self.paper, policy_file=self.policy)
        self.assertEqual(result["next_session_entry_mode"], "indicator_combo")
        self.assertEqual(result["next_session_indicators"], selection)
        self.assertEqual(result["current_session_open_positions"], 1)
        self.assertEqual((self.paper / "paper-positions.sqlite").read_bytes(), before)
        self.assertFalse(result["orders_sent"])

    def test_owner_directory_and_policy_errors_fail_without_private_output(self):
        output = io.StringIO()
        self.paper.chmod(0o755)
        try:
            with redirect_stdout(output):
                rc = main([
                    "--paper-directory", str(self.paper),
                    "--policy-file", str(self.policy),
                ])
            self.assertEqual(rc, 1)
            raw = output.getvalue()
            self.assertEqual(json.loads(raw)["status"], "owner_paper_preflight_denied")
            self.assertNotIn(str(self.base), raw)
        finally:
            self.paper.chmod(0o700)
        self.policy.chmod(0o644)
        with self.assertRaises(DataValidationError):
            preflight_paper_owner(
                paper_directory=self.paper, policy_file=self.policy,
            )


if __name__ == "__main__":
    unittest.main()
