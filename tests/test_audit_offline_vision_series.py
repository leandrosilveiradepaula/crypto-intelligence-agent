"""J1/HIST #241: end-to-end synthetic ZIPs, no network, no market data."""
from __future__ import annotations

from contextlib import redirect_stdout
from hashlib import sha256
from io import StringIO
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zipfile import ZIP_STORED

from scripts.audit_offline_vision_series import (
    VisionLocalAuditError, audit_private_vision_archives, main,
)
from test_offline_vision_month import synthetic_zip


@unittest.skipUnless(os.name == "posix", "private POSIX 0700/0600 required")
class PrivateVisionSeriesAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.root.chmod(0o700)
        self.manifest_path = self.root / "manifest.json"
        self.entries = []
        for year, month in ((2024, 1), (2024, 2)):
            blob, name, digest, end = synthetic_zip(
                year=year, month=month, compression=ZIP_STORED,
            )
            self.assertLessEqual(len(blob), 8_000_000)
            path = self.root / name
            path.write_bytes(blob)
            path.chmod(0o600)
            self.entries.append({"name": name, "sha256": digest})
            self.end = end
        self.write_manifest()

    def write_manifest(self, **changes):
        data = {
            "schema_version": "vision-local-series-v1",
            "as_of_ms": self.end,
            "archives": self.entries,
        }
        data.update(changes)
        self.manifest_path.write_text(json.dumps(data), encoding="ascii")
        self.manifest_path.chmod(0o600)

    def run_audit(self):
        return audit_private_vision_archives(
            manifest_path=str(self.manifest_path),
            allow_personal_nonproduction_research=True,
        )

    def test_two_realistic_synthetic_zip_files_full_pipeline(self):
        with patch("socket.create_connection", side_effect=AssertionError("network")):
            with patch("urllib.request.urlopen", side_effect=AssertionError("network")):
                first, second = self.run_audit(), self.run_audit()
        self.assertEqual(first, second)
        self.assertEqual(first["archive_count"], 2)
        self.assertEqual(first["closed_candle_count"], 744 + 696)
        self.assertEqual(first["end_open_exclusive_ms"], self.end - 1000)
        self.assertEqual(first["network_requests"], 0)
        self.assertFalse(first["data_stored"])
        for gate in (
            "source_authenticated", "dataset_rights_authorized",
            "canonical_ohlcv_approved", "historical_top50_approved",
            "financial_backtest_approved", "ready_for_trading",
            "live_trading_authorized", "orders_sent",
        ):
            self.assertIs(first[gate], False)
        self.assertEqual(len(first["local_archive_identity_manifest_sha256"]), 64)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()),
                         sorted(["manifest.json"] + [e["name"] for e in self.entries]))

    def test_opt_in_and_manifest_fail_before_zip_reads(self):
        with self.assertRaises(VisionLocalAuditError):
            audit_private_vision_archives(manifest_path=str(self.manifest_path))
        for updates in (
            {"as_of_ms": True},
            {"archives": self.entries[:1]},
            {"archives": self.entries * 13},
            {"archives": list(reversed(self.entries))},
            {"archives": [self.entries[0]] * 2},
            {"archives": [dict(self.entries[0], name="../escape.zip"), self.entries[1]]},
            {"archives": [dict(self.entries[0], sha256="f" * 64), self.entries[1]]},
            {"archives": [dict(self.entries[0], sha256="F" * 64), self.entries[1]]},
            {"schema_version": "unknown"},
            {"as_of_ms": self.end - 1},
        ):
            self.write_manifest(**updates)
            with self.subTest(updates=str(updates)[:70]):
                with self.assertRaises(VisionLocalAuditError):
                    self.run_audit()

    def test_missing_zip_permissions_symlink_hardlink_and_damage(self):
        target = self.root / self.entries[0]["name"]
        original = target.read_bytes()
        for mode in ("missing", "public", "symlink", "hardlink", "tampered"):
            with self.subTest(mode=mode):
                target.unlink(missing_ok=True)
                if mode == "missing":
                    with self.assertRaises(VisionLocalAuditError):
                        self.run_audit()
                elif mode == "symlink":
                    target.symlink_to(self.root / self.entries[1]["name"])
                    with self.assertRaises(VisionLocalAuditError):
                        self.run_audit()
                else:
                    target.write_bytes(original + (b"x" if mode == "tampered" else b""))
                    target.chmod(0o600)
                    if mode == "public":
                        target.chmod(0o644)
                    if mode == "hardlink":
                        os.link(target, self.root / "extra-link")
                    with self.assertRaises(VisionLocalAuditError):
                        self.run_audit()
                    if mode == "hardlink":
                        (self.root / "extra-link").unlink()
        target.unlink(missing_ok=True)
        target.write_bytes(original)
        target.chmod(0o600)
        self.assertEqual(self.run_audit()["archive_count"], 2)

    def test_cli_never_emits_private_filename_paths_or_ohlc(self):
        out = StringIO()
        args = ["--manifest", str(self.manifest_path)]
        with redirect_stdout(out):
            self.assertEqual(main(args), 1)
        self.assertEqual(json.loads(out.getvalue())["status"],
                         "private_vision_series_audit_rejected")
        out = StringIO()
        with redirect_stdout(out):
            self.assertEqual(main(args + ["--allow-personal-nonproduction-research"]), 0)
        report = json.loads(out.getvalue())
        self.assertEqual(report["archive_count"], 2)
        for secret in (str(self.root), self.entries[0]["name"], "BTCUSDT", "1250"):
            self.assertNotIn(secret, out.getvalue())


if __name__ == "__main__":
    unittest.main()
