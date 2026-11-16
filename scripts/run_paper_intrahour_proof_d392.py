"""D392 executable CLI: synthetic PAPER only, zero API or network calls."""
from __future__ import annotations

import argparse
import json

from crypto_intelligence_agent.paper_intrahour_proof_d392 import (
    demonstrate_paper_intrahour_cycle,
)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Reproduce a synthetic Bybit-shaped PAPER intrahour cycle."
    )
    p.add_argument(
        "--side", choices=("LONG", "SHORT"), default="LONG",
    )
    p.add_argument(
        "--scenario",
        choices=("two_targets_then_stop", "unknown_blocks_stop"),
        default="two_targets_then_stop",
    )
    args = p.parse_args(argv)
    report = demonstrate_paper_intrahour_cycle(
        scenario=args.scenario, side=args.side,
    )
    print(json.dumps(report, sort_keys=True, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
