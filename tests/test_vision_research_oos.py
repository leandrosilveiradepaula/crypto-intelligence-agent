"""J1 #243 monthly directional OOS is descriptive, never a fill/backtest."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import json
import os
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.vision_research_oos import diagnose_vision_monthly_direction
from test_offline_vision_series import month
from test_offline_vision_month import synthetic_zip
from scripts.audit_offline_vision_series import audit_private_vision_archives, main

D = Decimal


class VisionDirectionalMonthlyTests(unittest.TestCase):
    def test_no_lookahead_test_month_mutation_does_not_change_selection(self):
        a, b, c = month(2024, 1), month(2024, 2), month(2024, 3)
        cutoff = c.end_open_exclusive_ms + 1000
        original = diagnose_vision_monthly_direction((a, b, c), as_of_ms=cutoff)
        self.assertEqual(len(original.folds), 2)
        self.assertEqual(original.folds[0].selected_rule, "abstain")
        # Forge a different but valid, contiguous test month: its own selection
        # cannot change, while a LATER month's training summary may change.
        rows = list(b.candles)
        for i, candle in enumerate(rows):
            close = D(100 + (i % 5))
            rows[i] = replace(candle, open=close, high=close + 1,
                              low=close - 1, close=close)
        changed = diagnose_vision_monthly_direction(
            (a, replace(b, candles=tuple(rows)), c), as_of_ms=cutoff,
        )
        self.assertEqual(original.folds[0].selected_rule, changed.folds[0].selected_rule)
        self.assertEqual(original.folds[0].training_pairs, changed.folds[0].training_pairs)
        self.assertNotEqual(original.folds[1].training_pairs,
                            changed.folds[1].training_pairs)
        self.assertFalse(changed.financial_backtest_approved)
        self.assertFalse(changed.source_authenticated)
        self.assertFalse(changed.dataset_rights_authorized)
        self.assertFalse(changed.orders_sent)

    def test_invalid_assembly_cannot_be_scored(self):
        jan, feb, mar = month(2024, 1), month(2024, 2), month(2024, 3)
        cutoff = mar.end_open_exclusive_ms + 1000
        for sample in ((jan,), (jan, mar), (feb, jan), (jan, jan)):
            with self.subTest(n=len(sample)), self.assertRaises(DataValidationError):
                diagnose_vision_monthly_direction(sample, as_of_ms=cutoff)
        x = diagnose_vision_monthly_direction((jan, feb), as_of_ms=cutoff)
        self.assertEqual(x.folds[0].oos_pairs, 0)
        self.assertEqual(x.folds[0].oos_selected_hits, 0)
        self.assertEqual(x.folds[0].training_pairs, 0)
        self.assertEqual(x.folds[0].abstained_pairs, len(feb.candles) - 2)


@unittest.skipUnless(os.name == "posix", "private POSIX files required")
class VisionDirectionalCLITests(unittest.TestCase):
    def test_existing_cli_opt_in_adds_only_sanitized_fold_counts(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            root.chmod(0o700)
            entries = []
            cutoff = None
            for y, m in ((2024, 1), (2024, 2)):
                blob, name, digest, cutoff = synthetic_zip(year=y, month=m, compression=0)
                path = root / name
                path.write_bytes(blob)
                path.chmod(0o600)
                entries.append({"name": name, "sha256": digest})
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({
                "schema_version": "vision-local-series-v1",
                "as_of_ms": cutoff, "archives": entries,
            }), encoding="ascii")
            manifest.chmod(0o600)
            old = audit_private_vision_archives(
                manifest_path=str(manifest), allow_personal_nonproduction_research=True,
            )
            new = audit_private_vision_archives(
                manifest_path=str(manifest), allow_personal_nonproduction_research=True,
                audit_directional_oos=True,
            )
            self.assertNotIn("directional_oos", old)
            self.assertEqual(len(new["directional_oos"]["folds"]), 1)
            self.assertEqual(new["directional_oos"]["folds"][0]["selected_rule"], "abstain")
            self.assertFalse(new["directional_oos"]["financial_backtest_approved"])
            with redirect_stdout(StringIO()) as out:
                self.assertEqual(main([
                    "--manifest", str(manifest), "--allow-personal-nonproduction-research",
                    "--audit-directional-oos",
                ]), 0)
            public = out.getvalue()
            for secret in (str(root), "BTCUSDT", "1250", entries[0]["name"]):
                self.assertNotIn(secret, public)
            self.assertFalse(json.loads(public)["orders_sent"])


if __name__ == "__main__":
    unittest.main()
