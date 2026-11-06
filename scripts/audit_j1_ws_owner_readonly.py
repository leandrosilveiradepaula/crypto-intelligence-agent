"""Inspect existing private J1 WS research journal without network or writes.

Zero is only structural, local 24h completeness of a reviewed *sample*.
It is never evidence of running collector, authenticated venue, or global Top50.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from crypto_intelligence_agent.j1_ws_owner_readonly import audit_owner_ws_journal

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--decision-at-ms", required=True, type=int)
    parser.add_argument("--observed-at-ms", required=True, type=int)
    parser.add_argument("--allow-private-readonly-audit", action="store_true")
    args = parser.parse_args(argv)
    report = audit_owner_ws_journal(
        directory=args.directory, decision_at_ms=args.decision_at_ms,
        observed_at_ms=args.observed_at_ms,
        allow_private_readonly_audit=args.allow_private_readonly_audit,
    )
    print(json.dumps(report, separators=(",", ":"), sort_keys=True))
    return 0 if report["status"] == "reviewed_ws_sample_complete_unverified" else 2

if __name__ == "__main__":
    raise SystemExit(main())
