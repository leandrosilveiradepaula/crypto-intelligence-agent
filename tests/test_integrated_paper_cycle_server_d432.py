"""D432: owner projection writer, nofollow reader and fail-closed HTTP tests."""
from __future__ import annotations

from contextlib import closing
from http.client import HTTPConnection
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from threading import Thread
from unittest.mock import patch

from crypto_intelligence_agent.market_data import DataValidationError
from scripts import publish_integrated_paper_cycle_d432 as producer
from scripts import serve_j5_local_readonly as server

@unittest.skipUnless(os.name == "posix" and os.geteuid() != 0, "nonroot POSIX owner only")
class D432OwnerReaderTests(unittest.TestCase):
    def test_writer_is_atomic_owner_only_and_reader_agrees(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root)
            directory.chmod(0o700)
            report = {
                "schema_version": "j6_full_offline_paper_lifecycle_v1",
                "mode": "offline_paper",
                "stages": [
                    "j2_risk_open_intent_reserved_without_fill",
                    "explicit_fixture_open_fill_crosschecked_on_restart",
                    "three_explicit_fixture_partial_fills",
                    "runner2_hypothetical_trigger",
                    "runner_reduce_only_pending_recovered_without_fill",
                    "explicit_fixture_runner_fill_and_pre8_audit",
                ],
                "orders_sent": False, "network_requests": 0,
                "live_trading_authorized": False, "approved_for_live_use": False,
                "market_data_real": False, "financial_pnl_available": False,
                "native_stop_verified": False, "restart_duplicate_orders": 0,
                "confirmed_remaining_units": "0",
                "synthetic_partial_fills_injected_explicitly": 3,
            }
            def proof(*, side="LONG", scenario="two_targets_then_stop"):
                return {
                    "status": ("fixture_unknown_requires_reconciliation"
                               if scenario=="unknown_blocks_stop" else "fixture_cycle_closed"),
                    "position_side": side,
                    "orders_sent": False, "venue_account_connected": False,
                    "real_fills_verified": False,
                    "market_source": "SYNTHETIC_BYBIT_TICKER_FIXTURES",
                }
            with patch.object(producer, "run_full_offline_paper_lifecycle", return_value=report), patch.object(
                producer, "demonstrate_paper_intrahour_cycle", side_effect=proof,
            ) as intrahour:
                result = producer.publish(directory)
            self.assertEqual(intrahour.call_count, 3)
            self.assertTrue(result["bybit_intrahour_fixture_verified"])
            target = directory / producer._NAME
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
            self.assertEqual(server.read_integrated_cycle(directory=directory), report)
            target.chmod(0o644)
            with self.assertRaises(server.SourceNotReady):
                server.read_integrated_cycle(directory=directory)
            target.chmod(0o600)
            secret = directory / "not-public.txt"
            secret.write_text("sensitive")
            target.unlink()
            target.symlink_to(secret)
            with self.assertRaises(OSError):
                server.read_integrated_cycle(directory=directory)
            self.assertEqual(secret.read_text(), "sensitive")
            with patch.object(producer, "run_full_offline_paper_lifecycle", return_value=report), patch.object(
                producer, "demonstrate_paper_intrahour_cycle", side_effect=proof,
            ), self.assertRaises(DataValidationError):
                producer.publish(directory)
            self.assertTrue(target.is_symlink())

    def test_malicious_claim_never_published(self):
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root)
            directory.chmod(0o700)
            fixture = {
                "schema_version":"j6_full_offline_paper_lifecycle_v1",
                "mode":"offline_paper", "orders_sent":True,
            }
            with patch.object(producer,"run_full_offline_paper_lifecycle",return_value=fixture), patch.object(
                producer,"demonstrate_paper_intrahour_cycle",
                return_value={"status":"fixture_cycle_closed","position_side":"LONG"},
            ), self.assertRaises(DataValidationError):
                producer.publish(directory)
            self.assertFalse((directory/producer._NAME).exists())


class D432HTTPTests(unittest.TestCase):
    def test_disabled_and_sanitized_on_failure(self):
        cls = server.LoopbackPanelHandler
        original = cls.paper_watch_directory
        cls.paper_watch_directory = None
        httpd = server.HTTPServer((server.HOST, server.PORT), cls)
        worker = Thread(target=httpd.serve_forever, daemon=True)
        worker.start()
        try:
            def request(host=None):
                with closing(HTTPConnection(server.HOST,server.PORT,timeout=4)) as client:
                    client.request("GET","/api/integrated-paper-cycle",
                                   headers={"Host":host or f"{server.HOST}:{server.PORT}"})
                    r=client.getresponse()
                    return r.status, r.read()
            self.assertEqual(request()[0],503)
            self.assertEqual(request("external.example:8765")[0],403)
            cls.paper_watch_directory=Path("/unused-owner")
            with patch.object(server,"read_integrated_cycle",
                              side_effect=server.SourceNotReady("secret disk name")):
                status,body=request()
            self.assertEqual(status,503)
            self.assertNotIn(b"secret",body)
        finally:
            cls.paper_watch_directory=original
            httpd.shutdown()
            httpd.server_close()
            worker.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
