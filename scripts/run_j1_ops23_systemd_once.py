"""Off-by-default J1 OPS22 single UTC close via existing VPS systemd timer."""
from __future__ import annotations
import argparse
import json
from crypto_intelligence_agent.j1_ops23_once_timer import launch_once

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--target-utc", required=True)
    p.add_argument("--expected-sha", required=True)
    p.add_argument("--repo-root", required=True)
    p.add_argument("--python-bin", required=True)
    p.add_argument("--state-dir", required=True)
    args = p.parse_args(argv)
    result = launch_once(target_utc=args.target_utc, expected_sha=args.expected_sha,
                         repo_root=args.repo_root, python_bin=args.python_bin,
                         state_dir=args.state_dir)
    print(json.dumps(result.sanitized_report(), separators=(",", ":"), sort_keys=True))
    return 0 if result.status == "probe_completed_unverified" else 1

if __name__ == "__main__":
    raise SystemExit(main())
