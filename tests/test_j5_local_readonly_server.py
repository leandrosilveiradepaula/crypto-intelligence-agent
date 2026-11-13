"""J5/APP-SYNC1: local status endpoint security and truthful count-only data."""
from __future__ import annotations

from contextlib import closing
from http.client import HTTPConnection
from http.server import HTTPServer
import io
import json
from pathlib import Path
from threading import Thread
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.bybit_closed_stream_cache import HOUR_MS
from crypto_intelligence_agent.j5_n50_ws_hour_progress import (
    project_n50_ws_log_progress,
)
from scripts import serve_j5_local_readonly as panel

BASE = (1_800_000_000_000 // HOUR_MS) * HOUR_MS
NOW = BASE + 5 * HOUR_MS + 4 * 60_000


def report_event(hour: int, *, failed: bool = False) -> dict:
    end = BASE + hour * HOUR_MS
    return {
        "_SYSTEMD_UNIT": "cia-j1-n50-ws.service",
        "__REALTIME_TIMESTAMP": str((end + 102_000) * 1000),
        "MESSAGE": json.dumps({
            "schema_version": "j1-n50-ws-cached-owner-window-v1",
            "status": ("ws_owner_hour_audit_abstain" if failed
                       else "ws_owner_hour_50_observed_local_only"),
            "expected_contracts": 50,
            "confirmed_contracts": 0 if failed else 50,
            "missing_contracts": 50 if failed else 0,
            "closed_events_appended_to_ws_journal": 50,
            "subscription_acks": 1,
            "http_gets": 0,
            "orders_sent": False,
            "rest_database_modified": False,
            "systemd_modified": False,
            "utc_closed_hour_end_ms": end,
            "hour_evidence_sha256": None if failed else "a" * 64,
            "source_provenance": None if failed else "bybit_public_ws_confirmed",
            "secret": "BTCUSDT private key=NEVER_EXPORT",
        }, separators=(",", ":")),
    }


def source_bytes() -> bytes:
    return ("\n".join(json.dumps(x) for x in (
        report_event(3, failed=True),
        report_event(4),
        report_event(5),
    )) + "\n").encode()


class SourceProjectionTests(unittest.TestCase):
    def test_bounded_subprocess_and_existing_projection(self):
        outcome = SimpleNamespace(returncode=0, stdout=source_bytes())
        with patch.object(panel.subprocess, "run", return_value=outcome) as run:
            report = panel.read_n50_progress(now_ms=NOW)
        args, kwargs = run.call_args
        self.assertEqual(args[0], list(panel._JOURNALCTL_ARGV))
        self.assertNotIn("shell", kwargs)
        self.assertEqual(kwargs["timeout"], 6)
        self.assertIs(kwargs["stderr"], panel.subprocess.DEVNULL)
        self.assertEqual(report["observed_50_of_50_hours"], 2)
        self.assertEqual(report["failed_hours"], 1)
        self.assertEqual(report["consecutive_recent_observed_hours"], 2)
        self.assertEqual(report["hours_in_window"], 24)
        self.assertFalse(report["owner_d323_24h_audit_verified"])
        self.assertFalse(report["source_authenticated"])
        self.assertEqual(report["network_requests"], 0)
        output = json.dumps(report)
        for forbidden in ("BTCUSDT", "NEVER_EXPORT", "secret", "MESSAGE",
                          "hour_evidence_sha256", "/home/"):
            self.assertNotIn(forbidden, output)

    def test_source_failures_fail_closed(self):
        cases = (
            SimpleNamespace(returncode=1, stdout=b""),
            SimpleNamespace(returncode=0, stdout=b""),
            SimpleNamespace(returncode=0, stdout=b"x" * 1_048_577),
            SimpleNamespace(returncode=0, stdout=b"bad JSON\n"),
        )
        for value in cases:
            with self.subTest(code=value.returncode, size=len(value.stdout)), patch.object(
                panel.subprocess, "run", return_value=value
            ), self.assertRaises(panel.SourceNotReady):
                panel.read_n50_progress(now_ms=NOW)
        with patch.object(
            panel.subprocess, "run",
            side_effect=panel.subprocess.TimeoutExpired("journalctl", 6),
        ), self.assertRaises(panel.SourceNotReady):
            panel.read_n50_progress(now_ms=NOW)

    def test_cli_without_optin_never_binds_a_port(self):
        with patch.object(panel, "HTTPServer", side_effect=AssertionError("bind")), patch(
            "sys.stdout", new_callable=io.StringIO
        ) as out:
            self.assertEqual(panel.main([]), 65)
        result = json.loads(out.getvalue())
        self.assertEqual(result["status"], "explicit_loopback_optin_required")
        self.assertFalse(result["network_public"])


class LoopbackHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer((panel.HOST, panel.PORT),
                                panel.LoopbackPanelHandler)
        cls.worker = Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.worker.join(timeout=3)

    def get(self, method: str, path: str, host: str | None = None,
            origin: str | None = None):
        headers = {}
        if host is not None:
            headers["Host"] = host
        if origin is not None:
            headers["Origin"] = origin
        with closing(HTTPConnection(panel.HOST, panel.PORT, timeout=4)) as connection:
            connection.request(method, path, headers=headers)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()

    def test_ui_static_served_with_secure_headers_and_no_public_assets(self):
        code, headers, data = self.get("GET", "/")
        self.assertEqual(code, 200)
        self.assertIn(b"CRYPTO", data)
        self.assertEqual(headers.get("Cache-Control"), "no-store, max-age=0")
        self.assertEqual(headers.get("X-Frame-Options"), "DENY")
        self.assertIn("connect-src 'self'", headers.get("Content-Security-Policy", ""))
        self.assertNotIn("Access-Control-Allow-Origin", headers)
        self.assertNotIn("Set-Cookie", headers)
        for asset in ("/app.js", "/engine.js", "/style.css", "/index.html"):
            with self.subTest(asset=asset):
                self.assertEqual(self.get("GET", asset)[0], 200)
        for denied in ("/README.md", "/../docs/DECISIONS.md",
                       "/%2e%2e/docs/STATUS.md", "/api/orders", "/api/n50-progress?x=1"):
            with self.subTest(path=denied):
                self.assertEqual(self.get("GET", denied)[0], 404)

    def test_api_count_only_and_no_order_methods(self):
        synthetic = project_n50_ws_log_progress([], now_ms=NOW)
        with patch.object(panel, "read_n50_progress", return_value=synthetic) as read:
            code, headers, body = self.get("GET", "/api/n50-progress")
        self.assertEqual(code, 200)
        read.assert_called_once()
        self.assertEqual(headers["Content-Type"], "application/json; charset=utf-8")
        self.assertNotIn("Access-Control-Allow-Origin", headers)
        result = json.loads(body)
        self.assertEqual(result["hours_in_window"], 24)
        self.assertFalse(result["owner_d323_24h_audit_verified"])
        self.assertFalse(result["orders_sent"])
        for method in ("POST", "PUT", "DELETE", "OPTIONS", "HEAD"):
            with self.subTest(method=method):
                self.assertEqual(self.get(method, "/api/n50-progress")[0], 405)

    def test_no_internet_host_header_dns_rebinding(self):
        for host in ("evil.example:8765", "evil.example", "localhost:443",
                     "127.0.0.1:8799"):
            with self.subTest(host=host):
                self.assertEqual(self.get("GET", "/api/n50-progress", host)[0],403)
        self.assertEqual(
            self.get("GET", "/api/n50-progress", origin="https://evil.example")[0],
            403,
        )
        with patch.object(panel, "read_n50_progress",
                          side_effect=panel.SourceNotReady("not available")):
            self.assertEqual(
                self.get("GET", "/api/n50-progress", "localhost:8765")[0], 503
            )

    def test_source_failure_never_includes_raw_exception(self):
        with patch.object(panel,"read_n50_progress",
                          side_effect=panel.SourceNotReady("TOKEN SECRET")):
            code, _, data = self.get("GET", "/api/n50-progress")
        self.assertEqual(code, 503)
        self.assertEqual(json.loads(data)["status"], "source_not_available")
        self.assertNotIn(b"TOKEN", data)
        self.assertNotIn(b"SECRET", data)


if __name__ == "__main__":
    unittest.main()
