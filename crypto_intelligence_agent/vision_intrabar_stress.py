"""J3 conditional OHLC stress envelope; research only, never actual fills."""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal, localcontext, Context
from .market_data import DataValidationError
from .offline_vision_month import OfflineVisionCandle
from .synthetic_cost_scenarios import _rate
from .synthetic_margin_envelope import SyntheticMarginBasis

_CTX=Context(prec=512)
_BPS=Decimal(10000)

@dataclass(frozen=True)
class VisionStressAssumptions:
    margin: SyntheticMarginBasis
    stop_fraction: Decimal
    target_fraction: Decimal
    maintenance_bps: Decimal
    entry_fee_bps: Decimal
    exit_fee_bps: Decimal
    entry_slippage_bps: Decimal
    exit_slippage_bps: Decimal
    signed_funding_bps: Decimal

    def __post_init__(self):
        if type(self.margin) is not SyntheticMarginBasis:
            raise DataValidationError("typed synthetic margin basis required")
        for key in ("stop_fraction","target_fraction"):
            x=getattr(self,key)
            if type(x) is not Decimal or not x.is_finite() or not Decimal(0)<x<Decimal(1):
                raise DataValidationError("finite fractional stop/target required")
        for key in ("maintenance_bps","entry_fee_bps","exit_fee_bps",
                    "entry_slippage_bps","exit_slippage_bps"):
            _rate(getattr(self,key),key,signed=False)
        _rate(self.signed_funding_bps,"synthetic funding",signed=True)

@dataclass(frozen=True)
class VisionStressEnvelope:
    worst_net_quote: Decimal
    best_net_quote: Decimal
    worst_net_over_margin: Decimal
    best_net_over_margin: Decimal
    touched_stop: bool
    touched_target: bool
    touched_liquidation_proxy: bool
    intrabar_ambiguous: bool

    @property
    def financial_backtest_approved(self): return False
    @property
    def liquidation_formula_verified(self): return False
    @property
    def orders_sent(self): return False


def stress_vision_candle(candle: OfflineVisionCandle, *,
                         long: bool, assumptions: VisionStressAssumptions) -> VisionStressEnvelope:
    if type(candle) is not OfflineVisionCandle or type(long) is not bool or type(assumptions) is not VisionStressAssumptions:
        raise DataValidationError("typed offline stress inputs required")
    with localcontext(_CTX):
        e=candle.open
        if any(type(v) is not Decimal or not v.is_finite() or v<=0
               for v in (e,candle.high,candle.low,candle.close)):
            raise DataValidationError("positive finite OHLC required")
        if candle.high<max(e,candle.close) or candle.low>min(e,candle.close):
            raise DataValidationError("inconsistent OHLC")
        m=assumptions.margin
        n=m.entry_notional_quote
        q=n/e
        sign=Decimal(1) if long else Decimal(-1)
        stop=e*(1-sign*assumptions.stop_fraction)
        target=e*(1+sign*assumptions.target_fraction)
        # Conservative isolated-equity threshold approximation, not venue formula.
        entry_cost=n*(assumptions.entry_fee_bps+assumptions.entry_slippage_bps)/_BPS
        funding=n*assumptions.signed_funding_bps*sign/_BPS
        reserve=n*(assumptions.maintenance_bps+assumptions.exit_fee_bps+
                   assumptions.exit_slippage_bps)/_BPS
        liq=e+sign*(reserve+entry_cost+funding-m.requested_margin_quote)/q
        touched_stop=(candle.low<=stop if long else candle.high>=stop)
        touched_target=(candle.high>=target if long else candle.low<=target)
        # An isolated 1x LONG can have a zero/negative algebraic threshold:
        # there is then no positive price at which to assume liquidation.
        if (long and liq>=e) or (not long and liq<=e):
            raise DataValidationError("immediate liquidation proxy")
        touched_liq=(candle.low<=liq if long and liq>0 else
                     candle.high>=liq if not long else False)
        def net(exit_price):
            exit_n=q*exit_price
            costs=entry_cost+exit_n*(assumptions.exit_fee_bps+
                   assumptions.exit_slippage_bps)/_BPS+funding
            return sign*(exit_price-e)*q-costs
        # Gap-through stop/liquidation is evaluated at worse opening when applicable.
        downside = (liq if touched_liq else stop if touched_stop else candle.close)
        upside = (target if touched_target else stop if touched_stop else candle.close)
        worst=net(downside)
        best=net(upside)
        if best<worst: best=worst
        return VisionStressEnvelope(
            worst,best,worst/m.requested_margin_quote,best/m.requested_margin_quote,
            touched_stop,touched_target,touched_liq,
            sum((touched_stop,touched_target,touched_liq))>1,
        )
