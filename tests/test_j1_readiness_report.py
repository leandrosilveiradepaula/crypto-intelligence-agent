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
        self.assertFalse(data["ready_for_live_order_execution"])
        self.assertFalse(data["live_trading_authorized"])
        self.assertEqual(data["target_execution_mode"], "automated_entries_and_exits")
        self.assertEqual(data["current_execution_mode"], "offline_paper_not_deployed")
        self.assertEqual(data["schema_version"], "j1-readiness-v3")
        self.assertNotIn("manual_execution_candidates", data)
        by_name = {gate["capability"]: gate for gate in data["gates"]}
        self.assertEqual(len(by_name), len(data["gates"]))
        for cap in ("crypto_only_identity", "kraken_candle_volume_units",
                    "provider_external_rights", "binance_network_access"):
            self.assertEqual(by_name[cap]["status"], "blocked")
        self.assertEqual(by_name["historical_coverage"]["status"], "unknown")
        minimal = by_name["bybit_public_btcusdt_three_closed_1h_candles"]
        self.assertEqual(minimal["status"], "verified")
        self.assertEqual(minimal["issue"], 213)
        self.assertEqual(minimal["evidence_kind"], "owner_supplied_sanitized_ssh_output")
        self.assertIn("3 closed 1h", minimal["reason"])
        self.assertEqual(by_name["bybit_quote_currency"]["evidence_kind"],
                         "documented_schema_offline_only")
        # A proof of quote/settlement and KLINE volume cannot certify the
        # *ticker* fields, whose V5 REST schema omits an explicit unit.
        ticker = by_name["bybit_ticker_24h_units"]
        self.assertEqual(ticker["status"], "blocked")
        self.assertEqual(ticker["issue"], 196)
        self.assertEqual(ticker["evidence_kind"], "ticker_api_units_unattested")
        self.assertIn("ticker", ticker["reason"].lower())

    def test_no_authority_from_fixture_mutation(self):
        first = readiness_snapshot()
        first["ready_for_live_top50"] = True
        first["gates"][0]["status"] = "verified"
        again = readiness_snapshot()
        self.assertFalse(again["ready_for_live_top50"])
        self.assertEqual(again["gates"][0]["status"], "blocked")

    def test_execution_candidates_are_explicit_and_never_ready(self):
        report = readiness_snapshot()
        candidates = report["automated_execution_candidates"]
        self.assertEqual([row["venue"] for row in candidates],
                         ["binance_usdm", "bybit_v5"])
        self.assertEqual(candidates[0]["last_observed_access"], "http_451_restricted")
        self.assertEqual(candidates[1]["last_observed_access"],
                         "owner_vps_btcusdt_3_closed_1h_observed")
        for row in candidates:
            self.assertEqual(row["selection_status"], "candidate_not_selected")
            for flag in ("live_signal_approved", "automated_execution_approved",
                         "exchange_order_adapter_live_approved",
                         "order_execution_enabled"):
                self.assertFalse(row[flag])
        self.assertFalse(candidates[0]["account_access_verified"])
        self.assertTrue(candidates[1]["account_access_verified"])
        self.assertFalse(report["ready_for_live_top50"])
        bybit = candidates[1]
        self.assertEqual(
            bybit["ticker_units_evidence_scope"], "v5_rest_ticker_field_not_attested",
        )
        self.assertFalse(bybit["ticker_turnover_unit_verified"])
        self.assertFalse(bybit["ticker_volume_unit_verified"])
        self.assertFalse(report["ready_for_canonical_ohlcv"])
        self.assertFalse(report["ready_for_public_market_data_release"])

    def test_owner_auth_is_dated_not_market_data_or_trading_authorization(self):
        report = readiness_snapshot()
        binance, bybit = report["automated_execution_candidates"]
        self.assertEqual(binance["last_observed_access"], "http_451_restricted")
        self.assertEqual(bybit["last_observed_access"],
                         "owner_vps_btcusdt_3_closed_1h_observed")
        expected = (
            (binance, "access_or_region_restricted", False),
            (bybit, "authenticated_read_only_key_confirmed", True),
        )
        for candidate, status, attested in expected:
            with self.subTest(venue=candidate["venue"]):
                observed = candidate["private_api_auth_observation"]
                self.assertEqual(observed["status"], status)
                self.assertEqual(observed["observed_date_utc"], "2026-10-27")
                self.assertEqual(observed["evidence_kind"],
                                 "owner_supplied_sanitized_ssh_output")
                self.assertEqual(observed["evidence_issue"], 205)
                self.assertIs(observed["read_only_scope_attested_by_endpoint"],
                              attested)
                self.assertFalse(observed["current_access_rechecked"])
                self.assertFalse(candidate["live_signal_approved"])
                self.assertFalse(candidate["automated_execution_approved"])
                self.assertFalse(candidate["order_execution_enabled"])
        # Signed account authentication does NOT prove public candlesticks,
        # ticker units, historical Top50, rights, or permission to trade.
        self.assertFalse(report["ready_for_canonical_ohlcv"])
        self.assertFalse(report["ready_for_live_top50"])
        self.assertFalse(report["ready_for_public_market_data_release"])
        self.assertFalse(report["ready_for_live_order_execution"])

    def test_owner_auth_report_mutation_cannot_promote_gates(self):
        first = readiness_snapshot()
        first["automated_execution_candidates"][0]["private_api_auth_observation"][
            "status"] = "authenticated_read_only_key_confirmed"
        first["automated_execution_candidates"][1]["private_api_auth_observation"][
            "read_only_scope_attested_by_endpoint"] = False
        first["automated_execution_candidates"][1]["account_access_verified"] = False
        again = readiness_snapshot()
        self.assertEqual(again["automated_execution_candidates"][0][
            "private_api_auth_observation"]["status"],
                         "access_or_region_restricted")
        self.assertTrue(again["automated_execution_candidates"][1][
            "private_api_auth_observation"]["read_only_scope_attested_by_endpoint"])
        self.assertTrue(again["automated_execution_candidates"][1][
            "account_access_verified"])
        self.assertFalse(again["ready_for_live_order_execution"])

    def test_single_live_bybit_public_sample_does_not_certify_historical_feed(self):
        report = readiness_snapshot()
        binance, bybit = report["automated_execution_candidates"]
        self.assertEqual(binance["last_observed_access"], "http_451_restricted")
        previous = bybit["previous_github_actions_public_probe"]
        self.assertEqual(previous["status"],
                         "bybit_access_or_region_restricted_no_retry")
        self.assertEqual(previous["observed_closed_candles"], 0)
        self.assertEqual(previous["environment"],
                         "github_actions_runner_not_owner_vps")
        sample = bybit["public_market_research_observation"]
        self.assertEqual(sample["status"],
                         "private_real_bybit_base_btc_quote_usdt_observed")
        self.assertEqual(sample["observed_at_utc"],
                         "2026-10-27T13:07:29+00:00")
        self.assertEqual(sample["evidence_issue"], 213)
        self.assertEqual(sample["evidence_kind"],
                         "owner_supplied_sanitized_ssh_output")
        self.assertEqual(sample["symbol"], "BTCUSDT")
        self.assertEqual(sample["interval"], "1h")
        self.assertEqual(sample["requests_attempted"], 2)
        self.assertEqual(sample["validated_closed_candles"], 3)
        self.assertEqual(sample["documented_base_unit"], "BTC")
        self.assertEqual(sample["documented_turnover_quote_unit"],
                         "USDT_not_USD")
        self.assertEqual(sample["instrument_response_sha256"],
                         "cf3fbdc4bfe2f12c191cf122ca81f2e938c11111f7d6dbb9a075e16a7cf51651")
        self.assertEqual(sample["kline_response_sha256"],
                         "6e1727c293014f5aee5c596e90688ea6e6e091f21a9fbee0947862f75d7876d0")
        self.assertEqual(sample["registry_sha256"],
                         "a95179a342289833f3b14f0c2442163acdcb32f1ca0c9569fa01adeaa3534746")
        for flag in ("current_access_rechecked",
                     "raw_market_data_stored",
                     "provider_signed_provenance_verified",
                     "historical_top50_approved",
                     "canonical_ohlcv_approved",
                     "public_or_commercial_rights_authorized",
                     "ready_for_trading", "orders_sent", "credentials_used"):
            with self.subTest(flag=flag):
                self.assertFalse(sample[flag])
        for flag in ("ready_for_live_top50", "ready_for_canonical_ohlcv",
                     "ready_for_public_market_data_release",
                     "ready_for_live_order_execution", "live_trading_authorized"):
            self.assertFalse(report[flag])
        self.assertFalse(bybit["ticker_turnover_unit_verified"])
        self.assertFalse(bybit["ticker_volume_unit_verified"])
        self.assertFalse(bybit["order_execution_enabled"])

    def test_mutation_of_public_market_observation_cannot_change_gates(self):
        stale = readiness_snapshot()
        bybit = stale["automated_execution_candidates"][1]
        bybit["public_market_research_observation"]["validated_closed_candles"] = 50
        bybit["public_market_research_observation"]["historical_top50_approved"] = True
        bybit["previous_github_actions_public_probe"]["observed_closed_candles"] = 3
        stale["gates"][-2]["status"] = "blocked"
        again = readiness_snapshot()
        fresh_bybit = again["automated_execution_candidates"][1]
        self.assertEqual(fresh_bybit["public_market_research_observation"][
            "validated_closed_candles"], 3)
        self.assertFalse(fresh_bybit["public_market_research_observation"][
            "historical_top50_approved"])
        self.assertEqual(fresh_bybit["previous_github_actions_public_probe"][
            "observed_closed_candles"], 0)
        self.assertFalse(again["ready_for_live_top50"])
        self.assertFalse(again["ready_for_live_order_execution"])

    def test_mutated_candidate_cannot_change_future_gate(self):
        rows = readiness_snapshot()["automated_execution_candidates"]
        rows[0]["selection_status"] = "selected"
        rows[1]["order_execution_enabled"] = True
        again = readiness_snapshot()
        self.assertEqual(again["automated_execution_candidates"][0]["selection_status"],
                         "candidate_not_selected")
        self.assertFalse(again["automated_execution_candidates"][1]["order_execution_enabled"])
        self.assertFalse(again["ready_for_live_order_execution"])
        self.assertFalse(again["live_trading_authorized"])

    def test_ui_labels_or_candle_metadata_cannot_promote_ticker_units(self):
        """V5 KLINE BASE/QUOTE and venue UI labels are not REST ticker proof."""
        first = readiness_snapshot()
        injected = next(g for g in first["gates"]
                        if g["capability"] == "bybit_ticker_24h_units")
        injected["status"] = "verified"
        injected["reason"] = "some UI text says 24H Turnover(USDT)"
        first["automated_execution_candidates"][1][
            "ticker_turnover_unit_verified"
        ] = True
        first["automated_execution_candidates"][1][
            "ticker_volume_unit_verified"
        ] = True
        again = readiness_snapshot()
        gate = {r["capability"]: r for r in again["gates"]}[
            "bybit_ticker_24h_units"
        ]
        self.assertEqual(gate["status"], "blocked")
        self.assertEqual(gate["source"], "docs/J1_SOURCE_GATES.md")
        self.assertFalse(
            again["automated_execution_candidates"][1]["ticker_turnover_unit_verified"]
        )
        self.assertFalse(
            again["automated_execution_candidates"][1]["ticker_volume_unit_verified"]
        )
        self.assertFalse(again["ready_for_live_top50"])
        self.assertFalse(again["ready_for_live_order_execution"])

    def test_cli_stable_json(self):
        out = io.StringIO()
        with redirect_stdout(out):
            main()
        self.assertEqual(json.loads(out.getvalue()), readiness_snapshot())
        self.assertEqual(json.dumps(readiness_snapshot(), sort_keys=True),
                         json.dumps(readiness_snapshot(), sort_keys=True))


if __name__ == "__main__":
    unittest.main()
