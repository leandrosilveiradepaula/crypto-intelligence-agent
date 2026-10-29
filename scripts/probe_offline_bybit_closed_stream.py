"""J1 #326: exercise 24 synthetic CLOSED Bybit WS hours, completely offline.

No WebSocket client, REST fallback, credentials, owner database, or orders.
Creates a throwaway local SQLite fixture and prints ONLY sanitized counts/hashes.
--inject-disconnect stops one symbol to prove gap abstention; it never repairs
missing history by guessing or calling an external provider.
"""
from __future__ import annotations

import argparse
from decimal import Decimal
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from crypto_intelligence_agent.bybit_closed_stream_cache import (
    HOUR_MS, OfflineReviewedStreamScope, SQLiteOfflineClosedStreamJournal,
    parse_offline_confirmed_kline,
)
from crypto_intelligence_agent.bybit_instrument_volume_contract import BybitLinearInstrumentResearch
from crypto_intelligence_agent.bybit_paginated_universe_research import BybitInstrumentScanResearch
from crypto_intelligence_agent.research_registry_catalog import load_reviewed_registry

DECISION_MS = 1793282400000  # deterministic historical fixture, 29 Oct 2026 14 UTC
SCOPE_MS = DECISION_MS - 26 * HOUR_MS
_SYMBOLS = ("BTCUSDT", "ETHUSDT")


def run_mock(*, inject_disconnect: bool = False) -> dict:
    reviewed = load_reviewed_registry("expanded-13", as_of_ms=SCOPE_MS)
    contracts = tuple(BybitLinearInstrumentResearch(
        symbol=s, base_coin=s[:-4], quote_coin="USDT", settle_coin="USDT",
        observed_at_ms=SCOPE_MS, launch_time_ms=SCOPE_MS - 4*86_400_000,
        max_leverage=Decimal("50"), tick_size=Decimal("0.01"),
        quantity_step=Decimal("0.001"), registry_sha256=reviewed.sha256_digest,
    ) for s in _SYMBOLS)
    # Fixture scan is not proof that an HTTP catalog was genuinely observed.
    scan = BybitInstrumentScanResearch(SCOPE_MS, reviewed.sha256_digest, 1,
                                       len(_SYMBOLS), SCOPE_MS, contracts)
    scope = OfflineReviewedStreamScope.from_scan(scan, registry_variant="expanded-13")
    with TemporaryDirectory(prefix="cia-j1-ws-fixture-") as root:
        journal = SQLiteOfflineClosedStreamJournal.create(Path(root) / "fixture.sqlite")
        first = DECISION_MS - 24 * HOUR_MS
        for offset in range(24):
            start = first + offset * HOUR_MS
            for symbol in _SYMBOLS:
                if inject_disconnect and symbol == "ETHUSDT" and offset >= 12:
                    continue
                frame = {"topic": f"kline.60.{symbol}", "type": "snapshot",
                         "ts": start + HOUR_MS + 1200,
                         "data": [{"start": start, "end": start + HOUR_MS - 1,
                                   "interval": "60", "open": "10", "high": "11",
                                   "low": "9", "close": "10", "volume": "1",
                                   "turnover": "10", "confirm": True,
                                   "timestamp": start + HOUR_MS - 500}]}
                checked = parse_offline_confirmed_kline(
                    frame, scope=scope, received_at_ms=start+HOUR_MS+2000,
                )
                journal.append(checked)
        report = journal.audit(scope=scope, decision_at_ms=DECISION_MS,
                               as_of_ms=DECISION_MS + 4000)
        return report.sanitized_report()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inject-disconnect", action="store_true")
    args = parser.parse_args(argv)
    print(json.dumps(run_mock(inject_disconnect=args.inject_disconnect),
                     separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
