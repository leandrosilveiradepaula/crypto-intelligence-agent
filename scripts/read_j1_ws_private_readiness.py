"""Read one private WS readiness report. Never starts a collector or opens network."""
from __future__ import annotations

import argparse
import json

from crypto_intelligence_agent.j1_ws_private_readiness import read_private_ws_readiness


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True)
    args = parser.parse_args(argv)
    report = read_private_ws_readiness(args.directory)
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if report["status"] == "ws_private_sample_complete_not_live" else 1


if __name__ == "__main__":
    raise SystemExit(main())
