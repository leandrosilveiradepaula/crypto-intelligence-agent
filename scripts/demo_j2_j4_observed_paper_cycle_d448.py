"""D448 end-to-end OFFLINE protocol replay: confirmed kline -> J2 -> J4 -> J5.

Uses D436's existing genuine *parser/journal code* with fabricated WS frames,
not a public Bybit network session. All fills are explicitly HYPOTHETICAL,
and the only persistent SQLite files are disposable AUTO2 and AUTO4 journals.
"""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from crypto_intelligence_agent.bybit_public_ticker_state_d385 import (
    BybitTickerQuote, SOURCE,
)
from crypto_intelligence_agent.bybit_closed_stream_cache import (
    HOUR_MS, SQLiteOfflineClosedStreamJournal,
)
from crypto_intelligence_agent.j2_prospective_bybit_research_d436 import consume_confirmed_close_batch
from crypto_intelligence_agent.j2_bybit_closed_research_bridge import read_bybit_closed_research_series
from crypto_intelligence_agent.j2_observed_paper_entry_d447 import (
    ObservedPaperEntryPolicy, reserve_observed_paper_entry,
)
from crypto_intelligence_agent.j4_automatic_entry_materializer_d448 import (
    PaperEntryExitPolicy, arm_observed_paper_entry, materialize_observed_paper_entry,
)
from crypto_intelligence_agent.j4_private_paper_ws_operator_d425 import load_private_paper_routes
from crypto_intelligence_agent.j4_paper_conditional_pnl_d454 import conditional_paper_pnl_from_existing_fills
from crypto_intelligence_agent.j5_owner_paper_positions_d446 import read_owner_paper_positions
from crypto_intelligence_agent.paper_margin_preflight import (
    PaperLinearContractFixture, PaperMarginPreflightRequest,
)
from crypto_intelligence_agent.paper_order_store import SQLitePaperOrderJournal
from crypto_intelligence_agent.paper_position_reservations import SQLitePaperPositionJournal
from crypto_intelligence_agent.paper_risk_gate import PaperRiskLimits, PaperRiskObservation
from crypto_intelligence_agent.synthetic_order_lifecycle import PaperVenue
from crypto_intelligence_agent.synthetic_partial_exits import (
    ExitBasis, SyntheticExitTranche,
)
from crypto_intelligence_agent.synthetic_position_state import SyntheticLeverageSettings

from scripts.demo_j2_prospective_bybit_research_d436 import (
    CONFIG, FIRST, SYMBOL, _scope, _frame,
)


def run(*, side: str = "LONG") -> dict:
    if side not in ("LONG", "SHORT"):
        raise ValueError("D448 demo supports LONG or SHORT only")
    if os.name != "posix" or not hasattr(os, "geteuid") or os.geteuid() == 0:
        return {"status": "offline_nonroot_owner_required",
                "network_requests": 0, "orders_sent": False}
    scope = _scope()
    close_decision = FIRST + 25 * HOUR_MS
    with TemporaryDirectory(prefix="cia-d448-full-paper-") as root:
        home = Path(root)
        home.chmod(0o700)
        kline = home / "observed-closed.sqlite"
        SQLiteOfflineClosedStreamJournal.create(kline)
        ack = (json.dumps({
            "success": True, "ret_msg": "", "conn_id": "fixture", "op": "subscribe",
        }), FIRST + 1)
        seed = consume_confirmed_close_batch(
            frames=(ack,) + tuple(_frame(i) for i in range(24)),
            journal_path=kline, scope=scope, symbol=SYMBOL,
            decision_at_ms=FIRST + 24 * HOUR_MS,
            as_of_ms=FIRST + 24 * HOUR_MS + 2_000, config=CONFIG,
        )
        assert seed.status == "observed_no_hypothesis"
        raw, received = _frame(24)
        payload = json.loads(raw)
        if side == "SHORT":
            payload["data"][0].update(close="95", low="94", high="101")
        result = consume_confirmed_close_batch(
            frames=(ack, (json.dumps(payload), received)),
            journal_path=kline, scope=scope, symbol=SYMBOL,
            decision_at_ms=close_decision, as_of_ms=close_decision + 2000,
            config=CONFIG,
        )
        assert result.status == (
            "observed_long_hypothesis_not_authorized" if side == "LONG"
            else "observed_short_hypothesis_not_authorized"
        )
        series = read_bybit_closed_research_series(
            kline, scope=scope, symbol=SYMBOL,
            decision_at_ms=close_decision, as_of_ms=close_decision + 2000,
        )
        mark = Decimal("105") if side == "LONG" else Decimal("95")
        observed_at = close_decision + 2_000
        quote = BybitTickerQuote(
            symbol=SYMBOL, exchange_at_ms=observed_at - 100,
            received_at_ms=observed_at, cross_sequence=11,
            last_price=mark, mark_price=mark, index_price=mark,
            bid_price=mark - Decimal("0.1"),
            ask_price=mark + Decimal("0.1"),
            bid_size=Decimal("20"), ask_size=Decimal("20"),
            turnover_24h=Decimal("10000000"),
            volume_24h=Decimal("100000"), funding_rate=Decimal("0"),
            source=SOURCE,
        )
        order_file = home / "paper-orders.sqlite"
        position_file = home / "paper-positions.sqlite"
        orders = SQLitePaperOrderJournal(order_file)
        positions = SQLitePaperPositionJournal(position_file)
        order_file.chmod(0o600)
        position_file.chmod(0o600)
        exposure = PaperRiskObservation(
            venue=PaperVenue.BYBIT_V5, symbol=SYMBOL,
            quote_currency="USDT", observed_at_ms=observed_at,
            mark_price_quote=mark, symbol_exposure_quote=Decimal(0),
            portfolio_exposure_quote=Decimal(0),
            realized_loss_today_quote=Decimal(0),
            pending_open_orders=0, unresolved_open_exists=False,
            kill_switch_active=False,
        )
        constraints = PaperRiskLimits(
            max_order_notional_quote=Decimal("1000"),
            max_symbol_exposure_quote=Decimal("2000"),
            max_portfolio_exposure_quote=Decimal("5000"),
            max_realized_loss_today_quote=Decimal("50"),
            max_pending_open_orders=1, max_market_age_ms=3000,
        )
        assumptions = PaperLinearContractFixture(
            venue=PaperVenue.BYBIT_V5, symbol=SYMBOL, quote_currency="USDT",
            observed_at_ms=observed_at - 1000,
            fixture_version="fixture_d448_demo_unverified",
            max_leverage_assumed=50, price_tick_quote=Decimal("0.01"),
            quantity_step_base=Decimal("0.01"),
            min_quantity_base=Decimal("0.01"),
            min_notional_quote=Decimal("5"), max_notional_quote=None,
        )
        margin = PaperMarginPreflightRequest(
            SyntheticLeverageSettings(50), mark * Decimal("2") / Decimal(50),
            assumptions, max_contract_age_ms=60_000,
        )
        initial_policy = ObservedPaperEntryPolicy(
            target_distance_bps=Decimal("200"),
            stop_distance_bps=Decimal("50"),
            first_tranche_fraction=Decimal("0.30"),
            entry_fee_bps=Decimal("6"), exit_fee_bps=Decimal("6"),
            entry_adverse_slippage_bps=Decimal("3"),
            exit_adverse_slippage_bps=Decimal("3"),
        )
        pending = reserve_observed_paper_entry(
            series, config=CONFIG, quote=quote, observation=exposure,
            limits=constraints, margin=margin, policy=initial_policy,
            requested_units=Decimal("2"), journal=orders,
            position_journal_path=position_file, now_ms=observed_at,
            allow_hypothetical_paper_open=True,
        )
        assert pending.status == "paper_open_intent_reserved_only"
        exit_policy = PaperEntryExitPolicy(
            stop_distance_bps=Decimal("50"),
            target_distances_bps=(Decimal("200"), Decimal("300")),
            tranches=(
                SyntheticExitTranche(ExitBasis.INITIAL_POSITION, Decimal("30")),
                SyntheticExitTranche(ExitBasis.INITIAL_POSITION, Decimal("20")),
            ),
            runner_floor_percent=Decimal("50"),
            synthetic_lot_step_units=Decimal("0.01"),
            entry_fee_bps=Decimal("6"), exit_fee_bps=Decimal("6"),
            entry_adverse_slippage_bps=Decimal("3"),
            exit_adverse_slippage_bps=Decimal("3"),
        )
        armed = arm_observed_paper_entry(
            private_paper_directory=home, intent_id=pending.intent_id,
            policy=exit_policy, allow_paper_entry_strategy=True,
        )
        assert armed["status"] == "paper_entry_plan_armed"
        later_fill = replace(
            quote, exchange_at_ms=quote.exchange_at_ms + 500,
            received_at_ms=quote.received_at_ms + 500, cross_sequence=12,
        )
        filled = materialize_observed_paper_entry(
            private_paper_directory=home, intent_id=pending.intent_id,
            quote=later_fill, as_of_ms=later_fill.received_at_ms,
            enable_hypothetical_open_fill=True,
        )
        assert filled["status"] == "paper_position_routed_for_continuous_held_monitor"
        router = load_private_paper_routes(
            home, enable_hypothetical_exit_fills=True,
        )
        assert router.monitored_symbols == frozenset({SYMBOL})
        if side == "LONG":
            mark_after = Decimal("107.3")
        else:
            mark_after = Decimal("92.8")
        next_quote = replace(
            later_fill, exchange_at_ms=later_fill.exchange_at_ms + 500,
            received_at_ms=later_fill.received_at_ms + 500,
            cross_sequence=13, mark_price=mark_after, last_price=mark_after,
            bid_price=mark_after - Decimal("0.1"),
            ask_price=mark_after + Decimal("0.1"),
        )
        router.process(next_quote)
        inspected = read_owner_paper_positions(directory=home)
        assert len(inspected["positions"]) == 1
        position = positions.load(router.monitored_position_ids[0])
        assert len(position.exit_orders) == 1
        assert position.exit_orders[0].snapshot.filled_total_units == Decimal(0)
        assert position.leverage_at_intent == 50

        # D477: the target reservation is NOT a fill. Only a later,
        # independent post-latency BBO may conditionally fill AUTO4.
        exit_fill_quote = replace(
            next_quote,
            exchange_at_ms=next_quote.exchange_at_ms + 500,
            received_at_ms=next_quote.received_at_ms + 500,
            cross_sequence=14,
        )
        router.process(exit_fill_quote)
        after_exit_fill = positions.load(router.monitored_position_ids[0])
        assert len(after_exit_fill.exit_orders) == 1
        first_exit = after_exit_fill.exit_orders[0]
        assert first_exit.snapshot.filled_total_units > Decimal(0)
        filled_exit_units = first_exit.snapshot.filled_total_units
        event_count = len(first_exit.events)
        # Same public quote cannot silently double-fill on duplicate delivery.
        router.process(exit_fill_quote)
        after_replay = positions.load(router.monitored_position_ids[0])
        assert after_replay.exit_orders[0].snapshot.filled_total_units == filled_exit_units
        assert len(after_replay.exit_orders[0].events) == event_count
        pnl = conditional_paper_pnl_from_existing_fills(
            private_paper_directory=home,
            position_id=router.monitored_position_ids[0],
        )
        assert pnl.status == "conditional_paper_reference_before_unverified_funding"
        assert pnl.realized_exit_units == filled_exit_units
        assert pnl.conditional_realized_before_funding_quote is not None
        inspected = read_owner_paper_positions(directory=home)
        assert len(inspected["positions"]) == 1

        replay = materialize_observed_paper_entry(
            private_paper_directory=home, intent_id=pending.intent_id,
            quote=None, as_of_ms=next_quote.received_at_ms + 1_000,
            enable_hypothetical_open_fill=True,
        )
        assert replay["hypothetical_open_fill_written"] is False
        return {
            "schema_version": "d448-protocol-replay-to-paper-position-v1",
            "status": "offline_full_paper_path_demonstrated",
            "side": side, "confirmed_ws_close_history_replayed": 25,
            "observed_j2_hypotheses": 1,
            "durable_hypothetical_open_fills": len(orders.load(pending.intent_id).events),
            "persisted_auto4_positions": len(inspected["positions"]),
            "partial_exit_intents_reserved": len(position.exit_orders),
            "hypothetical_partial_exit_fills_recorded": event_count,
            "hypothetical_partial_exit_units": format(filled_exit_units, "f"),
            "duplicate_hypothetical_exit_fills": 0,
            "conditional_pnl_before_funding_available": True,
            "funding_settlement_verified": False,
            "duplicate_open_fills_after_restart": 0,
            "position_visible_in_j5": True,
            "financial_returns_validated": False, "native_stop_installed": False,
            "real_fill_verified": False, "public_market_session_observed": False,
            "network_requests": 0, "j1_accessed": False,
            "orders_sent": False, "approved_for_live_use": False,
        }


if __name__ == "__main__":
    print(json.dumps(run(), sort_keys=True, separators=(",", ":"), allow_nan=False))
