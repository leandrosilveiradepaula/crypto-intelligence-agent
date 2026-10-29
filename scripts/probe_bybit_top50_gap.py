"""J1 #319 owner-only: audit all Bybit linear instruments to expose Top50 GAP.

All requests use the same bounded official V5 public GET transport and
explicit regional/personal-research opt-in. NO SQLite access, data storage,
order APIs, authenticators or third-party data services. Logs are aggregate,
no symbols, OHLC, market bytes, URLs, cursors, filesystem paths or secrets.

This is a catalog/identity census, NOT market turnover ranking or permission
to mark 50 asset historical series as verified.
"""
from __future__ import annotations

import argparse
import json
import os
from typing import Callable

from crypto_intelligence_agent.bybit_paginated_universe_research import (
    MAX_PAGES, classify_bybit_instrument_scan_failure,
)
from crypto_intelligence_agent.bybit_public_j1_transport import (
    BoundedBybitPublicClient, J1BybitCaptureError, instruments_url,
)
from crypto_intelligence_agent.bybit_top50_coverage_census import (
    census_bybit_top50_identity_coverage,
)
from crypto_intelligence_agent.market_data import DataValidationError
from scripts.capture_private_bybit_j1 import _clock

MAX_CENSUS_DURATION_MS = 120_000


def owner_probe_bybit_top50_gap(
    *, allow_public_network: bool = False,
    confirm_region_and_personal_research: bool = False,
    client: BoundedBybitPublicClient | None = None,
    clock_ms: Callable[[], int] | None = None,
    registry_variant: str = "expanded-13",
) -> dict:
    if (allow_public_network is not True
            or confirm_region_and_personal_research is not True
            or os.name != "posix"):
        raise J1BybitCaptureError("top50_census_owner_opt_in_or_posix_required")
    fetch = client or BoundedBybitPublicClient()
    clock = clock_ms or _clock
    start = clock()
    pages, cursors, receipts = [], [], []
    cursor = None
    seen: set[str] = set()
    for _ in range(MAX_PAGES):
        _, page = fetch.get(instruments_url(cursor=cursor))
        received = clock()
        if (received < start
                or received - start > MAX_CENSUS_DURATION_MS):
            raise J1BybitCaptureError("top50_census_capture_exceeds_120s")
        pages.append(page)
        cursors.append(cursor)
        receipts.append(received)
        result = page.get("result")
        if type(result) is not dict:
            raise J1BybitCaptureError("top50_census_instrument_page_invalid")
        next_cursor = result.get("nextPageCursor")
        if next_cursor == "":
            break
        if (type(next_cursor) is not str or not next_cursor
                or len(next_cursor) > 300
                or any(ord(c) < 33 or ord(c) > 126 for c in next_cursor)
                or next_cursor in seen):
            raise J1BybitCaptureError("top50_census_cursor_invalid")
        seen.add(next_cursor)
        cursor = next_cursor
    else:
        raise J1BybitCaptureError("top50_census_max_pagination_exceeded")
    observed = clock()
    if observed - start > MAX_CENSUS_DURATION_MS:
        raise J1BybitCaptureError("top50_census_capture_exceeds_120s")
    try:
        census = census_bybit_top50_identity_coverage(
            instrument_pages=tuple(pages),
            requested_cursors=tuple(cursors),
            page_received_at_ms=tuple(receipts),
            observed_at_ms=observed,
            registry_variant=registry_variant,
        )
    except DataValidationError as error:
        raise J1BybitCaptureError(
            "top50_census_" +
            classify_bybit_instrument_scan_failure(error)
        ) from None
    report = census.sanitized_report()
    report["network_gets_attempted"] = fetch.requests_attempted
    report["data_stored"] = False
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-public-network", action="store_true")
    parser.add_argument(
        "--confirm-region-and-personal-research", action="store_true"
    )
    args = parser.parse_args(argv)
    client = BoundedBybitPublicClient()
    try:
        report = owner_probe_bybit_top50_gap(
            allow_public_network=args.allow_public_network,
            confirm_region_and_personal_research=(
                args.confirm_region_and_personal_research
            ),
            client=client,
        )
    except Exception as error:
        report = {
            "status": (str(error) if type(error) is J1BybitCaptureError
                       else "top50_census_failed_sanitized"),
            "last_request_stage": client.last_request_stage or "before_first_get",
            "network_gets_attempted": client.requests_attempted,
            "marketwide_top50_verified": False,
            "crypto_identity_for_unreviewed_candidates_verified": False,
            "data_stored": False,
            "orders_sent": False,
        }
        if client.last_provider_retcode is not None:
            report["provider_ret_code"] = client.last_provider_retcode
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if report["status"] == (
        "j1_top50_marketwide_identity_coverage_incomplete"
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
