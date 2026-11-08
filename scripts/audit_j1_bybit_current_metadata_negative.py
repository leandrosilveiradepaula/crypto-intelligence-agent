"""J1 D263: retrospective *negative-only* Bybit linear-instrument metadata audit.

No historical PIT identity is inferred from a fresh catalog. A populated
marketRegion / underlyingTicker is a provider TradFi indicator only. Empty
fields cannot prove crypto status. No API calls or writes unless the owner
explicitly opts into one bounded public catalog GET after a read-only replay.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import time
from typing import Any

try:
    import fcntl
except ImportError:  # Offline Windows import remains inert.
    fcntl = None

from crypto_intelligence_agent.bybit_public_j1_transport import (
    BoundedBybitPublicClient, J1BybitCaptureError, instruments_url,
)
from crypto_intelligence_agent.bybit_tradfi_negative_evidence import NEGATIVE_EVIDENCE
from scripts.audit_bybit_marketwide_closed24h import (
    MAX_ROWS, MAX_DB_BYTES, _strict_owner, _stable_json,
)
from scripts.audit_j1_marketwide_checkpoint import _replay, _DB, _LOCK, AuditRejected

_ALLOWED_REGIONS = frozenset({"US", "CN", "HK", "KR"})
_MAX_MARKET_AGE_MS = 120_000


def _default() -> dict[str, Any]:
    return {
        "schema_version": "j1-current-provider-metadata-negative-v1",
        "status": "abstain",
        "requests_attempted": 0,
        "network_accessed": False,
        "database_modified": False,
        "orders_sent": False,
        "crypto_identity_independently_verified": False,
        "marketwide_top50_verified": False,
        "continuous_collector_verified": False,
        "metadata_pit_valid_for_frozen_window": False,
        "provider_negative_is_crypto_allowlist": False,
        "provider_negative_catalog_complete_for_market": False,
    }


def _classify(payload: dict, *,
              frozen_members: frozenset[str],
              captured_at_ms: int,
              received_at_ms: int) -> dict[str, Any]:
    """One entire, non-paginated response, with no symbol disclosure."""
    if (type(payload) is not dict or payload.get("retCode") != 0
            or type(payload.get("result")) is not dict
            or payload["result"].get("category") != "linear"):
        raise AuditRejected("metadata_root_invalid")
    result = payload["result"]
    if result.get("nextPageCursor") not in ("", None):
        raise AuditRejected("metadata_pagination_incomplete")
    rows = result.get("list")
    if type(rows) is not list or not 50 <= len(rows) <= MAX_ROWS:
        raise AuditRejected("metadata_catalog_count_invalid")
    remote_time = payload.get("time")
    if (type(remote_time) is not int or
            not captured_at_ms <= remote_time <= received_at_ms or
            not 0 <= received_at_ms - captured_at_ms <= _MAX_MARKET_AGE_MS):
        raise AuditRejected("metadata_time_invalid")
    seen: set[str] = set()
    basic: set[str] = set()
    indicator: set[str] = set()
    absent: set[str] = set()
    for item in rows:
        if type(item) is not dict:
            raise AuditRejected("metadata_row_invalid")
        sym = item.get("symbol")
        if (type(sym) is not str or not 1 <= len(sym) <= 80
                or not sym.isascii() or not sym.isprintable()
                or any(c.isspace() for c in sym) or sym in seen):
            raise AuditRejected("metadata_symbol_invalid")
        seen.add(sym)
        if (item.get("contractType") != "LinearPerpetual"
                or item.get("status") != "Trading"
                or item.get("quoteCoin") != "USDT"
                or item.get("settleCoin") != "USDT"):
            continue
        base = item.get("baseCoin")
        if (type(base) is not str or sym != base + "USDT"
                or not 1 <= len(base) <= 28 or not base.isascii()
                or not base.isalnum() or base != base.upper()):
            raise AuditRejected("metadata_basic_contract_invalid")
        basic.add(sym)
        region, underlying = item.get("marketRegion"), item.get("underlyingTicker")
        if (region is not None and (type(region) is not str
                                    or region not in _ALLOWED_REGIONS | {""})):
            raise AuditRejected("metadata_region_invalid")
        if (underlying is not None and (type(underlying) is not str
                                       or len(underlying) > 80
                                       or not underlying.isascii()
                                       or not underlying.isprintable())):
            raise AuditRejected("metadata_underlying_invalid")
        # Null/absent indicator fields yield unknown, NOT crypto approval.
        if region is None or underlying is None:
            absent.add(sym)
        elif region or underlying:
            indicator.add(sym)
    overlap = basic & frozen_members
    documented = frozenset(NEGATIVE_EVIDENCE)
    return {
        "catalog_rows": len(rows),
        "current_basic_contract_count": len(basic),
        "frozen_basic_contract_count": len(frozen_members),
        "current_frozen_contract_overlap_count": len(overlap),
        "frozen_missing_from_current_count": len(frozen_members - basic),
        "current_not_in_frozen_count": len(basic - frozen_members),
        "current_provider_tradfi_indicator_count": len(indicator),
        "frozen_overlap_provider_tradfi_indicator_count": len(indicator & overlap),
        "frozen_overlap_missing_metadata_indicator_count": len(absent & overlap),
        "frozen_overlap_documented_tradfi_negative_count": len(documented & overlap),
        "frozen_overlap_documented_negative_without_provider_indicator_count": len(
            (documented & overlap) - indicator
        ),
        "current_possible_crypto_unverified_count": len(basic - indicator),
        # These are current (post-frozen) metadata observations; no time travel.
        "metadata_pit_valid_for_frozen_window": False,
        "provider_negative_catalog_complete_for_market": False,
        "provider_negative_is_crypto_allowlist": False,
        "crypto_identity_independently_verified": False,
        "marketwide_top50_verified": False,
        "continuous_collector_verified": False,
    }


def audit_current_metadata(*, directory: Path, client: Any,
                           now_ms: Any, allow_public_network: bool = False,
                           confirm_region_and_personal_research: bool = False,
                           owner_ok: bool | None = None) -> dict[str, Any]:
    report = _default()
    stage = "owner_gate"
    allowed = (os.name == "posix" and fcntl is not None
               and os.getuid() == os.geteuid() and os.geteuid() != 0
               ) if owner_ok is None else owner_ok
    if not (allowed and allow_public_network is True
            and confirm_region_and_personal_research is True):
        report["failure_code"] = "owner_opt_in_required"
        return report
    if (not isinstance(directory, Path) or not directory.is_absolute()
            or not callable(now_ms) or client is None):
        report["failure_code"] = "configuration_invalid"
        return report
    try:
        stage = "private_files"
        _strict_owner(directory.parent, directory=True)
        _strict_owner(directory, directory=True)
        database, lock = directory / _DB, directory / _LOCK
        _strict_owner(database, directory=False)
        _strict_owner(lock, directory=False)
        if not 0 < database.stat().st_size <= MAX_DB_BYTES:
            raise AuditRejected("database_size_invalid")
        lock_fd = os.open(lock, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except OSError:
                raise AuditRejected("writer_active") from None
            stage = "sqlite_replay"
            with closing(sqlite3.connect(database.as_uri() + "?mode=ro",
                                         uri=True, timeout=0.1)) as db:
                db.execute("PRAGMA query_only=ON")
                if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise AuditRejected("sqlite_integrity_invalid")
                proof = _replay(db)
                if proof["remaining_contracts"] != 0:
                    raise AuditRejected("frozen_scope_incomplete")
                members = frozenset(json.loads(db.execute(
                    "SELECT members_json FROM scope WHERE id=1"
                ).fetchone()[0]))
            stage = "network"
            start = now_ms()
            if type(start) is not int or start <= 1_600_000_000_000:
                raise AuditRejected("clock_invalid")
            report["network_accessed"] = True
            _, payload = client.get(instruments_url())
            end = now_ms()
            stage = "metadata_validation"
            counts = _classify(payload, frozen_members=members,
                               captured_at_ms=start, received_at_ms=end)
            report.update(counts)
            report["status"] = "current_provider_negative_survey_only"
            report["frozen_capture_window_end_ms"] = proof["capture_window_end_ms"]
            report["current_metadata_observed_at_ms"] = end
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
    except AuditRejected as err:
        report["failure_stage"] = stage
        report["failure_code"] = str(err)
    except (OSError, sqlite3.Error, ValueError, TypeError, OverflowError,
            J1BybitCaptureError):
        report["failure_stage"] = stage
        report["failure_code"] = "current_metadata_or_storage_invalid"
    finally:
        attempted = getattr(client, "requests_attempted", 0)
        report["requests_attempted"] = attempted if type(attempted) is int else 0
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--allow-public-network", action="store_true")
    parser.add_argument("--confirm-region-and-personal-research",
                        action="store_true")
    args = parser.parse_args(argv)
    report = audit_current_metadata(
        directory=args.directory, client=BoundedBybitPublicClient(),
        now_ms=lambda: time.time_ns() // 1_000_000,
        allow_public_network=args.allow_public_network,
        confirm_region_and_personal_research=(
            args.confirm_region_and_personal_research
        ),
    )
    print(_stable_json(report))
    return 0 if report["status"] == "current_provider_negative_survey_only" else 2


if __name__ == "__main__":
    raise SystemExit(main())
