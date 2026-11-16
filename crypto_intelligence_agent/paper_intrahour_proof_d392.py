"""D392: executable offline PAPER proof, not a strategy or live trading bot.

Drives the real D385 ticker decoder, D391 router, D389 stop-first
coordinator and existing transactional AUTO4 journal. Entry and fills
are EXPLICIT synthetic fixtures, not inferred from crossing target prices.
No REST/WS, credentials, private feeds, production accounts, real costs
or venue orders. This is deliberately an end-to-end ENGINEERING proof.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from .bybit_public_ticker_state_d385 import BybitPublicTickerBook
from .paper_intrahour_quote_router_d391 import (
    PaperIntrahourQuoteRouter, PaperQuoteRoute,
)
from .paper_intrahour_coordinator_d389 import PaperIntrahourDecision
from .paper_intrahour_emergency_stop_d388 import PaperEmergencyStopRule
from .paper_intrahour_target_step_d387 import PaperIntrahourTargetPolicy
from .paper_position_reservations import SQLitePaperPositionJournal
from .synthetic_order_lifecycle import (
    PaperOrderEffect, PaperOrderEvent, PaperOrderEventKind,
    PaperOrderIntent, PaperOrderSide, PaperVenue,
)
from .synthetic_partial_exits import (
    ExitBasis, SyntheticExitPlan, SyntheticExitTranche,
)
from .synthetic_position_state import SyntheticSide
from .market_data import DataValidationError


HOUR_START_MS = int(
    datetime(2026, 11, 16, 10, tzinfo=timezone.utc).timestamp() * 1000
)
MINUTE_MS = 60_000
POSITION_ID = "fixture_d392_open_position"
PLAN_VERSION = "d392-executable-proof-v1"
SYMBOL = "BTCUSDT"


def _frame(*, at_ms: int, cs: int, kind: str,
           mark: str, bid: str, ask: str) -> str:
    data: dict[str, str] = {"symbol": SYMBOL}
    if kind == "snapshot":
        data.update({
            "lastPrice": bid, "markPrice": mark, "indexPrice": mark,
            "bid1Price": bid, "ask1Price": ask,
            "bid1Size": "2", "ask1Size": "3",
        })
    else:
        data.update({
            "lastPrice": bid, "markPrice": mark, "indexPrice": mark,
            "bid1Price": bid, "ask1Price": ask,
        })
    return json.dumps({
        "topic": "tickers." + SYMBOL, "type": kind,
        "ts": at_ms - 25, "cs": cs, "data": data,
    }, sort_keys=True, separators=(",", ":"))


def _new_position(db: Path, *, short: bool) -> SQLitePaperPositionJournal:
    side = SyntheticSide.SHORT if short else SyntheticSide.LONG
    order_side = PaperOrderSide.SELL if short else PaperOrderSide.BUY
    opened = HOUR_START_MS + 5 * MINUTE_MS
    intent = PaperOrderIntent(
        intent_id="fixture_d392_open",
        fixture_signal_id="fixture_d392_signal",
        venue=PaperVenue.BYBIT_V5, symbol=SYMBOL,
        position_side=side, side=order_side,
        effect=PaperOrderEffect.OPEN, requested_units=Decimal(100),
        created_at_ms=opened - 10,
    )
    store = SQLitePaperPositionJournal(db)
    store.create_position(
        position_id=POSITION_ID, opening_intent=intent,
        opening_events=(PaperOrderEvent(
            "fixture_d392_explicit_entry_fill", PaperOrderEventKind.FILL,
            opened, Decimal(100),
        ),),
        exit_plan=SyntheticExitPlan(
            initial_units=Decimal(100),
            tranches=(
                SyntheticExitTranche(ExitBasis.INITIAL_POSITION, Decimal(30)),
                SyntheticExitTranche(ExitBasis.INITIAL_POSITION, Decimal(20)),
            ),
            residual_floor_percent=Decimal(50),
        ),
        plan_version=PLAN_VERSION, synthetic_lot_step_units=Decimal(1),
        as_of_ms=opened,
    )
    return store


def _route(db: Path, *, short: bool) -> PaperIntrahourQuoteRouter:
    return PaperIntrahourQuoteRouter(
        position_path=db, routes=(
            PaperQuoteRoute(
                POSITION_ID,
                PaperEmergencyStopRule(Decimal(102 if short else 99)),
                PaperIntrahourTargetPolicy(
                    PLAN_VERSION,
                    (Decimal(99), Decimal(97)) if short
                    else (Decimal(101), Decimal(103)),
                ),
            ),
        ),
    )


def _tick(book: BybitPublicTickerBook, *, minute: int, cs: int,
          kind: str, mark: str, bid: str, ask: str):
    at_ms = HOUR_START_MS + minute * MINUTE_MS
    return book.ingest(
        _frame(at_ms=at_ms, cs=cs, kind=kind,
               mark=mark, bid=bid, ask=ask),
        received_at_ms=at_ms,
    )


def _snapshot_summary(store: SQLitePaperPositionJournal,
                      *, minute: int, decision: PaperIntrahourDecision) -> dict:
    b = store.load(POSITION_ID)
    return {
        "minute_of_same_hour": minute,
        "decision": decision.value,
        "confirmed_exit_units": str(b.filled_exit_units),
        "reserved_unfilled_units": str(b.reserved_unfilled_units),
        "confirmed_remaining_units": str(b.confirmed_remaining_units),
        "recorded_exit_intents": len(b.exit_orders),
        "native_stop_verified": False,
    }


def _explicit_fill(store: SQLitePaperPositionJournal, *,
                   minute: int, intent_id: str,
                   event_id: str, units: Decimal) -> None:
    at_ms = HOUR_START_MS + minute * MINUTE_MS + 1
    store.append_exit_events(
        POSITION_ID, intent_id,
        (PaperOrderEvent(event_id, PaperOrderEventKind.FILL, at_ms, units),),
        as_of_ms=at_ms,
    )


def demonstrate_paper_intrahour_cycle(
    *, scenario: str = "two_targets_then_stop",
    side: str = "LONG",
) -> dict:
    """Run two deterministic scenarios; DB and network remain entirely local.

    `two_targets_then_stop`: at minute 12 reserve+explicitly fill 30,
    at minute 19 reserve+explicitly fill 20, then minute 27 reserve+fill
    the remaining 50. Fixture fills are separate data, not market touches.

    `unknown_blocks_stop`: reserve 30 at minute 12 then inject UNKNOWN;
    subsequent target and stop must abstain, keeping original capacity.
    """
    if scenario not in ("two_targets_then_stop", "unknown_blocks_stop"):
        raise DataValidationError("unknown D392 offline scenario")
    if side not in ("LONG", "SHORT"):
        raise DataValidationError("unknown D392 PAPER side")
    short = side == "SHORT"
    with TemporaryDirectory(prefix="cia-paper-d392-") as d:
        db = Path(d) / "paper_positions.sqlite"
        store = _new_position(db, short=short)
        router = _route(db, short=short)
        book = BybitPublicTickerBook(
            ranked_symbols=(SYMBOL,),
            universe_at_ms=HOUR_START_MS + 1 * MINUTE_MS,
        )
        # Acknowledged session is INJECTED: this is no network ACK.
        book.begin_acknowledged_session()
        steps: list[dict] = []
        first = _tick(
            book, minute=12, cs=1, kind="snapshot",
            mark="99.5" if short else "100.5",
            bid="98.98" if short else "101",
            ask="99" if short else "101.02",
        )
        first_decision = router.process(first)
        if (first_decision is None
                or first_decision.decision is not PaperIntrahourDecision.TARGET_RESERVED
                or first_decision.target is None
                or first_decision.target.tranche_step != 1):
            raise DataValidationError("D392 first partial did not reserve")
        steps.append(_snapshot_summary(store, minute=12, decision=first_decision.decision))
        if store.load(POSITION_ID).filled_exit_units != 0:
            raise DataValidationError("D392 reservation falsely generated a fill")

        if scenario == "unknown_blocks_stop":
            unknown_at = HOUR_START_MS + 12 * MINUTE_MS + 1
            store.append_exit_events(
                POSITION_ID, first_decision.created_intent_id,
                (PaperOrderEvent(
                    "fixture_d392_unknown_first", PaperOrderEventKind.UNKNOWN,
                    unknown_at,
                ),), as_of_ms=unknown_at,
            )
        else:
            _explicit_fill(
                store, minute=12, intent_id=first_decision.created_intent_id,
                event_id="fixture_d392_fill_first", units=Decimal(30),
            )
        # Checkpoint survived a new store instance, no shadow ledger.
        store = SQLitePaperPositionJournal(db)
        second = _tick(
            book, minute=19, cs=2, kind="delta",
            mark="97.5" if short else "102.5",
            bid="96.98" if short else "103",
            ask="97" if short else "103.02",
        )
        second_decision = router.process(second)
        expected_second = (
            PaperIntrahourDecision.TARGET_PENDING
            if scenario == "unknown_blocks_stop"
            else PaperIntrahourDecision.TARGET_RESERVED
        )
        if second_decision is None or second_decision.decision is not expected_second:
            raise DataValidationError("D392 second event violates pending/target contract")
        steps.append(_snapshot_summary(store, minute=19, decision=second_decision.decision))
        if scenario != "unknown_blocks_stop":
            if (second_decision.target is None
                    or second_decision.target.tranche_step != 2):
                raise DataValidationError("D392 second partial step incorrect")
            _explicit_fill(
                store, minute=19, intent_id=second_decision.created_intent_id,
                event_id="fixture_d392_fill_second", units=Decimal(20),
            )
            # Reconnect in the fixture: quotes and router cursors do not survive.
            book.mark_disconnected()
            book.begin_acknowledged_session()
            router = _route(db, short=short)
        third = _tick(
            book, minute=27,
            cs=1 if scenario == "two_targets_then_stop" else 3,
            kind="snapshot" if scenario == "two_targets_then_stop" else "delta",
            mark="103" if short else "98",
            bid="102.98" if short else "98",
            ask="103" if short else "98.02",
        )
        final_decision = router.process(third)
        expected_third = (
            PaperIntrahourDecision.STOP_UNRESOLVED
            if scenario == "unknown_blocks_stop"
            else PaperIntrahourDecision.STOP_RESERVED
        )
        if final_decision is None or final_decision.decision is not expected_third:
            raise DataValidationError("D392 protection/reconciliation contract violated")
        steps.append(_snapshot_summary(store, minute=27, decision=final_decision.decision))
        if scenario != "unknown_blocks_stop":
            if final_decision.stop.reserved_units != Decimal(50):
                raise DataValidationError("D392 stop must reserve only remaining 50 units")
            _explicit_fill(
                store, minute=27, intent_id=final_decision.created_intent_id,
                event_id="fixture_d392_fill_stop", units=Decimal(50),
            )
        last = SQLitePaperPositionJournal(db).load(POSITION_ID)
        if scenario == "unknown_blocks_stop":
            expected = (Decimal(0), Decimal(30), Decimal(100), 1)
        else:
            expected = (Decimal(100), Decimal(0), Decimal(0), 3)
        actual = (
            last.filled_exit_units, last.reserved_unfilled_units,
            last.confirmed_remaining_units, len(last.exit_orders),
        )
        if actual != expected:
            raise DataValidationError("D392 ledger final audit did not match scenario")
        if not last.protective_stop_seen and scenario != "unknown_blocks_stop":
            raise DataValidationError("D392 paper stop reservation absent")
        if last.runner_floor_units != Decimal(50):
            raise DataValidationError("D392 initial residual plan not preserved")
        result = {
            "schema_version": "cia-paper-intrahour-proof-d392-v1",
            "status": ("fixture_cycle_closed" if scenario == "two_targets_then_stop"
                       else "fixture_unknown_requires_reconciliation"),
            "scenario": scenario, "position_side": side,
            "market_source": "SYNTHETIC_BYBIT_TICKER_FIXTURES",
            "opening": "explicit_fixture_fill_at_minute_05",
            "timeline": steps,
            "same_hour": True,
            "candle_close_required_for_exit": False,
            "initial_confirmed_units": "100",
            "planned_residual_units": "50",
            "fixture_fill_event_count": 4 if scenario != "unknown_blocks_stop" else 1,
            "recorded_exit_intents": len(last.exit_orders),
            "final_filled_exit_units": str(last.filled_exit_units),
            "final_reserved_unfilled_units": str(last.reserved_unfilled_units),
            "final_remaining_units": str(last.confirmed_remaining_units),
            "reconciliation_required": scenario == "unknown_blocks_stop",
            "venue_account_connected": False,
            "native_stop_verified": False,
            "real_fills_verified": False,
            "net_pnl_verified": False,
            "fees_slippage_funding_liquidation_modeled": False,
            "entry_signal_computed": False,
            "leverage_at_open_verified": False,
            "marketwide_top50_verified": False,
            "order_submission_enabled": False,
            "orders_sent": False,
            "approved_for_live_use": False,
        }
        canonical = json.dumps(result, sort_keys=True, separators=(",", ":"))
        return {
            **result,
            "fixture_report_sha256": sha256(canonical.encode("ascii")).hexdigest(),
        }
