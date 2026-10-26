"""AUTH1: explicit, private, read-only connection diagnosis for one exchange.

Never sends orders, exposes balances or logs account identifiers.
Default is OFFLINE. This script is not an automated trading adapter.
"""
from __future__ import annotations

import argparse
from decimal import Decimal
import hashlib
import hmac
import json
import os
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import (
    HTTPSHandler, HTTPRedirectHandler, ProxyHandler, Request, build_opener,
)

_BINANCE_URL = "https://fapi.binance.com/fapi/v1/positionSide/dual"
_BYBIT_URL = "https://api.bybit.com/v5/user/query-api"
_MAX_RESPONSE = 8192
_TIMEOUT_S = 8


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _sign_binance(secret: str, timestamp_ms: int) -> str:
    query = urlencode({"timestamp": timestamp_ms, "recvWindow": 5000})
    sig = hmac.new(secret.encode("utf-8"), query.encode("ascii"), hashlib.sha256).hexdigest()
    return query + "&signature=" + sig


def _sign_bybit(key: str, secret: str, timestamp_ms: int) -> str:
    payload = str(timestamp_ms) + key + "5000"
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def _safe_result(venue: str, status: str) -> dict[str, object]:
    return {
        "venue": venue, "status": status,
        "orders_sent": False, "balances_exported": False,
        "trading_enabled": False, "source_market_data_verified": False,
        "private_account_details_exported": False,
    }


def _strict_json(raw: bytes) -> dict:
    if len(raw) > _MAX_RESPONSE:
        raise ValueError("oversized")
    def unique(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise ValueError("duplicate")
            out[key] = value
        return out
    data = json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                      parse_float=Decimal,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("constant")))
    if type(data) is not dict:
        raise ValueError("shape")
    return data


def diagnose(venue: str, *, allow_private_read: bool = False,
             confirm_read_only_key: bool = False,
             env: dict[str, str] | None = None,
             now_ms: int | None = None, opener=None) -> dict[str, object]:
    """One signed GET, ONLY with two explicit flags and private credentials.

    The opener argument is for offline unit tests only; no production caller
    should inject an alternative host or transport.
    """
    if venue not in ("binance", "bybit") or type(venue) is not str:
        raise ValueError("venue")
    if not allow_private_read or not confirm_read_only_key:
        return _safe_result(venue, "offline_network_disabled")
    values = os.environ if env is None else env
    prefix = "BINANCE" if venue == "binance" else "BYBIT"
    key = values.get(prefix + "_READONLY_API_KEY", "")
    secret = values.get(prefix + "_READONLY_API_SECRET", "")
    if not key or not secret or len(key) > 512 or len(secret) > 512:
        return _safe_result(venue, "missing_private_credentials")
    if any(ch in key + secret for ch in "\r\n"):
        return _safe_result(venue, "invalid_private_credentials")
    timestamp = int(time.time() * 1000) if now_ms is None else now_ms
    if type(timestamp) is not int or timestamp <= 0:
        raise ValueError("clock")
    if venue == "binance":
        url = _BINANCE_URL + "?" + _sign_binance(secret, timestamp)
        headers = {"X-MBX-APIKEY": key, "Accept": "application/json"}
    else:
        url = _BYBIT_URL
        headers = {
            "X-BAPI-API-KEY": key,
            "X-BAPI-TIMESTAMP": str(timestamp),
            "X-BAPI-RECV-WINDOW": "5000",
            "X-BAPI-SIGN": _sign_bybit(key, secret, timestamp),
            "X-BAPI-SIGN-TYPE": "2",
            "Accept": "application/json",
        }
    request = Request(url, method="GET", headers=headers)
    client = opener if opener is not None else build_opener(
        ProxyHandler({}), _NoRedirect(), HTTPSHandler(),
    )
    try:
        with client.open(request, timeout=_TIMEOUT_S) as response:
            if response.status != 200:
                return _safe_result(venue, "provider_http_error")
            if response.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
                return _safe_result(venue, "invalid_provider_response")
            raw = response.read(_MAX_RESPONSE + 1)
        data = _strict_json(raw)
        if venue == "bybit":
            if data.get("retCode") != 0 or type(data.get("result")) is not dict:
                return _safe_result(venue, "provider_rejected")
            if data["result"].get("readOnly") != 1:
                return _safe_result(venue, "key_not_confirmed_read_only")
            return _safe_result(venue, "authenticated_read_only_key_confirmed")
        if type(data.get("dualSidePosition")) is not bool:
            return _safe_result(venue, "invalid_provider_response")
        # This Binance endpoint proves authenticated access, NOT permissions.
        return _safe_result(venue, "authenticated_permissions_not_attested")
    except HTTPError as exc:
        if exc.code in (401, 403, 418, 451):
            status = "access_or_region_restricted"
        elif exc.code == 429:
            status = "rate_limited"
        else:
            status = "provider_http_error"
        return _safe_result(venue, status)
    except (URLError, TimeoutError, OSError):
        return _safe_result(venue, "network_unavailable")
    except (ValueError, UnicodeError, json.JSONDecodeError, TypeError):
        return _safe_result(venue, "invalid_provider_response")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Private read-only AUTH1 connectivity diagnostic")
    parser.add_argument("--venue", required=True, choices=("binance", "bybit"))
    parser.add_argument("--allow-private-read", action="store_true")
    parser.add_argument("--confirm-read-only-key", action="store_true")
    args = parser.parse_args(argv)
    report = diagnose(args.venue, allow_private_read=args.allow_private_read,
                      confirm_read_only_key=args.confirm_read_only_key)
    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"].startswith("authenticated_") else 1


if __name__ == "__main__":
    sys.exit(main())
