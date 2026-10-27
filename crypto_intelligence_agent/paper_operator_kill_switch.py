"""Persisted operator pause for LOCAL PAPER OPEN, never an exchange kill switch.

The switch is a bounded, checksummed optional meta record in the existing
AUTO2 SQLite file, committed atomically with each compare-and-swap update.
An unprivileged DB writer can recalculate a checksum: this is integrity
checking, not tamper-proof authentication. No real orders, network or deployment.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import sqlite3

from .market_data import DataValidationError

KEY = "paper_operator_kill_switch_v1"
VERSION = "paper-operator-kill-switch-v1"
_MAX_META = 1024
_MAX_SEQUENCE = 1_000_000_000
_MAX_UTC_MS = 253_402_300_799_999


@dataclass(frozen=True)
class PaperLocalKillSwitchState:
    active: bool
    sequence: int
    changed_at_ms: int
    last_action: str

    @property
    def paper_only(self) -> bool:
        return True

    @property
    def order_submission_enabled(self) -> bool:
        return False

    @property
    def live_trading_authorized(self) -> bool:
        return False

    @property
    def orders_sent(self) -> bool:
        return False


_DEFAULT = PaperLocalKillSwitchState(False, 0, 0, "unset")


def _canonical(value: dict[str, object]) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def _digest(text: str) -> str:
    return sha256(text.encode("ascii")).hexdigest()


def _validate(state: PaperLocalKillSwitchState) -> None:
    if (type(state) is not PaperLocalKillSwitchState
            or type(state.active) is not bool
            or type(state.sequence) is not int
            or not 1 <= state.sequence <= _MAX_SEQUENCE
            or type(state.changed_at_ms) is not int
            or not 0 < state.changed_at_ms <= _MAX_UTC_MS
            or state.last_action not in ("pause", "resume")
            or state.active is not (state.last_action == "pause")
            or state.active is not (state.sequence % 2 == 1)):
        raise DataValidationError("invalid persistent PAPER switch record")


def _envelope(state: PaperLocalKillSwitchState) -> str:
    _validate(state)
    payload = _canonical({
        "version": VERSION, "active": state.active,
        "sequence": state.sequence, "changed_at_ms": state.changed_at_ms,
        "last_action": state.last_action,
    })
    return _canonical({"payload": payload, "sha256": _digest(payload)})


def _decode(raw: str) -> PaperLocalKillSwitchState:
    if type(raw) is not str or not 1 <= len(raw) <= _MAX_META:
        raise DataValidationError("PAPER switch metadata malformed or oversized")
    try:
        envelope = json.loads(raw)
        if (type(envelope) is not dict
                or set(envelope) != {"payload", "sha256"}
                or type(envelope["payload"]) is not str
                or type(envelope["sha256"]) is not str
                or len(envelope["sha256"]) != 64
                or envelope != json.loads(_canonical(envelope))
                or _canonical(envelope) != raw
                or _digest(envelope["payload"]) != envelope["sha256"]):
            raise ValueError("switch metadata envelope invalid")
        payload = json.loads(envelope["payload"])
        if (type(payload) is not dict
                or set(payload) != {
                    "version", "active", "sequence", "changed_at_ms", "last_action",
                }
                or payload["version"] != VERSION
                or _canonical(payload) != envelope["payload"]):
            raise ValueError("switch payload invalid")
        state = PaperLocalKillSwitchState(
            payload["active"], payload["sequence"],
            payload["changed_at_ms"], payload["last_action"],
        )
        _validate(state)
        return state
    except (ValueError, TypeError, KeyError, OverflowError, ArithmeticError) as exc:
        raise DataValidationError("invalid or corrupted PAPER operator kill switch") from exc


def _read_locked(conn: sqlite3.Connection) -> PaperLocalKillSwitchState:
    row = conn.execute("SELECT value FROM paper_order_meta WHERE key=?", (KEY,)).fetchone()
    return _DEFAULT if row is None else _decode(row["value"])


def _write_locked(conn: sqlite3.Connection, state: PaperLocalKillSwitchState) -> None:
    raw = _envelope(state)
    conn.execute(
        "INSERT INTO paper_order_meta(key,value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (KEY, raw),
    )


def _transition_locked(
    conn: sqlite3.Connection, *, pause: bool, expected_sequence: int,
    changed_at_ms: int, acknowledge_resume: bool,
) -> PaperLocalKillSwitchState:
    if (type(pause) is not bool or type(expected_sequence) is not int
            or expected_sequence < 0 or expected_sequence >= _MAX_SEQUENCE
            or type(changed_at_ms) is not int
            or not 0 < changed_at_ms <= _MAX_UTC_MS
            or type(acknowledge_resume) is not bool):
        raise DataValidationError("explicit bounded PAPER switch transition required")
    current = _read_locked(conn)
    if expected_sequence != current.sequence:
        raise DataValidationError("stale PAPER switch sequence; reload status")
    if pause is current.active:
        raise DataValidationError("PAPER switch already has requested state")
    if not pause and acknowledge_resume is not True:
        raise DataValidationError("resuming PAPER openings requires explicit acknowledgement")
    if changed_at_ms < current.changed_at_ms:
        raise DataValidationError("PAPER switch update cannot use older UTC timestamp")
    next_state = PaperLocalKillSwitchState(
        pause, current.sequence + 1, changed_at_ms,
        "pause" if pause else "resume",
    )
    _write_locked(conn, next_state)
    return next_state
