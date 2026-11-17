"""Run an entirely offline 50+position, two-epoch public ticker coverage proof.

All market frames and clocks are fixtures. No networking, REST,
service startup, credentials, account, J1 journal or financial orders.
"""
from __future__ import annotations

import json

from crypto_intelligence_agent.bybit_public_ticker_coverage_d396 import (
    TickerUniverseEpoch, run_finite_public_ticker_coverage_pilot,
)
from crypto_intelligence_agent.bybit_public_ticker_supervisor_d386 import TickerLeaseBudget

T = 1_800_000_000_000
FIRST = tuple(f"A{i:02d}USDT" for i in range(50))
SECOND = tuple(f"A{i:02d}USDT" for i in range(1, 51))
HELD = ("A00USDT", "HOLDUSDT")


class OfflineClock:
    def __init__(self):
        self.seconds = 0.0
        self.utc_ms = T

    def mono(self):
        return self.seconds

    def wall(self):
        return self.utc_ms

    def sleep(self, seconds):
        self.seconds += seconds
        self.utc_ms += round(seconds * 1000)


class OfflineSession:
    def __init__(self, clock, symbols):
        self.clock = clock
        now = clock.wall()
        self.responses = [json.dumps({
            "success": True, "ret_msg": "subscribe",
            "conn_id": "fixture", "op": "subscribe",
            "req_id": "cia-ticker-1",
        })]
        for sym in sorted(symbols):
            self.responses.append(json.dumps({
                "topic": "tickers." + sym,
                "type": "snapshot", "ts": now - 50, "cs": 1,
                "data": {
                    "symbol": sym, "lastPrice": "100", "markPrice": "100",
                    "indexPrice": "100", "bid1Price": "99.9",
                    "ask1Price": "100.1", "bid1Size": "3",
                    "ask1Size": "4",
                },
            }, separators=(",", ":")))
        self.closed = False

    def send(self, raw):
        payload = json.loads(raw)
        if payload.get("op") not in ("subscribe", "ping"):
            raise AssertionError("offline proof cannot submit any action")

    def recv(self, timeout):
        if self.responses:
            return self.responses.pop(0)
        self.clock.sleep(timeout)
        raise TimeoutError()

    def close(self):
        self.closed = True


def run_demo() -> dict:
    clock = OfflineClock()
    epochs = (
        TickerUniverseEpoch(FIRST, HELD, T - 1000),
        TickerUniverseEpoch(SECOND, HELD, T + 1000),
    )
    factories = tuple(
        (lambda symbols=epoch.monitored: OfflineSession(clock, symbols))
        for epoch in epochs
    )
    report = run_finite_public_ticker_coverage_pilot(
        epochs=epochs,
        session_factories=factories,
        budget=TickerLeaseBudget(max_sessions=1, max_frames=256, max_seconds=3),
        clock=clock.mono, wall_ms=clock.wall, sleeper=clock.sleep,
    )
    if not report.all_observed_coverage:
        raise RuntimeError("offline market coverage fixture did not pass")
    return report.sanitized_report()


def main() -> int:
    print(json.dumps(run_demo(), sort_keys=True, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
