"""D487 - local, owner-only PAPER profile controls and historical preview.

Separate from production J5 8765. No websocket, exchange orders, account
credentials, real trading or service management. Server binds only loopback
on 8766, and only with explicit opt-in and an already owned 0600 D453 file.
POST edits apply only to a subsequent D453 session, never held positions.
"""
from __future__ import annotations

import argparse
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import re
import sys
import time

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.j3_paper_scorecard_d511 import paper_closed_scorecard
from crypto_intelligence_agent.paper_closed_route_archive_d502 import (
    read_closed_route_archive,
)
from scripts.inspect_paper_positions import multi_paper_snapshot
from crypto_intelligence_agent.paper_position_inspection import inspect_paper_positions
from crypto_intelligence_agent.paper_profile_d487 import save, snapshot
from crypto_intelligence_agent.j2_rest_n50_history_d461 import (
    reopen_frozen_rest_n50_for_research, research_rest_n50_24h,
)
from crypto_intelligence_agent.j4_private_paper_ws_operator_d425 import (
    _private_directory, load_private_paper_routes,
)
from scripts.run_j2_j4_public_paper_resident_d453 import read_owner_paper_policy
from crypto_intelligence_agent.paper_order_store import (
    SQLitePaperOrderJournal, _TABLES as ORDER_TABLES,
    _VERSION as ORDER_VERSION,
)
from crypto_intelligence_agent.paper_position_inspection import _read_database, inspect_paper_position
from crypto_intelligence_agent.j5_owner_paper_positions_d446 import (
    read_owner_paper_positions, OwnerPaperPositionsUnavailable,
)
from crypto_intelligence_agent.paper_position_reservations import (
    _TABLES as POSITION_TABLES, _VERSION as POSITION_VERSION,
)
from crypto_intelligence_agent.j5_resident_paper_status_d456 import (
    read_resident_paper_status, ResidentPaperStatusUnavailable,
)
from crypto_intelligence_agent.j5_paper_decision_funnel_d509 import (
    read_paper_decision_funnel, PaperDecisionUnavailable,
)

HOST, PORT = "127.0.0.1", 8766
HTML = Path(__file__).resolve().parents[1] / "web/app/profile-lab.html"
JS = Path(__file__).resolve().parents[1] / "web/app/profile-lab.js"
_NAME = re.compile(r"rest-history-d461-[0-9a-f]{18}-([0-9]{13})(?:-w([0-9]{2,3}))?[.]json\Z")
_MAX_SESSION_POSITIONS = 50  # recent history; older active positions are always pinned


def _historical_scan(*, paper_file: Path, history_directory: Path) -> dict:
    _private_directory(history_directory)
    cfg = read_owner_paper_policy(paper_file)
    if cfg.research.entry_mode == "ema_cross":
        min_required = max(
            24, cfg.research.ema_cross_periods[-1] + 2,
            cfg.research.features.quote_volume_period + 1,
        )
    else:
        min_required = max(
            cfg.research.features.ema_period,
            cfg.research.features.atr_period,
            cfg.research.features.extrema_period,
            cfg.research.features.quote_volume_period,
            cfg.research.compression_bars + cfg.research.baseline_bars + 2,
            24,
        )
    archive_candidates = []
    for entry in history_directory.iterdir():
        match = _NAME.fullmatch(entry.name)
        if (match is not None and entry.is_file() and not entry.is_symlink()):
            hours = int(match.group(2) or 24)
            archive_candidates.append((int(match.group(1)), hours, entry.name))
    if not archive_candidates:
        return {
            "status": "historical_data_not_available",
            "candidate_count": 0, "orders_sent": False,
        }
    sufficient = [x for x in archive_candidates if x[1] >= min_required]
    # Prefer latest causal sample meeting the chosen lookback. When no
    # adequate history exists, report insufficiency, never fake a signal.
    _, _, file = max(sufficient or archive_candidates)
    history = reopen_frozen_rest_n50_for_research(
        private_j2_directory=history_directory, filename=file,
    )
    if min_required > history.history_hours:
        return {
            "status": "more_closed_candles_required",
            "needed_candles": min_required,
            "available_candles": history.history_hours,
            "snapshot_closed_end_ms": history.window_end_ms,
            "candidate_count": 0, "orders_sent": False,
        }
    result = research_rest_n50_24h(history=history, config=cfg.research)
    rows = result["rows"]
    btc = next((x for x in rows if x["symbol"] == "BTCUSDT"), None)
    if btc is None:
        raise DataValidationError("BTC missing from historical cohort")
    btc_ret = Decimal(btc["historical_24h_return_percent"])
    candidates = []
    decisions = []
    counts = {
        "btc_reference": 0, "no_technical_hypothesis": 0,
        "btc_relative_not_aligned": 0, "historical_candidate": 0,
    }
    for item in rows:
        symbol, side = item["symbol"], item["historical_hypothesis_side"]
        relative = Decimal(item["historical_24h_return_percent"]) - btc_ret
        if symbol == "BTCUSDT":
            decision = "btc_reference"
        elif not side:
            decision = "no_technical_hypothesis"
        elif (side == "LONG" and relative > 0) or (side == "SHORT" and relative < 0):
            decision = "historical_candidate"
            candidates.append({
                "symbol": symbol, "side": side,
                "btc_relative_percent": format(relative.quantize(Decimal("0.01")), "f"),
                "provenance": "public_rest_history_research_only",
            })
        else:
            decision = "btc_relative_not_aligned"
        counts[decision] += 1
        decisions.append({
            "symbol": symbol,
            "historical_side": side,
            "btc_relative_percent": format(
                relative.quantize(Decimal("0.01")), "f"
            ),
            "decision": decision,
        })
    decisions.sort(key=lambda row: (
        {"historical_candidate": 0, "btc_relative_not_aligned": 1,
         "no_technical_hypothesis": 2, "btc_reference": 3}[row["decision"]],
        -abs(Decimal(row["btc_relative_percent"])), row["symbol"],
    ))
    candidates.sort(
        key=lambda x: (-abs(Decimal(x["btc_relative_percent"])), x["symbol"])
    )
    return {
        "schema_version": "d487-real-rest-paper-profile-preview-v1",
        "status": "historical_research_only",
        "closed_end_ms": history.window_end_ms,
        "candle_interval": "1h",
        "closed_bars_per_symbol": history.history_hours,
        "symbols": len(history.series),
        "raw_hypotheses": result["potential_hypothesis_count"],
        "candidate_count": len(candidates),
        "candidates": candidates[:50],
        "decision_funnel": {
            "schema_version": "d509-rest-research-funnel-v1",
            "member_count": len(rows),
            "reason_counts": counts,
            "decisions": decisions,
            "source": "public_rest_history_not_websocket",
            "paper_orders_sent": False,
        },
        "source_mode": history.source_mode,
        "websocket_confirmation": False,
        "broker_fills": False,
        "orders_sent": False,
        "approved_for_live_use": False,
    }



def _project_positions(*, directory: Path,
                       position_ids: tuple[str, ...] | None = None) -> list[dict]:
    """Project selected AUTO4 balances and route levels; never a broker fill.

    Explicit paged IDs are obtained only from the owner SQLite journal, with
    full replay/digest validation and archive fallback for closed routes.
    """
    if position_ids is None:
        original = read_owner_paper_positions(
            directory=directory, include_conditional_pnl=True,
        )
    else:
        records = inspect_paper_positions(
            directory / "paper-positions.sqlite", position_ids,
        )
        original = multi_paper_snapshot(records)
        from crypto_intelligence_agent.j4_paper_conditional_pnl_d454 import (
            conditional_paper_pnl_from_existing_fills,
        )
        for position in original["positions"]:
            if position["position_id"].startswith("fixture_d448_pos_"):
                outcome = conditional_paper_pnl_from_existing_fills(
                    private_paper_directory=directory,
                    position_id=position["position_id"],
                )
                position["conditional_paper_pnl"] = outcome.sanitized_report()
            else:
                position["conditional_paper_pnl"] = {
                    "status": "legacy_paper_position_without_priced_strategy",
                    "true_realized_net_pnl_available": False,
                }
    if original.get("orders_sent") is not False:
        raise DataValidationError("PAPER-only snapshot required")
    router = load_private_paper_routes(directory)
    projected = []
    for position in original["positions"]:
        symbol = position["symbol_fixture"]
        route = router.route_for_position(position["position_id"])
        archived = None
        if route is None:
            archived = read_closed_route_archive(
                directory, position["position_id"],
            )
            if archived is None:
                raise DataValidationError("PAPER route missing from manifest and archive")
        b = inspect_paper_position(
            directory / "paper-positions.sqlite", position["position_id"],
        ).balance
        if (b.symbol != symbol or b.side.value != position["side"]
                or str(b.initial_confirmed_units) != position["initial_confirmed_units"]
                or str(b.confirmed_remaining_units) != position["confirmed_remaining_units"]
                or str(b.filled_exit_units) != position["filled_exit_units"]):
            raise DataValidationError("PAPER journal changed across readback")
        status = (
            "CLOSED" if b.confirmed_remaining_units == 0
            else "PARTIAL" if b.filled_exit_units > 0 else "OPEN"
        )
        stop_fill = any(
            x.tranche_step == -1 and x.snapshot.status.value == "FILLED"
            for x in b.exit_orders
        )
        closure = (
            "STOP" if status == "CLOSED" and stop_fill
            else "TARGETS" if status == "CLOSED" and all(
                x.filled_units == x.target_units for x in b.tranches
            )
            else "OTHER" if status == "CLOSED" else "NONE"
        )
        conditional = position.get("conditional_paper_pnl")
        pnl = (
            conditional.get("conditional_realized_before_funding_quote")
            if type(conditional) is dict and conditional.get("status")
               == "conditional_paper_reference_before_unverified_funding"
            else None
        )
        margin = position["margin_intent_requested"]
        if margin is not None and type(margin) is not dict:
            raise DataValidationError("invalid PAPER margin receipt")
        projected.append({
            "symbol": symbol,
            "side": position["side"],
            "status": status,
            "closure_reason": closure,
            "opened_at_ms": b.opened_at_ms,
            "as_of_ms": b.as_of_ms,
            "initial_units": position["initial_confirmed_units"],
            "remaining_units": position["confirmed_remaining_units"],
            "filled_exit_units": position["filled_exit_units"],
            "leverage_at_intent": (
                None if margin is None else margin["leverage_at_intent"]
            ),
            "requested_margin_quote": (
                None if margin is None else margin["requested_margin_quote"]
            ),
            "stop_mark_price": (
                archived["stop_mark_price"] if archived is not None
                else str(route.stop_rule.stop_mark_price)
            ),
            "target_prices": (
                archived["target_prices"] if archived is not None
                else [str(x) for x in route.target_policy.prices]
            ),
            "exit_orders": [{
                "kind": ("STOP" if x.tranche_step == -1 else "TARGET"),
                "status": x.snapshot.status.value,
                "filled_units": str(x.snapshot.filled_total_units),
            } for x in b.exit_orders],
            "conditional_result_before_funding_quote": pnl,
            "funding_not_verified": True,
            "native_stop_verified": False,
            "real_orders_sent": False,
        })
    return projected


def _paper_session_read(*, directory: Path) -> dict:
    """Integrity-checked readback of observed OPEN intent and durable positions."""
    _private_directory(directory)
    orders = directory / "paper-orders.sqlite"
    positions = directory / "paper-positions.sqlite"
    if not orders.is_file() or not positions.is_file():
        return {"status":"paper_session_not_started",
                "intents":[], "position_count":0,
                "open_position_count":0, "closed_position_count":0,
                "positions":[], "orders_sent":False}
    with _read_database(
        orders, ORDER_TABLES, "paper_order_meta", ORDER_VERSION
    ) as db:
        intent_count = db.execute(
            "SELECT COUNT(*) FROM paper_order_intents WHERE effect='OPEN'"
        ).fetchone()[0]
        names = [x[0] for x in db.execute(
            "SELECT intent_id FROM paper_order_intents "
            "WHERE effect='OPEN' "
            "ORDER BY checkpoint_as_of_ms DESC, intent_id DESC LIMIT 50"
        )]
        intents=[]
        for ident in names:
            entry=SQLitePaperOrderJournal._checked_entry(db,ident)
            intents.append({
                "symbol":entry.intent.symbol,
                "side":entry.intent.position_side.value,
                "status":entry.snapshot.status.value,
                "requested_units":str(entry.intent.requested_units),
                "filled_units":str(entry.snapshot.filled_total_units),
                "created_at_ms":entry.intent.created_at_ms,
            })
    # The existing J5 owner reader deliberately abstains when no position
    # has EVER been materialized. Distinguish verified empty journal from a
    # corrupt/unreadable nonempty journal rather than masking both as zero.
    with _read_database(
        positions, POSITION_TABLES, "paper_position_meta", POSITION_VERSION,
    ) as position_db:
        materialized_count = position_db.execute(
            "SELECT COUNT(*) FROM paper_positions",
        ).fetchone()[0]
        newest_ids = tuple(x[0] for x in position_db.execute(
            "SELECT position_id FROM paper_positions "
            "ORDER BY checkpoint_at_ms DESC, position_id DESC LIMIT ?",
            (_MAX_SESSION_POSITIONS,),
        ))
    if materialized_count:
        router = load_private_paper_routes(directory)
        # D505: checkpoint times on CLOSED positions advance on exit. Thus
        # a still-OPEN older position can fall outside the latest 50 rows.
        # Always pin ALL presently monitored non-flat positions to the J5
        # readback, while preserving the latest 50 for consistent pagination.
        active_ids = tuple(
            ident for ident in router.monitored_position_ids
            if inspect_paper_position(
                positions, ident,
            ).balance.confirmed_remaining_units > 0
        )
        active_count = len(router.monitored_symbols)
        if (len(active_ids) != active_count or active_count > 50
                or active_count > materialized_count):
            raise DataValidationError("PAPER active route inventory mismatch")
        recent = set(newest_ids)
        pinned = tuple(ident for ident in active_ids if ident not in recent)
        displayed = _project_positions(
            directory=directory, position_ids=newest_ids + pinned,
        )
        if (len(displayed) != len(newest_ids) + len(pinned)
                or sum(p["status"] != "CLOSED" for p in displayed)
                   != active_count):
            raise DataValidationError("PAPER visible active position count mismatch")
        displayed.sort(
            key=lambda p: (p["status"] == "CLOSED", -p["as_of_ms"],
                           p["symbol"], p["side"]),
        )
    else:
        displayed, active_count = [], 0
    position_count = materialized_count
    scorecard = paper_closed_scorecard(
        displayed, total_positions=position_count,
        total_closed_positions=position_count - active_count,
    )
    return {
        "schema_version":"d487-local-paper-session-readback-v1",
        "paper_scorecard": scorecard,
        "status":"paper_journal_readback",
        "intents":intents,
        "position_count":position_count,
        "open_position_count":active_count,
        "closed_position_count":position_count - active_count,
        "displayed_position_count":len(displayed),
        "more_history_available":position_count > len(newest_ids),
        "intent_count":intent_count,
        "intents_more_available":intent_count > len(intents),
        "positions":displayed,
        "orders_sent":False,
        "source":"owner_only_local_paper_sqlite",
        "live_trading_authorized":False,
    }


def _paper_history_page(*, directory: Path, offset: int, limit: int) -> dict:
    """Read one bounded page of immutable owner AUTO4 history, no writes."""
    _private_directory(directory)
    if (type(offset) is not int or not 0 <= offset <= 1_000_000
            or type(limit) is not int or not 1 <= limit <= 50):
        raise DataValidationError("D502 bounded history pagination required")
    with _read_database(
        directory / "paper-positions.sqlite",
        POSITION_TABLES, "paper_position_meta", POSITION_VERSION,
    ) as db:
        total = db.execute("SELECT COUNT(*) FROM paper_positions").fetchone()[0]
        ids = tuple(x[0] for x in db.execute(
            "SELECT position_id FROM paper_positions "
            "ORDER BY checkpoint_at_ms DESC, position_id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ))
    displayed = (
        _project_positions(directory=directory, position_ids=ids)
        if ids else []
    )
    return {
        "schema_version": "d502-owner-paper-history-page-v1",
        "status": "paper_history_readonly",
        "offset": offset, "limit": limit,
        "position_count": total, "positions": displayed,
        "more_available": offset + len(displayed) < total,
        "orders_sent": False, "approved_for_live_use": False,
    }


class OwnerPaperProfileHandler(BaseHTTPRequestHandler):
    paper_file: Path | None = None
    history_directory: Path | None = None
    paper_session_directory: Path | None = None
    demo_position_directory: Path | None = None

    def log_message(self, fmt, *args):
        # Never log arbitrary client path, private profile or JSON body.
        return

    def _respond(self, status: int, value: dict | bytes, ctype="application/json; charset=utf-8"):
        data = value if isinstance(value, bytes) else json.dumps(
            value, sort_keys=True, ensure_ascii=True,
            separators=(",", ":")).encode("ascii")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        if ctype.startswith("text/html"):
            self.send_header("Content-Security-Policy",
                "default-src 'none'; script-src 'self'; style-src 'unsafe-inline'; "
                "connect-src 'self'; form-action 'none'; frame-ancestors 'none'; "
                "base-uri 'none'")
        self.end_headers()
        self.wfile.write(data)

    def _allowed(self) -> bool:
        return (self.client_address[0] in ("127.0.0.1", "::1")
                and self.headers.get("Host") in (
                    f"127.0.0.1:{PORT}", f"localhost:{PORT}"))

    def do_GET(self):
        if not self._allowed():
            return self._respond(403, {"status":"loopback_only"})
        if self.path == "/":
            return self._respond(200, HTML.read_bytes(), "text/html; charset=utf-8")
        if self.path == "/profile-lab.js":
            return self._respond(200, JS.read_bytes(), "text/javascript; charset=utf-8")
        if self.path == "/api/paper-session":
            path = type(self).paper_session_directory
            if path is None:
                return self._respond(503, {"status":"paper_session_reader_disabled"})
            try:
                return self._respond(200,_paper_session_read(directory=path))
            except (DataValidationError, OSError, ValueError,
                    TypeError, OwnerPaperPositionsUnavailable):
                return self._respond(503, {"status":"paper_session_not_ready"})
        if self.path.startswith("/api/paper-history"):
            path = type(self).paper_session_directory
            if path is None:
                return self._respond(503, {"status":"paper_history_reader_disabled"})
            matched = re.fullmatch(
                r"/api/paper-history[?]offset=([0-9]{1,7})&limit=([0-9]{1,2})",
                self.path,
            )
            if matched is None:
                return self._respond(400, {"status":"invalid_history_pagination"})
            try:
                page = _paper_history_page(
                    directory=path, offset=int(matched[1]), limit=int(matched[2]),
                )
                return self._respond(200, page)
            except (DataValidationError, OSError, ValueError, TypeError,
                    OwnerPaperPositionsUnavailable):
                return self._respond(503, {"status":"paper_history_not_ready"})
        if self.path == "/api/paper-decision-funnel":
            path = type(self).paper_session_directory
            if path is None:
                return self._respond(503, {
                    "status":"paper_funnel_reader_disabled",
                    "orders_sent":False,
                })
            try:
                report = read_paper_decision_funnel(
                    directory=path, now_ms=time.time_ns() // 1_000_000,
                )
                return self._respond(200, report)
            except (PaperDecisionUnavailable, OSError, ValueError, TypeError):
                return self._respond(503, {
                    "status":"no_valid_completed_public_lease",
                    "orders_sent":False,
                })
        if self.path == "/api/paper-operator":
            path = type(self).paper_session_directory
            if path is None:
                return self._respond(503, {"status":"paper_operator_reader_disabled"})
            try:
                x = read_resident_paper_status(
                    directory=path, now_ms=time.time_ns() // 1_000_000,
                )
                return self._respond(200, x)
            except (ResidentPaperStatusUnavailable, OSError, ValueError):
                return self._respond(503, {
                    "status":"no_fresh_operator_heartbeat",
                    "paper_protection_verified":False,
                })
        if self.path == "/api/paper-demo":
            path = type(self).demo_position_directory
            if path is None:
                return self._respond(503, {"status":"paper_demo_reader_disabled"})
            try:
                return self._respond(200, {
                    "status":"separate_manual_paper_demo",
                    "positions":_project_positions(directory=path),
                    "orders_sent":False,
                    "market_entry_signal":False,
                })
            except (DataValidationError, OSError, ValueError,
                    OwnerPaperPositionsUnavailable, TypeError):
                return self._respond(503, {"status":"paper_demo_not_available"})
        if self.path == "/api/profile":
            try:
                return self._respond(200, snapshot(type(self).paper_file))
            except (DataValidationError, OSError, ValueError, TypeError):
                return self._respond(503, {"status":"profile_not_available"})
        if self.path == "/api/research-preview":
            try:
                return self._respond(200, _historical_scan(
                    paper_file=type(self).paper_file,
                    history_directory=type(self).history_directory,
                ))
            except (DataValidationError, OSError, ValueError, TypeError):
                return self._respond(503, {"status":"historical_research_unavailable"})
        return self._respond(404, {"status":"not_found"})

    def do_POST(self):
        if not self._allowed():
            return self._respond(403, {"status":"loopback_only"})
        if self.path != "/api/profile":
            return self._respond(405, {"status":"profile_only"})
        host = self.headers.get("Host")
        if (self.headers.get("Origin") != f"http://{host}"
                or self.headers.get("X-CIA-Paper-Profile") != "1"
                or self.headers.get("Content-Type") != "application/json"):
            return self._respond(403, {"status":"same_origin_json_required"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 2 <= length <= 4096:
                raise DataValidationError("bounded JSON body required")
            data = json.loads(
                self.rfile.read(length).decode("ascii"),
                object_pairs_hook=_no_duplicates, parse_constant=_reject_number,
                parse_float=_reject_number,
            )
            if (type(data) is not dict
                    or set(data) != {"revision", "edits"}
                    or type(data["edits"]) is not dict):
                raise DataValidationError("invalid profile patch")
            result = save(type(self).paper_file,
                          revision=data["revision"], edits=data["edits"])
            return self._respond(200, result)
        except (DataValidationError, OSError, ValueError, UnicodeError,
                TypeError, OverflowError):
            return self._respond(409, {
                "status":"profile_change_rejected_reload_and_review",
                "orders_sent":False,
            })

    def do_PUT(self):
        return self._respond(405, {"status":"method_not_allowed"})
    def do_DELETE(self):
        return self._respond(405, {"status":"method_not_allowed"})
    def do_OPTIONS(self):
        return self._respond(405, {"status":"method_not_allowed"})


def _reject_number(_):
    raise DataValidationError("noninteger JSON number forbidden")


def _no_duplicates(pairs):
    out={}
    for k,v in pairs:
        if k in out: raise DataValidationError("duplicate patch key")
        out[k]=v
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enable-owner-paper-profile", action="store_true")
    parser.add_argument("--policy-file", type=Path)
    parser.add_argument("--historical-directory", type=Path)
    parser.add_argument("--paper-session-directory", type=Path)
    parser.add_argument("--demo-position-directory", type=Path)
    args=parser.parse_args(argv)
    if (args.enable_owner_paper_profile is not True
            or args.policy_file is None or args.historical_directory is None
            or os.name != "posix" or os.geteuid()==0
            or os.getuid()!=os.geteuid()):
        print(json.dumps({"status":"owner_paper_profile_optin_required",
                          "orders_sent":False}))
        return 65
    try:
        read_owner_paper_policy(args.policy_file)
        _private_directory(args.historical_directory)
        if args.paper_session_directory is not None:
            _private_directory(args.paper_session_directory)
        if args.demo_position_directory is not None:
            _private_directory(args.demo_position_directory)
    except (DataValidationError,OSError,ValueError,TypeError):
        print(json.dumps({"status":"safe_profile_directory_unavailable",
                          "orders_sent":False}))
        return 65
    OwnerPaperProfileHandler.paper_file = args.policy_file
    OwnerPaperProfileHandler.history_directory = args.historical_directory
    OwnerPaperProfileHandler.paper_session_directory = args.paper_session_directory
    OwnerPaperProfileHandler.demo_position_directory = args.demo_position_directory
    try:
        with HTTPServer((HOST,PORT),OwnerPaperProfileHandler) as srv:
            print(json.dumps({"status":"owner_paper_profile_loopback_ready",
                  "address":f"http://{HOST}:{PORT}/",
                  "paper_only":True, "orders_sent":False}),flush=True)
            srv.serve_forever(poll_interval=.5)
    except KeyboardInterrupt:
        return 0
    except OSError:
        print(json.dumps({"status":"profile_loopback_bind_failed",
                          "orders_sent":False}))
        return 65
    return 0


if __name__ == "__main__":
    sys.exit(main())
