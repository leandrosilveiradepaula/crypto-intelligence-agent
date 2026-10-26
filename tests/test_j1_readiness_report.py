"""Offline regression tests for the conservative J1 checkpoint."""
import io
import json
import unittest
from contextlib import redirect_stdout

from scripts.j1_readiness_report import main, readiness_snapshot


class ReadinessSnapshotTests(unittest.TestCase):
    def test_gates_never_infer_live_readiness(self):
        data = readiness_snapshot()
        self.assertFalse(data["ready_for_live_top50"])
        self.assertFalse(data["ready_for_canonical_ohlcv"])
        self.assertFalse(data["ready_for_public_market_data_release"])
        by_name = {gate["capability"]: gate for gate in data["gates"]}
        self.assertEqual(len(by_name), len(data["gates"]))
        for cap in ("crypto_only_identity", "kraken_candle_volume_units",
                    "provider_external_rights", "binance_network_access"):
            self.assertEqual(by_name[cap]["status"], "blocked")
        self.assertEqual(by_name["historical_coverage"]["status"], "unknown")
        self.assertEqual(by_name["bybit_quote_currency"]["evidence_kind"],
                         "documented_schema_offline_only")

    def test_no_authority_from_fixture_mutation(self):
        first = readiness_snapshot()
        first["ready_for_live_top50"] = True
        first["gates"][0]["status"] = "verified"
        again = readiness_snapshot()
        self.assertFalse(again["ready_for_live_top50"])
        self.assertEqual(again["gates"][0]["status"], "blocked")

    def test_execution_candidates_are_explicit_and_never_ready(self):
        report = readiness_snapshot()
        candidates = report["manual_execution_candidates"]
        self.assertEqual([row["venue"] for row in candidates],
                         ["binance_usdm", "bybit_v5"])
        self.assertEqual(candidates[0]["last_observed_access"], "http_451_restricted")
        self.assertEqual(candidates[1]["last_observed_access"],
                         "first_instrument_get_restricted_no_candles")
        for row in candidates:
            self.assertEqual(row["selection_status"], "candidate_not_selected")
            for flag in ("account_access_verified", "live_signal_approved",
                         "manual_plan_approved", "order_execution_enabled"):
                self.assertFalse(row[flag])
        self.assertFalse(report["ready_for_live_top50"])
        self.assertFalse(report["ready_for_canonical_ohlcv"])
        self.assertFalse(report["ready_for_public_market_data_release"])

    def test_mutated_candidate_cannot_change_future_gate(self):
        rows = readiness_snapshot()["manual_execution_candidates"]
        rows[0]["selection_status"] = "selected"
        rows[1]["order_execution_enabled"] = True
        again = readiness_snapshot()
        self.assertEqual(again["manual_execution_candidates"][0]["selection_status"],
                         "candidate_not_selected")
        self.assertFalse(again["manual_execution_candidates"][1]["order_execution_enabled"])

    def test_cli_stable_json(self):
        out = io.StringIO()
        with redirect_stdout(out):
            main()
        self.assertEqual(json.loads(out.getvalue()), readiness_snapshot())
        self.assertEqual(json.dumps(readiness_snapshot(), sort_keys=True),
                         json.dumps(readiness_snapshot(), sort_keys=True))


if __name__ == "__main__":
    unittest.main()
