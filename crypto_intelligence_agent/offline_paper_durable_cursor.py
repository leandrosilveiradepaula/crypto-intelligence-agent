"""J6/PRE2-B: bounded, crash-safe *local fixture* cursor in the AUTO2 file.

This is not a runner or an order sender. The cursor shares the existing AUTO2
BEGIN IMMEDIATE with the health/risk gate and the PENDING intent insert.
Only a dedicated, explicitly initialized synthetic journal may use this API.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import sqlite3
from typing import Sequence

from .causal_paper_open import (
    CausalPaperOpening, _finish_causal_paper_open, prepare_causal_paper_open,
)
from .market_data import ClosedCandle, DataValidationError
from .offline_paper_fixture_seal import (
    OfflinePaperFixtureSeal, SEAL_VERSION, seal_offline_paper_prefix,
    verify_offline_paper_extension,
)
from .paper_order_store import SQLitePaperOrderJournal, _digest, _json
from .paper_risk_gate import PaperRiskLimits, PaperRiskObservation
from .synthetic_entry_hypotheses import CompressionBreakoutConfig
from .synthetic_feature_engine import MAX_CANDLES
from .synthetic_manual_exit_replay import _utc_ms
from .synthetic_order_lifecycle import PaperVenue

_CURSOR_KEY = "offline_paper_forward_cursor_v1"
_CURSOR_VERSION = "offline-paper-forward-cursor-v1"
_MAX_CURSOR_CHARS = 2048


@dataclass(frozen=True)
class DurableOfflinePaperTick:
    sequence_number: int
    accepted_candle_count: int
    decision_at_ms: int
    opening: CausalPaperOpening
    seal: OfflinePaperFixtureSeal

    @property
    def durable_session_checkpoint_available(self) -> bool:
        return True

    @property
    def orders_sent(self) -> bool:
        return False

    @property
    def order_submission_enabled(self) -> bool:
        return False

    @property
    def approved_for_live_use(self) -> bool:
        return False

    @property
    def market_data_verified(self) -> bool:
        return False

    @property
    def cross_database_atomic_snapshot_available(self) -> bool:
        return False

    @property
    def source_quality(self) -> str:
        return "durable_local_synthetic_fixture_only"


@dataclass(frozen=True)
class _Cursor:
    seal: OfflinePaperFixtureSeal
    sequence: int
    open_intent_ids: tuple[str, ...]


def _checked_cursor_payload(cursor: _Cursor) -> str:
    seal = cursor.seal
    if (type(cursor) is not _Cursor or type(seal) is not OfflinePaperFixtureSeal
            or seal.version != SEAL_VERSION
            or type(cursor.sequence) is not int
            or not 1 <= cursor.sequence <= MAX_CANDLES
            or cursor.sequence < 1
            or type(cursor.open_intent_ids) is not tuple
            or len(cursor.open_intent_ids) > cursor.sequence
            or len(set(cursor.open_intent_ids)) != len(cursor.open_intent_ids)
            or any(type(v) is not str or not v.startswith("fixture_open_")
                   or len(v) > 128 for v in cursor.open_intent_ids)):
        raise DataValidationError("invalid durable PAPER cursor")
    for value in (seal.context_sha256, seal.prefix_sha256):
        if (type(value) is not str or len(value) != 64
                or any(ch not in "0123456789abcdef" for ch in value)):
            raise DataValidationError("invalid PAPER cursor digest")
    for value in (
        seal.candle_count, seal.first_open_time_ms, seal.last_open_time_ms,
        seal.last_close_time_ms, seal.decision_at_ms,
    ):
        if type(value) is not int or value <= 0:
            raise DataValidationError("invalid PAPER cursor timestamp/count")
    if (seal.candle_count < cursor.sequence
            or seal.candle_count > MAX_CANDLES
            or seal.first_open_time_ms > seal.last_open_time_ms
            or seal.last_open_time_ms > seal.last_close_time_ms
            or seal.last_close_time_ms > seal.decision_at_ms):
        raise DataValidationError("invalid PAPER cursor monotonic fields")
    return _json({
        "version": _CURSOR_VERSION,
        "sequence": cursor.sequence,
        "open_intent_ids": list(cursor.open_intent_ids),
        "seal": {
            "version": seal.version,
            "context_sha256": seal.context_sha256,
            "prefix_sha256": seal.prefix_sha256,
            "candle_count": seal.candle_count,
            "first_open_time_ms": seal.first_open_time_ms,
            "last_open_time_ms": seal.last_open_time_ms,
            "last_close_time_ms": seal.last_close_time_ms,
            "decision_at_ms": seal.decision_at_ms,
        },
    })


def _load_cursor(conn: sqlite3.Connection) -> _Cursor | None:
    from .paper_open_health import _verify_locked_order_schema
    # The strict AUTO8 reader expects exactly schema_version. This new key is
    # therefore deliberately validated here before any write; AUTO8 must be
    # updated to accept precisely this optional key, never arbitrary metadata.
    _verify_locked_order_schema(conn)
    rows = conn.execute(
        "SELECT key, value FROM paper_order_meta ORDER BY key"
    ).fetchall()
    values = {r["key"]: r["value"] for r in rows}
    if _CURSOR_KEY not in values:
        return None
    raw = values[_CURSOR_KEY]
    if type(raw) is not str or len(raw) > _MAX_CURSOR_CHARS:
        raise DataValidationError("PAPER cursor metadata exceeds bound")
    try:
        envelope = json.loads(raw)
        if type(envelope) is not dict or set(envelope) != {"payload", "sha256"}:
            raise ValueError("invalid envelope")
        payload = envelope["payload"]
        if type(payload) is not str or _digest(payload) != envelope["sha256"]:
            raise ValueError("cursor checksum")
        value = json.loads(payload)
        if type(value) is not dict or set(value) != {
            "version", "sequence", "open_intent_ids", "seal",
        } or value["version"] != _CURSOR_VERSION:
            raise ValueError("cursor version")
        s = value["seal"]
        if type(s) is not dict or set(s) != {
            "version", "context_sha256", "prefix_sha256", "candle_count",
            "first_open_time_ms", "last_open_time_ms", "last_close_time_ms",
            "decision_at_ms",
        } or type(value["open_intent_ids"]) is not list:
            raise ValueError("cursor fields")
        cursor = _Cursor(
            OfflinePaperFixtureSeal(**s), value["sequence"],
            tuple(value["open_intent_ids"]),
        )
        if _checked_cursor_payload(cursor) != payload:
            raise ValueError("noncanonical cursor")
        return cursor
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        raise DataValidationError("invalid or tampered durable PAPER cursor") from exc


def _verify_cursor_orders(conn: sqlite3.Connection, cursor: _Cursor | None) -> None:
    # Fail closed for legacy OPENs: their missing cursor history cannot be
    # reconstructed by guessing whether a signal was processed before crash.
    rows = conn.execute(
        "SELECT intent_id FROM paper_order_intents "
        "WHERE effect='OPEN' ORDER BY intent_id LIMIT 4097"
    ).fetchall()
    if len(rows) > 4096:
        raise DataValidationError("PAPER OPEN audit resource limit")
    ids = tuple(row["intent_id"] for row in rows)
    expected = () if cursor is None else tuple(sorted(cursor.open_intent_ids))
    if ids != expected:
        raise DataValidationError("PAPER OPEN journal and durable cursor diverged")
    for intent_id in ids:
        entry = SQLitePaperOrderJournal._checked_entry(conn, intent_id)
        if cursor is None or entry.intent.created_at_ms > cursor.seal.decision_at_ms:
            raise DataValidationError("PAPER OPEN checkpoint is missing or future")


def _write_cursor(conn: sqlite3.Connection, cursor: _Cursor) -> None:
    payload = _checked_cursor_payload(cursor)
    envelope = _json({"payload": payload, "sha256": _digest(payload)})
    if len(envelope) > _MAX_CURSOR_CHARS:
        raise DataValidationError("PAPER cursor envelope exceeds resource bound")
    conn.execute(
        "INSERT INTO paper_order_meta(key,value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (_CURSOR_KEY, envelope),
    )


def _checked_step_seal(
    closed_prefix: Sequence[ClosedCandle], previous: _Cursor | None, *,
    strategy: CompressionBreakoutConfig, venue: PaperVenue,
    requested_units, limits: PaperRiskLimits, decision_at_ms: int,
    close_safety_ms: int, max_candles: int,
) -> OfflinePaperFixtureSeal:
    kwargs = dict(
        strategy=strategy, venue=venue, requested_units=requested_units,
        limits=limits, decision_at_ms=decision_at_ms,
        close_safety_ms=close_safety_ms, max_candles=max_candles,
    )
    if previous is None:
        return seal_offline_paper_prefix(closed_prefix, **kwargs)
    return verify_offline_paper_extension(previous.seal, closed_prefix, **kwargs)


def step_durable_offline_paper(
    closed_prefix: Sequence[ClosedCandle], *,
    strategy: CompressionBreakoutConfig, venue: PaperVenue,
    requested_units, limits: PaperRiskLimits, observation: PaperRiskObservation,
    journal: SQLitePaperOrderJournal, position_journal_path: str | Path,
    decision_at_ms: int, close_safety_ms: int = 1_000,
    max_candles: int = MAX_CANDLES,
    fault_at: str | None = None,
) -> DurableOfflinePaperTick:
    """One decision/OPEN/cursor commit, including no-signal and risk denial.

    Fault injection is exclusively a local test hook; it raises before commit.
    No cursor-only recovery is attempted after a failed/ambiguous transaction.
    """
    if (type(journal) is not SQLitePaperOrderJournal
            or type(position_journal_path) not in (str, Path)
            or not str(position_journal_path).strip()
            or fault_at not in (None, "after_reservation_before_cursor",
                                "after_cursor_before_commit")):
        raise DataValidationError("explicit fixture journals and fault hook required")
    now = _utc_ms(decision_at_ms, "decision_at_ms")
    # Pure validation/planning happens before the write lock. The resulting
    # hypothesis is not an authorization and is never reused after a restart.
    prepared = prepare_causal_paper_open(
        closed_prefix, strategy=strategy, venue=venue,
        requested_units=requested_units, limits=limits,
        observation=observation, decision_at_ms=now,
        close_safety_ms=close_safety_ms,
    )
    with journal._transaction() as conn:
        previous = _load_cursor(conn)
        _verify_cursor_orders(conn, previous)
        seal = _checked_step_seal(
            closed_prefix, previous, strategy=strategy, venue=venue,
            requested_units=requested_units, limits=limits,
            decision_at_ms=now, close_safety_ms=close_safety_ms,
            max_candles=max_candles,
        )
        if prepared.intent is not None:
            from .paper_open_health import _audit_paper_open_health_locked
            journal._check_paper_open_risk_inputs(prepared.intent, limits, observation)
            health = _audit_paper_open_health_locked(
                conn, journal.path, position_journal_path, decision_at_ms=now,
            )
            receipt = (
                journal._reserve_open_risk_locked(
                    conn, prepared.intent, limits, observation, now,
                ) if health.new_open_allowed else None
            )
            opening = _finish_causal_paper_open(prepared, health, receipt)
        else:
            opening = prepared
        if fault_at == "after_reservation_before_cursor":
            raise RuntimeError("injected PAPER failure before cursor write")
        ids = (() if previous is None else previous.open_intent_ids)
        if opening.paper_intent_reserved:
            if opening.intent is None:
                raise DataValidationError("PAPER reserved without intent")
            ids = ids + (opening.intent.intent_id,)
        cursor = _Cursor(
            seal=seal,
            sequence=(1 if previous is None else previous.sequence + 1),
            open_intent_ids=tuple(sorted(ids)),
        )
        _write_cursor(conn, cursor)
        if fault_at == "after_cursor_before_commit":
            raise RuntimeError("injected PAPER failure before transaction commit")
        # commit on context-manager exit; all AUTO2 writes are in ONE file.
    return DurableOfflinePaperTick(
        cursor.sequence, seal.candle_count, now, opening, seal,
    )


def recover_durable_offline_paper(
    closed_prefix: Sequence[ClosedCandle], *,
    strategy: CompressionBreakoutConfig, venue: PaperVenue,
    requested_units, limits: PaperRiskLimits,
    journal: SQLitePaperOrderJournal,
    close_safety_ms: int = 1_000,
    max_candles: int = MAX_CANDLES,
) -> OfflinePaperFixtureSeal:
    """Read-only-in-effect restart verification; never replays an OPEN."""
    if type(journal) is not SQLitePaperOrderJournal:
        raise DataValidationError("typed PAPER journal required")
    if type(closed_prefix) not in (tuple, list) or not closed_prefix:
        raise DataValidationError("complete PAPER recovery prefix required")
    now = _utc_ms(closed_prefix[-1].close_time_ms + close_safety_ms, "recovery time")
    with journal._transaction() as conn:
        cursor = _load_cursor(conn)
        if cursor is None:
            raise DataValidationError("no durable PAPER checkpoint to recover")
        _verify_cursor_orders(conn, cursor)
        seal = seal_offline_paper_prefix(
            closed_prefix, strategy=strategy, venue=venue,
            requested_units=requested_units, limits=limits,
            decision_at_ms=now, close_safety_ms=close_safety_ms,
            max_candles=max_candles,
        )
        if seal != cursor.seal:
            raise DataValidationError("PAPER restart prefix or context differs")
        return seal
