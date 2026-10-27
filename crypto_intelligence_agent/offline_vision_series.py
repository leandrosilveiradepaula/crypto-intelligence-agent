"""J1/HIST #239: strict contiguous OFFLINE research-month stitching.

No data download, canonical feed, historical entitlement, signals, PnL or
orders. Every month must first pass inspect_offline_vision_month on ZIP bytes.
A dataclass constructed by callers is untrusted; digest alone proves nothing.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import re

from .market_data import DataValidationError
from .offline_vision_month import OfflineVisionCandle, OfflineVisionMonth

_MAX_MONTHS = 24
_MAX_BARS = 24 * 31 * 24
_HOUR_MS = 3_600_000
_NAME = re.compile(r"([A-Z0-9]{2,20}USDT)-1h-(20[0-9]{2})-(0[1-9]|1[0-2])\.zip\Z")
_HEX = re.compile("[0-9a-f]{64}\\Z")


@dataclass(frozen=True)
class OfflineVisionResearchSeries:
    symbol: str
    interval: str
    first_open_ms: int
    end_open_exclusive_ms: int
    month_names: tuple[str, ...]
    zip_sha256s: tuple[str, ...]
    series_manifest_sha256: str
    candles: tuple[OfflineVisionCandle, ...]

    @property
    def quality(self) -> str:
        return "unverified_offline_personal_nonproduction_research_only"

    @property
    def dataset_rights_authorized(self) -> bool:
        return False

    @property
    def provider_authenticated(self) -> bool:
        return False

    @property
    def historical_top50_verified(self) -> bool:
        return False

    @property
    def canonical_ohlcv_approved(self) -> bool:
        return False

    @property
    def financial_backtest_approved(self) -> bool:
        return False

    @property
    def live_trading_authorized(self) -> bool:
        return False

    @property
    def orders_sent(self) -> bool:
        return False


def assemble_offline_vision_months(
    months: tuple[OfflineVisionMonth, ...], *, as_of_ms: int,
    close_safety_ms: int = 1000,
) -> OfflineVisionResearchSeries:
    """Reject missing/reordered months and malformed synthetic research rows.

    No strategy calculation or persistence. The input may be caller-forged;
    therefore successful assembly never certifies a real provider archive.
    """
    if (type(months) is not tuple or not 2 <= len(months) <= _MAX_MONTHS
            or type(as_of_ms) is not int or not 0 < as_of_ms <= 253_402_300_799_999
            or type(close_safety_ms) is not int or not 0 <= close_safety_ms <= 86_400_000):
        raise DataValidationError("bounded explicit offline Vision months and cutoff required")
    out: list[OfflineVisionCandle] = []
    names: list[str] = []
    hashes: list[str] = []
    previous_end: int | None = None
    first_symbol: str | None = None
    for month in months:
        if type(month) is not OfflineVisionMonth or type(month.archive_name) is not str:
            raise DataValidationError("exact prevalidated research month type required")
        found = _NAME.fullmatch(month.archive_name)
        if found is None:
            raise DataValidationError("invalid Vision monthly research name")
        symbol, year, number = found[1], int(found[2]), int(found[3])
        start = int(datetime(year, number, 1, tzinfo=timezone.utc).timestamp() * 1000)
        next_year, next_month = (year + 1, 1) if number == 12 else (year, number + 1)
        end = int(datetime(next_year, next_month, 1, tzinfo=timezone.utc).timestamp() * 1000)
        if (month.symbol != symbol or month.interval != "1h"
                or month.first_open_ms != start or month.end_open_exclusive_ms != end
                or type(month.zip_sha256) is not str or _HEX.fullmatch(month.zip_sha256) is None
                or type(month.candles) is not tuple
                or len(month.candles) != calendar.monthrange(year, number)[1] * 24
                or (first_symbol is not None and symbol != first_symbol)
                or (previous_end is not None and start != previous_end)
                or end + close_safety_ms > as_of_ms):
            raise DataValidationError("Vision research month mismatch/gap/reorder/future")
        first_symbol = symbol
        previous_end = end
        for i, candle in enumerate(month.candles):
            expected = start + i * _HOUR_MS
            if (type(candle) is not OfflineVisionCandle
                    or type(candle.open_time_ms) is not int
                    or type(candle.close_time_ms) is not int
                    or candle.open_time_ms != expected
                    or candle.close_time_ms != expected + _HOUR_MS - 1):
                raise DataValidationError("Vision research candle timestamp/identity changed")
            prices = (candle.open, candle.high, candle.low, candle.close)
            volumes = (candle.documented_base_volume, candle.documented_quote_volume)
            if (any(type(v) is not Decimal or not v.is_finite() for v in prices + volumes)
                    or any(v <= 0 or len(v.as_tuple().digits) > 40 for v in prices)
                    or any(v < 0 or len(v.as_tuple().digits) > 40 for v in volumes)
                    or candle.high < max(prices)
                    or candle.low > min(prices)):
                raise DataValidationError("Vision research OHLC/volume malformed")
            out.append(candle)
            if len(out) > _MAX_BARS:
                raise DataValidationError("Vision research series resource bound")
        names.append(month.archive_name)
        hashes.append(month.zip_sha256)
    # Synthetic receipt over the exact asserted archive identities. This is
    # NOT an authenticated provider signature or file-content checksum.
    manifest = "\n".join(f"{n}:{h}" for n, h in zip(names, hashes)).encode("ascii")
    return OfflineVisionResearchSeries(
        symbol=first_symbol, interval="1h",
        first_open_ms=months[0].first_open_ms,
        end_open_exclusive_ms=months[-1].end_open_exclusive_ms,
        month_names=tuple(names), zip_sha256s=tuple(hashes),
        series_manifest_sha256=sha256(manifest).hexdigest(),
        candles=tuple(out),
    )
