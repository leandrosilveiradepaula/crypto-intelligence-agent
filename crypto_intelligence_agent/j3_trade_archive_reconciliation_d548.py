"""Offline candidate reconciliation of a daily Bybit linear trade archive.

No downloader, canonical candle creation, database write, or market-data
approval. File order is not assumed to be trade order. Equal timestamps with
different boundary prices make open/close ambiguous.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal, localcontext
import re
from typing import Iterable

from .j3_long_history_d528 import EXCHANGE, MARKET, QUALITY, DAY
from .market_data import ClosedCandle, DataValidationError

STEP = 300_000
MAX_LINE = 4096
MAX_ROWS = 3_000_000
_FIELDS = ("timestamp", "symbol", "size", "price", "trdMatchID")
_SYMBOL = re.compile(r"[A-Z0-9]{1,28}USDT\Z")
_ID = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
_NUMBER = re.compile(r"[0-9]{1,18}(?:\.[0-9]{1,12})?\Z")
_METRICS = ("open", "high", "low", "close", "base_volume", "quote_volume")


def _number(raw: str) -> Decimal:
    if _NUMBER.fullmatch(raw) is None:
        raise DataValidationError("D548 unsupported decimal")
    value = Decimal(raw)
    if value <= 0:
        raise DataValidationError("D548 nonpositive trade")
    return value


def _record(line: str) -> list[str]:
    if type(line) is not str or not 1 <= len(line) <= MAX_LINE or "\x00" in line:
        raise DataValidationError("D548 invalid archive line")
    try:
        return next(csv.reader([line], strict=True))
    except (csv.Error, StopIteration):
        raise DataValidationError("D548 malformed CSV") from None


@dataclass
class _Bucket:
    first_ts: Decimal
    last_ts: Decimal
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    base_volume: Decimal
    quote_volume: Decimal
    open_ambiguous: bool = False
    close_ambiguous: bool = False

    @classmethod
    def first(cls, ts, price, size):
        return cls(ts, ts, price, price, price, price, size, price * size)

    def add(self, ts, price, size):
        if ts < self.first_ts:
            self.first_ts, self.open, self.open_ambiguous = ts, price, False
        elif ts == self.first_ts and price != self.open:
            self.open_ambiguous = True
        if ts > self.last_ts:
            self.last_ts, self.close, self.close_ambiguous = ts, price, False
        elif ts == self.last_ts and price != self.close:
            self.close_ambiguous = True
        self.high = max(self.high, price)
        self.low = min(self.low, price)
        self.base_volume += size
        self.quote_volume += price * size


def reconcile_daily_trades(
    lines: Iterable[str],
    reference: Iterable[ClosedCandle],
    *,
    symbol: str,
    day_start_ms: int,
    max_rows: int = MAX_ROWS,
) -> dict:
    """Compare one whole UTC day's candidate aggregates to existing REST bars.

    Supported candidate CSV: decimal seconds since epoch, exact linear size
    in base units and positive price, unique trade IDs. Other columns are not
    used. Decimal arithmetic preserves the product price * size, so any
    provider-specific turnover rounding is reported as a difference, never
    silently tolerated. A day with missing candles cannot pass.
    """
    if (
        type(symbol) is not str or _SYMBOL.fullmatch(symbol) is None
        or type(day_start_ms) is not int or not 0 < day_start_ms <= 4_000_000_000_000 - DAY
        or day_start_ms % DAY
        or type(max_rows) is not int or not 1 <= max_rows <= MAX_ROWS
    ):
        raise DataValidationError("D548 invalid comparison scope")
    end = day_start_ms + DAY
    refs = {}
    for bar in reference:
        if (
            not isinstance(bar, ClosedCandle)
            or (bar.exchange, bar.market, bar.symbol, bar.interval, bar.quality)
            != (EXCHANGE, MARKET, symbol, "5m", QUALITY)
            or type(bar.open_time_ms) is not int
            or not day_start_ms <= bar.open_time_ms < end
            or bar.open_time_ms % STEP
            or bar.close_time_ms != bar.open_time_ms + STEP - 1
            or bar.open_time_ms in refs
            or any(type(getattr(bar, f)) is not Decimal
                   or not getattr(bar, f).is_finite()
                   for f in _METRICS)
            or min(bar.open, bar.high, bar.low, bar.close) <= 0
            or bar.low > min(bar.open, bar.close)
            or bar.high < max(bar.open, bar.close)
            or min(bar.base_volume, bar.quote_volume) < 0
        ):
            raise DataValidationError("D548 invalid REST reference")
        refs[bar.open_time_ms] = bar
    it = iter(lines)
    header = _record(next(it, ""))
    if len(header) != len(set(header)) or not set(_FIELDS).issubset(header):
        raise DataValidationError("D548 unsupported archive schema")
    idx = {f: header.index(f) for f in _FIELDS}
    buckets: dict[int, _Bucket] = {}
    seen: set[str] = set()
    count = 0
    # Inputs have <=30 decimal digits each; sums of <=3M products require
    # at most 67 digits, hence precision 80 is sufficient without rounding.
    with localcontext() as ctx:
        ctx.prec = 80
        for line in it:
            count += 1
            if count > max_rows:
                raise DataValidationError("D548 archive row limit")
            row = _record(line)
            if len(row) != len(header) or row[idx["symbol"]] != symbol:
                raise DataValidationError("D548 inconsistent archive row")
            trade_id = row[idx["trdMatchID"]]
            if _ID.fullmatch(trade_id) is None or trade_id in seen:
                raise DataValidationError("D548 invalid or duplicate trade ID")
            seen.add(trade_id)
            ts = _number(row[idx["timestamp"]]) * 1000
            if not day_start_ms <= ts < end:
                raise DataValidationError("D548 trade outside UTC day")
            price = _number(row[idx["price"]])
            size = _number(row[idx["size"]])
            bucket = int(ts // STEP) * STEP
            if bucket in buckets:
                buckets[bucket].add(ts, price, size)
            else:
                buckets[bucket] = _Bucket.first(ts, price, size)
    shared = refs.keys() & buckets.keys()
    differences = dict.fromkeys(_METRICS, 0)
    ambiguous = 0
    matched = 0
    for t in shared:
        b, ref = buckets[t], refs[t]
        uncertain = b.open_ambiguous or b.close_ambiguous
        ambiguous += int(uncertain)
        same = not uncertain
        for field in _METRICS:
            if ((field == "open" and b.open_ambiguous)
                    or (field == "close" and b.close_ambiguous)):
                continue
            if getattr(b, field) != getattr(ref, field):
                differences[field] += 1
                same = False
        matched += int(same)
    expected = DAY // STEP
    exact = matched == expected and len(refs) == len(buckets) == expected
    return {
        "schema_version": "d548-daily-archive-reconciliation-v1",
        "status": "exact_day_match" if exact else "not_equivalent",
        "expected_bars": expected,
        "trade_rows": count,
        "archive_bars": len(buckets),
        "rest_bars": len(refs),
        "paired_bars": len(shared),
        "exact_paired_bars": matched,
        "archive_missing_bars": expected - len(buckets),
        "rest_missing_bars": expected - len(refs),
        "archive_only_bars": len(buckets.keys() - refs.keys()),
        "rest_only_bars": len(refs.keys() - buckets.keys()),
        "ambiguous_paired_bars": ambiguous,
        "field_mismatches": differences,
        "scope": "one_symbol_one_utc_day_candidate_trade_bars",
        "source_equivalence_approved": False,
        "mark_price_verified": False,
        "funding_verified": False,
        "public_gets": 0,
        "data_stored": False,
        "orders_sent": False,
        "profile_modified": False,
        "j1_touched": False,
    }
