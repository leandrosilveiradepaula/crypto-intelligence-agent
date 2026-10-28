"""J1/PIT1: private coverage audit of existing only, no data downloads."""
from contextlib import redirect_stdout
from io import StringIO
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import os
import unittest

from scripts.audit_private_vision_multiasset import (
    VisionCoverageAuditError, audit_private_vision_multiasset_coverage, main,
)
from test_offline_vision_month import synthetic_zip


@unittest.skipUnless(os.name == "posix", "private POSIX 0700/0600 required")
class PrivateVisionCoverageTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.root.chmod(0o700)

    def make_series(self, symbol, months=((2026, 8), (2026, 9))):
        directory = self.root / ("fixture_" + symbol)
        directory.mkdir(mode=0o700)
        cutoff = None
        rows = []
        for year, month in months:
            blob, name, digest, cutoff = synthetic_zip(
                year=year, month=month, symbol=symbol,
            )
            payload = directory / name
            payload.write_bytes(blob)
            payload.chmod(0o600)
            sidecar = directory / (name + ".CHECKSUM")
            sidecar.write_bytes((digest + "  " + name + "\n").encode("ascii"))
            sidecar.chmod(0o600)
            rows.append({"name": name, "sha256": digest})
        manifest = directory / "manifest.json"
        manifest.write_text(json.dumps({
            "schema_version": "vision-local-series-v1",
            "as_of_ms": cutoff, "archives": rows,
        }), encoding="ascii")
        manifest.chmod(0o600)
        return str(manifest)

    def audit(self, *paths, allow=True):
        return audit_private_vision_multiasset_coverage(
            manifest_paths=tuple(paths),
            allow_personal_nonproduction_research=allow,
        )

    def test_real_checkpoint_shape_one_asset_is_not_top50(self):
        btc = self.make_series("BTCUSDT")
        with patch("socket.create_connection", side_effect=AssertionError("network")):
            x = self.audit(btc)
        self.assertEqual(x["status"], "private_research_coverage_audited")
        self.assertEqual(x["observed_symbol_count"], 1)
        self.assertEqual(x["archive_count"], 2)
        self.assertEqual(x["aligned_closed_1h_hours"], 1464)
        self.assertEqual(x["total_research_candle_rows"], 1464)
        self.assertFalse(x["has_two_or_more_local_assets"])
        self.assertEqual(x["network_requests"], 0)
        self.assertFalse(x["data_stored"])
        self.assertEqual(len(x["observed_sample_identity_sha256"]), 64)
        for gate in (
            "historical_top50_verified", "historical_listing_eligibility_verified",
            "usd_comparable_volume_verified", "source_authenticated",
            "dataset_rights_authorized_for_live", "canonical_ohlcv_approved",
            "financial_backtest_approved", "ready_for_trading",
            "live_trading_authorized", "orders_sent",
        ):
            self.assertFalse(x[gate])

    def test_two_assets_aligned_deterministic_no_stdout_market_data(self):
        btc, eth = self.make_series("BTCUSDT"), self.make_series("ETHUSDT")
        first, second = self.audit(btc, eth), self.audit(eth, btc)
        self.assertEqual(first, second)
        self.assertTrue(first["has_two_or_more_local_assets"])
        self.assertEqual(first["observed_symbol_count"], 2)
        self.assertEqual(first["archive_count"], 4)
        self.assertEqual(first["total_research_candle_rows"], 2928)
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main([
                "--manifest", btc, "--manifest", eth,
                "--allow-personal-nonproduction-research",
            ]), 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result, first)
        for secret in (btc, eth, "BTCUSDT", "ETHUSDT", "1250", str(self.root)):
            self.assertNotIn(secret, output.getvalue())
        self.assertEqual(sorted(p.name for p in Path(btc).parent.iterdir()),
                         sorted(["manifest.json", "BTCUSDT-1h-2026-08.zip",
                                 "BTCUSDT-1h-2026-09.zip",
                                 "BTCUSDT-1h-2026-08.zip.CHECKSUM",
                                 "BTCUSDT-1h-2026-09.zip.CHECKSUM"]))

    def test_missing_optin_duplicate_cross_root_and_mismatched_calendar(self):
        btc = self.make_series("BTCUSDT")
        eth = self.make_series("ETHUSDT", months=((2026, 7), (2026, 8)))
        with self.assertRaises(VisionCoverageAuditError):
            self.audit(btc, allow=False)
        with self.assertRaises(VisionCoverageAuditError):
            self.audit(btc, btc)
        with self.assertRaises(VisionCoverageAuditError):
            self.audit(btc, eth)
        with TemporaryDirectory() as td:
            other_root = Path(td)
            other_root.chmod(0o700)
            same = other_root / "manifest.json"
            same.write_text("{}", encoding="ascii")
            same.chmod(0o600)
            with self.assertRaises(VisionCoverageAuditError):
                self.audit(btc, str(same))
        with self.assertRaises(VisionCoverageAuditError):
            audit_private_vision_multiasset_coverage(
                manifest_paths=[btc], allow_personal_nonproduction_research=True,
            )

    def test_symlink_unsafe_permissions_checksum_and_json_rejected(self):
        btc = self.make_series("BTCUSDT")
        path = Path(btc)
        archive = path.parent / "BTCUSDT-1h-2026-08.zip.CHECKSUM"
        original = archive.read_bytes()
        archive.write_bytes(b"0"*64 + original[64:])
        with self.assertRaises(VisionCoverageAuditError):
            self.audit(btc)
        archive.write_bytes(original)
        archive.chmod(0o600)
        symlink = self.root / "fixture_symlink"
        symlink.symlink_to(path.parent, target_is_directory=True)
        with self.assertRaises(VisionCoverageAuditError):
            self.audit(str(symlink / "manifest.json"))
        symlink.unlink()
        path.parent.chmod(0o755)
        with self.assertRaises(VisionCoverageAuditError):
            self.audit(btc)
        path.parent.chmod(0o700)
        self.root.chmod(0o755)
        with self.assertRaises(VisionCoverageAuditError):
            self.audit(btc)
        self.root.chmod(0o700)
        original_manifest = path.read_text()
        path.write_text(original_manifest.replace(
            '"schema_version":', '"schema_version":"junk","schema_version":', 1,
        ))
        with self.assertRaises(VisionCoverageAuditError):
            self.audit(btc)
        path.write_text(original_manifest)
        path.chmod(0o600)
        self.assertEqual(self.audit(btc)["observed_symbol_count"], 1)

    def test_cli_fail_closed_no_network_no_private_text(self):
        btc = self.make_series("BTCUSDT")
        output = StringIO()
        with patch("socket.create_connection", side_effect=AssertionError("network")):
            with patch("urllib.request.urlopen", side_effect=AssertionError("network")):
                with redirect_stdout(output):
                    self.assertEqual(main(["--manifest", btc]), 1)
        result = json.loads(output.getvalue())
        self.assertEqual(result["status"], "private_vision_multiasset_audit_rejected")
        self.assertFalse(result["data_stored"])
        self.assertFalse(result["live_trading_authorized"])
        self.assertNotIn(str(self.root), output.getvalue())


if __name__ == "__main__":
    unittest.main()
