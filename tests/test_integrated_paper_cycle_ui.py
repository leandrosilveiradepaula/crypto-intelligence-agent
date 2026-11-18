"""D431: the browser accepts only the finite, explicitly synthetic lifecycle."""
from pathlib import Path
import unittest


class IntegratedPaperCycleUiTests(unittest.TestCase):
    def test_console_loads_the_strict_read_only_renderer(self):
        root = Path(__file__).parents[1]
        html = (root / "web" / "app" / "index.html").read_text(encoding="utf-8")
        app = (root / "web" / "app" / "app.js").read_text(encoding="utf-8")
        renderer = (root / "web" / "app" / "integrated-paper-cycle.js").read_text(encoding="utf-8")
        self.assertIn('src="./integrated-paper-cycle.js"', html)
        self.assertIn('j6_full_offline_paper_lifecycle_v1', app)
        self.assertIn("CIAIntegratedPaperCycle.install(payload)", app)
        for required in (
            "orders_sent === false", "live_trading_authorized === false",
            "market_data_real === false", "financial_pnl_available === false",
            "restart_duplicate_orders === 0", "Ciclo integrado reproduzido",
        ):
            self.assertIn(required, renderer)
        self.assertNotIn("fetch(", renderer)
