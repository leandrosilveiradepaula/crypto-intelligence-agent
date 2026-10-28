"""J1 #259: offline synthetic checksum sidecars and private audit regression."""
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

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.vision_checksum_sidecar import (
    parse_untrusted_local_vision_checksum,
)
from scripts.audit_offline_vision_series import (
    VisionLocalAuditError, audit_private_vision_archives, main,
)
from test_offline_vision_month import synthetic_zip

NAME = "BTCUSDT-1h-2024-01.zip"
DIGEST = "a" * 64


class LocalVisionSidecarParserTests(unittest.TestCase):
    def test_sha256sum_normal_binary_and_crlf(self):
        for separator in (b"  ", b" *"):
            for terminator in (b"", b"\n", b"\r\n"):
                raw = DIGEST.encode() + separator + NAME.encode() + terminator
                with self.subTest(separator=separator, terminator=terminator):
                    self.assertEqual(
                        parse_untrusted_local_vision_checksum(
                            raw, archive_name=NAME,
                        ), DIGEST,
                    )

    def test_bad_local_claims_fail_closed(self):
        valid = (DIGEST + "  " + NAME).encode()
        wrong = (
            b"", b"\xef\xbb\xbf" + valid, b"\\" + valid,
            valid + b"\n\n", valid + b"\n" + valid,
            valid + b"\x00", valid + b"\r", valid + b"\r" + valid,
            valid.replace(NAME.encode(), b"../" + NAME.encode()),
            valid.replace(NAME.encode(), b"OTHER-1h-2024-01.zip"),
            valid.replace(b"  ", b" \t"),
            valid.replace(b"a" * 64, b"A" * 64),
            valid.replace(b"a" * 64, b"1" * 63),
            valid + b"x" * 257,
        )
        for raw in wrong:
            with self.subTest(raw=raw[:18]), self.assertRaises(DataValidationError):
                parse_untrusted_local_vision_checksum(raw, archive_name=NAME)
        for invalid_name in ("../" + NAME, "BTCUSDT-1h-2024-13.zip", "BTCUSDC-1h-2024-01.zip", ""):
            with self.subTest(name=invalid_name), self.assertRaises(DataValidationError):
                parse_untrusted_local_vision_checksum(valid, archive_name=invalid_name)
        for bad_type in (None, "not bytes", bytearray(valid)):
            with self.subTest(type=type(bad_type).__name__), self.assertRaises(DataValidationError):
                parse_untrusted_local_vision_checksum(bad_type, archive_name=NAME)


@unittest.skipUnless(os.name == "posix", "private 0700/0600 contract requires POSIX")
class PrivateVisionChecksumAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.root.chmod(0o700)
        self.manifest_path = self.root / "manifest.json"
        self.entries = []
        self.zip_paths = []
        for year, month in ((2024, 1), (2024, 2)):
            raw, name, digest, as_of = synthetic_zip(
                year=year, month=month, compression=ZIP_STORED,
            )
            path = self.root / name
            path.write_bytes(raw)
            path.chmod(0o600)
            self.zip_paths.append(path)
            self.entries.append({"name": name, "sha256": digest})
            sidecar = self.root / (name + ".CHECKSUM")
            sidecar.write_bytes((digest + "  " + name + "\n").encode("ascii"))
            sidecar.chmod(0o600)
            self.as_of = as_of
        self.update_manifest()

    def update_manifest(self, entries=None):
        self.manifest_path.write_text(json.dumps({
            "schema_version": "vision-local-series-v1",
            "as_of_ms": self.as_of,
            "archives": self.entries if entries is None else entries,
        }), encoding="ascii")
        self.manifest_path.chmod(0o600)

    def run_audit(self, *, require=True):
        return audit_private_vision_archives(
            manifest_path=str(self.manifest_path),
            allow_personal_nonproduction_research=True,
            require_local_checksum_sidecars=require,
        )

    def test_two_months_and_legacy_mode_no_network_no_new_files(self):
        original = tuple(p.read_bytes() for p in self.zip_paths)
        before = sorted(p.name for p in self.root.iterdir())
        with patch("socket.create_connection", side_effect=AssertionError("network forbidden")):
            with patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")):
                first = self.run_audit()
                second = self.run_audit()
                legacy = self.run_audit(require=False)
        self.assertEqual(first, second)
        self.assertEqual(first["archive_count"], 2)
        self.assertEqual(first["closed_candle_count"], 744 + 696)
        self.assertEqual(first["untrusted_local_checksum_sidecars_matched"], 2)
        self.assertFalse(first["checksum_proves_provider_origin"])
        self.assertNotIn("untrusted_local_checksum_sidecars_matched", legacy)
        self.assertEqual(tuple(p.read_bytes() for p in self.zip_paths), original)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), before)
        for field in (
            "source_authenticated", "dataset_rights_authorized",
            "canonical_ohlcv_approved", "historical_top50_approved",
            "financial_backtest_approved", "live_trading_authorized", "orders_sent",
            "data_stored", "checksum_proves_provider_origin",
        ):
            self.assertIs(first[field], False)
        self.assertEqual(first["network_requests"], 0)

    def test_missing_invalid_tampered_and_wrong_archive_checksum(self):
        sidecar = self.root / (self.entries[0]["name"] + ".CHECKSUM")
        original = sidecar.read_bytes()
        examples = [
            b"", b"x", ("f" * 64 + "  " + self.entries[0]["name"]).encode(),
            (self.entries[0]["sha256"] + "  " + self.entries[1]["name"]).encode(),
            original + original, original + b"\n",
            original.replace(b"  ", b" *") + b"EXTRA",
        ]
        for raw in examples:
            with self.subTest(raw=raw[:12]):
                sidecar.write_bytes(raw)
                sidecar.chmod(0o600)
                with self.assertRaises(VisionLocalAuditError):
                    self.run_audit()
        sidecar.unlink()
        with self.assertRaises(VisionLocalAuditError):
            self.run_audit()
        sidecar.write_bytes(original)
        sidecar.chmod(0o600)
        self.assertEqual(self.run_audit()["untrusted_local_checksum_sidecars_matched"], 2)

    def test_sidecar_symlink_hardlink_and_permissions_rejected(self):
        sidecar = self.root / (self.entries[0]["name"] + ".CHECKSUM")
        original = sidecar.read_bytes()
        sidecar.chmod(0o644)
        with self.assertRaises(VisionLocalAuditError):
            self.run_audit()
        sidecar.unlink()
        sidecar.symlink_to(self.root / (self.entries[1]["name"] + ".CHECKSUM"))
        with self.assertRaises(VisionLocalAuditError):
            self.run_audit()
        sidecar.unlink()
        sidecar.write_bytes(original)
        sidecar.chmod(0o600)
        extra = self.root / "other-hardlink"
        os.link(sidecar, extra)
        with self.assertRaises(VisionLocalAuditError):
            self.run_audit()
        extra.unlink()
        self.assertEqual(self.run_audit()["untrusted_local_checksum_sidecars_matched"], 2)

    def test_manifest_mismatch_cannot_be_overridden_by_local_sidecar(self):
        different = [dict(self.entries[0], sha256="f" * 64), self.entries[1]]
        self.update_manifest(entries=different)
        with self.assertRaises(VisionLocalAuditError):
            self.run_audit()
        self.update_manifest()
        # Entire ZIP replaced, but sidecar and manifest remain unchanged.
        self.zip_paths[0].write_bytes(self.zip_paths[0].read_bytes() + b"tamper")
        with self.assertRaises(VisionLocalAuditError):
            self.run_audit()

    def test_cli_modes_sanitization_and_boolean_gate(self):
        out = StringIO()
        args = ["--manifest", str(self.manifest_path),
                "--require-local-checksum-sidecars"]
        with redirect_stdout(out):
            self.assertEqual(main(args), 1)
        self.assertEqual(json.loads(out.getvalue())["status"],
                         "private_vision_series_audit_rejected")
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(args + ["--allow-personal-nonproduction-research"]), 0)
        report = json.loads(output.getvalue())
        self.assertEqual(report["untrusted_local_checksum_sidecars_matched"], 2)
        for private in (str(self.root), self.entries[0]["name"], "BTCUSDT", "1250"):
            self.assertNotIn(private, output.getvalue())
        with self.assertRaises(VisionLocalAuditError):
            audit_private_vision_archives(
                manifest_path=str(self.manifest_path),
                allow_personal_nonproduction_research=True,
                require_local_checksum_sidecars="yes",
            )


if __name__ == "__main__":
    unittest.main()
