"""D393: actual AUTO4 FILL event audit, never inferred fills or real PnL."""
from __future__ import annotations

from decimal import Decimal as D
from pathlib import Path
import json
import tempfile
import unittest

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.paper_closed_cost_audit_d393 import (
    PaperDeclaredFillReference, audit_closed_paper_costs,
)
from crypto_intelligence_agent.paper_intrahour_proof_d392 import (
    HOUR_START_MS as T, MINUTE_MS as M, POSITION_ID,
    _new_position, _route, _tick, _explicit_fill,
)
from crypto_intelligence_agent.bybit_public_ticker_state_d385 import BybitPublicTickerBook
from crypto_intelligence_agent.paper_position_reservations import SQLitePaperPositionJournal
from crypto_intelligence_agent.synthetic_cost_scenarios import SyntheticFundingEvent
from crypto_intelligence_agent.synthetic_order_lifecycle import (
    PaperOrderEvent, PaperOrderEventKind,
)
from crypto_intelligence_agent.synthetic_partial_costed_replay import SyntheticPartialCostRates

RATES = SyntheticPartialCostRates(
    entry_fee_bps=D("10"), exit_fee_bps=D("10"),
    entry_adverse_slippage_bps=D("5"),
    exit_adverse_slippage_bps=D("5"),
)


class ClosedPaperCostAuditD393Tests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = Path(temp.name) / "paper.sqlite"
        self.store = _new_position(self.db, short=False)
        self.router = _route(self.db, short=False)
        self.book = BybitPublicTickerBook(
            ranked_symbols=("BTCUSDT",), universe_at_ms=T + M,
        )
        self.book.begin_acknowledged_session()

    def fill_first(self):
        first = self.router.process(_tick(
            self.book, minute=12, cs=1, kind="snapshot",
            mark="100.5", bid="101", ask="101.02",
        ))
        self.assertIsNotNone(first)
        _explicit_fill(
            self.store, minute=12, intent_id=first.created_intent_id,
            event_id="fixture_d393_first_fill", units=D(30),
        )
        return first

    def close_all(self):
        self.fill_first()
        second = self.router.process(_tick(
            self.book, minute=19, cs=2, kind="delta",
            mark="102.5", bid="103", ask="103.02",
        ))
        self.assertIsNotNone(second)
        _explicit_fill(
            self.store, minute=19, intent_id=second.created_intent_id,
            event_id="fixture_d393_second_fill", units=D(20),
        )
        self.book.mark_disconnected()
        self.book.begin_acknowledged_session()
        self.router = _route(self.db, short=False)
        third = self.router.process(_tick(
            self.book, minute=27, cs=1, kind="snapshot",
            mark="98", bid="98", ask="98.02",
        ))
        self.assertIsNotNone(third)
        _explicit_fill(
            self.store, minute=27, intent_id=third.created_intent_id,
            event_id="fixture_d393_stop_fill", units=D(50),
        )
        return (
            PaperDeclaredFillReference(
                first.created_intent_id, "fixture_d393_first_fill",
                T + 12 * M + 1, D("101"),
            ),
            PaperDeclaredFillReference(
                second.created_intent_id, "fixture_d393_second_fill",
                T + 19 * M + 1, D("103"),
            ),
            PaperDeclaredFillReference(
                third.created_intent_id, "fixture_d393_stop_fill",
                T + 27 * M + 1, D("98"),
            ),
        )

    def audit(self, references=(), funding=(), rates=RATES):
        return audit_closed_paper_costs(
            self.db, POSITION_ID,
            entry_reference_price_quote=D("100"),
            fill_references=references,
            cost_rates=rates,
            funding_events=funding,
        )

    def test_closed_ledger_exact_fee_and_slippage_conservation(self):
        refs = self.close_all()
        result = self.audit(refs)
        self.assertEqual(result.status, "conditional_closed_paper_cost_reference_only")
        self.assertEqual(result.paper_fill_count, 3)
        self.assertEqual(result.gross_reference_quote, D("-10"))
        self.assertEqual(result.entry_fee_quote, D("10"))
        self.assertEqual(result.exit_fee_quote, D("9.99"))
        self.assertEqual(result.entry_slippage_quote, D("5"))
        self.assertEqual(result.exit_slippage_quote, D("4.995"))
        self.assertEqual(result.signed_funding_quote, D("0"))
        self.assertEqual(
            result.conditional_net_after_supplied_costs_quote, D("-39.985"),
        )
        self.assertEqual(result.confirmed_remaining_units, D(0))
        report = result.sanitized_report()
        self.assertEqual(report["status"], "conditional_closed_paper_cost_reference_only")
        self.assertFalse(report["funding_calendar_complete"])
        self.assertFalse(report["net_pnl_verified"])
        self.assertFalse(report["liquidation_risk_verified"])
        self.assertFalse(report["orders_sent"])
        raw = json.dumps(report)
        self.assertNotIn("BTCUSDT", raw)
        self.assertNotIn(POSITION_ID, raw)
        self.assertNotIn(refs[0].intent_id, raw)

    def test_funding_signed_and_duplicate_event_no_double_count(self):
        refs = self.close_all()
        event = SyntheticFundingEvent(
            "fixture_funding_d393", T + 13 * M, D("7000"), D("2"),
        )
        result = self.audit(refs, (event, event))
        self.assertEqual(result.funding_events_supplied, 1)
        self.assertEqual(result.signed_funding_quote, D("1.4"))
        self.assertEqual(
            result.conditional_net_after_supplied_costs_quote, D("-41.385"),
        )
        receive = SyntheticFundingEvent(
            "fixture_funding_d393_negative", T + 13 * M, D("7000"), D("-2"),
        )
        result = self.audit(refs, (receive,))
        self.assertEqual(result.signed_funding_quote, D("-1.4"))
        self.assertEqual(
            result.conditional_net_after_supplied_costs_quote, D("-38.585"),
        )

    def test_pending_partial_refuses_any_cost_pnl(self):
        # Reserve but do not fill, then append UNKNOWN.
        first = self.router.process(_tick(
            self.book, minute=12, cs=1, kind="snapshot",
            mark="100.5", bid="101", ask="101.02",
        ))
        at = T + 12 * M + 1
        self.store.append_exit_events(
            POSITION_ID, first.created_intent_id,
            (PaperOrderEvent(
                "fixture_d393_unknown", PaperOrderEventKind.UNKNOWN, at,
            ),),
            as_of_ms=at,
        )
        result = self.audit()
        self.assertEqual(result.status, "reconciliation_or_open_balance_no_cost_pnl")
        self.assertEqual(result.confirmed_remaining_units, D(100))
        self.assertEqual(result.pending_reserved_units, D(30))
        self.assertIsNone(result.gross_reference_quote)
        self.assertIsNone(result.conditional_net_after_supplied_costs_quote)
        self.assertIsNone(result.sanitized_report()["conditional_net_after_supplied_costs_quote"])

    def test_reservation_without_fill_does_not_count_as_a_fill(self):
        first = self.router.process(_tick(
            self.book, minute=12, cs=1, kind="snapshot",
            mark="100.5", bid="101", ask="101.02",
        ))
        result = self.audit()
        self.assertEqual(result.paper_fill_count, 0)
        self.assertEqual(result.pending_reserved_units, D(30))
        self.assertIsNone(result.conditional_net_after_supplied_costs_quote)

    def test_mismatching_extra_or_missing_price_receipt_rejected(self):
        from dataclasses import replace
        refs = self.close_all()
        invalid = [
            refs[:2],
            refs + (PaperDeclaredFillReference(
                "fixture_extra", "fixture_unrecorded", T + 25*M, D(110),
            ),),
            (replace(refs[0], event_at_ms=refs[0].event_at_ms + 1), *refs[1:]),
            (refs[0], refs[0], refs[2]),
        ]
        for case in invalid:
            with self.subTest(case=case):
                with self.assertRaises(DataValidationError):
                    self.audit(case)
        self.assertEqual(SQLitePaperPositionJournal(self.db).load(
            POSITION_ID).filled_exit_units, D(100))

    def test_funding_uses_remaining_quantity_and_cannot_invent_payment(self):
        refs = self.close_all()
        invalid = [
            SyntheticFundingEvent(
                "fixture_funding_wrong_size", T + 13 * M,
                D("10000"), D("2"),
            ),
            SyntheticFundingEvent(
                "fixture_funding_late", T + 28 * M,
                D("0.01"), D("2"),
            ),
        ]
        for bad in invalid:
            with self.subTest(event=bad.event_id):
                with self.assertRaises(DataValidationError):
                    self.audit(refs, (bad,))

    def test_cli_process_executes_both_cost_and_unknown_abstention(self):
        import subprocess
        import sys

        for scenario in ("closed", "unknown"):
            with self.subTest(scenario=scenario):
                completed = subprocess.run(
                    [sys.executable, "-m", "scripts.run_paper_cost_audit_d393",
                     "--scenario", scenario],
                    check=True, capture_output=True, text=True, timeout=30,
                )
                result = json.loads(completed.stdout)
                self.assertEqual(result["schema_version"],
                                 "paper-closed-cost-audit-d393-v1")
                self.assertFalse(result["net_pnl_verified"])
                self.assertFalse(result["orders_sent"])
                if scenario == "closed":
                    self.assertEqual(
                        result["conditional_net_after_supplied_costs_quote"],
                        "-41.385",
                    )
                    self.assertEqual(result["paper_fill_count"], 3)
                    self.assertEqual(result["confirmed_remaining_units"], "0")
                else:
                    self.assertEqual(result["status"],
                                     "reconciliation_or_open_balance_no_cost_pnl")
                    self.assertIsNone(
                        result["conditional_net_after_supplied_costs_quote"],
                    )
                    self.assertEqual(result["pending_reserved_units"], "30")

    def test_zero_cost_is_distinct_from_real_net_profit(self):
        refs = self.close_all()
        zero = SyntheticPartialCostRates(D(0), D(0), D(0), D(0))
        x = self.audit(refs, rates=zero)
        self.assertEqual(x.gross_reference_quote, D("-10"))
        self.assertEqual(x.conditional_net_after_supplied_costs_quote, D("-10"))
        self.assertFalse(x.sanitized_report()["net_pnl_verified"])


if __name__ == "__main__":
    unittest.main()
