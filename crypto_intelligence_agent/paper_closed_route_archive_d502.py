"""D502: immutable owner-only archive of CLOSED PAPER quote routes.

The AUTO4 SQLite journal remains the sole financial ledger. Only a confirmed
flat position can be removed from the bounded D425 subscription manifest.
The caller holds the D425 exclusive writer lock. The archive is one immutable
0700-parent/0600-file per position, safe to retry after a crash.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile

from .j4_private_paper_ws_operator_d425 import (
    _JOURNAL, _decimal, _spread, _owner_file, _private_directory,
)
from .market_data import DataValidationError
from .paper_intrahour_target_step_d387 import _levels_valid
from .paper_position_inspection import inspect_paper_position

_SCHEMA = "paper-closed-route-archive-d502-v1"
_MAX_ARCHIVE_BYTES = 8192
_PREFIX = "paper-closed-route-"


def _identity(position_id: str) -> str:
    if (type(position_id) is not str or not 4 <= len(position_id) <= 128
            or not position_id.isascii()
            or not all(c.isalnum() or c in "_-" for c in position_id)):
        raise DataValidationError("D502 unsafe PAPER archive identity")
    return _PREFIX + sha256(position_id.encode("ascii")).hexdigest() + ".json"


def _canonical(value: dict) -> bytes:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("ascii")


def _unique(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise DataValidationError("D502 duplicate archive field")
        out[key] = value
    return out


def _verified_closed(home: Path, route: dict) -> None:
    if (type(route) is not dict or set(route) != {
            "position_id", "plan_version", "stop_mark_price",
            "target_prices", "max_spread_bps", "runner",
        } or type(route["plan_version"]) is not str
            or not 1 <= len(route["plan_version"]) <= 100
            or type(route["target_prices"]) is not list
            or not 1 <= len(route["target_prices"]) <= 64
            or route["runner"] is not None and type(route["runner"]) is not dict):
        raise DataValidationError("D502 invalid closed route structure")
    _identity(route["position_id"])
    _decimal(route["stop_mark_price"])
    _spread(route["max_spread_bps"])
    targets = tuple(_decimal(x) for x in route["target_prices"])
    balance = inspect_paper_position(
        home / _JOURNAL, route["position_id"],
    ).balance
    if (balance.plan_version != route["plan_version"]
            or len(balance.tranches) != len(targets)
            or not _levels_valid(targets, balance.side)
            or balance.confirmed_remaining_units != 0
            or balance.reserved_unfilled_units != 0
            or balance.filled_exit_units != balance.initial_confirmed_units):
        raise DataValidationError("D502 only reconciled CLOSED positions can be archived")


def read_closed_route_archive(home: Path, position_id: str) -> dict | None:
    """Load one archive by explicit ID; absent is distinct from unsafe."""
    home = _private_directory(home)
    name = _identity(position_id)
    path = home / name
    if not path.exists() and not path.is_symlink():
        return None
    fd = _owner_file(home, name)
    with os.fdopen(fd, "rb") as source:
        raw = source.read(_MAX_ARCHIVE_BYTES + 1)
    if not 2 <= len(raw) <= _MAX_ARCHIVE_BYTES:
        raise DataValidationError("D502 closed route archive size invalid")
    try:
        obj = json.loads(
            raw.decode("ascii"), object_pairs_hook=_unique,
            parse_float=lambda _: (_ for _ in ()).throw(
                DataValidationError("D502 floats forbidden")),
            parse_constant=lambda _: (_ for _ in ()).throw(
                DataValidationError("D502 nonfinite forbidden")),
        )
    except (ValueError, UnicodeError, TypeError) as exc:
        raise DataValidationError("D502 closed archive malformed") from exc
    if (type(obj) is not dict or set(obj) != {"schema", "route", "sha256"}
            or obj["schema"] != _SCHEMA
            or type(obj["route"]) is not dict
            or type(obj["sha256"]) is not str
            or obj["sha256"] != sha256(_canonical(obj["route"])).hexdigest()
            or obj["route"].get("position_id") != position_id):
        raise DataValidationError("D502 archive digest or identity mismatch")
    _verified_closed(home, obj["route"])
    return obj["route"]


def archive_closed_route(home: Path, route: dict) -> bool:
    """Append an immutable sidecar BEFORE removing the route from D425.

    Returns False on an identical, previously committed archive. A conflict
    fails closed; no archive or manifest record is overwritten.
    """
    home = _private_directory(home)
    _verified_closed(home, route)
    name = _identity(route["position_id"])
    before = read_closed_route_archive(home, route["position_id"])
    if before is not None:
        if before != route:
            raise DataValidationError("D502 existing archive conflicts with route")
        return False
    raw = _canonical({
        "schema": _SCHEMA, "route": route,
        "sha256": sha256(_canonical(route)).hexdigest(),
    })
    if not 2 <= len(raw) <= _MAX_ARCHIVE_BYTES:
        raise DataValidationError("D502 archived route too large")
    fd, tmp = tempfile.mkstemp(prefix=".d502-closed-", dir=home)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        # O_EXCL-like durable publication: never replace earlier evidence.
        try:
            os.link(tmp, home / name, follow_symlinks=False)
        except FileExistsError:
            already = read_closed_route_archive(home, route["position_id"])
            if already != route:
                raise DataValidationError("D502 parallel archive conflict")
            return False
        directory_fd = os.open(home, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return True
