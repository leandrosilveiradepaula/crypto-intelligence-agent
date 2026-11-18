"""Run D436's deterministic end-to-end replay without JSON imports or network.

The command creates an isolated SQLite journal, feeds 24 confirmed historical
closes plus a new confirmed close, and prints the updated research projection.
It is a reproducible protocol replay, not a live observation or trade demo.
"""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from crypto_intelligence_agent.bybit_closed_stream_cache import HOUR_MS, OfflineReviewedStreamScope, SQLiteOfflineClosedStreamJournal
from crypto_intelligence_agent.bybit_instrument_volume_contract import BybitLinearInstrumentResearch
from crypto_intelligence_agent.bybit_paginated_universe_research import BybitInstrumentScanResearch
from crypto_intelligence_agent.j2_prospective_bybit_research_d436 import consume_confirmed_close_batch
from crypto_intelligence_agent.research_registry_catalog import load_reviewed_registry
from crypto_intelligence_agent.synthetic_entry_hypotheses import CompressionBreakoutConfig
from crypto_intelligence_agent.synthetic_feature_engine import FeatureConfig

FIRST = 1_792_998_000_000
SYMBOL = "BTCUSDT"
CONFIG = CompressionBreakoutConfig(FeatureConfig(2, 2, 2, 2), 2, 2, Decimal("1"), Decimal("1"), 0)

def _scope() -> OfflineReviewedStreamScope:
    reviewed = load_reviewed_registry("expanded-13", as_of_ms=FIRST)
    contract = BybitLinearInstrumentResearch(SYMBOL, "BTC", "USDT", "USDT", FIRST,
        FIRST - 30 * 86_400_000, Decimal("50"), Decimal("0.01"), Decimal("0.001"), reviewed.sha256_digest)
    scan = BybitInstrumentScanResearch(FIRST, reviewed.sha256_digest, 1, 1, FIRST, (contract,))
    return OfflineReviewedStreamScope.from_scan(scan, registry_variant="expanded-13")

def _frame(index: int) -> tuple[str, int]:
    start = FIRST + index * HOUR_MS
    close = "105" if index == 24 else "100"
    high = "106" if index == 24 else "101"
    return json.dumps({"topic": f"kline.60.{SYMBOL}", "type": "snapshot", "ts": start + HOUR_MS + 1000,
        "data": [{"start": start, "end": start + HOUR_MS - 1, "interval": "60", "open": "100", "high": high,
        "low": "99", "close": close, "volume": "10", "turnover": "40" if index == 24 else "20",
        "confirm": True, "timestamp": start + HOUR_MS - 1}]}), start + HOUR_MS + 2000

def run() -> dict:
    scope = _scope()
    with TemporaryDirectory(prefix="cia-d436-") as root:
        path = Path(root) / "research.sqlite"
        SQLiteOfflineClosedStreamJournal.create(path)
        ack = (json.dumps({"success": True, "ret_msg": "", "conn_id": "fixture", "op": "subscribe"}), FIRST + 1)
        # One ACK per bounded session; first session establishes the 24h causal history.
        consume_confirmed_close_batch(frames=(ack,) + tuple(_frame(i) for i in range(24)), journal_path=path,
            scope=scope, symbol=SYMBOL, decision_at_ms=FIRST + 24 * HOUR_MS,
            as_of_ms=FIRST + 24 * HOUR_MS + 2000, config=CONFIG)
        update = consume_confirmed_close_batch(frames=(ack, _frame(24)), journal_path=path,
            scope=scope, symbol=SYMBOL, decision_at_ms=FIRST + 25 * HOUR_MS,
            as_of_ms=FIRST + 25 * HOUR_MS + 2000, config=CONFIG)
        return update.sanitized_report()



class FakeClock:
    """Bounded in-process clock; it never sleeps or opens a socket."""
    def __init__(self, start_ms: int):
        self.utc = start_ms
        self.mono = 0.0

    def clock(self) -> float:
        return self.mono

    def wall_ms(self) -> int:
        return self.utc

    def sleeper(self, seconds: float) -> None:
        self.mono += seconds


class FakeSession:
    """Protocol-shaped in-memory WS frames, not an exchange connection."""
    def __init__(self, clock: FakeClock, frames):
        self.clock = clock
        self.frames = list(frames)
        self.sent = []
        self.closed = False

    def send(self, raw: str) -> None:
        self.sent.append(json.loads(raw))

    def recv(self, timeout: float) -> str:
        if self.frames:
            payload, received_ms = self.frames.pop(0)
            self.clock.mono += 0.1
            self.clock.utc = received_ms
            return json.dumps(payload) if type(payload) is dict else payload
        self.clock.mono += timeout
        raise TimeoutError("no more offline replay frames")

    def close(self) -> None:
        self.closed = True


def _fake_ack():
    return {"op": "subscribe", "success": True, "ret_msg": "subscribe",
            "conn_id": "fixture", "req_id": "cia-ws-1"}


def _opened_frame(index: int):
    raw, received = _frame(index)
    payload = json.loads(raw)
    payload["data"][0]["confirm"] = False
    return payload, received


def run_supervised_cycle(*, scenario: str = "LONG") -> dict:
    """Full fake socket -> committed close -> J2 -> private J5 projection.

    The terminal projection is served as 'session ended', not as active market.
    Uses a new disposable private SQLite, no network, financial call or VPS.
    """
    from crypto_intelligence_agent.j2_prospective_bybit_research_d436 import (
        supervise_prospective_research, read_projection,
    )
    from crypto_intelligence_agent.bybit_ws_supervisor import WSRunBudget
    import os

    if scenario not in ("LONG", "SHORT", "FLAT"):
        raise ValueError("unsupported deterministic scenario")
    scope = _scope()
    with TemporaryDirectory(prefix="cia-d436-supervised-") as root:
        path = Path(root) / "research.sqlite"
        SQLiteOfflineClosedStreamJournal.create(path)
        ack = (json.dumps(_fake_ack()), FIRST + 1)
        seed = consume_confirmed_close_batch(
            frames=(ack,) + tuple(_frame(i) for i in range(24)),
            journal_path=path, scope=scope, symbol=SYMBOL,
            decision_at_ms=FIRST + 24 * HOUR_MS,
            as_of_ms=FIRST + 24 * HOUR_MS + 2000, config=CONFIG,
        )
        assert seed.status == "observed_no_hypothesis"
        frame, receipt = _frame(24)
        payload = json.loads(frame)
        if scenario == "SHORT":
            payload["data"][0].update(close="95", low="94", high="101")
        elif scenario == "FLAT":
            payload["data"][0].update(close="100", high="101", low="99")
        clock = FakeClock(receipt)
        session = FakeSession(clock, (
            (_fake_ack(), receipt),
            _opened_frame(24),
            (payload, receipt),
        ))
        projection_dir = Path(root) / "private"
        if os.name == "posix" and os.geteuid() != 0:
            projection_dir.mkdir(mode=0o700)
            projection_dir.chmod(0o700)
        else:
            projection_dir = None
        report, last = supervise_prospective_research(
            session_factory=lambda: session, journal_path=path,
            scope=scope, symbol=SYMBOL, config=CONFIG,
            budget=WSRunBudget(1, 12, 2),
            projection_directory=projection_dir,
            clock=clock.clock, wall_ms=clock.wall_ms, sleeper=clock.sleeper,
        )
        assert session.closed and report.closed_events_appended == 1
        assert report.open_updates == 1 and last is not None
        assert last.data_mode == "offline_protocol_replay"
        assert last.last_frame_received_ms == receipt
        assert last.session_ended is False
        assert last.status in (
            "observed_long_hypothesis_not_authorized",
            "observed_short_hypothesis_not_authorized", "observed_no_hypothesis",
        )
        result = {
            "schema_version": "d436-supervised-offline-replay-proof-v1",
            "research": last.sanitized_report(),
            "session": report.sanitized_report(),
            "terminal": None,
            "journal_replay_append_count": 0,
            "orders_sent": False, "network_attempted": False,
        }
        if projection_dir is not None:
            terminal = read_projection(projection_dir, now_ms=clock.utc)
            assert terminal["session_ended"] is True
            assert terminal["status"] == "observed_session_ended"
            result["terminal"] = terminal
        replay = FakeSession(clock, (
            (_fake_ack(), receipt),
            (payload, receipt),
        ))
        again, duplicate = supervise_prospective_research(
            session_factory=lambda: replay, journal_path=path,
            scope=scope, symbol=SYMBOL, config=CONFIG,
            budget=WSRunBudget(1, 12, 2),
            projection_directory=projection_dir,
            clock=clock.clock, wall_ms=clock.wall_ms, sleeper=clock.sleeper,
        )
        assert duplicate is None and again.closed_events_appended == 0
        assert again.identical_replays == 1
        result["journal_replay_append_count"] = again.closed_events_appended
        return result

if __name__ == "__main__":
    print(json.dumps(run_supervised_cycle(), sort_keys=True, separators=(",", ":")))
