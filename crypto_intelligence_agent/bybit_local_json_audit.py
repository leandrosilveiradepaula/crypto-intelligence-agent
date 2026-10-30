"""J1/WU48: audit locally supplied Bybit V5 public response BYTES, offline.

The caller supplies two API-shaped JSON files and self-declared capture
timestamps. No authentication, network access, rights grant, canonical OHLCV
conversion, storage, trading or external data disclosure is performed here.
A matching hash proves only which UNVERIFIED bytes were examined.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Mapping

from .bybit_instrument_volume_contract import stage_bybit_documented_linear_pair
from .decimal_json import decode_public_market_json_exact
from .market_data import DataValidationError, interval_duration_ms

MAX_LOCAL_BODY = 131_072
MAX_CAPTURE_DURATION_MS = 30_000
MAX_WINDOW_CANDLES = 720
_MAX_TIMESTAMP = 253_402_300_799_999

MANIFEST_FIELDS = frozenset({
    "symbol", "interval", "registry_variant", "start_open_ms", "end_open_ms",
    "capture_started_ms", "instrument_received_ms", "kline_received_ms",
    "capture_finished_ms",
})


@dataclass(frozen=True)
class LocalBybitCaptureManifest:
    """Owner's time claim, not evidence of an actual server-side capture."""

    symbol: str
    interval: str
    registry_variant: str
    start_open_ms: int
    end_open_ms: int
    capture_started_ms: int
    instrument_received_ms: int
    kline_received_ms: int
    capture_finished_ms: int

    def __post_init__(self) -> None:
        if type(self.symbol) is not str or not self.symbol.isascii() or not (
            self.symbol.endswith("USDT") or self.symbol.endswith("USDC")
        ) or not 6 <= len(self.symbol) <= 30:
            raise DataValidationError("local Bybit manifest requires exact linear symbol")
        if self.interval != "1h":
            raise DataValidationError("local Bybit audit supports closed 1h klines only")
        if self.registry_variant not in ("btc-eth", "expanded-10", "expanded-13"):
            raise DataValidationError("unsupported positive local registry revision")
        for key in (
            "start_open_ms", "end_open_ms", "capture_started_ms",
            "instrument_received_ms", "kline_received_ms", "capture_finished_ms",
        ):
            val = getattr(self, key)
            if type(val) is not int or not 0 < val < _MAX_TIMESTAMP:
                raise DataValidationError("manifest timestamps must be positive integer UTC-ms")
        period = interval_duration_ms(self.interval)
        if (
            self.end_open_ms <= self.start_open_ms
            or (self.end_open_ms - self.start_open_ms) % period != 0
            or (self.end_open_ms - self.start_open_ms) // period not in (*range(1, 73), 720)
            or (self.start_open_ms % period) != 0
            or (self.end_open_ms % period) != 0
        ):
            raise DataValidationError("local Bybit window requires 1..72 or exactly 720 contiguous UTC hours")
        if not (
            self.capture_started_ms <= self.instrument_received_ms
            <= self.kline_received_ms <= self.capture_finished_ms
        ) or self.capture_finished_ms - self.capture_started_ms > MAX_CAPTURE_DURATION_MS:
            raise DataValidationError("local capture claim must fit a consecutive 30s session")

    @classmethod
    def from_json_bytes(cls, raw: bytes) -> LocalBybitCaptureManifest:
        parsed = decode_public_market_json_exact(raw, max_bytes=4_096)
        if set(parsed) != MANIFEST_FIELDS:
            raise DataValidationError("local Bybit manifest has missing or extra fields")
        return cls(**parsed)


def audit_local_bybit_json(
    *, instrument_raw: bytes,
    kline_raw: bytes,
    manifest: LocalBybitCaptureManifest,
) -> dict[str, Any]:
    """Check only an offline schema conformance claim; return metadata NOT data.

    Both inputs are kept in memory and hashed; nothing is sent to any API,
    written to storage or promoted to an authenticated provider observation.
    """
    if type(manifest) is not LocalBybitCaptureManifest:
        raise DataValidationError("strict self-declared local capture manifest required")
    if type(instrument_raw) is not bytes or type(kline_raw) is not bytes:
        raise DataValidationError("local provider responses must be raw bytes")
    instrument = decode_public_market_json_exact(instrument_raw, max_bytes=MAX_LOCAL_BODY)
    kline = decode_public_market_json_exact(kline_raw, max_bytes=MAX_LOCAL_BODY)
    result = stage_bybit_documented_linear_pair(
        instrument_payload=instrument, kline_payload=kline,
        symbol=manifest.symbol,
        instrument_observed_at_ms=manifest.instrument_received_ms,
        kline_observed_at_ms=manifest.kline_received_ms,
        interval=manifest.interval, start_open_ms=manifest.start_open_ms,
        end_open_ms=manifest.end_open_ms,
        registry_variant=manifest.registry_variant,
        max_contract_age_ms=MAX_CAPTURE_DURATION_MS,
        close_safety_ms=1_000,
    )
    if (len(result.page.candles)
            != (manifest.end_open_ms - manifest.start_open_ms) // 3_600_000):
        raise DataValidationError("local Bybit schema candidate has incomplete window")
    if (result.instrument.observed_at_ms != manifest.instrument_received_ms
            or result.page.observed_at_ms != manifest.kline_received_ms
            or result.canonical_ohlcv or result.live_provider_verified):
        raise DataValidationError("local Bybit result must remain research-only")
    return {
        "schema_version": "j1-bybit-private-local-audit-v1",
        "status": "offline_schema_conformance_passed_origin_unverified",
        "input_origin": "unverified_user_supplied_local_bytes",
        "symbol": result.instrument.symbol,
        "interval": result.page.interval,
        "closed_candle_count": len(result.page.candles),
        "claimed_instrument_received_at_ms": manifest.instrument_received_ms,
        "claimed_kline_received_at_ms": manifest.kline_received_ms,
        "instrument_bytes_sha256": sha256(instrument_raw).hexdigest(),
        "kline_bytes_sha256": sha256(kline_raw).hexdigest(),
        "registry_sha256": result.instrument.registry_sha256,
        "documented_base_volume_unit": result.base_volume_unit,
        "documented_quote_turnover_unit": result.quote_turnover_unit,
        "financial_quote_is_usd": False,
        "actual_provider_origin_authenticated": False,
        "actual_capture_timestamps_verified": False,
        "live_public_schema_observed": False,
        "canonical_ohlcv_approved": False,
        "historical_top50_approved": False,
        "public_or_commercial_rights_authorized": False,
        "real_financial_backtest_approved": False,
        "live_trading_authorized": False,
        "orders_sent": False,
        "network_requests": 0,
        "data_stored": False,
    }
