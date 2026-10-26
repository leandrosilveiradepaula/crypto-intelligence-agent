"""J4/AUTO4: atomic aggregate REDUCE_ONLY reservations in a PAPER position.

Separate v1 research SQLite file; NEVER a migration of J4/AUTO2 or J1
storage. Reuses J4/PRE1 partial-exit math and AUTO1's order replay.
Contains no broker transport, keys, real market prices, orders or PnL.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, replace
from decimal import Decimal, localcontext
import json
from pathlib import Path
import re
import sqlite3
from typing import Iterator

from .market_data import DataValidationError
from .paper_order_store import (
    _decode_event, _decode_intent, _digest, _event_json, _intent_json,
)
from .synthetic_manual_exit_replay import _EXACT_CONTEXT, _utc_ms
from .synthetic_order_lifecycle import (
    PaperOrderEffect, PaperOrderEvent, PaperOrderEventKind, PaperOrderIntent,
    PaperOrderSnapshot, PaperOrderStatus, PaperVenue, replay_paper_order,
)
from .synthetic_partial_exits import (
    ExitBasis, SyntheticExitPlan, SyntheticExitTranche,
    plan_synthetic_partial_exits,
)
from .synthetic_position_state import SyntheticSide, _fixture_id

_VERSION = "paper-position-reservations-v1"
_TABLES = {"paper_position_meta", "paper_positions", "paper_position_order_ids"}
_PLAN_VERSION = re.compile(r"[A-Za-z0-9_.:-]{1,80}")
_MAX_EXITS = 128
_MAX_TOTAL_EVENTS = 2048
_MAX_PAYLOAD_BYTES = 1_000_000


def _canonical(value: dict[str, object]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _plan_payload(plan: SyntheticExitPlan) -> dict[str, object]:
    return {
        "initial_units": str(plan.initial_units),
        "residual_floor_percent": str(plan.residual_floor_percent),
        "tranches": [
            {"basis": tranche.basis.value, "percent": str(tranche.percent)}
            for tranche in plan.tranches
        ],
    }


def _decode_plan(value: object) -> SyntheticExitPlan:
    if type(value) is not dict:
        raise DataValidationError("stored paper plan must be object")
    try:
        plan = SyntheticExitPlan(
            initial_units=Decimal(value["initial_units"]),
            residual_floor_percent=Decimal(value["residual_floor_percent"]),
            tranches=tuple(
                SyntheticExitTranche(ExitBasis(t["basis"]), Decimal(t["percent"]))
                for t in value["tranches"]
            ),
        )
        if _plan_payload(plan) != value:
            raise ValueError("noncanonical paper exit plan")
        return plan
    except (KeyError, ValueError, TypeError, ArithmeticError, OverflowError) as exc:
        raise DataValidationError("invalid persisted paper exit plan") from exc


def _unique_events(events: tuple[PaperOrderEvent, ...]) -> tuple[PaperOrderEvent, ...]:
    if type(events) is not tuple or len(events) > 512:
        raise DataValidationError("paper order events require bounded immutable tuple")
    if any(type(e) is not PaperOrderEvent for e in events):
        raise DataValidationError("invalid paper order event type")
    seen: dict[str, str] = {}
    unique: list[PaperOrderEvent] = []
    for event in events:
        payload = _event_json(event)
        if event.event_id in seen:
            if seen[event.event_id] != payload:
                raise DataValidationError("conflicting duplicate paper event")
            continue
        seen[event.event_id] = payload
        unique.append(event)
    return tuple(unique)


@dataclass(frozen=True)
class _PaperExit:
    tranche_step: int
    intent: PaperOrderIntent
    events: tuple[PaperOrderEvent, ...]
    as_of_ms: int


@dataclass(frozen=True)
class _PaperRecord:
    position_id: str
    plan_version: str
    opening_intent: PaperOrderIntent
    opening_events: tuple[PaperOrderEvent, ...]
    plan: SyntheticExitPlan
    as_of_ms: int
    exits: tuple[_PaperExit, ...]


def _serialize(record: _PaperRecord) -> str:
    data = {
        "position_id": record.position_id,
        "plan_version": record.plan_version,
        "opening_intent": json.loads(_intent_json(record.opening_intent)),
        "opening_events": [json.loads(_event_json(e)) for e in record.opening_events],
        "plan": _plan_payload(record.plan),
        "as_of_ms": record.as_of_ms,
        "exits": [
            {
                "tranche_step": x.tranche_step,
                "intent": json.loads(_intent_json(x.intent)),
                "events": [json.loads(_event_json(e)) for e in x.events],
                "as_of_ms": x.as_of_ms,
            }
            for x in record.exits
        ],
    }
    value = _canonical(data)
    if len(value.encode("utf-8")) > _MAX_PAYLOAD_BYTES:
        raise DataValidationError("paper position event payload exceeds resource bound")
    return value


def _deserialize(payload: str) -> _PaperRecord:
    if type(payload) is not str or len(payload.encode("utf-8")) > _MAX_PAYLOAD_BYTES:
        raise DataValidationError("paper position data exceeds limit")
    try:
        value = json.loads(payload)
        if type(value) is not dict:
            raise ValueError("paper position root not an object")
        opening_intent = _decode_intent(_canonical(value["opening_intent"]))
        opening_events = tuple(
            _decode_event(_canonical(x)) for x in value["opening_events"]
        )
        exits = tuple(
            _PaperExit(
                tranche_step=x["tranche_step"],
                intent=_decode_intent(_canonical(x["intent"])),
                events=tuple(_decode_event(_canonical(e)) for e in x["events"]),
                as_of_ms=x["as_of_ms"],
            ) for x in value["exits"]
        )
        record = _PaperRecord(
            position_id=value["position_id"],
            plan_version=value["plan_version"],
            opening_intent=opening_intent,
            opening_events=opening_events,
            plan=_decode_plan(value["plan"]),
            as_of_ms=value["as_of_ms"],
            exits=exits,
        )
        if _serialize(record) != payload:
            raise ValueError("noncanonical paper position")
        return record
    except (KeyError, ValueError, TypeError, ArithmeticError, OverflowError) as exc:
        raise DataValidationError("invalid stored paper position") from exc


@dataclass(frozen=True)
class PaperTrancheBalance:
    step: int
    basis: ExitBasis
    target_units: Decimal
    filled_units: Decimal
    reserved_unfilled_units: Decimal
    unallocated_units: Decimal


@dataclass(frozen=True)
class PaperExitOrderBalance:
    tranche_step: int
    intent: PaperOrderIntent
    events: tuple[PaperOrderEvent, ...]
    snapshot: PaperOrderSnapshot
    reserved_unfilled_units: Decimal


@dataclass(frozen=True)
class PaperPositionBalance:
    position_id: str
    plan_version: str
    venue: PaperVenue
    symbol: str
    side: SyntheticSide
    opening_intent_id: str
    opened_at_ms: int
    as_of_ms: int
    initial_confirmed_units: Decimal
    filled_exit_units: Decimal
    reserved_unfilled_units: Decimal
    confirmed_remaining_units: Decimal
    unreserved_units: Decimal
    runner_floor_units: Decimal
    tranches: tuple[PaperTrancheBalance, ...]
    exit_orders: tuple[PaperExitOrderBalance, ...]

    @property
    def quality(self) -> str:
        return "synthetic_position_reservations_only"

    @property
    def orders_sent(self) -> bool:
        return False

    @property
    def approved_for_live_use(self) -> bool:
        return False

    @property
    def live_trading_authorized(self) -> bool:
        return False

    @property
    def persistent_idempotency_verified(self) -> bool:
        # True local PAPER deduplication does NOT prove exchange exactly-once.
        return False


def _balance(record: _PaperRecord) -> PaperPositionBalance:
    _fixture_id(record.position_id)
    if not isinstance(record.plan_version, str) or not _PLAN_VERSION.fullmatch(record.plan_version):
        raise DataValidationError("paper exit plan version missing/invalid")
    cutoff = _utc_ms(record.as_of_ms, "paper position checkpoint")
    opening = record.opening_intent
    if (type(opening) is not PaperOrderIntent
            or opening.effect is not PaperOrderEffect.OPEN):
        raise DataValidationError("paper position needs explicit opening intent")
    if _unique_events(record.opening_events) != record.opening_events:
        raise DataValidationError("duplicate entry event in durable position")
    opening_replay = replay_paper_order(opening, record.opening_events, as_of_ms=cutoff)
    if (opening_replay.status not in (PaperOrderStatus.FILLED, PaperOrderStatus.CANCELLED)
            or opening_replay.filled_total_units <= 0):
        raise DataValidationError("ACK/UNKNOWN/partial OPEN is not a confirmed paper position")
    with localcontext(_EXACT_CONTEXT):
        initial = opening_replay.filled_total_units
        if record.plan.initial_units != initial:
            raise DataValidationError("paper initial units must equal explicit OPEN fills")
        opened = next(e.event_at_ms for e in record.opening_events
                      if e.kind is PaperOrderEventKind.FILL)
        if cutoff < opened:
            raise DataValidationError("paper checkpoint predates opening fill")
        schedule = plan_synthetic_partial_exits(record.plan)
        if type(record.exits) is not tuple or len(record.exits) > _MAX_EXITS:
            raise DataValidationError("too many paper exit intents")
        filled = [Decimal(0) for _ in schedule.allocations]
        reserved = [Decimal(0) for _ in schedule.allocations]
        seen_orders = {opening.intent_id}
        seen_events = {e.event_id for e in record.opening_events}
        order_states: list[PaperExitOrderBalance] = []
        count = len(record.opening_events)
        for x in record.exits:
            if type(x.tranche_step) is not int or not 1 <= x.tranche_step <= len(filled):
                raise DataValidationError("paper exit references unplanned tranche")
            order = x.intent
            if (type(order) is not PaperOrderIntent
                    or order.effect is not PaperOrderEffect.REDUCE_ONLY
                    or order.venue is not opening.venue
                    or order.symbol != opening.symbol
                    or order.position_side is not opening.position_side
                    or order.created_at_ms < opened
                    or order.created_at_ms > x.as_of_ms
                    or x.as_of_ms > cutoff
                    or order.max_reducible_units is None
                    or order.max_reducible_units > initial):
                raise DataValidationError("paper exit provenance, side or quantity mismatch")
            if order.intent_id in seen_orders:
                raise DataValidationError("paper exit intent reused")
            seen_orders.add(order.intent_id)
            if _unique_events(x.events) != x.events:
                raise DataValidationError("duplicate paper exit event in durable journal")
            for event in x.events:
                if event.event_id in seen_events:
                    raise DataValidationError("paper event ID reused across position orders")
                seen_events.add(event.event_id)
            count += len(x.events)
            if count > _MAX_TOTAL_EVENTS:
                raise DataValidationError("paper position exceeds total event budget")
            replay = replay_paper_order(order, x.events, as_of_ms=x.as_of_ms)
            outstanding = replay.unfilled_units if replay.requires_reconciliation else Decimal(0)
            i = x.tranche_step - 1
            filled[i] += replay.filled_total_units
            reserved[i] += outstanding
            order_states.append(PaperExitOrderBalance(
                x.tranche_step, order, x.events, replay, outstanding,
            ))
        tranches: list[PaperTrancheBalance] = []
        for i, allocation in enumerate(schedule.allocations):
            used = filled[i] + reserved[i]
            if used > allocation.exit_units:
                raise DataValidationError("paper tranche aggregate exit allocation exceeded")
            tranches.append(PaperTrancheBalance(
                i + 1, allocation.basis, allocation.exit_units,
                filled[i], reserved[i], allocation.exit_units - used,
            ))
        total_filled = sum(filled, Decimal(0))
        outstanding_all = sum(reserved, Decimal(0))
        remaining = initial - total_filled
        unreserved = remaining - outstanding_all
        if (unreserved < schedule.residual_floor_units
                or remaining < 0
                or total_filled + outstanding_all > initial):
            raise DataValidationError("paper exits exceed confirmed quantity or runner floor")
    return PaperPositionBalance(
        position_id=record.position_id,
        plan_version=record.plan_version,
        venue=opening.venue, symbol=opening.symbol,
        side=opening.position_side, opening_intent_id=opening.intent_id,
        opened_at_ms=opened, as_of_ms=cutoff,
        initial_confirmed_units=initial,
        filled_exit_units=total_filled,
        reserved_unfilled_units=outstanding_all,
        confirmed_remaining_units=remaining,
        unreserved_units=unreserved,
        runner_floor_units=schedule.residual_floor_units,
        tranches=tuple(tranches), exit_orders=tuple(order_states),
    )


class SQLitePaperPositionJournal:
    """Single-aggregate SQLite transactions for PAPER position exit reservations.

    This schema is intentionally NOT compatible with the AUTO2 order journal;
    both the position, opening fills, exit intents and events share ONE row.
    A legacy journal requires a reviewed explicit future migration, not an
    automatic upgrade or a second non-atomic database.
    """

    def __init__(self, path: str | Path):
        self._path = str(path)
        if (not self._path or self._path == ":memory:"
                or self._path.startswith("file:") or "\x00" in self._path):
            raise ValueError("paper positions need an isolated ordinary SQLite file")
        self._initialize()

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._path, timeout=5)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self):
        with self._transaction() as con:
            tables = {r["name"] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%'"
            )}
            if tables and tables != _TABLES:
                raise DataValidationError("paper position journal refuses legacy/foreign schema")
            con.execute(
                "CREATE TABLE IF NOT EXISTS paper_position_meta "
                "(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            con.execute(
                "CREATE TABLE IF NOT EXISTS paper_positions "
                "(position_id TEXT PRIMARY KEY, payload TEXT NOT NULL, "
                "digest TEXT NOT NULL, checkpoint_at_ms INTEGER NOT NULL)"
            )
            con.execute(
                "CREATE TABLE IF NOT EXISTS paper_position_order_ids "
                "(intent_id TEXT PRIMARY KEY, position_id TEXT NOT NULL "
                "REFERENCES paper_positions(position_id))"
            )
            row = con.execute(
                "SELECT value FROM paper_position_meta WHERE key='schema_version'"
            ).fetchone()
            if row is None:
                if tables:
                    raise DataValidationError("missing paper position schema version")
                con.execute(
                    "INSERT INTO paper_position_meta VALUES ('schema_version', ?)",
                    (_VERSION,),
                )
            elif row["value"] != _VERSION:
                raise DataValidationError("unsupported paper position schema version")

    @staticmethod
    def _read(con: sqlite3.Connection, position_id: str) -> _PaperRecord:
        row = con.execute(
            "SELECT * FROM paper_positions WHERE position_id=?", (position_id,),
        ).fetchone()
        if row is None:
            raise DataValidationError("unknown paper position")
        if _digest(row["payload"]) != row["digest"]:
            raise DataValidationError("paper position integrity digest mismatch")
        record = _deserialize(row["payload"])
        view = _balance(record)
        if record.position_id != row["position_id"] or view.as_of_ms != row["checkpoint_at_ms"]:
            raise DataValidationError("paper position index/checkpoint disagrees with events")
        indexed = {
            item["intent_id"] for item in con.execute(
                "SELECT intent_id FROM paper_position_order_ids WHERE position_id=?",
                (position_id,),
            )
        }
        expected = {record.opening_intent.intent_id} | {
            x.intent.intent_id for x in record.exits
        }
        if indexed != expected:
            raise DataValidationError("paper position order index corrupted")
        return record

    @staticmethod
    def _update(con: sqlite3.Connection, record: _PaperRecord) -> PaperPositionBalance:
        view = _balance(record)
        payload = _serialize(record)
        cur = con.execute(
            "UPDATE paper_positions SET payload=?, digest=?, checkpoint_at_ms=? "
            "WHERE position_id=?",
            (payload, _digest(payload), record.as_of_ms, record.position_id),
        )
        if cur.rowcount != 1:
            raise DataValidationError("paper position vanished during update")
        return view

    def create_position(
        self, *,
        position_id: str,
        opening_intent: PaperOrderIntent,
        opening_events: tuple[PaperOrderEvent, ...],
        exit_plan: SyntheticExitPlan,
        plan_version: str,
        as_of_ms: int,
    ) -> PaperPositionBalance:
        """Materialize position ONLY from confirmed fictitious entry fills."""
        _fixture_id(position_id)
        if type(exit_plan) is not SyntheticExitPlan:
            raise DataValidationError("paper position needs immutable exit plan")
        if type(opening_intent) is not PaperOrderIntent:
            raise DataValidationError("paper opening intent required")
        cutoff = _utc_ms(as_of_ms, "paper checkpoint")
        cleaned = _unique_events(opening_events)
        if len(cleaned) == 0:
            raise DataValidationError("paper position cannot be created from ACK only")
        record = _PaperRecord(
            position_id, plan_version, opening_intent, cleaned, exit_plan,
            cutoff, (),
        )
        view = _balance(record)
        payload = _serialize(record)
        with self._transaction() as con:
            row = con.execute(
                "SELECT position_id FROM paper_positions WHERE position_id=?",
                (position_id,),
            ).fetchone()
            if row is not None:
                old = self._read(con, position_id)
                if _serialize(old) != payload:
                    raise DataValidationError("conflicting paper position registration")
                return _balance(old)
            try:
                con.execute(
                    "INSERT INTO paper_positions VALUES (?,?,?,?)",
                    (position_id, payload, _digest(payload), cutoff),
                )
                con.execute(
                    "INSERT INTO paper_position_order_ids VALUES (?,?)",
                    (opening_intent.intent_id, position_id),
                )
            except sqlite3.IntegrityError as exc:
                raise DataValidationError("paper entry order already bound to position") from exc
            return view

    def reserve_exit(
        self, position_id: str, tranche_step: int,
        intent: PaperOrderIntent, *, as_of_ms: int,
    ) -> PaperPositionBalance:
        """Reserve globally across all outstanding simulated exits; never POST."""
        _fixture_id(position_id)
        if type(intent) is not PaperOrderIntent:
            raise DataValidationError("validated paper exit intent required")
        cutoff = _utc_ms(as_of_ms, "as_of_ms")
        with self._transaction() as con:
            current = self._read(con, position_id)
            original = _balance(current)
            prior = con.execute(
                "SELECT position_id FROM paper_position_order_ids WHERE intent_id=?",
                (intent.intent_id,),
            ).fetchone()
            if prior is not None:
                if prior["position_id"] != position_id:
                    raise DataValidationError("paper order ID belongs to another position")
                same = next((x for x in current.exits
                             if x.intent.intent_id == intent.intent_id), None)
                if (same is None or same.tranche_step != tranche_step
                        or _intent_json(same.intent) != _intent_json(intent)):
                    raise DataValidationError("conflicting paper exit order reservation")
                return original
            if (cutoff < current.as_of_ms or intent.created_at_ms < current.as_of_ms
                    or intent.created_at_ms > cutoff):
                raise DataValidationError("paper exit reservation is noncausal")
            if (intent.effect is not PaperOrderEffect.REDUCE_ONLY
                    or intent.venue is not original.venue
                    or intent.symbol != original.symbol
                    or intent.position_side is not original.side
                    or intent.max_reducible_units is None
                    or intent.max_reducible_units > original.confirmed_remaining_units):
                raise DataValidationError("paper exit cannot reverse or exceed confirmed position")
            if len(current.exits) >= _MAX_EXITS:
                raise DataValidationError("paper position exit order budget exceeded")
            candidate = replace(
                current, as_of_ms=cutoff,
                exits=current.exits + (_PaperExit(tranche_step, intent, (), cutoff),),
            )
            view = _balance(candidate)
            try:
                con.execute(
                    "INSERT INTO paper_position_order_ids VALUES (?,?)",
                    (intent.intent_id, position_id),
                )
            except sqlite3.IntegrityError as exc:
                raise DataValidationError("paper exit intent already bound") from exc
            self._update(con, candidate)
            return view

    def append_exit_events(
        self, position_id: str, intent_id: str,
        events: tuple[PaperOrderEvent, ...], *, as_of_ms: int,
    ) -> PaperPositionBalance:
        """Advance the whole position atomically; conflicts roll back all writes."""
        _fixture_id(position_id)
        if type(intent_id) is not str or not intent_id.startswith("fixture_"):
            raise DataValidationError("invalid paper exit order ID")
        incoming = _unique_events(events)
        cutoff = _utc_ms(as_of_ms, "as_of_ms")
        with self._transaction() as con:
            current = self._read(con, position_id)
            if cutoff < current.as_of_ms:
                raise DataValidationError("paper position checkpoint cannot regress")
            target = next((x for x in current.exits
                           if x.intent.intent_id == intent_id), None)
            if target is None:
                raise DataValidationError("unbound paper exit intent")
            known = {e.event_id: _event_json(e) for e in target.events}
            additions: list[PaperOrderEvent] = []
            last_time = target.events[-1].event_at_ms if target.events else None
            for event in incoming:
                existing = known.get(event.event_id)
                if existing is not None:
                    if existing != _event_json(event):
                        raise DataValidationError("conflicting paper event reuse")
                    continue
                if event.event_at_ms < current.as_of_ms:
                    raise DataValidationError("late event predates position checkpoint")
                if last_time is not None and event.event_at_ms < last_time:
                    raise DataValidationError("paper exit event out of order")
                known[event.event_id] = _event_json(event)
                additions.append(event)
                last_time = event.event_at_ms
            if len(target.events) + len(additions) > 512:
                raise DataValidationError("paper order has too many events")
            candidate = replace(
                current, as_of_ms=cutoff,
                exits=tuple(
                    replace(x, events=x.events + tuple(additions), as_of_ms=cutoff)
                    if x.intent.intent_id == intent_id else x
                    for x in current.exits
                ),
            )
            return self._update(con, candidate)

    def load(self, position_id: str) -> PaperPositionBalance:
        _fixture_id(position_id)
        with self._transaction() as con:
            return _balance(self._read(con, position_id))
