"""J1 #245: owner-only offline read of an existing unverified Bybit SQLite DB."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import stat

from crypto_intelligence_agent.bybit_research_series import inspect_existing_bybit_research_series
from crypto_intelligence_agent.private_kraken_research import _private_db_path


def inspect_private_research(
    *, database: str, symbol: str, start_open_ms: int, end_open_ms: int,
    as_of_ms: int, allow_private_readonly_research: bool = False,
) -> dict[str, object]:
    if allow_private_readonly_research is not True or os.name != "posix":
        raise ValueError("explicit_private_posix_research_required")
    path = _private_db_path(database)
    if (not path.exists() or path.is_symlink() or not path.is_file()
            or path.stat().st_nlink != 1
            or stat.S_IMODE(path.stat().st_mode) & 0o077):
        raise ValueError("unsafe_private_existing_database")
    series = inspect_existing_bybit_research_series(
        path, symbol=symbol, interval="1h", start_open_ms=start_open_ms,
        end_open_ms=end_open_ms, as_of_ms=as_of_ms,
    )
    return {
        "schema_version": "bybit-private-series-inspection-v1",
        "status": "unverified_research_series_inspected",
        "page_count": series.page_count,
        "candle_count": len(series.candles),
        "start_open_ms": series.start_open_ms,
        "end_open_ms": series.end_open_ms,
        "header_digest_sha256": series.header_digest_sha256,
        "source_authenticated": False, "rights_authorized": False,
        "canonical_ohlcv_approved": False, "historical_top50_approved": False,
        "financial_backtest_approved": False, "live_trading_authorized": False,
        "orders_sent": False, "network_requests": 0, "data_stored": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--start-open-ms", type=int, required=True)
    parser.add_argument("--end-open-ms", type=int, required=True)
    parser.add_argument("--as-of-ms", type=int, required=True)
    parser.add_argument("--allow-private-readonly-research", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = inspect_private_research(
            database=args.database, symbol=args.symbol,
            start_open_ms=args.start_open_ms, end_open_ms=args.end_open_ms,
            as_of_ms=args.as_of_ms,
            allow_private_readonly_research=args.allow_private_readonly_research,
        )
    except Exception:
        report = {
            "schema_version": "bybit-private-series-inspection-v1",
            "status": "private_research_inspection_rejected",
            "rights_authorized": False, "canonical_ohlcv_approved": False,
            "financial_backtest_approved": False, "live_trading_authorized": False,
            "orders_sent": False, "network_requests": 0, "data_stored": False,
        }
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if report["status"] == "unverified_research_series_inspected" else 1


if __name__ == "__main__":
    raise SystemExit(main())
