"""J5/PRE4: persisted PAPER position reader is explicitly fail-closed and RO."""
from contextlib import redirect_stdout
from dataclasses import replace
from decimal import Decimal
from hashlib import sha256
from html.parser import HTMLParser
from io import StringIO
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.paper_order_store import SQLitePaperOrderJournal
from crypto_intelligence_agent.paper_position_inspection import inspect_paper_position
from crypto_intelligence_agent.paper_position_reservations import SQLitePaperPositionJournal
from crypto_intelligence_agent.synthetic_order_lifecycle import (
    PaperOrderEffect, PaperOrderEvent, PaperOrderEventKind, PaperOrderIntent,
    PaperOrderSide, PaperOrderStatus, PaperVenue,
)
from crypto_intelligence_agent.synthetic_partial_exits import (
    ExitBasis, SyntheticExitPlan, SyntheticExitTranche,
)
from crypto_intelligence_agent.synthetic_position_state import SyntheticSide
from scripts.inspect_paper_position import (
    TEMPLATE, main, paper_position_snapshot, render_paper_position,
)


D = Decimal
T = 1792985000000


def make_intent(suffix: str = "A", venue: PaperVenue = PaperVenue.BINANCE_USDM):
    return PaperOrderIntent(
        intent_id=f"fixture_open_{suffix}",
        fixture_signal_id=f"fixture_signal_{suffix}",
        venue=venue, symbol="BTCUSDT", position_side=SyntheticSide.LONG,
        side=PaperOrderSide.BUY, effect=PaperOrderEffect.OPEN,
        requested_units=D(100), created_at_ms=T,
    )


def fill(suffix: str = "A", at: int = 1):
    return PaperOrderEvent(
        f"fixture_event_open_{suffix}", PaperOrderEventKind.FILL,
        T + at, D(100),
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


def exit_intent(suffix: str = "A", at: int = 2, units: str = "50"):
    return PaperOrderIntent(
        intent_id=f"fixture_exit_{suffix}",
        fixture_signal_id=f"fixture_signal_exit_{suffix}",
        venue=PaperVenue.BINANCE_USDM, symbol="BTCUSDT",
        position_side=SyntheticSide.LONG, side=PaperOrderSide.SELL,
        effect=PaperOrderEffect.REDUCE_ONLY,
        requested_units=D(units), max_reducible_units=D(100),
        created_at_ms=T + at,
    )


def event(suffix: str, kind: PaperOrderEventKind, at: int, units: str = "0"):
    return PaperOrderEvent(
        f"fixture_event_exit_{suffix}", kind, T + at, D(units),
    )


class ParsedHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.attrs = []
        self.text = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attrs.append((tag, dict(attrs)))

    def handle_data(self, data):
        self.text.append(data)


class ReadOnlyPaperPositionTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.base = Path(folder.name)
        self.db = self.base / "position-paper.sqlite"
        self.order_db = self.base / "order-paper.sqlite"
        self.writer = SQLitePaperPositionJournal(self.db)
        self.entry = make_intent()
        self.open_event = fill()
        self.writer.create_position(
            position_id="fixture_position_A", opening_intent=self.entry,
            opening_events=(self.open_event,), exit_plan=plan(),
            plan_version="paper-plan-v1", synthetic_lot_step_units=D(1),
            as_of_ms=T + 1,
        )
        order_writer = SQLitePaperOrderJournal(self.order_db)
        order_writer.reserve(self.entry)
        order_writer.append_events(
            self.entry.intent_id, (self.open_event,), as_of_ms=T + 1,
        )

    def read(self, *, cross=False):
        return inspect_paper_position(
            self.db, "fixture_position_A",
            opening_order_path=self.order_db if cross else None,
        )

    def test_uses_existing_position_without_changes_and_no_implicit_extra_venue(self):
        before = self.db.read_bytes()
        tables = []
        with sqlite3.connect(self.db) as conn:
            tables = sorted(row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ))
        result = self.read()
        self.assertEqual(result.balance.position_id, "fixture_position_A")
        self.assertEqual(result.balance.venue, PaperVenue.BINANCE_USDM)
        self.assertEqual(result.balance.initial_confirmed_units, D(100))
        self.assertEqual(result.balance.confirmed_remaining_units, D(100))
        self.assertEqual(result.balance.runner_floor_units, D(6))
        self.assertEqual(result.balance.filled_exit_units, D(0))
        self.assertFalse(result.opening_order_cross_checked)
        self.assertEqual(self.db.read_bytes(), before)
        with sqlite3.connect(self.db) as conn:
            later_tables = sorted(row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ))
        self.assertEqual(tables, later_tables)
        self.assertFalse(result.orders_sent)
        self.assertFalse(result.live_trading_authorized)
        self.assertFalse(result.financial_pnl_available)
        self.assertEqual(result.quality, "synthetic_journal_replay_only")

    def test_explicit_secondary_order_journal_matches_no_cross_db_write(self):
        pos_before = sha256(self.db.read_bytes()).hexdigest()
        order_before = sha256(self.order_db.read_bytes()).hexdigest()
        view = self.read(cross=True)
        self.assertTrue(view.opening_order_cross_checked)
        self.assertEqual(view.balance.opening_intent_id, self.entry.intent_id)
        self.assertEqual(pos_before, sha256(self.db.read_bytes()).hexdigest())
        self.assertEqual(order_before, sha256(self.order_db.read_bytes()).hexdigest())
        snapshot = paper_position_snapshot(view)
        self.assertTrue(snapshot["opening_order_cross_checked"])
        self.assertEqual(snapshot["position"]["position_id"], "fixture_position_A")

    def test_partial_fill_and_unknown_reserve_are_not_misrepresented(self):
        exit_a = exit_intent()
        self.writer.reserve_exit("fixture_position_A", 1, exit_a, as_of_ms=T + 2)
        self.writer.append_exit_events(
            "fixture_position_A", exit_a.intent_id,
            (event("partial", PaperOrderEventKind.FILL, 3, "20"),),
            as_of_ms=T + 3,
        )
        self.writer.append_exit_events(
            "fixture_position_A", exit_a.intent_id,
            (event("unknown", PaperOrderEventKind.UNKNOWN, 4),),
            as_of_ms=T + 4,
        )
        view = inspect_paper_position(
            self.db, "fixture_position_A", opening_order_path=self.order_db,
        )
        self.assertEqual(view.balance.filled_exit_units, D(20))
        self.assertEqual(view.balance.reserved_unfilled_units, D(30))
        self.assertEqual(view.balance.confirmed_remaining_units, D(80))
        self.assertEqual(view.balance.unreserved_units, D(50))
        snapshot = paper_position_snapshot(view)
        self.assertEqual(snapshot["position"]["exit_orders"][0]["status"], "UNKNOWN")
        self.assertEqual(snapshot["position"]["exit_orders"][0]["filled_units"], "20")
        self.assertEqual(snapshot["position"]["exit_orders"][0]["reserved_unfilled_units"], "30")
        self.assertTrue(snapshot["position"]["exit_orders"][0]["requires_reconciliation"])
        html = render_paper_position(view, TEMPLATE.read_text("utf-8"))
        self.assertIn("UNKNOWN — resultado incerto", html)
        self.assertIn('data-metric="filled">20</dd>', html)
        self.assertIn('data-metric="reserved">30</dd>', html)
        self.assertIn('data-metric="available">50</dd>', html)
        self.assertIn("Reservas pendentes NÃO são fills", html)
        self.assertNotIn("RESULTADO FINANCEIRO", html)
        self.assertEqual(inspect_paper_position(self.db, "fixture_position_A").balance,
                         view.balance)

    def test_terminal_cancel_releases_only_pending_units(self):
        exit_a = exit_intent()
        self.writer.reserve_exit("fixture_position_A", 1, exit_a, as_of_ms=T + 2)
        self.writer.append_exit_events(
            "fixture_position_A", exit_a.intent_id,
            (event("part", PaperOrderEventKind.FILL, 3, "20"),
             event("timeout", PaperOrderEventKind.UNKNOWN, 4),
             event("cancel", PaperOrderEventKind.CANCELLED, 5)),
            as_of_ms=T + 5,
        )
        view = self.read()
        self.assertEqual(view.balance.filled_exit_units, D(20))
        self.assertEqual(view.balance.reserved_unfilled_units, D(0))
        self.assertEqual(view.balance.confirmed_remaining_units, D(80))
        self.assertEqual(view.balance.unreserved_units, D(80))
        self.assertEqual(view.balance.exit_orders[0].snapshot.status, PaperOrderStatus.CANCELLED)
        self.assertFalse(paper_position_snapshot(view)["position"]["exit_orders"][0][
            "requires_reconciliation"])

    def test_read_is_single_named_position_even_when_db_contains_two(self):
        second = make_intent("B", venue=PaperVenue.BYBIT_V5)
        self.writer.create_position(
            position_id="fixture_position_B",
            opening_intent=second,
            opening_events=(fill("B"),), exit_plan=plan(),
            plan_version="paper-plan-v1", synthetic_lot_step_units=D(1),
            as_of_ms=T + 1,
        )
        a = inspect_paper_position(self.db, "fixture_position_A")
        b = inspect_paper_position(self.db, "fixture_position_B")
        self.assertEqual(a.balance.venue, PaperVenue.BINANCE_USDM)
        self.assertEqual(b.balance.venue, PaperVenue.BYBIT_V5)
        self.assertNotEqual(a.balance.position_id, b.balance.position_id)
        self.assertEqual(len(a.balance.exit_orders), 0)
        with self.assertRaises(DataValidationError):
            inspect_paper_position(self.db, "fixture_position_unknown")

    def test_missing_or_wrong_db_refused_without_creation(self):
        missing = self.base / "must-not-create.sqlite"
        with self.assertRaises(DataValidationError):
            inspect_paper_position(missing, "fixture_position_A")
        self.assertFalse(missing.exists())
        for value in (":memory:", "file:/tmp/unknown?mode=rw", ""):
            with self.subTest(path=value), self.assertRaises(DataValidationError):
                inspect_paper_position(value, "fixture_position_A")
        symlink = self.base / "symlink.sqlite"
        symlink.symlink_to(self.db)
        with self.assertRaises(DataValidationError):
            inspect_paper_position(symlink, "fixture_position_A")
        with self.assertRaises(DataValidationError):
            inspect_paper_position(self.order_db, "fixture_position_A")
        with self.assertRaises(DataValidationError):
            inspect_paper_position(self.db, "not_a_fixture")

    def test_unknown_version_foreign_tables_and_corrupt_digest_fail(self):
        with sqlite3.connect(self.db) as conn:
            conn.execute(
                "UPDATE paper_position_meta SET value='unsupported-v900'"
            )
        with self.assertRaises(DataValidationError):
            self.read()
        with sqlite3.connect(self.db) as conn:
            conn.execute(
                "UPDATE paper_position_meta SET value='paper-position-reservations-v1'"
            )
            conn.execute("CREATE TABLE unexpected_private_table (secret TEXT)")
        with self.assertRaises(DataValidationError):
            self.read()
        with sqlite3.connect(self.db) as conn:
            conn.execute("DROP TABLE unexpected_private_table")
            conn.execute("UPDATE paper_positions SET payload='{}'")
        with self.assertRaises(DataValidationError):
            self.read()

    def test_order_journal_mismatch_and_corruption_fail_closed(self):
        with sqlite3.connect(self.order_db) as conn:
            conn.execute(
                "UPDATE paper_order_intents SET payload='{}' WHERE intent_id=?",
                (self.entry.intent_id,),
            )
        with self.assertRaises(DataValidationError):
            self.read(cross=True)
        # Optional cross-check genuinely optional: verified position remains readable.
        self.assertEqual(self.read().balance.initial_confirmed_units, D(100))
        with self.assertRaises(DataValidationError):
            inspect_paper_position(self.db, "fixture_position_A",
                                   opening_order_path=self.db)

    def test_checked_opening_must_match_exact_durable_events(self):
        other_order_path = self.base / "different-entry.sqlite"
        other = SQLitePaperOrderJournal(other_order_path)
        other.reserve(self.entry)  # Same intent but without FILL
        with self.assertRaises(DataValidationError):
            inspect_paper_position(
                self.db, "fixture_position_A",
                opening_order_path=other_order_path,
            )

    def test_json_contract_minimal_without_account_price_or_profit(self):
        snapshot = paper_position_snapshot(self.read())
        self.assertEqual(snapshot["schema_version"], "paper_position_snapshot_v1")
        self.assertEqual(snapshot["mode"], "offline_paper")
        self.assertEqual(snapshot["quality"], "synthetic_journal_replay_only")
        self.assertFalse(snapshot["live_trading_authorized"])
        self.assertFalse(snapshot["orders_sent"])
        self.assertFalse(snapshot["financial_pnl_available"])
        self.assertEqual(snapshot["position"]["runner_floor_units"], "6")
        self.assertEqual(snapshot["position"]["tranches"][0]["target_units"], "50")
        serialized = json.dumps(snapshot).lower()
        for forbidden in (
            "api_key", "account_id", "access_token", "wallet_address",
            "profit", "funding", "slippage", "notional", "mark_price",
        ):
            self.assertNotIn(forbidden, serialized)

    def test_html_is_accessible_static_and_explicitly_synthetic(self):
        page = render_paper_position(self.read(), TEMPLATE.read_text("utf-8"))
        parser = ParsedHTML()
        parser.feed(page)
        self.assertEqual(parser.tags.count("main"), 1)
        self.assertEqual(parser.tags.count("h1"), 1)
        self.assertTrue(page.lstrip().lower().startswith("<!doctype html>"))
        self.assertEqual(next(a for t, a in parser.attrs if t == "html")["lang"], "pt-BR")
        self.assertEqual(
            next(a for t, a in parser.attrs if t == "main")["data-mode"], "offline_paper")
        links = [(tag, a["href"]) for tag, a in parser.attrs if "href" in a]
        self.assertEqual(links, [("a", "#conteudo-principal")])
        for tag in ("script", "form", "input", "button", "iframe", "img", "link"):
            self.assertNotIn(tag, parser.tags)
        self.assertIn("SIMULADO — NENHUMA ORDEM REAL", page)
        self.assertIn("Nenhuma ordem de saída PAPER registrada", page)
        self.assertIn("Hash local não é assinatura", page)
        self.assertIn("default-src 'none'", page)
        self.assertIn("connect-src 'none'", page)
        self.assertIn("Pular para o conteúdo principal", page)
        self.assertNotIn("http://", page)
        self.assertNotIn("https://", page)

    def test_invalid_or_tampered_template_does_not_render(self):
        template = TEMPLATE.read_text("utf-8")
        for poison in (
            template.replace("{{initial}}", "{{missing}}"),
            template.replace("{{initial}}", "{{initial}}{{initial}}"),
            template.replace("{{checkpoint_iso}}", "{{checkpoint}}"),
            template.replace("</body>", '<a href="https://example.invalid">x</a></body>'),
            template.replace("</body>", '<script>alert(1)</script></body>'),
            template.replace("</body>", "<style>@import url(https://x.invalid)</style></body>"),
        ):
            with self.subTest(chars=len(poison)), self.assertRaises(DataValidationError):
                render_paper_position(self.read(), poison)

    def test_cli_stdout_json_and_html_never_overwrite_input_or_output(self):
        position_bytes = self.db.read_bytes()
        output = StringIO()
        with redirect_stdout(output):
            main(["--journal", str(self.db), "--position-id", "fixture_position_A",
                  "--format", "json", "--opening-order-journal", str(self.order_db)])
        parsed = json.loads(output.getvalue())
        self.assertTrue(parsed["opening_order_cross_checked"])
        self.assertEqual(parsed["position"]["position_id"], "fixture_position_A")
        destination = self.base / "new-paper-export.html"
        main(["--journal", str(self.db), "--position-id", "fixture_position_A",
              "--output", str(destination)])
        self.assertIn("SIMULADO", destination.read_text("utf-8"))
        initial_html = destination.read_bytes()
        with self.assertRaises(FileExistsError):
            main(["--journal", str(self.db), "--position-id", "fixture_position_A",
                  "--output", str(destination)])
        self.assertEqual(destination.read_bytes(), initial_html)
        self.assertEqual(self.db.read_bytes(), position_bytes)
        with self.assertRaises(SystemExit):
            main(["--input", "/tmp/illegal.json"])

    def test_public_tools_never_connect_to_network(self):
        with patch("urllib.request.urlopen", side_effect=AssertionError("network")):
            with patch("socket.create_connection", side_effect=AssertionError("network")):
                snapshot = self.read(cross=True)
                self.assertFalse(snapshot.orders_sent)
                html = render_paper_position(snapshot, TEMPLATE.read_text("utf-8"))
                self.assertIn("offline_paper", html)


if __name__ == "__main__":
    unittest.main()
