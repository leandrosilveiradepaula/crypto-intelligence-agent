"""D316: immutable private cache for one D314 dynamic N50 WS admission.

Store the *causal source pages and ranked D287 manifest* once under owner
0700/0600, then replay D314 from exactly those bytes on each bounded WS
lease without fresh hourly REST GETs. There is no network, daemon, REST DB,
systemd, or trading action in this module. Old epochs are never overwritten.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
from typing import Any

from .bybit_ws_owner_lock import _safe_stat
from .j1_auto_research_epoch import validate_ranked_research_scope
from .j1_n50_ws_dynamic_scope import (
    DynamicN50WSAdmission, admit_dynamic_n50_ws_scope,
)
from .market_data import DataGapError, DataValidationError

FILE_NAME = "ws-dynamic-n50-admission.json"
SCHEMA = "j1-n50-ws-owner-dynamic-admission-cache-v1"
MAX_CACHE_BYTES = 8_000_000
MAX_CACHE_AGE_MS = 48 * 3_600_000


def _canonical(obj: Any) -> bytes:
    return json.dumps(
        obj, sort_keys=True, ensure_ascii=True, allow_nan=False,
        separators=(",", ":"),
    ).encode("ascii")


def _object_no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DataValidationError("private WS metadata duplicate JSON key")
        result[key] = value
    return result


def _owner_directory(path: Path) -> None:
    if (os.name != "posix" or os.getuid() != os.geteuid()
            or os.geteuid() == 0
            or not isinstance(path, Path)
            or not path.is_absolute() or ".." in path.parts):
        raise DataValidationError("owner private N50 WS directory required")
    _safe_stat(path, directory=True)


@dataclass(frozen=True)
class N50WSPrivateAdmission:
    status: str
    admission: DynamicN50WSAdmission | None = field(default=None, repr=False)
    ranked_scope: dict | None = field(default=None, repr=False)
    file_digest_sha256: str | None = None
    file_written: bool = False

    def sanitized_report(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA,
            "status": self.status,
            "selected_contracts": 50 if self.admission else 0,
            "ranked_scope_sha256": (
                self.admission.ranked_scope_sha256 if self.admission else None
            ),
            "metadata_sha256": (
                self.admission.metadata_sha256 if self.admission else None
            ),
            "file_digest_sha256": self.file_digest_sha256,
            "private_cache_file_written": self.file_written,
            "network_requests": 0,
            "websocket_connections_opened": 0,
            "rest_database_modified": False,
            "systemd_modified": False,
            "marketwide_top50_verified": False,
            "crypto_identity_independently_verified": False,
            "source_authenticated": False,
            "live_trading_authorized": False,
            "orders_sent": False,
        }


def _replay_payload(payload: dict, *, current_at_ms: int,
                    expected_ranked_scope_sha256: str | None = None
                    ) -> tuple[dict, DynamicN50WSAdmission]:
    if (type(payload) is not dict
            or set(payload) != {
                "schema_version", "captured_at_ms", "ranked_scope",
                "instrument_pages", "requested_cursors", "page_received_at_ms",
            }
            or payload["schema_version"] != SCHEMA
            or type(current_at_ms) is not int
            or type(payload["captured_at_ms"]) is not int
            or not payload["captured_at_ms"] <= current_at_ms
                <= payload["captured_at_ms"] + MAX_CACHE_AGE_MS
            or type(payload["ranked_scope"]) is not dict
            or type(payload["instrument_pages"]) is not list
            or type(payload["requested_cursors"]) is not list
            or type(payload["page_received_at_ms"]) is not list):
        raise DataValidationError("private WS dynamic snapshot expired or malformed")
    ranked = payload["ranked_scope"]
    members, sha = validate_ranked_research_scope(
        ranked, now_ms=current_at_ms, max_assets=50,
    )
    if (len(members) != 50
            or (expected_ranked_scope_sha256 is not None
                and (type(expected_ranked_scope_sha256) is not str
                     or expected_ranked_scope_sha256 != sha))):
        raise DataValidationError("private WS ranked epoch changed")
    admission = admit_dynamic_n50_ws_scope(
        ranked_scope=ranked,
        instrument_pages=tuple(payload["instrument_pages"]),
        requested_cursors=tuple(payload["requested_cursors"]),
        page_received_at_ms=tuple(payload["page_received_at_ms"]),
        now_ms=payload["captured_at_ms"],
    )
    if admission.ranked_scope_sha256 != sha:
        raise DataValidationError("private WS admission rank digest mismatched")
    return ranked, admission


def cache_n50_ws_dynamic_admission_once(
    *, directory: Path, ranked_scope: dict,
    instrument_pages: tuple[dict, ...],
    requested_cursors: tuple[str | None, ...],
    page_received_at_ms: tuple[int, ...], captured_at_ms: int,
    allow_private_scope_write: bool = False,
) -> N50WSPrivateAdmission:
    """Write exactly one owner-only immutable proof file, no network.

    A complete JSON round-trip is validated by D287 and D314 BEFORE writing.
    The file keeps private public-market symbols; never expose its payload.
    """
    if allow_private_scope_write is not True:
        return N50WSPrivateAdmission("owner_optin_required")
    try:
        _owner_directory(directory)
        file = directory / FILE_NAME
        if file.exists() or file.is_symlink():
            return N50WSPrivateAdmission("cache_exists_no_overwrite")
        if type(captured_at_ms) is not int:
            raise DataValidationError("capture clock invalid")
        payload = json.loads(_canonical({
            "schema_version": SCHEMA,
            "captured_at_ms": captured_at_ms,
            "ranked_scope": ranked_scope,
            "instrument_pages": instrument_pages,
            "requested_cursors": requested_cursors,
            "page_received_at_ms": page_received_at_ms,
        }))
        ranked, admission = _replay_payload(
            payload, current_at_ms=captured_at_ms,
        )
        raw_payload = _canonical(payload)
        wrapped = _canonical({
            "payload": payload,
            "payload_sha256": sha256(raw_payload).hexdigest(),
            "ranked_scope_sha256": admission.ranked_scope_sha256,
            "metadata_sha256": admission.metadata_sha256,
        })
        if not 0 < len(wrapped) <= MAX_CACHE_BYTES:
            raise DataValidationError("private dynamic cache exceeds bound")
        flags = (os.O_WRONLY | os.O_CREAT | os.O_EXCL
                 | getattr(os, "O_NOFOLLOW", 0)
                 | getattr(os, "O_CLOEXEC", 0))
        fd = os.open(file, flags, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(wrapped)
            stream.flush()
            os.fsync(stream.fileno())
        _safe_stat(file, directory=False)
        return N50WSPrivateAdmission(
            "private_n50_ws_admission_cached_immutable", admission,
            ranked, sha256(wrapped).hexdigest(), True,
        )
    except (OSError, ValueError, TypeError, DataValidationError, DataGapError,
            UnicodeError, OverflowError):
        # Preserve any half-written invalid file for owner inspection: never
        # overwrite or delete it, and never mark its data as usable.
        return N50WSPrivateAdmission("private_n50_ws_cache_write_abstain")


def load_n50_ws_dynamic_admission(
    *, directory: Path, current_at_ms: int,
    expected_ranked_scope_sha256: str,
    allow_private_scope_read: bool = False,
) -> N50WSPrivateAdmission:
    """Replay immutable D314 pages from a bounded 0600 owner file, no GET.

    The separate expected digest must come from the current active D287
    manifest: no old epoch may silently become a current WS subscriber.
    """
    if allow_private_scope_read is not True:
        return N50WSPrivateAdmission("owner_optin_required")
    try:
        _owner_directory(directory)
        file = directory / FILE_NAME
        stat_before = _safe_stat(file, directory=False)
        if not 0 < stat_before.st_size <= MAX_CACHE_BYTES:
            raise DataValidationError("private N50 WS cache file size invalid")
        fd = os.open(
            file, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
        )
        with os.fdopen(fd, "rb") as stream:
            stat_inside = os.fstat(stream.fileno())
            if (stat_inside.st_dev != stat_before.st_dev
                    or stat_inside.st_ino != stat_before.st_ino
                    or stat_inside.st_uid != os.geteuid()
                    or not stat.S_ISREG(stat_inside.st_mode)
                    or stat_inside.st_nlink != 1
                    or stat.S_IMODE(stat_inside.st_mode) != 0o600
                    or stat_inside.st_size > MAX_CACHE_BYTES):
                raise DataValidationError("private WS cache inode/mode drift")
            raw = stream.read(MAX_CACHE_BYTES + 1)
        if not 0 < len(raw) <= MAX_CACHE_BYTES:
            raise DataValidationError("private WS cache bytes invalid")
        obj = json.loads(
            raw.decode("ascii"), object_pairs_hook=_object_no_duplicates,
            parse_constant=lambda _: (_ for _ in ()).throw(
                DataValidationError("nonfinite private WS metadata")),
        )
        if (type(obj) is not dict
                or set(obj) != {
                    "payload", "payload_sha256", "ranked_scope_sha256",
                    "metadata_sha256",
                }
                or _canonical(obj) != raw
                or sha256(_canonical(obj["payload"])).hexdigest()
                   != obj["payload_sha256"]):
            raise DataValidationError("private WS cache digest/canonicality invalid")
        ranked, admission = _replay_payload(
            obj["payload"], current_at_ms=current_at_ms,
            expected_ranked_scope_sha256=expected_ranked_scope_sha256,
        )
        if (obj["ranked_scope_sha256"] != admission.ranked_scope_sha256
                or obj["metadata_sha256"] != admission.metadata_sha256):
            raise DataValidationError("private WS cache identities changed")
        return N50WSPrivateAdmission(
            "private_n50_ws_admission_loaded_revalidated", admission,
            ranked, sha256(raw).hexdigest(), False,
        )
    except (OSError, ValueError, TypeError, DataValidationError, DataGapError,
            UnicodeError, OverflowError):
        return N50WSPrivateAdmission("private_n50_ws_cache_read_abstain")
