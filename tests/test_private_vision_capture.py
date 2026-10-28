"""No-network J1 owner-only Vision acquisition and atomic private retention."""
from contextlib import redirect_stdout
from hashlib import sha256
from io import BytesIO, StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import os
import unittest

from scripts.capture_private_vision_months import (
    BASE, VisionCaptureError, capture_private_vision_months, main,
)
from scripts.audit_offline_vision_series import audit_private_vision_archives
from test_offline_vision_month import synthetic_zip


class FakeResponse:
    def __init__(self, url, body, code=200):
        self.url, self.body, self.code = url, body, code
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def getcode(self): return self.code
    def geturl(self): return self.url
    def read(self, n): return self.body[:n]


@unittest.skipUnless(os.name == "posix", "owner-only POSIX mode required")
class VisionPrivateCaptureTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "private"
        self.root.mkdir(mode=0o700)
        self.out = self.root / "capture"
        self.files = {}
        self.names = []
        self.cutoff = 0
        for year, month in ((2025, 1), (2025, 2)):
            blob, name, digest, cutoff = synthetic_zip(year=year, month=month)
            self.cutoff = cutoff
            self.names.append(name)
            self.files[BASE + name] = blob
            self.files[BASE + name + ".CHECKSUM"] = (
                digest + "  " + name + "\n"
            ).encode("ascii")
        self.attempts = []

    def opened(self, request, *, timeout):
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(timeout, 10)
        url = request.full_url
        self.attempts.append(url)
        return FakeResponse(url, self.files[url])

    def capture(self, **options):
        args = dict(
            names=tuple(self.names), output_dir=str(self.out),
            as_of_ms=self.cutoff, allow_public_network=True,
            allow_personal_nonproduction_license=True,
            allow_private_archive_retention=True,
            confirm_territory_and_access=True, opened=self.opened,
        )
        args.update(options)
        return capture_private_vision_months(**args)

    def test_four_downloads_private_files_and_existing_offline_auditor(self):
        with patch("socket.create_connection", side_effect=AssertionError("network")):
            result = self.capture()
            audit = audit_private_vision_archives(
                manifest_path=str(self.out / "manifest.json"),
                allow_personal_nonproduction_research=True,
                require_local_checksum_sidecars=True,
            )
        self.assertEqual(result["archive_count"], 2)
        self.assertEqual(result["network_requests"], 4)
        self.assertEqual(audit["archive_count"], 2)
        self.assertEqual(result["closed_candle_count"], 744 + 672)
        self.assertEqual(audit["closed_candle_count"], 744 + 672)
        self.assertEqual(len(self.attempts), 4)
        self.assertEqual(self.out.stat().st_mode & 0o777, 0o700)
        self.assertEqual(len(tuple(self.out.iterdir())), 5)
        self.assertTrue(all(f.stat().st_mode & 0o777 == 0o600
                            for f in self.out.iterdir()))
        for k in ("dataset_rights_authorized_for_live",
                  "canonical_ohlcv_approved", "historical_top50_approved",
                  "financial_backtest_approved", "ready_for_trading",
                  "live_trading_authorized", "orders_sent"):
            self.assertFalse(result[k])
        self.assertFalse(audit["dataset_rights_authorized"])

    def test_no_optins_means_no_requests_or_files(self):
        for key in ("allow_public_network", "allow_personal_nonproduction_license",
                    "allow_private_archive_retention", "confirm_territory_and_access"):
            with self.subTest(key=key), self.assertRaises(VisionCaptureError):
                self.capture(**{key: False})
        self.assertEqual(self.attempts, [])
        self.assertFalse(self.out.exists())

    def test_bad_checksum_or_corrupt_zip_no_retention(self):
        url = BASE + self.names[1] + ".CHECKSUM"
        saved = self.files[url]
        self.files[url] = b"0" * 64 + b"  " + self.names[1].encode("ascii") + b"\n"
        with self.assertRaises(VisionCaptureError):
            self.capture()
        self.assertFalse(self.out.exists())
        self.files[url] = saved
        self.files[BASE + self.names[1]] = b"bad"
        with self.assertRaises((VisionCaptureError, Exception)):
            self.capture()
        self.assertFalse(self.out.exists())

    def test_reject_duplicate_future_wrong_month_or_preexisting_dir(self):
        for names in ((self.names[0], self.names[0]),
                      tuple(reversed(self.names)),
                      ("BTCUSDT-1h-2025-01.zip", "../evil.zip")):
            with self.subTest(names=names), self.assertRaises(VisionCaptureError):
                self.capture(names=tuple(names))
        with self.assertRaises(Exception):
            self.capture(as_of_ms=self.cutoff - 1001)
        self.assertFalse(self.out.exists())
        self.out.mkdir()
        with self.assertRaises(VisionCaptureError):
            self.capture()
        self.assertEqual(len(tuple(self.out.iterdir())), 0)

    def test_error_after_staging_rolls_back_directory(self):
        with patch("scripts.capture_private_vision_months.os.fsync",
                   side_effect=OSError("disk error")):
            with self.assertRaises(VisionCaptureError):
                self.capture()
        self.assertFalse(self.out.exists())

    def test_cli_defaults_no_network_and_no_secret_output(self):
        args = ["--first-month", self.names[0], "--second-month", self.names[1],
                "--output-dir", str(self.out), "--as-of-ms", str(self.cutoff)]
        out = StringIO()
        with redirect_stdout(out):
            status = main(args)
        self.assertEqual(status, 1)
        self.assertEqual(json.loads(out.getvalue())["status"],
                         "private_vision_capture_rejected")
        self.assertNotIn(str(self.out), out.getvalue())
        self.assertNotIn("BTCUSDT", out.getvalue())
        self.assertEqual(self.attempts, [])
        self.assertFalse(self.out.exists())


if __name__ == "__main__":
    unittest.main()
