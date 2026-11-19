"""D439 host operator: syntax and no-capability fail-closed; no network in CI."""
from pathlib import Path
import os
import shutil
import socket
import subprocess
import unittest


SCRIPT = (Path(__file__).resolve().parents[1]
          / "deploy" / "vps" / "j2_public_kline_owner_d439_once.sh")


@unittest.skipUnless(os.name == "posix" and shutil.which("bash"), "POSIX host Bash only")
class D439OwnerOperatorTests(unittest.TestCase):
    def test_script_parses_as_shell(self):
        result = subprocess.run(
            ["bash", "-n", str(SCRIPT)], capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_unsupported_host_or_user_cannot_start_network(self):
        if os.name == "posix" and os.geteuid() == 0 and socket.gethostname() == "srv1319424":
            self.skipTest("actual approved root host must never execute in CI")
        result = subprocess.run(
            ["bash", str(SCRIPT), "--capture", "a" * 40],
            capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(result.returncode, 77, result.stderr)
        self.assertTrue(result.stdout.startswith("D439_BLOCKED="))
        self.assertNotIn("D439_PUBLIC_REST_AND_WS=ATTEMPTING", result.stdout)
        self.assertNotIn("D439_PUBLIC_RESULT=public_", result.stdout)

    def test_invalid_mode_or_sha_rejected_without_host_access(self):
        for mode, sha in (("--unsafe", "a" * 40), ("--capture", "invalid")):
            with self.subTest(mode=mode, sha=sha):
                result = subprocess.run(
                    ["bash", str(SCRIPT), mode, sha],
                    capture_output=True, text=True, timeout=15,
                )
                self.assertEqual(result.returncode, 77)
                self.assertIn("D439_BLOCKED=", result.stdout)
                self.assertNotIn("D439_PUBLIC_REST_AND_WS=ATTEMPTING", result.stdout)
