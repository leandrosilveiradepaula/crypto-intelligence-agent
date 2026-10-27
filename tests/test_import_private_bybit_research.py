"""J1 #217: end-to-end owner-only local file import using synthetic Bybit bytes."""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.bybit_research_storage import SQLiteBybitResearchStore
from scripts.import_private_bybit_research import (
    PrivateBybitStagingError, stage_owner_supplied_bybit_files, main,
)
from test_bybit_research_storage import sample


@unittest.skipUnless(os.name == "posix", "private POSIX 0700/0600 required")
class PrivateBybitImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.folder.chmod(0o700)
        instrument, kline, manifest = sample()
        self.manifest = self.folder / "manifest.json"
        self.instrument = self.folder / "instrument.json"
        self.kline = self.folder / "kline.json"
        self.db = self.folder / "research.sqlite"
        body = {name: getattr(manifest, name) for name in (
            "symbol", "interval", "registry_variant", "start_open_ms",
            "end_open_ms", "capture_started_ms", "instrument_received_ms",
            "kline_received_ms", "capture_finished_ms",
        )}
        for path, raw in (
            (self.manifest, json.dumps(body).encode("ascii")),
            (self.instrument, instrument), (self.kline, kline),
        ):
            path.write_bytes(raw)
            path.chmod(0o600)
        self.window = manifest

    def import_now(self, **override):
        inputs = dict(
            manifest_path=str(self.manifest), instrument_path=str(self.instrument),
            kline_path=str(self.kline), database_path=str(self.db),
            allow_private_offline_input=True,
            allow_private_research_staging=True,
            attest_source_and_retention_rights_reviewed=True,
        )
        inputs.update(override)
        return stage_owner_supplied_bybit_files(**inputs)

    def test_idempotent_valid_fixture_to_sqlite_replay_without_network(self):
        with patch("urllib.request.urlopen", side_effect=AssertionError("network")):
            with patch("socket.create_connection", side_effect=AssertionError("network")):
                first = self.import_now()
                second = self.import_now()
        self.assertEqual(first, second)
        self.assertEqual(first["staged_closed_candles"], 3)
        self.assertEqual(first["network_requests"], 0)
        self.assertTrue(first["data_stored_locally"])
        self.assertEqual(self.db.stat().st_mode & 0o777, 0o600)
        for flag in (
            "provider_authenticated", "rights_authorized",
            "canonical_ohlcv_approved", "historical_top50_approved",
            "financial_backtest_approved", "ready_for_trading",
            "live_trading_authorized", "orders_sent",
        ):
            self.assertIs(first[flag], False)
        quality = SQLiteBybitResearchStore(self.db).quality_report(
            symbol=self.window.symbol, interval=self.window.interval,
            start_open_ms=self.window.start_open_ms,
            end_open_ms=self.window.end_open_ms,
        )
        self.assertTrue(quality.complete_for_offline_staging_only)

    def test_all_three_owner_flags_are_required_before_disk_io(self):
        for flag in (
            "allow_private_offline_input", "allow_private_research_staging",
            "attest_source_and_retention_rights_reviewed",
        ):
            with self.subTest(flag=flag):
                with self.assertRaises(PrivateBybitStagingError):
                    self.import_now(**{flag: False})
                self.assertFalse(self.db.exists())

    def test_unsafe_path_input_mode_and_hardlinked_db_fail_closed(self):
        self.instrument.chmod(0o644)
        with self.assertRaises(Exception):
            self.import_now()
        self.assertFalse(self.db.exists())
        self.instrument.chmod(0o600)
        for target in (str(self.instrument), "relative.sqlite",
                       str(self.folder / "not_sqlite.txt")):
            with self.subTest(target=target), self.assertRaises(Exception):
                self.import_now(database_path=target)
        self.assertFalse(self.db.exists())
        self.db.write_bytes(b"")
        self.db.chmod(0o600)
        os.link(self.db, self.folder / "hardlink.sqlite")
        with self.assertRaisesRegex(PrivateBybitStagingError, "hardlinked"):
            self.import_now()
        self.assertTrue(self.db.exists())

    def test_corrupt_input_cannot_create_db(self):
        self.kline.write_bytes(b'{"retCode":0,"result":{"list":[]}}')
        self.kline.chmod(0o600)
        with self.assertRaises(Exception):
            self.import_now()
        self.assertFalse(self.db.exists())

    def test_cli_returns_only_sanitized_no_market_data(self):
        args = [
            "--manifest", str(self.manifest), "--instrument", str(self.instrument),
            "--kline", str(self.kline), "--database", str(self.db),
        ]
        out = StringIO()
        with redirect_stdout(out):
            result = main(args)
        self.assertEqual(result, 1)
        self.assertFalse(self.db.exists())
        self.assertEqual(json.loads(out.getvalue())["status"],
                         "private_research_import_rejected")
        self.assertNotIn(str(self.folder), out.getvalue())
        out = StringIO()
        with redirect_stdout(out):
            result = main(args + [
                "--allow-private-offline-input",
                "--allow-private-research-staging",
                "--attest-source-and-retention-rights-reviewed",
            ])
        self.assertEqual(result, 0)
        self.assertEqual(json.loads(out.getvalue())["staged_closed_candles"], 3)
        for raw in (str(self.folder), "BTCUSDT", "api_key",
                    "instrument_bytes_sha256", "quote_volume"):
            self.assertNotIn(raw, out.getvalue())


if __name__ == "__main__":
    unittest.main()
