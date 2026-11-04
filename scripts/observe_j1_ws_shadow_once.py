"""OPS30: explicit owner-only finite public WS shadow; off by default.

No REST, SQLite, trades, state file, daemon, timer or background loop.
"""
from __future__ import annotations

import argparse
import json
import os
from typing import Callable

from crypto_intelligence_agent.j1_ws_shadow_observer import observe_shadow_once, ShadowWSReport

DEFAULT_TOPICS = ("kline.60.BTCUSDT", "kline.60.ETHUSDT")


def run_owner_shadow(
    *, allow_public_network: bool = False,
    allow_public_websocket: bool = False,
    confirm_region_and_personal_research: bool = False,
    topics: tuple[str, ...] = DEFAULT_TOPICS,
    seconds: int = 90,
    frames: int = 256,
    owner_check: Callable[[], bool] | None = None,
    session_factory=None,
    clock=None, wall_ms=None,
) -> ShadowWSReport:
    if (allow_public_network is not True
            or allow_public_websocket is not True
            or confirm_region_and_personal_research is not True):
        return ShadowWSReport("shadow_owner_optin_required")
    if owner_check is None:
        owner_check = lambda: os.name == "posix" and os.geteuid() != 0
    if not owner_check():
        return ShadowWSReport("shadow_nonroot_required")
    if session_factory is None:
        from crypto_intelligence_agent.bybit_public_ws_once import _real_session_factory
        session_factory = _real_session_factory
    options = dict(session_factory=session_factory, topics=topics,
                   max_seconds=seconds, max_frames=frames)
    if clock is not None:
        options["clock"] = clock
    if wall_ms is not None:
        options["wall_ms"] = wall_ms
    return observe_shadow_once(**options)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-public-network", action="store_true")
    parser.add_argument("--allow-public-websocket", action="store_true")
    parser.add_argument("--confirm-region-and-personal-research", action="store_true")
    parser.add_argument("--topic", action="append")
    parser.add_argument("--seconds", type=int, default=90)
    parser.add_argument("--frames", type=int, default=256)
    args = parser.parse_args(argv)
    topics = tuple(args.topic) if args.topic is not None else DEFAULT_TOPICS
    report = run_owner_shadow(
        allow_public_network=args.allow_public_network,
        allow_public_websocket=args.allow_public_websocket,
        confirm_region_and_personal_research=args.confirm_region_and_personal_research,
        topics=topics, seconds=args.seconds, frames=args.frames)
    print(json.dumps(report.sanitized_report(), sort_keys=True,
                     separators=(",", ":"), allow_nan=False))
    return 0 if report.status in (
        "shadow_closes_observed_quarantined",
        "shadow_no_closed_candle_unverified",
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
