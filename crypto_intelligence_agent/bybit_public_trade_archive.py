"""J1 #247: strictly bounded OFFLINE Bybit public-trades gzip inspection.

This is an unverified research sample, not a canonical feed or rights grant.
No network, persistence, orders, account access or trading decisions.
"""
from __future__ import annotations
import csv
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import gzip
from hashlib import sha256
from io import BytesIO, TextIOWrapper
import re

from .market_data import DataValidationError, DataGapError

MAX_GZIP_BYTES = 5_000_000
MAX_CSV_BYTES = 30_000_000
MAX_TRADES = 150_000
DATE = re.compile(r"BTCUSDT(20[0-9]{2})-(0[1-9]|1[0-2])-([0-3][0-9])\.csv\.gz\Z")
NUMBER = re.compile(r"(?:0|[1-9][0-9]{0,19})(?:\.[0-9]{1,18})?\Z")
FIELDS = ("timestamp", "symbol", "side", "size", "price", "tickDirection",
          "trdMatchID", "grossValue", "homeNotional", "foreignNotional")


@dataclass(frozen=True)
class TradeArchiveAudit:
    trades: int
    first_timestamp_ms: int
    last_timestamp_ms: int
    observed_hour_count: int
    gzip_sha256: str
    quality: str = "unverified_offline_bybit_public_trades_research"
    source_authenticated: bool = False
    dataset_rights_authorized_for_production: bool = False
    canonical_ohlcv_approved: bool = False
    historical_top50_approved: bool = False
    real_financial_backtest_approved: bool = False
    live_trading_authorized: bool = False
    orders_sent: bool = False


def inspect_trade_archive(blob: bytes, *, archive_name: str) -> TradeArchiveAudit:
    if type(blob) is not bytes or not 1 <= len(blob) <= MAX_GZIP_BYTES:
        raise DataValidationError("bounded gzip bytes required")
    match = DATE.fullmatch(archive_name) if type(archive_name) is str else None
    if not match:
        raise DataValidationError("exact BTCUSDT daily archive name required")
    try:
        day = datetime(int(match[1]), int(match[2]), int(match[3]), tzinfo=timezone.utc)
    except ValueError:
        raise DataValidationError("invalid UTC archive date") from None
    first_bound = int(day.timestamp() * 1000)
    last_bound = first_bound + 86_400_000
    try:
        with gzip.GzipFile(fileobj=BytesIO(blob), mode="rb") as zipped:
            raw = zipped.read(MAX_CSV_BYTES + 1)
        if not 1 <= len(raw) <= MAX_CSV_BYTES:
            raise DataValidationError("decompressed archive exceeds budget")
        data = raw.decode("utf-8", "strict")
        reader = csv.DictReader(data.splitlines(), strict=True)
        if tuple(reader.fieldnames or ()) != FIELDS:
            raise DataValidationError("unknown exact Bybit trading CSV header")
        count, first, previous, hours = 0, None, None, set()
        for row in reader:
            if None in row or any(row.get(key) is None for key in FIELDS):
                raise DataValidationError("CSV column count mismatch")
            count += 1
            if count > MAX_TRADES:
                raise DataValidationError("trade budget exceeded")
            ts = row["timestamp"]
            if not re.fullmatch(r"[0-9]{10}(?:\.[0-9]{1,6})?", ts):
                raise DataValidationError("invalid timestamp precision")
            milliseconds = int(Decimal(ts) * 1000)
            if milliseconds < first_bound or milliseconds >= last_bound:
                raise DataValidationError("trade falls outside declared UTC day")
            if previous is not None and milliseconds < previous:
                raise DataGapError("trade timestamps out of order")
            if row["symbol"] != "BTCUSDT" or row["side"] not in ("Buy", "Sell"):
                raise DataValidationError("invalid contract identity or side")
            for key in ("size", "price", "homeNotional", "foreignNotional", "grossValue"):
                value = row[key]
                if NUMBER.fullmatch(value) is None or Decimal(value) <= 0:
                    raise DataValidationError("invalid exact trade decimal")
            if not row["trdMatchID"] or len(row["trdMatchID"]) > 128:
                raise DataValidationError("invalid bounded trade id")
            first = milliseconds if first is None else first
            previous = milliseconds
            hours.add((milliseconds - first_bound) // 3_600_000)
        if count == 0:
            raise DataValidationError("empty archive")
        return TradeArchiveAudit(count, first, previous, len(hours), sha256(blob).hexdigest())
    except (OSError, EOFError, UnicodeError, csv.Error, ValueError) as error:
        if isinstance(error, (DataValidationError, DataGapError)):
            raise
        raise DataValidationError("invalid Bybit trading gzip or CSV") from None
