"""J1 #319 owner-only Bybit GET research, exactly 24 CLOSED 1h quote-USDT bars.

Audits FULL live paginated instruments-info twice (before and after all kline
GETs), then ranks ONLY newly reviewed crypto bases, with deterministic Decimal
turnover totals. This proves neither marketwide Top50 nor historical 30d
coverage. Never touches the existing two-asset SQLite or order credentials.

Bounded: fixed Bybit host, GET-only, real 2s pacing, 500 request total cap,
20 pages for each full catalog scan, <=6-minute total observation budget,
no retries on rate limits, no redirects. Any incomplete or changing full
catalog or 24-hour series aborts without reporting a ranked subset.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from typing import Callable

from crypto_intelligence_agent.bybit_paginated_universe_research import (
    scan_bybit_linear_instruments_offline,
    classify_bybit_instrument_scan_failure,
)
from crypto_intelligence_agent.bybit_public_j1_transport import (
    BoundedBybitPublicClient, J1BybitCaptureError, kline_url,
)
from crypto_intelligence_agent.bybit_top50_closed_hour_rank import (
    HOUR_MS, WINDOW_HOURS, MAX_BATCH_DURATION_MS,
    rank_bybit_reviewed_closed_24h_pit,
)
from crypto_intelligence_agent.market_data import (
    DataGapError, DataValidationError,
)
from crypto_intelligence_agent.research_registry_catalog import (
    load_reviewed_registry,
)
from scripts.probe_bybit_top50_gap import (
    _capture_complete_instrument_catalog,
)

REGISTRY = "expanded-52"
CLOSE_SAFETY_MS = 2000


def observe_reviewed_closed_24h_rank(
    *, fetch: BoundedBybitPublicClient,
    clock: Callable[[], int],
    progress: Callable[[dict], None] | None = None,
):
    """Trusted internal data structure for an owner-gated caller, never output."""
    start = clock()
    cutoff = start // HOUR_MS * HOUR_MS
    # Fail BEFORE first GET if the current hour cannot fit a conservatively
    # bounded 6-minute read; never mix two different UTC decision hours.
    if start - cutoff < CLOSE_SAFETY_MS:
        raise J1BybitCaptureError("closed24h_start_requires_closed_bar_safety")
    if start - cutoff > HOUR_MS - MAX_BATCH_DURATION_MS - CLOSE_SAFETY_MS:
        raise J1BybitCaptureError("closed24h_start_too_late_in_utc_hour")
    load_reviewed_registry(REGISTRY, as_of_ms=start)

    pages, cursors, receipts, first_finished = (
        _capture_complete_instrument_catalog(fetch, clock)
    )
    if first_finished // HOUR_MS * HOUR_MS != cutoff:
        raise J1BybitCaptureError("closed24h_initial_catalog_crossed_utc_hour")
    try:
        reviewed = scan_bybit_linear_instruments_offline(
            instrument_pages=pages, requested_cursors=cursors,
            page_received_at_ms=receipts, observed_at_ms=first_finished,
            registry_variant=REGISTRY,
        )
    except DataValidationError as error:
        raise J1BybitCaptureError(
            "closed24h_initial_catalog_" +
            classify_bybit_instrument_scan_failure(error)
        ) from None
    # Never query unreviewed or TradFi/USDC symbols as part of this rank.
    eligible = tuple(
        member for member in reviewed.instruments
        if member.launch_time_ms <= cutoff - WINDOW_HOURS * HOUR_MS
    )
    if not eligible:
        raise J1BybitCaptureError("closed24h_no_reviewed_eligible_contracts")
    if progress is not None:
        progress({
            "event": "closed24h_reviewed_rank_progress",
            "phase": "catalog_preflight_passed",
            "reviewed_contracts": len(reviewed.instruments),
            "reviewed_with_24h_listing_history": len(eligible),
            "network_gets_attempted": fetch.requests_attempted,
            "marketwide_top50_verified": False, "orders_sent": False,
        })

    kline_pages, kline_receipts = {}, {}
    for i, member in enumerate(eligible, 1):
        _, payload = fetch.get(kline_url(
            member.symbol, cutoff - WINDOW_HOURS * HOUR_MS, cutoff,
        ))
        received = clock()
        if (received // HOUR_MS * HOUR_MS != cutoff
                or received - start > MAX_BATCH_DURATION_MS):
            raise J1BybitCaptureError("closed24h_kline_crossed_utc_budget")
        kline_pages[member.symbol] = payload
        kline_receipts[member.symbol] = received
        if progress is not None and (i % 10 == 0 or i == len(eligible)):
            progress({
                "event": "closed24h_reviewed_rank_progress",
                "phase": "closed_kline_24h_pages_received",
                "completed": i, "expected": len(eligible),
                "network_gets_attempted": fetch.requests_attempted,
                "marketwide_top50_verified": False, "orders_sent": False,
            })
    # A second ENTIRE catalog scan catches mid-capture listing changes and
    # possible volume-rank selection drift of the reviewed membership.
    after_pages, after_cursors, after_receipts, observed = (
        _capture_complete_instrument_catalog(fetch, clock)
    )
    if (observed // HOUR_MS * HOUR_MS != cutoff
            or observed - start > MAX_BATCH_DURATION_MS):
        raise J1BybitCaptureError("closed24h_final_catalog_crossed_utc_budget")
    try:
        ranked = rank_bybit_reviewed_closed_24h_pit(
            before_instrument_pages=pages,
            before_requested_cursors=cursors,
            before_page_received_at_ms=receipts,
            after_instrument_pages=after_pages,
            after_requested_cursors=after_cursors,
            after_page_received_at_ms=after_receipts,
            kline_pages=kline_pages,
            kline_page_received_at_ms=kline_receipts,
            decision_at_ms=cutoff, observed_at_ms=observed,
            registry_variant=REGISTRY,
        )
    except (DataValidationError, DataGapError):
        raise J1BybitCaptureError(
            "closed24h_catalog_or_kline_coverage_validation_rejected"
        ) from None
    return ranked

def owner_rank_bybit_reviewed_closed_24h(
    *, allow_public_network: bool = False,
    confirm_region_and_personal_research: bool = False,
    emit_public_ranked_symbols: bool = False,
    client: BoundedBybitPublicClient | None = None,
    clock_ms: Callable[[], int] | None = None,
    progress: Callable[[dict], None] | None = None,
) -> dict:
    """One audited closed-hour research observation of the 52-base registry.

    No writes to local DB, filesystem, account or GitHub. The public-symbol
    option is solely for audit; prices, turnover and OHLC never leave RAM.
    """
    if (allow_public_network is not True
            or confirm_region_and_personal_research is not True
            or type(emit_public_ranked_symbols) is not bool
            or os.name != "posix"):
        raise J1BybitCaptureError("closed24h_owner_opt_in_or_posix_required")
    fetch = client if client is not None else BoundedBybitPublicClient()
    clock = clock_ms or (lambda: time.time_ns() // 1_000_000)
    ranked = observe_reviewed_closed_24h_rank(
        fetch=fetch, clock=clock, progress=progress)
    result = ranked.sanitized_report(
        include_public_symbols=emit_public_ranked_symbols
    )
    result["status"] = (
        "private_j1_reviewed_closed_24h_rank_verified_not_marketwide"
    )
    result["network_gets_attempted"] = fetch.requests_attempted
    result["data_stored"] = False
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-public-network", action="store_true")
    parser.add_argument("--confirm-region-and-personal-research",
                        action="store_true")
    parser.add_argument("--emit-public-ranked-symbols", action="store_true")
    args = parser.parse_args(argv)
    client = BoundedBybitPublicClient()

    def event(report):
        print(json.dumps(report, sort_keys=True, separators=(",", ":")),
              flush=True)

    try:
        result = owner_rank_bybit_reviewed_closed_24h(
            allow_public_network=args.allow_public_network,
            confirm_region_and_personal_research=(
                args.confirm_region_and_personal_research
            ),
            emit_public_ranked_symbols=args.emit_public_ranked_symbols,
            client=client, progress=event,
        )
    except Exception as exc:
        result = {
            "status": (str(exc) if type(exc) is J1BybitCaptureError
                       else "closed24h_capture_failed_sanitized"),
            "last_request_stage":
                client.last_request_stage or "before_first_get",
            "network_gets_attempted": client.requests_attempted,
            "data_stored": False,
            "marketwide_top50_verified": False,
            "orders_sent": False,
        }
        if client.last_provider_retcode is not None:
            result["provider_ret_code"] = client.last_provider_retcode
        # Only bounded, whitelisted response-header integers. No API body,
        # URL, symbol, server message, account headers or retry instructions.
        result.update(client.sanitized_quota_fields())
    event(result)
    return (0 if result["status"] ==
            "private_j1_reviewed_closed_24h_rank_verified_not_marketwide"
            else 1)


if __name__ == "__main__":
    raise SystemExit(main())
