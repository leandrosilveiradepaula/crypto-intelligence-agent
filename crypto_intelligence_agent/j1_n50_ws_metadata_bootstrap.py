"""J1/D317: owner-only one-time Bybit V5 metadata ingress into D316 cache.

This is the missing network-to-cache bridge for the D287 dynamic N50:
read an ALREADY sealed private rank, capture up to four paginated public
instrument metadata GETs via the existing D314 client, then persist only
an independently revalidated immutable owner cache. No KLINE REST, WS,
systemd, trading or restart. 10006 is never retried.
"""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import stat
import time
from typing import Any, Callable, Iterator

from .bybit_public_j1_transport import BoundedBybitPublicClient
from .bybit_ws_owner_lock import _safe_stat
from .j1_n50_ws_dynamic_scope import capture_n50_dynamic_ws_metadata_once
from .j1_n50_ws_private_cache import (
    FILE_NAME as WS_CACHE_NAME, cache_n50_ws_dynamic_admission_once,
)
from .j1_n50_ws_cached_runner import _HALT_REST_ROOT
from .market_data import DataGapError, DataValidationError
from scripts.run_j1_current_ranked_epoch_once import load_private_ranked_scope

_LOCK_NAME = ".n50-ws-metadata-bootstrap.lock"
_MAX_POST_CATALOG_AGE_MS = 15 * 60_000


def _report(status: str) -> dict[str, Any]:
    return {
        "schema_version": "j1-n50-ws-owner-metadata-bootstrap-v1",
        "status": status,
        "failure_category": None,
        "catalog_gets": 0,
        "selected_contracts": 0,
        "ranked_scope_sha256": None,
        "ws_metadata_sha256": None,
        "private_cache_written": False,
        "private_cache_sha256": None,
        "websocket_connections_opened": 0,
        "kline_rest_gets": 0,
        "rest_database_modified": False,
        "systemd_modified": False,
        "marketwide_top50_verified": False,
        "crypto_identity_independently_verified": False,
        "source_authenticated": False,
        "live_trading_authorized": False,
        "orders_sent": False,
    }


@contextmanager
def _exclusive_metadata_ingress(ws_directory: Path) -> Iterator[None]:
    """A separate nonblocking POSIX owner lease around GET and O_EXCL write."""
    from fcntl import LOCK_EX, LOCK_NB, LOCK_UN, flock

    _safe_stat(ws_directory, directory=True)
    lock = ws_directory / _LOCK_NAME
    fd = os.open(
        lock, os.O_RDWR | os.O_CREAT
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0), 0o600,
    )
    try:
        inside = os.fstat(fd)
        if (not stat.S_ISREG(inside.st_mode)
                or inside.st_uid != os.geteuid()
                or stat.S_IMODE(inside.st_mode) != 0o600
                or inside.st_nlink != 1):
            raise DataValidationError("N50 WS metadata owner lock unsafe")
        flock(fd, LOCK_EX | LOCK_NB)
        on_path = _safe_stat(lock, directory=False)
        if (on_path.st_dev, on_path.st_ino) != (inside.st_dev, inside.st_ino):
            raise DataGapError("N50 WS metadata owner lock changed")
        try:
            yield
        finally:
            flock(fd, LOCK_UN)
    finally:
        os.close(fd)


def cache_current_n50_ws_metadata_once(
    *, manifest_directory: Path, ws_directory: Path,
    allow_public_network: bool = False,
    confirm_region_and_personal_research: bool = False,
    enable_n50_ws_metadata_capture: bool = False,
    allow_private_manifest_read: bool = False,
    allow_private_ws_cache_write: bool = False,
    client: BoundedBybitPublicClient | None = None,
    clock_ms: Callable[[], int] = lambda: time.time_ns() // 1_000_000,
) -> dict[str, Any]:
    """One strict owner bridge, never starting a feed or modifying REST data."""
    out = _report("ws_metadata_bootstrap_optin_required")
    if not all((
        allow_public_network is True,
        confirm_region_and_personal_research is True,
        enable_n50_ws_metadata_capture is True,
        allow_private_manifest_read is True,
        allow_private_ws_cache_write is True,
    )):
        return out
    out["status"] = "ws_metadata_bootstrap_preflight_abstain"
    if (os.name != "posix" or os.getuid() != os.geteuid()
            or os.geteuid() == 0
            or not isinstance(manifest_directory, Path)
            or not isinstance(ws_directory, Path)
            or not manifest_directory.is_absolute()
            or not ws_directory.is_absolute()
            or ".." in manifest_directory.parts or ".." in ws_directory.parts
            or manifest_directory == ws_directory
            or ws_directory in manifest_directory.parents
            or manifest_directory in ws_directory.parents
            or ws_directory == _HALT_REST_ROOT
            or _HALT_REST_ROOT in ws_directory.parents
            or ws_directory in _HALT_REST_ROOT.parents
            or not callable(clock_ms)
            or client is not None and type(client) is not BoundedBybitPublicClient):
        return out
    try:
        # No symlinked ancestor may redirect WS output into REST HALT.
        if (manifest_directory.resolve(strict=True) != manifest_directory
                or ws_directory.resolve(strict=True) != ws_directory):
            return out
        _safe_stat(manifest_directory, directory=True)
        _safe_stat(ws_directory, directory=True)
        with _exclusive_metadata_ingress(ws_directory):
            # Refuse cached/stale scope BEFORE GET: never waste provider quota
            # or overwrite historical metadata in this owner WS epoch.
            cache_file = ws_directory / WS_CACHE_NAME
            if cache_file.exists() or cache_file.is_symlink():
                out["status"] = "ws_metadata_cache_exists_no_get"
                return out
            now = clock_ms()
            if type(now) is not int or now <= 0:
                return out
            ranked = load_private_ranked_scope(
                manifest_directory, now_ms=now,
            )
            post = ranked["catalog_post_observed_at_ms"]
            if not post <= now <= post + _MAX_POST_CATALOG_AGE_MS:
                out["status"] = "ws_metadata_capture_window_expired_no_get"
                return out
            received = capture_n50_dynamic_ws_metadata_once(
                ranked_scope=ranked, allow_public_network=True,
                confirm_region_and_personal_research=True,
                enable_n50_ws_metadata_capture=True, owner_ok=True,
                client=client, clock_ms=clock_ms,
            )
            out["catalog_gets"] = received.requests_attempted
            if received.status != "dynamic_n50_ws_metadata_captured_research_only":
                out["status"] = "ws_metadata_capture_abstain_no_retry"
                out["failure_category"] = received.failure_category
                return out
            if (received.admission is None
                    or type(received.instrument_pages) is not tuple
                    or type(received.requested_cursors) is not tuple
                    or type(received.page_received_at_ms) is not tuple):
                out["status"] = "ws_metadata_capture_missing_receipts"
                return out
            stored = cache_n50_ws_dynamic_admission_once(
                directory=ws_directory, ranked_scope=ranked,
                instrument_pages=received.instrument_pages,
                requested_cursors=received.requested_cursors,
                page_received_at_ms=received.page_received_at_ms,
                captured_at_ms=clock_ms(),
                allow_private_scope_write=True,
            )
            if (stored.status != "private_n50_ws_admission_cached_immutable"
                    or stored.admission is None
                    or stored.admission.metadata_sha256
                       != received.admission.metadata_sha256):
                out["status"] = "ws_metadata_cache_persist_abstain"
                return out
            out.update(
                status="ws_metadata_owner_n50_cached_for_ws_research",
                selected_contracts=50,
                ranked_scope_sha256=stored.admission.ranked_scope_sha256,
                ws_metadata_sha256=stored.admission.metadata_sha256,
                private_cache_sha256=stored.file_digest_sha256,
                private_cache_written=True,
            )
            return out
    except (OSError, ValueError, TypeError, RuntimeError, DataValidationError,
            DataGapError, OverflowError, KeyError, UnicodeError):
        out["status"] = "ws_metadata_bootstrap_integrity_or_lock_abstain"
        return out
