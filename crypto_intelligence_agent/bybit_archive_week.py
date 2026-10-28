"""J1 #250: seven-day private historical audit, research only, no persistence."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from hashlib import sha256
import json

from .bybit_public_trade_archive import inspect_trade_archive
from .market_data import DataValidationError

@dataclass(frozen=True)
class ArchiveWeekAudit:
    days: int
    trades: int
    observed_hour_total: int
    missing_hour_total: int
    partial_days: int
    first_timestamp_ms: int
    last_timestamp_ms: int
    manifest_sha256: str
    source_authenticated: bool = False
    rights_authorized: bool = False
    canonical_ohlcv_approved: bool = False
    historical_top50_approved: bool = False
    financial_backtest_approved: bool = False
    live_trading_authorized: bool = False
    orders_sent: bool = False


def inspect_seven_daily_archives(archives: tuple[tuple[str, bytes], ...]) -> ArchiveWeekAudit:
    """Accept EXACT seven contiguous UTC days. No synthetic gap filling."""
    if type(archives) is not tuple or len(archives) != 7:
        raise DataValidationError("exactly seven bounded archives required")
    summaries = []
    previous_day = None
    for name, raw in archives:
        if type(name) is not str or not name.startswith("BTCUSDT") or not name.endswith(".csv.gz"):
            raise DataValidationError("invalid historical archive name")
        try:
            day = date.fromisoformat(name[len("BTCUSDT"):-len(".csv.gz")])
        except ValueError:
            raise DataValidationError("invalid calendar date") from None
        if previous_day is not None and day != previous_day + timedelta(days=1):
            raise DataValidationError("daily archive chain has missing or repeated day")
        summaries.append(inspect_trade_archive(raw, archive_name=name))
        previous_day = day
    head = summaries[0]
    tail = summaries[-1]
    # Hash only strict metadata, NEVER raw bytes or market values.
    receipt = [(name, item.gzip_sha256, item.trades, item.observed_hour_count)
               for (name, _), item in zip(archives, summaries)]
    digest = sha256(json.dumps(receipt, separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()
    hours = sum(item.observed_hour_count for item in summaries)
    return ArchiveWeekAudit(
        days=7, trades=sum(item.trades for item in summaries),
        observed_hour_total=hours, missing_hour_total=168-hours,
        partial_days=sum(item.observed_hour_count != 24 for item in summaries),
        first_timestamp_ms=head.first_timestamp_ms,
        last_timestamp_ms=tail.last_timestamp_ms,
        manifest_sha256=digest,
    )
