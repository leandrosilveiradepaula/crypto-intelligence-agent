"""Await one bounded UTC-close window, without network, storage or orders."""
from __future__ import annotations

import argparse
import json

from crypto_intelligence_agent.j1_ws_utc_close_probe import await_close_window
from crypto_intelligence_agent.market_data import DataValidationError


def main(argv=None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    try:
        start_utc_ms = await_close_window()
    except (DataValidationError, OSError, ValueError, TypeError, OverflowError):
        print(json.dumps({
            "status": "utc_close_window_abstain", "network_requests": 0,
            "orders_sent": False,
        }, sort_keys=True, separators=(",", ":")))
        return 1
    print(json.dumps({
        "status": "utc_close_window_ready",
        "planned_start_utc_ms": start_utc_ms,
        "network_requests": 0, "orders_sent": False,
    }, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
