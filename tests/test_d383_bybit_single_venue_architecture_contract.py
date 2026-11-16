"""D383 — prevent regression to an undecided exchange or manual execution.

Read documentation only; network and broker credentials are forbidden.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class BybitTargetD383DocumentationTests(unittest.TestCase):
    def read(self, name: str) -> str:
        return (ROOT / name).read_text(encoding="utf-8")

    def test_owner_selected_bybit_not_open_exchange_menu(self):
        product = self.read("docs/PRODUCT_SPEC.md")
        auto = self.read("docs/AUTOMATED_EXECUTION_SPEC.md")
        agents = self.read("AGENTS.md")
        self.assertIn("Produto-alvo D383: execução AUTOMÁTICA", product)
        self.assertIn("exclusivamente na Bybit V5 linear", product)
        self.assertIn("venue operacional-alvo", auto)
        self.assertIn("Bybit V5 linear", agents)
        self.assertIn("não reabrir", agents.lower())
        self.assertIn("D383", self.read("docs/DECISIONS.md"))

    def test_rest_and_ws_have_different_roles(self):
        architecture = self.read("docs/BYBIT_V5_ARCHITECTURE_D383.md")
        for s in (
            "/v5/market/instruments-info",
            "/v5/market/tickers",
            "/v5/market/kline",
            "/v5/public/linear",
            "/v5/order/create",
            "/v5/position/trading-stop",
            "/v5/private",
            "ACK **não é** FILL",
            "API",
        ):
            self.assertIn(s, architecture)
        self.assertIn("WS público", architecture)
        self.assertIn("REST público", architecture)
        self.assertIn("WS privado", architecture)
        self.assertIn("D383", self.read("docs/ARCHITECTURE.md"))

    def test_legacy_j1_and_capital_risks_preserved(self):
        decision = self.read("docs/BYBIT_V5_ARCHITECTURE_D383.md")
        for s in (
            "j1_rest_incremental_owner.py",
            "dois escritores",
            "one-way mode",
            "minNotionalValue",
            "tpSize=slSize",
            "received_ts",
            "UNKNOWN",
            "não reconstitui perfeitamente",
            "sem chaves",
            "autorização humana explícita",
        ):
            self.assertIn(s.casefold(), decision.casefold())
        self.assertIn("50x", decision)
        self.assertIn("offline_paper", decision)
        self.assertIn("D383", self.read("docs/VALIDATION_PLAN.md"))
        self.assertIn("Bybit V5", self.read("docs/STATUS.md"))
        self.assertIn("Bybit V5", self.read("docs/OPERATIONAL_STATE.md"))


if __name__ == "__main__":
    unittest.main()
