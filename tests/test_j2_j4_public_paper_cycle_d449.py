"""D449: genuine existing 50-contract research journal -> PAPER via callbacks.

Network is patched forbidden; Bybit frames, catalog and quotes are EXPLICIT
fixtures. The pipeline itself invokes real D434/D435, AUTO2, AUTO4, D425,
D391 and J5 code with no fake financial objects in those journals.
"""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.bybit_closed_stream_cache import (
    HOUR_MS, OfflineReviewedStreamScope, SQLiteOfflineClosedStreamJournal,
)
from crypto_intelligence_agent.bybit_instrument_volume_contract import BybitLinearInstrumentResearch
from crypto_intelligence_agent.bybit_paginated_universe_research import BybitInstrumentScanResearch
from crypto_intelligence_agent.bybit_public_ticker_state_d385 import BybitTickerQuote, SOURCE
from crypto_intelligence_agent.bybit_ws_offline_pipeline import ingest_offline_ws_batch
from crypto_intelligence_agent.j2_j4_public_paper_cycle_d449 import (
    PaperPublicCycleConfig, PublicPaperCycle,
)
from crypto_intelligence_agent.j2_observed_paper_entry_d447 import ObservedPaperEntryPolicy
from crypto_intelligence_agent.j4_automatic_entry_materializer_d448 import PaperEntryExitPolicy
from crypto_intelligence_agent.j4_private_paper_ws_operator_d425 import load_private_paper_routes
from crypto_intelligence_agent.j5_owner_paper_positions_d446 import read_owner_paper_positions
from crypto_intelligence_agent.market_data import DataGapError, DataValidationError
from crypto_intelligence_agent.paper_margin_preflight import PaperLinearContractFixture
from crypto_intelligence_agent.paper_position_reservations import SQLitePaperPositionJournal
from crypto_intelligence_agent.paper_risk_gate import PaperRiskLimits, PaperRiskObservation
from crypto_intelligence_agent.research_registry_catalog import load_reviewed_registry
from crypto_intelligence_agent.synthetic_order_lifecycle import PaperOrderStatus, PaperVenue
from crypto_intelligence_agent.synthetic_partial_exits import ExitBasis, SyntheticExitTranche
from crypto_intelligence_agent.synthetic_position_state import SyntheticLeverageSettings
from scripts.demo_j2_prospective_bybit_research_d436 import CONFIG

FIRST = 1_793_577_600_000  # 2026-11-02 00:00 UTC (expanded-52 PIT available)
LAST = FIRST + 24 * HOUR_MS
DECISION = LAST + HOUR_MS
RECEIPT = DECISION + 2000
SIZE = 50
ENTRY = ObservedPaperEntryPolicy(
    target_distance_bps=Decimal("200"), stop_distance_bps=Decimal("50"),
    first_tranche_fraction=Decimal("0.30"),
    entry_fee_bps=Decimal("6"), exit_fee_bps=Decimal("6"),
    entry_adverse_slippage_bps=Decimal("3"),
    exit_adverse_slippage_bps=Decimal("3"),
)
EXITS = PaperEntryExitPolicy(
    stop_distance_bps=Decimal("50"),
    target_distances_bps=(Decimal("200"), Decimal("300")),
    tranches=(
        SyntheticExitTranche(ExitBasis.INITIAL_POSITION, Decimal("30")),
        SyntheticExitTranche(ExitBasis.INITIAL_POSITION, Decimal("20")),
    ),
    runner_floor_percent=Decimal("50"), synthetic_lot_step_units=Decimal("0.01"),
    entry_fee_bps=Decimal("6"), exit_fee_bps=Decimal("6"),
    entry_adverse_slippage_bps=Decimal("3"),
    exit_adverse_slippage_bps=Decimal("3"),
)
LIMITS = PaperRiskLimits(
    max_order_notional_quote=Decimal("1000"),
    max_symbol_exposure_quote=Decimal("2000"),
    max_portfolio_exposure_quote=Decimal("5000"),
    max_realized_loss_today_quote=Decimal("50"),
    max_pending_open_orders=1, max_market_age_ms=3000,
)
SETTINGS = PaperPublicCycleConfig(
    research=CONFIG, entry=ENTRY, exits=EXITS, limits=LIMITS,
    leverage=SyntheticLeverageSettings(50),
    margin_quote=Decimal("4.20"),
)


def scope_and_symbols():
    snapshot = load_reviewed_registry("expanded-52", as_of_ms=FIRST)
    bases = ["BTC", "ETH"] + [
        b for b in sorted(snapshot.verified_crypto_bases)
        if b not in ("BTC", "ETH")
    ][:SIZE - 2]
    assert len(bases) == SIZE
    members = tuple(BybitLinearInstrumentResearch(
        base + "USDT", base, "USDT", "USDT",
        FIRST, FIRST - 35 * 86_400_000, Decimal("50"),
        Decimal("0.01"), Decimal("0.01"), snapshot.sha256_digest,
    ) for base in bases)
    scan = BybitInstrumentScanResearch(
        FIRST, snapshot.sha256_digest, 1, SIZE, FIRST, members,
    )
    return OfflineReviewedStreamScope.from_scan(
        scan, registry_variant="expanded-52",
    ), tuple(base + "USDT" for base in bases)


def frame(symbol: str, hour: int):
    opened = FIRST + hour * HOUR_MS
    breakout = symbol == "ETHUSDT" and hour == 24
    return (json.dumps({
        "topic": "kline.60." + symbol, "type": "snapshot",
        "ts": opened + HOUR_MS + 1000,
        "data": [{
            "start": opened, "end": opened + HOUR_MS - 1, "interval": "60",
            "open": "100", "high": "106" if breakout else "101",
            "low": "99", "close": "105" if breakout else "100",
            "volume": "10", "turnover": "40" if breakout else "20",
            "confirm": True, "timestamp": opened + HOUR_MS - 1,
        }],
    }), opened + HOUR_MS + 2000)


def ticker(symbol="ETHUSDT", *, at=RECEIPT, mark="105", seq=10):
    p = Decimal(mark)
    return BybitTickerQuote(
        symbol=symbol, exchange_at_ms=at - 100, received_at_ms=at,
        cross_sequence=seq, last_price=p, mark_price=p, index_price=p,
        bid_price=p - Decimal("0.1"), ask_price=p + Decimal("0.1"),
        bid_size=Decimal("20"), ask_size=Decimal("20"),
        turnover_24h=Decimal("1000000"), volume_24h=Decimal("10000"),
        funding_rate=Decimal("0"), source=SOURCE,
    )


def contract(q):
    return PaperLinearContractFixture(
        venue=PaperVenue.BYBIT_V5, symbol=q.symbol,
        quote_currency="USDT", observed_at_ms=q.received_at_ms - 500,
        fixture_version="fixture_d449_unverified_public_terms",
        max_leverage_assumed=50, price_tick_quote=Decimal("0.01"),
        quantity_step_base=Decimal("0.01"),
        min_quantity_base=Decimal("0.01"),
        min_notional_quote=Decimal("5"), max_notional_quote=None,
    )


def paper_risk(q):
    return PaperRiskObservation(
        venue=PaperVenue.BYBIT_V5, symbol=q.symbol,
        quote_currency="USDT", observed_at_ms=q.received_at_ms,
        mark_price_quote=q.mark_price,
        symbol_exposure_quote=Decimal("0"),
        portfolio_exposure_quote=Decimal("0"),
        realized_loss_today_quote=Decimal("0"),
        pending_open_orders=0, unresolved_open_exists=False,
        kill_switch_active=False,
    )


@unittest.skipUnless(
    os.name == "posix" and hasattr(os, "geteuid") and os.geteuid() != 0,
    "POSIX nonroot owner for private 0700/0600 journals",
)
class Provisional50PaperCycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix="cia-d449-test-")
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.private = root / "paper"
        self.private.mkdir(mode=0o700)
        self.j2 = root / "j2"
        self.j2.mkdir(mode=0o700)
        self.closed = self.j2 / "closed.sqlite"
        self.scope, self.symbols = scope_and_symbols()
        journal = SQLiteOfflineClosedStreamJournal.create(self.closed)
        ack = (json.dumps({
            "success": True, "ret_msg": "", "conn_id": "fixture", "op": "subscribe",
        }), FIRST + 1)
        source = [ack]
        for hour in range(25):
            for symbol in self.symbols:
                source.append(frame(symbol, hour))
        with patch(
            "socket.create_connection",
            side_effect=AssertionError("network forbidden in test"),
        ):
            result = ingest_offline_ws_batch(
                frames=tuple(source), scope=self.scope, journal=journal,
            )
        self.assertEqual(result.appended, SIZE * 25)
        self.cycle = PublicPaperCycle(
            scope=self.scope, closed_journal_path=self.closed,
            private_paper_directory=self.private, config=SETTINGS,
            contract_for_quote=contract, risk_for_quote=paper_risk,
        )

    def all_closes(self, *, omit: str | None = None):
        for sym in self.symbols:
            if sym != omit:
                self.assertEqual(self.cycle.on_confirmed_close(
                    symbol=sym, open_ms=LAST, received_ms=RECEIPT,
                ), "confirmed_close_buffered")

    def test_50_causal_closes_to_one_selected_paper_held_position_and_partial(self):
        self.all_closes(omit="BTCUSDT")
        self.assertEqual(
            self.cycle.on_public_quote(ticker()), "closed_cohort_incomplete",
        )
        self.assertFalse((self.private / "paper-routes.json").exists())
        self.assertEqual(
            self.cycle.on_confirmed_close(
                symbol="BTCUSDT", open_ms=LAST, received_ms=RECEIPT,
            ), "confirmed_close_buffered",
        )
        self.assertEqual(self.cycle.on_public_quote(ticker()),
                         "paper_open_pending_armed")
        self.assertEqual(self.cycle.sanitized_report()["eligible_relative_btc_hypotheses"], 1)
        self.assertEqual(self.cycle.sanitized_report()["pending_paper_open_count"], 1)
        self.assertFalse((self.private / "paper-routes.json").exists())
        later = ticker(at=RECEIPT + 500, seq=11)
        self.assertEqual(
            self.cycle.on_public_quote(later),
            "paper_position_routed_for_continuous_held_monitor",
        )
        router = load_private_paper_routes(self.private)
        self.assertEqual(router.monitored_symbols, frozenset({"ETHUSDT"}))
        position_id = router.monitored_position_ids[0]
        ledger = SQLitePaperPositionJournal(self.private / "paper-positions.sqlite")
        position = ledger.load(position_id)
        self.assertEqual(position.leverage_at_intent, 50)
        self.assertEqual(position.confirmed_remaining_units, Decimal("2"))
        self.assertEqual(position.runner_floor_units, Decimal("1"))
        self.assertEqual(len(position.exit_orders), 0)
        at_target = ticker(at=RECEIPT + 1200, mark="107.3", seq=12)
        self.assertEqual(self.cycle.on_public_quote(at_target),
                         "no_new_paper_candidate")
        current = ledger.load(position_id)
        self.assertEqual(len(current.exit_orders), 1)
        self.assertEqual(current.exit_orders[0].tranche_step, 1)
        self.assertEqual(current.reserved_unfilled_units, Decimal("0.6"))
        self.assertEqual(current.filled_exit_units, 0)
        mobile = read_owner_paper_positions(directory=self.private)
        self.assertEqual(len(mobile["positions"]), 1)
        self.assertEqual(self.cycle.sanitized_report()["held_paper_contract_count"], 1)
        self.assertFalse(self.cycle.sanitized_report()["orders_sent"])
        self.assertFalse(self.cycle.sanitized_report()["marketwide_n50_independently_verified"])

        # Reopen all owner journals in a new process object. No duplicate
        # opening, fill or existing PAPER partial may be materialized.
        fresh = PublicPaperCycle(
            scope=self.scope, closed_journal_path=self.closed,
            private_paper_directory=self.private, config=SETTINGS,
            contract_for_quote=contract, risk_for_quote=paper_risk,
        )
        self.assertEqual(fresh.sanitized_report()["held_paper_contract_count"], 1)
        self.assertEqual(len(ledger.load(position_id).exit_orders), 1)

    def test_d499_held_noncausal_quote_abstains_without_stopping_50_symbol_research(self):
        self.all_closes()
        self.assertEqual(self.cycle.on_public_quote(ticker()),
                         "paper_open_pending_armed")
        self.assertEqual(
            self.cycle.on_public_quote(ticker(at=RECEIPT + 500, seq=11)),
            "paper_position_routed_for_continuous_held_monitor")
        with patch(
            "crypto_intelligence_agent.j2_j4_public_paper_cycle_d449."
            "PaperIntrahourQuoteRouter.process",
            side_effect=DataGapError("private stale public quote"),
        ):
            self.assertEqual(
                self.cycle.on_public_quote(
                    ticker(at=RECEIPT + 700, seq=12)),
                "held_quote_noncausal_abstained",
            )
        self.assertEqual(
            self.cycle.sanitized_report()["event_counts"][
                "held_quote_noncausal_abstained"], 1,
        )
        router = load_private_paper_routes(self.private)
        position = SQLitePaperPositionJournal(
            self.private / "paper-positions.sqlite"
        ).load(router.monitored_position_ids[0])
        self.assertEqual(position.filled_exit_units, 0)
        self.assertEqual(len(position.exit_orders), 0)
        # A later valid market observation resumes the same journal/position.
        self.assertEqual(
            self.cycle.on_public_quote(
                ticker(at=RECEIPT + 1200, mark="107.3", seq=13)),
            "no_new_paper_candidate",
        )
        self.assertEqual(
            len(SQLitePaperPositionJournal(
                self.private / "paper-positions.sqlite"
            ).load(router.monitored_position_ids[0]).exit_orders), 1,
        )

    def test_paper_candidate_waits_for_refreshed_contract_and_new_quote(self):
        self.all_closes()
        seen = []
        def initially_stale(quote):
            seen.append(quote.received_at_ms)
            if len(seen) == 1:
                raise DataGapError("D463 refresh not yet completed")
            return contract(quote)
        self.cycle._contract = initially_stale
        self.assertEqual(
            self.cycle.on_public_quote(ticker()),
            "public_contract_refresh_pending",
        )
        self.assertEqual(self.cycle.sanitized_report()["pending_paper_open_count"],0)
        self.assertEqual(
            self.cycle.sanitized_report()["event_counts"].get(
                "public_contract_refresh_pending",
            ),1,
        )
        # Only the NEXT, newer quote can reserve AUTO2. No invented
        # new signal is injected and the original 50/50 WS cohort remains.
        self.assertEqual(
            self.cycle.on_public_quote(ticker(at=RECEIPT+200,seq=11)),
            "paper_open_pending_armed",
        )
        self.assertEqual(len(seen),2)
        self.assertEqual(self.cycle.sanitized_report()["pending_paper_open_count"],1)
        self.assertFalse(self.cycle.sanitized_report()["orders_sent"])

    def test_silence_in_other_contract_prevents_entries_not_held_exits(self):
        self.all_closes(omit="BTCUSDT")
        self.assertEqual(
            self.cycle.on_public_quote(ticker()),
            "closed_cohort_incomplete",
        )
        self.assertEqual(self.cycle.sanitized_report()["held_paper_contract_count"], 0)
        # No fabricated zero-risk snapshot or PAPER OPEN when one of the 50
        # has not delivered the current confirmed candle.
        self.assertEqual(self.cycle.sanitized_report()["pending_paper_open_count"], 0)

    def test_stale_cohort_abstains_and_does_not_guess_margin(self):
        self.all_closes()
        self.assertEqual(
            self.cycle.on_public_quote(ticker(at=RECEIPT + 125000)),
            "closed_cohort_stale",
        )
        self.assertEqual(self.cycle.sanitized_report()["pending_paper_open_count"], 0)

    def test_mismatched_economic_policy_rejected_before_any_io(self):
        with self.assertRaises(DataValidationError):
            PaperPublicCycleConfig(
                research=CONFIG, entry=ENTRY,
                exits=replace(EXITS, stop_distance_bps=Decimal("80")),
                limits=LIMITS, leverage=SyntheticLeverageSettings(50),
                margin_quote=Decimal("4.20"),
            )


if __name__ == "__main__":
    unittest.main()
