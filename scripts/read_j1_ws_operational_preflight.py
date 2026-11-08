"""J1/D267 single read-only owner WS operational preflight CLI.

Only the named existing systemd unit, local owner journal and private
health observation. No WS/REST/network trade, writes, deploy or restart.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from crypto_intelligence_agent.j1_ws_operational_preflight import (
    observe_ws_operational_preflight,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--allow-private-readonly-preflight", action="store_true")
    args = parser.parse_args(argv)
    result = observe_ws_operational_preflight(
        directory=args.directory,
        allow_private_readonly_preflight=args.allow_private_readonly_preflight,
    )
    print(json.dumps(result, ensure_ascii=True,
                     sort_keys=True, separators=(",", ":")))
    return 0 if result["status"] == "read_only_operational_diagnostic" else 2


if __name__ == "__main__":
    raise SystemExit(main())
