"""J1/EXIT: offline-only orchestrator from PIT selection to 30d research SQLite.

All API-shaped raw bytes MUST already exist privately or be synthetic fixtures.
No HTTP, credentials, service scheduling, canonical schema, PnL or trading.
A failed batch may leave validated immutable pages for safe idempotent replay,
but NEVER reports a complete 30d outcome or writes a PIT coverage checkpoint.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .bybit_local_json_audit import (
    LocalBybitCaptureManifest, audit_local_bybit_json,
)
from .bybit_pit_research import (
    HOUR_MS, BybitPITResearchSelection,
)
from .bybit_research_storage import SQLiteBybitResearchStore
from .market_data import DataGapError, DataValidationError
from .research_registry_catalog import load_reviewed_registry


@dataclass(frozen=True)
class BybitResearchRawPage:
    instrument_raw: bytes
    kline_raw: bytes
    manifest: LocalBybitCaptureManifest


@dataclass(frozen=True)
class BybitResearchCycleResult:
    status: str
    observed_at_ms: int
    decision_at_ms: int
    fully_covered_sample_assets: int
    validated_closed_1h_rows: int
    historical_hours_per_asset: int
    immutable_pages_replayed: int
    pit_snapshot_sha256: str

    @property
    def observed_universe_is_marketwide_top50(self) -> bool:
        return False

    @property
    def provider_authenticated(self) -> bool:
        return False

    @property
    def rights_for_live_authorized(self) -> bool:
        return False

    @property
    def canonical_ohlcv_approved(self) -> bool:
        return False

    @property
    def orders_sent(self) -> bool:
        return False


def stage_offline_bybit_research_cycle(
    *, selection: BybitPITResearchSelection,
    history: Mapping[str, tuple[BybitResearchRawPage, ...]],
    store: SQLiteBybitResearchStore,
    required_hours: int = 720,
    capture_environment: str = "offline_fixture",
) -> BybitResearchCycleResult:
    """Strict preflight of all raw pages before any SQLite write.

    Each 1..72-bar page is separately verified by the existing WU39 research
    parser and then revalidated by SQLiteBybitResearchStore.commit_raw_pair.
    Multi-symbol atomicity is NOT claimed. Failed/retried batches are fail-closed
    and the store's immutable page replay handles idempotent safe restarts.
    """
    if (type(selection) is not BybitPITResearchSelection
            or type(store) is not SQLiteBybitResearchStore
            or type(history) is not dict
            or type(required_hours) is not int
            or capture_environment not in ("offline_fixture", "private_local_unverified")
            or not 3 <= required_hours <= 720
            or set(history) != {m.symbol for m in selection.ranked}):
        raise DataValidationError("complete research cycle sample and bounds required")
    first_open = selection.decision_at_ms - required_hours * HOUR_MS
    if first_open <= 0:
        raise DataValidationError("historical research interval before epoch")
    preflight: list[tuple[str, BybitResearchRawPage]] = []
    for member in selection.ranked:
        pages = history[member.symbol]
        if (type(pages) is not tuple
                or not 1 <= len(pages) <= 10
                or any(type(p) is not BybitResearchRawPage for p in pages)):
            raise DataValidationError("bounded immutable research history pages required")
        cursor = first_open
        for page in pages:
            manifest = page.manifest
            if (type(manifest) is not LocalBybitCaptureManifest
                    or manifest.symbol != member.symbol
                    or manifest.start_open_ms != cursor
                    or manifest.end_open_ms <= cursor
                    or manifest.end_open_ms > selection.decision_at_ms
                    or manifest.interval != "1h"
                    or not member.symbol.endswith("USDT")
                    or type(page.instrument_raw) is not bytes
                    or type(page.kline_raw) is not bytes):
                raise DataGapError("research history missing or out of order")
            reviewed = load_reviewed_registry(
                manifest.registry_variant,
                as_of_ms=manifest.instrument_received_ms,
            )
            if reviewed.sha256_digest != selection.registry_sha256:
                raise DataValidationError("historical capture used different crypto registry")
            inspected = audit_local_bybit_json(
                instrument_raw=page.instrument_raw,
                kline_raw=page.kline_raw,
                manifest=manifest,
            )
            if (inspected["status"] != "offline_schema_conformance_passed_origin_unverified"
                    or inspected["registry_sha256"] != selection.registry_sha256
                    or inspected["documented_quote_turnover_unit"] != "USDT"
                    or inspected["closed_candle_count"]
                       != (manifest.end_open_ms - cursor) // HOUR_MS):
                raise DataValidationError("invalid research page origin/schema claim")
            cursor = manifest.end_open_ms
            preflight.append((member.symbol, page))
        if cursor != selection.decision_at_ms:
            raise DataGapError("30-day research history incomplete")
    # No write can occur before all symbols have passed the preflight.
    for symbol, page in preflight:
        saved = store.commit_raw_pair(
            instrument_raw=page.instrument_raw,
            kline_raw=page.kline_raw,
            manifest=page.manifest,
            capture_environment=capture_environment,
        )
        if (saved.symbol != symbol or saved.quote_unit != "USDT"
                or saved.canonical_ohlcv_approved or saved.rights_authorized):
            raise DataValidationError("research storage replay contract rejected")

    for member in selection.ranked:
        report = store.quality_report(
            symbol=member.symbol, interval="1h",
            start_open_ms=first_open, end_open_ms=selection.decision_at_ms,
        )
        if (not report.complete_for_offline_staging_only
                or report.expected_candles != required_hours
                or report.persisted_candles != required_hours
                or report.missing_open_times_ms
                or report.rights_authorized
                or report.canonical_ohlcv_approved):
            raise DataGapError("stored research history fails independent quality audit")
    # Mark this PIT observation only AFTER all history is complete and rechecked.
    store.commit_pit_research_snapshot(selection)
    return BybitResearchCycleResult(
        "offline_reviewed_sample_30d_replayed_unverified",
        selection.observed_at_ms, selection.decision_at_ms,
        len(selection.ranked), len(selection.ranked) * required_hours,
        required_hours, len(preflight), selection.content_sha256,
    )

def append_offline_bybit_hourly_update(
    *, previous: BybitPITResearchSelection,
    updated: BybitPITResearchSelection,
    hourly_pages: Mapping[str, BybitResearchRawPage],
    store: SQLiteBybitResearchStore,
    original_history_hours: int = 720,
    capture_environment: str = "offline_fixture",
) -> BybitResearchCycleResult:
    """Append one fully closed candle per *unchanged* sample symbol, then PIT.

    Newly entered assets cannot borrow the last 30-day history from an
    unrelated symbol. If membership changes, a separate bounded full-history
    staging and audit is required before accepting an updated sample.
    """
    if (type(previous) is not BybitPITResearchSelection
            or type(updated) is not BybitPITResearchSelection
            or type(store) is not SQLiteBybitResearchStore
            or type(hourly_pages) is not dict
            or type(original_history_hours) is not int
            or not 3 <= original_history_hours <= 720
            or capture_environment not in ("offline_fixture", "private_local_unverified")
            or updated.decision_at_ms != previous.decision_at_ms + HOUR_MS
            or updated.observed_at_ms <= previous.observed_at_ms
            or updated.registry_sha256 != previous.registry_sha256
            or {x.symbol for x in previous.ranked}
               != {x.symbol for x in updated.ranked}
            or set(hourly_pages) != {x.symbol for x in updated.ranked}):
        raise DataValidationError("hourly PIT extension requires same crypto sample")
    preflight = []
    for member in updated.ranked:
        page = hourly_pages[member.symbol]
        if (type(page) is not BybitResearchRawPage
                or type(page.manifest) is not LocalBybitCaptureManifest
                or page.manifest.symbol != member.symbol
                or page.manifest.start_open_ms != previous.decision_at_ms
                or page.manifest.end_open_ms != updated.decision_at_ms):
            raise DataGapError("incremental research 1h must extend exact UTC cursor")
        registry = load_reviewed_registry(
            page.manifest.registry_variant,
            as_of_ms=page.manifest.instrument_received_ms,
        )
        if registry.sha256_digest != updated.registry_sha256:
            raise DataValidationError("hourly PIT crypto registry changed")
        report = audit_local_bybit_json(
            instrument_raw=page.instrument_raw,
            kline_raw=page.kline_raw,
            manifest=page.manifest,
        )
        if (report["closed_candle_count"] != 1
                or report["documented_quote_turnover_unit"] != "USDT"):
            raise DataValidationError("one closed quote USDT candle required")
        preflight.append(page)
    # Audit all input bytes before appending any research rows.
    for page in preflight:
        saved = store.commit_raw_pair(
            instrument_raw=page.instrument_raw,
            kline_raw=page.kline_raw,
            manifest=page.manifest,
            capture_environment=capture_environment,
        )
        if len(saved.candles) != 1 or saved.canonical_ohlcv_approved:
            raise DataValidationError("incremental research page invalid")
    start = previous.decision_at_ms - original_history_hours * HOUR_MS
    for member in updated.ranked:
        report = store.quality_report(
            symbol=member.symbol, interval="1h",
            start_open_ms=start, end_open_ms=updated.decision_at_ms,
        )
        if (not report.complete_for_offline_staging_only
                or report.persisted_candles != original_history_hours + 1
                or report.rights_authorized or report.canonical_ohlcv_approved):
            raise DataGapError("extended research series incomplete")
    store.commit_pit_research_snapshot(updated)
    return BybitResearchCycleResult(
        "offline_hourly_research_sample_extended_unverified",
        updated.observed_at_ms, updated.decision_at_ms,
        len(updated.ranked), len(updated.ranked) * (original_history_hours + 1),
        original_history_hours + 1, len(preflight), updated.content_sha256,
    )
