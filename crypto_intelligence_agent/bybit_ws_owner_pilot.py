"""J1/OPS4: opt-in, owner-only, finite Bybit WS admission and pilot.

No trading, credentials, periodic REST ranking, overwrite of owner REST SQLite,
or automatic service activation. Existing strictly offline validators remain
sources of truth. A cached private scope avoids redoing GETs per WS lease.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
import time
import tempfile
from typing import Callable

from .bybit_closed_stream_cache import (
    HOUR_MS, OfflineReviewedStreamScope,
    SQLiteOfflineClosedStreamJournal, _scope_contract_fingerprint,
)
from .bybit_instrument_volume_contract import BybitLinearInstrumentResearch
from .bybit_paginated_universe_research import (
    BybitInstrumentScanResearch, scan_bybit_linear_instruments_offline,
)
from .bybit_public_j1_transport import (
    BoundedBybitPublicClient, J1BybitCaptureError, instruments_url,
)
from .bybit_ws_owner_lock import _safe_stat, exclusive_owner_ws_writer
from .bybit_ws_supervisor import WSRunBudget, supervise_ws_research
from .market_data import DataGapError, DataValidationError
from .research_registry_catalog import load_reviewed_registry

MAX_CATALOG_PAGES = 4
MAX_PRIVATE_SCOPE_BYTES = 48_000
# Metadata churn must eventually be re-reviewed; no silent refresh may change
# the scope epoch of candles already captured in this separate WS journal.
MAX_PILOT_SCOPE_AGE_MS = 48 * HOUR_MS
_SCOPE_VERSION = "j1-owner-ws-reviewed-scope-v1"
_MEMBER_KEYS = frozenset({
    "symbol", "base_coin", "quote_coin", "settle_coin", "observed_at_ms",
    "launch_time_ms", "max_leverage", "tick_size", "quantity_step",
    "registry_sha256", "source",
})


def _canonical(data: dict) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _catalog_scope(*, client: BoundedBybitPublicClient,
                   clock_ms: Callable[[], int],
                   registry_variant: str = "expanded-52") -> tuple[OfflineReviewedStreamScope, int]:
    """A bounded FULL paginated catalog scan: no OHLCV or 52-volume GETs."""
    if (type(client) is not BoundedBybitPublicClient or not callable(clock_ms)
            or client.requests_attempted != 0 or registry_variant != "expanded-52"):
        raise DataValidationError("new bounded catalog client and reviewed registry required")
    pages, cursors, received = [], [], []
    cursor: str | None = None
    seen: set[str] = set()
    for _ in range(MAX_CATALOG_PAGES):
        _, payload = client.get(instruments_url(cursor=cursor))
        at = clock_ms()
        if type(at) is not int or at <= 0:
            raise DataValidationError("catalog receipt UTC clock invalid")
        pages.append(payload)
        received.append(at)
        cursors.append(cursor)
        result = payload.get("result")
        if type(result) is not dict:
            raise DataValidationError("catalog result absent")
        next_cursor = result.get("nextPageCursor")
        if next_cursor == "":
            break
        if (type(next_cursor) is not str or not 1 <= len(next_cursor) <= 300
                or not next_cursor.isascii()
                or not all(33 <= ord(ch) <= 126 for ch in next_cursor)
                or next_cursor in seen):
            raise DataValidationError("catalog cursor invalid or duplicated")
        seen.add(next_cursor)
        cursor = next_cursor
    else:
        raise DataGapError("catalog pagination exceeds safe GET budget")
    observed = clock_ms()
    if type(observed) is not int or observed <= 0:
        raise DataValidationError("catalog observation UTC clock invalid")
    scan = scan_bybit_linear_instruments_offline(
        instrument_pages=tuple(pages), requested_cursors=tuple(cursors),
        page_received_at_ms=tuple(received), observed_at_ms=observed,
        registry_variant=registry_variant,
    )
    if not 50 <= len(scan.instruments) <= 52:
        raise DataGapError("reviewed scope below 50 active contracts")
    return OfflineReviewedStreamScope.from_scan(scan, registry_variant=registry_variant), len(pages)


def _scope_bytes(scope: OfflineReviewedStreamScope) -> bytes:
    _scope_contract_fingerprint(scope)
    members = []
    for m in scope.contracts:
        members.append({
            "symbol": m.symbol, "base_coin": m.base_coin,
            "quote_coin": m.quote_coin, "settle_coin": m.settle_coin,
            "observed_at_ms": m.observed_at_ms,
            "launch_time_ms": m.launch_time_ms,
            "max_leverage": format(m.max_leverage, "f"),
            "tick_size": format(m.tick_size, "f"),
            "quantity_step": format(m.quantity_step, "f"),
            "registry_sha256": m.registry_sha256, "source": m.source,
        })
    payload = {"version": _SCOPE_VERSION, "observed_at_ms": scope.observed_at_ms,
               "registry_sha256": scope.registry_sha256,
               "asserted_full_catalog_rows": scope.asserted_full_catalog_rows,
               "contracts": members}
    raw = _canonical(payload)
    wrapped = _canonical({"payload": payload, "sha256": sha256(raw).hexdigest()})
    if len(wrapped) > MAX_PRIVATE_SCOPE_BYTES:
        raise DataValidationError("private reviewed scope exceeds size budget")
    return wrapped


def _write_new_scope(path: Path, scope: OfflineReviewedStreamScope) -> None:
    _safe_stat(path.parent, directory=True)
    data = _scope_bytes(scope)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                     getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0), 0o600)
    except OSError:
        raise DataGapError("private scope must not overwrite existing file") from None
    try:
        with os.fdopen(fd, "wb", closefd=True) as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        # File is newly created. A failure cannot turn it into valid evidence.
        raise DataGapError("private scope write failed") from None


def _object_no_duplicates(items):
    obj = {}
    for key, value in items:
        if key in obj:
            raise DataValidationError("duplicate private scope JSON key")
        obj[key] = value
    return obj


def _read_scope(path: Path, *, now_ms: int) -> OfflineReviewedStreamScope:
    if type(now_ms) is not int or now_ms <= 0:
        raise DataValidationError("private scope evaluation clock invalid")
    _safe_stat(path.parent, directory=True)
    before = _safe_stat(path, directory=False)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(path, flags)
    except OSError:
        raise DataGapError("private scope cannot be opened") from None
    with os.fdopen(fd, "rb") as stream:
        inside = os.fstat(stream.fileno())
        if ((before.st_dev, before.st_ino) != (inside.st_dev, inside.st_ino)
                or inside.st_size > MAX_PRIVATE_SCOPE_BYTES
                or inside.st_nlink != 1 or inside.st_uid != os.getuid()
                or stat.S_IMODE(inside.st_mode) != 0o600):
            raise DataGapError("private scope inode, mode or size invalid")
        raw = stream.read(MAX_PRIVATE_SCOPE_BYTES + 1)
    if not 1 <= len(raw) <= MAX_PRIVATE_SCOPE_BYTES:
        raise DataGapError("private scope JSON empty or oversized")
    try:
        doc = json.loads(raw.decode("ascii"), object_pairs_hook=_object_no_duplicates)
    except (ValueError, UnicodeError, TypeError):
        raise DataValidationError("private scope JSON invalid") from None
    if type(doc) is not dict or set(doc) != {"payload", "sha256"}:
        raise DataValidationError("private scope envelope invalid")
    payload = doc["payload"]
    if (type(payload) is not dict or set(payload) != {
            "version", "observed_at_ms", "registry_sha256",
            "asserted_full_catalog_rows", "contracts"}
            or payload["version"] != _SCOPE_VERSION
            or doc["sha256"] != sha256(_canonical(payload)).hexdigest()
            or _canonical(doc) != raw):
        raise DataValidationError("private scope digest or canonical bytes invalid")
    observed = payload["observed_at_ms"]
    if (type(observed) is not int or observed <= 0 or observed > now_ms
            or now_ms - observed > MAX_PILOT_SCOPE_AGE_MS
            or type(payload["asserted_full_catalog_rows"]) is not int
            or payload["asserted_full_catalog_rows"] < 50
            or type(payload["contracts"]) is not list
            or not 50 <= len(payload["contracts"]) <= 52):
        raise DataGapError("private scope expired, future or incomplete")
    # Reject fabricated/relabelled registry with the canonical catalog loader.
    registry = load_reviewed_registry("expanded-52", as_of_ms=observed)
    if payload["registry_sha256"] != registry.sha256_digest:
        raise DataValidationError("private scope registry digest mismatch")
    contracts = []
    for d in payload["contracts"]:
        if type(d) is not dict or set(d) != _MEMBER_KEYS:
            raise DataValidationError("private scope member structure invalid")
        for key in ("max_leverage", "tick_size", "quantity_step"):
            value = d[key]
            if (type(value) is not str or len(value) > 50
                    or not value.isascii() or not value.replace(".", "").isdecimal()
                    or value.count(".") > 1 or value.startswith("0") and len(value) > 1
                    and not value.startswith("0.")):
                raise DataValidationError("private scope decimal invalid")
        contracts.append(BybitLinearInstrumentResearch(
            symbol=d["symbol"], base_coin=d["base_coin"],
            quote_coin=d["quote_coin"], settle_coin=d["settle_coin"],
            observed_at_ms=d["observed_at_ms"],
            launch_time_ms=d["launch_time_ms"],
            max_leverage=Decimal(d["max_leverage"]),
            tick_size=Decimal(d["tick_size"]),
            quantity_step=Decimal(d["quantity_step"]),
            registry_sha256=d["registry_sha256"], source=d["source"],
        ))
    scan = BybitInstrumentScanResearch(
        observed, registry.sha256_digest, 1,
        payload["asserted_full_catalog_rows"], observed, tuple(contracts),
    )
    scope = OfflineReviewedStreamScope.from_scan(scan, registry_variant="expanded-52")
    _scope_contract_fingerprint(scope)
    return scope


def _write_private_health(directory: Path, report: dict, *, now_ms: int) -> None:
    """Owner-only atomic last-observation snapshot, NEVER a live PID assertion."""
    _safe_stat(directory, directory=True)
    if type(now_ms) is not int or now_ms <= 0:
        raise DataValidationError("private health UTC clock invalid")
    target = directory / "ws-pilot-health.json"
    if target.exists() or target.is_symlink():
        _safe_stat(target, directory=False)
    data = _canonical({"schema": "j1-owner-ws-last-observation-v1",
                       "observed_at_utc_ms": now_ms,
                       "worker_running_verified": False,
                       "report": report})
    if len(data) > 4096:
        raise DataValidationError("private health exceeds output budget")
    fd, tmp_name = tempfile.mkstemp(prefix=".ws-pilot-health-", dir=directory)
    tmp = Path(tmp_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, target)
    finally:
        if tmp.exists():
            tmp.unlink()


@dataclass(frozen=True)
class OwnerWSPilotReport:
    status: str
    catalog_gets: int = 0
    catalog_pages: int = 0
    reviewed_scope_assets: int = 0
    closed_events_appended: int = 0
    missing_24h_assets: int | None = None
    complete_24h_assets: int | None = None
    journal_rows: int | None = None
    last_evaluated_closed_hour_ms: int | None = None
    failure_category: str | None = None

    def sanitized_report(self) -> dict:
        return {
            "status": self.status, "failure_category": self.failure_category,
            "catalog_gets": self.catalog_gets, "catalog_pages": self.catalog_pages,
            "reviewed_scope_assets": self.reviewed_scope_assets,
            "closed_events_appended": self.closed_events_appended,
            "missing_24h_assets": self.missing_24h_assets,
            "complete_24h_assets": self.complete_24h_assets,
            "journal_rows": self.journal_rows,
            "last_evaluated_closed_hour_ms": self.last_evaluated_closed_hour_ms,
            "realtime_stream_verified": False,
            "marketwide_top50_verified": False,
            "source_authenticated": False,
            "live_trading_authorized": False,
            "orders_sent": False,
        }


def run_owner_ws_pilot(*, directory: str | Path,
                       allow_public_network: bool = False,
                       allow_public_websocket: bool = False,
                       allow_private_storage: bool = False,
                       confirm_region_and_personal_research: bool = False,
                       client: BoundedBybitPublicClient | None = None,
                       session_factory=None, budget: WSRunBudget = WSRunBudget(),
                       clock_ms: Callable[[], int] = lambda: time.time_ns() // 1_000_000,
                       monotonic: Callable[[], float] = time.monotonic,
                       sleeper: Callable[[float], None] = time.sleep,
                       ) -> OwnerWSPilotReport:
    """One opt-in lease, no 24/7 restart: explicit gate before any I/O.

    A previous scope file is reloaded (0 new GETs) to keep journal identities
    stable across sessions. On expiration/metadata change it FAILS CLOSED.
    Never synthesize PITs or graft REST candles into this WS-only journal.
    """
    if (os.name != "posix" or allow_public_network is not True
            or allow_public_websocket is not True or allow_private_storage is not True
            or confirm_region_and_personal_research is not True):
        return OwnerWSPilotReport("owner_opt_in_required")
    if (type(budget) is not WSRunBudget or not callable(clock_ms)
            or not callable(monotonic) or not callable(sleeper)
            or (client is not None and type(client) is not BoundedBybitPublicClient)):
        return OwnerWSPilotReport("pilot_arguments_invalid")
    d = Path(directory)
    path = d / "ws-confirmed.sqlite"
    scope_path = d / "ws-reviewed-scope.json"
    gets = pages = count = appended = 0
    transport = client
    try:
        _safe_stat(d, directory=True)
        if path.is_symlink():
            raise DataValidationError("private WS journal must not be symlink")
        if path.exists():
            _safe_stat(path, directory=False)
            journal = SQLiteOfflineClosedStreamJournal(path)
        else:
            journal = SQLiteOfflineClosedStreamJournal.create(path)
        with exclusive_owner_ws_writer(journal=journal, allow_private_ws_writer=True):
            now = clock_ms()
            if scope_path.exists() or scope_path.is_symlink():
                scope = _read_scope(scope_path, now_ms=now)
            else:
                transport = client if client is not None else BoundedBybitPublicClient()
                scope, pages = _catalog_scope(client=transport, clock_ms=clock_ms)
                gets = transport.requests_attempted
                _write_new_scope(scope_path, scope)
            count = len(scope.contracts)
            now = clock_ms()
            decision = now // HOUR_MS * HOUR_MS
            if now < decision + 1000:
                raise DataValidationError("pilot UTC close safety margin required")
            # Audit ALL existing WS rows against stored scope before new writes;
            # no duplicate producer, registry drift or hidden corrupt rows.
            journal.audit(scope=scope, decision_at_ms=decision, as_of_ms=now)
            if session_factory is None:
                from .bybit_public_ws_once import _real_session_factory
                factory = _real_session_factory
            else:
                factory = session_factory
            outcome = supervise_ws_research(
                session_factory=factory, scope=scope, journal=journal,
                budget=budget, clock=monotonic, wall_ms=clock_ms,
                sleeper=sleeper,
            )
            appended = outcome.closed_events_appended
            now = clock_ms()
            decision = now // HOUR_MS * HOUR_MS
            if now < decision + 1000:
                raise DataValidationError("pilot UTC close safety margin required")
            audited = journal.audit(scope=scope, decision_at_ms=decision,
                                    as_of_ms=now)
            if (outcome.sessions_fully_acknowledged == 0 or
                    outcome.status in ("ws_fail_closed_abstain",
                                       "ws_reconnect_budget_exhausted_abstain",
                                       "ws_budget_ended_abstain")):
                state = "ws_pilot_degraded_abstain"
            elif audited.missing_24h_symbols == 0 and audited.complete_24h_symbols == count:
                state = "ws_pilot_sample_rank_ready_not_marketwide"
            else:
                state = "ws_pilot_warming_up_abstain"
            report = OwnerWSPilotReport(state, gets, pages, count, appended,
                                      audited.missing_24h_symbols,
                                      audited.complete_24h_symbols,
                                      audited.persisted_rows, decision,
                                      outcome.failure_category)
            _write_private_health(d, report.sanitized_report(), now_ms=now)
            return report
    except J1BybitCaptureError:
        # 10006 is NOT a retry signal; do not infer a reset delay.
        return OwnerWSPilotReport("ws_pilot_catalog_denied_no_retry",
                                  transport.requests_attempted if transport else gets,
                                  pages, count, appended, failure_category="provider_or_quota")
    except (DataValidationError, DataGapError, OSError, ValueError, TypeError):
        return OwnerWSPilotReport("ws_pilot_fail_closed_abstain",
                                  transport.requests_attempted if transport else gets,
                                  pages, count, appended, failure_category="scope_journal_or_clock")