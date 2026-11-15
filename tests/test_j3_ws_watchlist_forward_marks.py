"""J2/J3 #640: prospective-shaped but NOT prospectively attested WS mark outcomes."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import json
import socket
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.bybit_closed_stream_cache import HOUR_MS
from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.j2_n50_ws_descriptive_watchlist import (
    build_ws_descriptive_watchlist,
)
from crypto_intelligence_agent.j3_ws_watchlist_forward_marks import (
    ForwardCostAssumptions, freeze_ws_watchlist_reference,
    evaluate_ws_watchlist_forward_marks,
)
from crypto_intelligence_agent.synthetic_cost_scenarios import SyntheticFundingEvent
from test_j2_n50_ws_descriptive_watchlist import source_ws, END, NOW

SCOPE = "f"*64
JOURNAL = "e"*64
D = Decimal


def plan():
    return ForwardCostAssumptions(
        hypothetical_notional_quote_units=D("100"),
        entry_fee_bps=D("4"), exit_fee_bps=D("6"),
        entry_adverse_slippage_bps=D("2"),
        exit_adverse_slippage_bps=D("3"),
    )


def decision():
    ws = source_ws()
    snapshot = build_ws_descriptive_watchlist(
        ws, now_ms=NOW, include_private_symbols=True,
    )
    assert snapshot["status"] == "ws_descriptive_watchlist_ready", snapshot
    names = {
        row["symbol"] for side in ("up", "down")
        for row in snapshot[f"{side}_breakout_watchlist"]
    }
    prices = {name: "100" for name in names | {"BTCUSDT"}}
    frozen = freeze_ws_watchlist_reference(
        snapshot,
        registered_at_ms=NOW,
        ranked_scope_sha256=SCOPE,
        decision_closes=prices,
    )
    return snapshot, frozen


def future(frozen, *, up="101", down="99", btc="100.5"):
    closes = {c.symbol: (up if c.direction.value == "LONG" else down)
              for c in frozen.candidates}
    closes["BTCUSDT"] = btc
    return closes


def evaluate(frozen, horizon=1, *, now=None, marks=None, scope=SCOPE, costs=None,
             funding=None):
    end = frozen.decision_end_ms + HOUR_MS*horizon
    return evaluate_ws_watchlist_forward_marks(
        frozen, horizon_bars=horizon,
        observed_at_ms=end+240_000 if now is None else now,
        future_scope_sha256=scope,
        future_journal_digest_sha256=JOURNAL,
        future_closes=future(frozen) if marks is None else marks,
        costs=plan() if costs is None else costs,
        hypothetical_funding_events=funding,
    )


class FreezeDecisionTests(unittest.TestCase):
    def test_deterministic_private_shortlist_freezes_at_decision_not_future(self):
        source, a = decision()
        _, b = decision()
        self.assertEqual(a, b)
        self.assertEqual(a.registered_at_ms, NOW)
        self.assertEqual(a.decision_end_ms, END)
        self.assertTrue(a.candidates)
        self.assertLessEqual(len(a.candidates), 10)
        self.assertEqual(len(a.decision_commitment_sha256), 64)
        self.assertFalse(a.prospective_registration_verified)
        self.assertFalse(a.approved_for_signals)
        self.assertFalse(a.orders_sent)
        self.assertEqual(a.window_sha256, source["window_digest_sha256"])

    def test_refuse_unverified_and_unspecified_private_candidates(self):
        snapshot, ref = decision()
        changes = [
            ("schema_version", "unknown"),
            ("status", "not_ready"),
            ("audited_assets", 49),
            ("ws_journal_integrity_replayed", False),
            ("marketwide_top50_verified", True),
            ("formal_d323_24h_verified", True),
            ("orders_sent", True),
            ("approved_for_signals", True),
            ("window_digest_sha256", "BAD"),
            ("btc_context_available", False),
            ("observed_up_breakout_candidates", -1),
            ("observed_down_breakout_candidates", True),
            ("network_requests", 1),
        ]
        for key, value in changes:
            with self.subTest(key=key):
                tampered = dict(snapshot)
                tampered[key] = value
                with self.assertRaises(DataValidationError):
                    freeze_ws_watchlist_reference(
                        tampered, registered_at_ms=NOW,
                        ranked_scope_sha256=SCOPE,
                        decision_closes={c.symbol: "100" for c in ref.candidates}
                                        | {"BTCUSDT": "100"},
                    )
        for registration in (
            END+1, END+179_999, END+HOUR_MS,
            END+HOUR_MS-60_000, True, float(NOW),
        ):
            with self.subTest(registration=registration):
                with self.assertRaises(DataValidationError):
                    freeze_ws_watchlist_reference(
                        snapshot, registered_at_ms=registration,
                        ranked_scope_sha256=SCOPE,
                        decision_closes={c.symbol: "100" for c in ref.candidates}
                                        | {"BTCUSDT": "100"},
                    )

    def test_reject_unranked_ticker_or_btc_decision_mark_poisoning(self):
        snap, frozen = decision()
        ref_prices = {c.symbol: "100" for c in frozen.candidates}
        ref_prices["BTCUSDT"] = "100"
        problems = [
            {**ref_prices, "PRIVATEUSDT": "100"},
            {k:v for k,v in ref_prices.items() if k!="BTCUSDT"},
            {**ref_prices, "BTCUSDT": "0"},
            {**ref_prices, "BTCUSDT": "NaN"},
            {**ref_prices, "BTCUSDT": "1e309"},
        ]
        for prices in problems:
            with self.subTest(prices=prices):
                with self.assertRaises(DataValidationError):
                    freeze_ws_watchlist_reference(
                        snap, registered_at_ms=NOW,
                        ranked_scope_sha256=SCOPE,
                        decision_closes=prices,
                    )
        source = dict(snap)
        up = [dict(x) for x in snap["up_breakout_watchlist"]]
        self.assertGreater(len(up), 1)
        up[0], up[1] = up[1], up[0]
        source["up_breakout_watchlist"] = up
        with self.assertRaises(DataValidationError):
            freeze_ws_watchlist_reference(
                source, registered_at_ms=NOW,
                ranked_scope_sha256=SCOPE, decision_closes=ref_prices,
            )


class FutureMarksTests(unittest.TestCase):
    def test_ex_post_direction_and_assumed_j3_costs_without_lookahead(self):
        _, ref = decision()
        result = evaluate(ref, horizon=1)
        n = len(ref.candidates)
        self.assertEqual(result["status"],
                         "ex_post_reference_marks_scored_not_a_backtest")
        self.assertEqual(result["selected_observations"], n)
        self.assertEqual(result["matured_observations"], n)
        self.assertEqual(result["aligned_observations"], n)
        self.assertEqual(result["contrary_observations"], 0)
        self.assertEqual(result["unchanged_observations"], 0)
        self.assertGreater(D(result["gross_reference_bps_sum"]), 0)
        self.assertLess(D(result["net_reference_after_assumed_costs_bps_sum"]),
                        D(result["gross_reference_bps_sum"]))
        self.assertGreater(D(result["assumed_total_cost_quote_units"]), 0)
        self.assertEqual(result["funding_events_hypothetical"], 0)
        for field in (
            "prospective_registration_verified", "intrabar_path_verified",
            "venue_fees_verified", "funding_schedule_verified",
            "out_of_sample_results_validated", "financial_backtest_approved",
            "marketwide_top50_verified", "approved_for_signals",
            "live_trading_authorized", "orders_sent", "database_accessed",
            "systemd_modified",
        ):
            self.assertFalse(result[field])
        blob = json.dumps(result)
        self.assertNotIn("BTCUSDT", blob)
        self.assertNotIn("TST", blob)
        self.assertNotIn(SCOPE, blob)
        self.assertNotIn("101", blob)

    def test_only_matured_horizon_scored_and_no_fabricated_zero(self):
        _, ref = decision()
        for horizon in (1, 4, 8, 24):
            end = ref.decision_end_ms + horizon*HOUR_MS
            pending = evaluate(ref, horizon,
                               now=end+179_999)
            self.assertEqual(pending["status"],"awaiting_future_closed_hour")
            self.assertEqual(pending["matured_observations"],0)
            self.assertIsNone(pending["net_reference_after_assumed_costs_bps_sum"])
            ready = evaluate(ref, horizon, now=end+240_000)
            self.assertEqual(ready["matured_observations"],len(ref.candidates))
            stale = evaluate(ref, horizon,
                             now=end+HOUR_MS-60_000)
            self.assertEqual(stale["status"], "future_observation_stale_abstain")
            self.assertIsNone(stale["gross_reference_bps_sum"])

    def test_future_cohort_shift_or_missing_btc_abstains_without_counting_loss(self):
        _, ref = decision()
        for scope, marks, status in (
            ("0"*64, future(ref), "cohort_changed_forward_abstain"),
            (SCOPE, {"BTCUSDT":"101"}, "future_observations_unavailable"),
            (SCOPE, {}, "future_observations_unavailable"),
            (SCOPE, None, "ex_post_reference_marks_scored_not_a_backtest"),
        ):
            with self.subTest(status=status):
                result=evaluate(ref, scope=scope, marks=marks)
                self.assertEqual(result["status"], status)
                if status!="ex_post_reference_marks_scored_not_a_backtest":
                    self.assertEqual(result["matured_observations"],0)
                    self.assertIsNone(result["net_reference_after_assumed_costs_bps_sum"])
        for bad in ({"BTCUSDT":"0"}, {"BTCUSDT":"NaN"}):
            marks=future(ref)
            marks.update(bad)
            with self.assertRaises(DataValidationError):
                evaluate(ref, marks=marks)

    def test_reference_returns_shift_with_future_not_frozen_selection(self):
        _, ref = decision()
        changed = future(ref, up="95", down="106")
        baseline = evaluate(ref)
        adverse = evaluate(ref, marks=changed)
        self.assertEqual(ref, decision()[1])
        self.assertEqual(adverse["selected_observations"],
                         baseline["selected_observations"])
        self.assertEqual(adverse["aligned_observations"], 0)
        self.assertEqual(adverse["contrary_observations"], len(ref.candidates))
        self.assertLess(D(adverse["gross_reference_bps_sum"]), 0)
        self.assertEqual(adverse["financial_backtest_approved"], False)

    def test_uses_existing_j3_cost_engine_and_funding_signed_convention(self):
        _, ref = decision()
        first = ref.candidates[0]
        funding = SyntheticFundingEvent(
            event_id="fixture_funding_1h_A",
            event_at_ms=END+HOUR_MS//2,
            hypothetical_notional_quote_units=D("100"),
            signed_funding_rate_bps=D("2"),
        )
        funded=evaluate(ref,funding={first.symbol:(funding,)})
        neutral=evaluate(ref)
        self.assertEqual(funded["funding_events_hypothetical"], 1)
        self.assertNotEqual(funded["assumed_total_cost_quote_units"],
                            neutral["assumed_total_cost_quote_units"])
        more=ForwardCostAssumptions(
            D("100"),D("20"),D("20"),D("10"),D("10"),
        )
        expensive=evaluate(ref,costs=more)
        self.assertEqual(expensive["gross_reference_bps_sum"],
                         neutral["gross_reference_bps_sum"])
        self.assertLess(D(expensive["net_reference_after_assumed_costs_bps_sum"]),
                        D(neutral["net_reference_after_assumed_costs_bps_sum"]))
        with self.assertRaises(DataValidationError):
            evaluate(ref,funding={first.symbol:(funding,),
                                  "OTHERUSDT":(funding,)})
        if first.symbol != "BTCUSDT":
            with self.assertRaises(DataValidationError):
                evaluate(ref, funding={"BTCUSDT": (funding,)})

    def test_future_mark_grader_never_opens_database_network_or_order(self):
        _, ref = decision()
        with patch("sqlite3.connect", side_effect=AssertionError("db")), \
             patch("socket.create_connection",
                   side_effect=AssertionError("network")), \
             patch("urllib.request.urlopen", side_effect=AssertionError("http")):
            self.assertEqual(evaluate(ref)["matured_observations"],
                             len(ref.candidates))

    def test_reject_tampered_frozen_commitment_and_bad_horizon(self):
        _, ref = decision()
        with self.assertRaises(DataValidationError):
            evaluate(replace(ref, registered_at_ms=NOW+1))
        with self.assertRaises(DataValidationError):
            evaluate(replace(ref, window_sha256="0"*64))
        with self.assertRaises(DataValidationError):
            evaluate(replace(ref, decision_commitment_sha256="0"*64))
        for h in (0,2,9,25,True,1.0,"1"):
            with self.subTest(h=h), self.assertRaises(DataValidationError):
                evaluate(ref,horizon=h)


if __name__ == "__main__":
    unittest.main()
