"""J1 #253 — hourly observations from already validated public trade archives.

Research-only trade-derived OHLC. No canonical ClosedCandle, fill, funding,
contract-unit inference, positions, orders, disk writes or network access.
An hour with trades is NOT proof that every trade in that hour was captured.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, localcontext

from .bybit_archive_week import inspect_seven_daily_archives
from .bybit_public_trade_archive import inspect_trade_archive
from .market_data import DataValidationError

_HOUR_MS = 3_600_000
_HOUR_US = 3_600_000_000


@dataclass(frozen=True)
class TradeDerivedHour:
    open_time_ms: int
    open_price: Decimal | None
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal | None
    trade_count: int
    reported_size_total: Decimal
    reported_home_notional_total: Decimal
    reported_foreign_notional_total: Decimal
    open_boundary_ambiguous: bool
    close_boundary_ambiguous: bool


@dataclass(frozen=True)
class WeeklyTradeHourResearch:
    hours: tuple[TradeDerivedHour, ...]
    missing_hour_open_ms: tuple[int, ...]
    archive_manifest_sha256: str
    source_authenticated: bool = False
    rights_authorized: bool = False
    canonical_ohlcv_approved: bool = False
    historical_top50_approved: bool = False
    financial_backtest_approved: bool = False
    live_trading_authorized: bool = False
    orders_sent: bool = False

    @property
    def ambiguous_boundary_hours(self) -> int:
        return sum(
            h.open_boundary_ambiguous or h.close_boundary_ambiguous
            for h in self.hours
        )

    @property
    def unambiguous_boundary_hours(self) -> int:
        return len(self.hours) - self.ambiguous_boundary_hours


@dataclass
class _HourBuilder:
    count: int = 0
    min_us: int | None = None
    max_us: int | None = None
    min_boundary_price: Decimal | None = None
    max_boundary_price: Decimal | None = None
    min_ambiguous: bool = False
    max_ambiguous: bool = False
    low: Decimal | None = None
    high: Decimal | None = None
    size_total: Decimal = Decimal(0)
    home_total: Decimal = Decimal(0)
    foreign_total: Decimal = Decimal(0)

    def add(self, time_us: int, price: Decimal, size: Decimal,
            home: Decimal, foreign: Decimal) -> None:
        if self.count == 0:
            self.min_us = self.max_us = time_us
            self.min_boundary_price = self.max_boundary_price = price
            self.low = self.high = price
        else:
            self.low = min(self.low, price)
            self.high = max(self.high, price)
            if time_us < self.min_us:
                self.min_us, self.min_boundary_price = time_us, price
                self.min_ambiguous = False
            elif time_us == self.min_us and price != self.min_boundary_price:
                self.min_ambiguous = True
            if time_us > self.max_us:
                self.max_us, self.max_boundary_price = time_us, price
                self.max_ambiguous = False
            elif time_us == self.max_us and price != self.max_boundary_price:
                self.max_ambiguous = True
        # Raw decimal strings can have 20 integer and 18 fractional digits.
        # Explicit precision ensures a million additions never round silently.
        with localcontext() as ctx:
            ctx.prec = 96
            self.size_total += size
            self.home_total += home
            self.foreign_total += foreign
        self.count += 1

    def freeze(self, hour_ms: int) -> TradeDerivedHour:
        if self.count <= 0 or self.low is None or self.high is None:
            raise DataValidationError("empty reconstructed hour")
        return TradeDerivedHour(
            open_time_ms=hour_ms,
            open_price=None if self.min_ambiguous else self.min_boundary_price,
            high_price=self.high,
            low_price=self.low,
            close_price=None if self.max_ambiguous else self.max_boundary_price,
            trade_count=self.count,
            reported_size_total=self.size_total,
            reported_home_notional_total=self.home_total,
            reported_foreign_notional_total=self.foreign_total,
            open_boundary_ambiguous=self.min_ambiguous,
            close_boundary_ambiguous=self.max_ambiguous,
        )


def reconstruct_weekly_trade_hours(
    archives: tuple[tuple[str, bytes], ...],
) -> WeeklyTradeHourResearch:
    """Seven consecutive UTC archives; exact numeric research observations only.

    First run the pre-existing calendar and integrity validator, then reuse its
    validated-trade CSV parser with an in-memory callback. Never forward-fill.
    Boundary timestamps with different prices have no defensible OPEN/CLOSE.
    """
    week = inspect_seven_daily_archives(archives)
    first_name = archives[0][0]
    first_day = first_name[len("BTCUSDT"):-len(".csv.gz")]
    start_ms = int(
        datetime.fromisoformat(first_day).replace(tzinfo=timezone.utc).timestamp()
        * 1000
    )
    slots: dict[int, _HourBuilder] = {}

    def on_trade(time_us: int, price: Decimal, size: Decimal,
                 home: Decimal, foreign: Decimal) -> None:
        hour_ms = time_us // _HOUR_US * _HOUR_MS
        if hour_ms < start_ms or hour_ms >= start_ms + 168 * _HOUR_MS:
            raise DataValidationError("trade outside seven-day UTC window")
        slots.setdefault(hour_ms, _HourBuilder()).add(
            time_us, price, size, home, foreign,
        )

    for name, raw in archives:
        inspect_trade_archive(
            raw, archive_name=name, on_valid_trade=on_trade,
        )
    if len(slots) != week.observed_hour_total:
        raise DataValidationError("trade/hour coverage reconciliation failed")
    expected = tuple(start_ms + i * _HOUR_MS for i in range(168))
    missing = tuple(t for t in expected if t not in slots)
    observed = tuple(slots[t].freeze(t) for t in sorted(slots))
    if len(observed) + len(missing) != 168:
        raise DataValidationError("invalid weekly hour partition")
    return WeeklyTradeHourResearch(
        hours=observed,
        missing_hour_open_ms=missing,
        archive_manifest_sha256=week.manifest_sha256,
    )
