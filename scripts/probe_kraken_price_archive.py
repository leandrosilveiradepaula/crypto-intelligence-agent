"""One-shot PRIVATE Kraken Futures BTC price-only SQLite research conformance.

At most ONE public GET, no credentials, no trading, no retries or redirects.
The runner's SQLite file is temporary and destroyed before the summary prints.
All financial values stay off logs. No canonical OHLCV or rights are granted.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from time import time
from typing import Any, Callable

from crypto_intelligence_agent.kraken_price_archive import SQLiteKrakenPriceOnlyArchive
from crypto_intelligence_agent.kraken_public_readonly import KrakenPublicReadOnlyResearch
from crypto_intelligence_agent.market_data import (
    DataGapError, DataTimeoutError, DataValidationError,
    ExchangeAccessError, HttpResponseError,
)

HOUR_MS = 3_600_000
SYMBOL = "PF_XBTUSD"


class PriceProbeError(ValueError):
    pass


def inspect_once(
    *, allow_public_network: bool, allow_private_kraken_prices: bool,
    client: Any | None = None, clock_ms: Callable[[], int] | None = None,
) -> dict[str, Any]:
    if allow_public_network is not True or allow_private_kraken_prices is not True:
        raise PriceProbeError("double_opt_in_required")
    clock = clock_ms or (lambda: int(time() * 1000))
    now = clock()
    if type(now) is not int or not 10 * HOUR_MS < now < 253_402_300_799_999:
        raise PriceProbeError("invalid_utc_clock")
    top = (now // HOUR_MS) * HOUR_MS
    start, end = top - 4 * HOUR_MS, top - HOUR_MS
    report = {
        "schema_version": "j1-kraken-private-price-archive-v1",
        "provider": "kraken_futures",
        "symbol": SYMBOL, "interval": "1h",
        "observed_at_utc": datetime.fromtimestamp(now / 1000, timezone.utc)
            .isoformat(timespec="seconds"),
        "requested_start_ms": start, "requested_end_ms_exclusive": end,
        "requests_attempted": 0, "credentials_used": False,
        "orders_sent": False, "raw_responses_persisted": False,
        "retained_market_data_after_run": False,
        "market_data_published": False, "canonical_ohlcv_approved": False,
        "crypto_universe_approved": False, "volume_unit_verified": False,
        "commercial_or_public_rights_verified": False,
        "ready_for_live_top50": False, "ready_for_trading": False,
    }
    reader = client or KrakenPublicReadOnlyResearch(
        allow_public_network=True, timeout_seconds=8.0,
        close_safety_ms=1_000,
    )
    try:
        # A real one-shot chart GET; no instruments/tickers, no market eligibility
        # assertion. The real BTC identity seed alone does not validate listings.
        report["requests_attempted"] = 1
        captured = reader.staged_closed_candles(
            symbol=SYMBOL, interval="1h",
            start_open_ms=start, end_open_ms=end,
        )
        with TemporaryDirectory() as directory:
            path = Path(directory) / "private_kraken_research.sqlite"
            archive = SQLiteKrakenPriceOnlyArchive(path)
            saved = archive.commit_price_only(captured)
            quality = archive.price_quality(
                symbol=SYMBOL, interval="1h", start_open_ms=start,
                end_open_ms=end, as_of_ms=captured.observed_at_ms,
            )
            if not quality.complete or saved != 3:
                raise PriceProbeError("price_only_coverage_incomplete")
            if archive.candles(
                exchange="kraken_futures", market="linear_perpetual",
                symbol=SYMBOL, interval="1h",
                start_open_ms=start, end_open_ms=end,
            ):
                raise PriceProbeError("canonical_table_contaminated")
            report["closed_prices_stored_ephemerally"] = saved
            report["price_only_coverage"] = "complete"
            report["research_schema_only"] = True
        report["status"] = "private_price_only_archive_validated"
    except ExchangeAccessError:
        report["status"] = "access_restricted_no_retry"
    except (DataGapError, DataValidationError):
        report["status"] = "invalid_chart_or_price_only_page"
    except DataTimeoutError:
        report["status"] = "network_timeout_no_retry"
    except HttpResponseError:
        report["status"] = "public_chart_http_failure"
    except PriceProbeError as error:
        report["status"] = str(error)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-public-network", action="store_true")
    parser.add_argument("--allow-private-kraken-prices", action="store_true")
    args = parser.parse_args()
    try:
        result = inspect_once(
            allow_public_network=args.allow_public_network,
            allow_private_kraken_prices=args.allow_private_kraken_prices,
        )
    except PriceProbeError as error:
        result = {"status": str(error), "requests_attempted": 0,
                  "orders_sent": False, "raw_responses_persisted": False}
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["status"] == "private_price_only_archive_validated" else 1


if __name__ == "__main__":
    raise SystemExit(main())
