"""Owner-only, sanitized read of last WS pilot observation; no PID claims."""
from __future__ import annotations

import argparse
import json

from crypto_intelligence_agent.j1_ws_service_health import read_owner_ws_health


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True)
    args = parser.parse_args(argv)
    out = read_owner_ws_health(args.directory)
    print(json.dumps(out, sort_keys=True, separators=(",", ":")))
    # This is report accessibility, not a live service or trading readiness gate.
    return 0 if out["status"] == "health_recent_unverified" else 1


if __name__ == "__main__":
    raise SystemExit(main())