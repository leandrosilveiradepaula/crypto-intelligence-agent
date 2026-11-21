"""D437 finite Bybit public kline pilot; operator-only and fail-closed.

Never enabled by CI, imports, a timer, or an omitted switch. The input is a
pre-reviewed, private, recent OFFLINE scan manifest, not proof of an exchange
capture. Data remains unverified and must not authorize signals or orders.
"""
from __future__ import annotations

import argparse
from decimal import Decimal
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import time

from crypto_intelligence_agent.bybit_closed_stream_cache import (
    MAX_SCOPE_AGE_MS, OfflineReviewedStreamScope, SQLiteOfflineClosedStreamJournal,
)
from crypto_intelligence_agent.bybit_instrument_volume_contract import BybitLinearInstrumentResearch
from crypto_intelligence_agent.bybit_paginated_universe_research import BybitInstrumentScanResearch
from crypto_intelligence_agent.bybit_ws_supervisor import WSRunBudget
from crypto_intelligence_agent.j2_prospective_bybit_research_d436 import (
    read_projection, run_authorized_public_kline_session,
)
from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.bybit_public_j1_transport import J1BybitCaptureError
from crypto_intelligence_agent.j2_public_btc_scope_d441 import fetch_single_btc_scope_from_public_rest
from scripts.demo_j2_prospective_bybit_research_d436 import CONFIG

_SCHEMA = "d437-reviewed-single-kline-scope-v1"
_MAX_MANIFEST_BYTES = 8192
_DECIMAL = re.compile(r"(?:0|[1-9][0-9]{0,15})(?:\.[0-9]{1,18})?\Z")
_SCOPE_KEYS = frozenset((
    "schema", "registry_variant", "registry_sha256", "observed_at_ms",
    "page_count", "instrument_row_count", "last_server_time_ms", "contracts",
))
_CONTRACT_KEYS = frozenset((
    "symbol", "base_coin", "quote_coin", "settle_coin",
    "observed_at_ms", "launch_time_ms", "max_leverage", "tick_size",
    "quantity_step",
))
_OPTINS = (
    "allow_public_network", "allow_public_websocket",
    "confirm_personal_readonly_research", "confirm_region_eligible",
)


def _reject(message: str):
    raise DataValidationError(message)


def _pairs_unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _reject("D437 duplicate manifest key")
        result[key] = value
    return result


def _positive_decimal(value: object) -> Decimal:
    if type(value) is not str or _DECIMAL.fullmatch(value) is None:
        _reject("D437 decimal text invalid")
    result = Decimal(value)
    if not result.is_finite() or result <= 0:
        _reject("D437 decimal not positive")
    return result


def build_reviewed_scope(raw: bytes, *, now_ms: int) -> OfflineReviewedStreamScope:
    """Validate shape, registered identity and age; never claim live capture."""
    if type(raw) is not bytes or len(raw) > _MAX_MANIFEST_BYTES or len(raw) < 2:
        _reject("D437 bounded manifest required")
    if type(now_ms) is not int or now_ms <= 0:
        _reject("D437 owner clock invalid")
    try:
        obj = json.loads(raw.decode("ascii"), object_pairs_hook=_pairs_unique,
                         parse_float=lambda _: _reject("D437 JSON float forbidden"),
                         parse_constant=lambda _: _reject("D437 JSON constant forbidden"))
    except (UnicodeError, ValueError, TypeError) as exc:
        raise DataValidationError("D437 manifest JSON invalid") from exc
    if type(obj) is not dict or set(obj) != _SCOPE_KEYS or obj["schema"] != _SCHEMA:
        _reject("D437 scope manifest fields invalid")
    observed = obj["observed_at_ms"]
    if (type(observed) is not int or observed <= 0
            or not observed <= now_ms <= observed + MAX_SCOPE_AGE_MS):
        _reject("D437 scope timestamp missing, future or expired")
    if (obj["registry_variant"] != "expanded-13"
            or type(obj["registry_sha256"]) is not str
            or any(type(obj[k]) is not int for k in
                   ("page_count", "instrument_row_count", "last_server_time_ms"))
            or obj["page_count"] < 1
            or obj["instrument_row_count"] < 1
            or not 0 < obj["last_server_time_ms"] <= observed
            or type(obj["contracts"]) is not list
            or len(obj["contracts"]) != 1):
        _reject("D437 single reviewed scope required")
    row = obj["contracts"][0]
    if type(row) is not dict or set(row) != _CONTRACT_KEYS:
        _reject("D437 contract shape invalid")
    if (any(type(row[k]) is not str for k in
            ("symbol", "base_coin", "quote_coin", "settle_coin"))
            or any(type(row[k]) is not int for k in
                   ("observed_at_ms", "launch_time_ms"))):
        _reject("D437 contract field type invalid")
    contract = BybitLinearInstrumentResearch(
        row["symbol"], row["base_coin"], row["quote_coin"],
        row["settle_coin"], row["observed_at_ms"], row["launch_time_ms"],
        _positive_decimal(row["max_leverage"]),
        _positive_decimal(row["tick_size"]),
        _positive_decimal(row["quantity_step"]), obj["registry_sha256"],
    )
    scan = BybitInstrumentScanResearch(
        observed, obj["registry_sha256"], obj["page_count"],
        obj["instrument_row_count"], obj["last_server_time_ms"], (contract,),
    )
    scope = OfflineReviewedStreamScope.from_scan(
        scan, registry_variant=obj["registry_variant"])
    if tuple(x.symbol for x in scope.contracts) != ("BTCUSDT",):
        _reject("D437 BTCUSDT-only research pilot")
    return scope


def _owner_private_directory(path: Path) -> None:
    if os.name != "posix" or not hasattr(os, "geteuid") or os.geteuid() == 0:
        _reject("D437 unprivileged POSIX owner required")
    if path.is_symlink() or not path.is_dir():
        _reject("D437 private directory missing")
    info = path.stat()
    if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
        _reject("D437 private directory ownership or mode invalid")


def read_private_manifest(path: Path, *, now_ms: int) -> OfflineReviewedStreamScope:
    """Owner 0700 parent + 0600 regular file, no links, no changed reads."""
    _owner_private_directory(path.parent)
    if path.is_symlink():
        _reject("D437 manifest symlink forbidden")
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode)
                or before.st_uid != os.geteuid()
                or stat.S_IMODE(before.st_mode) != 0o600
                or before.st_nlink != 1
                or not 2 <= before.st_size <= _MAX_MANIFEST_BYTES):
            _reject("D437 private manifest unsafe")
        raw = os.read(fd, _MAX_MANIFEST_BYTES + 1)
        after = os.fstat(fd)
    finally:
        os.close(fd)
    if (len(raw) != before.st_size
            or before.st_ino != after.st_ino
            or before.st_mtime_ns != after.st_mtime_ns
            or before.st_size != after.st_size):
        _reject("D437 manifest changed during read")
    return build_reviewed_scope(raw, now_ms=now_ms)


def _successful_finite_public_close(session: dict) -> bool:
    """A post-close failure is NOT a successful finite public lease."""
    return (type(session) is dict
            and session.get("status") == "ws_budget_ended_research_only"
            and type(session.get("sessions_fully_acknowledged")) is int
            and session["sessions_fully_acknowledged"] == 1
            and type(session.get("subscriptions_acknowledged")) is int
            and session["subscriptions_acknowledged"] == 1
            and type(session.get("closed_events_appended")) is int
            and session["closed_events_appended"] >= 1)


def _pilot_public_outcome(session: dict) -> str:
    """Classify evidence conservatively, never hide a failed lease behind an ACK."""
    if type(session) is not dict or session.get("status") != "ws_budget_ended_research_only":
        return "public_session_abstained"
    if (type(session.get("sessions_fully_acknowledged")) is not int
            or session["sessions_fully_acknowledged"] != 1
            or type(session.get("subscriptions_acknowledged")) is not int
            or session["subscriptions_acknowledged"] != 1):
        return "public_session_abstained"
    if _successful_finite_public_close(session):
        return "public_confirmed_close_observed_unverified"
    if (type(session.get("open_updates")) is int and session["open_updates"] > 0):
        return "public_open_updates_observed_unverified"
    return "public_subscription_ack_observed_unverified"


def run_once(args: argparse.Namespace) -> dict:
    """No file or network action until every human gate and owner gate pass."""
    if any(type(getattr(args, key, None)) is not bool for key in _OPTINS):
        return {"status": "invalid_optin_flags", "network_attempted": False,
                "orders_sent": False}
    if not all(getattr(args, key) for key in _OPTINS):
        return {"status": "explicit_public_research_optin_required",
                "network_attempted": False, "orders_sent": False}
    if os.name != "posix" or not hasattr(os, "geteuid") or os.geteuid() == 0:
        return {"status": "unprivileged_owner_required",
                "network_attempted": False, "orders_sent": False}
    # A J1 pointer or operator-crafted manifest cannot authorize this pilot.
    # D441 is intentionally independent of previously accepted J1 collection.
    if (getattr(args, "state_directory", None) is not None
            or getattr(args, "scope_file", None) is not None
            or getattr(args, "allow_private_pointer_read", False)):
        return {"status": "j1_or_manual_scope_not_used_by_isolated_pilot",
                "network_attempted": False, "orders_sent": False}
    try:
        _owner_private_directory(args.output_dir)
        budget = WSRunBudget(max_sessions=1, max_frames=args.max_frames,
                             max_seconds=args.max_seconds)
    except (DataValidationError, OSError, ValueError, TypeError):
        return {"status": "owner_preflight_abstained",
                "network_attempted": False, "orders_sent": False}

    # Exactly one opt-in public instrument GET. Validate current BTCUSDT
    # metadata before any WebSocket is created. Never consult J1 state.
    try:
        scope = fetch_single_btc_scope_from_public_rest()
    except (J1BybitCaptureError, DataValidationError, OSError,
            ValueError, TypeError):
        return {"status": "public_rest_instrument_abstained",
                "network_attempted": True, "websocket_attempted": False,
                "orders_sent": False}

    # A unique 0700 pilot directory and isolated journal; never touch J1 owner.
    pilot = Path(tempfile.mkdtemp(prefix="d437-public-once-", dir=args.output_dir))
    projection = pilot / "projection"
    projection.mkdir(mode=0o700)
    journal = pilot / "observed-research.sqlite"
    SQLiteOfflineClosedStreamJournal.create(journal)
    try:
        report, update = run_authorized_public_kline_session(
            journal_path=journal, scope=scope, symbol="BTCUSDT",
            config=CONFIG, budget=budget, projection_directory=projection,
            allow_public_network=True, allow_public_websocket=True,
            confirm_personal_readonly_research=True, confirm_region_eligible=True,
        )
        if type(report) is dict:
            # Real transport preflight returned an abstention, not a WS lease.
            return {"status": "public_ws_preflight_abstained",
                    "network_attempted": True, "websocket_observation_proven": False,
                    "private_evidence_retained": True, "orders_sent": False,
                    "live_trading_authorized": False}
        terminal = read_projection(projection, now_ms=time.time_ns() // 1_000_000)
        session = report.sanitized_report()
        outcome = _pilot_public_outcome(session)
        return {
            "status": outcome,
            "source": "public_ws_observed_unverified",
            "scope_source": "single_btc_public_rest_instrument_unverified",
            "scope_members": 1,
            "network_attempted": True,
            "session": session,
            "research": update.sanitized_report() if update is not None else None,
            "terminal": terminal,
            "private_evidence_retained": True,
            "marketwide_top50_verified": False,
            "approved_for_signals": False,
            "orders_sent": False,
            "live_trading_authorized": False,
        }
    except (DataValidationError, OSError, RuntimeError, ImportError, ValueError, TypeError):
        return {
            "status": "owner_session_failed_closed", "network_attempted": True,
            "private_evidence_retained": True, "orders_sent": False,
            "live_trading_authorized": False,
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="D437 owner-only bounded Bybit kline pilot")
    # Deprecated arguments remain parseable only to fail closed (no J1 I/O).
    parser.add_argument("--state-directory", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--scope-file", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--allow-private-pointer-read", action="store_true",
                        help=argparse.SUPPRESS)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-seconds", type=int, default=240)
    parser.add_argument("--max-frames", type=int, default=24000)
    for field in _OPTINS:
        parser.add_argument("--" + field.replace("_", "-"), action="store_true")
    result = run_once(parser.parse_args(argv))
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0 if result["status"] in (
        "public_confirmed_close_observed_unverified",
        "public_open_updates_observed_unverified",
        "public_subscription_ack_observed_unverified",
    ) else 2


if __name__ == "__main__":
    raise SystemExit(main())
