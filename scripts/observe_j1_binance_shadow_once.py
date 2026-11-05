"""Owner-only finite Binance USD-M shadow; no network without explicit opt-ins."""
from __future__ import annotations

import argparse
import json
import os
from typing import Callable

from crypto_intelligence_agent.j1_binance_ws_shadow_observer import (
    BinanceShadowReport, URL, observe_binance_shadow_once,
)


def _real_binance_session_factory():
    # Lazy import: default CLI and tests cannot open a socket.
    from websockets.sync.client import connect
    from websockets.exceptions import ConnectionClosed
    connection = connect(URL, open_timeout=5, close_timeout=2,
                         compression=None, max_size=16384, proxy=None)

    class Adapter:
        def send(self, payload):
            connection.send(payload)

        def recv(self, timeout):
            try:
                return connection.recv(timeout=timeout)
            except ConnectionClosed:
                raise OSError("binance socket closed") from None

        def close(self):
            connection.close()

    return Adapter()


def run_owner_binance_shadow(
    *, allow_public_network: bool = False,
    allow_public_websocket: bool = False,
    confirm_region_and_personal_research: bool = False,
    seconds: int = 180, frames: int = 1024,
    owner_check: Callable[[], bool] | None = None,
    session_factory=None, clock=None, wall_ms=None,
) -> BinanceShadowReport:
    if (allow_public_network is not True
            or allow_public_websocket is not True
            or confirm_region_and_personal_research is not True):
        return BinanceShadowReport("binance_owner_optin_required")
    if owner_check is None:
        owner_check = lambda: os.name == "posix" and os.geteuid() != 0
    if not owner_check():
        return BinanceShadowReport("binance_nonroot_required")
    if session_factory is None:
        session_factory = _real_binance_session_factory
    kwargs = dict(session_factory=session_factory,
                  max_seconds=seconds, max_frames=frames)
    if clock is not None:
        kwargs["clock"] = clock
    if wall_ms is not None:
        kwargs["wall_ms"] = wall_ms
    return observe_binance_shadow_once(**kwargs)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--allow-public-network", action="store_true")
    p.add_argument("--allow-public-websocket", action="store_true")
    p.add_argument("--confirm-region-and-personal-research", action="store_true")
    p.add_argument("--seconds", type=int, default=180)
    p.add_argument("--frames", type=int, default=1024)
    args = p.parse_args(argv)
    report = run_owner_binance_shadow(**vars(args))
    print(json.dumps(report.sanitized_report(), sort_keys=True,
                     separators=(",", ":"), allow_nan=False))
    return 0 if report.status == "binance_closes_observed_unverified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
