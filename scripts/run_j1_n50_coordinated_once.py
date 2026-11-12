"""D293: one explicit N50 action under a global owner-only UTC lease.

Never installs systemd or performs recurring operations. Capture and writer
are mutually exclusive for each observed UTC close.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from crypto_intelligence_agent.j1_n50_global_lease import coordinated_n50_once


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("capture_seal","hourly_writer"))
    p.add_argument("--lock-directory", type=Path, required=True)
    p.add_argument("--manifest-directory", type=Path, required=True)
    p.add_argument("--output-directory", type=Path)
    p.add_argument("--allow-public-network", action="store_true")
    p.add_argument("--allow-private-storage", action="store_true")
    p.add_argument("--allow-private-manifest-read", action="store_true")
    p.add_argument("--allow-private-readonly-audit", action="store_true")
    p.add_argument("--allow-private-manifest-write", action="store_true")
    p.add_argument("--confirm-region-and-personal-research", action="store_true")
    p.add_argument("--enable-coordinated-n50-once", action="store_true")
    result=coordinated_n50_once(**vars(p.parse_args(argv)))
    print(json.dumps(result, ensure_ascii=True, sort_keys=True,
                     separators=(",",":")))
    return 0 if result["status"] in (
        "capture_sealed", "research_hour_persisted", "deferred"
    ) else 65


if __name__=="__main__":
    raise SystemExit(main())
