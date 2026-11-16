"""D382 — prevent reintroducing manual execution as the product destination.

Documentation-only governance regression, with no market data or network.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class AutomatedTargetDocumentationTests(unittest.TestCase):
    def read(self, path: str) -> str:
        return (ROOT / path).read_text(encoding="utf-8")

    def test_d77_supersedes_manual_d06(self):
        decisions = self.read("docs/DECISIONS.md")
        self.assertIn("D06 **HISTÓRICA, SUBSTITUÍDA PELA D77**", decisions)
        self.assertIn("## D382 — horários de velas não são horários obrigatórios de trading", decisions)
        self.assertIn("D77", self.read("AGENTS.md"))
        self.assertIn("Regra anti-regressão D382", self.read("AGENTS.md"))

    def test_intrahour_execution_is_not_hourly_venue_polling(self):
        contract = self.read("docs/AUTOMATED_EXECUTION_SPEC.md")
        self.assertIn("não** é a frequência da tomada de decisão", contract)
        self.assertIn("O Product Owner **não confirma cada operação**", contract)
        self.assertIn("camada **independente de dados intrahorários/tempo real**", contract)
        self.assertIn("proteção e supervisão de posições não", contract)
        self.assertIn("50x aumenta a criticidade do risco", contract)
        architecture = self.read("docs/ARCHITECTURE.md")
        self.assertIn("D382 — duas temporalidades, robô automático", architecture)

    def test_state_and_journeys_keep_automatic_target_distinct_from_live_gate(self):
        product = self.read("docs/PRODUCT_SPEC.md")
        state = self.read("docs/OPERATIONAL_STATE.md")
        journeys = self.read("docs/JOURNEYS.md")
        self.assertIn("robô que detecta oportunidades, abre, acompanha e encerra posições automaticamente", product)
        self.assertIn("alvo D77 = operações AUTOMÁTICAS", state)
        self.assertNotIn("operação manual sem ordens reais nesta fase.", state)
        self.assertIn("gatilhos intrahorários automáticos", journeys)
        self.assertIn("saídas automáticas durante a hora", journeys)
        self.assertIn("ordens reais somente após gate específico", product)
        self.assertIn("nenhuma ordem real até gate live", state)


if __name__ == "__main__":
    unittest.main()
