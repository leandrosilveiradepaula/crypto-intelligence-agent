"""D400: offline resource benchmark quality and fail-closed negative tests."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from unittest.mock import patch

from scripts.benchmark_public_n50_resources_d400 import run_benchmark


class OfflineResourceBenchmarkD400Tests(unittest.TestCase):
    def test_five_runs_measure_existing_two_epoch_fixture(self):
        result = run_benchmark(5)
        self.assertEqual(result["status"], "offline_synthetic_resource_sample")
        self.assertEqual(result["runs"], 5)
        self.assertEqual(result["epochs"], 10)
        self.assertEqual(result["ranked_per_epoch"], 50)
        self.assertEqual(result["ticker_frames_accepted"], 515)
        self.assertGreater(result["elapsed_wall_ms"], 0)
        self.assertGreaterEqual(result["process_cpu_ms"], 0)
        self.assertGreater(result["tracemalloc_peak_bytes"], 0)
        self.assertGreater(result["synthetic_frames_per_wall_second"], 0)
        self.assertFalse(result["includes_socket_and_os_rss"])
        for field in ("real_network_latency_or_load_verified",
                      "continuous_24x7_verified",
                      "marketwide_top50_verified", "orders_sent",
                      "order_submission_enabled", "approved_for_live_use"):
            self.assertIs(result[field], False)
        payload = json.dumps(result)
        for forbidden in ("A00USDT", "HOLDUSDT", "100.1", "99.9"):
            self.assertNotIn(forbidden, payload)

    def test_invalid_counts_rejected_before_fixture(self):
        for bad in (True, 0, -1, 21, 1.2, "5", None):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    run_benchmark(bad)

    def test_missing_coverage_is_error_not_benchmark_success(self):
        with patch("scripts.benchmark_public_n50_resources_d400.run_demo",
                   return_value={
                       "schema_version": "bybit-public-n50-coverage-pilot-d396-v1",
                       "status": "abstained_incomplete_coverage",
                       "all_observed_coverage": False,
                       "attempted_epochs": 1,
                       "continuous_24x7_verified": False,
                       "orders_sent": False,
                   }):
            with self.assertRaises(RuntimeError):
                run_benchmark(1)

    def test_cli_emits_only_count_and_resource_summary(self):
        proc = subprocess.run([
            sys.executable, "-m", "scripts.benchmark_public_n50_resources_d400",
            "--runs", "1",
        ], capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["ticker_frames_accepted"], 103)
        self.assertFalse(result["real_network_latency_or_load_verified"])


if __name__ == "__main__":
    unittest.main()
