"""Offline-only J1 local SQLite health check; no collector, network or orders.

Exit 0: local PIT sample has 24 structural closed hourly candles and checkpoints.
Exit 2: absence, staleness, corruption or any other non-healthy state.
Neither code proves marketwide Top50 nor a continuous worker is running.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from crypto_intelligence_agent.j1_local_health import (  # noqa: E402
    HOUR_MS, audit_local_sqlite_health,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True,
                        help="Existing local SQLite database; never created or modified")
    parser.add_argument("--exchange", required=True,
                        help="Exact exchange identifier used by existing candle rows")
    parser.add_argument("--market", default="linear_perpetual")
    parser.add_argument("--snapshot-source", default=None)
    parser.add_argument("--selection-rule-version", default=None)
    parser.add_argument("--decision-at-ms", type=int, default=None,
                        help="Optional UTC-ms for reproducible offline audit")
    parser.add_argument("--max-snapshot-age-hours", type=int, default=2)
    args = parser.parse_args(argv)
    now_ms = time.time_ns() // 1_000_000 if args.decision_at_ms is None else args.decision_at_ms
    if os.name == "posix" and os.geteuid() == 0:
        report = {"schema_version": "j1_local_health_v1", "status": "nonroot_required",
                  "marketwide_top50_verified": False, "orders_sent": False}
    else:
        try:
            report = audit_local_sqlite_health(
                db_path=args.db, decision_at_ms=now_ms, exchange=args.exchange,
                market=args.market, snapshot_source=args.snapshot_source,
                selection_rule_version=args.selection_rule_version,
                max_snapshot_age_ms=args.max_snapshot_age_hours * HOUR_MS,
            )
        except (ValueError, TypeError, OverflowError):
            report = {"schema_version": "j1_local_health_v1", "status": "config_invalid",
                      "marketwide_top50_verified": False, "orders_sent": False}
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if report["status"] == "sample_window_complete_unverified" else 2


if __name__ == "__main__":
    raise SystemExit(main())
