"""J1/WU25: owner-only, bounded PUBLIC Hyperliquid /info conformance smoke.

Exactly two informational POSTs when explicitly enabled: native BTC perp metadata
and three old, fully closed 1h candles. This tool has no account, wallet,
authentication, exchange/order capability or persistence. Responses are
inspected IN MEMORY; only a sanitized evidence summary may be printed.
No candlestick units, identity, legal rights or trading safety are certified.
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

from crypto_intelligence_agent.hyperliquid_native_research import (
    _native_perp_context, stage_hyperliquid_native_perp_candles,
)
from crypto_intelligence_agent.market_data import DataGapError, DataValidationError

INFO_URL = "https://api.hyperliquid.xyz/info"
HOUR_MS = 3_600_000
MAX_META_BYTES = 1_048_576
MAX_CANDLE_BYTES = 32_768
TIMEOUT_SECONDS = 8


class InfoSmokeError(ValueError):
    """Safe, finite-code diagnostic failure; do not log remote exception data."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _default_open(req: Request, *, timeout: int):
    # Never use proxy credentials or silently follow Location to another host.
    return build_opener(ProxyHandler({}), NoRedirect()).open(req, timeout=timeout)


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, val in pairs:
        if key in output:
            raise InfoSmokeError("duplicate_json_key")
        output[key] = val
    return output


def _bad_float(_: str) -> None:
    raise InfoSmokeError("numeric_float_not_accepted")


def _bad_constant(_: str) -> None:
    raise InfoSmokeError("nonfinite_json_not_accepted")


def _read_json(raw: bytes) -> Any:
    try:
        return json.loads(raw, object_pairs_hook=_unique_pairs,
                          parse_float=_bad_float, parse_constant=_bad_constant)
    except (UnicodeDecodeError, ValueError, RecursionError) as e:
        if isinstance(e, InfoSmokeError):
            raise
        raise InfoSmokeError("invalid_json") from None


def _http_status_code(response: Any) -> int:
    status = response.getcode() if hasattr(response, "getcode") else response.status
    if type(status) is not int:
        raise InfoSmokeError("invalid_http_status")
    return status


def _post_info(
    body: dict[str, Any], *, size_limit: int,
    opened: Callable[..., Any],
    audit: dict[str, Any],
) -> Any:
    # Never accept an arbitrary method, path, user, symbol or request body.
    kind = body.get("type")
    if kind == "metaAndAssetCtxs":
        permitted = body == {"type": "metaAndAssetCtxs", "dex": ""}
    elif kind == "candleSnapshot":
        req_obj = body.get("req")
        permitted = (
            set(body) == {"type", "req"}
            and type(req_obj) is dict
            and set(req_obj) == {"coin", "interval", "startTime", "endTime"}
            and req_obj["coin"] == "BTC"
            and req_obj["interval"] == "1h"
            and type(req_obj["startTime"]) is int
            and type(req_obj["endTime"]) is int
            and 0 < req_obj["startTime"] <= req_obj["endTime"]
        )
    else:
        permitted = False
    if not permitted:
        raise InfoSmokeError("unapproved_info_request")
    data = json.dumps(body, separators=(",", ":"), sort_keys=True).encode("ascii")
    req = Request(INFO_URL, data=data, method="POST",
                  headers={"Content-Type": "application/json", "Accept": "application/json"})
    audit["requests_attempted"] += 1
    try:
        with opened(req, timeout=TIMEOUT_SECONDS) as response:
            if _http_status_code(response) != 200:
                raise InfoSmokeError("unexpected_http_status")
            if response.geturl() != INFO_URL:
                raise InfoSmokeError("redirect_or_unexpected_host")
            content_type = response.headers.get("Content-Type", "").split(";")[0].lower()
            if content_type != "application/json":
                raise InfoSmokeError("unexpected_content_type")
            raw = response.read(size_limit + 1)
            if not 1 <= len(raw) <= size_limit:
                raise InfoSmokeError("response_size_invalid")
    except HTTPError as e:
        if e.code in (301, 302, 303, 307, 308):
            raise InfoSmokeError("redirect_rejected") from None
        if e.code in (403, 418, 429, 451):
            raise InfoSmokeError("access_or_rate_restricted") from None
        raise InfoSmokeError("http_error") from None
    except (TimeoutError, URLError, ConnectionError, OSError) as e:
        raise InfoSmokeError("network_failure") from None
    parsed = _read_json(raw)
    audit[kind + "_sha256"] = sha256(raw).hexdigest()
    return parsed


def inspect_once(
    *, allow_public_network: bool,
    allow_hyperliquid_info: bool,
    clock_ms: Callable[[], int] | None = None,
    opened: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Return only non-sensitive evidence; keep failure and all gates explicit."""
    if allow_public_network is not True or allow_hyperliquid_info is not True:
        raise InfoSmokeError("double_opt_in_required")
    now = int(time() * 1000) if clock_ms is None else clock_ms()
    if type(now) is not int or not 5 * HOUR_MS < now <= 253_402_300_799_999:
        raise InfoSmokeError("invalid_utc_clock")
    base = (now // HOUR_MS) * HOUR_MS
    # Exclude the most recently closed bar as an additional full-hour buffer.
    start, end = base - 4 * HOUR_MS, base - HOUR_MS
    report: dict[str, Any] = {
        "schema_version": "j1-hl-native-info-smoke-v1",
        "provider": "hyperliquid_native",
        "endpoint": "POST /info (informational only)",
        "coin": "BTC", "interval": "1h",
        "observed_at_utc": datetime.fromtimestamp(now / 1000, timezone.utc)
          .isoformat(timespec="seconds"),
        "requested_window_start_ms": start,
        "requested_window_end_ms_exclusive": end,
        "requests_attempted": 0,
        "credentials_used": False, "orders_sent": False,
        "raw_responses_persisted": False,
        "crypto_identity_verified": False,
        "volume_unit_verified": False,
        "external_data_rights_verified": False,
        "ready_for_live_top50": False,
        "ready_for_canonical_ohlcv": False,
    }
    post = opened or _default_open
    try:
        meta = _post_info({"type": "metaAndAssetCtxs", "dex": ""}, size_limit=MAX_META_BYTES,
                          opened=post, audit=report)
        # Reject absence, duplicate symbols or delisted BTC before a second request.
        _native_perp_context(meta, symbol="BTC", observed_at_ms=now)
        if (type(meta) not in (tuple, list) or type(meta[0]) is not dict
                or type(meta[0].get("universe")) is not list):
            raise InfoSmokeError("meta_schema_invalid")
        report["native_instrument_count"] = len(meta[0]["universe"])
        candle = _post_info(
            {"type": "candleSnapshot", "req": {
                "coin": "BTC", "interval": "1h",
                "startTime": start, "endTime": end - 1,
            }},
            size_limit=MAX_CANDLE_BYTES, opened=post, audit=report,
        )
        page = stage_hyperliquid_native_perp_candles(
            meta, candle, symbol="BTC", dex_scope="", interval="1h",
            start_open_ms=start, end_open_ms=end,
            context_observed_at_ms=now, observed_at_ms=now,
            max_context_age_ms=0, close_safety_ms=1_000,
            max_candles=3,
        )
        report["closed_candle_count"] = len(page.candles)
        report["observed_schema_conformance"] = "pass_metadata_and_three_closed_candles"
        report["status"] = "schema_observed_no_live_readiness"
    except (DataValidationError, DataGapError):
        report["status"] = "invalid_provider_schema"
    except InfoSmokeError as exc:
        report["status"] = exc.code
    # No response objects or market values escape this function.
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Owner-only two-request public BTC info conformance diagnostic"
    )
    parser.add_argument("--allow-public-network", action="store_true")
    parser.add_argument("--allow-hyperliquid-info-probe", action="store_true")
    args = parser.parse_args(argv)
    if not (args.allow_public_network and args.allow_hyperliquid_info_probe):
        parser.error("no network by default; require both explicit flags")
    result = inspect_once(
        allow_public_network=args.allow_public_network,
        allow_hyperliquid_info=args.allow_hyperliquid_info_probe,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "schema_observed_no_live_readiness" else 2


if __name__ == "__main__":
    raise SystemExit(main())
