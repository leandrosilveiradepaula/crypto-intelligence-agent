"""J5/PRE5: multi-position selection is single-snapshot, read-only and non-live."""
from contextlib import redirect_stdout
from decimal import Decimal
from html.parser import HTMLParser
from io import StringIO
import json
from pathlib import Path
import sqlite3
import tempfile
from threading import Thread
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.paper_position_inspection import inspect_paper_positions
from crypto_intelligence_agent.paper_position_reservations import SQLitePaperPositionJournal
from crypto_intelligence_agent.synthetic_order_lifecycle import (
    PaperOrderEffect, PaperOrderEvent, PaperOrderEventKind,
    PaperOrderIntent, PaperOrderSide, PaperVenue,
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


def opening(suffix, venue, symbol):
    return PaperOrderIntent(
        intent_id=f"fixture_multi_open_{suffix}",
        fixture_signal_id=f"fixture_multi_signal_{suffix}",
        venue=venue, symbol=symbol,
        position_side=SyntheticSide.LONG, side=PaperOrderSide.BUY,
        effect=PaperOrderEffect.OPEN, requested_units=D(100),
        created_at_ms=T,
    )


def plan():
    return SyntheticExitPlan(
        initial_units=D(100),
        tranches=tuple(
            SyntheticExitTranche(ExitBasis.REMAINING_BALANCE, D(n))
            for n in ("50", "60", "70")
        ),
        residual_floor_percent=D(6),
    )


def exit_order():
    return PaperOrderIntent(
        intent_id="fixture_multi_exit_B",
        fixture_signal_id="fixture_multi_exit_signal_B",
        venue=PaperVenue.BYBIT_V5, symbol="ETHUSDT",
        position_side=SyntheticSide.LONG, side=PaperOrderSide.SELL,
        effect=PaperOrderEffect.REDUCE_ONLY, requested_units=D(10),
        max_reducible_units=D(100), created_at_ms=T + 2,
    )


class LayoutParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.attrs = []
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attrs.append((tag, dict(attrs)))


class MultiPaperPositionsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name)
        self.path = self.home / "positions.sqlite"
        self.writer = SQLitePaperPositionJournal(self.path)
        for suffix, venue, symbol in (
            ("A", PaperVenue.BINANCE_USDM, "BTCUSDT"),
            ("B", PaperVenue.BYBIT_V5, "ETHUSDT"),
        ):
            self.writer.create_position(
                position_id=f"fixture_multi_position_{suffix}",
                opening_intent=opening(suffix, venue, symbol),
                opening_events=(
                    PaperOrderEvent(f"fixture_multi_fill_{suffix}",
                                    PaperOrderEventKind.FILL, T + 1, D(100)),
                ),
                exit_plan=plan(), plan_version="multi-v1",
                synthetic_lot_step_units=D(1), as_of_ms=T + 1,
            )

    def selected(self, ids=("fixture_multi_position_A", "fixture_multi_position_B")):
        return inspect_paper_positions(self.path, tuple(ids))

    def test_named_selection_is_independent_and_never_sums_heterogeneous_units(self):
        before = self.path.read_bytes()
        selected = self.selected()
        self.assertEqual(len(selected), 2)
        self.assertEqual(
            [x.balance.position_id for x in selected],
            ["fixture_multi_position_A", "fixture_multi_position_B"],
        )
        self.assertEqual(
            [x.balance.venue for x in selected],
            [PaperVenue.BINANCE_USDM, PaperVenue.BYBIT_V5],
        )
        data = multi_paper_snapshot(selected)
        self.assertEqual(data["schema_version"], "paper_positions_snapshot_v1")
        self.assertTrue(data["no_cross_instrument_quantity_aggregation"])
        self.assertEqual(len(data["positions"]), 2)
        self.assertEqual(
            [x["symbol_fixture"] for x in data["positions"]],
            ["BTCUSDT", "ETHUSDT"],
        )
        self.assertFalse(data["orders_sent"])
        self.assertFalse(data["live_trading_authorized"])
        self.assertFalse(data["financial_pnl_available"])
        self.assertNotIn("portfolio_total_units", data)
        self.assertNotIn("gross_notional", data)
        self.assertNotIn("pnl", json.dumps(data).lower())
        self.assertEqual(before, self.path.read_bytes())

    def test_explicit_order_retained_and_subset_is_not_implicit_listing(self):
        selected = self.selected(("fixture_multi_position_B",))
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0].balance.symbol, "ETHUSDT")
        swapped = self.selected(("fixture_multi_position_B", "fixture_multi_position_A"))
        self.assertEqual([x.balance.symbol for x in swapped],
                         ["ETHUSDT", "BTCUSDT"])

    def test_duplicate_missing_empty_wildcard_and_oversized_selections_denied(self):
        choices = (
            (), ("fixture_multi_position_A", "fixture_multi_position_A"),
            ("fixture_missing",), ("*",), ("all",),
            ("fixture_multi_position_A", "fixture_not_found"),
            tuple("fixture_missing_" + str(i) for i in range(129)),
        )
        for ids in choices:
            with self.subTest(ids=ids[:2]), self.assertRaises(DataValidationError):
                self.selected(ids)
        with self.assertRaises(DataValidationError):
            inspect_paper_positions(self.path, ["fixture_multi_position_A"])

    def test_corrupt_second_selected_position_does_not_return_partial_results(self):
        with sqlite3.connect(self.path) as con:
            con.execute(
                "UPDATE paper_positions SET payload='{}' WHERE position_id=?",
                ("fixture_multi_position_B",),
            )
        with self.assertRaises(DataValidationError):
            self.selected()
        with self.assertRaises(DataValidationError):
            self.selected(("fixture_multi_position_B",))
        # Separate uncorrupted selected fixture remains individually readable.
        self.assertEqual(self.selected(("fixture_multi_position_A",))[0].balance.symbol,
                         "BTCUSDT")

    def test_all_positions_share_one_sqlite_snapshot_under_concurrent_wal_writer(self):
        # With WAL mode a writer can advance B after A is read while the single
        # inspector transaction keeps the prior B snapshot consistent.
        with sqlite3.connect(self.path) as con:
            self.assertEqual(con.execute("PRAGMA journal_mode=WAL").fetchone()[0], "wal")
        original_read = SQLitePaperPositionJournal._read
        errors = []
        finished = []

        def hooked(con, name):
            record = original_read(con, name)
            if name == "fixture_multi_position_A":
                def advance_second():
                    try:
                        self.writer.reserve_exit(
                            "fixture_multi_position_B", 1, exit_order(),
                            as_of_ms=T + 2,
                        )
                        finished.append(True)
                    except Exception as exc:
                        errors.append(str(exc))
                worker = Thread(target=advance_second, daemon=True)
                worker.start()
                worker.join(timeout=5)
                if worker.is_alive():
                    raise AssertionError("WAL writer blocked during RO snapshot")
            return record

        with patch.object(SQLitePaperPositionJournal, "_read", side_effect=hooked):
            selected = self.selected()
        self.assertFalse(errors, errors)
        self.assertTrue(finished)
        self.assertEqual(selected[0].balance.as_of_ms, T + 1)
        self.assertEqual(selected[1].balance.as_of_ms, T + 1)
        self.assertEqual(selected[1].balance.reserved_unfilled_units, D(0))
        after = self.selected(("fixture_multi_position_B",))[0]
        self.assertEqual(after.balance.as_of_ms, T + 2)
        self.assertEqual(after.balance.reserved_unfilled_units, D(10))

    def test_no_wallet_price_or_pnl_in_export_and_pending_unknown_flag(self):
        order = exit_order()
        self.writer.reserve_exit("fixture_multi_position_B", 1, order, as_of_ms=T + 2)
        self.writer.append_exit_events(
            "fixture_multi_position_B", order.intent_id,
            (
                PaperOrderEvent("fixture_multi_unknown", PaperOrderEventKind.UNKNOWN, T + 3),
            ),
            as_of_ms=T + 3,
        )
        data = multi_paper_snapshot(self.selected())
        b = data["positions"][1]
        self.assertEqual(b["reserved_unfilled_units"], "10")
        self.assertEqual(b["unknown_order_count"], 1)
        self.assertEqual(b["pending_or_unknown_orders"], 1)
        self.assertEqual(data["positions"][0]["unknown_order_count"], 0)
        html = render_paper_positions(self.selected(), TEMPLATE.read_text("utf-8"))
        self.assertIn("UNKNOWN: 1", html)
        self.assertIn("fixture_multi_position_A", html)
        self.assertIn("fixture_multi_position_B", html)
        self.assertIn("Nenhum total consolidado", html) if "Nenhum total consolidado" in html else self.assertIn("Não existe total consolidado", html)
        self.assertNotIn("https://", html)

    def test_safe_mobile_html_and_invalid_template_fail_closed(self):
        template = TEMPLATE.read_text("utf-8")
        html = render_paper_positions(self.selected(), template)
        parsed = LayoutParser()
        parsed.feed(html)
        self.assertEqual(parsed.tags.count("main"), 1)
        self.assertEqual(parsed.tags.count("article"), 2)
        self.assertEqual(
            [a.get("data-position") for tag, a in parsed.attrs
             if tag == "article"],
            ["fixture_multi_position_A", "fixture_multi_position_B"],
        )
        self.assertEqual(
            [(tag, a["href"]) for tag, a in parsed.attrs if "href" in a],
            [("a", "#conteudo-principal")],
        )
        self.assertEqual(
            next(a for tag, a in parsed.attrs if tag == "main")["data-mode"],
            "offline_paper",
        )
        for forbidden in ("form", "input", "button", "script", "iframe", "img", "link"):
            self.assertNotIn(forbidden, parsed.tags)
        self.assertIn("SIMULADO", html)
        self.assertIn("default-src 'none'", html)
        self.assertIn("connect-src 'none'", html)
        for poison in (
            template.replace("{{count}}", "{{unknown}}"),
            template.replace("{{count}}", "{{count}}{{count}}"),
            template.replace("</body>", '<a href="https://example.invalid">x</a></body>'),
            template.replace("</body>", '<script>alert(1)</script></body>'),
        ):
            with self.subTest(poison=len(poison)), self.assertRaises(DataValidationError):
                render_paper_positions(self.selected(), poison)

    def test_cli_deterministic_json_html_and_exclusive_output(self):
        ids = ["--position-id", "fixture_multi_position_A",
               "--position-id", "fixture_multi_position_B"]
        stdout = StringIO()
        with redirect_stdout(stdout):
            main(["--journal", str(self.path), *ids, "--format", "json"])
        data = json.loads(stdout.getvalue())
        self.assertEqual(data["schema_version"], "paper_positions_snapshot_v1")
        self.assertEqual(len(data["positions"]), 2)
        output = self.home / "multi.html"
        before = self.path.read_bytes()
        main(["--journal", str(self.path), *ids, "--output", str(output)])
        self.assertIn("SIMULADO", output.read_text("utf-8"))
        raw = output.read_bytes()
        with self.assertRaises(FileExistsError):
            main(["--journal", str(self.path), *ids, "--output", str(output)])
        self.assertEqual(raw, output.read_bytes())
        self.assertEqual(before, self.path.read_bytes())
        for invalid in (["--all"], ["--input", "/tmp/untrusted.json"]):
            with redirect_stdout(StringIO()), self.assertRaises(SystemExit):
                main(["--journal", str(self.path), *ids, *invalid])

    def test_no_network_when_reopening_positions(self):
        with patch("socket.create_connection",
                   side_effect=AssertionError("network attempted")):
            with patch("urllib.request.urlopen",
                       side_effect=AssertionError("network attempted")):
                inspected = self.selected()
                self.assertEqual(len(inspected), 2)
                self.assertIn("offline_paper", render_paper_positions(
                    inspected, TEMPLATE.read_text("utf-8"),
                ))


if __name__ == "__main__":
    unittest.main()
