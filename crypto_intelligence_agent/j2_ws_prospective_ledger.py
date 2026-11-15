"""J2/J3 #644: local owner-only decision capture BEFORE later WS closed outcomes.

No new market transport or SQLite reader: both stages call existing D624.
One private 0600 file per decision hour, created atomically with no overwrite.
A same-owner file+SHA is NOT independent timestamp attestation or OOS proof.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import os
import re
from pathlib import Path
import stat
import time
from typing import Any

from .bybit_closed_stream_cache import HOUR_MS
from .j2_n50_ws_private_screen import observe_active_private_ws_n50_24closed
from .j2_n50_ws_descriptive_watchlist import build_ws_descriptive_watchlist
from .j3_ws_watchlist_forward_marks import (
    FrozenCandidateReference, FrozenWSWatchlistReference, ForwardCostAssumptions,
    _positive, _digest, _time, _commitment, freeze_ws_watchlist_reference,
    evaluate_ws_watchlist_forward_marks,
)
from .market_data import DataValidationError
from .synthetic_intrabar_barriers import ResearchDirection

LEDGER_ROOT = Path("/home/cia-probe/agent/j2-ws-prospective-private")
_SCHEMA = "j2-ws-owner-decision-ledger-v1"
_MAX_RECORD_BYTES = 8192
_FIELDS = frozenset((
    "schema_version", "decision_end_ms", "registered_at_ms",
    "scope_sha256", "window_sha256", "ws_metadata_sha256", "btc_decision_close",
    "candidates", "decision_commitment_sha256", "record_sha256",
))


def _report(status: str) -> dict[str, Any]:
    return {
        "schema_version": "j2-ws-owner-ledger-status-v1",
        "status": status,
        "capture_records_created": 0,
        "candidates_captured": 0,
        "owner_ws_sqlite_readonly_replayed": False,
        "local_decision_record_consistency_verified": False,
        "prospective_registration_independently_verified": False,
        "marketwide_top50_verified": False,
        "financial_backtest_approved": False,
        "approved_for_signals": False,
        "orders_sent": False,
        "network_requests": 0,
        "database_mutation_statements": 0,
        "systemd_modified": False,
    }


def _canonical(value: dict) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _record_payload(ref: FrozenWSWatchlistReference, ws_metadata_sha256: str) -> dict[str, Any]:
    if type(ref) is not FrozenWSWatchlistReference or _commitment(ref) != ref.decision_commitment_sha256:
        raise DataValidationError("frozen reference commitment mismatched")
    data = {
        "schema_version": _SCHEMA,
        "decision_end_ms": ref.decision_end_ms,
        "registered_at_ms": ref.registered_at_ms,
        "scope_sha256": ref.scope_sha256,
        "window_sha256": ref.window_sha256,
        "ws_metadata_sha256": _digest(ws_metadata_sha256),
        "btc_decision_close": format(ref.btc_decision_close, "f"),
        "candidates": [
            {
                "symbol": x.symbol, "direction": x.direction.value,
                "decision_close": format(x.decision_close, "f"),
            } for x in ref.candidates
        ],
        "decision_commitment_sha256": ref.decision_commitment_sha256,
    }
    data["record_sha256"] = sha256(_canonical(data)).hexdigest()
    return data


def _decode_record(raw: bytes) -> tuple[FrozenWSWatchlistReference, str]:
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= _MAX_RECORD_BYTES:
        raise DataValidationError("owner ledger size out of bounds")
    try:
        obj = json.loads(
            raw.decode("ascii"),
            object_pairs_hook=lambda pairs: _distinct_pairs(pairs),
        )
    except (UnicodeError, ValueError, TypeError, KeyError):
        raise DataValidationError("owner ledger corrupted JSON") from None
    if type(obj) is not dict or set(obj) != _FIELDS or _canonical(obj) != raw:
        raise DataValidationError("owner ledger schema or canonical bytes invalid")
    digest = _digest(obj["record_sha256"])
    copied = {k:v for k,v in obj.items() if k != "record_sha256"}
    if sha256(_canonical(copied)).hexdigest() != digest or obj["schema_version"] != _SCHEMA:
        raise DataValidationError("owner ledger SHA mismatch")
    end = _time(obj["decision_end_ms"], aligned=True)
    registered = _time(obj["registered_at_ms"])
    if not end + 180_000 <= registered < end + HOUR_MS - 60_000:
        raise DataValidationError("owner ledger registration is not causal")
    candidates = obj["candidates"]
    if type(candidates) is not list or len(candidates) > 10:
        raise DataValidationError("owner ledger candidates invalid")
    parsed = []
    seen = set()
    for item in candidates:
        if type(item) is not dict or set(item) != {"symbol","direction","decision_close"}:
            raise DataValidationError("owner ledger candidate shape invalid")
        sym = item["symbol"]
        if (type(sym) is not str or not sym.endswith("USDT")
                or re.fullmatch(r"[A-Z0-9]{1,28}USDT", sym) is None
                or sym in seen):
            raise DataValidationError("owner ledger symbols invalid")
        seen.add(sym)
        try:
            direction = ResearchDirection(item["direction"])
        except (TypeError, ValueError):
            raise DataValidationError("owner ledger direction invalid") from None
        parsed.append(FrozenCandidateReference(
            symbol=sym, direction=direction,
            decision_close=_positive(item["decision_close"], context="decision price"),
        ))
    ref = FrozenWSWatchlistReference(
        end, registered, _digest(obj["scope_sha256"]),
        _digest(obj["window_sha256"]),
        _positive(obj["btc_decision_close"], context="BTC price"),
        tuple(parsed), _digest(obj["decision_commitment_sha256"]),
    )
    if _commitment(ref) != ref.decision_commitment_sha256:
        raise DataValidationError("owner ledger decision commitment altered")
    return ref, _digest(obj["ws_metadata_sha256"])


def _distinct_pairs(pairs: list) -> dict:
    out = {}
    for key, val in pairs:
        if key in out:
            raise DataValidationError("owner ledger duplicate JSON key")
        out[key] = val
    return out


def _owner_guard() -> None:
    if (os.name != "posix" or os.getuid() != os.geteuid()
            or os.geteuid() == 0 or not LEDGER_ROOT.is_absolute()
            or ".." in LEDGER_ROOT.parts):
        raise DataValidationError("unprivileged POSIX owner is required")


def _owner_directory(*, create: bool) -> Path:
    _owner_guard()
    parent = LEDGER_ROOT.parent
    if parent.is_symlink():
        raise DataValidationError("owner ledger parent symlink")
    before = parent.lstat()
    if (not stat.S_ISDIR(before.st_mode) or before.st_uid != os.geteuid()
            or stat.S_IMODE(before.st_mode) & 0o022):
        raise DataValidationError("owner ledger parent not safe")
    if create:
        try:
            os.mkdir(LEDGER_ROOT, 0o700)
        except FileExistsError:
            pass
    st = LEDGER_ROOT.lstat()
    if (not stat.S_ISDIR(st.st_mode) or st.st_uid != os.geteuid()
            or stat.S_IMODE(st.st_mode) != 0o700
            or LEDGER_ROOT.is_symlink()):
        raise DataValidationError("owner ledger directory DAC invalid")
    return LEDGER_ROOT


def _filename(root: Path, end_ms: int) -> Path:
    _time(end_ms, aligned=True)
    return root / f"decision-{end_ms}.json"


def _write_once(ref: FrozenWSWatchlistReference, ws_metadata_sha256: str) -> str:
    root = _owner_directory(create=True)
    name = _filename(root, ref.decision_end_ms)
    obj = _record_payload(ref, ws_metadata_sha256)
    raw = _canonical(obj)
    if len(raw) > _MAX_RECORD_BYTES:
        raise DataValidationError("owner record too large")
    # No clobber on duplicate hour; never chmod/rewrite existing evidence.
    temp = root / (".capture-" + os.urandom(12).hex() + ".tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                 | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
                 0o600)
    linked = False
    try:
        with os.fdopen(fd, "wb") as stream:
            if stat.S_IMODE(os.fstat(stream.fileno()).st_mode) != 0o600:
                raise DataValidationError("owner temporary file mode invalid")
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        # Hard link commits the COMPLETE file atomically; EEXIST = abstain.
        # This operation cannot replace existing evidence, even on retry.
        os.link(temp, name, follow_symlinks=False)
        linked = True
    finally:
        temp.unlink(missing_ok=True)
    if not linked:
        raise DataValidationError("owner decision was not committed")
    dir_fd = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                     | getattr(os, "O_NOFOLLOW", 0))
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)
    return obj["record_sha256"]


def _read_one(decision_end_ms: int) -> tuple[FrozenWSWatchlistReference, str]:
    root = _owner_directory(create=False)
    path = _filename(root, decision_end_ms)
    before = path.lstat()
    if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid()
            or before.st_nlink != 1
            or stat.S_IMODE(before.st_mode) != 0o600
            or path.is_symlink() or not 1 <= before.st_size <= _MAX_RECORD_BYTES):
        raise DataValidationError("owner record DAC or size invalid")
    fd = os.open(path, os.O_RDONLY | getattr(os,"O_NOFOLLOW",0)
                 | getattr(os,"O_CLOEXEC",0))
    with os.fdopen(fd, "rb") as stream:
        inside = os.fstat(stream.fileno())
        if (inside.st_ino,inside.st_dev) != (before.st_ino,before.st_dev):
            raise DataValidationError("owner record changed inode")
        raw = stream.read(_MAX_RECORD_BYTES+1)
    ref, metadata_digest = _decode_record(raw)
    if ref.decision_end_ms != decision_end_ms:
        raise DataValidationError("owner record indexed under different decision hour")
    return ref, metadata_digest


def _private_source(now_ms: int) -> tuple[dict[str, Any], dict[str, str]]:
    """Read only the current immutable D321 owner epoch through D624."""
    snapshot = observe_active_private_ws_n50_24closed(
        allow_private_readonly_research=True,
        include_private_symbols=True,
        include_private_last_closes=True,
        now_ms=now_ms,
    )
    if (snapshot.get("status") != "ws_n50_descriptive_24h_ready"
            or snapshot.get("ws_journal_integrity_replayed") is not True
            or snapshot.get("audited_assets") != 50
            or snapshot.get("eligible_closed_bars_per_asset") != 24):
        raise DataValidationError("owner WS 50x24 not ready")
    end = snapshot.get("latest_closed_end_ms")
    if (type(end) is not int or end != now_ms-now_ms%HOUR_MS
            or not 180_000 <= now_ms-end < HOUR_MS-60_000
            or any(_digest(snapshot.get(name)) != snapshot[name] for name in (
                "ranked_scope_sha256", "ws_metadata_sha256",
                "window_digest_sha256",
            ))):
        raise DataValidationError("WS snapshot clock or provenance mismatch")
    closes = snapshot.get("private_last_closes")
    rows = snapshot.get("research_rows")
    if (type(closes) is not dict or type(rows) is not list
            or len(closes) != 50 or len(rows) != 50
            or set(closes) != {row.get("symbol") for row in rows
                              if type(row) is dict}
            or "BTCUSDT" not in closes):
        raise DataValidationError("owner private closes do not match audited universe")
    if any(type(k) is not str or type(v) is not str for k,v in closes.items()):
        raise DataValidationError("owner private closes types invalid")
    for value in closes.values():
        _positive(value, context="owner last closed WS reference")
    return snapshot, closes


def capture_owner_ws_decision_once(*, allow_private_readonly_research: bool = False,
                                   allow_private_ledger_write: bool = False) -> dict[str, Any]:
    """One self-timestamped capture; no caller-supplied/backdated clock."""
    if allow_private_readonly_research is not True or allow_private_ledger_write is not True:
        return _report("owner_read_and_write_optin_required")
    out = _report("owner_capture_abstain")
    try:
        _owner_guard()
        now = time.time_ns() // 1_000_000
        snapshot, closes = _private_source(now)
        selection = build_ws_descriptive_watchlist(
            snapshot, now_ms=now, include_private_symbols=True,
        )
        if selection.get("status") != "ws_descriptive_watchlist_ready":
            return out
        after = time.time_ns() // 1_000_000
        if now//HOUR_MS != after//HOUR_MS:
            return out
        names = {
            row["symbol"] for side in ("up","down")
            for row in selection[side+"_breakout_watchlist"]
        } | {"BTCUSDT"}
        ref = freeze_ws_watchlist_reference(
            selection,
            registered_at_ms=after,
            ranked_scope_sha256=snapshot["ranked_scope_sha256"],
            decision_closes={symbol:closes[symbol] for symbol in names},
        )
        # A slower writer must not record the prior hour after its cutoff.
        if time.time_ns()//1_000_000 >= ref.decision_end_ms+HOUR_MS-60_000:
            return out
        _write_once(ref, snapshot["ws_metadata_sha256"])
        out.update(
            status="owner_local_decision_captured_not_independent_attestation",
            capture_records_created=1,
            candidates_captured=len(ref.candidates),
            owner_ws_sqlite_readonly_replayed=True,
            local_decision_record_consistency_verified=True,
        )
        return out
    except FileExistsError:
        return _report("owner_decision_hour_already_recorded")
    except (OSError, ValueError, KeyError, TypeError, OverflowError, UnicodeError,
            DataValidationError, InvalidOperation):
        return out


def score_owner_ws_decision_once(*, horizon_bars: int,
                                 costs: ForwardCostAssumptions,
                                 allow_private_readonly_research: bool = False,
                                 allow_private_ledger_read: bool = False) -> dict[str, Any]:
    """Evaluate a persisted prior decision with later owner-audited WS closes.

    Never uses caller-supplied timestamps, arbitrary paths or new SQL readers.
    """
    if allow_private_readonly_research is not True or allow_private_ledger_read is not True:
        return _report("owner_read_optin_required")
    out = _report("owner_score_abstain")
    if type(horizon_bars) is not int or horizon_bars not in (1,4,8):
        return _report("owner_score_horizon_not_supported_for_rotating_epoch")
    if type(costs) is not ForwardCostAssumptions:
        return _report("owner_score_cost_assumptions_required")
    try:
        _owner_guard()
        now = time.time_ns() // 1_000_000
        source, closes = _private_source(now)
        if time.time_ns()//1_000_000//HOUR_MS != now//HOUR_MS:
            return out
        end = source["latest_closed_end_ms"]
        ref, original_metadata = _read_one(end-horizon_bars*HOUR_MS)
        if original_metadata != source["ws_metadata_sha256"]:
            return _report("owner_ws_metadata_changed_forward_abstain")
        names = {item.symbol for item in ref.candidates} | {"BTCUSDT"}
        values = {symbol: closes[symbol] for symbol in names}
        result = evaluate_ws_watchlist_forward_marks(
            ref, horizon_bars=horizon_bars, observed_at_ms=now,
            future_scope_sha256=source["ranked_scope_sha256"],
            future_journal_digest_sha256=source["window_digest_sha256"],
            future_closes=values, costs=costs,
        )
        # The pure J3 evaluator already forces false auth/trading/OOS flags.
        result["owner_local_decision_file_verified"] = True
        result["owner_ws_sqlite_readonly_replayed"] = True
        # The pure grader itself does not access SQL, but the owner wrapper
        # DID replay SQLite read-only to source the current closed marks.
        result["database_accessed"] = True
        result["prospective_registration_independently_verified"] = False
        return result
    except (OSError, ValueError, KeyError, TypeError, OverflowError, UnicodeError,
            DataValidationError, InvalidOperation):
        return out
