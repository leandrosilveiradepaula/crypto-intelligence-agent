"""Owner-only J1 Bybit quota header diagnostic: exactly ONE public GET.

Use this instead of replaying 52 kline queries after a 10006 failure.
No retries, background polling, request scheduling, IP/proxy rotation,
credentials, SQLite reads/writes, market numbers or financial orders.

Official documentation: https://bybit-exchange.github.io/docs/v5/rate-limit
X-Bapi-Limit applies per endpoint and the server may not send headers.
Neither one successful call nor observed headers can prove another consumer
did or did not share quota. A missing header means UNKNOWN, never zero.
"""
from __future__ import annotations

import argparse
import json
import os
from typing import Callable

from crypto_intelligence_agent.bybit_public_j1_transport import (
    BoundedBybitPublicClient, J1BybitCaptureError, kline_url,
)
from scripts.capture_private_bybit_j1 import _clock

HOUR_MS = 3_600_000
CLOSE_SAFETY_MS = 2_000


def owner_observe_bybit_kline_quota_once(
    *, allow_public_network: bool = False,
    confirm_region_and_personal_research: bool = False,
    client: BoundedBybitPublicClient | None = None,
    clock_ms: Callable[[], int] | None = None,
) -> dict:
    """One single closed-hour public BTCUSDT kline GET, no market output.

    The first BTCUSDT 1h request is a public routing diagnostic only. It
    does not validate Top50, 24h turnover, historical 30d or live trading.
    """
    if (allow_public_network is not True
            or confirm_region_and_personal_research is not True
            or os.name != "posix"):
        raise J1BybitCaptureError("quota_probe_owner_opt_in_or_posix_required")
    clock = clock_ms or _clock
    fetch = client if client is not None else BoundedBybitPublicClient()
    observed = clock()
    cutoff = observed // HOUR_MS * HOUR_MS
    if (type(observed) is not int or observed < HOUR_MS * 2
            or observed - cutoff < CLOSE_SAFETY_MS):
        raise J1BybitCaptureError("quota_probe_requires_closed_hour_safety")
    # Exact permitted GET query. No auth, API key, POST or alternative host.
    fetch.get(kline_url("BTCUSDT", cutoff - HOUR_MS, cutoff))
    return {
        "status": "j1_one_public_kline_quota_observation_only",
        "network_gets_attempted": fetch.requests_attempted,
        "last_request_stage": fetch.last_request_stage,
        **fetch.sanitized_quota_fields(),
        "data_stored": False,
        "marketwide_top50_verified": False,
        "orders_sent": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-public-network", action="store_true")
    parser.add_argument(
        "--confirm-region-and-personal-research", action="store_true"
    )
    args = parser.parse_args(argv)
    fetch = BoundedBybitPublicClient()
    try:
        report = owner_observe_bybit_kline_quota_once(
            allow_public_network=args.allow_public_network,
            confirm_region_and_personal_research=(
                args.confirm_region_and_personal_research
            ),
            client=fetch,
        )
    except Exception as error:
        report = {
            "status": (str(error) if type(error) is J1BybitCaptureError
                       else "quota_probe_failed_sanitized"),
            "network_gets_attempted": fetch.requests_attempted,
            "last_request_stage":
                fetch.last_request_stage or "before_first_get",
            **fetch.sanitized_quota_fields(),
            "data_stored": False,
            "marketwide_top50_verified": False,
            "orders_sent": False,
        }
        if fetch.last_provider_retcode is not None:
            report["provider_ret_code"] = fetch.last_provider_retcode
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if report["status"] == (
        "j1_one_public_kline_quota_observation_only"
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
