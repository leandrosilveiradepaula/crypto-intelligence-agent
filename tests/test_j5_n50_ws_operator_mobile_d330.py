"""J5/D330: mobile view accepts only sanitised D323 evidence."""
from __future__ import annotations

from html.parser import HTMLParser
import os
from pathlib import Path
import stat
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.j1_n50_ws_24h_witness import _result
from crypto_intelligence_agent.j5_n50_ws_operator_mobile import (
    InvalidN50OperatorWitness,
    render_n50_ws_operator_html,
    validate_n50_ws_operator_witness,
    write_n50_ws_operator_html_once,
)
from scripts.render_j5_n50_ws_operator_once import main as cli_main

NOW = 1_794_492_600_000
END = NOW - NOW % 3_600_000
SHA = "a" * 64


def witness(status: str = "awaiting_owner_ws_journal_audit"):
    out = _result(status)
    out.update(
        latest_eligible_closed_end_ms=END,
        ws_timer_active_enabled=True,
        rotation_timer_active_enabled=True,
        n2_quiesced=True,
        old_rest_n50_quiesced=True,
        ws_service_not_failed=True,
    )
    if status in (
        "accumulating_or_incomplete_ws_24h",
        "ws_24h_local_evidence_verified",
    ):
        out.update(
            persisted_ws_rows=830,
            ranked_scope_sha256=SHA,
            ws_metadata_sha256=SHA,
            ws_journal_sha256=SHA,
            ws_journal_integrity_verified=True,
        )
    if status == "ws_24h_local_evidence_verified":
        out.update(
            verified_closed_hours=24,
            verified_contracts_per_hour=50,
            persisted_ws_rows=1200,
            last_hour_sha256=SHA,
            ws_closed_24h_local_verified=True,
        )
    if status == "n2_failback_observed":
        out.update(
            ws_timer_active_enabled=False,
            rotation_timer_active_enabled=False,
            n2_quiesced=False,
            ws_service_not_failed=False,
        )
    return out


class Document(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.text = []
        self.attrs = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attrs.append((tag, dict(attrs)))

    def handle_data(self, data):
        self.text.append(data)


class J5N50MobileWitnessTests(unittest.TestCase):
    def test_valid_24h_is_local_evidence_only_not_approved_trading(self):
        source = witness("ws_24h_local_evidence_verified")
        view = validate_n50_ws_operator_witness(source, observed_at_ms=NOW)
        self.assertTrue(view["local24"])
        self.assertEqual(view["verified_closed_hours"], 24)
        self.assertEqual(view["persisted_rows"], 1200)
        html = render_n50_ws_operator_html(source, observed_at_ms=NOW)
        page = Document()
        page.feed(html)
        page.close()
        self.assertEqual(page.tags.count("main"), 1)
        self.assertNotIn("script", page.tags)
        self.assertNotIn("form", page.tags)
        self.assertNotIn("button", page.tags)
        self.assertNotIn("iframe", page.tags)
        self.assertIn("lang=\"pt-BR\"", html)
        self.assertIn("width=device-width", html)
        self.assertIn("default-src 'none'", html)
        self.assertIn("24 / 24", html)
        self.assertIn("24 horas locais auditadas", html)
        self.assertIn("não comprova operação contínua 24/7", html)
        self.assertIn("data-trading=\"disabled\"", html)
        self.assertNotIn("BTCUSDT", html)
        self.assertNotIn(SHA, html)
        self.assertNotIn("https://", html)

    def test_schedule_alone_never_looks_like_a_confirmed_closed_hour(self):
        html = render_n50_ws_operator_html(witness(), observed_at_ms=NOW)
        self.assertIn("Agendamentos disponíveis; journal ainda não auditado", html)
        self.assertIn("0 / 24", html)
        self.assertIn("Ativo e habilitado", html)
        self.assertIn("Ainda não comprovada", html)
        self.assertIn("Timer habilitado não significa candle recebido", html)

    def test_partial_journal_rows_do_not_claim_hours_complete(self):
        source = witness("accumulating_or_incomplete_ws_24h")
        html = render_n50_ws_operator_html(source, observed_at_ms=NOW)
        self.assertIn("830", html)
        self.assertIn("0 / 24", html)
        self.assertIn("sem aceite 24h", html)
        self.assertNotIn("24 horas locais auditadas", html)

    def test_n2_fallback_becomes_warning_even_if_timer_history_exists(self):
        source = witness("n2_failback_observed")
        html = render_n50_ws_operator_html(source, observed_at_ms=NOW)
        self.assertIn("Fallback N2 observado", html)
        self.assertIn("Verificar / pode ter sido acionado", html)
        self.assertIn("Não confirmado", html)

    def test_invalid_contracts_are_rejected_before_html(self):
        cases = []
        base = witness("ws_24h_local_evidence_verified")
        for key, value in (
            ("verified_closed_hours", 23),
            ("verified_contracts_per_hour", 49),
            ("persisted_ws_rows", 1199),
            ("ws_timer_active_enabled", False),
            ("ws_journal_integrity_verified", False),
            ("last_hour_sha256", None),
            ("approved_for_signals", True),
            ("live_trading_authorized", True),
            ("orders_sent", True),
            ("network_requests", True),
            ("expected_contracts_per_hour", 52),
            ("status", "<img src=x onerror=alert(1)>"),
            ("ws_journal_sha256", "not-a-sha"),
        ):
            case = dict(base)
            case[key] = value
            cases.append((key, case))
        extra = dict(base)
        extra["secret_private_field"] = "never printable"
        cases.append(("extra", extra))
        for key, candidate in cases:
            with self.subTest(field=key):
                with self.assertRaises(InvalidN50OperatorWitness):
                    render_n50_ws_operator_html(candidate, observed_at_ms=NOW)

    def test_incomplete_case_cannot_promote_24h_or_forged_integrity(self):
        base = witness("accumulating_or_incomplete_ws_24h")
        base["ws_closed_24h_local_verified"] = True
        with self.assertRaises(InvalidN50OperatorWitness):
            render_n50_ws_operator_html(base, observed_at_ms=NOW)
        base = witness()
        base["persisted_ws_rows"] = 50
        with self.assertRaises(InvalidN50OperatorWitness):
            render_n50_ws_operator_html(base, observed_at_ms=NOW)

    def test_time_grid_future_and_bool_now_rejected(self):
        for now in (True, 0, END - 1, END + 3_600_000):
            with self.subTest(now=now):
                with self.assertRaises(InvalidN50OperatorWitness):
                    render_n50_ws_operator_html(witness(), observed_at_ms=now)
        source = witness()
        source["latest_eligible_closed_end_ms"] = END + 1000
        with self.assertRaises(InvalidN50OperatorWitness):
            render_n50_ws_operator_html(source, observed_at_ms=NOW)


@unittest.skipUnless(os.name == "posix", "private POSIX DAC")
class J5N50MobileWriteTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "ws"
        self.root.mkdir(mode=0o700)

    def write(self, report=None, **kwargs):
        args = {
            "observed_at_ms": NOW, "root_directory": self.root,
            "allow_private_report_write": True, "owner_ok": True,
        }
        args.update(kwargs)
        return write_n50_ws_operator_html_once(
            witness() if report is None else report, **args,
        )

    def test_writes_0600_once_no_network_no_db_orders_or_public_paths(self):
        saved = self.write()
        self.assertEqual(saved["status"], "private_report_saved")
        self.assertEqual(saved["orders_sent"], False)
        self.assertEqual(saved["network_requests"], 0)
        self.assertEqual(saved["systemd_modified"], False)
        self.assertEqual(saved["ws_database_modified"], False)
        path = self.root / "operator-reports" / saved["file_name"]
        self.assertTrue(path.is_file())
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)
        self.assertIn("Somente pesquisa", path.read_text())
        self.assertEqual(self.write()["status"], "identical_private_report_exists")
        self.assertEqual(len(list(path.parent.iterdir())), 1)

    def test_refuses_without_optin_or_wrong_owner_and_invalid_evidence(self):
        self.assertEqual(self.write(allow_private_report_write=False)
                         ["status"], "optin_required")
        self.assertEqual(self.write(owner_ok=False)["status"], "blocked")
        wrong = witness()
        wrong["orders_sent"] = True
        self.assertEqual(self.write(report=wrong)["status"], "blocked")
        self.assertFalse((self.root / "operator-reports").exists())

    def test_symlink_root_or_existing_report_is_never_overwritten(self):
        link = self.root.parent / "linked"
        link.symlink_to(self.root, target_is_directory=True)
        self.assertEqual(self.write(root_directory=link)["status"], "blocked")
        first = self.write()
        dest = self.root / "operator-reports" / first["file_name"]
        dest.write_text("tampered", encoding="utf-8")
        self.assertEqual(self.write()["status"], "blocked")
        self.assertEqual(dest.read_text(), "tampered")

    def test_existing_symlink_with_correct_name_does_not_follow(self):
        report_dir = self.root / "operator-reports"
        report_dir.mkdir(mode=0o700)
        elsewhere = self.root / "other"
        elsewhere.write_text("untouched")
        dest = report_dir / f"n50-ws-ops-{NOW}.html"
        dest.symlink_to(elsewhere)
        self.assertEqual(self.write()["status"], "blocked")
        self.assertEqual(elsewhere.read_text(), "untouched")


class J5N50MobileCLITests(unittest.TestCase):
    def test_three_optins_fail_before_any_read_or_write(self):
        with patch("scripts.render_j5_n50_ws_operator_once.observe_n50_ws_24h",
                   side_effect=AssertionError("unauthorised read")):
            with patch("scripts.render_j5_n50_ws_operator_once.write_n50_ws_operator_html_once",
                       side_effect=AssertionError("unauthorised write")):
                self.assertEqual(cli_main([]), 65)
                self.assertEqual(cli_main([
                    "--allow-private-readonly-audit",
                    "--enable-ws-24h-witness",
                ]), 65)

    def test_explicit_optins_call_existing_witness_once_without_market(self):
        with patch("scripts.render_j5_n50_ws_operator_once.observe_n50_ws_24h",
                   return_value=witness()) as observed:
            with patch("scripts.render_j5_n50_ws_operator_once.write_n50_ws_operator_html_once",
                       return_value={"status": "private_report_saved"}) as saved:
                self.assertEqual(cli_main([
                    "--allow-private-readonly-audit",
                    "--enable-ws-24h-witness",
                    "--allow-private-report-write",
                ]), 0)
                observed.assert_called_once()
                self.assertTrue(observed.call_args.kwargs["enable_ws_24h_witness"])
                saved.assert_called_once()
                self.assertTrue(saved.call_args.kwargs["allow_private_report_write"])


if __name__ == "__main__":
    unittest.main()
