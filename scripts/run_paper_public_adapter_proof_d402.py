"""Run one complete offline Bybit-shaped ticker -> PAPER journal demonstration."""
from __future__ import annotations

import argparse
import json

from crypto_intelligence_agent.paper_public_adapter_proof_d402 import (
    demonstrate_adapter_to_paper_cycle,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Exercise the full public ticker adapter and PAPER positions without network."
    )
    parser.add_argument("--scenario", choices=("closed", "unknown"),
                        default="closed")
    parser.add_argument("--mobile-snapshot", action="store_true",
                        help="Include read-only AUTO4 position JSON for mobile J5 import")
    args = parser.parse_args(argv)
    print(json.dumps(
        demonstrate_adapter_to_paper_cycle(
            scenario=args.scenario, include_mobile_snapshot=args.mobile_snapshot,
        ),
        ensure_ascii=True, sort_keys=True,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
