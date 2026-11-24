"""Owner-only profile editor, without network/real orders."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.paper_profile_d487 import save, snapshot
from scripts.run_j2_j4_public_paper_resident_d453 import read_owner_paper_policy

SAMPLE = (Path(__file__).resolve().parents[1] / "docs/examples"
          / "d453_public_paper_policy.example.json")


@unittest.skipUnless(os.name == "posix" and os.geteuid() != 0,
                     "unprivileged owner required")
class OwnerPaperProfileTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="cia-d487-")
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name)
        self.home.chmod(0o700)
        self.file = self.home / "strategy.json"
        shutil.copyfile(SAMPLE, self.file)
        self.file.chmod(0o600)

    def test_user_can_edit_indicators_and_fully_close_in_two_paper_tranches(self):
        first = snapshot(self.file)
        self.assertEqual(first["research"]["ema_period"], 2)
        out = save(self.file, revision=first["revision"], edits={
            "research": {
                "ema_period": 20, "atr_period": 14,
                "extrema_period": 10, "quote_volume_period": 10,
                "compression_bars": 5, "baseline_bars": 5,
                "max_atr_ratio": "1.5", "min_quote_volume_ratio": "0.7",
                "experimental_paper_relaxation": True,
            },
            "paper": {
                "margin_quote": "5", "leverage": 50,
                "stop_distance_bps": "50",
                "target_distances_bps": ["100", "200"],
                "tranches": [
                    {"basis":"INITIAL_POSITION","percent":"50"},
                    {"basis":"INITIAL_POSITION","percent":"50"},
                ],
                "runner_floor_percent":"0",
            },
        })
        self.assertNotEqual(out["revision"], first["revision"])
        cfg = read_owner_paper_policy(self.file)
        self.assertEqual(cfg.research.features.ema_period, 20)
        self.assertEqual(cfg.research.features.atr_period, 14)
        self.assertEqual(cfg.exits.runner_floor_percent, 0)
        self.assertEqual(tuple(cfg.exits.target_distances_bps), (100,200))
        self.assertEqual(self.file.stat().st_mode & 0o777,0o600)
        self.assertEqual(out["applies_to"],"future_paper_sessions_only")
        self.assertFalse(out["orders_sent"])
        with self.assertRaises(DataValidationError):
            save(self.file, revision=first["revision"],
                 edits={"research":{"ema_period": 15}})

    def test_d503_configure_10_30_60_without_changing_existing_positions(self):
        first = snapshot(self.file)
        self.assertEqual(first["research"].get("entry_mode", "breakout"), "breakout")
        after = save(self.file, revision=first["revision"], edits={
            "research": {
                "entry_mode": "ema_cross",
                "ema_cross_periods": [10, 30, 60],
            },
        })
        self.assertEqual(after["research"]["ema_cross_periods"], [10, 30, 60])
        cfg = read_owner_paper_policy(self.file)
        self.assertEqual(cfg.research.entry_mode, "ema_cross")
        self.assertEqual(cfg.research.ema_cross_periods, (10, 30, 60))
        self.assertEqual(cfg.leverage.for_new_positions, 50)
        before = self.file.read_bytes()
        for values in ([10, 10, 60], [30, 10, 60], [10, 30, 121], ["10", 30, 60]):
            with self.subTest(values=values), self.assertRaises(DataValidationError):
                save(self.file, revision=after["revision"], edits={
                    "research": {"ema_cross_periods": values},
                })
            self.assertEqual(before, self.file.read_bytes())

    def test_d513_save_independent_sma_and_pivot_without_ema(self):
        first = snapshot(self.file)
        selection = {
            "ema": [{"enabled": False, "period": n} for n in (10, 30, 60)],
            "sma": [{"enabled": n != 30, "period": n} for n in (5, 30, 21)],
            "pivot_supertrend": {
                "enabled": True, "pivot_period": 3, "atr_period": 12,
                "atr_factor": "2.5",
            },
        }
        result = save(self.file, revision=first["revision"], edits={
            "research": {"entry_mode": "indicator_combo", "indicators": selection}
        })
        cfg = read_owner_paper_policy(self.file)
        self.assertEqual(cfg.research.entry_mode, "indicator_combo")
        self.assertEqual(cfg.research.indicators.as_json(), selection)
        self.assertEqual(result["research"]["indicators"], selection)
        self.assertEqual(cfg.leverage.for_new_positions, 50)
        self.assertEqual(result["applies_to"], "future_paper_sessions_only")
        before = self.file.read_bytes()
        selection["sma"][0]["period"] = 80
        with self.assertRaises(DataValidationError):
            save(self.file, revision=result["revision"], edits={
                "research": {"indicators": selection}})
        self.assertEqual(self.file.read_bytes(), before)

    def test_d521_bollinger_profile_roundtrip_and_rejection(self):
        from crypto_intelligence_agent.j2_configurable_indicators_d513 import (
            BollingerBands, IndicatorSelection, MovingAverageSlot, PivotSuperTrend,
        )
        off = tuple(MovingAverageSlot(False,n) for n in (10,30,60))
        selection = IndicatorSelection(off,off,PivotSuperTrend(False,2,10,Decimal(3)),
                                       BollingerBands(True,21,Decimal("2.5"),"reentry"))
        result = save(self.file,revision=snapshot(self.file)["revision"],edits={
            "research":{"entry_mode":"indicator_combo","indicators":selection.as_json()}})
        cfg = read_owner_paper_policy(self.file)
        self.assertEqual(cfg.research.indicators,selection)
        self.assertEqual(result["research"]["indicators"],selection.as_json())
        self.assertEqual(result["applies_to"],"future_paper_sessions_only")
        before = self.file.read_bytes()
        bad = selection.as_json()
        bad["bollinger"]["period"] = 121
        with self.assertRaises(DataValidationError):
            save(self.file,revision=result["revision"],edits={"research":{"indicators":bad}})
        self.assertEqual(self.file.read_bytes(),before)

    def test_invalid_research_leverage_and_tranches_keep_existing_bytes(self):
        old=snapshot(self.file)
        original=self.file.read_bytes()
        invalid = (
            {"research":{"ema_period": 1}},
            {"research":{"ema_period": 501}},
            {"research":{"ema_period": True}},
            {"research":{"max_atr_ratio":"1.5"}},
            {"paper":{"leverage": 250}},
            {"paper":{"target_distances_bps":["200","100"]}},
            {"paper":{"tranches":[
                {"basis":"INITIAL_POSITION","percent":"85"},
                {"basis":"INITIAL_POSITION","percent":"30"}]}},
            {"risk":{"max_order_notional_quote":"50000"}},
        )
        for change in invalid:
            with self.subTest(change=change),self.assertRaises(DataValidationError):
                save(self.file,revision=old["revision"],edits=change)
            self.assertEqual(self.file.read_bytes(),original)

    def test_no_symlink_or_unsafe_mode(self):
        linked=self.home/"linked.json"
        linked.symlink_to(self.file)
        with self.assertRaises(DataValidationError):
            snapshot(linked)
        self.file.chmod(0o644)
        with self.assertRaises(DataValidationError):
            snapshot(self.file)


if __name__ == "__main__":
    unittest.main()
