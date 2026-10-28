"""J5/PRE14: all-or-nothing read-only AUTO2/AUTO4 selection crosscheck."""
from contextlib import redirect_stdout
from decimal import Decimal
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.paper_order_store import SQLitePaperOrderJournal
from crypto_intelligence_agent.paper_position_inspection import inspect_paper_positions
from crypto_intelligence_agent.paper_position_reservations import SQLitePaperPositionJournal
from crypto_intelligence_agent.synthetic_order_lifecycle import (
    PaperOrderEffect, PaperOrderEvent, PaperOrderEventKind, PaperOrderIntent,
    PaperOrderSide, PaperVenue,
)
from crypto_intelligence_agent.synthetic_partial_exits import (
    ExitBasis, SyntheticExitPlan, SyntheticExitTranche,
)
from crypto_intelligence_agent.synthetic_position_state import SyntheticSide
from scripts.inspect_paper_positions import (
    TEMPLATE, main, multi_paper_snapshot, render_paper_positions,
)

D = Decimal
T = 1792985000000


class MultiCrosscheckTests(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.orders = Path(folder.name) / "orders.sqlite"
        self.positions = Path(folder.name) / "positions.sqlite"
        orders = SQLitePaperOrderJournal(self.orders)
        positions = SQLitePaperPositionJournal(self.positions)
        plan = SyntheticExitPlan(
            initial_units=D(100),
            tranches=(SyntheticExitTranche(ExitBasis.REMAINING_BALANCE, D(50)),),
            residual_floor_percent=D(0),
        )
        self.ids = ("fixture_cross_A", "fixture_cross_B")
        for suffix, pid in zip(("A", "B"), self.ids):
            opening = PaperOrderIntent(
                intent_id=f"fixture_cross_open_{suffix}",
                fixture_signal_id=f"fixture_cross_signal_{suffix}",
                venue=PaperVenue.BINANCE_USDM, symbol="BTCUSDT",
                position_side=SyntheticSide.LONG, side=PaperOrderSide.BUY,
                effect=PaperOrderEffect.OPEN, requested_units=D(100), created_at_ms=T,
            )
            event = PaperOrderEvent(
                f"fixture_cross_fill_{suffix}", PaperOrderEventKind.FILL,
                T + 1, D(100),
            )
            orders.reserve(opening)
            orders.append_events(opening.intent_id, (event,), as_of_ms=T + 1)
            positions.create_position(
                position_id=pid, opening_intent=opening, opening_events=(event,),
                exit_plan=plan, plan_version="cross-v1",
                synthetic_lot_step_units=D(1), as_of_ms=T + 1,
            )

    def test_opt_in_checks_both_and_legacy_default_remains_unchecked(self):
        original = inspect_paper_positions(self.positions, self.ids)
        self.assertTrue(all(not item.opening_order_cross_checked for item in original))
        before = (self.orders.read_bytes(), self.positions.read_bytes())
        checked = inspect_paper_positions(
            self.positions, self.ids, opening_order_path=self.orders,
        )
        self.assertTrue(all(item.opening_order_cross_checked for item in checked))
        self.assertEqual((self.orders.read_bytes(), self.positions.read_bytes()), before)
        data = multi_paper_snapshot(checked)
        self.assertTrue(all(row["opening_order_cross_checked"]
                            for row in data["positions"]))
        self.assertTrue(all(row["margin_intent_requested"] is None
                            for row in data["positions"]))
        self.assertFalse(data["orders_sent"])
        self.assertFalse(data["live_trading_authorized"])
        html = render_paper_positions(checked, TEMPLATE.read_text(encoding="utf-8"))
        self.assertEqual(html.count("Conferido entre diários locais"), 2)
        self.assertNotIn("<script", html.lower())

    def test_cli_json_with_and_without_crosscheck(self):
        for cross in (False, True):
            args = ["--journal", str(self.positions), "--format", "json"]
            for pid in self.ids:
                args += ["--position-id", pid]
            if cross:
                args += ["--opening-order-journal", str(self.orders)]
            out = StringIO()
            with redirect_stdout(out):
                main(args)
            payload = json.loads(out.getvalue())
            self.assertEqual(
                [row["opening_order_cross_checked"] for row in payload["positions"]],
                [cross, cross],
            )
            self.assertNotIn("wallet_balance", out.getvalue())
            self.assertNotIn("mark_price", out.getvalue())

    def test_missing_open_second_id_rejects_complete_selection(self):
        other = self.positions.parent / "incomplete.sqlite"
        journal = SQLitePaperOrderJournal(other)
        with self.assertRaises(DataValidationError):
            inspect_paper_positions(self.positions, self.ids,
                                    opening_order_path=other)
        self.assertTrue(self.positions.exists())

    def test_same_file_and_missing_file_fail_closed(self):
        for other in (self.positions, self.positions.parent / "missing.sqlite"):
            with self.subTest(other=other), self.assertRaises(DataValidationError):
                inspect_paper_positions(self.positions, self.ids,
                                        opening_order_path=other)
        self.assertFalse((self.positions.parent / "missing.sqlite").exists())

    def test_no_network_during_full_crosscheck(self):
        with patch("socket.create_connection",
                   side_effect=AssertionError("network")):
            with patch("urllib.request.urlopen",
                       side_effect=AssertionError("network")):
                checked = inspect_paper_positions(
                    self.positions, self.ids, opening_order_path=self.orders,
                )
        self.assertEqual(len(checked), 2)


if __name__ == "__main__":
    unittest.main()
