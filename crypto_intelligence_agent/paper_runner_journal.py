"""J4/RUNNER2: separate durable PAPER trailing replay, never an exchange stop.

The journal stores bounded *synthetic* marks. An immutable PAPER position
checkpoint and explicit trail policy are pinned. Every recovery recomputes
the original pure RUNNER1 result; local SHA is not broker authentication.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3

from .market_data import DataValidationError
from .paper_position_inspection import inspect_paper_position
from .paper_runner_trailing import (
    PaperRunnerMark, PaperRunnerTrailPolicy, PaperRunnerTrailReport,
    PaperRunnerTrailState, inspect_paper_runner_trail,
)

_VERSION = "paper-runner-trail-v1"
_TABLES = {"paper_runner_meta", "paper_runner_state"}
_MAX_BYTES = 50000


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _fingerprint(balance) -> str:
    # Identifies exact confirmed paper runner and reserved orders at checkpoint.
    fields = {
        "position": balance.position_id,
        "plan": balance.plan_version,
        "checkpoint": balance.as_of_ms,
        "opened": balance.opened_at_ms,
        "venue": balance.venue.value,
        "symbol": balance.symbol,
        "side": balance.side.value,
        "initial": str(balance.initial_confirmed_units),
        "remaining": str(balance.confirmed_remaining_units),
        "runner": str(balance.runner_floor_units),
        "step": str(balance.synthetic_lot_step_units),
        "tranches": [
            [t.step, str(t.target_units), str(t.filled_units),
             str(t.reserved_unfilled_units), str(t.unallocated_units)]
            for t in balance.tranches
        ],
        "orders": [
            [x.intent.intent_id, x.snapshot.status.value,
             str(x.snapshot.filled_total_units), str(x.reserved_unfilled_units)]
            for x in balance.exit_orders
        ],
    }
    return sha256(_canonical(fields).encode("ascii")).hexdigest()


def _policy_values(policy: PaperRunnerTrailPolicy) -> list[object]:
    if type(policy) is not PaperRunnerTrailPolicy:
        raise DataValidationError("explicit PAPER runner policy required")
    return [str(policy.activation_bps), str(policy.trail_distance_bps),
            policy.max_tick_gap_ms, policy.max_last_tick_age_ms]


def _checked_path(path: str | Path, *, existing: bool) -> Path:
    if type(path) not in (Path, str):
        raise DataValidationError("local PAPER runner journal path required")
    source = Path(path)
    if (not str(path) or str(path).startswith("file:") or
            str(path) == ":memory:" or "\x00" in str(path) or source.is_symlink()):
        raise DataValidationError("unsafe PAPER runner journal path")
    if existing:
        if not source.is_file():
            raise DataValidationError("PAPER runner journal not found")
    elif source.exists() or not source.parent.is_dir():
        raise DataValidationError("new PAPER runner journal path must be unused")
    return source.resolve(strict=existing)


def _decode(conn: sqlite3.Connection) -> dict[str, object]:
    schema = conn.execute(
        "SELECT type,name FROM sqlite_master WHERE type IN "
        "('table','trigger','view') AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    if any(row[0] != "table" for row in schema) or {
            row[1] for row in schema} != _TABLES:
        raise DataValidationError("invalid PAPER runner journal schema")
    meta = conn.execute("SELECT k,v FROM paper_runner_meta").fetchall()
    if meta != [("version", _VERSION)]:
        raise DataValidationError("unknown PAPER runner journal version")
    rows = conn.execute("SELECT id,payload,digest FROM paper_runner_state").fetchall()
    if len(rows) != 1 or rows[0][0] != 1:
        raise DataValidationError("PAPER runner snapshot count invalid")
    payload, digest = rows[0][1:]
    if type(payload) is not str or len(payload.encode("utf-8")) > _MAX_BYTES:
        raise DataValidationError("PAPER runner payload out of bounds")
    if sha256(payload.encode("ascii")).hexdigest() != digest:
        raise DataValidationError("PAPER runner journal digest mismatch")
    try:
        data = json.loads(payload)
        if (type(data) is not dict or
                set(data) != {"fingerprint", "policy", "marks"} or
                type(data["fingerprint"]) is not str or
                len(data["fingerprint"]) != 64 or
                type(data["policy"]) is not list or
                len(data["policy"]) != 4 or
                type(data["marks"]) is not list or
                not 1 <= len(data["marks"]) <= 256 or
                any(type(x) is not list or len(x) != 3 for x in data["marks"]) or
                _canonical(data) != payload):
            raise ValueError("invalid canonical runner record")
        return data
    except (ValueError, TypeError, OverflowError, UnicodeError) as exc:
        raise DataValidationError("corrupt PAPER runner record") from exc


def _marks(data: dict[str, object]) -> tuple[PaperRunnerMark, ...]:
    try:
        return tuple(PaperRunnerMark(symbol, at, Decimal(price))
                     for symbol, at, price in data["marks"])
    except (ValueError, TypeError, ArithmeticError) as exc:
        raise DataValidationError("invalid saved PAPER runner marks") from exc


def _replay(data: dict[str, object], position_path: str | Path,
            position_id: str, policy: PaperRunnerTrailPolicy,
            as_of_ms: int) -> PaperRunnerTrailReport:
    selected = inspect_paper_position(position_path, position_id)
    if (_fingerprint(selected.balance) != data["fingerprint"]
            or _policy_values(policy) != data["policy"]):
        raise DataValidationError("PAPER runner position/policy changed; re-arm forbidden")
    return inspect_paper_runner_trail(
        selected.balance, _marks(data), policy=policy, as_of_ms=as_of_ms)


def _encode(data: dict[str, object]) -> tuple[str, str]:
    payload = _canonical(data)
    if len(payload.encode("utf-8")) > _MAX_BYTES:
        raise DataValidationError("PAPER runner payload too large")
    return payload, sha256(payload.encode("ascii")).hexdigest()


def start_paper_runner_journal(
    path: str | Path, position_path: str | Path, position_id: str,
    *, policy: PaperRunnerTrailPolicy, first_mark: PaperRunnerMark,
    as_of_ms: int,
) -> PaperRunnerTrailReport:
    """Create a NEW separate research database. Never overwrite an old runner."""
    if type(first_mark) is not PaperRunnerMark:
        raise DataValidationError("explicit first mark required")
    checked = _checked_path(path, existing=False)
    selected = inspect_paper_position(position_path, position_id)
    report = inspect_paper_runner_trail(
        selected.balance, (first_mark,), policy=policy, as_of_ms=as_of_ms)
    if report.state is PaperRunnerTrailState.WAITING_FOR_CONFIRMED_RUNNER:
        raise DataValidationError("unconfirmed PAPER runner cannot be armed")
    data = {
        "fingerprint": _fingerprint(selected.balance),
        "policy": _policy_values(policy),
        "marks": [[first_mark.symbol, first_mark.at_ms, str(first_mark.mark_price_quote)]],
    }
    payload, digest = _encode(data)
    fd = os.open(str(checked), os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
    os.close(fd)
    try:
        with sqlite3.connect(checked) as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("CREATE TABLE paper_runner_meta (k TEXT PRIMARY KEY,v TEXT NOT NULL)")
            conn.execute("CREATE TABLE paper_runner_state (id INTEGER PRIMARY KEY,"
                         "payload TEXT NOT NULL,digest TEXT NOT NULL)")
            conn.execute("INSERT INTO paper_runner_meta VALUES (?,?)", ("version", _VERSION))
            conn.execute("INSERT INTO paper_runner_state VALUES (1,?,?)",(payload,digest))
        return report
    except Exception:
        # Only the exclusively-created file belongs to this call.
        checked.unlink(missing_ok=True)
        raise


def load_paper_runner_journal(
    path: str | Path, position_path: str | Path, position_id: str,
    *, policy: PaperRunnerTrailPolicy, as_of_ms: int,
) -> PaperRunnerTrailReport:
    """Read-only recovery; stale or conflicting position/policy fails closed."""
    checked = _checked_path(path, existing=True)
    try:
        with sqlite3.connect(checked.as_uri() + "?mode=ro", uri=True) as conn:
            conn.execute("PRAGMA query_only=ON")
            conn.execute("BEGIN")
            data = _decode(conn)
            return _replay(data, position_path, position_id, policy, as_of_ms)
    except sqlite3.DatabaseError as exc:
        raise DataValidationError("unreadable PAPER runner journal") from exc


def append_paper_runner_mark(
    path: str | Path, position_path: str | Path, position_id: str,
    mark: PaperRunnerMark, *, policy: PaperRunnerTrailPolicy, as_of_ms: int,
) -> PaperRunnerTrailReport:
    """Transactional mark append. Exact last-tick replay is idempotent.

    Triggered paper stops become immutable: a hypothetical trigger is not
    an execution acknowledgement, so no additional mark can clear it.
    """
    if type(mark) is not PaperRunnerMark:
        raise DataValidationError("typed PAPER runner mark required")
    checked = _checked_path(path, existing=True)
    try:
        with sqlite3.connect(checked.as_uri() + "?mode=rw", uri=True) as conn:
            conn.execute("BEGIN IMMEDIATE")
            data = _decode(conn)
            current_marks = _marks(data)
            previous = _replay(data,position_path,position_id,policy,current_marks[-1].at_ms)
            if mark.at_ms == current_marks[-1].at_ms:
                if mark != current_marks[-1]:
                    raise DataValidationError("conflicting duplicate PAPER runner tick")
                # Exact idempotency still enforces the caller's freshness cutoff.
                return _replay(data,position_path,position_id,policy,as_of_ms)
            if (previous.state is PaperRunnerTrailState.TRIGGERED_HYPOTHETICAL_ONLY
                    or mark.at_ms < current_marks[-1].at_ms
                    or len(current_marks) >= 256):
                raise DataValidationError("runner terminal/reordered/oversized tick")
            new_data = {**data,"marks":data["marks"]+[
                [mark.symbol,mark.at_ms,str(mark.mark_price_quote)]]}
            report = _replay(new_data,position_path,position_id,policy,as_of_ms)
            payload,digest = _encode(new_data)
            conn.execute("UPDATE paper_runner_state SET payload=?,digest=? WHERE id=1",
                         (payload,digest))
            return report
    except sqlite3.DatabaseError as exc:
        raise DataValidationError("unreadable PAPER runner journal") from exc
