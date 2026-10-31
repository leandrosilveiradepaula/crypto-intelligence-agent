"""J5: read-only local PAPER operator status for a mobile PT-BR view.

This is a snapshot of ONE existing AUTO2 SQLite fixture journal, NOT a
broker status, live order control, real position health or HTTP endpoint.
It reuses the strict, read-only SQLite inspector, cursor and pause contracts.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .offline_paper_durable_cursor import _load_cursor, _verify_cursor_orders
from .paper_operator_kill_switch import _read_locked
from .paper_order_store import (
    SQLitePaperOrderJournal, _TABLES as _ORDER_TABLES, _VERSION as _ORDER_VERSION,
)
from .paper_position_inspection import _read_database
from .synthetic_manual_exit_replay import _utc_ms


@dataclass(frozen=True)
class PaperOperatorStatus:
    """Numeric fixture journal evidence; never a certified account snapshot."""

    new_paper_open_paused: bool
    pause_sequence: int
    pause_changed_at_ms: int
    durable_cursor_present: bool
    cursor_sequence: int
    accepted_candle_count: int
    last_closed_candle_at_ms: int | None
    reserved_open_intent_count: int
    pending_or_unresolved_open_count: int
    unknown_open_requires_reconciliation: bool

    @property
    def mode(self) -> str:
        return "offline_paper"

    @property
    def provider_market_data_authenticated(self) -> bool:
        return False

    @property
    def native_stop_verified(self) -> bool:
        return False

    @property
    def financial_pnl_available(self) -> bool:
        return False

    @property
    def live_trading_authorized(self) -> bool:
        return False

    @property
    def order_submission_enabled(self) -> bool:
        return False

    @property
    def orders_sent(self) -> bool:
        return False


def inspect_local_paper_operator_status(
    order_journal_path: str | Path, *, decision_at_ms: int | None = None,
) -> PaperOperatorStatus:
    """Read one consistent SQLite snapshot with ZERO local writes.

    Unknown schema, foreign tables/metadata, broken cursor, missing OPEN,
    forged digest, misindexed order or corrupt replay always fail closed.
    This does not inspect AUTO4 positions or assert native stop protection.
    """
    if decision_at_ms is not None:
        _utc_ms(decision_at_ms, "PAPER operator decision cutoff")
    with _read_database(
        order_journal_path, _ORDER_TABLES, "paper_order_meta", _ORDER_VERSION,
    ) as connection:
        cursor = _load_cursor(connection)
        _verify_cursor_orders(connection, cursor)
        pause = _read_locked(connection)
        if decision_at_ms is not None and (
            (cursor is not None and
             cursor.seal.decision_at_ms > decision_at_ms)
            or pause.changed_at_ms > decision_at_ms
        ):
            raise DataValidationError(
                "PAPER operator cursor or pause is newer than decision cutoff"
            )
        pending, unresolved_unknown = (
            SQLitePaperOrderJournal._pending_open_from_connection(connection)
        )
        return PaperOperatorStatus(
            new_paper_open_paused=pause.active,
            pause_sequence=pause.sequence,
            pause_changed_at_ms=pause.changed_at_ms,
            durable_cursor_present=cursor is not None,
            cursor_sequence=0 if cursor is None else cursor.sequence,
            accepted_candle_count=0 if cursor is None else cursor.seal.candle_count,
            last_closed_candle_at_ms=(
                None if cursor is None else cursor.seal.last_close_time_ms
            ),
            reserved_open_intent_count=(
                0 if cursor is None else len(cursor.open_intent_ids)
            ),
            pending_or_unresolved_open_count=pending,
            unknown_open_requires_reconciliation=unresolved_unknown,
        )
