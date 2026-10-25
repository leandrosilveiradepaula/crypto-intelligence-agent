"""Single-request, no-auth Kraken Futures *feasibility probe* (not a trading adapter).

Public endpoint only. No secrets, order APIs, retries, redirects or raw payload
storage. Default CLI behavior is OFFLINE: the network must be explicitly enabled.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import re
import sys
from time import monotonic
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener


PUBLIC_URL = "https://futures.kraken.com/derivatives/api/v3/instruments"
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
MAX_TIMEOUT_SECONDS = 8
_SYMBOL = re.compile(r"^[A-Z0-9_]{1,64}$")


class _NoRedirect(HTTPRedirectHandler):
    """A redirected request could target an unreviewed host: stop instead."""

    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def _default_open(request: Request, *, timeout: int):
    return build_opener(_NoRedirect()).open(request, timeout=timeout)


def make_report(*, opener: Callable[..., Any] | None = None) -> dict[str, object]:
    """Make exactly one allowed GET; return a sanitized public metadata report."""
    opened = opener or _default_open
    began = monotonic()
    at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    common: dict[str, object] = {
        "provider": "kraken_futures",
        "endpoint": "GET /derivatives/api/v3/instruments",
        "source": "futures.kraken.com",
        "observed_at_utc": at,
        "requests_attempted": 1,
        "auth_used": False,
        "orders_enabled": False,
        "raw_response_persisted": False,
        "instrument_classification": "symbol_prefix_heuristic_only",
    }
    request = Request(PUBLIC_URL, headers={"Accept": "application/json"}, method="GET")
    try:
        with opened(request, timeout=MAX_TIMEOUT_SECONDS) as response:
            code = response.getcode()
            if code != 200:
                return {**common, "status": "unexpected_http", "http_status": code}
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                return {**common, "status": "response_too_large", "http_status": code}
            try:
                payload = json.loads(raw)
            except (UnicodeDecodeError, ValueError):
                return {**common, "status": "invalid_json", "http_status": code}
            if (not isinstance(payload, dict)
                    or payload.get("result") != "success"
                    or not isinstance(payload.get("instruments"), list)):
                return {**common, "status": "invalid_schema", "http_status": code}
            instruments = payload["instruments"]
            symbols = [
                instrument["symbol"]
                for instrument in instruments
                if (isinstance(instrument, dict)
                    and isinstance(instrument.get("symbol"), str)
                    and _SYMBOL.fullmatch(instrument["symbol"]) is not None)
            ]
            if not instruments or len(symbols) != len(instruments):
                return {**common, "status": "invalid_instrument_rows", "http_status": code}
            perpetual_candidates = [
                name for name in symbols if name.startswith(("PI_", "PF_"))
            ]
            elapsed_ms = int((monotonic() - began) * 1000)
            return {
                **common,
                "status": "ok",
                "http_status": code,
                "elapsed_ms": elapsed_ms,
                "instrument_count": len(instruments),
                "perpetual_prefix_candidates": len(perpetual_candidates),
                "sample_symbols": sorted(perpetual_candidates)[:5],
                "conformance_limit": (
                    "A reachable GET and symbol-prefix counts do not prove "
                    "contract eligibility, volume comparability or historical coverage"
                ),
            }
    except HTTPError as exc:
        return {
            **common, "http_status": exc.code,
            "status": "policy_or_access_restriction"
            if exc.code in (403, 418, 451) else "http_error",
            "elapsed_ms": int((monotonic() - began) * 1000),
        }
    except (URLError, TimeoutError, OSError):
        return {
            **common, "status": "network_or_dns_failure",
            "elapsed_ms": int((monotonic() - began) * 1000),
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="One public Kraken Futures GET, no authentication or orders."
    )
    parser.add_argument(
        "--allow-public-network", action="store_true",
        help="Required to authorize one public read-only instruments request.",
    )
    args = parser.parse_args(argv)
    if not args.allow_public_network:
        parser.error("no network permitted by default; require --allow-public-network")
    outcome = make_report()
    print(json.dumps(outcome, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if outcome["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
