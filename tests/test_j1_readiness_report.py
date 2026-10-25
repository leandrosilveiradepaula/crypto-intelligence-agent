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

    def test_cli_stable_json(self):
        out = io.StringIO()
        with redirect_stdout(out):
            main()
        self.assertEqual(json.loads(out.getvalue()), readiness_snapshot())
        self.assertEqual(json.dumps(readiness_snapshot(), sort_keys=True),
                         json.dumps(readiness_snapshot(), sort_keys=True))


if __name__ == "__main__":
    unittest.main()
