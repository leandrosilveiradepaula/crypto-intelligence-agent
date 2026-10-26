"""Private, credential-gated CandleFeed Free OHLCV research conformance.

One bounded BTCUSDT (Binance origin via CandleFeed aggregation) historical
GET, with 24 closed 1h bars and precise JSON. Disabled by default. Requires
an account the user has independently authorized and a key in the PRIVATE
CANDLEFEED_API_KEY environment variable. Never store keys in this repository
or put it into issue_comment GitHub Actions without a separate security gate.
No orders, market-data persistence, canonical ClosedCandle or public display.

CandleFeed terms section 5.3 allows internal research; section 6 warns
upstream exchange terms may apply. Their Free plan allows 5 symbols, 30d,
100 daily requests, no card; this tool never invokes paid APIs.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
import re
from time import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import (
    HTTPRedirectHandler, ProxyHandler, Request, build_opener,
)

from crypto_intelligence_agent.candlefeed_ohlcv_research import (
    HOUR_MS, WINDOW_HOURS, stage_candlefeed_btc_24h,
)
from crypto_intelligence_agent.decimal_json import decode_public_market_json_exact
from crypto_intelligence_agent.market_data import DataGapError, DataValidationError
from crypto_intelligence_agent.research_registry_catalog import load_reviewed_registry

HOST_AND_PATH = "https://candlefeed.ai/api/v1/candles"
ENV_KEY = "CANDLEFEED_API_KEY"
_MAX_RESPONSE = 131_072
_MAX_CAPTURE_MS = 30_000
_TIMEOUT = 8
_KEY_SHAPE = re.compile(r"cf_live_[A-Za-z0-9_-]{8,200}")


class CandleFeedPrivateError(ValueError):
    """Always use non-secret, provider-independent error strings."""


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _default_open(request: Request, *, timeout: int):
    return build_opener(ProxyHandler({}), _RejectRedirects()).open(
        request, timeout=timeout,
    )


def _clock(clock: Callable[[], int]) -> int:
    value = clock()
    if type(value) is not int or not 10 * HOUR_MS < value < 253_402_300_799_999:
        raise CandleFeedPrivateError("invalid_clock")
    return value


def _url(start_open_ms: int, end_open_ms: int) -> str:
    def iso(ms: int) -> str:
        return datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat(
            timespec="seconds",
        ).replace("+00:00", "Z")
    query = urlencode((
        ("symbol", "BTCUSDT"),
        ("exchange", "binance"),
        ("interval", "1h"),
        ("start", iso(start_open_ms)),
        # CandleFeed 'end' is inclusive; select the last required bar open.
        ("end", iso(end_open_ms - HOUR_MS)),
        ("limit", str(WINDOW_HOURS)),
    ))
    return HOST_AND_PATH + "?" + query


def inspect_once(
    *, allow_public_network: bool, allow_private_research: bool,
    api_key: str | None = None,
    opened: Callable[..., Any] | None = None,
    clock_ms: Callable[[], int] | None = None,
) -> dict[str, Any]:
    if allow_public_network is not True or allow_private_research is not True:
        raise CandleFeedPrivateError("double_opt_in_required")
    # No implicit account/key creation. ENV used only after explicit opt-in.
    key = os.environ.get(ENV_KEY) if api_key is None else api_key
    if type(key) is not str or _KEY_SHAPE.fullmatch(key) is None:
        raise CandleFeedPrivateError("private_candlefeed_api_key_required")
    now_fn = clock_ms or (lambda: int(time() * 1000))
    started = _clock(now_fn)
    registry = load_reviewed_registry("btc-eth", as_of_ms=started)
    if "BTC" not in registry.verified_crypto_bases:
        raise CandleFeedPrivateError("btc_identity_not_reviewed_at_capture")
    aligned = started // HOUR_MS * HOUR_MS
    start, end = aligned - (WINDOW_HOURS + 1) * HOUR_MS, aligned - HOUR_MS
    url = _url(start, end)
    output: dict[str, Any] = {
        "schema_version": "j1-candlefeed-private-ohlcv-research-v1",
        "origin_exchange": "binance",
        "aggregator": "candlefeed",
        "symbol": "BTCUSDT",
        "requested_hours": WINDOW_HOURS,
        "observed_at_utc": datetime.fromtimestamp(
            started / 1000, timezone.utc,
        ).isoformat(timespec="seconds"),
        "requests_attempted": 0,
        "registry_sha256": registry.sha256_digest,
        "volume_basis": "provider_reported_base_BTC_and_normalized_USD",
        "settlement_quote_currency": "USDT_not_equal_to_reported_USD",
        "credentials_in_output": False,
        "raw_data_in_output": False,
        "provider_data_persisted": False,
        "canonical_ohlcv_approved": False,
        "financial_backtest_approved": False,
        "commercial_or_public_redistribution_authorized": False,
        "upstream_venue_rights_verified": False,
        "top50_historical_approved": False,
        "orders_sent": False,
    }
    opener = opened or _default_open
    request = Request(url, method="GET", headers={
        "Accept": "application/json", "X-API-Key": key,
    })
    output["requests_attempted"] = 1
    try:
        with opener(request, timeout=_TIMEOUT) as response:
            if response.getcode() != 200:
                raise CandleFeedPrivateError("provider_unexpected_http_status")
            if response.geturl() != url:
                raise CandleFeedPrivateError("redirect_or_origin_change_rejected")
            mime = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
            if mime != "application/json":
                raise CandleFeedPrivateError("invalid_json_content_type")
            raw = response.read(_MAX_RESPONSE + 1)
            if not 1 <= len(raw) <= _MAX_RESPONSE:
                raise CandleFeedPrivateError("invalid_json_response_size")
        output["response_sha256"] = sha256(raw).hexdigest()
        payload = decode_public_market_json_exact(raw, max_bytes=_MAX_RESPONSE)
        observed = _clock(now_fn)
        if observed < started or observed - started > _MAX_CAPTURE_MS:
            raise CandleFeedPrivateError("capture_clock_expired_or_reversed")
        page = stage_candlefeed_btc_24h(
            payload, start_open_ms=start, end_open_ms=end,
            requested_at_ms=started, observed_at_ms=observed,
        )
        output["valid_closed_candles"] = len(page.candles)
        output["full_requested_window"] = len(page.candles) == WINDOW_HOURS
        output["status"] = "private_provider_schema_validated_not_venue_verified"
    except HTTPError as error:
        # Never emit remote error bodies, key, headers or URL.
        output["status"] = (
            "provider_auth_or_access_blocked"
            if error.code in (401, 403, 418, 429, 451)
            else "provider_http_error_no_retry"
        )
    except (URLError, TimeoutError, OSError, ConnectionError):
        output["status"] = "provider_network_failure_no_retry"
    except (DataGapError, DataValidationError):
        output["status"] = "provider_hourly_schema_or_completeness_rejected"
    except CandleFeedPrivateError as error:
        output["status"] = error.args[0]
    except Exception:
        # An unexpected opener/provider exception might embed a credential in
        # its message. Never let that message reach stdout or traceback output.
        output["status"] = "unexpected_provider_failure_sanitized"
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-public-network", action="store_true")
    parser.add_argument("--allow-private-research", action="store_true")
    args = parser.parse_args()
    try:
        result = inspect_once(
            allow_public_network=args.allow_public_network,
            allow_private_research=args.allow_private_research,
        )
    except (CandleFeedPrivateError, DataValidationError):
        result = {
            "status": "private_preflight_rejected_no_network",
            "requests_attempted": 0,
            "raw_data_in_output": False,
            "credentials_in_output": False,
            "canonical_ohlcv_approved": False,
            "commercial_or_public_redistribution_authorized": False,
            "orders_sent": False,
        }
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["status"] == "private_provider_schema_validated_not_venue_verified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
