"""One-shot 52-topic public LINEAR WS protocol proof. No REST or storage.

Explicit non-root opt-in only. Prints aggregate protocol evidence without
symbols, market values, provider payloads, file paths or credentials.
"""
from __future__ import annotations

import argparse
import json

from crypto_intelligence_agent.bybit_ws_linear_live_probe import owner_probe_linear_topics_once


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--allow-public-network", action="store_true")
    p.add_argument("--allow-public-websocket", action="store_true")
    p.add_argument("--confirm-region-and-personal-research", action="store_true")
    p.add_argument("--seconds", type=int, default=35)
    p.add_argument("--max-frames", type=int, default=512)
    args = p.parse_args(argv)
    report = owner_probe_linear_topics_once(
        allow_public_network=args.allow_public_network,
        allow_public_websocket=args.allow_public_websocket,
        confirm_region_and_personal_research=args.confirm_region_and_personal_research,
        seconds=args.seconds, max_frames=args.max_frames)
    print(json.dumps(report.sanitized_report(), sort_keys=True, separators=(",", ":")))
    return 0 if report.status in ("ws_ack_only_unverified",
                                  "ws_ack_with_market_frames_unverified") else 1


if __name__ == "__main__":
    raise SystemExit(main())