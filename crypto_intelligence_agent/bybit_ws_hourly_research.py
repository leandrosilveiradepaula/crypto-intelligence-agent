"""J1/OPS1: offline-only hourly WS research with a complete local 24h rank.

The exchange feed, subscription/ACK and persisted closed hours are provided
by existing, separately tested components. This module NEVER opens a socket,
issues an HTTP request, reads the private REST research database, or sends an
order. A selection is only for the reviewed offline stream scope, not for the
Bybit-wide crypto market. It is not a daemon or an installed live collector.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from .bybit_closed_stream_cache import (
    HOUR_MS, OfflineReviewedStreamScope, SQLiteOfflineClosedStreamJournal,
)
from .bybit_ws_offline_pipeline import ingest_offline_ws_batch
from .market_data import DataGapError, DataValidationError

MAX_RESEARCH_TOP_N = 50


@dataclass(frozen=True)
class OfflineHourlyResearchResult:
    """One causal decision; selected identities are private in-memory only."""

    status: str
    closed_hour_ms: int
    reviewed_scope_assets: int
    complete_24h_assets: int
    missing_24h_assets: int
    selected_assets: int
    journal_rows: int
    appended_this_batch: int
    idempotent_replays: int
    ignored_open_updates: int
    rank_digest_sha256: str | None
    _selected_symbols: tuple[str, ...] = field(default=(), repr=False, compare=False)

    def selected_symbols(self) -> tuple[str, ...]:
        """Research-only selection for an INTERNAL consumer, never a public report."""
        if self.status != "offline_reviewed_hour_ready_not_marketwide":
            raise DataGapError("incomplete closed hour: ranking abstained")
        if len(self._selected_symbols) != self.selected_assets:
            raise DataGapError("private research selection mismatch")
        return self._selected_symbols

    def sanitized_report(self) -> dict:
        """Keep private universe membership, financial amounts and URLs out."""
        return {
            "status": self.status,
            "closed_hour_ms": self.closed_hour_ms,
            "reviewed_scope_assets": self.reviewed_scope_assets,
            "complete_24h_assets": self.complete_24h_assets,
            "missing_24h_assets": self.missing_24h_assets,
            "selected_assets": self.selected_assets,
            "journal_rows": self.journal_rows,
            "closed_events_appended": self.appended_this_batch,
            "identical_replays": self.idempotent_replays,
            "open_updates_not_stored": self.ignored_open_updates,
            "rank_digest_sha256": self.rank_digest_sha256,
            "ranking_uses_last_24_closed_utc_hours": True,
            "reviewed_sample_only": True,
            "marketwide_top50_verified": False,
            "historical_720h_proven_by_ws": False,
            "source_authenticated": False,
            "canonical_ohlcv_approved": False,
            "live_trading_authorized": False,
            "orders_sent": False,
            "network_requests": 0,
        }


def replay_offline_ws_closed_hour(
    *,
    frames: Iterable[tuple[str | bytes, int]],
    scope: OfflineReviewedStreamScope,
    journal: SQLiteOfflineClosedStreamJournal,
    closed_hour_ms: int,
    as_of_ms: int,
    max_assets: int = MAX_RESEARCH_TOP_N,
) -> OfflineHourlyResearchResult:
    """Replay a bounded WS batch and evaluate a LOCAL point-in-time 24h rank.

    All scope members must have 24 *closed* candles in the SQLite journal;
    selecting 50 of 52 is forbidden when either missing member might outrank
    those 50. Open candles and trailing rolling tickers are never ranked.

    Disconnect/invalid frame errors propagate and the decision abstains; the
    existing journal may retain individually committed valid earlier frames.
    On a later explicit retry, identical frames replay idempotently. This
    cannot backfill a missing historical candle, nor create an artificial PIT.
    """
    if (type(scope) is not OfflineReviewedStreamScope
            or type(journal) is not SQLiteOfflineClosedStreamJournal
            or type(closed_hour_ms) is not int
            or type(as_of_ms) is not int
            or closed_hour_ms <= 24 * HOUR_MS
            or closed_hour_ms % HOUR_MS != 0
            or not closed_hour_ms + 1000 <= as_of_ms < closed_hour_ms + HOUR_MS
            or type(max_assets) is not int
            or not 1 <= max_assets <= MAX_RESEARCH_TOP_N
            or max_assets > len(scope.contracts)):
        raise DataValidationError("offline reviewed closed-hour decision invalid")

    batch = ingest_offline_ws_batch(
        frames=frames, scope=scope, journal=journal, require_ack=True,
    )
    audited = journal.audit(
        scope=scope, decision_at_ms=closed_hour_ms, as_of_ms=as_of_ms,
    )
    complete = (
        audited.status == "offline_reviewed_24h_complete_not_top50"
        and audited.missing_24h_symbols == 0
        and audited.complete_24h_symbols == len(scope.contracts)
        and audited.rank_digest_sha256 is not None
        and len(audited.private_ranked_members) == len(scope.contracts)
    )
    selected = audited.private_ranked_members[:max_assets] if complete else ()
    return OfflineHourlyResearchResult(
        status=("offline_reviewed_hour_ready_not_marketwide" if complete
                else "offline_closed_hour_incomplete_abstain"),
        closed_hour_ms=closed_hour_ms,
        reviewed_scope_assets=len(scope.contracts),
        complete_24h_assets=audited.complete_24h_symbols,
        missing_24h_assets=audited.missing_24h_symbols,
        selected_assets=len(selected),
        journal_rows=audited.persisted_rows,
        appended_this_batch=batch.appended,
        idempotent_replays=batch.identical_replays,
        ignored_open_updates=batch.open_updates,
        rank_digest_sha256=audited.rank_digest_sha256 if complete else None,
        _selected_symbols=tuple(symbol for symbol, _ in selected),
    )