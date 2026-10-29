"""J1 #319 owner-only public Bybit ticker priority, NOT a confirmed Top50.

Fixed-origin GET: full instruments pages + ONE aggregate ticker endpoint.
All in-memory, 2s minimum GET spacing, bounded resources; no SQLite, orders,
auth, credentials, raw prices, OHLC or full ticker market-data output.
Bybit ticker turnover24h is ROLLING, not the 24 CLOSED UTC hourly candles
required for a marketwide ranking. This ranks only independent-review WORK,
never trading decisions or historical PIT eligibility.

Only when --emit-public-review-symbols is explicit, output identifiers
from the 75 highest ticker-proxy-ranked candidates, excluding the 13 reviewed
bases. No prices or market values are emitted even under this opt-in.
Do not copy those identifiers into the public repository or deploy them.
"""
from __future__ import annotations

import argparse
import json
import os
from typing import Callable

from crypto_intelligence_agent.bybit_paginated_universe_research import (
    classify_bybit_instrument_scan_failure,
)
from crypto_intelligence_agent.bybit_public_j1_transport import (
    BoundedBybitPublicClient, J1BybitCaptureError, tickers_url,
)
from crypto_intelligence_agent.bybit_top50_ticker_priority import (
    rank_bybit_ticker_identity_review_priority,
)
from crypto_intelligence_agent.market_data import DataValidationError
from scripts.capture_private_bybit_j1 import _clock
from scripts.probe_bybit_top50_gap import _capture_complete_instrument_catalog

MAX_TOTAL_REVIEW_PROBE_MS = 150_000


def owner_prioritize_bybit_top50_review(
    *, allow_public_network: bool = False,
    confirm_region_and_personal_research: bool = False,
    emit_public_review_symbols: bool = False,
    client: BoundedBybitPublicClient | None = None,
    clock_ms: Callable[[], int] | None = None,
    priority_rank_limit: int = 75,
) -> dict:
    """GET-only owner probe; only candidate *identifiers* optional in report."""
    if (allow_public_network is not True
            or confirm_region_and_personal_research is not True
            or type(emit_public_review_symbols) is not bool
            or os.name != "posix"):
        raise J1BybitCaptureError("priority_probe_owner_opt_in_or_posix_required")
    fetch = client if client is not None else BoundedBybitPublicClient()
    clock = clock_ms or _clock
    start = clock()
    pages, cursors, receipts, _ = _capture_complete_instrument_catalog(
        fetch, clock,
    )
    # No raw instrument or symbol list is persisted in this workflow.
    # The one ticker GET happens only AFTER complete pagination was received.
    _, ticker = fetch.get(tickers_url())
    observed = clock()
    if (observed < start
            or observed - start > MAX_TOTAL_REVIEW_PROBE_MS):
        raise J1BybitCaptureError("priority_probe_capture_exceeds_150s")
    try:
        result = rank_bybit_ticker_identity_review_priority(
            instrument_pages=pages,
            requested_cursors=cursors,
            page_received_at_ms=receipts,
            ticker_payload=ticker,
            observed_at_ms=observed,
            priority_rank_limit=priority_rank_limit,
        )
    except DataValidationError as error:
        raise J1BybitCaptureError(
            "priority_probe_" +
            classify_bybit_instrument_scan_failure(error)
        ) from None
    report = result.sanitized_report()
    report["network_gets_attempted"] = fetch.requests_attempted
    report["data_stored"] = False
    if emit_public_review_symbols:
        # Identifiers are public contract symbols, NOT personal information.
        # Explicit opt-in is required because previous J1 scripts are redacted.
        # Never include raw ticker turnovers, prices, addresses or account data.
        report["public_review_contract_identifiers_only"] = list(
            result.priority_review_symbols,
        )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-public-network", action="store_true")
    parser.add_argument(
        "--confirm-region-and-personal-research", action="store_true"
    )
    parser.add_argument("--emit-public-review-symbols", action="store_true")
    parser.add_argument("--priority-rank-limit", type=int, default=75)
    args = parser.parse_args(argv)
    client = BoundedBybitPublicClient()
    try:
        report = owner_prioritize_bybit_top50_review(
            allow_public_network=args.allow_public_network,
            confirm_region_and_personal_research=(
                args.confirm_region_and_personal_research
            ),
            emit_public_review_symbols=args.emit_public_review_symbols,
            priority_rank_limit=args.priority_rank_limit,
            client=client,
        )
    except Exception as error:
        report = {
            "status": (str(error) if type(error) is J1BybitCaptureError
                       else "priority_probe_failed_sanitized"),
            "last_request_stage": client.last_request_stage or "before_first_get",
            "network_gets_attempted": client.requests_attempted,
            "data_stored": False,
            "marketwide_top50_verified": False,
            "orders_sent": False,
        }
        if client.last_provider_retcode is not None:
            report["provider_ret_code"] = client.last_provider_retcode
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if report["status"] == (
        "j1_top50_rolling_ticker_identity_review_priority_only"
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
