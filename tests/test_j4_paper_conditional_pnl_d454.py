"""D454: durable exact-decimal PAPER reference prices and conditional partial PnL."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import os
from pathlib import Path
import tempfile
import unittest

from crypto_intelligence_agent.j2_observed_paper_entry_d447 import reserve_observed_paper_entry
from crypto_intelligence_agent.j4_automatic_entry_materializer_d448 import (
    arm_observed_paper_entry, materialize_observed_paper_entry,
)
from crypto_intelligence_agent.j4_paper_conditional_pnl_d454 import (
    conditional_paper_pnl_from_existing_fills,
)
from crypto_intelligence_agent.j4_private_paper_ws_operator_d425 import (
    load_private_paper_routes,
)
from crypto_intelligence_agent.j5_owner_paper_positions_d446 import (
    read_owner_paper_positions,
)
from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.paper_order_store import (
    SQLitePaperOrderJournal, _event_json, _decode_event,
)
from crypto_intelligence_agent.paper_position_reservations import SQLitePaperPositionJournal
from crypto_intelligence_agent.synthetic_order_lifecycle import (
    PaperOrderEvent, PaperOrderEventKind,
)
from test_j2_observed_paper_entry_d447 import inputs
from test_j4_automatic_entry_materializer_d448 import POLICY


class PricedPaperEventContractTests(unittest.TestCase):
    def test_legacy_bytes_unchanged_and_priced_event_roundtrips(self):
        legacy = PaperOrderEvent(
            "fixture_old_fill", PaperOrderEventKind.FILL,
            1_800_000_000_000, Decimal("0.25"),
        )
        raw = _event_json(legacy)
        self.assertNotIn("hypothetical_reference_price_quote", raw)
        self.assertEqual(_decode_event(raw), legacy)
        modern = replace(
            legacy, hypothetical_reference_price_quote=Decimal("101.2500"),
        )
        self.assertEqual(_decode_event(_event_json(modern)), modern)
        self.assertNotEqual(raw, _event_json(modern))

    def test_price_is_for_paper_fill_only(self):
        with self.assertRaises(DataValidationError):
            PaperOrderEvent(
                "fixture_bad_ack", PaperOrderEventKind.ACKNOWLEDGED,
                1_800_000_000_000,
                hypothetical_reference_price_quote=Decimal("100"),
            )
        for value in (Decimal("NaN"), Decimal("-1"), Decimal("0"), 100.0):
            with self.subTest(value=repr(value)):
                with self.assertRaises(DataValidationError):
                    PaperOrderEvent(
                        "fixture_bad_price", PaperOrderEventKind.FILL,
                        1_800_000_000_000, Decimal("1"),
                        hypothetical_reference_price_quote=value,
                    )


@unittest.skipUnless(os.name == "posix" and hasattr(os, "geteuid")
                     and os.geteuid() != 0, "owner-only POSIX financial journals")
class DurableConditionalPaperPnLTests(unittest.TestCase):
    def test_long_short_price_survives_restart_and_partial_costs_are_exact(self):
        for side in ("LONG", "SHORT"):
            with self.subTest(side=side), tempfile.TemporaryDirectory(prefix="cia-d454-") as tmp:
                home = Path(tmp)
                home.chmod(0o700)
                order_file = home / "paper-orders.sqlite"
                position_file = home / "paper-positions.sqlite"
                orders = SQLitePaperOrderJournal(order_file)
                positions = SQLitePaperPositionJournal(position_file)
                order_file.chmod(0o600)
                position_file.chmod(0o600)
                args = inputs(side)
                opening = reserve_observed_paper_entry(
                    **args, journal=orders,
                    position_journal_path=position_file,
                )
                self.assertEqual(opening.status, "paper_open_intent_reserved_only")
                arm_observed_paper_entry(
                    private_paper_directory=home, intent_id=opening.intent_id,
                    policy=POLICY, allow_paper_entry_strategy=True,
                )
                first = args["quote"]
                filled_quote = replace(
                    first,
                    exchange_at_ms=args["now_ms"] + 400,
                    received_at_ms=args["now_ms"] + 500,
                    cross_sequence=first.cross_sequence + 1,
                    bid_size=Decimal(20), ask_size=Decimal(20),
                )
                done = materialize_observed_paper_entry(
                    private_paper_directory=home, intent_id=opening.intent_id,
                    quote=filled_quote, as_of_ms=filled_quote.received_at_ms,
                    enable_hypothetical_open_fill=True,
                )
                self.assertTrue(done["hypothetical_open_fill_written"])
                saved_entry = orders.load(opening.intent_id).events[0]
                expected_entry_bbo = (
                    filled_quote.ask_price if side == "LONG"
                    else filled_quote.bid_price
                )
                self.assertEqual(
                    saved_entry.hypothetical_reference_price_quote,
                    expected_entry_bbo,
                )
                router = load_private_paper_routes(
                    home, enable_hypothetical_exit_fills=True,
                )
                position_id = router.monitored_position_ids[0]
                after = Decimal("102.4") if side == "LONG" else Decimal("97.6")
                target_quote = replace(
                    filled_quote, exchange_at_ms=filled_quote.exchange_at_ms + 1200,
                    received_at_ms=filled_quote.received_at_ms + 1200,
                    cross_sequence=filled_quote.cross_sequence + 1,
                    mark_price=after, last_price=after,
                    bid_price=after - Decimal("0.1"),
                    ask_price=after + Decimal("0.1"),
                )
                router.process(target_quote)
                self.assertEqual(
                    positions.load(position_id).reserved_unfilled_units,
                    Decimal("0.75"),
                )
                following = replace(
                    target_quote,
                    exchange_at_ms=target_quote.exchange_at_ms + 500,
                    received_at_ms=target_quote.received_at_ms + 500,
                    cross_sequence=target_quote.cross_sequence + 1,
                )
                router.process(following)
                position = positions.load(position_id)
                self.assertEqual(position.filled_exit_units, Decimal("0.75"))
                exit_event = position.exit_orders[0].events[0]
                expected_exit_bbo = (
                    following.bid_price if side == "LONG"
                    else following.ask_price
                )
                self.assertEqual(
                    exit_event.hypothetical_reference_price_quote,
                    expected_exit_bbo,
                )
                report = conditional_paper_pnl_from_existing_fills(
                    private_paper_directory=home, position_id=position_id,
                )
                self.assertEqual(
                    report.status, "conditional_paper_reference_before_unverified_funding",
                )
                self.assertEqual(report.priced_fill_events, 2)
                self.assertEqual(report.realized_exit_units, Decimal("0.75"))
                signed = Decimal(1) if side == "LONG" else Decimal(-1)
                gross = signed * (expected_exit_bbo - expected_entry_bbo) * Decimal("0.75")
                self.assertEqual(report.gross_realized_reference_quote, gross)
                self.assertGreater(
                    report.conditional_realized_before_funding_quote, Decimal(0),
                )
                self.assertLess(
                    report.conditional_realized_before_funding_quote, gross,
                )
                sanitized = report.sanitized_report()
                self.assertIs(sanitized["funding_settlement_unknown"], True)
                self.assertIs(sanitized["true_realized_net_pnl_available"], False)
                self.assertIs(sanitized["orders_sent"], False)
                replayed = conditional_paper_pnl_from_existing_fills(
                    private_paper_directory=home, position_id=position_id,
                )
                self.assertEqual(report, replayed)
                # Existing J5 defaults remain unchanged, while explicitly
                # requested financial projections are clearly conditional.
                original_ui = read_owner_paper_positions(directory=home)
                self.assertNotIn(
                    "conditional_paper_pnl", original_ui["positions"][0],
                )
                priced_ui = read_owner_paper_positions(
                    directory=home, include_conditional_pnl=True,
                )
                self.assertEqual(
                    priced_ui["positions"][0]["conditional_paper_pnl"],
                    sanitized,
                )
                self.assertFalse(priced_ui["financial_pnl_available"])


if __name__ == "__main__":
    unittest.main()
