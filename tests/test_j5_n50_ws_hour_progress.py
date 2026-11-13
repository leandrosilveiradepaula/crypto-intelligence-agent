"""J5/PROGRESS1: adversarial log-derived N50 progress without D323 claims."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from html.parser import HTMLParser
from decimal import Decimal
import json
import socket
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.bybit_closed_stream_cache import HOUR_MS
from crypto_intelligence_agent.j5_n50_ws_hour_progress import (
    project_n50_ws_log_progress, render_n50_ws_log_progress_html,
)
from crypto_intelligence_agent.market_data import DataValidationError

T = 1_800_000_000_000
M = 60_000
SHA = "b" * 64

def row(hour, status="ws_owner_hour_50_observed_local_only", *,
        appends=50, confirmed=50, digest=SHA, end=True):
    close = T + hour*HOUR_MS
    ok = status == "ws_owner_hour_50_observed_local_only"
    return {
        "finished_at_ms": close + 118_000,
        "report": {
            "schema_version": "j1-n50-ws-cached-owner-window-v1",
            "status": status,
            "expected_contracts": 50,
            "confirmed_contracts": confirmed,
            "missing_contracts": 50-confirmed,
            "utc_closed_hour_end_ms": close if end else None,
            "hour_evidence_sha256": digest if ok else None,
            "source_provenance": "bybit_public_ws_confirmed" if ok else None,
            "closed_events_appended_to_ws_journal": appends,
            "subscription_acks": 1,
            "http_gets": 0,
            "rest_database_modified": False,
            "systemd_modified": False,
            "orders_sent": False,
        },
    }


def failing(hour):
    return row(hour, "ws_owner_hour_audit_abstain",
               appends=50, confirmed=0, digest=None, end=False)


def project(entries=(), now=T+5*HOUR_MS+4*M):
    return project_n50_ws_log_progress(entries, now_ms=now)


class SummaryTests(unittest.TestCase):
    def test_50_appends_without_audit_is_failed_not_success(self):
        report = project([row(3), failing(4), row(5)])
        self.assertEqual(report["hours_in_window"], 24)
        self.assertEqual(report["observed_50_of_50_hours"], 2)
        self.assertEqual(report["consecutive_recent_observed_hours"], 1)
        self.assertEqual(report["failed_hours"], 1)
        self.assertEqual(report["missing_hours"], 21)
        self.assertEqual(report["duplicate_hours"], 0)
        self.assertEqual([r["state"] for r in report["slots"][-3:]],
                         ["ok", "failed", "ok"])
        for key in (
            "owner_d323_24h_audit_verified",
            "rotation_36h_live_verified",
            "continuous_collector_verified",
            "marketwide_top50_verified",
            "crypto_identity_independently_verified",
            "source_authenticated",
            "approved_for_signals",
            "live_trading_authorized",
            "orders_sent",
            "database_accessed",
            "systemd_modified",
        ):
            self.assertFalse(report[key], key)
        self.assertEqual(report["network_requests"], 0)
        self.assertNotIn("bybit", json.dumps(report))
        self.assertNotIn(SHA, json.dumps(report))

    def test_24_successful_logs_never_approve_formal_d323(self):
        entries = [row(i) for i in range(1, 25)]
        report = project(entries, now=T+24*HOUR_MS+4*M)
        self.assertEqual(report["observed_50_of_50_hours"], 24)
        self.assertEqual(report["consecutive_recent_observed_hours"], 24)
        self.assertEqual(report["failed_hours"], 0)
        self.assertEqual(report["missing_hours"], 0)
        self.assertFalse(report["owner_d323_24h_audit_verified"])
        self.assertFalse(report["continuous_collector_verified"])

    def test_missing_hour_resets_streak_and_duplicate_abstains(self):
        report = project([row(3),row(5)])
        self.assertEqual(report["consecutive_recent_observed_hours"], 1)
        self.assertEqual(report["missing_hours"], 22)
        duplicate = project([row(5), deepcopy(row(5))])
        self.assertEqual(duplicate["duplicate_hours"], 1)
        self.assertEqual(duplicate["observed_50_of_50_hours"], 0)
        self.assertEqual(duplicate["consecutive_recent_observed_hours"], 0)
        conflicted = project([row(5), failing(5)])
        self.assertEqual(conflicted["duplicate_hours"], 1)
        self.assertEqual(conflicted["observed_50_of_50_hours"], 0)

    def test_three_minute_settlement_prevents_premature_missing(self):
        early = project([row(4)], now=T+5*HOUR_MS+2*M)
        self.assertEqual(early["latest_eligible_closed_end_ms"], T+4*HOUR_MS)
        self.assertEqual(early["consecutive_recent_observed_hours"], 1)
        self.assertEqual(early["observed_50_of_50_hours"], 1)
        late = project([row(4)], now=T+5*HOUR_MS+3*M)
        self.assertEqual(late["latest_eligible_closed_end_ms"], T+5*HOUR_MS)
        self.assertEqual(late["consecutive_recent_observed_hours"], 0)
        with self.assertRaises(DataValidationError):
            project([row(5)], now=T+5*HOUR_MS+2*M)

    def test_malformed_and_forged_sanitized_reports_rejected(self):
        base = row(5)
        changes = (
            ("schema_version", "other"),
            ("status", "<script>alert(1)</script>"),
            ("status", ["unhashable"]),
            ("expected_contracts", True),
            ("expected_contracts", 52),
            ("confirmed_contracts", 49),
            ("confirmed_contracts", True),
            ("missing_contracts", 1),
            ("hour_evidence_sha256", None),
            ("hour_evidence_sha256", "not-a-digest"),
            ("source_provenance", "unverified"),
            ("orders_sent", True),
            ("http_gets", 1),
            ("systemd_modified", True),
            ("closed_events_appended_to_ws_journal", 100),
            ("subscription_acks", 0),
        )
        for key,value in changes:
            with self.subTest(key=key, value=str(value)[:30]):
                bad = deepcopy(base)
                bad["report"][key] = value
                with self.assertRaises(DataValidationError):
                    project([bad])

    def test_bad_type_end_time_and_future_rejected(self):
        for raw in (
            True, "not an entry", {"finished_at_ms": T, "report": {}},
            {"finished_at_ms": T, "report": {}, "secret": "x"},
        ):
            with self.subTest(item=str(raw)[:60]), self.assertRaises(DataValidationError):
                project([raw])
        for wrong in (T+5*HOUR_MS-1, T+5*HOUR_MS+181_000,
                      T+5*HOUR_MS+HOUR_MS):
            bad = row(5)
            bad["finished_at_ms"] = wrong
            with self.subTest(wrong=wrong), self.assertRaises(DataValidationError):
                project([bad])
        for now in (True, 0, float(T), T+5*HOUR_MS+2*M):
            with self.subTest(now=now), self.assertRaises(DataValidationError):
                project([row(5)], now=now)
        with self.assertRaises(DataValidationError):
            project([row(5)] * 4097)

    def test_rendered_mobile_is_static_accessible_and_never_echoes_payload(self):
        source = row(5)
        source["report"]["unexpected_symbol"] = "<img src=x onerror=alert(1)>BTCUSDT"
        html = render_n50_ws_log_progress_html([source, failing(4)], now_ms=T+5*HOUR_MS+4*M)
        self.assertIn('lang="pt-BR"', html)
        self.assertIn("width=device-width", html)
        self.assertIn("default-src 'none'", html)
        self.assertIn("Acompanhamento preliminar, não homologação", html)
        self.assertIn("1 / 24", html)
        self.assertIn("Sequência recente sem lacunas", html)
        self.assertIn("24h no journal SQLite", html)
        self.assertNotIn("BTCUSDT", html)
        self.assertNotIn(SHA, html)
        self.assertNotIn("https://", html)
        self.assertNotIn("<script", html.lower())
        self.assertNotIn("<form", html.lower())
        self.assertLess(len(html.encode("utf-8")), 32768)
        class HTML(HTMLParser):
            def __init__(self):
                super().__init__()
                self.tags = []
            def handle_starttag(self, tag, attrs):
                self.tags.append(tag)
        parser = HTML()
        parser.feed(html)
        parser.close()
        self.assertEqual(parser.tags.count("li"), 24)
        self.assertNotIn("script", parser.tags)
        self.assertNotIn("button", parser.tags)
        self.assertNotIn("form", parser.tags)

    def test_deterministic_no_database_or_network(self):
        with patch("socket.create_connection", side_effect=AssertionError("net")), patch(
            "urllib.request.urlopen", side_effect=AssertionError("http")
        ), patch("sqlite3.connect", side_effect=AssertionError("db")):
            a = project([row(3), failing(4), row(5)])
            b = project([row(5),row(3), failing(4)])
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
