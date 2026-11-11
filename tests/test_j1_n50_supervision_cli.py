"""Read-only CLI preflight: denies opt-in, path errors, corrupted audit and leaks."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch
import unittest

from scripts.plan_j1_n50_supervision_once import inspect_n50_epoch_once
from tests.test_j1_n50_supervision import T, HOUR_MS, scope, audit

MANIFEST = Path("/private/n50/scope")
JOURNAL = Path("/private/n50/output")


class N50SupervisionCliTests(unittest.TestCase):
    def run_once(self, **override):
        opts=dict(
            manifest_directory=MANIFEST, output_directory=JOURNAL,
            now_ms=T+HOUR_MS+120_000,owner_ok=True,
            allow_private_manifest_read=True,
            allow_private_readonly_audit=True,
        )
        opts.update(override)
        return inspect_n50_epoch_once(**opts)

    def test_full_readonly_path_validates_and_never_issues_network(self):
        with patch("scripts.plan_j1_n50_supervision_once.load_private_ranked_scope",
                   return_value=scope()) as load, \
                patch("scripts.plan_j1_n50_supervision_once.audit_existing_rest_resume",
                      return_value=audit()) as owner_audit, \
                patch("urllib.request.urlopen", side_effect=AssertionError("GET")), \
                patch("sqlite3.connect", side_effect=AssertionError("direct DB")), \
                patch("subprocess.run",side_effect=AssertionError("systemd")):
            out=self.run_once()
        self.assertEqual(out["action"],"run_existing_epoch_once")
        self.assertEqual(out["status"],"needs_external_gate")
        self.assertEqual(load.call_count,1)
        self.assertEqual(owner_audit.call_args.kwargs["expected_members"],50)
        self.assertFalse(out["orders_sent"])
        self.assertEqual(out["network_requests"],0)
        self.assertNotIn("USDT",str(out))

    def test_no_optin_owner_or_malicious_paths_does_not_read(self):
        with patch("scripts.plan_j1_n50_supervision_once.load_private_ranked_scope",
                   side_effect=AssertionError("private read")), \
                patch("scripts.plan_j1_n50_supervision_once.audit_existing_rest_resume",
                      side_effect=AssertionError("sqlite read")):
            for opts in (
                {"allow_private_manifest_read":False},
                {"allow_private_readonly_audit":False},
                {"owner_ok":False},
                {"manifest_directory":JOURNAL},
                {"output_directory":Path("relative/path")},
                {"manifest_directory":Path("/private")},
            ):
                with self.subTest(opts=opts):
                    out=self.run_once(**opts)
                    self.assertEqual(out["status"],"blocked")
                    self.assertEqual(out["network_requests"],0)

    def test_bad_readiness_never_relabels_bootstrap(self):
        with patch("scripts.plan_j1_n50_supervision_once.load_private_ranked_scope",
                   return_value=scope()), \
                patch("scripts.plan_j1_n50_supervision_once.audit_existing_rest_resume",
                      return_value={"status":"journal_unavailable_or_integrity_blocked"}):
            out=self.run_once()
        self.assertEqual(out["status"],"blocked")
        self.assertNotEqual(out["action"],"bootstrap_new_empty_epoch")


if __name__=="__main__":
    unittest.main()
