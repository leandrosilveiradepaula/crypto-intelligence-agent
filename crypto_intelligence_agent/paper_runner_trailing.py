"""J4/RUNNER1: inspect a confirmed residual PAPER runner, no order sender.

A mark-only trailing threshold is descriptive: tick gaps do not establish
intrabar chronology, stops are not venue-native and no execution is assumed.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext
from enum import Enum
from hashlib import sha256
import json

from .market_data import DataValidationError
from .paper_position_reservations import PaperPositionBalance
from .paper_risk_gate import _quote
from .synthetic_manual_exit_replay import _EXACT_CONTEXT, _utc_ms
from .synthetic_position_state import SyntheticSide

_BPS = Decimal(10000)


@dataclass(frozen=True)
class PaperRunnerTrailPolicy:
    activation_bps: Decimal
    trail_distance_bps: Decimal
    max_tick_gap_ms: int
    max_last_tick_age_ms: int

    def __post_init__(self) -> None:
        _quote(self.activation_bps, "activation_bps", allow_zero=True)
        _quote(self.trail_distance_bps, "trail_distance_bps", allow_zero=False)
        if (self.activation_bps >= _BPS
                or self.trail_distance_bps >= _BPS):
            raise DataValidationError("runner activation/trail must be below 10000 bps")
        for field in ("max_tick_gap_ms", "max_last_tick_age_ms"):
            value = getattr(self, field)
            if type(value) is not int or not 1 <= value <= 86_400_000:
                raise DataValidationError("bounded positive tick staleness limits required")


@dataclass(frozen=True)
class PaperRunnerMark:
    symbol: str
    at_ms: int
    mark_price_quote: Decimal

    def __post_init__(self) -> None:
        if (type(self.symbol) is not str or
                not 4 <= len(self.symbol) <= 25 or
                not self.symbol.isascii() or
                not self.symbol.isupper() or
                not self.symbol.isalnum()):
            raise DataValidationError("bounded uppercase synthetic ticker required")
        _utc_ms(self.at_ms, "runner mark time")
        _quote(self.mark_price_quote, "synthetic mark", allow_zero=False)


class PaperRunnerTrailState(str, Enum):
    WAITING_FOR_CONFIRMED_RUNNER = "WAITING_FOR_CONFIRMED_RUNNER"
    NOT_ACTIVATED = "NOT_ACTIVATED"
    TRACKING = "TRACKING"
    TRIGGERED_HYPOTHETICAL_ONLY = "TRIGGERED_HYPOTHETICAL_ONLY"


@dataclass(frozen=True)
class PaperRunnerTrailReport:
    state: PaperRunnerTrailState
    observed_tick_count: int
    runner_units: Decimal
    activated: bool
    triggered_tick_number: int | None
    last_stop_mark_quote: Decimal | None
    digest_sha256: str

    def sanitized_report(self) -> dict[str, object]:
        return {
            "status": "paper_runner_trailing_research_only",
            "state": self.state.value,
            "observed_tick_count": self.observed_tick_count,
            "runner_units": str(self.runner_units),
            "activated": self.activated,
            "triggered_tick_number": self.triggered_tick_number,
            "digest_sha256": self.digest_sha256,
            "native_stop_verified": False,
            "financial_pnl_available": False,
            "orders_sent": False,
            "order_submission_enabled": False,
            "approved_for_live_use": False,
            "live_trading_authorized": False,
            "network_requests": 0,
        }


def inspect_paper_runner_trail(
    balance: PaperPositionBalance,
    marks: tuple[PaperRunnerMark, ...], *,
    policy: PaperRunnerTrailPolicy,
    as_of_ms: int,
) -> PaperRunnerTrailReport:
    if (type(balance) is not PaperPositionBalance or
            type(policy) is not PaperRunnerTrailPolicy or
            type(marks) is not tuple or not 1 <= len(marks) <= 256 or
            any(type(t) is not PaperRunnerMark for t in marks)):
        raise DataValidationError("typed bounded PAPER runner observations required")
    _utc_ms(as_of_ms, "runner audit cutoff")
    if (balance.orders_sent or balance.live_trading_authorized or
            balance.approved_for_live_use):
        raise DataValidationError("PAPER runner must not represent live execution")
    if (balance.as_of_ms > as_of_ms or
            not balance.as_of_ms <= marks[0].at_ms or
            marks[-1].at_ms > as_of_ms or
            as_of_ms - marks[-1].at_ms > policy.max_last_tick_age_ms or
            any(x.symbol != balance.symbol for x in marks)):
        raise DataValidationError("invalid runner observation provenance or cutoff")
    times = tuple(x.at_ms for x in marks)
    if any(y <= x or y-x > policy.max_tick_gap_ms for x, y in zip(times, times[1:])):
        raise DataValidationError("unordered/stale PAPER runner mark observations")

    with localcontext(_EXACT_CONTEXT):
        step = balance.synthetic_lot_step_units
        if (type(step) is not Decimal or not step.is_finite() or step <= 0 or
                balance.initial_confirmed_units <= 0 or
                balance.confirmed_remaining_units < 0 or
                balance.unreserved_units < 0 or
                balance.runner_floor_units < 0 or
                balance.filled_exit_units + balance.confirmed_remaining_units != balance.initial_confirmed_units or
                balance.unreserved_units + balance.reserved_unfilled_units != balance.confirmed_remaining_units or
                balance.confirmed_remaining_units % step != 0 or
                balance.runner_floor_units % step != 0 or
                type(balance.side) is not SyntheticSide):
            raise DataValidationError("inconsistent PAPER runner balance")
        if (balance.runner_floor_units == 0 or
                not balance.tranches or
                balance.confirmed_remaining_units != balance.runner_floor_units or
                balance.reserved_unfilled_units != 0 or
                any(t.filled_units != t.target_units or
                    t.reserved_unfilled_units != 0 or
                    t.unallocated_units != 0 for t in balance.tranches) or
                any(o.snapshot.requires_reconciliation for o in balance.exit_orders)):
            state = PaperRunnerTrailState.WAITING_FOR_CONFIRMED_RUNNER
            stop = None
            active = False
            triggered = None
        else:
            first = marks[0].mark_price_quote
            favorable = first
            stop = None
            active = False
            triggered = None
            for idx, mark in enumerate(marks, start=1):
                price = mark.mark_price_quote
                if active and (
                    (balance.side is SyntheticSide.LONG and price <= stop)
                    or (balance.side is SyntheticSide.SHORT and price >= stop)
                ):
                    triggered = idx
                    break
                if balance.side is SyntheticSide.LONG:
                    favorable = max(favorable, price)
                    activate = favorable >= first * (_BPS + policy.activation_bps) / _BPS
                    candidate = favorable * (_BPS - policy.trail_distance_bps) / _BPS
                    if activate:
                        stop = candidate if stop is None else max(stop, candidate)
                else:
                    favorable = min(favorable, price)
                    activate = favorable <= first * (_BPS - policy.activation_bps) / _BPS
                    candidate = favorable * (_BPS + policy.trail_distance_bps) / _BPS
                    if activate:
                        stop = candidate if stop is None else min(stop, candidate)
                if activate:
                    active = True
            state = (
                PaperRunnerTrailState.TRIGGERED_HYPOTHETICAL_ONLY if triggered
                else PaperRunnerTrailState.TRACKING if active
                else PaperRunnerTrailState.NOT_ACTIVATED
            )
        digest = sha256(json.dumps({
            "schema": "paper-runner-trailing-v1",
            "position_id": balance.position_id,
            "plan_version": balance.plan_version,
            "checkpoint": balance.as_of_ms,
            "side": balance.side.value,
            "runner": str(balance.runner_floor_units),
            "policy": [str(policy.activation_bps),str(policy.trail_distance_bps),
                       policy.max_tick_gap_ms,policy.max_last_tick_age_ms],
            "marks": [(t.at_ms,str(t.mark_price_quote)) for t in marks],
            "state": state.value,
            "stop": None if stop is None else str(stop),
            "trigger": triggered,
        },sort_keys=True,separators=(",",":")).encode("ascii")).hexdigest()
        return PaperRunnerTrailReport(
            state,len(marks),balance.runner_floor_units,
            active,triggered,stop,digest)
