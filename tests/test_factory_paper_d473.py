"""D473: native Factory Droid and bounded mission are versioned and reviewable.

This test validates repository files only, not a Factory session or billing.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class FactoryPaperProjectContract(unittest.TestCase):
    def test_native_project_droid_has_valid_frontmatter_and_scope(self):
        path = ROOT / ".factory" / "droids" / "paper-delivery.md"
        text = path.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\nname: paper-delivery\n"))
        self.assertIn("\nmodel: inherit\n", text)
        self.assertIn('"Execute"', text)
        self.assertIn("\n---\n\n", text)
        for term in ("J2/J3/J4/J5", "OPEN PENDING", "FILL hipotético",
                     "sem ordens reais", "J1", "GitHub"):
            self.assertIn(term, text)

    def test_factory_mission_is_a_whole_paper_product_without_live_orders(self):
        path = ROOT / ".factory" / "missions" / "paper-end-to-end.md"
        text = path.read_text(encoding="utf-8")
        for term in ("droid exec --mission --auto high -f", "253.263", "50/50",
                     "PAPER", "J5", "SQLite", "restart",
                     "R$0", "gates humanos"):
            self.assertIn(term, text)
        self.assertNotIn("skip-permissions-unsafe", text)
        self.assertNotIn("live trading enable", text)


if __name__ == "__main__":
    unittest.main()
