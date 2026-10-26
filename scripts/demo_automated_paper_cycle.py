"""End-to-end AUTOMATED PAPER fixture: no strategy, market, keys or orders.

Run: python3 -m scripts.demo_automated_paper_cycle
This deterministic demonstration is deliberately NOT a trading recommendation,
backtest, live-venue probe or proof of financial-market functionality.
"""
from __future__ import annotations

from decimal import Decimal
import json
from pathlib import Path
import tempfile

from crypto_intelligence_agent.paper_order_store import SQLitePaperOrderJournal
from crypto_intelligence_agent.paper_position_reservations import SQLitePaperPositionJournal
from crypto_intelligence_agent.paper_risk_gate import (
    PaperRiskLimits, PaperRiskObservation, PaperRiskReason, evaluate_paper_risk,
)
from crypto_intelligence_agent.synthetic_order_lifecycle import (
    PaperOrderEffect, PaperOrderEvent, PaperOrderEventKind, PaperOrderIntent,
    PaperOrderSide, PaperOrderStatus, PaperVenue,
)
from crypto_intelligence_agent.synthetic_partial_exits import (
    ExitBasis, SyntheticExitPlan, SyntheticExitTranche, plan_synthetic_partial_exits,
)
from crypto_intelligence_agent.synthetic_position_state import SyntheticSide


T = 1_792_985_000_000
D = Decimal


def _order_event(venue: PaperVenue, suffix: str,
                 kind: PaperOrderEventKind, offset: int, quantity: str = "0") -> PaperOrderEvent:
    return PaperOrderEvent(
        event_id=f"fixture_event_{venue.value}_{suffix}", kind=kind,
        event_at_ms=T + offset, filled_units=D(quantity),
    )


def simulate_automatic_paper_cycle(venue: PaperVenue) -> dict[str, object]:
    """Simulate a prescribed paper-only sequence for ONE candidate venue.

    The signal, price, order events and fills are made-up engineering fixtures.
    No API, signal generator, exchange acceptance or real risk observation.
    """
    if type(venue) is not PaperVenue:
        raise ValueError("paper demonstration requires explicit candidate enum")
    symbol = "BTCUSDT"  # Fixture label only, NOT an eligible real listing attestation.
    prefix = venue.value
    opening = PaperOrderIntent(
        intent_id=f"fixture_open_{prefix}", fixture_signal_id=f"fixture_signal_{prefix}",
        venue=venue, symbol=symbol, position_side=SyntheticSide.LONG,
        side=PaperOrderSide.BUY, effect=PaperOrderEffect.OPEN,
        requested_units=D(100), created_at_ms=T,
    )
    limits = PaperRiskLimits(
        max_order_notional_quote=D(500),
        max_symbol_exposure_quote=D(1000),
        max_portfolio_exposure_quote=D(2000),
        max_realized_loss_today_quote=D(100),
        max_pending_open_orders=1,
        max_market_age_ms=1000,
    )
    observed = PaperRiskObservation(
        venue=venue, symbol=symbol, quote_currency="USDT", observed_at_ms=T,
        mark_price_quote=D(2),  # Completely synthetic, NOT BTC/USDT price.
        symbol_exposure_quote=D(0), portfolio_exposure_quote=D(0),
        realized_loss_today_quote=D(0), pending_open_orders=0,
        unresolved_open_exists=False, kill_switch_active=False,
    )
    risk = evaluate_paper_risk(opening, limits, observed, decision_at_ms=T)
    if not risk.allowed_for_paper_only or risk.reason is not PaperRiskReason.OPEN_ALLOWED_PAPER_ONLY:
        raise RuntimeError("PAPER risk gate rejected entry, do not create simulated OPEN")

    exit_plan = SyntheticExitPlan(
        initial_units=D(100),
        tranches=tuple(
            SyntheticExitTranche(ExitBasis.REMAINING_BALANCE, D(pct))
            for pct in ("50", "60", "70")
        ),
        residual_floor_percent=D(6),
    )
    schedule = plan_synthetic_partial_exits(exit_plan)
    entry_events = (
        _order_event(venue, "opening_ack", PaperOrderEventKind.ACKNOWLEDGED, 1),
        _order_event(venue, "opening_fill", PaperOrderEventKind.FILL, 2, "100"),
    )
    with tempfile.TemporaryDirectory(prefix="paper_cycle_fixture_") as temp_dir:
        base = Path(temp_dir)
        # Isolated different schemas; neither is a market-data or live account DB.
        orders = SQLitePaperOrderJournal(base / "orders.sqlite")
        orders.reserve(opening)
        confirmed_entry = orders.append_events(
            opening.intent_id, entry_events, as_of_ms=T + 2,
        )
        if (confirmed_entry.snapshot.status is not PaperOrderStatus.FILLED
                or confirmed_entry.snapshot.filled_total_units != D(100)):
            raise RuntimeError("paper opening was not explicitly filled")

        positions = SQLitePaperPositionJournal(base / "positions.sqlite")
        pos_id = f"fixture_position_{prefix}"
        position = positions.create_position(
            position_id=pos_id, opening_intent=confirmed_entry.intent,
            opening_events=confirmed_entry.events,
            exit_plan=exit_plan, plan_version="demo-automatic-paper-v1",
            synthetic_lot_step_units=D(1), as_of_ms=T + 2,
        )
        partials = []
        had_unknown = False
        for step in schedule.allocations:
            at = 3 + (step.step_number - 1) * 3
            intent = PaperOrderIntent(
                intent_id=f"fixture_exit_{prefix}_{step.step_number}",
                fixture_signal_id=f"fixture_exit_signal_{prefix}_{step.step_number}",
                venue=venue, symbol=symbol, position_side=SyntheticSide.LONG,
                side=PaperOrderSide.SELL, effect=PaperOrderEffect.REDUCE_ONLY,
                requested_units=step.exit_units, created_at_ms=T + at,
                max_reducible_units=position.confirmed_remaining_units,
            )
            position = positions.reserve_exit(
                pos_id, step.step_number, intent, as_of_ms=T + at,
            )
            if step.step_number == 2:
                # UNKNOWN holds the reserved quantity; no retry/second OPEN.
                position = positions.append_exit_events(
                    pos_id, intent.intent_id,
                    (_order_event(venue, "second_unknown", PaperOrderEventKind.UNKNOWN,
                                  at + 1),), as_of_ms=T + at + 1,
                )
                had_unknown = position.exit_orders[-1].snapshot.status is PaperOrderStatus.UNKNOWN
            else:
                position = positions.append_exit_events(
                    pos_id, intent.intent_id,
                    (_order_event(venue, f"exit_ack_{step.step_number}",
                                  PaperOrderEventKind.ACKNOWLEDGED, at + 1),),
                    as_of_ms=T + at + 1,
                )
            position = positions.append_exit_events(
                pos_id, intent.intent_id,
                (_order_event(venue, f"exit_fill_{step.step_number}",
                              PaperOrderEventKind.FILL, at + 2,
                              str(step.exit_units)),),
                as_of_ms=T + at + 2,
            )
            final_order = position.exit_orders[-1].snapshot
            if final_order.status is not PaperOrderStatus.FILLED:
                raise RuntimeError("paper exit not reconciled by explicit fictitious FILL")
            if position.reserved_unfilled_units != 0:
                raise RuntimeError("paper exit still holds unaccounted reservation")
            partials.append({
                "step": step.step_number,
                "basis": step.basis.value,
                "filled_units": str(step.exit_units),
                "status": final_order.status.value,
            })
        after_restart = SQLitePaperPositionJournal(base / "positions.sqlite").load(pos_id)
        if (position != after_restart
                or position.initial_confirmed_units != D(100)
                or position.filled_exit_units != D(94)
                or position.confirmed_remaining_units != D(6)
                or position.unreserved_units != D(6)
                or not had_unknown):
            raise RuntimeError("paper fixture position failed conservation/recovery")

    return {
        "mode": "offline_paper",
        "quality": "synthetic_fixture_only",
        "signal_source": "predefined_test_fixture_not_a_validated_strategy",
        "market_data_source": "invented_unit_test_values_not_exchange_data",
        "venue_candidate": venue.value,
        "venue_selected_for_live": False,
        "symbol_fixture": symbol,
        "hypothetical_mark_price_quote": "2",
        "quote_currency_fixture": "USDT",
        "paper_risk_result": risk.reason.value,
        "entry_status": confirmed_entry.snapshot.status.value,
        "initial_confirmed_units": str(position.initial_confirmed_units),
        "exit_steps": partials,
        "filled_exit_units": str(position.filled_exit_units),
        "residual_units": str(position.confirmed_remaining_units),
        "residual_percent_of_initial": "6",
        "unknown_resolved_by_explicit_fixture_fill": had_unknown,
        "recovery_consistent_after_restart": True,
        "approved_for_live_use": False,
        "live_trading_authorized": False,
        "orders_sent": False,
        "real_financial_pnl_available": False,
        "database_retention": "temporary_files_discarded",
    }


def main() -> None:
    result = {
        "demo": "two_independent_synthetic_candidate_venues",
        "mode": "offline_paper",
        "live_trading_authorized": False,
        "orders_sent": False,
        "results": [
            simulate_automatic_paper_cycle(PaperVenue.BINANCE_USDM),
            simulate_automatic_paper_cycle(PaperVenue.BYBIT_V5),
        ],
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
