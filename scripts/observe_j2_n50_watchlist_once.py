"""J2/D308 owner-only N50 watchlist: no trade, writes or network.

The CLI is OFF without both read-only and watchlist flags. Per-symbol
display additionally requires two distinct explicit privacy flags.
"""
from __future__ import annotations

import argparse
import json

from crypto_intelligence_agent.j2_n50_descriptive_watchlist import (
    observe_private_n50_watchlist,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-private-readonly-audit", action="store_true")
    parser.add_argument("--enable-descriptive-watchlist", action="store_true")
    parser.add_argument("--include-private-symbols", action="store_true")
    parser.add_argument("--confirm-private-symbol-output", action="store_true")
    options = vars(parser.parse_args(argv))
    result = observe_private_n50_watchlist(**options)
    print(json.dumps(result, sort_keys=True, ensure_ascii=True,
                     separators=(",", ":")))
    return 0 if result["status"] == "descriptive_watchlist_ready" else 65


if __name__ == "__main__":
    raise SystemExit(main())
