"""Single bounded, read-only public historical trade archive diagnostic.

No V5 API workaround, proxies, redirects, retries, credentials or persistence.
Only explicit one-shot opt-in; no cron/PR/push network calls.
"""
from __future__ import annotations
import argparse
from dataclasses import asdict
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, ProxyHandler, HTTPRedirectHandler, build_opener

from crypto_intelligence_agent.bybit_public_trade_archive import (
    inspect_trade_archive, MAX_GZIP_BYTES,
)

ARCHIVE_NAME = "BTCUSDT2020-03-25.csv.gz"
ARCHIVE_URL = "https://public.bybit.com/trading/BTCUSDT/" + ARCHIVE_NAME


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _open(request, *, timeout):
    return build_opener(ProxyHandler({}), _NoRedirect()).open(request, timeout=timeout)


def probe_archive(*, allow_public_network: bool = False,
                  allow_one_public_archive_probe: bool = False,
                  opened=None) -> dict:
    report = {
        "schema_version": "bybit-archive-one-shot-v1",
        "status": "explicit_opt_in_required",
        "requests_attempted": 0, "data_stored": False,
        "dataset_rights_authorized_for_production": False,
        "canonical_ohlcv_approved": False,
        "historical_top50_approved": False,
        "real_financial_backtest_approved": False,
        "live_trading_authorized": False, "orders_sent": False,
    }
    if allow_public_network is not True or allow_one_public_archive_probe is not True:
        return report
    report["requests_attempted"] = 1
    request = Request(ARCHIVE_URL, method="GET", headers={
        "Accept": "application/octet-stream",
    })
    try:
        with (opened or _open)(request, timeout=10) as response:
            if response.getcode() != 200 or response.geturl() != ARCHIVE_URL:
                report["status"] = "http_or_redirect_rejected_no_retry"
                return report
            data = response.read(MAX_GZIP_BYTES + 1)
        result = inspect_trade_archive(data, archive_name=ARCHIVE_NAME)
        report.update({
            "status": "unverified_historical_trade_schema_observed",
            "archive_date_utc": "2020-03-25",
            "trades": result.trades,
            "observed_hour_count": result.observed_hour_count,
            "first_timestamp_ms": result.first_timestamp_ms,
            "last_timestamp_ms": result.last_timestamp_ms,
            "source_file_sha256": result.gzip_sha256,
        })
    except HTTPError as error:
        report["status"] = (
            "access_restricted_no_retry" if error.code in (401, 403, 418, 429, 451)
            else "http_error_no_retry"
        )
    except Exception:
        # Never disclose URLs, response body, prices, transport trace or paths.
        report["status"] = "archive_unavailable_or_schema_rejected"
    return report


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--allow-public-network", action="store_true")
    p.add_argument("--allow-one-public-archive-probe", action="store_true")
    args = p.parse_args(argv)
    report = probe_archive(
        allow_public_network=args.allow_public_network,
        allow_one_public_archive_probe=args.allow_one_public_archive_probe,
    )
    print(json.dumps(report, separators=(",", ":"), sort_keys=True))
    return 0 if report["status"] == "unverified_historical_trade_schema_observed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
