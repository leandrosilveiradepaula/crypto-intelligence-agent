"""J5 #236: real read-only local PAPER status and static mobile document."""
from __future__ import annotations

from contextlib import closing, redirect_stderr, redirect_stdout
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal
from hashlib import sha256
from html.parser import HTMLParser
from io import StringIO
from pathlib import Path
import json
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.offline_paper_batch import run_durable_offline_paper_batch
from crypto_intelligence_agent.paper_operator_status import (
    PaperOperatorStatus, inspect_local_paper_operator_status,
)
from crypto_intelligence_agent.paper_order_store import SQLitePaperOrderJournal
from crypto_intelligence_agent.paper_position_reservations import SQLitePaperPositionJournal
from crypto_intelligence_agent.synthetic_order_lifecycle import (
    PaperOrderEvent, PaperOrderEventKind, PaperVenue,
)
from scripts.render_paper_operator_status import main, render_local_paper_status
from test_causal_paper_open import limits, observation
from test_synthetic_research_cycle import candles, config

D = Decimal


class _HTMLSafety(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.attrs = []
    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attrs.extend(attrs)


class PaperOperatorReadOnlyDashboardTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.db = self.root / "orders.sqlite"
        self.positions = self.root / "positions.sqlite"
        self.orders = SQLitePaperOrderJournal(self.db)
        SQLitePaperPositionJournal(self.positions)
        self.cs = candles(n=10)
        self.observations = tuple(
            observation(row.close_time_ms + 1000) for row in self.cs
        )

    def batch(self, steps):
        return run_durable_offline_paper_batch(
            self.cs, observations=self.observations,
            strategy=config().strategy, venue=PaperVenue.BINANCE_USDM,
            requested_units=D(2), limits=limits(),
            journal=self.orders, position_journal_path=self.positions,
            bootstrap_candles=5, max_new_steps=steps,
            max_candles=20,
        )

    def snapshot(self):
        return inspect_local_paper_operator_status(self.db)

    def test_new_journal_no_cursor_has_no_imaginary_running_bot(self):
        before = sha256(self.db.read_bytes()).hexdigest()
        status = self.snapshot()
        self.assertEqual(sha256(self.db.read_bytes()).hexdigest(), before)
        self.assertIsInstance(status, PaperOperatorStatus)
        self.assertFalse(status.new_paper_open_paused)
        self.assertFalse(status.durable_cursor_present)
        self.assertEqual(status.cursor_sequence, 0)
        self.assertEqual(status.accepted_candle_count, 0)
        self.assertEqual(status.pending_or_unresolved_open_count, 0)
        self.assertFalse(status.orders_sent)
        self.assertFalse(status.live_trading_authorized)
        self.assertFalse(status.order_submission_enabled)
        self.assertFalse(status.native_stop_verified)
        with self.assertRaises(FrozenInstanceError):
            status.orders_sent = True

    def test_rolling_cursor_and_pending_open_count_from_real_sqlite(self):
        self.batch(2)
        report = self.snapshot()
        self.assertTrue(report.durable_cursor_present)
        self.assertEqual(report.cursor_sequence, 2)
        self.assertEqual(report.accepted_candle_count, 6)
        self.assertEqual(report.last_closed_candle_at_ms, self.cs[5].close_time_ms)
        self.assertEqual(report.reserved_open_intent_count, 1)
        self.assertEqual(report.pending_or_unresolved_open_count, 1)
        self.assertFalse(report.unknown_open_requires_reconciliation)
        self.assertFalse(report.provider_market_data_authenticated)

    def test_operator_cutoff_rejects_future_cursor_and_pause_without_writes(self):
        self.batch(1)
        initial = self.snapshot()
        assert initial.durable_cursor_present
        cursor_cutoff = self.cs[4].close_time_ms + 1000
        before = self.db.read_bytes()
        with self.assertRaisesRegex(DataValidationError, "newer than decision cutoff"):
            inspect_local_paper_operator_status(self.db, decision_at_ms=cursor_cutoff-1)
        self.assertEqual(
            inspect_local_paper_operator_status(self.db, decision_at_ms=cursor_cutoff),
            initial)
        self.assertEqual(self.db.read_bytes(), before)
        pause_at = cursor_cutoff + 1
        self.orders.set_local_kill_switch(
            pause=True, expected_sequence=0, changed_at_ms=pause_at,
        )
        before = self.db.read_bytes()
        with self.assertRaisesRegex(DataValidationError, "newer than decision cutoff"):
            inspect_local_paper_operator_status(self.db, decision_at_ms=cursor_cutoff)
        self.assertTrue(inspect_local_paper_operator_status(
            self.db, decision_at_ms=pause_at).new_paper_open_paused)
        self.assertEqual(self.db.read_bytes(), before)

    def test_persisted_pause_reflected_across_reopen_and_resume(self):
        self.batch(1)
        self.orders.set_local_kill_switch(
            pause=True, expected_sequence=0,
            changed_at_ms=self.cs[4].close_time_ms + 1001,
        )
        self.orders = SQLitePaperOrderJournal(self.db)
        status = self.snapshot()
        self.assertTrue(status.new_paper_open_paused)
        self.assertEqual(status.pause_sequence, 1)
        html = render_local_paper_status(status)
        self.assertIn("Novas entradas PAPER pausadas", html)
        self.assertIn('data-paused="true"', html)
        self.assertIn("SOMENTE SIMULAÇÃO", html)
        self.assertNotIn("Conectado à Binance", html)
        self.orders.set_local_kill_switch(
            pause=False, expected_sequence=1,
            changed_at_ms=self.cs[5].close_time_ms + 1001,
            acknowledge_resume=True,
        )
        updated = self.snapshot()
        self.assertFalse(updated.new_paper_open_paused)
        self.assertEqual(updated.pause_sequence, 2)

    def test_unknown_open_is_flagged_not_mistaken_for_fill(self):
        self.batch(2)
        with closing(sqlite3.connect(self.db)) as conn:
            row = conn.execute(
                "SELECT intent_id FROM paper_order_intents"
            ).fetchone()
        event = PaperOrderEvent(
            "fixture_status_unknown", PaperOrderEventKind.UNKNOWN,
            self.cs[5].close_time_ms + 1_001, D(0),
        )
        self.orders.append_events(
            row[0], (event,), as_of_ms=event.event_at_ms,
        )
        status = self.snapshot()
        self.assertTrue(status.unknown_open_requires_reconciliation)
        self.assertEqual(status.pending_or_unresolved_open_count, 1)
        self.assertIn("requer reconciliação", render_local_paper_status(status))

    def test_corruption_and_foreign_schema_deny_all_output(self):
        self.batch(1)
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute(
                "UPDATE paper_order_meta SET value='forged' "
                "WHERE key='offline_paper_forward_cursor_v1'"
            )
        with self.assertRaises(DataValidationError):
            self.snapshot()
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["--journal", str(self.db)])
        self.assertEqual(code, 1)
        self.assertEqual(out.getvalue(), "")
        self.assertNotIn(str(self.db), err.getvalue())

    def test_no_unknown_metadata_tolerated(self):
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute(
                "INSERT INTO paper_order_meta(key,value) "
                "VALUES ('unexpected_operator_key', 'evil')"
            )
        with self.assertRaises(DataValidationError):
            self.snapshot()

    def test_responsive_html_has_no_script_forms_external_assets(self):
        self.batch(2)
        html = render_local_paper_status(self.snapshot())
        parser = _HTMLSafety()
        parser.feed(html)
        self.assertIn("main", parser.tags)
        self.assertIn("h1", parser.tags)
        self.assertIn("dl", parser.tags)
        self.assertIn("meta", parser.tags)
        self.assertIn("style", parser.tags)
        for banned in ("script", "button", "form", "iframe", "img", "input",
                       "link", "svg", "audio", "video", "select"):
            self.assertNotIn(banned, parser.tags)
        self.assertIn("width=device-width, initial-scale=1", [v for k,v in parser.attrs if k=="content"])
        self.assertIn("@media (max-width: 420px)", html)
        self.assertIn("grid-template-columns: minmax(0, 1fr)", html)
        for key, value in parser.attrs:
            self.assertNotIn(key, ("src", "srcset", "action", "formaction"))
            if key == "href":
                self.assertEqual(value, "#conteudo")
        self.assertNotIn("https://", html)
        self.assertNotIn("http://", html)

    def test_cli_json_and_exclusive_new_html_output_never_touch_journal(self):
        self.batch(2)
        before = self.db.read_bytes()
        out = StringIO()
        with redirect_stdout(out):
            self.assertEqual(main([
                "--journal", str(self.db), "--format", "json",
            ]), 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["schema_version"], "paper_operator_read_only_status_v1")
        self.assertEqual(payload["accepted_candle_count"], 6)
        self.assertFalse(payload["orders_sent"])
        self.assertFalse(payload["live_trading_authorized"])
        self.assertNotIn(str(self.db), out.getvalue())
        self.assertNotIn("BTCUSDT", out.getvalue())
        output = self.root / "operator.html"
        with redirect_stdout(StringIO()):
            self.assertEqual(main([
                "--journal", str(self.db), "--format", "html",
                "--output", str(output),
            ]), 0)
        html = output.read_text(encoding="utf-8")
        self.assertIn("Estado local do agente PAPER", html)
        self.assertEqual(self.db.read_bytes(), before)
        err = StringIO()
        with redirect_stderr(err):
            self.assertEqual(main([
                "--journal", str(self.db), "--output", str(output),
            ]), 1)
        self.assertNotIn(str(output), err.getvalue())
        self.assertEqual(output.read_text(encoding="utf-8"), html)

    def test_fail_when_journal_missing_or_display_dataclass_forged(self):
        with self.assertRaises(DataValidationError):
            inspect_local_paper_operator_status(self.root / "missing.sqlite")
        self.assertFalse((self.root / "missing.sqlite").exists())
        s = self.snapshot()
        with self.assertRaises(DataValidationError):
            render_local_paper_status(replace(s, reserved_open_intent_count=3))
        with self.assertRaises(DataValidationError):
            render_local_paper_status(replace(s, pause_sequence=True))
        with self.assertRaises(DataValidationError):
            render_local_paper_status(None)

    def test_read_only_status_never_uses_network(self):
        with patch("urllib.request.urlopen", side_effect=AssertionError("internet")):
            with patch("socket.create_connection", side_effect=AssertionError("internet")):
                self.batch(2)
                outcome = self.snapshot()
                html = render_local_paper_status(outcome)
        self.assertFalse(outcome.order_submission_enabled)
        self.assertTrue(html.startswith("<!doctype html>"))


if __name__ == "__main__":
    unittest.main()
