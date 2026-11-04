"""OPS31: one absolute-UTC owner-only VPS shadow observation, OFF by default."""
from __future__ import annotations

import argparse
import json

from crypto_intelligence_agent.j1_ops31_shadow_timer import launch_shadow_once


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--target-utc", required=True)
    p.add_argument("--expected-sha", required=True)
    p.add_argument("--repo-root", required=True)
    p.add_argument("--python-bin", required=True)
    p.add_argument("--state-dir", required=True)
    args = p.parse_args(argv)
    report = launch_shadow_once(**vars(args))
    print(json.dumps(report.sanitized_report(), sort_keys=True,
                     separators=(",", ":"), allow_nan=False))
    return 0 if report.status in (
        "shadow_observed_quarantined", "shadow_no_close_unverified",
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
