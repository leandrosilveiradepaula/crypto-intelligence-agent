"""D538 mark-based isolated-collateral stress, not historical liquidation."""
from dataclasses import dataclass
from bisect import bisect_left
from decimal import Context, Decimal, ROUND_FLOOR, ROUND_CEILING, localcontext

from .j3_funding_replay_d537 import ObservedFundingHistory
from .market_data import DataValidationError
from .synthetic_intrabar_barriers import ResearchDirection
from .synthetic_margin_envelope import SyntheticMarginBasis

_CTX=Context(prec=128)
_D=Decimal
_ZERO=_D(0)
_ONE=_D(1)
_BPS=_D(10000)
_Q=_D("1e-18")


def parse_maintenance_grid(value):
    if (type(value) not in (tuple,list) or len(value)>3
            or any(type(x) is not int or not 1<=x<=1000 for x in value)
            or tuple(sorted(set(value)))!=tuple(value)):
        raise DataValidationError("D538 use 1..3 increasing maintenance stress bps (1..1000), or no stress")
    return tuple(value)


@dataclass(frozen=True)
class MaintenanceStressResult:
    checked_bars:int
    first_possible_breach_bar:int | None
    worst_buffer_quote:Decimal


def stress_paths(source,*,direction,entry_at,end_at,entry_price,margin,changes,
                 entry_cost_bps,close_reserve_bps,maintenance_grid):
    """Proportional initial collateral release, entry costs pro rata.

    No realized profit or funding credits added; all observed funding debits
    retained. Reserve eventual close costs at mark. Combine worst mark and
    possible positive quantities with all debits in each exposed bar.
    A nonpositive buffer is a possible stress breach, not a venue liquidation.
    Missing exposed mark or incomplete funding queries makes result unavailable.
    """
    grid=parse_maintenance_grid(maintenance_grid)
    if (not grid or type(source) is not ObservedFundingHistory
            or type(direction) is not ResearchDirection or type(margin) is not SyntheticMarginBasis
            or any(type(x) is not Decimal or not x.is_finite() or not 0<=x<=1000
                   for x in (entry_cost_bps,close_reserve_bps))):
        raise DataValidationError("D538 explicit research assumptions required")
    if source.cost_bounds(direction=direction,entry_at=entry_at,end_at=end_at,
            entry_price=entry_price,notional=margin.entry_notional_quote,changes=changes) is None:
        return None
    if any(c.minimum_positive is None for c in changes):
        raise DataValidationError("D538 trace must preserve intrabar positive exposure")
    sign=_ONE if direction is ResearchDirection.LONG else -_ONE
    dt=source.duration
    cursor=0
    event=bisect_left(source.times,entry_at)
    remaining=_ONE
    debit=_ZERO
    checked=0
    worst={x:None for x in grid}
    first={x:None for x in grid}
    with localcontext(_CTX):
        for index,t in enumerate(range(entry_at,end_at,dt)):
            if not remaining:
                break
            mark=source.marks.get(t)
            if mark is None:
                return None
            lo,hi=mark
            change=changes[cursor] if cursor<len(changes) and changes[cursor].bar_index==index else None
            qmin=change.minimum_positive if change is not None else remaining
            while event<len(source.rates) and source.rates[event][0]<t+dt:
                _,rate=source.rates[event]
                if sign*rate>0:
                    debit+=(sign*rate*remaining*margin.entry_notional_quote*hi/entry_price).quantize(
                        _Q,rounding=ROUND_CEILING)
                event+=1
            # Worst mark follows the signed monotone slope; maintenance plus
            # reserve is bounded to 20% of mark notional.
            mark_price=lo if direction is ResearchDirection.LONG else hi
            marked_notional=margin.entry_notional_quote*mark_price/entry_price
            per_fraction_equity=(margin.requested_margin_quote
                +sign*(marked_notional-margin.entry_notional_quote)
                -margin.entry_notional_quote*entry_cost_bps/_BPS)
            for bps in grid:
                base=per_fraction_equity-marked_notional*(_D(bps)+close_reserve_bps)/_BPS
                buffer=(min(qmin*base,remaining*base)-debit).quantize(_Q,rounding=ROUND_FLOOR)
                worst[bps]=buffer if worst[bps] is None else min(worst[bps],buffer)
                if buffer<=0 and first[bps] is None:
                    first[bps]=index
            checked+=1
            if change is not None:
                remaining=change.after
                cursor+=1
    if not checked:
        raise DataValidationError("D538 empty exposed path")
    return {bps:MaintenanceStressResult(checked,first[bps],worst[bps]) for bps in grid}
