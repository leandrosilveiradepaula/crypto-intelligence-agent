"""Read-only readiness of the existing J1 research REST SQLite journal.

Never issues HTTP, starts a timer or mutates SQLite. This report is not
an operational authorization for continuous collection or for trading.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

from crypto_intelligence_agent.j1_rest_resume_readiness import (
    audit_existing_rest_resume,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-directory", required=True, type=Path)
    parser.add_argument("--allow-private-readonly-audit", action="store_true")
    parser.add_argument("--now-ms", type=int, default=None)
    args = parser.parse_args(argv)
    report = audit_existing_rest_resume(
        output_directory=args.output_directory,
        now_ms=(time.time_ns() // 1_000_000 if args.now_ms is None else args.now_ms),
        allow_private_readonly_audit=args.allow_private_readonly_audit,
    )
    print(json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=True))
    return 0 if report["journal_integrity_verified"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
