"""OPS35: bounded owner-only GET-only metadata audit; no persistence.

No network by default. No proxies, redirects, account keys, orders, SQLite,
filesystem output, background scheduler, HTTP retries or error-body logging.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, ProxyHandler, HTTPRedirectHandler, build_opener

from crypto_intelligence_agent.j1_binance_metadata_probe import (
    URL, MAX_BODY_BYTES, capture_binance_metadata_once,
)
from crypto_intelligence_agent.research_registry_catalog import load_reviewed_registry


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def bounded_binance_get(url: str, max_bytes: int) -> bytes:
    if (url != URL or type(max_bytes) is not int or max_bytes != MAX_BODY_BYTES):
        raise ValueError("binance_fixed_origin_required")
    req = Request(URL, headers={"Accept": "application/json"}, method="GET")
    opener = build_opener(ProxyHandler({}), NoRedirect())
    try:
        with opener.open(req, timeout=8) as response:
            ctype = response.headers.get("Content-Type", "").split(";")[0].lower().strip()
            if (response.status != 200 or response.geturl() != URL
                    or ctype != "application/json"):
                raise ValueError("binance_http_unexpected_response")
            value = response.read(max_bytes + 1)
            if not 1 <= len(value) <= max_bytes:
                raise ValueError("metadata_size_abstain")
            return value
    except HTTPError:
        raise ValueError("binance_http_access_or_provider_denied_no_retry") from None
    except (URLError, TimeoutError, OSError):
        raise ValueError("binance_http_transport_no_retry") from None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-public-network", action="store_true")
    parser.add_argument("--confirm-region-and-personal-research", action="store_true")
    args = parser.parse_args(argv)
    # Importing Python module does not create an HTTP session. Registry loading
    # is local read-only and happens only after explicit network/owner gate.
    allowed = (args.allow_public_network is True and
               args.confirm_region_and_personal_research is True and
               os.name == "posix" and os.geteuid() != 0)
    if not allowed:
        from crypto_intelligence_agent.j1_binance_metadata_probe import MetadataProbeReport
        report = MetadataProbeReport("metadata_owner_optin_required")
    else:
        try:
            now_ms = int(time.time() * 1000)
            registry = load_reviewed_registry("expanded-52", as_of_ms=now_ms)
            report = capture_binance_metadata_once(
                registry=registry, allow_public_network=True,
                confirm_region_and_personal_research=True,
                owner_check=lambda: True, fetch=bounded_binance_get,
                utc_ms=lambda: int(time.time() * 1000))
        except Exception:
            from crypto_intelligence_agent.j1_binance_metadata_probe import MetadataProbeReport
            report = MetadataProbeReport("metadata_local_registry_or_config_abstain")
    print(json.dumps(report.sanitized_report(), sort_keys=True,
                     separators=(",", ":"), allow_nan=False))
    return 0 if report.status == "metadata_catalog_pair_research_unverified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
