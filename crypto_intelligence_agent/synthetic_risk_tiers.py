"""Synthetic PIT maintenance tiers for tick-replay research, never venue rules.

All values are explicit fixtures. A valid schedule cannot certify Bybit/other
exchange risk limits, fill prices, liquidation thresholds, or live access.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Context, Decimal, localcontext
import re

from .market_data import DataValidationError
from .synthetic_cost_scenarios import _amount, _rate, _time

_CTX = Context(prec=512)
_FIXTURE = re.compile(r"fixture_[A-Za-z0-9_-]{1,48}\Z")


@dataclass(frozen=True)
class SyntheticMaintenanceTier:
    lower_notional_quote: Decimal
    upper_notional_quote: Decimal | None
    maintenance_bps: Decimal
    maintenance_deduction_quote: Decimal

    def __post_init__(self) -> None:
        if type(self.lower_notional_quote) is not Decimal:
            raise DataValidationError("tier lower must be Decimal")
        if self.lower_notional_quote == 0:
            pass
        else:
            _amount(self.lower_notional_quote, "tier lower")
        if self.upper_notional_quote is not None:
            _amount(self.upper_notional_quote, "tier upper")
            if self.upper_notional_quote <= self.lower_notional_quote:
                raise DataValidationError("tier upper must exceed lower")
        _rate(self.maintenance_bps, "maintenance bps", signed=False)
        if type(self.maintenance_deduction_quote) is not Decimal:
            raise DataValidationError("deduction requires Decimal")
        if self.maintenance_deduction_quote == 0:
            pass
        else:
            _amount(self.maintenance_deduction_quote, "deduction")


@dataclass(frozen=True)
class SyntheticRiskSnapshot:
    instrument_id: str
    source_version: str
    observed_at_ms: int
    effective_at_ms: int
    tiers: tuple[SyntheticMaintenanceTier, ...]

    def __post_init__(self) -> None:
        if (type(self.instrument_id) is not str or
                _FIXTURE.fullmatch(self.instrument_id) is None or
                type(self.source_version) is not str or
                _FIXTURE.fullmatch(self.source_version) is None):
            raise DataValidationError("synthetic PIT identity/version required")
        _time(self.observed_at_ms, "snapshot observed")
        _time(self.effective_at_ms, "snapshot effective")
        if self.observed_at_ms > self.effective_at_ms:
            raise DataValidationError("future-known risk snapshot")
        if (type(self.tiers) is not tuple or not 1 <= len(self.tiers) <= 16
                or any(type(x) is not SyntheticMaintenanceTier for x in self.tiers)):
            raise DataValidationError("bounded typed risk tiers required")
        first = self.tiers[0]
        if first.lower_notional_quote != 0 or first.maintenance_deduction_quote != 0:
            raise DataValidationError("initial bracket starts at zero with zero deduction")
        with localcontext(_CTX):
            for prev, cur in zip(self.tiers, self.tiers[1:]):
                if (prev.upper_notional_quote is None or
                        prev.upper_notional_quote != cur.lower_notional_quote or
                        cur.maintenance_bps < prev.maintenance_bps):
                    raise DataValidationError("maintenance tiers must be contiguous and monotone")
                expected = (prev.maintenance_deduction_quote +
                    cur.lower_notional_quote *
                    (cur.maintenance_bps - prev.maintenance_bps) / Decimal(10000))
                if cur.maintenance_deduction_quote != expected:
                    raise DataValidationError("maintenance deduction must preserve boundary continuity")
        if self.tiers[-1].upper_notional_quote is not None:
            raise DataValidationError("last maintenance tier must be unbounded")


def validate_synthetic_risk_snapshots(
    snapshots: tuple[SyntheticRiskSnapshot, ...], *,
    instrument_id: str, entry_at_ms: int, as_of_ms: int,
) -> None:
    if (type(snapshots) is not tuple or not 1 <= len(snapshots) <= 16
            or any(type(x) is not SyntheticRiskSnapshot for x in snapshots)):
        raise DataValidationError("risk snapshots must be bounded immutable fixtures")
    times = [s.effective_at_ms for s in snapshots]
    if (times != sorted(set(times)) or times[0] > entry_at_ms
            or times[-1] > as_of_ms
            or len({s.source_version for s in snapshots}) != len(snapshots)
            or any(s.instrument_id != instrument_id for s in snapshots)
            or any(s.observed_at_ms > s.effective_at_ms for s in snapshots)):
        raise DataValidationError("wrong identity, duplicate or future PIT snapshot")
    # Later snapshots may not retroactively rewrite a position's opening state.
    if any(s.effective_at_ms <= entry_at_ms for s in snapshots[1:]):
        raise DataValidationError("duplicate pre-entry effective risk schedule")


def maintenance_for_mark(
    snapshot: SyntheticRiskSnapshot, *,
    mark_notional_quote: Decimal, close_reserve_quote: Decimal,
) -> Decimal:
    _amount(mark_notional_quote, "mark notional")
    if type(close_reserve_quote) is not Decimal or not close_reserve_quote.is_finite() or close_reserve_quote < 0:
        raise DataValidationError("invalid synthetic close reserve")
    with localcontext(_CTX):
        for tier in snapshot.tiers:
            if (mark_notional_quote >= tier.lower_notional_quote and
                (tier.upper_notional_quote is None or mark_notional_quote < tier.upper_notional_quote)):
                return (mark_notional_quote * tier.maintenance_bps / Decimal(10000)
                        - tier.maintenance_deduction_quote + close_reserve_quote)
    raise DataValidationError("mark notional has no maintenance tier")
