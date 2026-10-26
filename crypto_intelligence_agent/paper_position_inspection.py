"""J5/PRE4: strictly read-only inspection of an EXISTING local PAPER journal.

The writer constructors in AUTO2/AUTO4 initialize tables and can open write
transactions. Do NOT instantiate them here. Use SQLite mode=ro plus
PRAGMA query_only and reuse their *checked* replay routines. A digest guards
local corruption, NOT proof of exchange authenticity or financial correctness.

No market data, network, account identifiers, trading, migrations or DDL.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Iterator

from .market_data import DataValidationError
from .paper_order_store import (
    SQLitePaperOrderJournal, _TABLES as _ORDER_TABLES,
    _VERSION as _ORDER_VERSION, _intent_json,
)
from .paper_position_reservations import (
    PaperPositionBalance, SQLitePaperPositionJournal, _TABLES as _POSITION_TABLES,
    _VERSION as _POSITION_VERSION, _balance,
)
from .synthetic_position_state import _fixture_id


@dataclass(frozen=True)
class PaperPositionInspection:
    """A local synthetic snapshot, NEVER an exchange position or instruction."""

    balance: PaperPositionBalance
    opening_order_cross_checked: bool

    @property
    def quality(self) -> str:
        return "synthetic_journal_replay_only"

    @property
    def source_provenance(self) -> str:
        return "local_sqlite_digest_not_exchange_authenticated"

    @property
    def mode(self) -> str:
        return "offline_paper"

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
    def financial_pnl_available(self) -> bool:
        return False


def _checked_path(path: str | Path) -> Path:
    if not isinstance(path, (str, Path)):
        raise DataValidationError("existing PAPER journal path required")
    value = str(path)
    if not value or value == ":memory:" or value.startswith("file:") or "\x00" in value:
        raise DataValidationError("in-memory/URI PAPER journals forbidden")
    original = Path(value)
    if original.is_symlink():
        raise DataValidationError("PAPER journal path must not be a symlink")
    try:
        resolved = original.resolve(strict=True)
        if not resolved.is_file():
            raise DataValidationError("PAPER journal must be an existing regular file")
    except (OSError, RuntimeError) as exc:
        raise DataValidationError("PAPER journal missing or inaccessible") from exc
    return resolved


@contextmanager
def _read_database(
    path: str | Path, expected_tables: set[str],
    meta_table: str, expected_version: str,
) -> Iterator[sqlite3.Connection]:
    source = _checked_path(path)
    connection = None
    try:
        # Path.as_uri() percent-encodes special characters before SQLite URI
        # query parameters; mode=ro never creates the target DB.
        connection = sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        entries = connection.execute(
            "SELECT type, name FROM sqlite_master "
            "WHERE type IN ('table','view','trigger') AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        if any(row["type"] != "table" for row in entries):
            raise DataValidationError("foreign view/trigger in PAPER database")
        if {row["name"] for row in entries} != expected_tables:
            raise DataValidationError("wrong or foreign PAPER journal schema")
        meta = connection.execute(
            f"SELECT key, value FROM {meta_table} ORDER BY key"
        ).fetchall()
        if meta_table == "paper_order_meta":
            from .paper_open_health import _verify_locked_order_schema
            _verify_locked_order_schema(connection)
        elif len(meta) != 1 or meta[0]["key"] != "schema_version" or meta[0]["value"] != expected_version:
            raise DataValidationError("unknown PAPER journal version")
        yield connection
    except sqlite3.DatabaseError as exc:
        raise DataValidationError("invalid or unreadable PAPER SQLite journal") from exc
    finally:
        if connection is not None:
            connection.close()


def inspect_paper_position(
    position_path: str | Path, position_id: str,
    *, opening_order_path: str | Path | None = None,
) -> PaperPositionInspection:
    """Snapshot exactly ONE named fictitious position from local persisted fills.

    No wildcard/listing or aggregation across venues/accounts. If the optional
    AUTO2 opening-order database is supplied, it MUST contain exactly matching
    original OPEN intent and events; mismatches fail closed. There is no
    cross-database atomic transaction; independent journals remain research-only.
    """
    _fixture_id(position_id)
    with _read_database(
        position_path, _POSITION_TABLES, "paper_position_meta", _POSITION_VERSION,
    ) as connection:
        # Existing AUTO4 verifies canonical JSON, digest, checkpoint, order IDs,
        # quantities, fills, UNKNOWN reservations and runner conservation.
        record = SQLitePaperPositionJournal._read(connection, position_id)
        balance = _balance(record)

    if opening_order_path is not None:
        if _checked_path(position_path) == _checked_path(opening_order_path):
            raise DataValidationError("order and position journals must be independent")
        with _read_database(
            opening_order_path, _ORDER_TABLES, "paper_order_meta", _ORDER_VERSION,
        ) as conn:
            entry = SQLitePaperOrderJournal._checked_entry(
                conn, record.opening_intent.intent_id,
            )
            if (_intent_json(entry.intent) != _intent_json(record.opening_intent)
                    or entry.events != record.opening_events):
                raise DataValidationError("AUTO2 OPEN does not match stored AUTO4 position")
    return PaperPositionInspection(
        balance=balance,
        opening_order_cross_checked=opening_order_path is not None,
    )


def inspect_paper_positions(
    position_path: str | Path, position_ids: tuple[str, ...],
) -> tuple[PaperPositionInspection, ...]:
    """Read an EXPLICIT collection in ONE local SQLite read transaction.

    No wildcard, automatic listing, financial sum, multiple files or implicit
    account namespace. SQLite holds a single snapshot across every selected
    position: the reader never creates a database and fails all-or-nothing
    if any selected ID, replay, hash or checkpoint is invalid.

    The 128-ID limit is solely a local resource bound, NOT a trading cap.
    """
    if (type(position_ids) is not tuple
            or not 1 <= len(position_ids) <= 128
            or any(type(pid) is not str for pid in position_ids)):
        raise DataValidationError("1-128 explicitly selected PAPER fixture IDs required")
    if len(set(position_ids)) != len(position_ids):
        raise DataValidationError("duplicate PAPER position identity is forbidden")
    for position_id in position_ids:
        _fixture_id(position_id)
    balances = []
    with _read_database(
        position_path, _POSITION_TABLES, "paper_position_meta", _POSITION_VERSION,
    ) as connection:
        for position_id in position_ids:
            # Reuse exactly the same digest/contract/replay checks as PRE4.
            record = SQLitePaperPositionJournal._read(connection, position_id)
            balances.append(PaperPositionInspection(
                balance=_balance(record), opening_order_cross_checked=False,
            ))
    return tuple(balances)
