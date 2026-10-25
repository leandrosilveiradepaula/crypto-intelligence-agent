"""Developer-only CLI for J1 data collection. Defaults to zero-network fixtures."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from pathlib import Path
import json
import sqlite3
import sys
import tempfile
from time import time

from .market_data import (
    BinanceFuturesPublicAdapter, MarketDataError, interval_duration_ms,
)
from .offline_fixtures import OfflineFixtureTransport
from .pipeline import ReadOnlyCollectionPipeline
from .storage import SQLiteMarketDataStore


OFFLINE_CLOCK_MS = 20_000_000
OFFLINE_END_MS = 3 * 3_600_000


def _closed_boundary(now_ms: int, interval: str, safety_ms: int = 1_000) -> int:
    duration = interval_duration_ms(interval)
    anchor = 4 * 86_400_000 if interval == "1w" else 0
    return (now_ms - safety_ms - anchor) // duration * duration + anchor


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="crypto-intelligence-data",
        description="Auditable read-only market-data pipeline. OFFLINE fixture mode is the default.",
    )
    parser.add_argument("--mode", choices=("offline", "live"), default="offline")
    parser.add_argument(
        "--allow-public-network", action="store_true",
        help="Explicit second gate required for public read-only live calls.",
    )
    parser.add_argument("--database", type=Path, help="SQLite file (temporary if omitted)")
    parser.add_argument("--fixture-dir", type=Path, help="Optional offline fixture directory")
    parser.add_argument("--interval", default="1h")
    parser.add_argument("--candles", type=int, default=3)
    parser.add_argument("--max-symbols", type=int, default=2)
    parser.add_argument("--page-size", type=int, default=2)
    parser.add_argument("--min-age-ms", type=int, default=0)
    parser.add_argument("--max-clock-skew-ms", type=int, default=5_000,
                        help="Fail closed if server/local offset plus RTT uncertainty exceeds this limit")
    parser.add_argument("--symbols", default="", help="Comma-separated subset of the ranked eligible universe")
    parser.add_argument("--start-ms", type=int)
    parser.add_argument("--end-ms", type=int)
    args = parser.parse_args(argv)

    if args.mode == "live" and not args.allow_public_network:
        parser.error("live mode requires --allow-public-network; CI must remain offline")
    if args.mode == "offline" and args.allow_public_network:
        parser.error("--allow-public-network is incompatible with offline mode")
    if args.mode == "live" and args.fixture_dir is not None:
        parser.error("--fixture-dir is only valid for offline mode")
    if (args.start_ms is None) != (args.end_ms is None):
        parser.error("--start-ms and --end-ms must be supplied together")
    if (args.candles < 1 or not 1 <= args.max_symbols <= 50 or not 1 <= args.page_size <= 1_500
            or args.min_age_ms < 0 or args.max_clock_skew_ms < 0):
        parser.error("candles must be positive, symbols 1-50, page size 1-1500, minimum age >= 0")

    now = (lambda: OFFLINE_CLOCK_MS) if args.mode == "offline" else (lambda: int(time() * 1000))
    if args.mode == "offline":
        transport = OfflineFixtureTransport(args.fixture_dir)
        source_name = "synthetic_fixture"
    else:
        transport = None  # The built-in adapter only performs public GET requests.
        source_name = "binance_usdm_public"

    observed = now()
    if args.start_ms is None:
        end = OFFLINE_END_MS if args.mode == "offline" else _closed_boundary(observed, args.interval)
        start = end - args.candles * interval_duration_ms(args.interval)
    else:
        start, end = args.start_ms, args.end_ms
    if args.mode == "live" and end > _closed_boundary(observed, args.interval):
        parser.error("requested live range includes a candle not confirmed closed")

    symbols = tuple(x.strip() for x in args.symbols.split(",") if x.strip())
    if len(symbols) != len(set(symbols)):
        parser.error("duplicate symbols are not accepted")

    with ExitStack() as stack:
        if args.database is None:
            directory = Path(stack.enter_context(tempfile.TemporaryDirectory()))
            db_path = directory / "market.sqlite3"
        else:
            db_path = args.database
            if not db_path.parent.exists():
                parser.error("the database parent directory must exist")
        try:
            store = SQLiteMarketDataStore(db_path)
            adapter = BinanceFuturesPublicAdapter(
                transport=transport, clock_ms=now,
                initial_backoff_seconds=0 if args.mode == "offline" else 0.25,
            )
            pipeline = ReadOnlyCollectionPipeline(
                adapter, store, clock_ms=now,
                mode=args.mode, source_name=source_name,
                max_clock_skew_ms=args.max_clock_skew_ms,
            )
            summary = pipeline.run(
                interval=args.interval, start_open_ms=start,
                end_open_ms=end, max_symbols=args.max_symbols,
                page_size=args.page_size, min_onboard_age_ms=args.min_age_ms,
                required_symbols=symbols,
            )
        except (MarketDataError, ValueError, sqlite3.Error, OSError) as exc:
            print(json.dumps({
                "status": "error", "error_type": type(exc).__name__,
                "detail": str(exc), "mode": args.mode,
                "network_enabled": args.mode == "live",
            }, sort_keys=True), file=sys.stderr)
            return 2
        print(json.dumps({
            "status": "success",
            "database": str(db_path) if args.database is not None else "temporary_removed_after_run",
            "audit_events": len(store.collection_events()),
            "data": summary.to_dict(),
            "disclaimer": "Synthetic fixtures are NOT historical market evidence" if args.mode == "offline"
                          else "Public read-only endpoint observations; not proof of full historical coverage",
        }, indent=2, sort_keys=True, ensure_ascii=False))
    return 0
