"""D436 finite prospective Bybit closed-candle research operator.

This is deliberately a *composition* of the established public kline parser,
isolated confirmed-candle journal and D434/D435 boundary.  It has no order,
RiskGate, AUTO2/AUTO4, credential or owner-J1 dependency.  A caller supplies
the receive clock with each WebSocket frame; therefore replay is deterministic
and a restart is safe to repeat.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .bybit_closed_stream_cache import HOUR_MS, OfflineReviewedStreamScope, SQLiteOfflineClosedStreamJournal
from .bybit_ws_offline_pipeline import ingest_offline_ws_batch
from .j2_bybit_closed_research_bridge import read_bybit_closed_research_series
from .j2_observed_bybit_research import evaluate_observed_bybit_research
from .market_data import DataGapError, DataValidationError
from .synthetic_entry_hypotheses import CompressionBreakoutConfig


@dataclass(frozen=True)
class ProspectiveResearchUpdate:
    """Sanitizable result for one confirmed-close evaluation attempt."""

    status: str
    evaluated_at_ms: int
    latest_closed_end_ms: int | None
    journal_digest_sha256: str | None
    appended: int
    identical_replays: int
    failure_category: str | None = None

    def sanitized_report(self) -> dict:
        return {
            "schema_version": "j2-prospective-bybit-research-d436-v1",
            "status": self.status,
            "evaluated_at_ms": self.evaluated_at_ms,
            "latest_closed_end_ms": self.latest_closed_end_ms,
            "journal_digest_sha256": self.journal_digest_sha256,
            "closed_events_appended": self.appended,
            "identical_replays": self.identical_replays,
            "failure_category": self.failure_category,
            "source": "bybit_v5_public_kline_60_confirmed",
            "data_quality": "bybit_public_ws_confirmed_unverified",
            "approved_for_signals": False,
            "orders_sent": False,
            "risk_gate_called": False,
            "auto2_called": False,
            "auto4_called": False,
            "live_trading_authorized": False,
        }


def consume_confirmed_close_batch(
    *, frames: Iterable[tuple[str | bytes, int]], journal_path: str | Path,
    scope: OfflineReviewedStreamScope, symbol: str, decision_at_ms: int,
    as_of_ms: int, config: CompressionBreakoutConfig,
) -> ProspectiveResearchUpdate:
    """Persist a bounded batch and evaluate its latest causal close.

    The established journal rejects conflicting replays and records gaps.  An
    incomplete/stale/contradictory journal produces an explicit abstention;
    it never falls back to REST or invents an intervening candle.
    """
    if (type(symbol) is not str or type(decision_at_ms) is not int
            or type(as_of_ms) is not int or decision_at_ms % HOUR_MS
            or not decision_at_ms + 1 <= as_of_ms < decision_at_ms + HOUR_MS):
        raise DataValidationError("D436 decision clock or symbol invalid")
    journal = SQLiteOfflineClosedStreamJournal(Path(journal_path))
    try:
        batch = ingest_offline_ws_batch(frames=frames, scope=scope, journal=journal)
        series = read_bybit_closed_research_series(
            journal_path, scope=scope, symbol=symbol,
            decision_at_ms=decision_at_ms, as_of_ms=as_of_ms,
        )
        evaluation = evaluate_observed_bybit_research(
            series, config=config, decision_at_ms=decision_at_ms,
        )
        latest = series.candles[-1].close_time_ms
        status = ("observed_long_hypothesis_not_authorized"
                  if evaluation.hypotheses and evaluation.hypotheses[0].side.value == "LONG"
                  else "observed_short_hypothesis_not_authorized"
                  if evaluation.hypotheses else "observed_no_hypothesis")
        return ProspectiveResearchUpdate(status, decision_at_ms, latest,
                                         series.journal_digest_sha256,
                                         batch.appended, batch.identical_replays)
    except DataGapError:
        return ProspectiveResearchUpdate("observed_data_insufficient", decision_at_ms,
                                         None, None, 0, 0, "gap_or_stale")
    except DataValidationError:
        return ProspectiveResearchUpdate("observed_feed_unavailable", decision_at_ms,
                                         None, None, 0, 0, "invalid_frame_or_scope")
