"""Read-only local PAPER recovery diagnostic (never an OPEN authorization).

Usage: python -m scripts.inspect_paper_recovery --orders /private/orders.sqlite --positions /private/positions.sqlite
No network, writes, account identifiers, prices, payloads or exchange credentials.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from crypto_intelligence_agent.paper_recovery_status import (
    PaperRecoveryState, inspect_local_paper_recovery_status,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Diagnostico local PAPER (sem ordens)")
    parser.add_argument("--orders", type=Path, required=True)
    parser.add_argument("--positions", type=Path, required=True)
    args = parser.parse_args(argv)
    status = inspect_local_paper_recovery_status(args.orders, args.positions)
    print(json.dumps({
        "mode": "offline_paper",
        "state": status.state.value,
        "reason": status.reason,
        "cross_database_atomic_snapshot_available": False,
        "native_stop_verified": False,
        "new_open_authorized": False,
        "orders_sent": False,
        "live_trading_authorized": False,
    }, sort_keys=True))
    return 0 if status.state is PaperRecoveryState.PAPER_FLAT_HYPOTHETICAL_ONLY else 2


if __name__ == "__main__":
    raise SystemExit(main())
