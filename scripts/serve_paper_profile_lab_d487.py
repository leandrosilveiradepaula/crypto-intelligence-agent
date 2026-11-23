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

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.paper_profile_d487 import save, snapshot
from crypto_intelligence_agent.j2_rest_n50_history_d461 import (
    reopen_frozen_rest_n50_for_research, research_rest_n50_24h,
)
from crypto_intelligence_agent.j4_private_paper_ws_operator_d425 import (
    _private_directory,
)
from scripts.run_j2_j4_public_paper_resident_d453 import read_owner_paper_policy

HOST, PORT = "127.0.0.1", 8766
HTML = Path(__file__).resolve().parents[1] / "web/app/profile-lab.html"
JS = Path(__file__).resolve().parents[1] / "web/app/profile-lab.js"
_NAME = re.compile(r"rest-history-d461-[0-9a-f]{18}-[0-9]{13}[.]json\Z")


def _historical_scan(*, paper_file: Path, history_directory: Path) -> dict:
    _private_directory(history_directory)
    filenames = sorted(
        (x.name for x in history_directory.iterdir()
         if _NAME.fullmatch(x.name) and x.is_file() and not x.is_symlink())
    )
    if not filenames:
        return {
            "status": "historical_data_not_available",
            "candidate_count": 0, "orders_sent": False,
        }
    file = filenames[-1]
    history = reopen_frozen_rest_n50_for_research(
        private_j2_directory=history_directory, filename=file,
    )
    cfg = read_owner_paper_policy(paper_file)
    min_required = max(
        cfg.research.features.ema_period,
        cfg.research.features.atr_period,
        cfg.research.features.extrema_period,
        cfg.research.features.quote_volume_period,
        cfg.research.compression_bars + cfg.research.baseline_bars + 2,
        24,
    )
    if min_required > 24:
        return {
            "status": "more_closed_candles_required",
            "needed_candles": min_required,
            "available_candles": 24,
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
    for item in rows:
        symbol, side = item["symbol"], item["historical_hypothesis_side"]
        if symbol == "BTCUSDT" or not side:
            continue
        relative = Decimal(item["historical_24h_return_percent"]) - btc_ret
        if (side == "LONG" and relative > 0) or (side == "SHORT" and relative < 0):
            candidates.append({
                "symbol": symbol, "side": side,
                "btc_relative_percent": format(relative.quantize(Decimal("0.01")), "f"),
                "provenance": "public_rest_history_research_only",
            })
    candidates.sort(
        key=lambda x: (-abs(Decimal(x["btc_relative_percent"])), x["symbol"])
    )
    return {
        "schema_version": "d487-real-rest-paper-profile-preview-v1",
        "status": "historical_research_only",
        "closed_end_ms": history.window_end_ms,
        "candle_interval": "1h",
        "closed_bars_per_symbol": 24,
        "symbols": len(history.series),
        "raw_hypotheses": result["potential_hypothesis_count"],
        "candidate_count": len(candidates),
        "candidates": candidates[:50],
        "source_mode": history.source_mode,
        "websocket_confirmation": False,
        "broker_fills": False,
        "orders_sent": False,
        "approved_for_live_use": False,
    }


class OwnerPaperProfileHandler(BaseHTTPRequestHandler):
    paper_file: Path | None = None
    history_directory: Path | None = None

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
    except (DataValidationError,OSError,ValueError,TypeError):
        print(json.dumps({"status":"safe_profile_directory_unavailable",
                          "orders_sent":False}))
        return 65
    OwnerPaperProfileHandler.paper_file = args.policy_file
    OwnerPaperProfileHandler.history_directory = args.historical_directory
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
