"""D294: opt-in one-hour N50 managed epoch tick, OFF until operational gate.

With a pre-created owner-only 0700 root containing lease/ and epochs/,
choose exactly one: current 50-candidate capture+new epoch or incremental M1.
Never installs/starts timers, invokes an exchange's private API, or trades.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from crypto_intelligence_agent.j1_n50_managed_cycle import managed_n50_tick_once


def main(argv: list[str] | None = None) -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root-directory",type=Path,required=True)
    p.add_argument("--allow-public-network",action="store_true")
    p.add_argument("--allow-private-storage",action="store_true")
    p.add_argument("--allow-private-manifest-read",action="store_true")
    p.add_argument("--allow-private-readonly-audit",action="store_true")
    p.add_argument("--allow-private-manifest-write",action="store_true")
    p.add_argument("--confirm-region-and-personal-research",action="store_true")
    p.add_argument("--enable-managed-n50-tick",action="store_true")
    result=managed_n50_tick_once(**vars(p.parse_args(argv)))
    print(json.dumps(result,sort_keys=True,separators=(",",":"),ensure_ascii=True))
    return 0 if result["status"] in (
        "epoch_started","epoch_rotated","research_hour_persisted","deferred",
    ) else 65


if __name__=="__main__":
    raise SystemExit(main())
