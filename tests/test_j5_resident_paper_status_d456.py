"""D456: loopback status is validated, local only, stale-safe, not proof of stops."""
from __future__ import annotations
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.j5_resident_paper_status_d456 import (
    ResidentPaperStatusUnavailable, read_resident_paper_status,
)
from scripts import serve_j5_local_readonly as panel

NOW=1_800_000_000_000
def report(**kwargs):
    value={
      "schema_version":"d453-resident-paper-status-v1",
      "state":"observing_public_lease",
      "updated_at_ms":NOW-3000,
      "stale_after_ms":NOW+120000,
      "cycles_attempted":3,
      "primary_leases_completed":2,
      "held_only_fallbacks":0,
      "last_cycle":3,
      "last_failure_class":None,
      "mode":"public_research_unverified",
      "native_protective_orders":False,
      "position_monitoring_guaranteed":False,
      "real_orders_sent":False,
    }
    value.update(kwargs)
    return value


@unittest.skipUnless(os.name=="posix" and hasattr(os,"geteuid") and os.geteuid()!=0,
                     "owner-only POSIX private state")
class D456StatusTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory(prefix="cia-d456-")
        self.addCleanup(t.cleanup)
        self.home=Path(t.name)
        self.home.chmod(0o700)
        self.file=self.home/"paper-operator-state-d453.json"
        self.write(report())
    def write(self,value):
        self.file.write_text(json.dumps(value,sort_keys=True),encoding="ascii")
        self.file.chmod(0o600)
    def test_read_real_private_status_with_no_native_stop_claim(self):
        result=read_resident_paper_status(directory=self.home,now_ms=NOW)
        self.assertEqual(result["cycle_attempts"],3)
        self.assertEqual(result["primary_leases_completed"],2)
        self.assertFalse(result["native_stop_verified"])
        self.assertFalse(result["lease_now_guaranteed_active"])
        self.assertFalse(result["uninterrupted_market_coverage_verified"])
        self.assertFalse(result["real_orders_sent"])
        self.assertEqual(result["status"],"observing_public_lease")
    def test_stale_tamper_permissions_symlink_future_and_modes_fail_closed(self):
        for mutation in (
          report(stale_after_ms=NOW-1),report(updated_at_ms=NOW+6000),
          report(position_monitoring_guaranteed=True),
          report(native_protective_orders=True),
          report(real_orders_sent=True),
          report(state="arbitrary"),
          report(cycles_attempted=1,primary_leases_completed=2),
          report(mode="authenticated_private_bybit"),
          report(last_failure_class="secret"),
          report(stale_after_ms=NOW+500000),
        ):
            self.write(mutation)
            with self.subTest(mutation=mutation),self.assertRaises(ResidentPaperStatusUnavailable):
                read_resident_paper_status(directory=self.home,now_ms=NOW)
        self.write(report())
        self.file.chmod(0o644)
        with self.assertRaises(ResidentPaperStatusUnavailable):
            read_resident_paper_status(directory=self.home,now_ms=NOW)
        self.file.chmod(0o600)
        self.file.unlink()
        external=self.home/"external.json"
        external.write_text(json.dumps(report()))
        external.chmod(0o600)
        self.file.symlink_to(external)
        with self.assertRaises(ResidentPaperStatusUnavailable):
            read_resident_paper_status(directory=self.home,now_ms=NOW)
    def test_duplicate_json_key_fails_closed(self):
        self.file.write_text('{"schema_version":"d453-resident-paper-status-v1","schema_version":"bad"}')
        self.file.chmod(0o600)
        with self.assertRaises(ResidentPaperStatusUnavailable):
            read_resident_paper_status(directory=self.home,now_ms=NOW)


class D456LoopbackContractTests(unittest.TestCase):
    def test_status_route_defaults_disabled_and_owned_optin(self):
        script=Path(panel.__file__).read_text()
        self.assertIn('self.path == "/api/resident-paper-status"',script)
        self.assertIn('resident_paper_directory: Path | None = None',script)
        self.assertIn('--allow-resident-paper-status-loopback',script)
        self.assertIn('read_resident_paper_status(',script)
        self.assertIn('max_bytes=4096',script)
        self.assertIn('"resident_paper_status_nonroot_required"',script)


if __name__=="__main__":
    unittest.main()
