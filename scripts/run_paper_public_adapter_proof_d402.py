"""One complete offline Bybit-shaped ticker -> PAPER journal demonstration.

The optional --mobile-output writes a new private, directly importable J5
PAPER JSON report. No real quotes, account data, orders or persistent service.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

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
                        help="Include read-only AUTO4 position JSON in CLI report")
    parser.add_argument("--mobile-output", type=Path,
                        help="Create NEW private directly importable PAPER J5 JSON")
    args = parser.parse_args(argv)
    output = args.mobile_output
    if output is not None and (
        not output.is_absolute() or output.is_symlink()
    ):
        print("D409: destino de exportacao PAPER invalido.", file=sys.stderr)
        return 65
    report = demonstrate_adapter_to_paper_cycle(
        scenario=args.scenario,
        include_mobile_snapshot=args.mobile_snapshot or output is not None,
    )
    if output is not None:
        mobile = report.pop("mobile_snapshot")
        wire = json.dumps(mobile, sort_keys=True, ensure_ascii=True,
                          allow_nan=False, separators=(",", ":")) + "\n"
        try:
            fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                         | getattr(os, "O_NOFOLLOW", 0), 0o600)
            with os.fdopen(fd, "w", encoding="ascii") as stream:
                stream.write(wire)
        except OSError:
            print("D409: destino de exportacao PAPER indisponivel.", file=sys.stderr)
            return 65
    print(json.dumps(report, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
