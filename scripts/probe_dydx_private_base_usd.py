"""One-shot dYdX Chain v4 BTC perpetual *research* conformance.

Exactly 1 GET current perpetual market + at most 1 GET recent candles,
only after TWO opt-ins. No key, paid API, order, POST, redirect, proxy,
retry, disk persistence, raw price/volume output or commercial rights.
In CI the network flags are never enabled; test with an injected opener.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from time import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import (
    HTTPRedirectHandler, ProxyHandler, Request, build_opener,
)

from crypto_intelligence_agent.decimal_json import decode_public_market_json_exact
from crypto_intelligence_agent.dydx_v4_candle_research import (
    HOUR_MS, TICKER, stage_dydx_v4_btc_hourly,
)
from crypto_intelligence_agent.market_data import DataGapError, DataValidationError
from crypto_intelligence_agent.research_registry_catalog import load_reviewed_registry

MARKETS_URL = "https://indexer.dydx.trade/v4/perpetualMarkets?ticker=BTC-USD"
CANDLES_URL = (
    "https://indexer.dydx.trade/v4/candles/perpetualMarkets/"
    "BTC-USD?resolution=1HOUR&limit=6"
)
MAX_BYTES = 131_072
TIMEOUT_SECONDS = 8
MAX_ELAPSED_MS = 30_000


class PrivateProbeError(ValueError):
    """Bounded diagnostic, with no remote error payload echoed."""


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _open(req: Request, *, timeout: int):
    return build_opener(ProxyHandler({}), _RejectRedirects()).open(
        req, timeout=timeout,
    )


def _get(url: str, *, opened: Callable[..., Any],
         report: dict[str, Any], hash_field: str) -> dict[str, Any]:
    if url not in (MARKETS_URL, CANDLES_URL):
        raise PrivateProbeError("invalid_fixed_host_or_endpoint")
    if report["requests_attempted"] >= 2:
        raise PrivateProbeError("two_get_budget_exceeded")
    request = Request(url, method="GET", headers={"Accept": "application/json"})
    report["requests_attempted"] += 1
    try:
        with opened(request, timeout=TIMEOUT_SECONDS) as response:
            if response.getcode() != 200:
                raise PrivateProbeError("unexpected_http_status")
            if response.geturl() != url:
                raise PrivateProbeError("redirect_or_changed_origin_rejected")
            if response.headers.get("geo-origin-status", "").lower() in ("restricted", "blocked"):
                raise PrivateProbeError("access_or_geographic_restriction")
            if response.headers.get("Content-Type", "").split(";")[0].lower() != "application/json":
                raise PrivateProbeError("unexpected_content_type")
            raw = response.read(MAX_BYTES + 1)
            if not 1 <= len(raw) <= MAX_BYTES:
                raise PrivateProbeError("response_size_invalid")
    except HTTPError as error:
        if error.code in (301, 302, 303, 307, 308):
            raise PrivateProbeError("redirect_rejected") from None
        if error.code in (403, 418, 429, 451):
            raise PrivateProbeError("access_or_geographic_restriction") from None
        raise PrivateProbeError("http_error") from None
    except (URLError, OSError, TimeoutError, ConnectionError):
        raise PrivateProbeError("network_failure_no_retry") from None
    report[hash_field] = sha256(raw).hexdigest()
    try:
        return decode_public_market_json_exact(raw, max_bytes=MAX_BYTES)
    except DataValidationError:
        raise PrivateProbeError("invalid_exact_json") from None


def _clock_ms(clock: Callable[[], int]) -> int:
    value = clock()
    if type(value) is not int or not 10 * HOUR_MS < value < 253_402_300_799_999:
        raise PrivateProbeError("invalid_utc_clock")
    return value


def inspect_once(
    *, allow_public_network: bool, allow_private_dydx_probe: bool,
    opened: Callable[..., Any] | None = None,
    clock_ms: Callable[[], int] | None = None,
) -> dict[str, Any]:
    if allow_public_network is not True or allow_private_dydx_probe is not True:
        raise PrivateProbeError("double_opt_in_required")
    clock = clock_ms or (lambda: int(time() * 1000))
    started = _clock_ms(clock)
    # Reject a backdated, expired or unapproved crypto registry BEFORE any GET.
    registry = load_reviewed_registry("btc-eth", as_of_ms=started)
    if "BTC" not in registry.verified_crypto_bases:
        raise PrivateProbeError("btc_identity_not_verified")
    top = (started // HOUR_MS) * HOUR_MS
    start, end = top - 4 * HOUR_MS, top - HOUR_MS
    report: dict[str, Any] = {
        "schema_version": "j1-dydx-v4-private-btc-volume-v1",
        "source": "dydx_v4_indexer",
        "ticker": TICKER, "resolution": "1HOUR",
        "observed_at_utc": datetime.fromtimestamp(started / 1000, timezone.utc)
            .isoformat(timespec="seconds"),
        "window_start_ms": start, "window_end_ms_exclusive": end,
        "requests_attempted": 0, "credentials_used": False, "orders_sent": False,
        "responses_persisted": False, "market_data_published": False,
        "canonical_ohlcv_approved": False, "historical_top50_approved": False,
        "public_or_commercial_rights_authorized": False,
        "ready_for_trading": False,
        "reporting_quote_volume_unit": "USD (not settlement USDC)",
        "reporting_base_volume_unit": "BTC",
        "registry_sha256": registry.sha256_digest,
    }
    opener = opened or _open
    try:
        markets = _get(MARKETS_URL, opened=opener, report=report,
                       hash_field="markets_response_sha256")
        current = _clock_ms(clock)
        if current < started or current - started > MAX_ELAPSED_MS:
            raise PrivateProbeError("metadata_capture_window_expired")
        item = markets.get("markets")
        if (type(item) is not dict or type(item.get(TICKER)) is not dict
                or item[TICKER].get("status") != "ACTIVE"
                or item[TICKER].get("ticker", TICKER) != TICKER):
            raise PrivateProbeError("inactive_or_mismatched_btc_market")
        candles = _get(CANDLES_URL, opened=opener, report=report,
                       hash_field="candles_response_sha256")
        observed = _clock_ms(clock)
        if observed < current or observed - started > MAX_ELAPSED_MS:
            raise PrivateProbeError("candles_capture_window_expired")
        page = stage_dydx_v4_btc_hourly(
            markets, candles, market_observed_at_ms=current,
            observed_at_ms=observed, start_open_ms=start, end_open_ms=end,
        )
        report["validated_closed_candles"] = len(page.candles)
        report["base_and_usd_volume_fields_seen"] = all(
            c.base_token_volume > 0 and c.usd_volume > 0 for c in page.candles)
        report["source_schema_and_temporal_validity_verified"] = True
        report["status"] = "private_dydx_base_usd_schema_observed"
    except PrivateProbeError as error:
        report["status"] = error.args[0]
    except (DataValidationError, DataGapError):
        report["status"] = "market_or_candle_contract_rejected"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-public-network", action="store_true")
    parser.add_argument("--allow-private-dydx-probe", action="store_true")
    args = parser.parse_args()
    try:
        output = inspect_once(
            allow_public_network=args.allow_public_network,
            allow_private_dydx_probe=args.allow_private_dydx_probe,
        )
    except (PrivateProbeError, DataValidationError) as error:
        output = {
            "status": "preflight_rejected",
            "requests_attempted": 0, "credentials_used": False,
            "orders_sent": False, "responses_persisted": False,
            "canonical_ohlcv_approved": False,
            "public_or_commercial_rights_authorized": False,
        }
    print(json.dumps(output, sort_keys=True, separators=(",", ":")))
    return 0 if output["status"] == "private_dydx_base_usd_schema_observed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
