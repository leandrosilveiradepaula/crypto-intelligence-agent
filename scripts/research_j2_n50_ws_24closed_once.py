"""Owner-only CLI for the existing private N50 WS descriptive 24h reader.

No exchange requests, no database writer, no automatic scheduler or orders.
The CLI never prints private symbols; even a successful output is not D323.
"""
from __future__ import annotations

import argparse
import json

from crypto_intelligence_agent.j2_n50_ws_private_screen import (
    observe_active_private_ws_n50_24closed,
)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--allow-private-readonly-research", action="store_true")
    args = p.parse_args(argv)
    # The owner is required in the imported function. CLI deliberately has
    # no symbols flag and prints only the sanitized aggregate report.
    report = observe_active_private_ws_n50_24closed(
        allow_private_readonly_research=args.allow_private_readonly_research,
        include_private_symbols=False,
    )
    print(json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=True))
    return 0 if report["status"] == "ws_n50_descriptive_24h_ready" else 65


if __name__ == "__main__":
    raise SystemExit(main())
