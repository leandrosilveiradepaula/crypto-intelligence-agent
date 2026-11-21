"""J5/APP-SYNC1: self-contained LOOPBACK-only read-only N50 panel.

No deployment or daemon is installed by this module. This explicit opt-in
foreground server binds ONLY 127.0.0.1:8765. It serves four public static
assets and one count-only endpoint, never a credential, private file, database,
exchange API, order path, or public interface. Not remotely reachable without
a separately authorized private tunnel.
"""
from __future__ import annotations

import argparse
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import re
import stat
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

from crypto_intelligence_agent.market_data import DataValidationError, DataGapError
from crypto_intelligence_agent.j2_public_n50_health_cycles_d421 import _owned_directory
from crypto_intelligence_agent.j5_local_health_reader_d422 import (
    HealthUnavailable, read_local_health,
)
from crypto_intelligence_agent.j5_paper_watch_d427 import (
    PaperWatchUnavailable, read_paper_watch,
)
from crypto_intelligence_agent.j5_owner_paper_positions_d446 import (
    OwnerPaperPositionsUnavailable, read_owner_paper_positions,
)
from crypto_intelligence_agent.j4_continuous_paper_worker_d444 import (
    WorkerStatusUnavailable, read_private_worker_status,
)
from crypto_intelligence_agent.j5_resident_paper_status_d456 import (
    ResidentPaperStatusUnavailable, read_resident_paper_status,
)
from crypto_intelligence_agent.j5_last_public_paper_lease_d470 import (
    LastPaperLeaseUnavailable, read_last_paper_lease,
)
from crypto_intelligence_agent.j2_prospective_bybit_research_d436 import read_projection
from crypto_intelligence_agent.bybit_public_j1_transport import J1BybitCaptureError
from crypto_intelligence_agent.bybit_public_rest_price_pulse_d403 import capture_public_rest_price_pulse
from crypto_intelligence_agent.bybit_public_j1_transport import _SYMBOL
from crypto_intelligence_agent.j2_n50_ws_private_screen import (
    observe_active_private_ws_n50_24closed,
)
from scripts.export_j5_n50_ws_journald_once import export_n50_journald_progress

HOST = "127.0.0.1"
PORT = 8765
_MAX_JOURNAL_BYTES = 1_048_576
_STATIC_ROOT = Path(__file__).resolve().parents[1] / "web" / "app"
_STATIC_FILES: dict[str, tuple[str, str]] = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/engine.js": ("engine.js", "text/javascript; charset=utf-8"),
    "/public-market.js": ("public-market.js", "text/javascript; charset=utf-8"),
    "/persisted-paper.js": ("persisted-paper.js", "text/javascript; charset=utf-8"),
    "/integrated-paper-cycle.js": ("integrated-paper-cycle.js", "text/javascript; charset=utf-8"),
    "/research-scorebook.js": ("research-scorebook.js", "text/javascript; charset=utf-8"),
    "/paper-ws-health.js": ("paper-ws-health.js", "text/javascript; charset=utf-8"),
    "/paper-watch.js": ("paper-watch.js", "text/javascript; charset=utf-8"),
    "/resident-paper.js": ("resident-paper.js", "text/javascript; charset=utf-8"),
    "/last-public-paper-lease.js": ("last-public-paper-lease.js", "text/javascript; charset=utf-8"),
    "/prospective-research.js": ("prospective-research.js", "text/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
}
_ALLOWED_HOST_HEADERS = frozenset((f"{HOST}:{PORT}", f"localhost:{PORT}"))
_JOURNALCTL_ARGV = (
    "/usr/bin/journalctl", "--unit=cia-j1-n50-ws.service",
    "--since=26 hours ago", "--output=json", "--no-pager",
    "--grep=j1-n50-ws-cached-owner-window-v1", "--lines=128",
)
_INTEGRATED_CYCLE_FILE = "latest-integrated-paper-cycle.json"


class SourceNotReady(Exception):
    """Only a bounded, sanitized 503 is allowed to escape to the UI."""


def read_integrated_cycle(*, directory: Path) -> dict[str, Any]:
    """Read a bounded owner-only D431 report; browser revalidates its contract."""
    _owned_directory(directory)
    path = directory / _INTEGRATED_CYCLE_FILE
    # Open first with NOFOLLOW and verify the actual descriptor; stat()+open()
    # can otherwise follow a symlink switched between the two operations.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as source:
        info = os.fstat(source.fileno())
        if (not stat.S_ISREG(info.st_mode)
                or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_uid != os.geteuid()
                or not 2 <= info.st_size <= 32_768):
            raise SourceNotReady("integrated cycle artifact unavailable")
        raw = source.read(32_769)
        after = os.fstat(source.fileno())
    if (len(raw) != info.st_size or after.st_size != info.st_size
            or after.st_mtime_ns != info.st_mtime_ns
            or after.st_ino != info.st_ino):
        raise SourceNotReady("integrated cycle artifact unstable")
    def no_duplicate_fields(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise SourceNotReady("duplicate integrated cycle field")
            result[key] = value
        return result
    report = json.loads(
        raw.decode("utf-8"), object_pairs_hook=no_duplicate_fields,
        parse_constant=lambda value: (_ for _ in ()).throw(
            SourceNotReady("invalid integrated cycle numeric field")),
    )
    if (type(report) is not dict
            or report.get("schema_version") != "j6_full_offline_paper_lifecycle_v1"
            or report.get("mode") != "offline_paper"
            or report.get("orders_sent") is not False
            or report.get("live_trading_authorized") is not False
            or report.get("approved_for_live_use") is not False
            or report.get("market_data_real") is not False
            or report.get("financial_pnl_available") is not False
            or report.get("native_stop_verified") is not False
            or report.get("network_requests") != 0):
        raise SourceNotReady("integrated cycle contract unavailable")
    return report


def read_n50_progress(*, now_ms: int) -> dict[str, Any]:
    """Query local systemd journal, then delegate to the EXISTING validator.

    Fixed argv and timeout. No shell, caller-supplied path, SQL, HTTP client,
    raw log output, scheduler, or privileged login. Only count-only projection.
    """
    try:
        outcome = subprocess.run(
            list(_JOURNALCTL_ARGV), stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=6, check=False,
        )
        if (outcome.returncode != 0
                or not 0 < len(outcome.stdout) <= _MAX_JOURNAL_BYTES):
            raise SourceNotReady("no bounded owner-hour journal")
        report = export_n50_journald_progress(
            outcome.stdout, now_ms=now_ms,
        )
    except (DataValidationError, OSError, ValueError, TypeError,
            OverflowError, UnicodeError, subprocess.TimeoutExpired) as exc:
        raise SourceNotReady("read-only source not available") from None
    if (report.get("schema_version") != "j5-n50-ws-log-progress-v1"
            or report.get("owner_d323_24h_audit_verified") is not False
            or report.get("orders_sent") is not False
            or report.get("network_requests") != 0
            or report.get("source_authenticated") is not False):
        raise SourceNotReady("unsafe projection blocked")
    return report



_RESEARCH_OUTPUT_KEYS = frozenset((
    "schema_version", "status", "quality", "latest_closed_end_ms",
    "audited_assets", "eligible_closed_bars_per_asset",
    "btc_context_available", "descriptive_up_breakouts",
    "descriptive_down_breakouts", "descriptive_inside_bars", "research_rows",
    "ws_journal_integrity_replayed", "window_digest_sha256",
    "formal_d323_24h_verified", "continuous_collector_verified",
    "rotation_36h_live_verified", "marketwide_top50_verified",
    "crypto_identity_independently_verified", "source_authenticated",
    "approved_for_signals", "approved_for_live_use",
    "financial_backtest_approved", "orders_sent",
    "network_requests", "database_mutation_statements", "systemd_modified",
))


def read_j2_descriptive() -> dict[str, Any]:
    """Revalidate current owner D321/24h and expose count-only J2 research.

    No new journal reader, imports, REST, websocket, ticker export or orders.
    The existing owner gate makes missing 24h or invalid DAC an abstention.
    """
    try:
        source = observe_active_private_ws_n50_24closed(
            allow_private_readonly_research=True,
            include_private_symbols=False,
        )
    except (DataValidationError, OSError, ValueError, TypeError,
            RuntimeError, OverflowError, UnicodeError):
        raise SourceNotReady("J2 private window not ready") from None
    if (type(source) is not dict
            or source.get("schema_version") != "j2-ws-n50-descriptive-24closed-v1"
            or source.get("status") not in (
                "ws_n50_descriptive_24h_ready", "ws_n50_btc_context_missing"
            )
            or source.get("audited_assets") != 50
            or source.get("eligible_closed_bars_per_asset") != 24
            or source.get("ws_journal_integrity_replayed") is not True
            or type(source.get("research_rows")) is not list
            or source["research_rows"] != []
            or type(source.get("window_digest_sha256")) is not str
            or re.fullmatch(r"[0-9a-f]{64}", source["window_digest_sha256"]) is None
            or source.get("quality") != "private_ws_24h_descriptive_research_only"
            or type(source.get("latest_closed_end_ms")) is not int
            or not 1_600_000_000_000 <= source["latest_closed_end_ms"] <= 4_102_444_800_000
            or source["latest_closed_end_ms"] % 3_600_000 != 0
            or any(source.get(key) is not False for key in (
                "formal_d323_24h_verified", "continuous_collector_verified",
                "rotation_36h_live_verified", "marketwide_top50_verified",
                "crypto_identity_independently_verified",
                "source_authenticated", "approved_for_signals",
                "approved_for_live_use", "financial_backtest_approved",
                "orders_sent", "systemd_modified"
            ))
            or source.get("network_requests") != 0
            or source.get("database_mutation_statements") != 0
            or any(type(source.get(key)) is not int
                   or source[key] < 0 or source[key] > 50
                   for key in ("descriptive_up_breakouts",
                               "descriptive_down_breakouts",
                               "descriptive_inside_bars"))
            or sum(source[key] for key in (
                "descriptive_up_breakouts", "descriptive_down_breakouts",
                "descriptive_inside_bars"
            )) != 50
            or not _RESEARCH_OUTPUT_KEYS.issubset(source)):
        raise SourceNotReady("unsafe J2 projection rejected")
    # Exact allowlist: no owner paths, symbols, registry hashes or extra fields
    # survive from future producer versions. Existing browser validation reused.
    return {key: source[key] for key in sorted(_RESEARCH_OUTPUT_KEYS)}


_PUBLIC_PULSE_KEYS = frozenset((
    "schema_version", "status", "source", "server_at_ms", "captured_at_ms",
    "observed_symbol_count", "quotes", "network_gets_in_this_capture",
    "crypto_only_membership_verified", "continuous_websocket_verified",
    "imported_report_authenticated_by_browser", "paper_positions_linked",
    "orders_sent", "approved_for_signals", "approved_for_live_use",
))
_PUBLIC_PRICE_KEYS = frozenset((
    "symbol", "last_price", "mark_price", "bid_price", "ask_price",
    "bid_size", "ask_size", "turnover_24h",
))


def read_public_market_prices(*, symbols: tuple[str, ...]) -> dict[str, Any]:
    """One public HTTPS market snapshot, isolated from J1 owner data and PAPER.

    The caller (the opt-in loopback handler) enforces a 60s request budget,
    so the client is used for no more than one public GET per minute.
    """
    try:
        value = capture_public_rest_price_pulse(symbols=symbols)
    except (J1BybitCaptureError, DataValidationError, DataGapError,
            OSError, ValueError, TypeError):
        raise SourceNotReady("D404 public REST source unavailable") from None
    if (type(value) is not dict
            or set(value) != _PUBLIC_PULSE_KEYS
            or value.get("schema_version") != "bybit-public-rest-price-pulse-d403-v1"
            or value.get("status") != "rest_snapshot_display_only"
            or value.get("source") != "bybit_v5_public_linear_tickers"
            or value.get("observed_symbol_count") != len(symbols)
            or value.get("network_gets_in_this_capture") != 1
            or any(value.get(k) is not False for k in (
                "crypto_only_membership_verified", "continuous_websocket_verified",
                "imported_report_authenticated_by_browser", "paper_positions_linked",
                "orders_sent", "approved_for_signals", "approved_for_live_use"))
            or type(value.get("quotes")) is not list
            or len(value["quotes"]) != len(symbols)
            or any(type(q) is not dict or set(q) != _PUBLIC_PRICE_KEYS
                   for q in value["quotes"])
            or tuple(q["symbol"] for q in value["quotes"]) != tuple(sorted(symbols))):
        raise SourceNotReady("D404 unsafe public REST projection")
    # No provider metadata or future accidental fields may leave localhost.
    return value


def _static_file(path: str) -> tuple[bytes, str] | None:
    spec = _STATIC_FILES.get(path)
    if spec is None:
        return None
    name, content_type = spec
    target = _STATIC_ROOT / name
    if target.is_symlink() or not target.is_file():
        return None
    try:
        data = target.read_bytes()
    except OSError:
        return None
    if len(data) == 0 or len(data) > 96_000:
        return None
    return data, content_type


class LoopbackPanelHandler(BaseHTTPRequestHandler):
    """No CORS and no state mutations. Host check blocks DNS rebinding."""
    market_symbols: tuple[str, ...] = ()  # disabled unless explicit server opt-in
    market_last_attempt_ms = 0
    market_cached: dict[str, Any] | None = None
    # OFF by default; only a same-owner POSIX 0700 directory can enable it.
    public_health_directory: Path | None = None
    paper_watch_directory: Path | None = None  # separate opt-in; 0700/0600, count-only
    persisted_paper_directory: Path | None = None  # D446 read-only detail, opt-in
    paper_worker_directory: Path | None = None  # D444 owner state, count-only
    resident_paper_directory: Path | None = None  # D453 resident PAPER owner-only status
    last_public_paper_lease_directory: Path | None = None  # D470 last lease; NOT live feed
    prospective_research_directory: Path | None = None
    protocol_version = "HTTP/1.1"
    server_version = "CIA-Local-ReadOnly"
    sys_version = ""

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(8)

    def log_message(self, _format: str, *args: object) -> None:
        # Never print URL, Origin, headers or content to service/owner logs.
        return

    def _response(self, status: int, data: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Connection", "close")
        if content_type.startswith("text/html"):
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; script-src 'self'; style-src 'self'; "
                "connect-src 'self'; img-src 'self' data:; "
                "base-uri 'none'; form-action 'none'; "
                "frame-src 'none'; object-src 'none'",
            )
        else:
            self.send_header("Content-Security-Policy", "default-src 'none'")
        self.end_headers()
        self.wfile.write(data)
        self.close_connection = True

    def _json(self, code: int, obj: dict[str, Any], *, max_bytes: int = 32_768) -> None:
        body = json.dumps(
            obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        ).encode("ascii")
        if len(body) > max_bytes:
            body = b'{"status":"projection_too_large_abstain"}'
            code = 503
        self._response(code, body, "application/json; charset=utf-8")

    def _request_allowed(self) -> bool:
        hosts = self.headers.get_all("Host") or []
        origins = self.headers.get_all("Origin") or []
        return (
            self.client_address[0] == HOST
            and self.server.server_address[0] == HOST
            and len(hosts) == 1 and hosts[0] in _ALLOWED_HOST_HEADERS
            and (not origins or (
                len(origins) == 1 and origins[0] in (
                    f"http://{HOST}:{PORT}", f"http://localhost:{PORT}",
                )
            ))
        )

    def do_GET(self) -> None:
        if not self._request_allowed():
            self._json(403, {"status": "loopback_host_required"})
            return
        if self.path == "/api/bybit-public-price":
            cls = type(self)
            if not cls.market_symbols:
                self._json(503, {"status": "public_market_not_enabled",
                                 "orders_sent": False})
                return
            now_ms = time.time_ns() // 1_000_000
            # Never poll more than once per minute per foreground server.
            if cls.market_last_attempt_ms and (
                now_ms - cls.market_last_attempt_ms < 60_000
            ):
                cached = cls.market_cached
                if (cached is None or
                        now_ms - cached["captured_at_ms"] > 45_000):
                    self._json(503, {"status": "public_market_stale",
                                     "orders_sent": False})
                else:
                    self._json(200, cached)
                return
            cls.market_last_attempt_ms = now_ms
            cls.market_cached = None
            try:
                report = read_public_market_prices(symbols=cls.market_symbols)
            except SourceNotReady:
                self._json(503, {"status": "public_market_unavailable",
                                 "orders_sent": False})
                return
            cls.market_cached = report
            self._json(200, report)
            return
        if self.path == "/api/owner-paper-positions":
            directory = type(self).persisted_paper_directory
            if directory is None:
                self._json(503, {"status": "owner_paper_positions_not_enabled",
                                 "orders_sent": False})
                return
            try:
                report = read_owner_paper_positions(
                    directory=directory, include_conditional_pnl=True,
                )
            except OwnerPaperPositionsUnavailable:
                self._json(503, {"status": "owner_paper_positions_unavailable",
                                 "orders_sent": False})
                return
            # Up to 50 routed PAPER positions; this cap applies ONLY on a
            # separately opt-in LOOPBACK-only endpoint, never public HTTP.
            self._json(200, report, max_bytes=96_000)
            return
        if self.path == "/api/last-public-paper-lease":
            directory = type(self).last_public_paper_lease_directory
            if directory is None:
                self._json(503, {"status": "last_public_paper_lease_not_enabled",
                                 "orders_sent": False})
                return
            try:
                report = read_last_paper_lease(
                    directory=directory, now_ms=time.time_ns() // 1_000_000,
                )
            except LastPaperLeaseUnavailable:
                self._json(503, {"status": "last_public_paper_lease_unavailable",
                                 "orders_sent": False})
                return
            self._json(200, report, max_bytes=4096)
            return
        if self.path == "/api/resident-paper-status":
            directory = type(self).resident_paper_directory
            if directory is None:
                self._json(503, {"status": "resident_paper_status_not_enabled",
                                 "orders_sent": False})
                return
            try:
                report = read_resident_paper_status(
                    directory=directory, now_ms=time.time_ns() // 1_000_000,
                )
            except ResidentPaperStatusUnavailable:
                self._json(503, {"status": "resident_paper_status_unavailable",
                                 "orders_sent": False})
                return
            self._json(200, report, max_bytes=4096)
            return
        if self.path == "/api/paper-worker":
            directory = type(self).paper_worker_directory
            if directory is None:
                self._json(503, {
                    "status": "paper_worker_loopback_not_enabled",
                    "orders_sent": False,
                })
                return
            try:
                report = read_private_worker_status(
                    directory=directory,
                    now_ms=time.time_ns() // 1_000_000,
                )
            except WorkerStatusUnavailable:
                self._json(503, {
                    "status": "paper_worker_stopped_or_unavailable",
                    "orders_sent": False,
                })
                return
            self._json(200, report)
            return
        if self.path == "/api/paper-watch":
            directory = type(self).paper_watch_directory
            if directory is None:
                self._json(503, {
                    "status": "paper_watch_not_enabled",
                    "orders_sent": False,
                })
                return
            try:
                report = read_paper_watch(
                    directory=directory, now_ms=time.time_ns() // 1_000_000,
                )
            except PaperWatchUnavailable:
                self._json(503, {
                    "status": "paper_watch_not_fresh_or_available",
                    "orders_sent": False,
                })
                return
            self._json(200, report)
            return
        if self.path == "/api/integrated-paper-cycle":
            directory = type(self).paper_watch_directory
            if directory is None:
                self._json(503, {"status": "integrated_cycle_not_enabled", "orders_sent": False})
                return
            try:
                self._json(200, read_integrated_cycle(directory=directory))
            except (OSError, ValueError, UnicodeError, SourceNotReady, DataValidationError):
                self._json(503, {"status": "integrated_cycle_not_available", "orders_sent": False})
            return
        if self.path == "/api/n50-public-health":
            directory = type(self).public_health_directory
            if directory is None:
                self._json(503, {
                    "status": "local_public_health_disabled",
                    "orders_sent": False,
                })
                return
            try:
                report = read_local_health(
                    directory=directory, now_ms=time.time_ns() // 1_000_000,
                )
            except HealthUnavailable:
                self._json(503, {
                    "status": "local_public_health_unavailable",
                    "orders_sent": False,
                })
                return
            self._json(200, report)
            return
        if self.path == "/api/j2-research":
            try:
                report = read_j2_descriptive()
            except SourceNotReady:
                self._json(503, {
                    "schema_version": "j5-local-research-unavailable-v1",
                    "status": "research_not_available",
                    "approved_for_signals": False,
                    "orders_sent": False,
                })
                return
            self._json(200, report)
            return
        if self.path == "/api/j2-prospective-research":
            directory = type(self).prospective_research_directory
            if directory is None:
                self._json(503, {"status": "prospective_research_not_enabled", "orders_sent": False})
                return
            try:
                self._json(200, read_projection(directory, now_ms=time.time_ns() // 1_000_000))
            except (OSError, ValueError, UnicodeError, DataValidationError):
                self._json(503, {"status": "prospective_research_not_fresh_or_available", "orders_sent": False})
            return
        if self.path == "/api/n50-progress":
            try:
                report = read_n50_progress(now_ms=time.time_ns() // 1_000_000)
            except SourceNotReady:
                self._json(503, {
                    "schema_version": "j5-local-status-unavailable-v1",
                    "status": "source_not_available",
                    "owner_d323_24h_audit_verified": False,
                    "orders_sent": False,
                })
                return
            self._json(200, report)
            return
        asset = _static_file(self.path)
        if asset is None:
            self._json(404, {"status": "not_found"})
            return
        self._response(200, asset[0], asset[1])

    def do_POST(self) -> None:
        self._json(405, {"status": "read_only_get_only"})

    def do_PUT(self) -> None:
        self._json(405, {"status": "read_only_get_only"})

    def do_DELETE(self) -> None:
        self._json(405, {"status": "read_only_get_only"})

    def do_OPTIONS(self) -> None:
        self._json(405, {"status": "read_only_get_only"})

    def do_HEAD(self) -> None:
        self._response(405, b"", "application/json; charset=utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-loopback-readonly-http", action="store_true")
    parser.add_argument("--allow-public-rest-samples", action="store_true")
    parser.add_argument("--allow-private-health-loopback", action="store_true")
    parser.add_argument("--private-health-directory", type=Path)
    parser.add_argument("--allow-paper-watch-loopback", action="store_true")
    parser.add_argument("--paper-watch-directory", type=Path)
    parser.add_argument("--allow-owner-paper-positions-loopback", action="store_true")
    parser.add_argument("--owner-paper-positions-directory", type=Path)
    parser.add_argument("--allow-paper-worker-loopback", action="store_true")
    parser.add_argument("--allow-resident-paper-status-loopback", action="store_true")
    parser.add_argument("--resident-paper-status-directory", type=Path)
    parser.add_argument("--allow-last-public-paper-lease-loopback", action="store_true")
    parser.add_argument("--last-public-paper-lease-directory", type=Path)
    parser.add_argument("--paper-worker-directory", type=Path)
    parser.add_argument("--allow-prospective-research-loopback", action="store_true")
    parser.add_argument("--prospective-research-directory", type=Path)
    parser.add_argument("--market-symbols", default="", help="1..50 reviewed USDT symbols")
    args = parser.parse_args(argv)
    if not args.allow_loopback_readonly_http:
        print(json.dumps({
            "status": "explicit_loopback_optin_required",
            "network_public": False, "orders_sent": False,
        }, sort_keys=True))
        return 65
    # Public REST network is an independent opt-in, never inferred from
    # enabling the existing loopback N50/J2 read-only endpoints.
    if args.market_symbols and not args.allow_public_rest_samples:
        print(json.dumps({"status": "public_rest_optin_required",
                          "orders_sent": False}, sort_keys=True))
        return 65
    if args.allow_private_health_loopback != (args.private_health_directory is not None):
        print(json.dumps({
            "status": "private_health_explicit_optin_and_directory_required",
            "orders_sent": False,
        }, sort_keys=True))
        return 65
    if args.allow_last_public_paper_lease_loopback != (
            args.last_public_paper_lease_directory is not None):
        print(json.dumps({"status": "last_public_paper_lease_explicit_optin_required",
                          "orders_sent": False}, sort_keys=True))
        return 65
    if args.allow_resident_paper_status_loopback != (args.resident_paper_status_directory is not None):
        print(json.dumps({"status": "resident_paper_status_explicit_optin_required",
                          "orders_sent": False}, sort_keys=True))
        return 65
    if args.allow_paper_worker_loopback != (args.paper_worker_directory is not None):
        print(json.dumps({"status": "paper_worker_explicit_optin_and_directory_required",
                          "orders_sent": False}, sort_keys=True))
        return 65
    if args.allow_owner_paper_positions_loopback != (args.owner_paper_positions_directory is not None):
        print(json.dumps({"status": "owner_paper_positions_explicit_optin_required",
                          "orders_sent": False}, sort_keys=True))
        return 65
    if args.allow_paper_watch_loopback != (args.paper_watch_directory is not None):
        print(json.dumps({
            "status": "paper_watch_explicit_optin_and_directory_required",
            "orders_sent": False,
        }, sort_keys=True))
        return 65
    if args.allow_prospective_research_loopback != (args.prospective_research_directory is not None):
        print(json.dumps({"status": "prospective_research_explicit_optin_and_directory_required", "orders_sent": False}, sort_keys=True))
        return 65
    if args.allow_prospective_research_loopback:
        if os.name != "posix" or os.geteuid() == 0:
            print(json.dumps({"status": "prospective_research_unprivileged_owner_required", "orders_sent": False}, sort_keys=True)); return 65
        try: _owned_directory(args.prospective_research_directory)
        except (OSError, DataValidationError):
            print(json.dumps({"status": "prospective_research_owner_directory_unavailable", "orders_sent": False}, sort_keys=True)); return 65
    if args.allow_last_public_paper_lease_loopback:
        if os.name != "posix" or os.geteuid() == 0:
            print(json.dumps({"status": "last_public_paper_lease_nonroot_required",
                              "orders_sent": False}, sort_keys=True))
            return 65
        try:
            _owned_directory(args.last_public_paper_lease_directory)
        except (OSError, DataValidationError):
            print(json.dumps({"status": "last_public_paper_lease_owner_directory_unavailable",
                              "orders_sent": False}, sort_keys=True))
            return 65
    if args.allow_resident_paper_status_loopback:
        if os.name != "posix" or os.geteuid() == 0:
            print(json.dumps({"status": "resident_paper_status_nonroot_required",
                              "orders_sent": False}, sort_keys=True))
            return 65
        try:
            _owned_directory(args.resident_paper_status_directory)
        except (OSError, DataValidationError):
            print(json.dumps({"status": "resident_paper_status_directory_unavailable",
                              "orders_sent": False}, sort_keys=True))
            return 65
    if args.allow_paper_worker_loopback:
        if os.name != "posix" or os.geteuid() == 0:
            print(json.dumps({"status": "paper_worker_unprivileged_owner_required",
                              "orders_sent": False}, sort_keys=True))
            return 65
        try:
            _owned_directory(args.paper_worker_directory)
        except (OSError, DataValidationError):
            print(json.dumps({"status": "paper_worker_owner_directory_unavailable",
                              "orders_sent": False}, sort_keys=True))
            return 65
    if args.allow_owner_paper_positions_loopback:
        if os.name != "posix" or os.geteuid() == 0:
            print(json.dumps({"status": "owner_paper_positions_nonroot_required",
                              "orders_sent": False}, sort_keys=True))
            return 65
        try:
            _owned_directory(args.owner_paper_positions_directory)
        except (OSError, DataValidationError):
            print(json.dumps({"status": "owner_paper_positions_directory_unavailable",
                              "orders_sent": False}, sort_keys=True))
            return 65
    if args.allow_paper_watch_loopback:
        if os.name != "posix" or os.geteuid() == 0:
            print(json.dumps({
                "status": "paper_watch_unprivileged_owner_required",
                "orders_sent": False,
            }, sort_keys=True))
            return 65
        try:
            _owned_directory(args.paper_watch_directory)
        except (OSError, DataValidationError):
            print(json.dumps({
                "status": "paper_watch_owner_directory_unavailable",
                "orders_sent": False,
            }, sort_keys=True))
            return 65
    if args.allow_private_health_loopback:
        if os.name != "posix" or os.geteuid() == 0:
            print(json.dumps({
                "status": "unprivileged_posix_owner_required",
                "orders_sent": False,
            }, sort_keys=True))
            return 65
        try:
            _owned_directory(args.private_health_directory)
        except (OSError, DataValidationError):
            print(json.dumps({
                "status": "private_health_owner_directory_unavailable",
                "orders_sent": False,
            }, sort_keys=True))
            return 65
    names = tuple(args.market_symbols.split(",")) if args.market_symbols else ()
    if args.allow_public_rest_samples and (
        not 1 <= len(names) <= 50 or
        len(set(names)) != len(names) or
        any(type(x) is not str or _SYMBOL.fullmatch(x) is None for x in names)
    ):
        print(json.dumps({"status": "invalid_public_rest_membership",
                          "orders_sent": False}, sort_keys=True))
        return 65
    LoopbackPanelHandler.market_symbols = tuple(sorted(names)) if args.allow_public_rest_samples else ()
    LoopbackPanelHandler.market_last_attempt_ms = 0
    LoopbackPanelHandler.market_cached = None
    LoopbackPanelHandler.public_health_directory = (
        args.private_health_directory if args.allow_private_health_loopback else None
    )
    LoopbackPanelHandler.paper_watch_directory = (
        args.paper_watch_directory if args.allow_paper_watch_loopback else None
    )
    LoopbackPanelHandler.persisted_paper_directory = (
        args.owner_paper_positions_directory
        if args.allow_owner_paper_positions_loopback else None
    )
    LoopbackPanelHandler.paper_worker_directory = (
        args.paper_worker_directory if args.allow_paper_worker_loopback else None
    )
    LoopbackPanelHandler.resident_paper_directory = (
        args.resident_paper_status_directory
        if args.allow_resident_paper_status_loopback else None
    )
    LoopbackPanelHandler.last_public_paper_lease_directory = (
        args.last_public_paper_lease_directory
        if args.allow_last_public_paper_lease_loopback else None
    )
    LoopbackPanelHandler.prospective_research_directory = (
        args.prospective_research_directory if args.allow_prospective_research_loopback else None
    )
    try:
        with HTTPServer((HOST, PORT), LoopbackPanelHandler) as server:
            print(json.dumps({
                "status": "loopback_readonly_panel_serving",
                "address": f"http://{HOST}:{PORT}/",
                "external_access_enabled": False,
                "public_rest_opted_in": bool(LoopbackPanelHandler.market_symbols),
                "orders_sent": False,
            }, sort_keys=True), flush=True)
            server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        return 0
    except OSError:
        print(json.dumps({
            "status": "loopback_bind_unavailable",
            "external_access_enabled": False,
            "orders_sent": False,
        }, sort_keys=True))
        return 65
    return 0


if __name__ == "__main__":
    sys.exit(main())
