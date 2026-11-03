"""One-shot owner-only WS x REST corroboration (same venue; never storage)."""
from __future__ import annotations

import argparse
import json

from crypto_intelligence_agent.j1_ws_rest_one_candle_probe import owner_compare_one_candle


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--allow-public-network", action="store_true")
    p.add_argument("--allow-public-websocket", action="store_true")
    p.add_argument("--allow-one-public-rest-get", action="store_true")
    p.add_argument("--confirm-region-and-personal-research", action="store_true")
    args = p.parse_args(argv)
    report = owner_compare_one_candle(
        allow_public_network=args.allow_public_network,
        allow_public_websocket=args.allow_public_websocket,
        allow_one_public_rest_get=args.allow_one_public_rest_get,
        confirm_region_and_personal_research=args.confirm_region_and_personal_research,
    )
    print(json.dumps(report.sanitized_report(), sort_keys=True, separators=(",", ":")))
    # 6/6 is an observational match, NEVER source authentication or approval.
    return 0 if report.status == "ws_rest_match_unverified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
