"""J5/PRE13 #286: mobile PT-BR PAPER receipt rendering is clear and offline.

Fixtures are synthetic and read-only; displayed margin is a REQUEST at OPEN,
not real collateral or a trading recommendation. Chrome QA tests six widths.
"""
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.market_data import DataValidationError
from scripts.audit_multi_paper_positions_browser import _local_fixture_selected
from scripts.audit_paper_position_browser import _synthetic_fixture_html
from scripts.inspect_paper_position import (
    TEMPLATE as SINGLE_TEMPLATE, paper_position_snapshot, render_paper_position,
)
from scripts.inspect_paper_positions import (
    TEMPLATE as MULTI_TEMPLATE, multi_paper_snapshot, render_paper_positions,
)


class PaperMarginMobilePresentationTests(unittest.TestCase):
    def test_one_margin_receipt_exports_only_requested_terms(self):
        with_margin, legacy = _local_fixture_selected()
        value = paper_position_snapshot(with_margin)
        self.assertEqual(value["schema_version"], "paper_position_snapshot_v1")
        self.assertEqual(value["mode"], "offline_paper")
        margin = value["position"]["margin_intent_requested"]
        self.assertEqual(margin["leverage_at_intent"], 50)
        self.assertEqual(margin["requested_margin_quote"], "5")
        self.assertEqual(margin["quote_currency"], "USDT")
        self.assertEqual(margin["quality"], "synthetic_requested_margin_at_intent_only")
        self.assertFalse(margin["opening_order_cross_checked"])
        for flag in ("actual_position_margin_verified",
                     "venue_leverage_verified", "orders_sent"):
            self.assertFalse(margin[flag])
        data = json.dumps(value, ensure_ascii=False)
        for field in ("hypothetical_mark_quote", "assumed_notional_quote",
                      "account_id", "api_key", "equity", "realized_pnl",
                      "liquidation_price", "wallet_balance"):
            self.assertNotIn(field, data)
        self.assertFalse(value["orders_sent"])
        self.assertFalse(value["financial_pnl_available"])
        self.assertFalse(with_margin.live_trading_authorized)

    def test_legacy_position_never_receives_inferred_50x_or_zero_margin(self):
        _, legacy = _local_fixture_selected()
        snapshot = paper_position_snapshot(legacy)
        self.assertIsNone(snapshot["position"]["margin_intent_requested"])
        self.assertNotIn("leverage_at_intent", snapshot["position"])
        html = render_paper_position(
            legacy, SINGLE_TEMPLATE.read_text(encoding="utf-8"),
        )
        self.assertIn("Não registrada", html)
        self.assertIn("Sem recibo PRE11/PRE12", html)
        self.assertNotIn(">50x (PAPER)<", html)
        self.assertNotIn(">5 USDT<", html)
        self.assertIn("SIMULADO", html)

    def test_single_position_html_renders_50x_and_5_usdt_with_limitation(self):
        html = _synthetic_fixture_html()
        self.assertIn('data-field="margin-leverage">50x (PAPER)</p>', html)
        self.assertIn('data-field="margin-requested">5 USDT</p>', html)
        self.assertIn("Alavancagem solicitada (PAPER)", html)
        self.assertIn("Margem solicitada (PAPER)", html)
        self.assertIn("Não comprova margem efetiva", html)
        self.assertIn("Conferido entre os dois diários locais", html)
        self.assertIn("sem negociação real", html)
        self.assertIn("default-src 'none'", html)
        self.assertIn("connect-src 'none'", html)
        self.assertNotIn("<script", html.lower())
        self.assertNotIn("https://", html)

    def test_multi_positions_keep_one_margin_and_one_unknown_without_aggregation(self):
        selected = _local_fixture_selected()
        report = multi_paper_snapshot(selected)
        self.assertEqual(report["schema_version"], "paper_positions_snapshot_v1")
        self.assertTrue(report["no_cross_instrument_quantity_aggregation"])
        self.assertEqual(len(report["positions"]), 2)
        first, second = report["positions"]
        self.assertEqual(first["margin_intent_requested"]["leverage_at_intent"], 50)
        self.assertEqual(first["margin_intent_requested"]["requested_margin_quote"], "5")
        self.assertIsNone(second["margin_intent_requested"])
        self.assertEqual(first["unknown_order_count"], 0)
        self.assertEqual(second["unknown_order_count"], 1)
        self.assertNotIn("portfolio_margin_quote", report)
        self.assertNotIn("portfolio_notional_quote", report)
        self.assertFalse(report["live_trading_authorized"])

    def test_cards_render_ptbr_without_cross_assigning_margin_or_unknown(self):
        selected = _local_fixture_selected()
        html = render_paper_positions(
            selected, MULTI_TEMPLATE.read_text(encoding="utf-8"),
        )
        marker_a = html.index('data-position="fixture_browse_position_A"')
        marker_b = html.index('data-position="fixture_browse_position_B"')
        self.assertLess(marker_a, marker_b)
        card_a = html[marker_a:marker_b]
        card_b = html[marker_b:html.index("</article>", marker_b)]
        self.assertIn("Alavancagem solicitada (PAPER): 50x", card_a)
        self.assertIn("Margem solicitada (PAPER): 5 USDT", card_a)
        self.assertIn("sem comprovar saldo", card_a)
        self.assertNotIn("50x", card_b)
        self.assertIn("não registradas", card_b)
        self.assertIn("UNKNOWN: 1", card_b)
        self.assertIn("Não existe total consolidado", html)
        self.assertNotIn("https://", html)
        self.assertNotIn("<script", html.lower())

    def test_renderers_refuse_modified_csp_or_untrusted_template(self):
        selected = _local_fixture_selected()
        single = SINGLE_TEMPLATE.read_text(encoding="utf-8")
        multi = MULTI_TEMPLATE.read_text(encoding="utf-8")
        with self.assertRaises(DataValidationError):
            render_paper_position(selected[0], single.replace(
                "connect-src 'none'", "connect-src https:",
            ))
        with self.assertRaises(DataValidationError):
            render_paper_positions(selected, multi.replace(
                "default-src 'none'", "default-src https:",
            ))

    def test_rendering_is_finite_offline_and_does_not_access_exchange(self):
        with patch("socket.create_connection", side_effect=AssertionError("network")):
            with patch("urllib.request.urlopen", side_effect=AssertionError("network")):
                one = _synthetic_fixture_html()
                selected = _local_fixture_selected()
                many = render_paper_positions(
                    selected, MULTI_TEMPLATE.read_text(encoding="utf-8"),
                )
        self.assertIn("SIMULADO", one)
        self.assertIn("SIMULADO", many)
        self.assertIn("5 USDT", one)
        self.assertIn("5 USDT", many)


if __name__ == "__main__":
    unittest.main()
