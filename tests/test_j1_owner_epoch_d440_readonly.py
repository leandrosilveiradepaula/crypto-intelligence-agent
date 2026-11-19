"""D440 diagnostic smoke tests: no provider network, J1 reads or writes."""
import unittest
from unittest.mock import patch

from scripts.diag_j1_owner_n50_d440_readonly import (
    MAX_AGE_MS, age_status, report,
)


class D440OwnerEpochDiagnosisTests(unittest.TestCase):
    def test_timestamp_boundary_and_invalid_types(self):
        now = 1_800_000_000_000
        self.assertEqual(age_status(now, now), "WITHIN_48H")
        self.assertEqual(age_status(now, now - MAX_AGE_MS), "WITHIN_48H")
        self.assertEqual(age_status(now, now - MAX_AGE_MS - 1), "EXPIRED_48H")
        self.assertEqual(age_status(now, now + 1), "FUTURE_TIMESTAMP")
        for value in ("1800000000000", None, True, 0, -1):
            with self.subTest(value=value):
                self.assertEqual(age_status(now, value), "INVALID_TIMESTAMP")

    def test_nonroot_gate_does_not_touch_private_path(self):
        with patch("scripts.diag_j1_owner_n50_d440_readonly.os.geteuid",
                   return_value=0):
            with patch("scripts.diag_j1_owner_n50_d440_readonly.secure_owner_file",
                       side_effect=AssertionError("unexpected owner state read")):
                got = report()
        self.assertEqual(got["POINTER"], "NONROOT_OWNER_REQUIRED")
        self.assertEqual(got["J1_MODIFIED"], "NO")
        self.assertEqual(got["ORDERS_SENT"], "NO")
        self.assertEqual(got["OWNER_DIAG"], "READ_ONLY_NO_NETWORK")

    def test_output_schema_never_exposes_market_data_or_paths(self):
        with patch("scripts.diag_j1_owner_n50_d440_readonly.os.geteuid",
                   return_value=0):
            got = report()
        self.assertEqual(set(got), {
            "OWNER_DIAG", "OWNER_REPO_HEAD", "DEPLOYED_EPOCH_MODULE",
            "POINTER", "MANIFEST", "METADATA_CACHE", "EPOCH_BINDING",
            "J1_MODIFIED", "ORDERS_SENT",
        })
