"""Read-only J1 Top50 pressure from existing marketwide census."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from crypto_intelligence_agent.j1_top50_private_pressure import (
    audit_private_top50_pressure,
)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--directory", required=True, type=Path)
    p.add_argument("--allow-private-readonly-audit", action="store_true")
    p.add_argument("--include-public-symbols", action="store_true")
    a = p.parse_args(argv)
    r = audit_private_top50_pressure(
        a.directory,
        allow_private_readonly_audit=a.allow_private_readonly_audit,
        include_public_symbols=a.include_public_symbols,
    )
    print(json.dumps(r, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
    return 0 if r["status"] == "existing_census_rank_review_queue_unverified" else 2


if __name__ == "__main__":
    raise SystemExit(main())
