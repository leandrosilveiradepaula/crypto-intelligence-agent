"""Owner-only, one finite Bybit public kline WebSocket read; no data storage."""
from __future__ import annotations
import argparse
import json
from crypto_intelligence_agent.bybit_public_ws_once import owner_probe

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-public-websocket", action="store_true")
    parser.add_argument("--confirm-region-and-personal-research", action="store_true")
    parser.add_argument("--schedule-closed-utc-hour", action="store_true")
    args = parser.parse_args(argv)
    report = owner_probe(allow_public_websocket=args.allow_public_websocket,
                         confirm_region_and_personal_research=args.confirm_region_and_personal_research,
                         schedule_closed_utc_hour=args.schedule_closed_utc_hour)
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if report["status"] == "ws_one_closed_hour_observed_only" else 1

if __name__ == "__main__": raise SystemExit(main())
