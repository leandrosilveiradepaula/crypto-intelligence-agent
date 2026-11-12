"""Explicit owner-only, opt-in ONE-hour N50 writer; NO timers are installed."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from crypto_intelligence_agent.j1_n50_supervised_once import run_supervised_n50_once


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest-directory", type=Path, required=True)
    p.add_argument("--output-directory", type=Path, required=True)
    p.add_argument("--allow-private-manifest-read", action="store_true")
    p.add_argument("--allow-private-readonly-audit", action="store_true")
    p.add_argument("--allow-public-network", action="store_true")
    p.add_argument("--allow-private-storage", action="store_true")
    p.add_argument("--confirm-region-and-personal-research", action="store_true")
    p.add_argument("--enable-n50-research-once", action="store_true")
    opts = vars(p.parse_args(argv))
    result = run_supervised_n50_once(**opts)
    print(json.dumps(result, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=True))
    return 0 if result["status"] in ("research_hour_persisted", "deferred") else 65


if __name__ == "__main__":
    raise SystemExit(main())
