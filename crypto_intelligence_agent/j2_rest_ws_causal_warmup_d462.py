"""D462: causal 24 REST historical hours + ONE genuine journaled WS close.

This is NOT a migration or REST backfill into a WS journal. Historical
OHLCV retains REST quality; only the final bar has post-ACK WS provenance.
A frozen REST set is reread/checksummed at use, and the final WS receipt is
read from the existing canonical immutable D451 SQLite journal. No new
trading order, account access, credentials, polling or network request.
"""
from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
import stat

from .bybit_closed_stream_cache import (
    HOUR_MS, OfflineReviewedStreamScope, SQLiteOfflineClosedStreamJournal,
    _validated_payload,
)
from .j2_bybit_closed_research_bridge import BybitClosedResearchSeries
from .j2_rest_n50_history_d461 import (
    RestN50History, reopen_frozen_rest_n50_for_research,
)
from .j4_private_paper_ws_operator_d425 import _owner_file
from .market_data import ClosedCandle, DataGapError, DataValidationError

_STATUS = "research_only_mixed_rest24_ws1_closed_series"
_REST = "bybit_public_rest_historical_closed_unverified"
_WS = "bybit_public_ws_confirmed_unverified"


@dataclass(frozen=True)
class CausalRestWsResearch:
    series: BybitClosedResearchSeries
    rest_warmup_count: int
    ws_confirmed_close_count: int
    last_ws_received_ms: int
    historical_rest_snapshot_sha256: str
    ws_confirmed_event_sha256: str

    def sanitized_report(self) -> dict:
        return {
            "schema_version": "d462-causal-rest24-ws1-closed-hour-v1",
            "status": "causal_rest_warmup_and_ws_close_validated_for_paper_research",
            "symbol": self.series.candles[-1].symbol,
            "rest_historical_candles": self.rest_warmup_count,
            "post_ack_ws_confirmed_candles": self.ws_confirmed_close_count,
            "last_ws_received_ms": self.last_ws_received_ms,
            "rest_snapshot_sha256": self.historical_rest_snapshot_sha256,
            "last_ws_event_sha256": self.ws_confirmed_event_sha256,
            "combined_research_sha256": self.series.journal_digest_sha256,
            "historical_and_live_sources_distinct": True,
            "source_authenticated": False,
            "native_protective_orders": False,
            "orders_sent": False,
            "approved_for_live_trading": False,
        }


def read_causal_rest_warmup_ws_close(
    *, history: RestN50History,
    scope: OfflineReviewedStreamScope,
    journal_path: Path, symbol: str,
    open_ms: int, received_ms: int,
) -> CausalRestWsResearch:
    """Return series only after independently validating BOTH histories.

    The caller is the D450 post-ACK and post-SQLite-append receipt consumer;
    a stale/future REST snapshot or REST/WS mixed scope always abstains.
    """
    if (type(history) is not RestN50History
            or type(scope) is not OfflineReviewedStreamScope
            or not isinstance(journal_path, Path)
            or type(symbol) is not str
            or symbol not in {c.symbol for c in scope.contracts}
            or type(open_ms) is not int or open_ms <= 0 or open_ms % HOUR_MS
            or type(received_ms) is not int
            or not open_ms + HOUR_MS <= received_ms <= open_ms + HOUR_MS + 120_000
            or history.window_end_ms != open_ms
            or history.scope_sha256 != scope.registry_sha256
            or history.source_mode not in (
                "public_rest_observed_unverified", "injected_offline_protocol_replay",
            )
            or history.snapshot_file is None
            or not isinstance(history.snapshot_file, Path)
            or symbol not in history.symbols
            or len(history.series) != 50
            or not open_ms <= history.captured_at_ms < open_ms + HOUR_MS
            or history.captured_at_ms >= received_ms):
        raise DataValidationError("D462 exact causal REST warmup and WS scope required")
    frozen = reopen_frozen_rest_n50_for_research(
        private_j2_directory=history.snapshot_file.parent,
        filename=history.snapshot_file.name,
    )
    if (frozen.scope_sha256 != history.scope_sha256
            or frozen.digest_sha256 != history.digest_sha256
            or frozen.window_end_ms != history.window_end_ms
            or frozen.source_mode != history.source_mode
            or frozen.symbols != history.symbols
            or frozen.captured_at_ms != history.captured_at_ms):
        raise DataGapError("D462 frozen historical archive was replaced")
    bars = dict(frozen.series)[symbol]
    if (len(bars) != 24 or bars[-1].close_time_ms + 1 != open_ms
            or any(c.quality != _REST for c in bars)
            or any(y.open_time_ms != x.open_time_ms + HOUR_MS
                   for x, y in zip(bars, bars[1:]))):
        raise DataGapError("D462 23+1 historical time window not contiguous")
    # Require the owner-only canonical journal. A single WS close can be
    # verified without falsely requiring 24 previously observed WS closes.
    # All SQLite reads occur in one read-only transaction.
    path = journal_path
    fd = _owner_file(path.parent, path.name)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode)
                or before.st_uid != os.geteuid()
                or stat.S_IMODE(before.st_mode) != 0o600):
            raise DataValidationError("D462 unsafe public WS research journal")
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=2)) as db:
            db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN")
            journal = SQLiteOfflineClosedStreamJournal(path)
            journal._check_schema(db)
            row = db.execute(
                "SELECT symbol,open_ms,received_ms,registry_sha256,payload,digest "
                "FROM confirmed WHERE symbol=? AND open_ms=?",
                (symbol, open_ms),
            ).fetchone()
            if row is None:
                raise DataGapError("D462 no post-ACK WS confirmed close for exact hour")
            recorded_symbol, recorded_open, recorded_receipt, registry, raw, digest = row
            data = _validated_payload(raw, digest)
        after = path.lstat()
        if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
            raise DataGapError("D462 canonical journal replaced while reading")
    except sqlite3.DatabaseError:
        raise DataGapError("D462 cannot inspect canonical WS journal") from None
    finally:
        os.close(fd)
    member = scope.member(symbol)
    if (recorded_symbol != symbol or recorded_open != open_ms
            or recorded_receipt != received_ms or registry != scope.registry_sha256
            or data["symbol"] != symbol or data["registry_sha256"] != registry
            or data["scope_observed_ms"] != scope.observed_at_ms
            or data["launch_ms"] != member.launch_time_ms
            or data["open_ms"] != open_ms
            or data["end_ms"] != open_ms + HOUR_MS - 1
            or data["received_ms"] != received_ms
            or not open_ms + HOUR_MS <= data["server_ms"] <= received_ms
            or data["trade_ms"] > data["server_ms"]
            or data["server_ms"] < scope.observed_at_ms
            or data["received_ms"] - data["server_ms"] > 3_000):
        raise DataGapError("D462 post-ACK WS receipt or immutable scope mismatch")
    # Some Bybit closes have trade_ms=end+202ms, bounded by server time.
    if not open_ms <= data["trade_ms"]:
        raise DataGapError("D462 out-of-hour WS trade clock")
    ws = ClosedCandle(
        exchange="bybit_v5_public", market="linear_perpetual",
        symbol=symbol, interval="1h",
        open_time_ms=open_ms, close_time_ms=data["end_ms"],
        open=Decimal(data["open"]), high=Decimal(data["high"]),
        low=Decimal(data["low"]), close=Decimal(data["close"]),
        base_volume=Decimal(data["volume_base"]),
        quote_volume=Decimal(data["turnover_usdt"]),
        quality=_WS,
    )
    recent = tuple(bars) + (ws,)
    combined = sha256(json.dumps({
        "schema": "d462-rest24-plus-postack-ws1-v1",
        "scope": scope.registry_sha256,
        "symbol": symbol,
        "rest_history_sha256": frozen.digest_sha256,
        "ws_payload_sha256": digest,
        "ws_open_ms": open_ms,
        "ws_received_ms": received_ms,
    }, sort_keys=True, separators=(",", ":")).encode("ascii")).hexdigest()
    return CausalRestWsResearch(
        series=BybitClosedResearchSeries(
            recent, combined, registry, _STATUS,
        ),
        rest_warmup_count=24,
        ws_confirmed_close_count=1,
        last_ws_received_ms=received_ms,
        historical_rest_snapshot_sha256=frozen.digest_sha256,
        ws_confirmed_event_sha256=digest,
    )
