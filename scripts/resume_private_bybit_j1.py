"""J1 #310 — resume PRIVATE Bybit SQLite without discarding 30-day history.

Owner-only, opt-in, GET-only research. Replays immutable data with no
historical PIT invention. Only new point-in-time observations receive
snapshots; intervening missing CLOSED hours are data catch-up, NOT past PITs.

Never exposes symbols, prices, URLs, API bodies or filesystem paths in stdout.
No live feed rights, production migrations, order endpoints or credentials.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import time
from typing import Callable

from crypto_intelligence_agent.bybit_local_json_audit import audit_local_bybit_json
from crypto_intelligence_agent.bybit_public_j1_transport import (
    BoundedBybitPublicClient, J1BybitCaptureError,
)
from crypto_intelligence_agent.bybit_research_cycle import BybitResearchRawPage
from crypto_intelligence_agent.bybit_research_storage import SQLiteBybitResearchStore
from crypto_intelligence_agent.market_data import DataGapError, DataValidationError
from crypto_intelligence_agent.private_kraken_research import _private_db_path
from crypto_intelligence_agent.research_registry_catalog import load_reviewed_registry
from scripts.audit_private_bybit_j1_progress import (
    audit_private_bybit_j1_progress,
)
from scripts.capture_private_bybit_j1 import (
    CLOSE_SAFETY_MS, HISTORY_HOURS, REGISTRY, _clock, _observe, _page,
    HOUR_MS,
)

# Hard cap on closed-hour catch-up. Beyond this boundary, require a
# separate reviewed recovery plan, never expand network work silently.
MAX_CATCHUP_HOURS = 144
# J1 acceptance requires two distinct post-initial PIT hourly observations.
# A missed historical PIT is NEVER synthesized and the report discloses gaps.
REQUIRED_DISTINCT_UPDATES = 2


def _status_event(progress: Callable[[dict], None] | None, *,
                  phase: str, completed: int, network_gets: int) -> None:
    if progress is not None:
        progress({
            "event": "private_j1_resume_progress",
            "phase": phase, "distinct_pit_updates_after_initial": completed,
            "network_gets_attempted": network_gets,
            "marketwide_top50_verified": False, "orders_sent": False,
        })


def _private_state(target: Path):
    audit = audit_private_bybit_j1_progress(
        database=target, allow_private_readonly_audit=True,
    )
    if (audit["status"] != "private_bybit_progress_readonly_verified"
            or audit["sample_asset_count"] < 1
            or not audit["first_pit_720h_coverage"]
            or audit["immutable_pit_snapshots"] < 1):
        raise J1BybitCaptureError("existing_private_history_audit_required")
    # The read-only audit has already checked all page digests, PIT digests,
    # SQLite integrity, ownership and access modes. This second read only
    # obtains the private cursor and PIT key, never prints identifiers.
    with closing(sqlite3.connect(
        target.resolve(strict=True).as_uri() + "?mode=ro&immutable=1",
        uri=True, timeout=0,
    )) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        snapshots = db.execute(
            "SELECT observed_at_ms,decision_at_ms "
            "FROM bybit_research_pit_snapshots "
            "ORDER BY observed_at_ms DESC LIMIT 1",
        ).fetchall()
        ends = db.execute(
            "SELECT symbol,MIN(start_open_ms) AS earliest,"
            "MAX(end_open_ms) AS latest "
            "FROM bybit_research_pages GROUP BY symbol",
        ).fetchall()
    if len(snapshots) != 1 or len(ends) != audit["sample_asset_count"]:
        raise J1BybitCaptureError("unrecognized_private_resume_cursor")
    # SQLiteBybitResearchStore initializes existing metadata transactionally;
    # unlike capture_private_bybit_j1, it MUST NOT create a new research DB.
    if not target.is_file():
        raise J1BybitCaptureError("existing_private_database_required")
    store = SQLiteBybitResearchStore(target)
    previous = store.replay_pit_research_snapshot(snapshots[0]["observed_at_ms"])
    cursors = {row["symbol"]: row["latest"] for row in ends}
    initial = {row["symbol"]: row["earliest"] for row in ends}
    members = {m.symbol for m in previous.ranked}
    first = audit["first_pit_decision_ms"] - HISTORY_HOURS * HOUR_MS
    if (members != set(cursors)
            or any(start != first for start in initial.values())
            or any(cursor < previous.decision_at_ms
                   or cursor % HOUR_MS for cursor in cursors.values())
            or len(members) > 13):
        raise J1BybitCaptureError("private_research_cursor_or_scope_mismatch")
    return store, previous, cursors, audit, first


def _catchup_pages(
    client: BoundedBybitPublicClient, clock: Callable[[], int], *,
    previous, updated, cursors: dict[str, int], start: int,
    store: SQLiteBybitResearchStore,
) -> int:
    if {m.symbol for m in previous.ranked} != {m.symbol for m in updated.ranked}:
        raise J1BybitCaptureError("reviewed_sample_changed_requires_new_backfill")
    if previous.registry_sha256 != updated.registry_sha256:
        raise J1BybitCaptureError("reviewed_crypto_registry_changed")
    if updated.decision_at_ms <= previous.decision_at_ms:
        raise J1BybitCaptureError("resume_target_not_new_closed_hour")
    hours_elapsed = (updated.decision_at_ms - previous.decision_at_ms) // HOUR_MS
    if hours_elapsed > MAX_CATCHUP_HOURS:
        raise J1BybitCaptureError("resume_catchup_exceeds_144h_safety_limit")
    # Collect + audit ALL missing closed pages before the first new SQLite
    # row, just like J1's original 720h preflight. Failed network responses
    # do not change the existing database.
    pending: dict[str, tuple[BybitResearchRawPage, ...]] = {}
    missing = 0
    for member in updated.ranked:
        cursor = cursors[member.symbol]
        if cursor > updated.decision_at_ms:
            raise J1BybitCaptureError("existing_private_series_ahead_of_observation")
        pages = []
        while cursor < updated.decision_at_ms:
            remaining = (updated.decision_at_ms - cursor) // HOUR_MS
            hours = 72 if remaining >= 72 else 24 if remaining >= 24 else 1
            pages.append(_page(client, clock, member.symbol, cursor, hours))
            cursor += hours * HOUR_MS
            missing += hours
        pending[member.symbol] = tuple(pages)
    for pages in pending.values():
        for page in pages:
            try:
                report = audit_local_bybit_json(
                    instrument_raw=page.instrument_raw,
                    kline_raw=page.kline_raw,
                    manifest=page.manifest,
                )
                if (report["status"] !=
                        "offline_schema_conformance_passed_origin_unverified"
                        or report["registry_sha256"] != updated.registry_sha256
                        or report["documented_quote_turnover_unit"] != "USDT"
                        or report["closed_candle_count"] != (
                            page.manifest.end_open_ms
                            - page.manifest.start_open_ms) // HOUR_MS):
                    raise J1BybitCaptureError("resume_missing_page_preflight_rejected")
            except (DataValidationError, DataGapError):
                raise J1BybitCaptureError("resume_missing_page_preflight_rejected") from None
    if clock() // HOUR_MS * HOUR_MS != updated.decision_at_ms:
        raise J1BybitCaptureError("resume_pit_hour_expired_before_write")
    for pages in pending.values():
        for page in pages:
            store.commit_raw_pair(
                instrument_raw=page.instrument_raw,
                kline_raw=page.kline_raw,
                manifest=page.manifest,
                capture_environment="private_local_unverified",
            )
    for member in updated.ranked:
        quality = store.quality_report(
            symbol=member.symbol, interval="1h",
            start_open_ms=start, end_open_ms=updated.decision_at_ms,
        )
        expected = (updated.decision_at_ms - start) // HOUR_MS
        if (not quality.complete_for_offline_staging_only
                or quality.persisted_candles != expected
                or quality.expected_candles != expected):
            raise J1BybitCaptureError("resume_replayed_history_incomplete")
    # The PIT is observed NOW, after actual GETs. We never synthesize a PIT
    # at missing historical hours. Protect from crossing another UTC boundary.
    if clock() // HOUR_MS * HOUR_MS != updated.decision_at_ms:
        raise J1BybitCaptureError("resume_pit_hour_expired_after_write")
    store.commit_pit_research_snapshot(updated)
    return missing


def owner_resume_private_j1(
    *, database: str | Path, max_assets: int = 2,
    allow_public_network: bool = False,
    allow_private_storage: bool = False,
    confirm_region_and_personal_research: bool = False,
    client: BoundedBybitPublicClient | None = None,
    clock_ms: Callable[[], int] | None = None,
    sleep: Callable[[float], None] | None = None,
    progress: Callable[[dict], None] | None = None,
) -> dict:
    """Resume 720h without re-downloading it; 2 DISTINCT observed PIT hours.

    If any GET or gate fails, previously validated pages remain immutable,
    and this can be safely re-entered after reviewing the sanitized reason.
    """
    if (allow_public_network is not True or allow_private_storage is not True
            or confirm_region_and_personal_research is not True
            or type(max_assets) is not int or not 1 <= max_assets <= 13
            or os.name != "posix"):
        raise J1BybitCaptureError("resume_owner_opt_in_or_posix_required")
    path = _private_db_path(database)
    clock = clock_ms or _clock
    sleeper = sleep or time.sleep
    fetch = client or BoundedBybitPublicClient()
    store, previous, cursors, initial_report, first = _private_state(path)
    if len(previous.ranked) != max_assets:
        raise J1BybitCaptureError("resume_sample_size_does_not_match_private_history")
    registry = load_reviewed_registry(REGISTRY, as_of_ms=clock())
    if previous.registry_sha256 != registry.sha256_digest:
        raise J1BybitCaptureError("existing_snapshot_crypto_registry_changed")
    distinct = initial_report["immutable_pit_snapshots"] - 1
    if distinct >= REQUIRED_DISTINCT_UPDATES:
        final = initial_report
    else:
        now = clock()
        cutoff = now // HOUR_MS * HOUR_MS
        if cutoff - previous.decision_at_ms > MAX_CATCHUP_HOURS * HOUR_MS:
            raise J1BybitCaptureError("resume_catchup_exceeds_144h_safety_limit")
        if cutoff > previous.decision_at_ms:
            current, _ = _observe(fetch, clock, max_assets)
            _catchup_pages(
                fetch, clock, previous=previous, updated=current,
                cursors=cursors, start=first, store=store,
            )
            # This is one NEW actual observation, even if past closed bars
            # had to be caught up. Never synthesize a PIT for missed hours.
            distinct += 1
            previous = current
            cursors = {m.symbol: current.decision_at_ms for m in current.ranked}
            _status_event(progress, phase="current_pit_verified",
                          completed=distinct,
                          network_gets=fetch.requests_attempted)
        while distinct < REQUIRED_DISTINCT_UPDATES:
            next_decision = previous.decision_at_ms + HOUR_MS
            wait_ms = next_decision + CLOSE_SAFETY_MS - clock()
            _status_event(progress, phase="waiting_for_next_closed_hour",
                          completed=distinct,
                          network_gets=fetch.requests_attempted)
            if wait_ms > 0:
                sleeper(wait_ms / 1000)
            if clock() // HOUR_MS * HOUR_MS != next_decision:
                raise J1BybitCaptureError("resume_hourly_observation_window_missed")
            updated, _ = _observe(fetch, clock, max_assets)
            if updated.decision_at_ms != next_decision:
                raise J1BybitCaptureError("resume_hourly_observation_not_consecutive")
            if {m.symbol for m in previous.ranked} != {
                    m.symbol for m in updated.ranked}:
                raise J1BybitCaptureError("reviewed_sample_changed_requires_new_backfill")
            # This existing research DB may now exceed 720h. The original
            # append_offline_bybit_hourly_update API is designed for an exact
            # 720-hour fixed window, so use the verified closed-hour catch-up
            # path here instead; it preserves the complete retained history.
            _catchup_pages(
                fetch, clock, previous=previous, updated=updated,
                cursors=cursors, start=first, store=store,
            )
            cursors = {m.symbol: updated.decision_at_ms for m in updated.ranked}
            previous = updated
            distinct += 1
            _status_event(progress, phase="hourly_pit_verified",
                          completed=distinct,
                          network_gets=fetch.requests_attempted)
        final = audit_private_bybit_j1_progress(
            database=path, allow_private_readonly_audit=True,
        )
    if (not final["sqlite_integrity_passed"]
            or not final["private_page_replay_passed"]
            or not final["first_pit_720h_coverage"]
            or final["immutable_pit_snapshots"] - 1 < REQUIRED_DISTINCT_UPDATES
            or final["sample_asset_count"] != max_assets):
        raise J1BybitCaptureError("resumed_history_final_audit_rejected")
    return {
        "status": "private_j1_two_distinct_updates_verified_not_top50",
        "sample_assets": final["sample_asset_count"],
        "stored_closed_candles": final["stored_closed_candle_rows"],
        "stored_page_count": final["stored_page_count"],
        "historical_hours_per_asset_at_initial_PIT": HISTORY_HOURS,
        "immutable_pit_snapshots": final["immutable_pit_snapshots"],
        "distinct_hourly_pit_updates_after_initial": (
            final["immutable_pit_snapshots"] - 1),
        "consecutive_hourly_updates_at_end": final["consecutive_snapshots_at_end"],
        "last_pit_decision_ms": final["last_pit_decision_ms"],
        "first_pit_digest_sha256": final["initial_snapshot_digest_sha256"],
        "sqlite_integrity": True,
        "private_page_replay": True,
        "old_720h_history_preserved": True,
        "network_gets_attempted_this_run": fetch.requests_attempted,
        "marketwide_top50_verified": False,
        "data_stored_locally": True,
        "canonical_data_authorized": False,
        "rights_for_live_authorized": False,
        "orders_sent": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True)
    parser.add_argument("--max-assets", type=int, default=2)
    parser.add_argument("--allow-public-network", action="store_true")
    parser.add_argument("--allow-private-storage", action="store_true")
    parser.add_argument("--confirm-region-and-personal-research", action="store_true")
    args = parser.parse_args(argv)
    client = BoundedBybitPublicClient()

    def event(report):
        print(json.dumps(report, sort_keys=True, separators=(",", ":")),
              flush=True)

    try:
        result = owner_resume_private_j1(
            database=args.database,
            max_assets=args.max_assets,
            allow_public_network=args.allow_public_network,
            allow_private_storage=args.allow_private_storage,
            confirm_region_and_personal_research=(
                args.confirm_region_and_personal_research),
            client=client, progress=event,
        )
    except Exception as exc:
        result = {
            "status": (
                str(exc) if type(exc) is J1BybitCaptureError
                else "private_resume_failed_sanitized"
            ),
            "last_request_stage": client.last_request_stage or "before_first_get",
            "network_gets_attempted": client.requests_attempted,
            "existing_database_preserved": True,
            "marketwide_top50_verified": False,
            "orders_sent": False,
        }
        if client.last_provider_retcode is not None:
            result["provider_ret_code"] = client.last_provider_retcode
    event(result)
    return 0 if result["status"] == (
        "private_j1_two_distinct_updates_verified_not_top50"
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
