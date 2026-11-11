"""J1 automatic USDT-perpetual catalog research, owner-only and GET-only.

Never creates an execution allowlist, history, local snapshot, or live orders.
Read-only metadata observation: no SQLite, private keys, POST or retry.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any, Callable

from crypto_intelligence_agent.bybit_public_j1_transport import (
    BoundedBybitPublicClient, J1BybitCaptureError, instruments_url,
)
from crypto_intelligence_agent.bybit_paginated_universe_research import (
    MAX_PAGES, _cursor, _response,
)
from crypto_intelligence_agent.j1_auto_usdt_perp import (
    screen_bybit_usdt_perps_offline,
)
from crypto_intelligence_agent.market_data import DataValidationError

MAX_OBSERVATION_MS = 300_000


def observe_current_usdt_perpetuals(
    *, client: Any, now_ms: Callable[[], int],
    allow_public_network: bool = False,
    confirm_region_and_personal_research: bool = False,
    include_public_symbols: bool = False,
    private_directory: Path | None = None,
    allow_private_readonly_audit: bool = False,
    owner_ok: bool | None = None,
) -> dict[str, Any]:
    """Consume a whole current Bybit V5 catalog once, bounded and sanitized.

    Requires deliberate owner opt-in. Caller may inject a fake client for
    offline tests. Every GET is the existing allowlisted Bybit public client.
    The V5 cursor chain is validated again by the pure screen function.
    """
    report: dict[str, Any] = {
        "schema_version": "j1-auto-usdt-current-catalog-readonly-v1",
        "status": "abstain",
        "requests_attempted": 0,
        "network_accessed": False,
        "database_modified": False,
        "orders_sent": False,
        "marketwide_top50_verified": False,
        "crypto_identity_independently_verified": False,
    }
    owner = (os.name == "posix" and os.getuid() == os.geteuid()
             and os.geteuid() != 0) if owner_ok is None else owner_ok
    if not (owner and allow_public_network is True
            and confirm_region_and_personal_research is True):
        report["failure_code"] = "owner_opt_in_required"
        return report
    if (client is None or not callable(now_ms)
            or type(include_public_symbols) is not bool
            or (private_directory is not None and
                (not isinstance(private_directory, Path)
                 or not private_directory.is_absolute()
                 or allow_private_readonly_audit is not True))
            or (private_directory is None and
                allow_private_readonly_audit is True)):
        report["failure_code"] = "configuration_invalid"
        return report
    pages = []
    cursors = []
    receipts = []
    requested: str | None = None
    stage = "clock"
    try:
        started = now_ms()
        if type(started) is not int or started <= 1_600_000_000_000:
            raise DataValidationError("invalid local capture clock")
        for index in range(MAX_PAGES):
            stage = "network"
            report["network_accessed"] = True
            _, payload = client.get(instruments_url(cursor=requested))
            received = now_ms()
            if (type(received) is not int or received < started
                    or received - started > MAX_OBSERVATION_MS):
                raise DataValidationError("market catalog receipt clock invalid")
            # Validate provider status/category/time BEFORE another cursor GET.
            _response(
                payload, label="Bybit automatic catalog",
                at_ms=received, age_ms=120_000,
            )
            pages.append(payload)
            cursors.append(requested)
            receipts.append(received)
            stage = "cursor"
            next_cursor = _cursor(
                payload["result"].get("nextPageCursor"), terminal_ok=True
            )
            if next_cursor == "":
                break
            if next_cursor == requested or next_cursor in cursors:
                raise DataValidationError("catalog cursor cycle")
            requested = next_cursor
        else:
            raise DataValidationError("catalog exceeds bounded pagination")
        stage = "screen"
        pool = screen_bybit_usdt_perps_offline(
            instrument_pages=tuple(pages),
            requested_cursors=tuple(cursors),
            page_received_at_ms=tuple(receipts),
            observed_at_ms=receipts[-1],
        )
        report.update(pool.sanitized_report(
            include_public_symbols=include_public_symbols
        ))
        report["schema_version"] = "j1-auto-usdt-current-catalog-readonly-v1"
        report["catalog_captured_after_ms"] = started
        report["catalog_captured_until_ms"] = receipts[-1]
        report["database_modified"] = False
        report["orders_sent"] = False
        report["marketwide_top50_verified"] = False
        report["crypto_identity_independently_verified"] = False
        if private_directory is not None:
            from crypto_intelligence_agent.j1_auto_private_reconcile import (
                reconcile_auto_pool_with_private_census,
            )
            private_result = reconcile_auto_pool_with_private_census(
                pool, private_directory,
                allow_private_readonly_audit=True, owner_ok=owner,
            )
            report["retrospective_private_join"] = private_result
            if private_result["status"] != (
                "retrospective_auto_crypto_usdt_overlap_research_only"
            ):
                report["status"] = "abstain"
                report["failure_code"] = "auto_catalog_private_join_rejected"
    except (DataValidationError, J1BybitCaptureError, ValueError, TypeError, OSError):
        # Never expose provider bodies, URLs, symbols or arbitrary exception.
        report["failure_code"] = "auto_catalog_" + stage + "_rejected"
    finally:
        attempted = getattr(client, "requests_attempted", 0)
        report["requests_attempted"] = (
            attempted if type(attempted) is int and 0 <= attempted <= MAX_PAGES
            else MAX_PAGES
        )
        # The pure classifier and private SQLite join make zero GETs, but
        # this owner CLI *does* fetch catalog pages. The outer report must
        # reflect actual transport attempts, including failed requests.
        report["network_requests"] = report["requests_attempted"]
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-public-network", action="store_true")
    parser.add_argument("--confirm-region-and-personal-research",
                        action="store_true")
    parser.add_argument("--include-public-symbols", action="store_true")
    parser.add_argument("--private-directory", type=Path)
    parser.add_argument("--allow-private-readonly-audit", action="store_true")
    args = parser.parse_args(argv)
    result = observe_current_usdt_perpetuals(
        client=BoundedBybitPublicClient(),
        now_ms=lambda: time.time_ns() // 1_000_000,
        allow_public_network=args.allow_public_network,
        confirm_region_and_personal_research=(
            args.confirm_region_and_personal_research
        ),
        include_public_symbols=args.include_public_symbols,
        private_directory=args.private_directory,
        allow_private_readonly_audit=args.allow_private_readonly_audit,
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["status"] == (
        "automatic_usdt_perpetual_research_candidates_only"
    ) else 2


if __name__ == "__main__":
    raise SystemExit(main())
