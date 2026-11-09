"""One-shot J1 research-only hourly REST collector. Default network OFF."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from crypto_intelligence_agent.j1_rest_incremental_owner import run_hourly_once


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--frozen-directory", required=True, type=Path)
    p.add_argument("--output-directory", required=True, type=Path)
    p.add_argument("--max-assets", type=int, default=2)
    p.add_argument("--allow-public-network", action="store_true")
    p.add_argument("--allow-private-storage", action="store_true")
    p.add_argument("--confirm-region-and-personal-research", action="store_true")
    args = p.parse_args(argv)
    report = run_hourly_once(
        frozen_directory=args.frozen_directory,
        output_directory=args.output_directory,
        max_assets=args.max_assets,
        allow_public_network=args.allow_public_network,
        allow_private_storage=args.allow_private_storage,
        confirm_region_and_personal_research=args.confirm_region_and_personal_research,
    )
    print(json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=True))
    if report["status"] == "research_sample_closed_hour_persisted":
        return 0
    if report["status"] in (
        "research_provider_fail_stop", "halted_owner_review_required",
        "research_integrity_or_environment_abstain",
    ):
        return 65
    return 64


if __name__ == "__main__":
    raise SystemExit(main())
