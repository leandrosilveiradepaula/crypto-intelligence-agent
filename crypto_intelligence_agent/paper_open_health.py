"""J4/AUTO8: read-only, fail-closed PAPER OPEN/position health.

The AUTO2 order journal and AUTO4 position journal are intentionally separate
SQLite files.  They cannot provide a cross-file atomic snapshot or prove a
venue-native stop.  This module therefore treats every local exit plan as
*hypothetical only* and blocks a new PAPER OPEN whenever an opening fill or a
position needs reconciliation.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from pathlib import Path

from .market_data import DataValidationError
from .paper_margin_receipt import (
    PaperMarginIntentReceipt, META_PREFIX, MAX_RECEIPTS_PER_JOURNAL,
)
from .paper_order_store import (
    SQLitePaperOrderJournal, _TABLES as _ORDER_TABLES, _VERSION as _ORDER_VERSION,
    _intent_json,
)
from .paper_position_inspection import _checked_path, _read_database
from .paper_position_reservations import (
    SQLitePaperPositionJournal, _TABLES as _POSITION_TABLES,
    _VERSION as _POSITION_VERSION, _balance,
)
from .synthetic_order_lifecycle import PaperOrderEffect, PaperOrderStatus
from .synthetic_manual_exit_replay import _utc_ms


class PaperProtectionState(str, Enum):
    CLOSED_FLAT_HYPOTHETICAL_ONLY = "CLOSED_FLAT_HYPOTHETICAL_ONLY"
    PROTECTED_HYPOTHETICAL_ONLY = "PROTECTED_HYPOTHETICAL_ONLY"
    UNPROTECTED = "UNPROTECTED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class PaperOpenFillHealth:
    """Identity evidence only; never an exchange position or native stop."""

    intent_id: str
    position_id: str | None
    protection_state: PaperProtectionState
    reason: str


@dataclass(frozen=True)
class PaperOpenHealth:
    """Conservative local result used only to deny/allow another PAPER intent."""

    fills: tuple[PaperOpenFillHealth, ...]
    new_open_allowed: bool
    reason: str
    cross_database_atomic_snapshot_available: bool = False

    @property
    def closed_flat_paper_only(self) -> bool:
        return bool(self.fills) and all(
            item.protection_state is PaperProtectionState.CLOSED_FLAT_HYPOTHETICAL_ONLY
            for item in self.fills
        )

    @property
    def orders_sent(self) -> bool:
        return False

    @property
    def approved_for_live_use(self) -> bool:
        return False

    @property
    def native_stop_verified(self) -> bool:
        return False

    @property
    def unverified_protection(self) -> bool:
        return any(
            item.protection_state is PaperProtectionState.PROTECTED_HYPOTHETICAL_ONLY
            for item in self.fills
        )


def _verify_locked_order_schema(order_connection) -> None:
    """Match the strict RO reader's schema checks under the order write lock."""
    entries = order_connection.execute(
        "SELECT type, name FROM sqlite_master "
        "WHERE type IN ('table','view','trigger') AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    if (any(row["type"] != "table" for row in entries)
            or {row["name"] for row in entries} != _ORDER_TABLES):
        raise DataValidationError("foreign or incorrect PAPER order journal schema")
    meta = order_connection.execute(
        "SELECT key, value FROM paper_order_meta ORDER BY key"
    ).fetchall()
    keys = {row["key"]: row["value"] for row in meta}
    ordinary = {
        "schema_version", "offline_paper_forward_cursor_v1",
        "paper_operator_kill_switch_v1",
    }
    margin_keys = tuple(key for key in keys if key.startswith(META_PREFIX))
    if (len(keys) != len(meta) or keys.get("schema_version") != _ORDER_VERSION
            or len(margin_keys) > MAX_RECEIPTS_PER_JOURNAL
            or any(key not in ordinary and key not in margin_keys for key in keys)):
        raise DataValidationError("incorrect PAPER order journal version or unknown meta key")
    # Receipt-v1 shares the AUTO2 transaction with the OPEN intent. Never
    # accept forged keys, orphaned metadata, or valid hashes bound to another
    # venue/quantity/intention. Unkeyed SHA is only local integrity evidence.
    for key in margin_keys:
        receipt = PaperMarginIntentReceipt.deserialize(keys[key])
        if receipt.key != key:
            raise DataValidationError("PAPER margin receipt key and identity disagree")
        order = order_connection.execute(
            "SELECT payload,payload_sha256 FROM paper_order_intents WHERE intent_id=?",
            (receipt.intent_id,),
        ).fetchone()
        if order is None:
            raise DataValidationError("orphaned PAPER margin receipt without OPEN")
        from .paper_order_store import _check_digest, _decode_intent
        _check_digest(order["payload"], order["payload_sha256"], "margin receipt intent")
        receipt.verify_intent(_decode_intent(order["payload"]))
    if "offline_paper_forward_cursor_v1" in keys:
        from .offline_paper_durable_cursor import _decode_cursor_envelope
        _decode_cursor_envelope(keys["offline_paper_forward_cursor_v1"])
    if "paper_operator_kill_switch_v1" in keys:
        from .paper_operator_kill_switch import _decode
        _decode(keys["paper_operator_kill_switch_v1"])


def _checked_order_entries(order_connection):
    """Replay every journal row while caller holds a stable order snapshot."""
    rows = order_connection.execute(
        "SELECT intent_id FROM paper_order_intents ORDER BY intent_id LIMIT 4097"
    ).fetchall()
    if len(rows) > 4096:
        raise DataValidationError("PAPER health order audit exceeds resource bound")
    return tuple(
        SQLitePaperOrderJournal._checked_entry(order_connection, row["intent_id"])
        for row in rows
    )


def _order_margin_receipts(order_connection) -> dict[str, PaperMarginIntentReceipt]:
    """Read validated AUTO2 receipts from this SAME order snapshot/lock."""
    rows = order_connection.execute(
        "SELECT key,value FROM paper_order_meta "
        "WHERE key LIKE ? ORDER BY key LIMIT ?",
        (META_PREFIX + "%", MAX_RECEIPTS_PER_JOURNAL + 1),
    ).fetchall()
    if len(rows) > MAX_RECEIPTS_PER_JOURNAL:
        raise DataValidationError("PAPER margin receipt audit resource bound")
    result = {}
    for row in rows:
        receipt = PaperMarginIntentReceipt.deserialize(row["value"])
        if receipt.key != row["key"] or receipt.intent_id in result:
            raise DataValidationError("invalid or duplicate PAPER margin receipt")
        result[receipt.intent_id] = receipt
    return result


def _audit_with_orders(
    orders, position_journal_path: str | Path,
    *, decision_at_ms: int | None = None,
    margin_receipts: dict[str, PaperMarginIntentReceipt] | None = None,
) -> PaperOpenHealth:
    """Inspect local positions; these are never exchange-native protection."""
    if decision_at_ms is not None:
        _utc_ms(decision_at_ms, "PAPER health decision_at_ms")
    with _read_database(
        position_journal_path, _POSITION_TABLES, "paper_position_meta", _POSITION_VERSION,
    ) as position_connection:
        rows = position_connection.execute(
            "SELECT position_id FROM paper_positions ORDER BY position_id LIMIT 4097"
        ).fetchall()
        if len(rows) > 4096:
            raise DataValidationError("PAPER health position audit exceeds resource bound")
        # _read verifies canonical digest, event replay, position indexes and
        # quantity conservation; do not replace it with unchecked SQL.
        records = tuple(
            SQLitePaperPositionJournal._read(position_connection, row["position_id"])
            for row in rows
        )
        if decision_at_ms is not None and any(
            record.as_of_ms > decision_at_ms for record in records
        ):
            raise DataValidationError('future PAPER position checkpoint is not causal')
        # A dangling index may be invisible to per-position replay. Always
        # reject a journal with orphaned intent->position references.
        orphan = position_connection.execute(
            "SELECT 1 FROM paper_position_order_ids i "
            "LEFT JOIN paper_positions p ON i.position_id=p.position_id "
            "WHERE p.position_id IS NULL LIMIT 1"
        ).fetchone()
        if orphan is not None:
            raise DataValidationError("PAPER position journal has orphaned order index")

    positions_by_open: dict[str, list[object]] = {}
    for record in records:
        positions_by_open.setdefault(record.opening_intent.intent_id, []).append(record)
    fills: list[PaperOpenFillHealth] = []
    filled_ids: set[str] = set()
    for entry in orders:
        if decision_at_ms is not None and entry.snapshot.as_of_ms > decision_at_ms:
            raise DataValidationError("future PAPER order checkpoint is not causal")
        if entry.intent.effect is PaperOrderEffect.REDUCE_ONLY:
            if entry.snapshot.requires_reconciliation:
                fills.append(PaperOpenFillHealth(
                    entry.intent.intent_id, None, PaperProtectionState.UNKNOWN,
                    "unresolved_order_journal_reduce_only",
                ))
            continue
        if entry.intent.effect is not PaperOrderEffect.OPEN or entry.snapshot.filled_total_units == 0:
            continue
        filled_ids.add(entry.intent.intent_id)
        matches = positions_by_open.get(entry.intent.intent_id, [])
        if len(matches) != 1:
            fills.append(PaperOpenFillHealth(
                entry.intent.intent_id, None, PaperProtectionState.UNPROTECTED,
                "missing_or_duplicate_local_position",
            ))
            continue
        record = matches[0]
        if (_intent_json(record.opening_intent) != _intent_json(entry.intent)
                or record.opening_events != entry.events):
            fills.append(PaperOpenFillHealth(
                entry.intent.intent_id, record.position_id, PaperProtectionState.UNKNOWN,
                "opening_intent_or_fill_events_mismatch",
            ))
            continue
        # A receipt committed atomically to an AUTO2 OPEN must be copied
        # verbatim into its confirmed AUTO4 position. Separate files cannot
        # be read atomically; a mismatch is UNKNOWN, never a valid stop.
        expected_receipt = (margin_receipts or {}).get(entry.intent.intent_id)
        if record.opening_margin_intent != expected_receipt:
            fills.append(PaperOpenFillHealth(
                entry.intent.intent_id, record.position_id, PaperProtectionState.UNKNOWN,
                "opening_margin_receipt_cross_journal_mismatch",
            ))
            continue
        if entry.snapshot.requires_reconciliation:
            fills.append(PaperOpenFillHealth(
                entry.intent.intent_id, record.position_id, PaperProtectionState.UNKNOWN,
                "opening_order_not_terminal",
            ))
            continue
        # Reuse canonical AUTO4 replay, with exact Decimal conservation.
        balance = _balance(record)
        if any(
            exit_order.snapshot.requires_reconciliation
            or exit_order.snapshot.status not in (
                PaperOrderStatus.FILLED, PaperOrderStatus.CANCELLED,
                PaperOrderStatus.REJECTED,
            )
            for exit_order in balance.exit_orders
        ):
            fills.append(PaperOpenFillHealth(
                entry.intent.intent_id, record.position_id, PaperProtectionState.UNKNOWN,
                "unresolved_paper_reduce_only_exit",
            ))
        elif (balance.initial_confirmed_units > Decimal(0)
              and balance.confirmed_remaining_units == Decimal(0)
              and balance.reserved_unfilled_units == Decimal(0)
              and balance.unreserved_units == Decimal(0)
              and balance.runner_unallocated_units == Decimal(0)
              and balance.runner_filled_units == balance.runner_floor_units
              and balance.filled_exit_units == balance.initial_confirmed_units):
            fills.append(PaperOpenFillHealth(
                entry.intent.intent_id, record.position_id,
                PaperProtectionState.CLOSED_FLAT_HYPOTHETICAL_ONLY,
                "explicit_reduce_only_fills_fully_flat_paper_only",
            ))
        else:
            fills.append(PaperOpenFillHealth(
                entry.intent.intent_id, record.position_id,
                PaperProtectionState.PROTECTED_HYPOTHETICAL_ONLY,
                "synthetic_exit_plan_is_not_native_stop",
            ))
    for opening_id, matches in positions_by_open.items():
        if opening_id not in filled_ids:
            for record in matches:
                fills.append(PaperOpenFillHealth(
                    opening_id, record.position_id, PaperProtectionState.UNKNOWN,
                    "position_has_no_matching_filled_open_snapshot",
                ))
    if not fills:
        return PaperOpenHealth((), True, "no_filled_open_or_position_requires_protection")
    states = {item.protection_state for item in fills}
    if states == {PaperProtectionState.CLOSED_FLAT_HYPOTHETICAL_ONLY}:
        return PaperOpenHealth(tuple(fills), True, "all_paper_positions_fully_flat_hypothetical_only")
    if PaperProtectionState.UNKNOWN in states:
        reason = "paper_open_health_unknown"
    elif PaperProtectionState.UNPROTECTED in states:
        reason = "paper_open_unprotected"
    else:
        reason = "paper_open_unverified_protection"
    return PaperOpenHealth(tuple(fills), False, reason)


def _audit_paper_open_health_locked(
    order_connection, order_journal_path: str | Path,
    position_journal_path: str | Path, *, decision_at_ms: int,
) -> PaperOpenHealth:
    """Used only during the order journal BEGIN IMMEDIATE transaction.

    By reading the OPEN rows under the SAME write lock as the prospective
    reservation, no other AUTO2 writer can insert a FILL in the health->OPEN
    gap. AUTO4 remains an independently read SQLite file, not an atomic
    cross-database snapshot; protection remains unverified.
    """
    if _checked_path(order_journal_path) == _checked_path(position_journal_path):
        raise DataValidationError("PAPER order and position health sources must be independent")
    _verify_locked_order_schema(order_connection)
    return _audit_with_orders(
        _checked_order_entries(order_connection), position_journal_path,
        decision_at_ms=decision_at_ms,
        margin_receipts=_order_margin_receipts(order_connection),
    )


def audit_paper_open_health(
    order_journal_path: str | Path, position_journal_path: str | Path,
    *, decision_at_ms: int | None = None,
) -> PaperOpenHealth:
    """Read-only independent diagnostic (not a reservation authorization).

    For a reservation use the order-journal guarded method so the health
    check and eventual OPEN insert happen under one order-file write lock.
    """
    if _checked_path(order_journal_path) == _checked_path(position_journal_path):
        raise DataValidationError("PAPER order and position health sources must be independent")
    with _read_database(
        order_journal_path, _ORDER_TABLES, "paper_order_meta", _ORDER_VERSION,
    ) as order_connection:
        return _audit_with_orders(
            _checked_order_entries(order_connection), position_journal_path,
            decision_at_ms=decision_at_ms,
            margin_receipts=_order_margin_receipts(order_connection),
        )
