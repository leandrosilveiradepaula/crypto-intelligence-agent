"""Regression: loss or weakening of J1 source gates must break docs CI (offline)."""
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
DOCS = (
    "AGENTS.md",
    "docs/PRODUCT_SPEC.md",
    "docs/ARCHITECTURE.md",
    "docs/DATA_CONTRACT.md",
    "docs/CRYPTO_REGISTRY.md",
    "docs/PROVIDER_RIGHTS.md",
    "docs/STRATEGY_SPEC.md",
    "docs/VALIDATION_PLAN.md",
    "docs/DECISIONS.md",
    "docs/JOURNEYS.md",
    "docs/STATUS.md",
    "docs/OPERATIONAL_STATE.md",
    "docs/J1_SOURCE_GATES.md",
    "docs/AUTOMATED_EXECUTION_SPEC.md",
)


class SourceGateDocsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for rel in (*DOCS, "scripts/check_docs.py"):
            src, dst = ROOT / rel, self.root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)

    def check(self):
        return subprocess.run(
            [sys.executable, str(self.root / "scripts/check_docs.py")],
            cwd=self.root, capture_output=True, text=True, timeout=15, check=False,
        )

    def test_current_matrix_passes(self):
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("14 documentos validados", result.stdout)

    def test_missing_matrix_fails(self):
        (self.root / "docs/J1_SOURCE_GATES.md").unlink()
        result = self.check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing: docs/J1_SOURCE_GATES.md", result.stdout)

    def test_automated_execution_spec_is_mandatory(self):
        (self.root / "docs/AUTOMATED_EXECUTION_SPEC.md").unlink()
        result = self.check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing: docs/AUTOMATED_EXECUTION_SPEC.md", result.stdout)

    def test_critical_auto_trading_controls_cannot_disappear(self):
        spec = self.root / "docs/AUTOMATED_EXECUTION_SPEC.md"
        original = spec.read_text(encoding="utf-8")
        for marker in ("offline_paper", "testnet", "kill-switch",
                       "reduce-only", "live_trading_enabled=false",
                       "order_submission_enabled=false"):
            with self.subTest(marker=marker):
                spec.write_text(re.sub(re.escape(marker), "DELETED", original,
                                       flags=re.IGNORECASE), encoding="utf-8")
                result = self.check()
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn("missing automated execution invariant", result.stdout)
        spec.write_text(original, encoding="utf-8")

    def test_removing_critical_invariants_fails(self):
        matrix = self.root / "docs/J1_SOURCE_GATES.md"
        original = matrix.read_text(encoding="utf-8")
        for token in (
            "#32", "#36", "#48", "Top50", "price-only",
            "bybit_ticker_24h_units=blocked",
            "ticker_turnover_unit_verified=false",
            "ticker_volume_unit_verified=false",
        ):
            with self.subTest(token=token):
                matrix.write_text(original.replace(token, "REDACTED"), encoding="utf-8")
                result = self.check()
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn("missing J1 source-gates invariant", result.stdout)
        matrix.write_text(original, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
