"""J1 #310: zero-network private progress audit and provider failure taxonomy."""
from contextlib import redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.bybit_public_j1_transport import (
    BoundedBybitPublicClient, J1BybitCaptureError,
    classify_provider_retcode, instruments_url, kline_url,
)
from scripts.audit_private_bybit_j1_progress import (
    BybitProgressAuditError, audit_private_bybit_j1_progress, main,
)
from scripts.capture_private_bybit_j1 import owner_private_j1_capture
from test_j1_private_bybit_capture import FakeFeed, H, T


class ProviderFailuresTests(unittest.TestCase):
    def test_official_codes_categorized_without_raw_retmsg_or_body(self):
        cases = (
            (10001, "provider_request_parameters_rejected_no_retry"),
            (10006, "provider_rate_limit_no_retry"),
            (10009, "provider_region_restriction"),
            (10024, "provider_region_restriction"),
            (10000, "provider_server_unavailable_no_retry"),
            (10016, "provider_server_unavailable_no_retry"),
            (10029, "provider_route_or_symbol_unavailable_no_retry"),
            (999777, "provider_unclassified_ret_code_no_retry"),
        )
        for code, reason in cases:
            with self.subTest(code=code):
                data = json.dumps({
                    "retCode": code,
                    "retMsg": "SECRET_PRICE_12345_PRIVATE_PATH",
                }).encode("ascii")
                client = BoundedBybitPublicClient(transport=lambda url, limit: data)
                with self.assertRaisesRegex(J1BybitCaptureError, reason) as error:
                    client.get(instruments_url())
                self.assertNotIn("SECRET_", str(error.exception))
                self.assertEqual(client.last_request_stage, "instrument_universe")
                self.assertEqual(client.requests_attempted, 1)
                self.assertEqual(
                    client.last_provider_retcode, code if code != 999777 else None,
                )

    def test_stage_identifies_kline_page_sizes_without_symbol_or_url(self):
        decision = T // H * H
        for hours, name in ((1, "closed_kline_1h"), (24, "closed_kline_24h"),
                            (72, "closed_kline_72h")):
            client = BoundedBybitPublicClient(transport=lambda url, limit: (
                b'{"retCode":10001,"retMsg":"NO_PRIVATE_SYMBOLS_ALLOWED"}'))
            with self.assertRaises(J1BybitCaptureError):
                client.get(kline_url("BTCUSDT", decision - hours * H, decision))
            self.assertEqual(client.last_request_stage, name)
            self.assertNotIn("BTC", client.last_request_stage)
        self.assertEqual(classify_provider_retcode(False),
                         "provider_retcode_invalid_no_retry")


@unittest.skipUnless(os.name == "posix", "private 0700/0600 audit requires POSIX")
class PrivateProgressAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name)
        self.dir.chmod(0o700)
        self.db = self.dir / "bybit.sqlite"

    def create_private_staged_history(self, *, fail_update=False):
        fake = FakeFeed()
        client = BoundedBybitPublicClient(transport=(
            (lambda url, limit: (
                b'{"retCode":10006,"retMsg":"too_many_visits!"}'
                if fake.call_count >= 43 else fake.get(url, limit)
            )) if fail_update else fake.get
        ))
        def advance(seconds):
            fake.observed += int(seconds * 1000) + 100
        args = dict(
            database=self.db, max_assets=2,
            two_hourly_updates=fail_update,
            allow_public_network=True, allow_private_storage=True,
            confirm_region_and_personal_research=True,
            client=client, clock_ms=fake.now, sleep=advance,
        )
        with patch("socket.create_connection",
                   side_effect=AssertionError("network forbidden")):
            if fail_update:
                with self.assertRaisesRegex(
                    J1BybitCaptureError, "provider_rate_limit_no_retry"
                ):
                    owner_private_j1_capture(**args)
            else:
                result = owner_private_j1_capture(**args)
                self.assertEqual(result["closed_candles"], 1440)
        return client

    def test_missing_database_is_safe_positive_finding(self):
        report = audit_private_bybit_j1_progress(
            database=self.db, allow_private_readonly_audit=True)
        self.assertEqual(report["status"], "private_bybit_db_absent")
        self.assertFalse(report["database_exists"])
        self.assertFalse(report["data_stored_by_this_audit"])
        self.assertFalse(self.db.exists())

    def test_one_snapshot_and_30d_survive_failed_first_hour(self):
        client = self.create_private_staged_history(fail_update=True)
        self.assertEqual(client.last_request_stage, "instrument_universe")
        self.assertEqual(client.last_provider_retcode, 10006)
        self.assertTrue(self.db.exists())
        before = self.db.read_bytes()
        with patch("socket.create_connection",
                   side_effect=AssertionError("no network during audit")):
            report = audit_private_bybit_j1_progress(
                database=self.db, allow_private_readonly_audit=True)
        self.assertEqual(report["status"], "private_bybit_progress_readonly_verified")
        self.assertTrue(report["sqlite_integrity_passed"])
        self.assertTrue(report["private_page_replay_passed"])
        self.assertEqual(report["sample_asset_count"], 2)
        self.assertEqual(report["stored_page_count"], 20)
        self.assertEqual(report["stored_closed_candle_rows"], 1440)
        self.assertEqual(report["immutable_pit_snapshots"], 1)
        self.assertEqual(report["min_hours_per_asset"], 720)
        self.assertEqual(report["consecutive_snapshots_at_end"], 0)
        self.assertTrue(report["first_pit_720h_coverage"])
        self.assertEqual(before, self.db.read_bytes())
        self.assertFalse(Path(str(self.db) + "-wal").exists())
        self.assertFalse(Path(str(self.db) + "-shm").exists())
        self.assertFalse(report["marketwide_top50_verified"])
        self.assertEqual(report["network_requests"], 0)

    def test_tampered_page_and_temp_sidecar_fail_closed(self):
        self.create_private_staged_history()
        original = self.db.read_bytes()
        with sqlite3.connect(self.db) as db:
            db.execute("UPDATE bybit_research_candles SET close='98765' "
                       "WHERE rowid=(SELECT MIN(rowid) FROM bybit_research_candles)")
        with self.assertRaisesRegex(BybitProgressAuditError, "replay"):
            audit_private_bybit_j1_progress(
                database=self.db, allow_private_readonly_audit=True)
        self.db.write_bytes(original)
        sidecar = Path(str(self.db) + "-wal")
        sidecar.write_bytes(b"x")
        with self.assertRaisesRegex(BybitProgressAuditError, "not_safe"):
            audit_private_bybit_j1_progress(
                database=self.db, allow_private_readonly_audit=True)

    def test_path_and_permissions_rejections(self):
        with self.assertRaises(BybitProgressAuditError):
            audit_private_bybit_j1_progress(database=self.db)
        self.create_private_staged_history()
        self.db.chmod(0o644)
        with self.assertRaisesRegex(BybitProgressAuditError, "path_rejected"):
            audit_private_bybit_j1_progress(
                database=self.db, allow_private_readonly_audit=True)
        self.db.chmod(0o600)
        alias = self.dir / "alias.sqlite"
        alias.symlink_to(self.db)
        with self.assertRaises(BybitProgressAuditError):
            audit_private_bybit_j1_progress(
                database=alias, allow_private_readonly_audit=True)

    def test_cli_outputs_only_sanitized_aggregate(self):
        self.create_private_staged_history()
        output = StringIO()
        with redirect_stdout(output):
            retcode = main([
                "--database", str(self.db), "--allow-private-readonly-audit",
            ])
        self.assertEqual(retcode, 0)
        report = json.loads(output.getvalue())
        self.assertEqual(report["stored_closed_candle_rows"], 1440)
        for private in (str(self.db), str(self.dir), "BTCUSDT", "ETHUSDT"):
            self.assertNotIn(private, output.getvalue())


if __name__ == "__main__":
    unittest.main()
