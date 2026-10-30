"""Offline fixture funding settlement coverage, never provider authorization.

A supplied calendar contains timestamps only; rates and notionals MUST come
from separate SyntheticFundingEvent fixtures. No missing rate is treated as 0.
"""
from __future__ import annotations
from dataclasses import dataclass
import re

from .market_data import DataValidationError
from .synthetic_cost_scenarios import SyntheticFundingEvent, _time

_FIXTURE = re.compile(r"fixture_[A-Za-z0-9_-]{1,48}\Z")
_MAX_SLOTS = 64


@dataclass(frozen=True)
class SyntheticFundingCalendar:
    instrument_id: str
    calendar_version: str
    anchor_at_ms: int
    interval_ms: int

    def __post_init__(self) -> None:
        if (type(self.instrument_id) is not str
                or _FIXTURE.fullmatch(self.instrument_id) is None
                or type(self.calendar_version) is not str
                or _FIXTURE.fullmatch(self.calendar_version) is None):
            raise DataValidationError("fixture-only instrument and funding calendar version")
        _time(self.anchor_at_ms, "funding anchor")
        if (type(self.interval_ms) is not int
                or not 60_000 <= self.interval_ms <= 86_400_000
                or self.interval_ms % 60_000 != 0):
            raise DataValidationError("explicit minute-aligned synthetic funding cadence")


def validate_synthetic_funding_coverage(
    calendar: SyntheticFundingCalendar, *,
    instrument_id: str,
    entry_at_ms: int,
    last_tick_at_ms: int,
    tick_times: tuple[int, ...],
    funding_events: tuple[SyntheticFundingEvent, ...],
) -> tuple[int, ...]:
    """Require one explicit event per expected funding timestamp, no extras.

    Does not infer settlement, notional, rate, or whether a real venue paid.
    Tick/event simultaneity cannot be ordered from these fixtures, so abort.
    """
    if (type(calendar) is not SyntheticFundingCalendar
            or calendar.instrument_id != instrument_id
            or type(tick_times) is not tuple
            or type(funding_events) is not tuple
            or any(type(e) is not SyntheticFundingEvent for e in funding_events)):
        raise DataValidationError("typed synthetic calendar/event identity required")
    _time(entry_at_ms, "entry")
    _time(last_tick_at_ms, "last tick")
    if (last_tick_at_ms <= entry_at_ms
            or calendar.anchor_at_ms > entry_at_ms + calendar.interval_ms):
        raise DataValidationError("funding calendar does not cover open interval")
    # Calendar is an observed fixture. Do not invent rates for gaps.
    step = max(0, (entry_at_ms - calendar.anchor_at_ms) // calendar.interval_ms + 1)
    first = calendar.anchor_at_ms + step * calendar.interval_ms
    if first == last_tick_at_ms:
        raise DataValidationError("funding at final tick has ambiguous ordering")
    count = (last_tick_at_ms - 1 - first) // calendar.interval_ms + 1 if first < last_tick_at_ms else 0
    if count > _MAX_SLOTS:
        raise DataValidationError("funding interval exceeds 64 fixture settlements")
    expected = tuple(first + i * calendar.interval_ms for i in range(count))
    if (set(expected).intersection(tick_times)
            or tuple(e.event_at_ms for e in funding_events) != expected):
        raise DataValidationError("funding settlement is missing, extra, or same-time as tick")
    return expected
