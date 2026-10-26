"""J1/WU44: private, bounded Bybit V5 BTCUSDT perp volume conformance.

Reuse WU39's pure contract+price parser, now with independently verified
GET-only HTTPS origin. Strictly 2 GET maximum (instrument + 3 closed 1h
klines). Disabled without two opt-ins; no credentials, POST, trade, retries,
redirects, proxies or raw data in logs/disk.

OFFICIAL unit documentation:
https://bybit-exchange.github.io/docs/v5/market/kline
USDT linear volume is BASE BTC, turnover is quote USDT (NOT USD).
Bybit API rights and region still UNAPPROVED; never promote to canonical
ClosedCandle or any public/commercial product automatically.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from time import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import (
    HTTPRedirectHandler, ProxyHandler, Request, build_opener,
)

from crypto_intelligence_agent.bybit_instrument_volume_contract import (
    stage_bybit_documented_linear_pair,
)
from crypto_intelligence_agent.decimal_json import decode_public_market_json_exact
from crypto_intelligence_agent.market_data import DataGapError, DataValidationError
from crypto_intelligence_agent.research_registry_catalog import load_reviewed_registry

BASE = "https://api.bybit.com"
INSTRUMENT_URL = (
    BASE + "/v5/market/instruments-info?category=linear&symbol=BTCUSDT&limit=1"
)
_KLINE_PATH = BASE + "/v5/market/kline"
HOUR_MS = 3_600_000
MAX_BODY = 131_072
TIMEOUT_SECONDS = 8
MAX_CAPTURE_MS = 30_000


class PrivateBybitProbeError(ValueError):
    """Do not propagate provider messages, URLs or raw payloads to stdout."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _open(request: Request, *, timeout: int):
    # No ambient proxies, redirect following, cookies, credentials or retries.
    return build_opener(ProxyHandler({}), _NoRedirect()).open(
        request, timeout=timeout,
    )


def _now(clock: Callable[[], int]) -> int:
    value = clock()
    if type(value) is not int or not 10 * HOUR_MS < value < 253_402_300_799_999:
        raise PrivateBybitProbeError("invalid_utc_clock")
    return value


def _kline_url(start_open_ms: int, end_open_ms: int) -> str:
    # The end parameter is INCLUSIVE at millisecond precision; the selected
    # window is start <= candle.open < end. Do not include a live newest bar.
    query = urlencode((
        ("category", "linear"), ("symbol", "BTCUSDT"),
        ("interval", "60"), ("start", str(start_open_ms)),
        ("end", str(end_open_ms - 1)), ("limit", "3"),
    ))
    return _KLINE_PATH + "?" + query


def _read(
    *, url: str, exact_allowed_url: str,
    opened: Callable[..., Any], report: dict[str, Any], hash_key: str,
) -> dict[str, Any]:
    if url != exact_allowed_url or report["requests_attempted"] >= 2:
        raise PrivateBybitProbeError("unapproved_endpoint_or_request_budget")
    report["requests_attempted"] += 1
    req = Request(url, method="GET", headers={"Accept": "application/json"})
    try:
        with opened(req, timeout=TIMEOUT_SECONDS) as response:
            if response.getcode() != 200:
                raise PrivateBybitProbeError("http_response_not_200")
            if response.geturl() != url:
                raise PrivateBybitProbeError("redirect_or_origin_changed")
            mime = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
            if mime != "application/json":
                raise PrivateBybitProbeError("unexpected_content_type")
            raw = response.read(MAX_BODY + 1)
            if not 1 <= len(raw) <= MAX_BODY:
                raise PrivateBybitProbeError("unexpected_response_length")
    except HTTPError as error:
        if error.code in (301, 302, 303, 307, 308):
            raise PrivateBybitProbeError("redirect_rejected_no_retry") from None
        if error.code in (401, 403, 418, 429, 451):
            raise PrivateBybitProbeError("bybit_access_or_region_restricted_no_retry") from None
        raise PrivateBybitProbeError("http_error_no_retry") from None
    except (URLError, TimeoutError, ConnectionError, OSError):
        raise PrivateBybitProbeError("network_error_no_retry") from None
    report[hash_key] = sha256(raw).hexdigest()
    try:
        return decode_public_market_json_exact(raw, max_bytes=MAX_BODY)
    except DataValidationError:
        raise PrivateBybitProbeError("nonexact_or_invalid_json_rejected") from None


def inspect_once(
    *, allow_public_network: bool = False, allow_private_bybit_probe: bool = False,
    opened: Callable[..., Any] | None = None,
    clock_ms: Callable[[], int] | None = None,
) -> dict[str, Any]:
    if allow_public_network is not True or allow_private_bybit_probe is not True:
        raise PrivateBybitProbeError("double_opt_in_required")
    clock = clock_ms or (lambda: int(time() * 1000))
    started = _now(clock)
    # Explicit positive ID / as-of registry, BEFORE any GET.
    registry = load_reviewed_registry("expanded-10", as_of_ms=started)
    if "BTC" not in registry.verified_crypto_bases:
        raise PrivateBybitProbeError("reviewed_crypto_btc_missing")
    aligned = (started // HOUR_MS) * HOUR_MS
    start, end = aligned - 4 * HOUR_MS, aligned - HOUR_MS
    expected_kline_url = _kline_url(start, end)
    report: dict[str, Any] = {
        "schema_version": "j1-bybit-v5-private-base-quote-v1",
        "source": "bybit_v5_linear_private_research",
        "symbol": "BTCUSDT", "interval": "1h",
        "observed_at_utc": datetime.fromtimestamp(started / 1000, timezone.utc)
            .isoformat(timespec="seconds"),
        "requests_attempted": 0,
        "max_get_requests": 2,
        "registry_sha256": registry.sha256_digest,
        "documented_base_unit": "BTC",
        "documented_turnover_quote_unit": "USDT_not_USD",
        "data_stored": False,
        "raw_prices_or_volumes_logged": False,
        "credentials_used": False,
        "orders_sent": False,
        "canonical_ohlcv_approved": False,
        "historical_top50_approved": False,
        "public_or_commercial_rights_authorized": False,
        "ready_for_trading": False,
    }
    opener = opened or _open
    try:
        instruments = _read(
            url=INSTRUMENT_URL, exact_allowed_url=INSTRUMENT_URL,
            opened=opener, report=report, hash_key="instrument_response_sha256",
        )
        at_instrument = _now(clock)
        if at_instrument < started or at_instrument - started > MAX_CAPTURE_MS:
            raise PrivateBybitProbeError("instrument_capture_clock_invalid")
        # retCode 10009 is the documented geographic restriction; do not
        # retry with alternate domains/IPs or proxies.
        if instruments.get("retCode") in (10009, 10024):
            raise PrivateBybitProbeError("bybit_access_or_region_restricted_no_retry")
        # Prevalidate metadata BEFORE the kline GET, using the WU39 module.
        from crypto_intelligence_agent.bybit_instrument_volume_contract import (
            validate_bybit_linear_instrument,
        )
        validate_bybit_linear_instrument(
            instruments, symbol="BTCUSDT",
            observed_at_ms=at_instrument, registry_variant="expanded-10",
        )
        klines = _read(
            url=expected_kline_url, exact_allowed_url=expected_kline_url,
            opened=opener, report=report, hash_key="kline_response_sha256",
        )
        at_chart = _now(clock)
        if at_chart < at_instrument or at_chart - started > MAX_CAPTURE_MS:
            raise PrivateBybitProbeError("kline_capture_clock_invalid")
        if klines.get("retCode") in (10009, 10024):
            raise PrivateBybitProbeError("bybit_access_or_region_restricted_no_retry")
        result = stage_bybit_documented_linear_pair(
            instrument_payload=instruments, kline_payload=klines,
            symbol="BTCUSDT", instrument_observed_at_ms=at_instrument,
            kline_observed_at_ms=at_chart, interval="1h",
            start_open_ms=start, end_open_ms=end, registry_variant="expanded-10",
        )
        if (len(result.page.candles) != 3
                or result.base_volume_unit != "BTC"
                or result.quote_turnover_unit != "USDT"
                or result.canonical_ohlcv
                or result.public_or_commercial_use_authorized):
            raise PrivateBybitProbeError("research_contract_not_verified")
        report["validated_closed_candles"] = len(result.page.candles)
        report["live_public_schema_observed"] = True
        report["status"] = "private_real_bybit_base_btc_quote_usdt_observed"
    except PrivateBybitProbeError as error:
        report["status"] = error.args[0]
    except (DataValidationError, DataGapError):
        report["status"] = "instrument_or_kline_contract_rejected"
    except Exception:
        # Untrusted transport exceptions may contain URLs or response bodies.
        report["status"] = "unexpected_public_probe_error_sanitized"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-public-network", action="store_true")
    parser.add_argument("--allow-private-bybit-probe", action="store_true")
    args = parser.parse_args()
    try:
        out = inspect_once(
            allow_public_network=args.allow_public_network,
            allow_private_bybit_probe=args.allow_private_bybit_probe,
        )
    except (PrivateBybitProbeError, DataValidationError):
        out = {
            "status": "offline_or_registry_preflight_rejected",
            "requests_attempted": 0,
            "orders_sent": False, "data_stored": False,
            "canonical_ohlcv_approved": False,
            "public_or_commercial_rights_authorized": False,
        }
    print(json.dumps(out, separators=(",", ":"), sort_keys=True))
    return 0 if out["status"] == "private_real_bybit_base_btc_quote_usdt_observed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
