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
import json
import os
import stat
import tempfile

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
    data_mode: str = "offline_protocol_replay"
    last_frame_received_ms: int | None = None

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
            "source": self.data_mode,
            "network_attempted": self.data_mode == "public_ws_observed_unverified",
            "last_frame_received_ms": self.last_frame_received_ms,
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


def evaluate_persisted_confirmed_close(*, journal_path: str | Path,
    scope: OfflineReviewedStreamScope, symbol: str, open_ms: int,
    received_ms: int, config: CompressionBreakoutConfig,
    data_mode: str = "public_ws_observed_unverified") -> ProspectiveResearchUpdate:
    """Causal post-append callback: no parser, reingest or synthetic clock."""
    if (type(open_ms) is not int or open_ms <= 0 or open_ms % HOUR_MS
            or type(received_ms) is not int or received_ms < open_ms + HOUR_MS + 1000
            or data_mode not in ("offline_protocol_replay", "public_ws_observed_unverified")):
        raise DataValidationError("D436 callback close clock invalid")
    decision = open_ms + HOUR_MS
    try:
        series = read_bybit_closed_research_series(journal_path, scope=scope, symbol=symbol,
            decision_at_ms=decision, as_of_ms=received_ms)
        result = evaluate_observed_bybit_research(series, config=config, decision_at_ms=decision)
        status = ("observed_long_hypothesis_not_authorized" if result.hypotheses and result.hypotheses[0].side.value == "LONG"
                  else "observed_short_hypothesis_not_authorized" if result.hypotheses else "observed_no_hypothesis")
        return ProspectiveResearchUpdate(status, decision, series.candles[-1].close_time_ms,
            series.journal_digest_sha256, 1, 0, None, data_mode, received_ms)
    except (DataGapError, DataValidationError):
        return ProspectiveResearchUpdate("observed_data_insufficient", decision, None, None,
            1, 0, "gap_or_stale", data_mode, received_ms)


_PROJECTION = "latest-j2-prospective-research.json"

def publish_projection(directory: Path, update: ProspectiveResearchUpdate) -> None:
    """Atomically publish a bounded owner-only J5 projection on POSIX."""
    if os.name != "posix" or os.geteuid() == 0 or directory.is_symlink() or not directory.is_dir():
        raise DataValidationError("D436 owner projection directory required")
    info = directory.stat()
    if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise DataValidationError("D436 unsafe projection directory")
    blob = json.dumps(update.sanitized_report(), sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    if not 1 <= len(blob) <= 4096: raise DataValidationError("D436 projection size")
    fd, temp = tempfile.mkstemp(prefix=".j2-d436-", dir=directory)
    try:
        with os.fdopen(fd, "wb") as out:
            os.fchmod(out.fileno(), 0o600); out.write(blob); out.flush(); os.fsync(out.fileno())
        os.replace(temp, directory / _PROJECTION); temp = ""
    finally:
        if temp: os.unlink(temp)


def read_projection(directory: Path, *, now_ms: int) -> dict:
    path = directory / _PROJECTION
    if (path.is_symlink() or not path.is_file() or type(now_ms) is not int):
        raise DataValidationError("D436 projection unavailable")
    info = path.stat()
    if stat.S_IMODE(info.st_mode) != 0o600 or not 1 <= info.st_size <= 4096:
        raise DataValidationError("D436 projection unsafe")
    value = json.loads(path.read_text(encoding="ascii"))
    required = {"schema_version", "status", "evaluated_at_ms", "latest_closed_end_ms", "journal_digest_sha256", "closed_events_appended", "identical_replays", "failure_category", "source", "network_attempted", "last_frame_received_ms", "data_quality", "approved_for_signals", "orders_sent", "risk_gate_called", "auto2_called", "auto4_called", "live_trading_authorized"}
    if (type(value) is not dict or set(value) != required or value.get("schema_version") != "j2-prospective-bybit-research-d436-v1"
            or value.get("orders_sent") is not False or value.get("approved_for_signals") is not False
            or type(value.get("evaluated_at_ms")) is not int or now_ms - value["evaluated_at_ms"] > 120_000):
        raise DataValidationError("D436 projection stale or invalid")
    return value
