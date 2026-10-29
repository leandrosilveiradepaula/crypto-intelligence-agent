"""One-shot, owner-only Bybit V5 30-day local research with two optional hours.

No secrets, orders, POST, proxy, redistribution or automatic deployment. The
positive crypto registry currently has 13 bases: this is NOT verified Top50.
Only UTC-closed candles; caller must independently confirm lawful regional
access and scope of personal/private research before enabling network/storage.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import time
from typing import Callable

from crypto_intelligence_agent.bybit_local_json_audit import LocalBybitCaptureManifest
from crypto_intelligence_agent.bybit_paginated_universe_research import (
    MAX_PAGES, scan_bybit_linear_instruments_offline,
)
from crypto_intelligence_agent.bybit_pit_research import (
    HOUR_MS, select_bybit_reviewed_sample_pit,
)
from crypto_intelligence_agent.bybit_public_j1_transport import (
    BoundedBybitPublicClient, J1BybitCaptureError, instruments_url, kline_url,
)
from crypto_intelligence_agent.bybit_research_cycle import (
    BybitResearchRawPage, append_offline_bybit_hourly_update,
    stage_offline_bybit_research_cycle,
)
from crypto_intelligence_agent.bybit_research_storage import SQLiteBybitResearchStore
from crypto_intelligence_agent.market_data import DataGapError, DataValidationError
from crypto_intelligence_agent.private_kraken_research import (
    _create_private_file, _private_db_path,
)
from crypto_intelligence_agent.research_registry_catalog import load_reviewed_registry

REGISTRY = "expanded-13"
HISTORY_HOURS = 720
PAGE_HOURS = 72
CLOSE_SAFETY_MS = 2000


def _clock() -> int:
    return time.time_ns() // 1_000_000


def _observe(client, clock, max_assets):
    start = clock()
    decision = start // HOUR_MS * HOUR_MS
    if start - decision < CLOSE_SAFETY_MS:
        raise J1BybitCaptureError("closed_hour_safety_margin_required")
    pages, cursors = [], []
    cursor = None
    seen = set()
    for _ in range(MAX_PAGES):
        _, response = client.get(instruments_url(cursor=cursor))
        pages.append(response)
        cursors.append(cursor)
        result = response.get("result")
        if type(result) is not dict:
            raise J1BybitCaptureError("invalid_instrument_page")
        next_cursor = result.get("nextPageCursor")
        if next_cursor == "":
            break
        if (type(next_cursor) is not str or not next_cursor
                or next_cursor in seen or len(next_cursor) > 300):
            raise J1BybitCaptureError("unsafe_or_repeated_instrument_cursor")
        seen.add(next_cursor)
        cursor = next_cursor
    else:
        raise J1BybitCaptureError("instrument_pagination_exceeded_limit")
    at_scan = clock()
    try:
        scan = scan_bybit_linear_instruments_offline(
            instrument_pages=tuple(pages), requested_cursors=tuple(cursors),
            observed_at_ms=at_scan, registry_variant=REGISTRY,
        )
    except DataValidationError:
        raise J1BybitCaptureError("instrument_registry_or_pagination_rejected") from None
    eligible = tuple(x for x in scan.instruments
                     if x.launch_time_ms <= decision - 24 * HOUR_MS)
    if not eligible:
        raise J1BybitCaptureError("no_eligible_reviewed_crypto_assets")
    klines = {}
    for item in eligible:
        _, data = client.get(kline_url(
            item.symbol, decision - 24 * HOUR_MS, decision))
        klines[item.symbol] = data
    observed = clock()
    if observed // HOUR_MS * HOUR_MS != decision:
        raise J1BybitCaptureError("snapshot_crossed_hour_boundary")
    try:
        selection = select_bybit_reviewed_sample_pit(
            instrument_pages=tuple(pages), requested_cursors=tuple(cursors),
            kline_pages=klines, observed_at_ms=observed,
            decision_at_ms=decision, registry_variant=REGISTRY,
            max_candidates=max_assets,
        )
    except (DataValidationError, DataGapError):
        raise J1BybitCaptureError("pit_closed_24h_validation_rejected") from None
    return selection, scan.instrument_row_count


def _page(client, clock, symbol, first, hours):
    started = clock()
    meta_raw, _ = client.get(instruments_url(symbol=symbol))
    meta_at = clock()
    candle_raw, _ = client.get(
        kline_url(symbol, first, first + hours * HOUR_MS))
    chart_at = clock()
    try:
        manifest = LocalBybitCaptureManifest(
            symbol=symbol, interval="1h", registry_variant=REGISTRY,
            start_open_ms=first, end_open_ms=first + hours * HOUR_MS,
            capture_started_ms=started, instrument_received_ms=meta_at,
            kline_received_ms=chart_at, capture_finished_ms=chart_at,
        )
    except DataValidationError:
        raise J1BybitCaptureError("page_capture_timing_rejected") from None
    return BybitResearchRawPage(meta_raw, candle_raw, manifest)


def owner_private_j1_capture(
    *, database: str | Path, max_assets: int = 2,
    two_hourly_updates: bool = False,
    allow_public_network: bool = False,
    allow_private_storage: bool = False,
    confirm_region_and_personal_research: bool = False,
    client: BoundedBybitPublicClient | None = None,
    clock_ms: Callable[[], int] | None = None,
    sleep: Callable[[float], None] | None = None,
) -> dict:
    if (allow_public_network is not True or allow_private_storage is not True
            or confirm_region_and_personal_research is not True
            or type(max_assets) is not int or not 1 <= max_assets <= 13
            or type(two_hourly_updates) is not bool or os.name != "posix"):
        raise J1BybitCaptureError("owner_opt_in_or_posix_requirement_failed")
    target = _private_db_path(database)
    if target.exists():
        raise J1BybitCaptureError("existing_db_requires_explicit_readonly_review")
    clock = clock_ms or _clock
    sleeper = sleep or time.sleep
    fetch = client or BoundedBybitPublicClient()
    load_reviewed_registry(REGISTRY, as_of_ms=clock())
    original, instrument_rows = _observe(fetch, clock, max_assets)
    start = original.decision_at_ms - HISTORY_HOURS * HOUR_MS
    history = {
        member.symbol: tuple(
            _page(fetch, clock, member.symbol,
                  start + i * PAGE_HOURS * HOUR_MS, PAGE_HOURS)
            for i in range(HISTORY_HOURS // PAGE_HOURS)
        ) for member in original.ranked
    }
    # First ensure each required page passes the offline preflight; the
    # private DB is created only once all upstream GETs have completed.
    store = None
    created = False
    try:
        created = _create_private_file(target)
        store = SQLiteBybitResearchStore(target)
        initial = stage_offline_bybit_research_cycle(
            selection=original, history=history, store=store,
            required_hours=HISTORY_HOURS,
            capture_environment="private_local_unverified",
        )
        previous = original
        for _ in range(2 if two_hourly_updates else 0):
            next_hour = previous.decision_at_ms + HOUR_MS
            remaining_ms = next_hour + CLOSE_SAFETY_MS - clock()
            if remaining_ms > 0:
                sleeper(remaining_ms / 1000)
            if clock() // HOUR_MS * HOUR_MS != next_hour:
                raise J1BybitCaptureError("hourly_update_window_missed")
            updated, _ = _observe(fetch, clock, max_assets)
            if updated.decision_at_ms != next_hour:
                raise J1BybitCaptureError("nonconsecutive_hourly_snapshot")
            if {x.symbol for x in previous.ranked} != {
                    x.symbol for x in updated.ranked}:
                raise J1BybitCaptureError("sample_changed_requires_new_backfill")
            hourly_pages = {
                m.symbol: _page(fetch, clock, m.symbol,
                                previous.decision_at_ms, 1)
                for m in updated.ranked
            }
            append_offline_bybit_hourly_update(
                previous=previous, updated=updated,
                hourly_pages=hourly_pages, store=store,
                original_history_hours=HISTORY_HOURS,
                capture_environment="private_local_unverified",
            )
            previous = updated
        updates = (previous.decision_at_ms - original.decision_at_ms) // HOUR_MS
        for m in previous.ranked:
            report = store.quality_report(
                symbol=m.symbol, interval="1h",
                start_open_ms=start, end_open_ms=previous.decision_at_ms)
            if (not report.complete_for_offline_staging_only
                    or report.persisted_candles != HISTORY_HOURS + updates):
                raise J1BybitCaptureError("final_quality_gap_or_conflict")
        if (store.replay_pit_research_snapshot(original.observed_at_ms)
                != original or store.replay_pit_research_snapshot(
                    previous.observed_at_ms) != previous):
            raise J1BybitCaptureError("readonly_snapshot_replay_mismatch")
        return {
            "status": "private_reviewed_sample_complete_not_top50",
            "instrument_rows": instrument_rows,
            "reviewed_eligible_ranked_count": original.candidates_with_full_24h_count,
            "selected_assets": len(original.ranked),
            "closed_candles": initial.validated_closed_1h_rows
                + len(original.ranked) * updates,
            "historical_hours_per_asset": HISTORY_HOURS,
            "consecutive_hourly_updates": updates,
            "pit_snapshot_count": updates + 1,
            "first_pit_sha256": original.content_sha256,
            "last_pit_sha256": previous.content_sha256,
            "requests_attempted": fetch.requests_attempted,
            "private_sqlite_stored": True,
            "quality_and_readonly_replay": True,
            "marketwide_top50_verified": False,
            "canonical_data_authorized": False,
            "orders_sent": False,
        }
    except (DataValidationError, DataGapError):
        raise J1BybitCaptureError("private_research_integrity_or_gap_rejected") from None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True)
    parser.add_argument("--max-assets", type=int, default=2)
    parser.add_argument("--two-hourly-updates", action="store_true")
    parser.add_argument("--allow-public-network", action="store_true")
    parser.add_argument("--allow-private-storage", action="store_true")
    parser.add_argument("--confirm-region-and-personal-research", action="store_true")
    args = parser.parse_args()
    try:
        report = owner_private_j1_capture(
            database=args.database, max_assets=args.max_assets,
            two_hourly_updates=args.two_hourly_updates,
            allow_public_network=args.allow_public_network,
            allow_private_storage=args.allow_private_storage,
            confirm_region_and_personal_research=args.confirm_region_and_personal_research,
        )
    except Exception as exc:
        report = {
            "status": (str(exc) if type(exc) is J1BybitCaptureError
                       else "private_capture_failed_sanitized"),
            "partial_data_may_remain": True,
            "marketwide_top50_verified": False, "orders_sent": False,
        }
    print(json.dumps(report, separators=(",", ":"), sort_keys=True))
    return 0 if report["status"] == "private_reviewed_sample_complete_not_top50" else 1


if __name__ == "__main__":
    raise SystemExit(main())
