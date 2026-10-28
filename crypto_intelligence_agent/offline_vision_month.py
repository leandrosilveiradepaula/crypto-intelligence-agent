"""J1/HIST: bounded OFFLINE monthly USD-M kline archive research gate.

Inputs are caller-supplied ZIP bytes and an expected hash, NOT authenticated
Binance data. Never downloads, writes, promotes ClosedCandle, feeds a strategy,
authorizes datasets, or emits orders. Terms and regional access require a
separate affirmative human review before any real archive is acquired.
"""
from __future__ import annotations

import calendar
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
from io import BytesIO, StringIO
import re
from zipfile import BadZipFile, ZipFile

from .market_data import BinanceFuturesPublicAdapter, DataValidationError

_MAX_ZIP_BYTES = 8_000_000
_MAX_CSV_BYTES = 32_000_000
_MAX_RATIO = 100
_HOUR_MS = 3_600_000
_NAME = re.compile(r"(BTC|ETH|[A-Z0-9]{2,20})USDT-1h-(20[0-9]{2})-(0[1-9]|1[0-2])\.zip\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class OfflineVisionCandle:
    """Separate type: cannot be passed to canonical candle storage by accident."""

    open_time_ms: int
    close_time_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    documented_base_volume: Decimal
    documented_quote_volume: Decimal


@dataclass(frozen=True)
class OfflineVisionMonth:
    archive_name: str
    zip_sha256: str
    symbol: str
    interval: str
    first_open_ms: int
    end_open_exclusive_ms: int
    candles: tuple[OfflineVisionCandle, ...]

    @property
    def quality(self) -> str:
        return "unverified_offline_personal_research_only"

    @property
    def provider_authenticated(self) -> bool:
        return False

    @property
    def dataset_rights_authorized(self) -> bool:
        return False

    @property
    def canonical_ohlcv_approved(self) -> bool:
        return False

    @property
    def ready_for_trading(self) -> bool:
        return False

    @property
    def live_trading_authorized(self) -> bool:
        return False

    @property
    def orders_sent(self) -> bool:
        return False


def inspect_offline_vision_month(
    archive: bytes, *,
    archive_name: str,
    expected_sha256: str,
    as_of_ms: int,
    close_safety_ms: int = 1_000,
) -> OfflineVisionMonth:
    """Inspect exactly one complete closed calendar month, without I/O.

    expected_sha256 checks consistency with a value supplied by the caller,
    NOT an authenticated Binance .CHECKSUM. Never use this output as a
    production signal or assert licensing, exchange source, market status,
    contract rights or real fills.
    """
    if type(archive_name) is not str:
        raise DataValidationError("explicit fixed archive name required")
    match = _NAME.fullmatch(archive_name)
    if match is None:
        raise DataValidationError("expected USD-M USDT 1h monthly ZIP name")
    if (type(archive) is not bytes or not 1 <= len(archive) <= _MAX_ZIP_BYTES
            or type(expected_sha256) is not str
            or _HASH.fullmatch(expected_sha256) is None):
        raise DataValidationError("bounded ZIP bytes and lowercase SHA-256 required")
    if type(as_of_ms) is not int or type(close_safety_ms) is not int or close_safety_ms < 0:
        raise DataValidationError("explicit bounded UTC cutoff required")
    digest = sha256(archive).hexdigest()
    if digest != expected_sha256:
        raise DataValidationError("ZIP digest mismatch")
    year, month = int(match[2]), int(match[3])
    symbol = archive_name.split("-")[0]
    start = int(datetime(year, month, 1, tzinfo=timezone.utc).timestamp() * 1000)
    following_year, following_month = (year + 1, 1) if month == 12 else (year, month + 1)
    end = int(datetime(following_year, following_month, 1, tzinfo=timezone.utc).timestamp() * 1000)
    if not 0 < as_of_ms <= 253_402_300_799_999 or end + close_safety_ms > as_of_ms:
        raise DataValidationError("whole month must already be closed at cutoff")
    expected_rows = calendar.monthrange(year, month)[1] * 24
    csv_name = archive_name[:-4] + ".csv"
    try:
        with ZipFile(BytesIO(archive), "r") as zf:
            files = zf.infolist()
            if (len(files) != 1 or files[0].filename != csv_name
                    or files[0].is_dir() or files[0].flag_bits & 1
                    or files[0].file_size > _MAX_CSV_BYTES
                    or files[0].file_size == 0
                    or files[0].compress_size == 0
                    or files[0].file_size > files[0].compress_size * _MAX_RATIO):
                raise DataValidationError("ZIP must contain one bounded expected CSV")
            if files[0].compress_type not in (0, 8):
                raise DataValidationError("unsupported ZIP compression method")
            with zf.open(files[0], "r") as fd:
                data = fd.read(_MAX_CSV_BYTES + 1)
            if len(data) > _MAX_CSV_BYTES or len(data) != files[0].file_size:
                raise DataValidationError("CSV decompression exceeds declared bounds")
    except (BadZipFile, OSError, EOFError, RuntimeError, ValueError) as exc:
        raise DataValidationError("invalid bounded offline ZIP") from exc
    try:
        decoded = data.decode("ascii", errors="strict")
    except UnicodeError as exc:
        raise DataValidationError("CSV must be bounded ASCII decimal data") from exc
    rows = csv.reader(StringIO(decoded, newline=""), strict=True)
    out: list[OfflineVisionCandle] = []
    # Binance USD-M archives may have an exact 12-column CSV header.
    # Accept only this known schema at row zero; never skip arbitrary text.
    official_header = (
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_asset_volume", "number_of_trades",
        "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume", "ignore",
    )
    try:
        first_row = next(rows, None)
        if first_row is None:
            raise DataValidationError("empty historical CSV")
        if tuple(first_row) != official_header:
            from itertools import chain
            rows = chain((first_row,), rows)
        for index, row in enumerate(rows):
            if index >= expected_rows or len(row) != 12 or any(
                not cell.isascii() or not cell or len(cell) > 80 for cell in row
            ):
                raise DataValidationError("unexpected CSV kline shape or excess rows")
            # Reuse the existing canonical Binance OHLC arithmetic validator,
            # then copy ONLY fields into an explicitly unverified research type.
            parsed = BinanceFuturesPublicAdapter._parse_candle(symbol, "1h", row)
            required = start + index * _HOUR_MS
            if parsed.open_time_ms != required or parsed.close_time_ms != required + _HOUR_MS - 1:
                raise DataValidationError("historical month has a gap, duplicate or wrong timestamp")
            out.append(OfflineVisionCandle(
                parsed.open_time_ms, parsed.close_time_ms,
                parsed.open, parsed.high, parsed.low, parsed.close,
                parsed.base_volume, parsed.quote_volume,
            ))
    except (csv.Error, UnicodeError, OverflowError, ValueError) as exc:
        raise DataValidationError("invalid historical CSV content") from exc
    if len(out) != expected_rows or out[-1].close_time_ms != end - 1:
        raise DataValidationError("incomplete historical calendar month")
    return OfflineVisionMonth(
        archive_name, digest, symbol, "1h", start, end, tuple(out),
    )
