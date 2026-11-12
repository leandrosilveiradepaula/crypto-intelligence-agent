"""J1/D309: N50 24h research continuity witness (owner-only, read-only).

No network, symbol output, price, SQL write, scheduled action or trading.
The report is NOT a certification of automatic epoch rotation or 24/7 SLA.
"""
from __future__ import annotations

import argparse
import json

from crypto_intelligence_agent.j1_n50_24h_witness import (
    observe_n50_24h_witness,
)

_NONERROR_UNVERIFIED = frozenset((
    "accumulating_24_closed_hours", "awaiting_verified_writer",
    "closed_24h_pit_evidence_verified",
))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-private-readonly-audit", action="store_true")
    parser.add_argument("--enable-closed24h-witness", action="store_true")
    args = parser.parse_args(argv)
    report = observe_n50_24h_witness(**vars(args))
    print(json.dumps(report, sort_keys=True, ensure_ascii=True,
                     separators=(",", ":")))
    return 0 if report["status"] in _NONERROR_UNVERIFIED else 65


if __name__ == "__main__":
    raise SystemExit(main())
