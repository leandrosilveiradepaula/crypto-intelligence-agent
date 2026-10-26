"""J4/AUTO2: transactional SQLite journal for PAPER intents and fictitious fills.

This is NOT an order sender. It imports neither account transports nor private
exchange APIs. Its file is deliberately separate from J1 market-data storage.
SQLite durability and paper replay cannot guarantee a real exchange fill,
exactly-once networking, venue-native reduce-only, or live readiness.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, replace
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Iterator

from .market_data import DataValidationError
from .paper_risk_gate import (
    PaperRiskDecision, PaperRiskLimits, PaperRiskObservation, evaluate_paper_risk,
)
from .synthetic_order_lifecycle import (
    PaperOrderEffect, PaperOrderEvent, PaperOrderEventKind, PaperOrderIntent,
    PaperOrderSnapshot, PaperOrderSide, PaperOrderStatus, PaperVenue, replay_paper_order,
)
from .synthetic_position_state import SyntheticSide
from .synthetic_manual_exit_replay import MAX_FIXTURE_EVENTS, _utc_ms


_VERSION = "paper-order-journal-v1"
_TABLES = {"paper_order_meta", "paper_order_intents", "paper_order_events"}


def _json(value: dict[str, object]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _intent_json(intent: PaperOrderIntent) -> str:
    return _json({
        "intent_id": intent.intent_id,
        "fixture_signal_id": intent.fixture_signal_id,
        "venue": intent.venue.value,
        "symbol": intent.symbol,
        "position_side": intent.position_side.value,
        "side": intent.side.value,
        "effect": intent.effect.value,
        "requested_units": str(intent.requested_units),
        "created_at_ms": intent.created_at_ms,
        "max_reducible_units": (None if intent.max_reducible_units is None
                                else str(intent.max_reducible_units)),
    })


def _event_json(event: PaperOrderEvent) -> str:
    return _json({
        "event_id": event.event_id,
        "kind": event.kind.value,
        "event_at_ms": event.event_at_ms,
        "filled_units": str(event.filled_units),
    })


def _snapshot_json(snapshot: PaperOrderSnapshot) -> str:
    return _json({
        "intent_id": snapshot.intent_id,
        "venue": snapshot.venue.value,
        "effect": snapshot.effect.value,
        "status": snapshot.status.value,
        "requested_units": str(snapshot.requested_units),
        "filled_total_units": str(snapshot.filled_total_units),
        "unfilled_units": str(snapshot.unfilled_units),
        "as_of_ms": snapshot.as_of_ms,
        "unique_event_count": snapshot.unique_event_count,
        "exact_duplicate_count": snapshot.exact_duplicate_count,
        "last_unique_event_at_ms": snapshot.last_unique_event_at_ms,
    })


def _decode_intent(payload: str) -> PaperOrderIntent:
    try:
        value = json.loads(payload)
        intent = PaperOrderIntent(
            intent_id=value["intent_id"],
            fixture_signal_id=value["fixture_signal_id"],
            venue=PaperVenue(value["venue"]),
            symbol=value["symbol"],
            position_side=SyntheticSide(value["position_side"]),
            side=PaperOrderSide(value["side"]),
            effect=PaperOrderEffect(value["effect"]),
            requested_units=Decimal(value["requested_units"]),
            created_at_ms=value["created_at_ms"],
            max_reducible_units=(
                None if value["max_reducible_units"] is None
                else Decimal(value["max_reducible_units"])
            ),
        )
        if _intent_json(intent) != payload:
            raise ValueError("non-canonical paper intent")
        return intent
    except (KeyError, ValueError, TypeError, ArithmeticError, OverflowError) as exc:
        raise DataValidationError("invalid stored paper intent") from exc


def _decode_event(payload: str) -> PaperOrderEvent:
    try:
        value = json.loads(payload)
        event = PaperOrderEvent(
            event_id=value["event_id"],
            kind=PaperOrderEventKind(value["kind"]),
            event_at_ms=value["event_at_ms"],
            filled_units=Decimal(value["filled_units"]),
        )
        if _event_json(event) != payload:
            raise ValueError("non-canonical paper event")
        return event
    except (KeyError, ValueError, TypeError, ArithmeticError, OverflowError) as exc:
        raise DataValidationError("invalid stored paper event") from exc


def _check_digest(payload: str, expected: str, label: str) -> None:
    if _digest(payload) != expected:
        raise DataValidationError(f"paper journal {label} integrity failure")


@dataclass(frozen=True)
class PaperJournalEntry:
    intent: PaperOrderIntent
    events: tuple[PaperOrderEvent, ...]
    snapshot: PaperOrderSnapshot

    @property
    def orders_sent(self) -> bool:
        return False

    @property
    def approved_for_live_use(self) -> bool:
        return False

    @property
    def persistent_idempotency_verified(self) -> bool:
        # Verified only for this local paper journal, not for remote exchange IDs.
        return False

    @property
    def quality(self) -> str:
        return "durable_paper_fixture_only"


@dataclass(frozen=True)
class PaperOpenRiskReservation:
    """Never a real order or permission; local PAPER risk/insert receipt."""

    decision: PaperRiskDecision
    entry: PaperJournalEntry | None
    local_pending_before: int
    local_unknown_before: bool

    @property
    def orders_sent(self) -> bool:
        return False

    @property
    def approved_for_live_use(self) -> bool:
        return False

    @property
    def order_submission_enabled(self) -> bool:
        return False


class SQLitePaperOrderJournal:
    """Atomic *local PAPER* ledger; no API to submit or place exchange orders.

    All read-modify-write operations use BEGIN IMMEDIATE and unique constraints.
    Within ONE file, an OPEN signal identity is reserved at most once, including
    across venue candidates (no account/strategy namespaces exist yet).
    """

    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        if (not self._path or self._path == ":memory:" or self._path.startswith("file:")
                or "\x00" in self._path):
            raise ValueError("paper journal requires a dedicated ordinary SQLite file path")
        self._initialize()

    @property
    def path(self) -> Path:
        """Dedicated local fixture path, exposed for read-only health checks."""
        return Path(self._path)

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._path, timeout=5)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _initialize(self) -> None:
        with self._transaction() as conn:
            tables = {
                row["name"] for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name NOT LIKE 'sqlite_%'"
                )
            }
            if tables and tables != _TABLES:
                raise DataValidationError("paper journal cannot reuse another database/schema")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS paper_order_meta "
                "(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS paper_order_intents (
                    intent_id TEXT PRIMARY KEY,
                    fixture_signal_id TEXT NOT NULL,
                    venue TEXT NOT NULL,
                    effect TEXT NOT NULL CHECK (effect IN ('OPEN','REDUCE_ONLY')),
                    payload TEXT NOT NULL, payload_sha256 TEXT NOT NULL,
                    checkpoint_as_of_ms INTEGER NOT NULL,
                    event_count INTEGER NOT NULL CHECK (event_count >= 0),
                    snapshot TEXT NOT NULL, snapshot_sha256 TEXT NOT NULL
                )"""
            )
            # No new OPEN for the same simulated signal after restart/UNKNOWN.
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS paper_one_open_per_signal "
                "ON paper_order_intents (fixture_signal_id) WHERE effect='OPEN'"
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS paper_order_events (
                    intent_id TEXT NOT NULL REFERENCES paper_order_intents(intent_id),
                    sequence INTEGER NOT NULL CHECK (sequence >= 1),
                    event_id TEXT NOT NULL,
                    payload TEXT NOT NULL, payload_sha256 TEXT NOT NULL,
                    PRIMARY KEY(intent_id, sequence),
                    UNIQUE(intent_id, event_id)
                )"""
            )
            row = conn.execute(
                "SELECT value FROM paper_order_meta WHERE key='schema_version'"
            ).fetchone()
            if row is None:
                if tables:
                    raise DataValidationError("paper journal missing schema version")
                conn.execute(
                    "INSERT INTO paper_order_meta VALUES ('schema_version', ?)",
                    (_VERSION,),
                )
            elif row["value"] != _VERSION:
                raise DataValidationError("unsupported paper journal schema version")

    @staticmethod
    def _checked_entry(conn: sqlite3.Connection, intent_id: str) -> PaperJournalEntry:
        row = conn.execute(
            "SELECT * FROM paper_order_intents WHERE intent_id=?", (intent_id,),
        ).fetchone()
        if row is None:
            raise DataValidationError("unknown paper order intent")
        _check_digest(row["payload"], row["payload_sha256"], "intent")
        intent = _decode_intent(row["payload"])
        if (intent.intent_id != row["intent_id"]
                or intent.fixture_signal_id != row["fixture_signal_id"]
                or intent.venue.value != row["venue"]
                or intent.effect.value != row["effect"]):
            raise DataValidationError("paper intent index disagrees with payload")
        rows = conn.execute(
            "SELECT * FROM paper_order_events WHERE intent_id=? ORDER BY sequence",
            (intent_id,),
        ).fetchall()
        if len(rows) != row["event_count"] or len(rows) > MAX_FIXTURE_EVENTS:
            raise DataValidationError("paper event cursor mismatches stored events")
        events = []
        for sequence, item in enumerate(rows, start=1):
            if item["sequence"] != sequence or item["intent_id"] != intent_id:
                raise DataValidationError("paper event sequence or intent changed")
            _check_digest(item["payload"], item["payload_sha256"], "event")
            event = _decode_event(item["payload"])
            if event.event_id != item["event_id"]:
                raise DataValidationError("paper event ID index changed")
            events.append(event)
        snapshot = replay_paper_order(
            intent, tuple(events), as_of_ms=row["checkpoint_as_of_ms"],
        )
        snapshot_payload = _snapshot_json(snapshot)
        _check_digest(row["snapshot"], row["snapshot_sha256"], "checkpoint")
        if row["snapshot"] != snapshot_payload:
            raise DataValidationError("paper checkpoint disagrees with event replay")
        return PaperJournalEntry(intent=intent, events=tuple(events), snapshot=snapshot)

    @staticmethod
    def _reserve_on_connection(
        conn: sqlite3.Connection, intent: PaperOrderIntent,
    ) -> PaperJournalEntry:
        """Share ONE atomic insert contract between legacy PAPER and gated API."""
        payload = _intent_json(intent)
        found = conn.execute(
            "SELECT intent_id FROM paper_order_intents WHERE intent_id=?",
            (intent.intent_id,),
        ).fetchone()
        if found:
            entry = SQLitePaperOrderJournal._checked_entry(conn, intent.intent_id)
            if _intent_json(entry.intent) != payload:
                raise DataValidationError("conflicting reserved paper intent payload")
            return entry
        snapshot = replay_paper_order(intent, (), as_of_ms=intent.created_at_ms)
        snap_payload = _snapshot_json(snapshot)
        try:
            conn.execute(
                """INSERT INTO paper_order_intents
                (intent_id, fixture_signal_id, venue, effect, payload,
                 payload_sha256, checkpoint_as_of_ms, event_count,
                 snapshot, snapshot_sha256) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    intent.intent_id, intent.fixture_signal_id,
                    intent.venue.value, intent.effect.value, payload,
                    _digest(payload), intent.created_at_ms, 0,
                    snap_payload, _digest(snap_payload),
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise DataValidationError(
                "paper signal already has an OPEN intent, or ID conflicts"
            ) from exc
        return PaperJournalEntry(intent, (), snapshot)

    def reserve(self, intent: PaperOrderIntent) -> PaperJournalEntry:
        """Legacy paper-only reservation; no order sender or real risk approval."""
        if type(intent) is not PaperOrderIntent:
            raise DataValidationError("validated paper intent required")
        with self._transaction() as conn:
            return self._reserve_on_connection(conn, intent)

    @staticmethod
    def _pending_open_from_connection(
        conn: sqlite3.Connection,
    ) -> tuple[int, bool]:
        """Verify ALL relevant local PAPER OPEN events under one write lock."""
        rows = conn.execute(
            "SELECT intent_id FROM paper_order_intents "
            "ORDER BY intent_id LIMIT 4097"
        ).fetchall()
        if len(rows) > 4096:
            raise DataValidationError("paper pending order audit exceeds resource bound")
        pending = 0
        has_unknown = False
        for row in rows:
            item = SQLitePaperOrderJournal._checked_entry(conn, row["intent_id"])
            # _checked_entry verifies the indexed effect against signed-off
            # canonical payload before we skip REDUCE_ONLY paper exits.
            if item.intent.effect is not PaperOrderEffect.OPEN:
                continue
            if item.snapshot.requires_reconciliation:
                pending += 1
                if item.snapshot.status is PaperOrderStatus.UNKNOWN:
                    has_unknown = True
        return pending, has_unknown

    @staticmethod
    def _check_paper_open_risk_inputs(
        intent: PaperOrderIntent, limits: PaperRiskLimits,
        observation: PaperRiskObservation,
    ) -> None:
        if (type(intent) is not PaperOrderIntent
                or intent.effect is not PaperOrderEffect.OPEN
                or type(limits) is not PaperRiskLimits
                or type(observation) is not PaperRiskObservation):
            raise DataValidationError("explicit paper OPEN, risk limits and observation required")

    def _reserve_open_risk_locked(
        self, conn: sqlite3.Connection, intent: PaperOrderIntent,
        limits: PaperRiskLimits, observation: PaperRiskObservation,
        decision_at_ms: int,
    ) -> "PaperOpenRiskReservation":
        """Single AUTO6 contract reused with and without the AUTO8 guard."""
        existing = conn.execute(
            "SELECT intent_id FROM paper_order_intents WHERE intent_id=?",
            (intent.intent_id,),
        ).fetchone()
        if existing is not None:
            self._checked_entry(conn, intent.intent_id)
            raise DataValidationError("paper intent already reserved; recover existing state")
        pending_local, unknown_local = self._pending_open_from_connection(conn)
        effective = replace(
            observation,
            pending_open_orders=max(pending_local, observation.pending_open_orders),
            unresolved_open_exists=(
                unknown_local or observation.unresolved_open_exists
            ),
        )
        decision = evaluate_paper_risk(
            intent, limits, effective, decision_at_ms=decision_at_ms,
        )
        if not decision.allowed_for_paper_only:
            return PaperOpenRiskReservation(
                decision=decision, entry=None, local_pending_before=pending_local,
                local_unknown_before=unknown_local,
            )
        entry = self._reserve_on_connection(conn, intent)
        return PaperOpenRiskReservation(
            decision=decision, entry=entry, local_pending_before=pending_local,
            local_unknown_before=unknown_local,
        )

    def reserve_open_if_paper_risk(
        self, intent: PaperOrderIntent, limits: PaperRiskLimits,
        observation: PaperRiskObservation, *, decision_at_ms: int,
    ) -> "PaperOpenRiskReservation":
        """Legacy atomic PAPER risk reservation; never an exchange order.

        Pending/UNKNOWN cannot be hidden by a stale caller fixture, but the
        legacy API has NO cross-journal position-health guard. The causal
        AUTO7 caller MUST use reserve_open_if_paper_risk_with_health instead.
        """
        self._check_paper_open_risk_inputs(intent, limits, observation)
        with self._transaction() as conn:
            return self._reserve_open_risk_locked(
                conn, intent, limits, observation, decision_at_ms,
            )

    def reserve_open_if_paper_risk_with_health(
        self, intent: PaperOrderIntent, limits: PaperRiskLimits,
        observation: PaperRiskObservation, *,
        decision_at_ms: int,
        position_journal_path: str | Path,
    ) -> "tuple[PaperOpenHealth, PaperOpenRiskReservation | None]":
        """Guard health + OPEN risk + reservation under ONE order-file lock.

        Health reads every AUTO2 OPEN while BEGIN IMMEDIATE prevents a new
        order FILL from slipping between audit and insert. The separate AUTO4
        file remains independently sampled, never cross-database atomic.
        Blocking health returns no reservation; allow only a PENDING fixture.
        """
        from .paper_open_health import _audit_paper_open_health_locked

        self._check_paper_open_risk_inputs(intent, limits, observation)
        with self._transaction() as conn:
            health = _audit_paper_open_health_locked(
                conn, self.path, position_journal_path,
            )
            if not health.new_open_allowed:
                return health, None
            receipt = self._reserve_open_risk_locked(
                conn, intent, limits, observation, decision_at_ms,
            )
            return health, receipt

    @staticmethod
    def _insert_event(
        conn: sqlite3.Connection, intent_id: str,
        sequence: int, event: PaperOrderEvent,
    ) -> None:
        payload = _event_json(event)
        conn.execute(
            "INSERT INTO paper_order_events VALUES (?,?,?,?,?)",
            (intent_id, sequence, event.event_id, payload, _digest(payload)),
        )

    def append_events(
        self, intent_id: str, events: tuple[PaperOrderEvent, ...],
        *, as_of_ms: int,
    ) -> PaperJournalEntry:
        """Atomically append hypothetical events AND checkpoint after full replay.

        Exact old events are ignored; conflicts or any rejected second event
        roll back the whole batch. Does NOT retry UNKNOWN or resubmit anything.
        """
        if (type(intent_id) is not str or not intent_id.startswith("fixture_")
                or len(intent_id) > 64):
            raise DataValidationError("bounded paper fixture intent ID required")
        if type(events) is not tuple or len(events) > MAX_FIXTURE_EVENTS:
            raise DataValidationError("bounded immutable paper event batch required")
        if any(type(event) is not PaperOrderEvent for event in events):
            raise DataValidationError("paper event batch contains wrong type")
        cutoff = _utc_ms(as_of_ms, "as_of_ms")
        with self._transaction() as conn:
            previous = self._checked_entry(conn, intent_id)
            if cutoff < previous.snapshot.as_of_ms:
                raise DataValidationError("paper checkpoint cannot go backwards")
            known = {e.event_id: _event_json(e) for e in previous.events}
            added: list[PaperOrderEvent] = []
            last_time = previous.events[-1].event_at_ms if previous.events else None
            for event in events:
                payload = _event_json(event)
                old = known.get(event.event_id)
                if old is not None:
                    if payload != old:
                        raise DataValidationError("conflicting paper event ID across sessions")
                    continue
                if event.event_at_ms < previous.snapshot.as_of_ms:
                    raise DataValidationError("paper event predates committed checkpoint")
                if last_time is not None and event.event_at_ms < last_time:
                    raise DataValidationError("paper event order must be monotonic")
                known[event.event_id] = payload
                last_time = event.event_at_ms
                added.append(event)
            if len(previous.events) + len(added) > MAX_FIXTURE_EVENTS:
                raise DataValidationError("paper journal event bound exceeded")
            combined = previous.events + tuple(added)
            snapshot = replay_paper_order(
                previous.intent, combined, as_of_ms=cutoff,
            )
            for index, event in enumerate(added, start=len(previous.events) + 1):
                self._insert_event(conn, intent_id, index, event)
            snap_payload = _snapshot_json(snapshot)
            conn.execute(
                """UPDATE paper_order_intents SET checkpoint_as_of_ms=?,
                   event_count=?, snapshot=?, snapshot_sha256=? WHERE intent_id=?""",
                (cutoff, len(combined), snap_payload, _digest(snap_payload), intent_id),
            )
            return PaperJournalEntry(previous.intent, combined, snapshot)

    def load(self, intent_id: str) -> PaperJournalEntry:
        """Reopen and verify hashes, event sequence and complete paper replay."""
        if (type(intent_id) is not str or not intent_id.startswith("fixture_")
                or len(intent_id) > 64):
            raise DataValidationError("bounded paper fixture intent ID required")
        with self._transaction() as conn:
            return self._checked_entry(conn, intent_id)
