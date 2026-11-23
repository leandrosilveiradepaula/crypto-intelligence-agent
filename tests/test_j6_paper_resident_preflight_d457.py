"""D457 operator preflight and deployment candidate may never turn into orders."""
from __future__ import annotations
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from scripts.preflight_j2_j4_paper_resident_d457 import preflight
from crypto_intelligence_agent.market_data import DataValidationError

ROOT=Path(__file__).resolve().parents[1]


class PaperResidentD457PackagingTests(unittest.TestCase):
    def test_systemd_candidate_is_nonroot_and_not_installed(self):
        path=ROOT/"deploy/systemd/cia-j2-j4-public-paper-resident.service.template"
        content=path.read_text()
        self.assertIn("User=cia-probe",content)
        self.assertIn("NoNewPrivileges=true",content)
        self.assertIn("ProtectSystem=strict",content)
        self.assertIn("ExecStartPre=@PYTHON@ -m scripts.preflight_j2_j4_paper_resident_d457",content)
        self.assertIn("Restart=on-failure",content)
        self.assertIn("MemoryMax=",content)
        self.assertIn("ReadWritePaths=@J2_DIR@ @PAPER_DIR@",content)
        self.assertNotIn("api_key",content.lower())
        self.assertNotIn("api_secret",content.lower())
        self.assertNotIn("ExecStart=/usr/bin/bybit",content)
        self.assertNotIn("Environment=LIVE_TRADING",content)
    @unittest.skipUnless(os.name=="posix" and hasattr(os,"geteuid")
                         and os.geteuid()!=0,"owner-only preflight")
    def test_no_mutations_when_paths_missing_and_wrong_permissions(self):
        with tempfile.TemporaryDirectory(prefix="cia-d457-test-") as tmp:
            root=Path(tmp);root.chmod(0o700)
            paper=root/"paper";paper.mkdir(mode=0o700)
            j2=root/"j2"
            policy=root/"sample.json"
            before=set(root.iterdir())
            report=preflight(j2_directory=j2,paper_directory=paper,policy_file=policy)
            self.assertEqual(report["status"],"blocked_fail_closed")
            self.assertFalse(report["checks"]["j2_private_owner_directory"])
            self.assertFalse(report["checks"]["policy_owner_only_and_valid"])
            self.assertEqual(before,set(root.iterdir()))
            self.assertFalse(report["network_attempted"])
            self.assertFalse(report["filesystem_changed"])
            self.assertFalse(report["real_orders_sent"])
            self.assertFalse(report["production_install_authorized"])
            j2.mkdir(mode=0o700)
            paper.chmod(0o755)
            report=preflight(j2_directory=j2,paper_directory=paper,policy_file=policy)
            self.assertFalse(report["checks"]["paper_private_owner_directory"])
            self.assertFalse(report["checks"]["policy_owner_only_and_valid"])
    @unittest.skipUnless(os.name=="posix" and hasattr(os,"geteuid")
                         and os.geteuid()!=0,"owner-only preflight")
    def test_reject_same_directories_and_j1_reuse(self):
        with tempfile.TemporaryDirectory(prefix="cia-d457-test-") as tmp:
            root=Path(tmp);root.chmod(0o700)
            result=preflight(j2_directory=root,paper_directory=root,
                             policy_file=root/"p.json")
            self.assertFalse(result["checks"]["directories_separate"])
            j1=root/"j1-existing";j1.mkdir(mode=0o700)
            result=preflight(j2_directory=j1,paper_directory=root,
                             policy_file=root/"p.json")
            self.assertFalse(result["checks"]["directories_separate"])

if __name__=="__main__":
    unittest.main()
