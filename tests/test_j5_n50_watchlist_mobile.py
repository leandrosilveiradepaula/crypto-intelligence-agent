"""J5/D310: existing private view consumes exactly reviewed D308 observations."""
from __future__ import annotations

from copy import deepcopy
from html.parser import HTMLParser
import unittest

from crypto_intelligence_agent.j5_n50_private_html import (
    InvalidPrivateResearchView, render_n50_private_html,
)
from test_j5_n50_private_mobile import report


class Inspect(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags: list[str] = []
        self.attributes: list[tuple[str, dict[str, str | None]]] = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attributes.append((tag, dict(attrs)))


class WatchlistMobileTests(unittest.TestCase):
    def test_descriptive_watchlist_is_not_an_order_or_second_ranking(self):
        html = render_n50_private_html(report())
        self.assertIn("Rompimentos e força relativa", html)
        self.assertIn("até cinco contratos", html)
        self.assertIn("Observação de 24 fechamentos auditados", html)
        self.assertIn("Baixa observada <span class=\"muted\">(10)", html)
        self.assertIn("Alta observada <span class=\"muted\">(0)", html)
        self.assertIn("TST19USDT", html)
        self.assertIn("intensidade de turnover", html)
        self.assertIn("não validada fora da amostra", html)
        self.assertNotIn("<script", html.lower())
        self.assertNotIn("fetch(", html.lower())
        self.assertNotIn("websocket", html.lower())
        self.assertNotIn("http://", html.lower())
        self.assertNotIn("https://", html.lower())
        self.assertNotIn("enviar ordem", html.lower())
        self.assertNotIn("preço de entrada", html.lower())
        self.assertNotIn("__WATCHLIST_", html)
        self.assertEqual(html.count('data-kind="descriptive-only"'), 1)
        self.assertEqual(html.count("class=\"observation-list\""), 2)
        p = Inspect()
        p.feed(html)
        self.assertNotIn("button", p.tags)
        self.assertNotIn("form", p.tags)
        self.assertNotIn("input", p.tags)
        self.assertEqual(p.tags.count("tr"), 51)  # original 50 rows unchanged
        self.assertEqual(p.tags.count("article"), 4)
        self.assertFalse(any(
            name.startswith("on") for _, attrs in p.attributes for name in attrs
        ))

    def test_missing_btc_abstains_explicitly_without_fake_ranking(self):
        html = render_n50_private_html(report(btc=False))
        self.assertIn("Indisponível: esta coorte não contém referência BTC", html)
        self.assertEqual(html.count("Sem contexto BTC auditado."), 2)
        self.assertIn("Alta observada <span class=\"muted\">(0)", html)
        self.assertIn("Baixa observada <span class=\"muted\">(0)", html)
        self.assertNotIn("descriptive_watchlist_ready", html)
        self.assertIn("NENHUMA ORDEM", html)

    def test_d308_audit_rejects_internal_relative_inconsistency(self):
        original = report()
        bad = deepcopy(original)
        bad["research_rows"][1]["relative_vs_btc_pct_points"] = "9999"
        with self.assertRaises(InvalidPrivateResearchView):
            render_n50_private_html(bad)
        # Old J5 checked only the field's type/presence, not its relation to BTC.
        self.assertEqual(render_n50_private_html(original).count("<main "), 1)

    def test_d308_rejects_untrusted_volume_metric(self):
        bad = report()
        bad["research_rows"][2]["last_quote_turnover_vs_prior23_mean"] = "0.1"
        # Insufficient volume is not a recommendation, and that asset
        # must not appear in the relevant observed up-breakout list.
        html = render_n50_private_html(bad)
        section = html.split('id="observacoes-combinadas"', 1)[1].split(
            'id="universo"', 1
        )[0]
        self.assertNotIn("TST02USDT", section)
        self.assertIn("Nenhum rompimento sob estes critérios.", section)

    def test_d308_source_claims_are_not_promoted(self):
        bad = report()
        bad["source_authenticated"] = True
        with self.assertRaises(InvalidPrivateResearchView):
            render_n50_private_html(bad)
        bad = report()
        bad["marketwide_top50_verified"] = True
        with self.assertRaises(InvalidPrivateResearchView):
            render_n50_private_html(bad)


if __name__ == "__main__":
    unittest.main()
