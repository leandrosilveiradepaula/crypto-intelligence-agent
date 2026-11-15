"""Owner-only CLI: count-only J2 N50 WS shortlist from audited closed candles.

No network, new SQLite reader, websocket, REST or order path. By default,
abstains until BOTH read-only research flags are explicitly supplied.
"""
from __future__ import annotations

import argparse
import json

from crypto_intelligence_agent.j2_n50_ws_descriptive_watchlist import (
    observe_active_ws_n50_descriptive_watchlist,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-private-readonly-research", action="store_true")
    parser.add_argument("--enable-descriptive-watchlist", action="store_true")
    parser.add_argument("--include-private-symbols", action="store_true")
    parser.add_argument("--confirm-private-symbol-output", action="store_true")
    args = parser.parse_args(argv)
    report = observe_active_ws_n50_descriptive_watchlist(
        allow_private_readonly_research=args.allow_private_readonly_research,
        enable_descriptive_watchlist=args.enable_descriptive_watchlist,
        include_private_symbols=args.include_private_symbols,
        confirm_private_symbol_output=args.confirm_private_symbol_output,
    )
    print(json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=True))
    return 0 if report["status"] == "ws_descriptive_watchlist_ready" else 65


if __name__ == "__main__":
    raise SystemExit(main())
