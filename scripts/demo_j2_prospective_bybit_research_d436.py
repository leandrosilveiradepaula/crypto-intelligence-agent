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

if __name__ == "__main__":
    print(json.dumps(run(), sort_keys=True, separators=(",", ":")))
