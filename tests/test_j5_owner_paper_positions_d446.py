"""D446 read-only route-selected AUTO4 positions, not local browser fixtures."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.j5_owner_paper_positions_d446 import (
    read_owner_paper_positions, OwnerPaperPositionsUnavailable,
)
from crypto_intelligence_agent.paper_intrahour_proof_d392 import (
    POSITION_ID, PLAN_VERSION, _new_position,
)
from test_j4_held_multi_public_d445 import extra_position, ETH_ID

SCHEMA = "j4-private-paper-routes-d425-v1"


@unittest.skipUnless(os.name == "posix" and hasattr(os, "geteuid")
                     and os.geteuid() != 0, "POSIX nonroot owner only")
class OwnerPaperViewD446Tests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)
        self.home.chmod(0o700)
        self.path = self.home / "paper-positions.sqlite"
        self.store = _new_position(self.path, short=False)
        extra_position(self.store)
        self.path.chmod(0o600)
        entries = [{
            "position_id": identity, "plan_version": PLAN_VERSION,
            "stop_mark_price": "99", "target_prices": ["101", "103"],
            "max_spread_bps": "30", "runner": None,
        } for identity in (POSITION_ID, ETH_ID)]
        self.manifest = self.home / "paper-routes.json"
        self.manifest.write_text(json.dumps({
            "schema_version": SCHEMA, "positions": entries,
        }), encoding="utf-8")
        self.manifest.chmod(0o600)

    def test_two_actual_saved_positions_visible_in_existing_d407_contract(self):
        with patch("socket.create_connection",
                   side_effect=AssertionError("UI read attempted network")):
            result = read_owner_paper_positions(directory=self.home)
        self.assertEqual(result["schema_version"], "paper_positions_snapshot_v1")
        self.assertEqual(len(result["positions"]), 2)
        self.assertEqual(set(p["symbol_fixture"] for p in result["positions"]),
                         {"BTCUSDT", "ETHUSDT"})
        self.assertEqual(set(p["position_id"] for p in result["positions"]),
                         {POSITION_ID, ETH_ID})
        self.assertTrue(all(p["filled_exit_units"] == "0"
                            for p in result["positions"]))
        self.assertFalse(result["financial_pnl_available"])
        self.assertFalse(result["orders_sent"])

    def test_owner_directory_manifest_or_journal_unsafe_fail_closed(self):
        for target in (self.home, self.manifest, self.path):
            mode = target.stat().st_mode & 0o777
            try:
                target.chmod(0o755 if target.is_dir() else 0o644)
                with self.assertRaises(OwnerPaperPositionsUnavailable):
                    read_owner_paper_positions(directory=self.home)
            finally:
                target.chmod(mode)
        renamed = self.home / "safe-snapshot.sqlite"
        self.path.rename(renamed)
        self.path.symlink_to(renamed)
        with self.assertRaises(OwnerPaperPositionsUnavailable):
            read_owner_paper_positions(directory=self.home)

    def test_invalid_route_fails_all_positions_without_partial_snapshot(self):
        self.manifest.write_text('{"schema_version":"j4-private-paper-routes-d425-v1",'
                                 '"positions":[]}', encoding="ascii")
        self.manifest.chmod(0o600)
        with self.assertRaises(OwnerPaperPositionsUnavailable):
            read_owner_paper_positions(directory=self.home)
