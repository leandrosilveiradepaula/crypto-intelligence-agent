"""OPS33 one-shot Binance finite shadow runner, OFF by default."""
from __future__ import annotations

import argparse
import json

from crypto_intelligence_agent.j1_ops33_binance_timer import launch_binance_once


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("target-utc", "expected-sha", "repo-root",
                 "python-bin", "state-dir"):
        p.add_argument("--" + name, required=True)
    report = launch_binance_once(**vars(p.parse_args(argv)))
    print(json.dumps(report.sanitized_report(), sort_keys=True,
                     separators=(",", ":"), allow_nan=False))
    return 0 if report.status == "ops33_shadow_observed_unverified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
