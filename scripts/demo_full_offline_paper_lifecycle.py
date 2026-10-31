"""J6/PRE9: finite causal fixture, J2 signal -> AUTO2 -> AUTO4 -> runner.

This research demo must NEVER submit an exchange order or synthesize a FILL
inside an automatic decision. Every FILL is a separately marked fixture
injection. Uses only disposable SQLite and completely invented candles/marks.
"""
from __future__ import annotations

import argparse
from decimal import Decimal
import json
from pathlib import Path
import tempfile

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.offline_paper_batch import run_durable_offline_paper_batch
from crypto_intelligence_agent.offline_paper_durable_cursor import (
    _load_cursor, _verify_cursor_orders,
)
from crypto_intelligence_agent.paper_open_health import audit_paper_open_health
from crypto_intelligence_agent.paper_operator_status import inspect_local_paper_operator_status
from crypto_intelligence_agent.paper_order_store import (
    SQLitePaperOrderJournal, _TABLES as _ORDER_TABLES, _VERSION as _ORDER_VERSION,
)
from crypto_intelligence_agent.paper_position_inspection import (
    _read_database, inspect_paper_position,
)
from crypto_intelligence_agent.paper_position_reservations import SQLitePaperPositionJournal
from crypto_intelligence_agent.paper_portfolio_incident_audit import (
    audit_selected_paper_portfolio_incidents,
)
from crypto_intelligence_agent.paper_runner_close_step import (
    PaperRunnerCloseStepState, step_durable_paper_runner_close,
)
from crypto_intelligence_agent.paper_runner_journal import (
    append_paper_runner_mark, start_paper_runner_journal,
)
from crypto_intelligence_agent.paper_runner_trailing import (
    PaperRunnerMark, PaperRunnerTrailPolicy, PaperRunnerTrailState,
)
from crypto_intelligence_agent.synthetic_order_lifecycle import (
    PaperOrderEffect, PaperOrderEvent, PaperOrderEventKind, PaperOrderSide,
)
from crypto_intelligence_agent.synthetic_partial_exits import (
    ExitBasis, SyntheticExitPlan, SyntheticExitTranche,
)
from scripts.demo_durable_offline_paper_batch import _fixture_inputs
from crypto_intelligence_agent.paper_risk_gate import PaperRiskLimits
from crypto_intelligence_agent.synthetic_entry_hypotheses import CompressionBreakoutConfig
from crypto_intelligence_agent.synthetic_feature_engine import FeatureConfig
from crypto_intelligence_agent.synthetic_order_lifecycle import PaperVenue

D = Decimal
_PID = "fixture_pre9_causal_open_position"


def _policy() -> PaperRunnerTrailPolicy:
    return PaperRunnerTrailPolicy(D(100), D(50), 5000, 5000)


def _plan(open_units: Decimal) -> SyntheticExitPlan:
    return SyntheticExitPlan(
        initial_units=open_units,
        tranches=tuple(
            SyntheticExitTranche(ExitBasis.REMAINING_BALANCE, D(x))
            for x in ("50", "60", "70")
        ),
        residual_floor_percent=D(6),
    )


def _opened_from_cursor(orders_path: Path):
    """Read the actual strategy-generated intent, never invent an OPEN ID."""
    with _read_database(orders_path, _ORDER_TABLES, "paper_order_meta", _ORDER_VERSION) as conn:
        cursor = _load_cursor(conn)
        _verify_cursor_orders(conn, cursor)
        if cursor is None or len(cursor.open_intent_ids) != 1:
            raise DataValidationError("exactly one sealed synthetic OPEN expected")
        entry = SQLitePaperOrderJournal._checked_entry(conn, cursor.open_intent_ids[0])
        if (entry.intent.effect is not PaperOrderEffect.OPEN
                or entry.events or entry.snapshot.filled_total_units != 0):
            raise DataValidationError("AUTO2 OPEN must be pending and unfilled")
        return entry.intent



def _interruption_check(
    orders: Path, positions: Path, *,
    checkpoint: str, expected_reason: str, expected_open_allowed: bool,
    expect_pending_gate: bool = False,
    position_id: str | None = None, cutoff_ms: int | None = None,
    incident_code: str | None = None, incident_severity: str | None = None,
) -> dict[str, object]:
    """Read-only observable checkpoint; expected controls must fail closed."""
    health = audit_paper_open_health(orders, positions, decision_at_ms=cutoff_ms)
    operator = inspect_local_paper_operator_status(orders)
    if (health.reason != expected_reason or
            health.new_open_allowed is not expected_open_allowed or
            health.native_stop_verified or health.orders_sent or
            not operator.durable_cursor_present or
            (expect_pending_gate and operator.pending_or_unresolved_open_count < 1)):
        raise DataValidationError("PAPER interruption health/operator guard mismatch")
    # A health audit admitting a PENDING open never replaces the order risk
    # gate (AUTO6). Report only local evidence, not trade authorization.
    entry = {
        "checkpoint": checkpoint,
        "health_reason": health.reason,
        "health_new_open_allowed_paper_only": health.new_open_allowed,
        "pending_auto6_gate_required": expect_pending_gate,
        "native_stop_verified": False,
        "orders_sent": False,
        "live_trading_authorized": False,
    }
    if position_id is not None:
        if cutoff_ms is None or incident_code is None or incident_severity is None:
            raise DataValidationError("explicit PAPER incident expectations required")
        report = audit_selected_paper_portfolio_incidents(
            positions, (position_id,), as_of_ms=cutoff_ms,
            max_checkpoint_age_ms=10_000, opening_order_path=orders,
        ).sanitized_report()
        if (report["batch_block_code"] is not None or
                len(report["positions"]) != 1 or
                report["positions"][0]["incident_code"] != incident_code or
                report["positions"][0]["severity"] != incident_severity or
                report["native_stop_verified"] or report["orders_sent"]):
            raise DataValidationError("PAPER interruption portfolio audit mismatch")
        entry["incident_code"] = incident_code
        entry["incident_severity"] = incident_severity
    return entry


def _isolated_identity_mismatch(
    root: Path, orders: Path, opening_intent, opened_event: PaperOrderEvent,
) -> dict[str, object]:
    """Forge only an isolated AUTO4 fixture, NEVER mutate the causal path."""
    isolated = root / "forged_position.sqlite"
    fixture_position = SQLitePaperPositionJournal(isolated)
    bad_event = PaperOrderEvent(
        "fixture_pre10_other_open_fill", PaperOrderEventKind.FILL,
        opened_event.event_at_ms, opening_intent.requested_units)
    fixture_position.create_position(
        position_id=_PID, opening_intent=opening_intent,
        opening_events=(bad_event,), exit_plan=_plan(opening_intent.requested_units),
        plan_version="fixture_pre10_bad_open_v1",
        synthetic_lot_step_units=D("0.01"), as_of_ms=opened_event.event_at_ms)
    health = audit_paper_open_health(
        orders, isolated, decision_at_ms=opened_event.event_at_ms)
    incident = audit_selected_paper_portfolio_incidents(
        isolated, (_PID,), as_of_ms=opened_event.event_at_ms + 1,
        max_checkpoint_age_ms=10_000,
        opening_order_path=orders,
    ).sanitized_report()
    if (health.new_open_allowed or health.reason != "paper_open_health_unknown"
            or len(health.fills) != 1 or
            health.fills[0].reason != "opening_intent_or_fill_events_mismatch"
            or incident["severity"] != "BLOCKED"
            or incident["batch_block_code"] != "INVALID_OR_INCONSISTENT_SELECTED_JOURNALS"
            or incident["observed_count"] != 0):
        raise DataValidationError("forged PAPER position did not fail closed")
    return {
        "checkpoint": "isolated_auto4_mismatched_fill_identity",
        "health_reason": health.reason,
        "health_new_open_allowed_paper_only": False,
        "portfolio_batch_block_code": incident["batch_block_code"],
        "portfolio_severity": incident["severity"],
        "native_stop_verified": False, "orders_sent": False,
        "live_trading_authorized": False,
    }


def run_full_offline_paper_lifecycle() -> dict[str, object]:
    stages = []
    checks = []
    with tempfile.TemporaryDirectory(prefix="cia_pre9_full_lifecycle_") as folder:
        root = Path(folder)
        orders_path = root / "orders.sqlite"
        positions_path = root / "positions.sqlite"
        runner_path = root / "runner.sqlite"
        journal = SQLitePaperOrderJournal(orders_path)
        position = SQLitePaperPositionJournal(positions_path)

        candles, observations = _fixture_inputs()
        strategy = CompressionBreakoutConfig(
            features=FeatureConfig(2, 2, 2, 2),
            compression_bars=2, baseline_bars=2, max_atr_ratio=D("0.6"),
            min_quote_volume_ratio=D(2), cooldown_bars=1,
        )
        limits = PaperRiskLimits(
            max_order_notional_quote=D(400),
            max_symbol_exposure_quote=D(1000),
            max_portfolio_exposure_quote=D(2000),
            max_realized_loss_today_quote=D(50),
            max_pending_open_orders=1, max_market_age_ms=1000,
        )
        batch_inputs = dict(
            observations=observations, strategy=strategy,
            venue=PaperVenue.BINANCE_USDM, requested_units=D(2),
            limits=limits, position_journal_path=positions_path,
            bootstrap_candles=5, max_candles=20,
        )
        first = run_durable_offline_paper_batch(
            candles, journal=journal, max_new_steps=2, **batch_inputs)
        if (first.reserved_open_intents != 1
                or first.processed_steps != 2 or first.orders_sent):
            raise RuntimeError("synthetic signal/risk did not reserve exactly one OPEN")
        opened = _opened_from_cursor(orders_path)
        if (opened.requested_units != D(2)
                or opened.effect is not PaperOrderEffect.OPEN
                or opened.venue is not PaperVenue.BINANCE_USDM):
            raise RuntimeError("strategy OPEN terms differ from durable AUTO2 receipt")
        try:
            inspect_paper_position(positions_path, _PID)
        except DataValidationError:
            pass
        else:
            raise RuntimeError("PENDING without FILL created an invented position")
        checks.append(_interruption_check(
            orders_path, positions_path, checkpoint="pending_open_without_fill",
            expected_reason="no_filled_open_or_position_requires_protection",
            expected_open_allowed=True, expect_pending_gate=True,
            cutoff_ms=opened.created_at_ms))
        stages.append("j2_risk_open_intent_reserved_without_fill")

        # An independent fixture event, NOT a market fill or an engine action.
        open_fill = PaperOrderEvent(
            "fixture_pre9_explicit_open_fill", PaperOrderEventKind.FILL,
            opened.created_at_ms + 1, opened.requested_units,
        )
        filled = journal.append_events(
            opened.intent_id, (open_fill,), as_of_ms=open_fill.event_at_ms)
        if (filled.intent != opened
                or filled.snapshot.filled_total_units != opened.requested_units):
            raise RuntimeError("AUTO2 fixture fill does not match generated OPEN")
        checks.append(_interruption_check(
            orders_path, positions_path, checkpoint="filled_open_without_auto4_position",
            expected_reason="paper_open_unprotected",
            expected_open_allowed=False, cutoff_ms=open_fill.event_at_ms))
        checks.append(_isolated_identity_mismatch(
            root, orders_path, filled.intent, open_fill))
        current = position.create_position(
            position_id=_PID, opening_intent=filled.intent,
            opening_events=filled.events, exit_plan=_plan(opened.requested_units),
            plan_version="fixture_pre9_full_lifecycle_v1",
            synthetic_lot_step_units=D("0.01"), as_of_ms=open_fill.event_at_ms,
        )
        verified = inspect_paper_position(
            positions_path, _PID, opening_order_path=orders_path)
        if (not verified.opening_order_cross_checked
                or verified.balance.opening_intent_id != opened.intent_id):
            raise RuntimeError("AUTO4 opening is not causally linked to AUTO2")
        # Replay of the same fixture does not create a second position.
        restart = SQLitePaperPositionJournal(positions_path)
        recovered = restart.create_position(
            position_id=_PID, opening_intent=filled.intent,
            opening_events=filled.events, exit_plan=_plan(opened.requested_units),
            plan_version="fixture_pre9_full_lifecycle_v1",
            synthetic_lot_step_units=D("0.01"), as_of_ms=open_fill.event_at_ms,
        )
        if recovered != current:
            raise RuntimeError("AUTO4 restart did not recover exact confirmed OPEN")
        checks.append(_interruption_check(
            orders_path, positions_path, checkpoint="auto4_open_confirmed_no_native_stop",
            expected_reason="paper_open_unverified_protection",
            expected_open_allowed=False, position_id=_PID,
            cutoff_ms=open_fill.event_at_ms+1,
            incident_code="PARTIALS_INCOMPLETE", incident_severity="REVIEW"))
        stages.append("explicit_fixture_open_fill_crosschecked_on_restart")

        for step in (1, 2, 3):
            amount = current.tranches[step-1].target_units
            if amount <= 0:
                raise RuntimeError("invalid synthetic partial amount")
            side = (PaperOrderSide.SELL if opened.side is PaperOrderSide.BUY
                    else PaperOrderSide.BUY)
            intent = opened.__class__(
                intent_id=f"fixture_pre9_partial_{step}",
                fixture_signal_id=f"fixture_pre9_partial_signal_{step}",
                venue=opened.venue, symbol=opened.symbol,
                position_side=opened.position_side, side=side,
                effect=PaperOrderEffect.REDUCE_ONLY,
                requested_units=amount,
                max_reducible_units=current.confirmed_remaining_units,
                created_at_ms=current.as_of_ms,
            )
            current = position.reserve_exit(_PID, step, intent, as_of_ms=current.as_of_ms)
            part_fill = PaperOrderEvent(
                f"fixture_pre9_partial_fill_{step}", PaperOrderEventKind.FILL,
                current.as_of_ms + 1, amount)
            current = position.append_exit_events(
                _PID, intent.intent_id, (part_fill,), as_of_ms=part_fill.event_at_ms)
        if (current.filled_exit_units != D("1.88")
                or current.confirmed_remaining_units != D("0.12")
                or current.runner_floor_units != D("0.12")):
            raise RuntimeError("synthetic 50/60/70 conservation failed")
        checks.append(_interruption_check(
            orders_path, positions_path, checkpoint="partial_exits_leave_runner",
            expected_reason="paper_open_unverified_protection",
            expected_open_allowed=False, position_id=_PID,
            cutoff_ms=current.as_of_ms+1,
            incident_code="RUNNER_UNPROTECTED", incident_severity="REVIEW"))
        stages.append("three_explicit_fixture_partial_fills")

        # Mark prices below are arbitrary invented values in quote units.
        policy = _policy()
        mark_t0 = current.as_of_ms + 100
        start_paper_runner_journal(
            runner_path, positions_path, _PID, policy=policy,
            first_mark=PaperRunnerMark(opened.symbol, mark_t0, D(100)),
            as_of_ms=mark_t0,
        )
        prices = ((D(102), D(103), D(102)) if opened.side is PaperOrderSide.BUY
                  else (D(98), D(97), D(98)))
        for n, price in enumerate(prices, 1):
            mark_time = mark_t0 + n*1000
            trail = append_paper_runner_mark(
                runner_path, positions_path, _PID,
                PaperRunnerMark(opened.symbol, mark_time, price),
                policy=policy, as_of_ms=mark_time)
        if trail.state is not PaperRunnerTrailState.TRIGGERED_HYPOTHETICAL_ONLY:
            raise RuntimeError("synthetic RUNNER2 did not trigger")
        stages.append("runner2_hypothetical_trigger")

        action_time = mark_t0 + 3200
        reserved = step_durable_paper_runner_close(
            runner_path, positions_path, _PID, policy=policy,
            as_of_ms=action_time)
        if (reserved.state is not PaperRunnerCloseStepState.RESERVED_PAPER_ONLY
                or reserved.runner_reserved_unfilled_units != D("0.12")
                or reserved.runner_filled_units != 0):
            raise RuntimeError("runner step failed to reserve residual only PAPER")
        replay = step_durable_paper_runner_close(
            runner_path, positions_path, _PID, policy=policy,
            as_of_ms=action_time + 1)
        if (replay.state is not PaperRunnerCloseStepState.PENDING_RECONCILIATION_PAPER_ONLY
                or replay.runner_order_count != 1
                or replay.created_intent_id is not None):
            raise RuntimeError("runner restart would double-reserve")
        before_runner_fill = position.load(_PID)
        if (before_runner_fill.confirmed_remaining_units != D("0.12")
                or before_runner_fill.runner_filled_units != 0):
            raise RuntimeError("reservation incorrectly invented a runner FILL")
        checks.append(_interruption_check(
            orders_path, positions_path, checkpoint="pending_runner_after_restart",
            expected_reason="paper_open_health_unknown",
            expected_open_allowed=False, position_id=_PID,
            cutoff_ms=action_time+1,
            incident_code="RUNNER_EXIT_PENDING_RECONCILIATION",
            incident_severity="REVIEW"))
        stages.append("runner_reduce_only_pending_recovered_without_fill")

        explicit_runner_fill = PaperOrderEvent(
            "fixture_pre9_explicit_runner_fill", PaperOrderEventKind.FILL,
            action_time + 2, D("0.12"))
        position.append_exit_events(
            _PID, reserved.created_intent_id, (explicit_runner_fill,),
            as_of_ms=explicit_runner_fill.event_at_ms)
        after = position.load(_PID)
        portfolio = audit_selected_paper_portfolio_incidents(
            positions_path, (_PID,), as_of_ms=after.as_of_ms + 1,
            max_checkpoint_age_ms=10_000,
            opening_order_path=orders_path)
        inspected = portfolio.sanitized_report()
        if (after.confirmed_remaining_units != 0
                or after.filled_exit_units != D(2)
                or after.runner_filled_units != D("0.12")
                or inspected["batch_block_code"] is not None
                or inspected["positions"][0]["incident_code"] != "RUNNER_CLOSED_PAPER_ONLY"
                or inspected["positions"][0]["severity"] != "INFO"):
            raise RuntimeError("AUTO2/AUTO4 runner close or PRE8 audit diverged")
        checks.append(_interruption_check(
            orders_path, positions_path, checkpoint="fully_flat_after_runner_fill",
            expected_reason="all_paper_positions_fully_flat_hypothetical_only",
            expected_open_allowed=True, position_id=_PID,
            cutoff_ms=after.as_of_ms+1,
            incident_code="RUNNER_CLOSED_PAPER_ONLY", incident_severity="INFO"))
        stages.append("explicit_fixture_runner_fill_and_pre8_audit")

    return {
        "schema_version": "j6_full_offline_paper_lifecycle_v1",
        "mode": "offline_paper",
        "stages": stages,
        "interruption_checks": checks,
        "strategy_open_intent_count": 1,
        "synthetic_open_fill_injected_explicitly": True,
        "synthetic_partial_fills_injected_explicitly": 3,
        "synthetic_runner_fill_injected_explicitly": True,
        "opening_units": "2",
        "partial_exit_units": "1.88",
        "runner_exit_units": "0.12",
        "confirmed_remaining_units": "0",
        "restart_duplicate_orders": 0,
        "crosschecked_auto2_auto4_opening": True,
        "portfolio_positions_observed": 1,
        "market_data_real": False,
        "orders_sent": False,
        "native_stop_verified": False,
        "live_trading_authorized": False,
        "approved_for_live_use": False,
        "financial_pnl_available": False,
        "network_requests": 0,
        "persistent_files_retained": False,
    }


def main(argv: list[str] | None = None) -> None:
    argparse.ArgumentParser(
        description="Demonstra ciclo PAPER inteiramente fictício, de sinal a runner."
    ).parse_args(argv)
    print(json.dumps(run_full_offline_paper_lifecycle(), sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    main()
