"""J6/PRE10 #272: local PAPER alert transitions are deterministic and non-live."""
from __future__ import annotations

from contextlib import closing, redirect_stderr, redirect_stdout
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal
from html.parser import HTMLParser
from io import StringIO
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.offline_paper_batch import run_durable_offline_paper_batch
from crypto_intelligence_agent.paper_operator_alerts import (
    PaperAlertKind, PaperAlertSeverity, summarize_paper_observations,
)
from crypto_intelligence_agent.paper_operator_overview import (
    inspect_local_paper_operator_overview,
)
from crypto_intelligence_agent.paper_operator_status import PaperOperatorStatus
from crypto_intelligence_agent.paper_order_store import SQLitePaperOrderJournal
from crypto_intelligence_agent.paper_position_reservations import SQLitePaperPositionJournal
from crypto_intelligence_agent.paper_recovery_status import (
    PaperRecoveryState, PaperRecoveryStatus, inspect_local_paper_recovery_status,
)
from crypto_intelligence_agent.synthetic_order_lifecycle import (
    PaperOrderEffect, PaperOrderEvent, PaperOrderEventKind, PaperOrderIntent,
    PaperOrderSide, PaperVenue,
)
from crypto_intelligence_agent.synthetic_partial_exits import (
    ExitBasis, SyntheticExitPlan, SyntheticExitTranche,
)
from crypto_intelligence_agent.synthetic_position_state import SyntheticSide
from scripts.observe_paper_operator import (
    main, paper_alert_report_json, render_paper_alert_report_html,
    run_observations,
)
from test_causal_paper_open import limits, observation
from test_synthetic_research_cycle import candles, config


D = Decimal


def durable_operator():
    return PaperOperatorStatus(
        new_paper_open_paused=False,
        pause_sequence=0,
        pause_changed_at_ms=0,
        durable_cursor_present=True,
        cursor_sequence=1,
        accepted_candle_count=5,
        last_closed_candle_at_ms=1_700_000_000_000,
        reserved_open_intent_count=0,
        pending_or_unresolved_open_count=0,
        unknown_open_requires_reconciliation=False,
    )


def flat():
    return PaperRecoveryStatus(
        PaperRecoveryState.PAPER_FLAT_HYPOTHETICAL_ONLY,
        "paper_flat_not_live_verified", durable_operator(),
    )


def blocked():
    return PaperRecoveryStatus(
        PaperRecoveryState.BLOCKED, "paper_operator_paused", durable_operator(),
    )


def unverified():
    return PaperRecoveryStatus(
        PaperRecoveryState.UNVERIFIED, "paper_journal_unverified", None,
    )


class PurePaperAlertTests(unittest.TestCase):
    def test_identical_flat_samples_emit_only_one_hypothetical_alert(self):
        report = summarize_paper_observations((flat(), flat(), flat()))
        self.assertEqual(report.sample_count, 3)
        self.assertEqual(len(report.events), 1)
        self.assertEqual(report.events[0].kind, PaperAlertKind.INITIAL)
        self.assertEqual(
            report.events[0].severity, PaperAlertSeverity.INFO_HYPOTHETICAL_ONLY,
        )
        self.assertFalse(report.had_degraded_state)
        self.assertFalse(report.orders_sent)
        self.assertFalse(report.new_open_authorized)
        with self.assertRaises(FrozenInstanceError):
            report.orders_sent = True

    def test_alerts_fire_on_status_changes_not_repeated_samples(self):
        report = summarize_paper_observations((
            flat(), blocked(), blocked(), unverified(), flat(),
        ))
        self.assertEqual(
            [(x.sample, x.kind.value) for x in report.events], [
                (1, "INITIAL"), (2, "STATUS_CHANGED"),
                (4, "STATUS_CHANGED"), (5, "STATUS_CHANGED"),
            ],
        )
        self.assertEqual(report.events[2].severity, PaperAlertSeverity.CRITICAL)
        self.assertTrue(report.had_degraded_state)
        self.assertEqual(report.final.state, PaperRecoveryState.PAPER_FLAT_HYPOTHETICAL_ONLY)

    def test_invalid_boundaries_and_spoofed_live_status_fail_closed(self):
        for sequence in ((), tuple(flat() for _ in range(17)), [flat()], (None,)):
            with self.subTest(sequence=str(type(sequence))), self.assertRaises(DataValidationError):
                summarize_paper_observations(sequence)
        for status in (
            replace(flat(), orders_sent=True),
            replace(blocked(), new_open_authorized=True),
            replace(unverified(), live_trading_authorized=True),
            replace(flat(), operator=None),
            replace(blocked(), reason="../private/secret"),
        ):
            with self.subTest(state=status.state), self.assertRaises(DataValidationError):
                summarize_paper_observations((status,))

    def test_json_output_does_not_include_private_position_or_market_details(self):
        report = summarize_paper_observations((unverified(), blocked()))
        output = json.dumps(paper_alert_report_json(report))
        self.assertIn('"mode": "offline_paper"', output)
        self.assertIn('"severity": "CRITICAL"', output)
        for forbidden in (
            "account_id", "position_id", "symbol", "price", "pnl",
            "market_data", "credential", "API_KEY",
        ):
            self.assertNotIn(forbidden, output)
        self.assertFalse(paper_alert_report_json(report)["live_trading_authorized"])


class BoundedPaperAlertCLITests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.order_path = self.root / "orders.sqlite"
        self.position_path = self.root / "positions.sqlite"
        self.orders = SQLitePaperOrderJournal(self.order_path)
        self.positions = SQLitePaperPositionJournal(self.position_path)
        self.cs = candles(n=10)
        self.obs = tuple(observation(c.close_time_ms + 1_000) for c in self.cs)

    def batch(self, steps=1):
        return run_durable_offline_paper_batch(
            self.cs, observations=self.obs,
            strategy=config().strategy, venue=PaperVenue.BINANCE_USDM,
            requested_units=D(2), limits=limits(), journal=self.orders,
            position_journal_path=self.position_path,
            bootstrap_candles=5, max_new_steps=steps, max_candles=20,
        )

    def arguments(self, *more):
        return [
            "--orders", str(self.order_path),
            "--positions", str(self.position_path), *more,
        ]

    def test_cli_new_journals_deny_recovery_without_writing_or_network(self):
        before = (self.order_path.read_bytes(), self.position_path.read_bytes())
        out = StringIO()
        with patch("urllib.request.urlopen", side_effect=AssertionError("network")):
            with patch("socket.create_connection", side_effect=AssertionError("network")):
                with redirect_stdout(out):
                    result = main(self.arguments())
        self.assertEqual(result, 2)
        data = json.loads(out.getvalue())
        self.assertEqual(data["final_state"], "UNVERIFIED")
        self.assertEqual(data["alert_count"], 1)
        self.assertEqual(data["events"][0]["severity"], "CRITICAL")
        self.assertNotIn(str(self.root), out.getvalue())
        self.assertEqual(
            (self.order_path.read_bytes(), self.position_path.read_bytes()), before,
        )

    def test_durable_replay_is_informational_only(self):
        self.batch(1)
        out = StringIO()
        with redirect_stdout(out):
            result = main(self.arguments("--samples", "3"))
        self.assertEqual(result, 0)
        data = json.loads(out.getvalue())
        self.assertEqual(data["sample_count"], 3)
        self.assertEqual(data["alert_count"], 1)
        self.assertEqual(data["final_state"], "PAPER_FLAT_HYPOTHETICAL_ONLY")
        self.assertFalse(data["new_open_authorized"])
        self.assertFalse(data["financial_pnl_available"])

