"""Owner-only PAPER strategy editor: validated, atomic profiles for future sessions.

Configuration is *never* an order or a hot mutation of held positions. The
existing D453 parser remains the single contract for the PAPER engine.
"""
from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
from hashlib import sha256
try:
    import fcntl
except ImportError:  # Windows CI imports the POSIX owner-only module.
    fcntl = None
import json
import os
from pathlib import Path
import stat
import tempfile

from crypto_intelligence_agent.j4_private_paper_ws_operator_d425 import _private_directory
from crypto_intelligence_agent.market_data import DataValidationError
from scripts.run_j2_j4_public_paper_resident_d453 import read_owner_paper_policy

MAX_BYTES = 8192
SCHEMA = "cia-owner-paper-strategy-profile-v1"
RESEARCH_INTS = frozenset(("ema_period", "atr_period", "extrema_period",
    "quote_volume_period", "compression_bars", "baseline_bars", "cooldown_bars"))
RESEARCH_DECIMALS = frozenset(("max_atr_ratio", "min_quote_volume_ratio"))
RESEARCH_STRATEGY = frozenset(("entry_mode", "ema_cross_periods"))
PAPER_DECIMALS = frozenset(("margin_quote", "stop_distance_bps",
    "runner_floor_percent"))
PAPER_INTS = frozenset(("leverage",))
PAPER_LISTS = frozenset(("target_distances_bps", "tranches"))
ALLOWED = {
    "research": RESEARCH_INTS | RESEARCH_DECIMALS |
                RESEARCH_STRATEGY | {"experimental_paper_relaxation"},
    "paper": PAPER_DECIMALS | PAPER_INTS | PAPER_LISTS,
}


def _no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DataValidationError("duplicate PAPER profile field")
        result[key] = value
    return result


def _decode(blob: bytes) -> dict:
    if not 2 <= len(blob) <= MAX_BYTES:
        raise DataValidationError("PAPER profile file size rejected")
    try:
        data = json.loads(blob.decode("ascii"), object_pairs_hook=_no_duplicates,
            parse_constant=lambda _: (_ for _ in ()).throw(
                DataValidationError("PAPER profile nonfinite number")),
            parse_float=lambda _: (_ for _ in ()).throw(
                DataValidationError("PAPER profile float forbidden")))
    except (ValueError, UnicodeError, TypeError) as exc:
        raise DataValidationError("PAPER profile invalid JSON") from exc
    if type(data) is not dict or set(data) != {
        "schema_version", "research", "paper", "risk"
    }:
        raise DataValidationError("PAPER profile structure rejected")
    return data


def _read(path: Path) -> bytes:
    if not isinstance(path, Path) or not path.is_absolute() or path.suffix != ".json":
        raise DataValidationError("absolute owner policy .json required")
    _private_directory(path.parent)
    if path.is_symlink():
        raise DataValidationError("PAPER profile symlink forbidden")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    with os.fdopen(fd, "rb") as fp:
        st = os.fstat(fp.fileno())
        if (not stat.S_ISREG(st.st_mode) or st.st_uid != os.geteuid()
                or stat.S_IMODE(st.st_mode) != 0o600 or st.st_nlink != 1
                or not 2 <= st.st_size <= MAX_BYTES):
            raise DataValidationError("unsafe PAPER profile file")
        return fp.read(MAX_BYTES+1)


def snapshot(path: Path) -> dict:
    raw = _read(path)
    data = _decode(raw)
    read_owner_paper_policy(path)
    return {
        "schema_version": SCHEMA,
        "revision": sha256(raw).hexdigest(),
        "research": data["research"],
        "paper": {
            key: data["paper"][key] for key in
            ("leverage", "margin_quote", "stop_distance_bps",
             "target_distances_bps", "tranches", "runner_floor_percent")
        },
        "applies_to": "future_paper_sessions_only",
        "orders_sent": False,
    }


def _valid_int(value, name: str) -> int:
    if type(value) is not int or value < 0 or value > 500:
        raise DataValidationError("invalid integer: " + name)
    return value


def _valid_decimal(value, name: str) -> str:
    if type(value) is not str or not 1 <= len(value) <= 32:
        raise DataValidationError("invalid decimal string: " + name)
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise DataValidationError("invalid decimal: " + name) from exc
    if not number.is_finite() or number < 0 or number > Decimal("100000"):
        raise DataValidationError("out-of-range decimal: " + name)
    return format(number, "f")


def _apply(document: dict, edits: dict) -> dict:
    if type(edits) is not dict or not edits or set(edits) - set(ALLOWED):
        raise DataValidationError("unknown PAPER profile section")
    doc = json.loads(json.dumps(document))
    for section, values in edits.items():
        if type(values) is not dict or not values or set(values) - ALLOWED[section]:
            raise DataValidationError("unknown PAPER profile setting")
        for key, value in values.items():
            if section == "research":
                if key in RESEARCH_INTS:
                    doc[section][key] = _valid_int(value, key)
                elif key in RESEARCH_DECIMALS:
                    doc[section][key] = _valid_decimal(value, key)
                elif key == "experimental_paper_relaxation":
                    if type(value) is not bool:
                        raise DataValidationError("PAPER relaxation requires boolean")
                    doc[section][key] = value
                elif key == "entry_mode":
                    if type(value) is not str or value not in ("breakout", "ema_cross"):
                        raise DataValidationError("D503 unknown strategy entry mode")
                    doc[section][key] = value
                elif key == "ema_cross_periods":
                    if (type(value) is not list or len(value) != 3
                            or any(type(v) is not int or not 2 <= v <= 120 for v in value)
                            or not value[0] < value[1] < value[2]):
                        raise DataValidationError("D503 invalid EMA crossing periods")
                    doc[section][key] = value
            elif key in PAPER_INTS:
                doc[section][key] = _valid_int(value, key)
            elif key in PAPER_DECIMALS:
                doc[section][key] = _valid_decimal(value, key)
            elif key == "target_distances_bps":
                if type(value) is not list or len(value) != 2:
                    raise DataValidationError("two price targets required")
                doc[section][key] = [_valid_decimal(v, key) for v in value]
            elif key == "tranches":
                if type(value) is not list or len(value) != 2:
                    raise DataValidationError("two exit tranches required")
                for v in value:
                    if type(v) is not dict or set(v) != {"basis", "percent"}:
                        raise DataValidationError("exit tranche structure rejected")
                    if v["basis"] not in ("INITIAL_POSITION", "REMAINING_BALANCE"):
                        raise DataValidationError("exit tranche basis rejected")
                doc[section][key] = [
                    {"basis": v["basis"], "percent": _valid_decimal(v["percent"], "percent")}
                    for v in value
                ]
    p = doc["paper"]
    levels = [Decimal(x) for x in p["target_distances_bps"]]
    if not (Decimal(0) < levels[0] < levels[1]):
        raise DataValidationError("ordered positive PAPER targets required")
    tranches = p["tranches"]
    perc = [Decimal(t["percent"]) for t in tranches]
    # Conservative: allow full closure if both tranches are initial-basis.
    if any(t["basis"] != "INITIAL_POSITION" for t in tranches):
        raise DataValidationError("profile editor currently uses initial-basis tranches")
    if not all(Decimal(0) < x <= 100 for x in perc):
        raise DataValidationError("partial percent out of range")
    if sum(perc) + Decimal(p["runner_floor_percent"]) > 100:
        raise DataValidationError("partials plus runner exceed initial position")
    return doc


@contextmanager
def _owner_lock(home: Path):
    if fcntl is None:
        raise DataValidationError("POSIX owner-only lock unavailable")
    lock = home / ".paper-profile.lock"
    fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def save(path: Path, *, revision: str, edits: dict) -> dict:
    if (type(revision) is not str or len(revision) != 64
            or any(c not in "0123456789abcdef" for c in revision)):
        raise DataValidationError("revision required")
    if os.geteuid() == 0 or os.getuid() != os.geteuid():
        raise DataValidationError("PAPER config save requires owner nonroot")
    home = _private_directory(path.parent)
    with _owner_lock(home):
        previous = _read(path)
        if sha256(previous).hexdigest() != revision:
            raise DataValidationError("profile changed: reload before saving")
        data = _apply(_decode(previous), edits)
        encoded = (json.dumps(data, sort_keys=True, ensure_ascii=True,
                   separators=(",", ":")) + "\n").encode("ascii")
        if len(encoded) > MAX_BYTES:
            raise DataValidationError("PAPER profile exceeds file bound")
        fd, filename = tempfile.mkstemp(prefix="paper-profile-d487-", suffix=".json", dir=home)
        tmp = Path(filename)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(encoded)
                f.flush()
                os.fsync(f.fileno())
            read_owner_paper_policy(tmp)
            os.replace(tmp, path)
            fd_dir = os.open(home, os.O_RDONLY | os.O_DIRECTORY)
            try: os.fsync(fd_dir)
            finally: os.close(fd_dir)
        finally:
            if tmp.exists(): tmp.unlink()
    return snapshot(path)
