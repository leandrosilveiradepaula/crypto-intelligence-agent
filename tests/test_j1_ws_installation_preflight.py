"""D268 private WS install survey: safety gates and read-only preparation."""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts.preflight_j1_ws_installation import (
    _validate_unit, _default, installation_preflight, main,
)
from scripts.render_j1_ws_service import render_j1_ws_unit

SHA = "f1d8d8ad2a093b1c7f5d65d0f67073811cd9c2e6"
PRIVATE = Path("/home/cia-probe/agent/ws-owner-private")


def systemd(*, installed=False):
    values = {
        "Id": "cia-j1-ws-owner.service",
        "LoadState": "loaded" if installed else "not-found",
        "ActiveState": "inactive",
        "SubState": "dead",
        "MainPID": "0",
        "User": "cia-probe" if installed else "",
        "UnitFileState": "disabled" if installed else "",
        "Result": "success",
    }
    return "".join(f"{k}={v}\n" for k, v in values.items())


class PortableTemplateTests(unittest.TestCase):
    def test_unit_rendering_includes_stop_on_denial_and_sandbox(self):
        rendered = render_j1_ws_unit(
            username="cia-probe", repo_root="/home/cia-probe/agent/repo",
            python_bin="/home/cia-probe/agent/ws-venv/bin/python",
            private_dir=str(PRIVATE),
        )
        _validate_unit(rendered,
                       repo=Path("/home/cia-probe/agent/repo"),
                       python=Path("/home/cia-probe/agent/ws-venv/bin/python"),
                       private_dir=PRIVATE)
        self.assertIn("RestartPreventExitStatus=64 65 66 77 130", rendered)
        self.assertIn("ProtectSystem=strict", rendered)
        self.assertIn("ReadWritePaths=/home/cia-probe/agent/ws-owner-private",
                      rendered)

    def test_modified_unit_no_sandbox_or_extra_command_fails(self):
        unit = render_j1_ws_unit(
            username="cia-probe", repo_root="/home/cia-probe/agent/repo",
            python_bin="/home/cia-probe/agent/ws-venv/bin/python",
            private_dir=str(PRIVATE))
        cases = (
            unit.replace("NoNewPrivileges=true", "NoNewPrivileges=false"),
            unit.replace("RestartPreventExitStatus=64 65 66 77 130",
                         "RestartPreventExitStatus="),
            unit + "\nExecStartPre=/bin/sh -c dangerous\n",
            unit.replace("User=cia-probe", "User=root"),
            unit.replace("Restart=always", "Restart=no"),
        )
        for modified in cases:
            with self.subTest(modified=modified[-45:]):
                with self.assertRaises(ValueError):
                    _validate_unit(
                        modified, repo=Path("/home/cia-probe/agent/repo"),
                        python=Path("/home/cia-probe/agent/ws-venv/bin/python"),
                        private_dir=PRIVATE)

    def test_default_is_never_deploy(self):
        report = _default()
        self.assertFalse(report["deployment_authorized"])
        self.assertFalse(report["service_activated"])
        self.assertFalse(report["continuous_collector_verified"])
        self.assertFalse(report["orders_sent"])
        self.assertTrue(report["scope_expiry_requires_separate_renewal"])

    def test_cli_default_does_not_touch_environment(self):
        stdout = StringIO()
        with patch("subprocess.run", side_effect=AssertionError("no calls")):
            with redirect_stdout(stdout):
                code = main(["--private-directory", str(PRIVATE),
                             "--expected-sha", SHA])
        self.assertEqual(code, 2)
        report = json.loads(stdout.getvalue())
        self.assertEqual(report["installation_blocker"], "owner_optin_required")
        self.assertEqual(report["network_requests"], 0)


@unittest.skipUnless(os.name == "posix", "owner-only POSIX test")
class PosixSurveyTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / "repo"
        self.repo.mkdir()
        self.python = Path(self.temp.name) / "python"
        self.python.write_text("mock interpreter\n", encoding="ascii")
        self.used = []

    def run_survey(self, *, installed=False, exists=False, sha=SHA,
                   clean=True, private=PRIVATE, allow=True):
        def service():
            self.used.append("service")
            return systemd(installed=installed)
        def git(_):
            self.used.append("git")
            return sha, clean
        def safe_dir(_path, *, owner_uid):
            self.used.append("dir")
            self.assertEqual(owner_uid, 12345)
            return "ready" if exists else "missing"
        with patch("scripts.preflight_j1_ws_installation._safe_dir",
                   side_effect=safe_dir):
            result = installation_preflight(
                private_directory=private, expected_sha=SHA,
                allow_readonly=allow, owner_ok=True, owner_uid=12345,
                repo=self.repo, python=self.python,
                service_reader=service, git_reader=git,
            )
        self.assertFalse(result["deployment_authorized"])
        self.assertFalse(result["service_activated"])
        self.assertFalse(result["network_requests"])
        self.assertFalse(result["orders_sent"])
        self.assertFalse(result["continuous_collector_verified"])
        self.assertNotIn(str(self.repo), json.dumps(result))
        self.assertNotIn(str(private), json.dumps(result))
        return result

    def test_missing_unit_and_private_dir_require_owner_gate(self):
        result = self.run_survey()
        self.assertEqual(result["status"], "read_only_installation_preflight")
        self.assertEqual(result["installation_blocker"],
                         "private_directory_requires_owner_provisioning")
        self.assertFalse(result["private_directory_ready"])
        self.assertFalse(result["service_present"])
        self.assertTrue(result["unit_template_valid"])

    def test_prepared_dir_still_cannot_authorize_deploy(self):
        result = self.run_survey(exists=True)
        self.assertEqual(result["installation_blocker"],
                         "separate_activation_gate_required")
        self.assertTrue(result["repo_clean_at_expected_sha"])
        self.assertTrue(result["private_directory_ready"])

    def test_existing_unit_stops_installation(self):
        result = self.run_survey(exists=True, installed=True)
        self.assertEqual(result["installation_blocker"],
                         "existing_service_requires_review")

    def test_wrong_sha_or_dirty_repo_never_passes(self):
        for sha, clean in (("f"*40, True), (SHA, False)):
            self.used.clear()
            result = self.run_survey(exists=True, sha=sha, clean=clean)
            self.assertEqual(result["installation_blocker"],
                             "repo_not_at_expected_sha")

    def test_invalid_paths_and_no_optin_make_no_service_calls(self):
        for path in (Path("/tmp/outside"), Path("../relative"),
                     Path("/home/cia-probe/agent/repo/private"),
                     Path("/home/cia-probe/agent/ws-venv/private"),
                     Path("/home/cia-probe/agent/ws-owner-private/run")):
            self.used.clear()
            result = self.run_survey(private=path)
            self.assertEqual(result["status"], "abstain")
            self.assertEqual(self.used, [])
        self.used.clear()
        result = self.run_survey(allow=False)
        self.assertEqual(result["status"], "abstain")
        self.assertEqual(self.used, [])

    def test_untrusted_systemd_response_abstains_without_unit_claim(self):
        result = installation_preflight(
            private_directory=PRIVATE, expected_sha=SHA, allow_readonly=True,
            owner_ok=True, owner_uid=12345, repo=self.repo, python=self.python,
            service_reader=lambda: "User=root\n",
            git_reader=lambda _: (SHA, True))
        self.assertEqual(result["status"], "abstain")
        self.assertFalse(result["deployment_authorized"])


if __name__ == "__main__":
    unittest.main()
