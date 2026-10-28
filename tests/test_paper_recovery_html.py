"""J5/PRE8 #268: static PT-BR PAPER recovery UI contract and CLI."""
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from html.parser import HTMLParser
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.paper_order_store import SQLitePaperOrderJournal
from crypto_intelligence_agent.paper_position_reservations import SQLitePaperPositionJournal
from crypto_intelligence_agent.paper_recovery_status import (
    PaperRecoveryState, PaperRecoveryStatus,
)
from scripts.inspect_paper_recovery import main, render_recovery_html


class HTMLContract(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.attributes = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attributes.extend(attrs)


class RecoveryHTMLTests(unittest.TestCase):
    def test_unverified_page_has_explicit_read_only_security_language(self):
        state = PaperRecoveryStatus(
            PaperRecoveryState.UNVERIFIED, "paper_journal_unverified", None,
        )
        html = render_recovery_html(state)
        parsed = HTMLContract()
        parsed.feed(html)
        self.assertTrue(html.startswith("<!doctype html>"))
        self.assertIn('lang="pt-BR"', html)
        self.assertIn("Recuperação PAPER não verificada", html)
        self.assertIn("Novas OPEN autorizadas por esta página", html)
        self.assertIn("Stop nativo", html)
        self.assertIn("Snapshot atômico", html)
        self.assertIn("EXCLUSIVAMENTE PAPER", html)
        self.assertIn('data-state="UNVERIFIED"', html)
        self.assertIn("width=device-width, initial-scale=1", html)
        self.assertIn("@media (max-width: 420px)", html)
        self.assertIn("default-src 'none'", html)
        self.assertIn("connect-src 'none'", html)
        self.assertIn("main", parsed.tags)
        self.assertIn("meta", parsed.tags)
        self.assertIn("style", parsed.tags)
        for forbidden in (
            "script", "form", "button", "input", "iframe",
            "img", "link", "svg", "select", "video", "audio",
        ):
            self.assertNotIn(forbidden, parsed.tags)
        for name, value in parsed.attributes:
            self.assertNotIn(name, ("src", "srcset", "action", "formaction"))
            self.assertFalse(name.startswith("on"))
            if name == "href":
                self.assertEqual(value, "#conteudo")
        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)

    def test_forged_live_flags_and_bad_reason_are_rejected(self):
        state = PaperRecoveryStatus(
            PaperRecoveryState.UNVERIFIED, "paper_journal_unverified", None,
        )
        for field in (
            "orders_sent", "live_trading_authorized", "new_open_authorized",
            "native_stop_verified", "cross_database_atomic_snapshot_available",
        ):
            with self.subTest(field=field), self.assertRaises(DataValidationError):
                render_recovery_html(replace(state, **{field: True}))
        for reason in ("../../private", "<script>alert(1)</script>", "", "A" * 300):
            with self.subTest(reason=reason[:20]), self.assertRaises(DataValidationError):
                render_recovery_html(replace(state, reason=reason))
        with self.assertRaises(DataValidationError):
            render_recovery_html(replace(state, state=PaperRecoveryState.PAPER_FLAT_HYPOTHETICAL_ONLY))
        with self.assertRaises(DataValidationError):
            render_recovery_html(replace(state, state=PaperRecoveryState.BLOCKED))

    def test_missing_journals_render_explicitly_unverified_without_creation(self):
        with TemporaryDirectory() as directory:
            orders = Path(directory) / "private-orders.sqlite"
            positions = Path(directory) / "private-positions.sqlite"
            out = StringIO()
            with redirect_stdout(out):
                result = main([
                    "--orders", str(orders), "--positions", str(positions),
                    "--format", "html",
                ])
            self.assertEqual(result, 2)
            self.assertIn('data-state="UNVERIFIED"', out.getvalue())
            self.assertNotIn(str(directory), out.getvalue())
            self.assertFalse(orders.exists())
            self.assertFalse(positions.exists())

    def test_html_output_exclusive_and_journals_unchanged(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            orders, positions, output = (
                root / "orders.sqlite", root / "positions.sqlite", root / "status.html",
            )
            SQLitePaperOrderJournal(orders)
            SQLitePaperPositionJournal(positions)
            before = (orders.read_bytes(), positions.read_bytes())
            args = [
                "--orders", str(orders), "--positions", str(positions),
                "--format", "html", "--output", str(output),
            ]
            with redirect_stdout(StringIO()):
                self.assertEqual(main(args), 2)
            initial = output.read_text(encoding="utf-8")
            self.assertIn('data-state="UNVERIFIED"', initial)
            self.assertNotIn(str(root), initial)
            error = StringIO()
            with redirect_stderr(error), redirect_stdout(StringIO()):
                self.assertEqual(main(args), 2)
            self.assertIn("indisponível", error.getvalue())
            self.assertNotIn(str(root), error.getvalue())
            self.assertEqual(output.read_text(encoding="utf-8"), initial)
            self.assertEqual((orders.read_bytes(), positions.read_bytes()), before)

    def test_output_same_as_journal_never_overwrites_database(self):
        with TemporaryDirectory() as directory:
            orders = Path(directory) / "orders.sqlite"
            positions = Path(directory) / "positions.sqlite"
            SQLitePaperOrderJournal(orders)
            SQLitePaperPositionJournal(positions)
            original = (orders.read_bytes(), positions.read_bytes())
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                code = main([
                    "--orders", str(orders), "--positions", str(positions),
                    "--format", "html", "--output", str(orders),
                ])
            self.assertEqual(code, 2)
            self.assertEqual((orders.read_bytes(), positions.read_bytes()), original)


if __name__ == "__main__":
    unittest.main()
