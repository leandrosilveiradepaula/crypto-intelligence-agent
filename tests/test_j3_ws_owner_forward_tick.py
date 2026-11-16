"""J3 #667: future-only owner score tick; no synthetic PnL on empty decisions."""
from __future__ import annotations

from decimal import Decimal
from io import StringIO
import json
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.bybit_closed_stream_cache import HOUR_MS
from crypto_intelligence_agent.j3_ws_watchlist_forward_marks import (
    ForwardCostAssumptions, _empty as scored_empty,
)
from crypto_intelligence_agent.j2_ws_owner_preflight import _report as pre_report
from scripts import run_j3_ws_owner_forward_tick_once as tick
from scripts import render_j3_ws_forward_score_timer_once as units


END = (1_800_000_000_000 // HOUR_MS) * HOUR_MS
NOW = END + 18*60_000
SHA = "a"*40
COSTS = ForwardCostAssumptions(
    hypothetical_notional_quote_units=Decimal("100"),
    entry_fee_bps=Decimal("4"), exit_fee_bps=Decimal("6"),
    entry_adverse_slippage_bps=Decimal("2"),
    exit_adverse_slippage_bps=Decimal("3"),
)


def preflight():
    p = pre_report("owner_preflight_ready_no_capture")
    p.update(
        owner_nonroot_posix_verified=True,
        owner_ledger_parent_dac_verified=True,
        os_ntp_sync_reported=True, capture_window_open=True,
        owner_ws_50x24_readonly_replayed=True, capture_eligible_now=True,
    )
    return p


def future_score(h: int, *, selected: int = 0):
    status = "no_observations_selected" if selected == 0 else (
        "ex_post_reference_marks_scored_not_a_backtest"
    )
    result = scored_empty(status, selected=selected, horizon_bars=h)
    result.update(
        owner_local_decision_file_verified=True,
        decision_closed_end_ms=END-h*HOUR_MS,
        future_closed_end_ms=END,
        owner_ws_sqlite_readonly_replayed=True,
        database_accessed=True,
        prospective_registration_independently_verified=False,
    )
    if selected:
        result.update(
            matured_observations=selected,
            aligned_observations=1, contrary_observations=selected-1,
            gross_reference_bps_sum="23.5",
            net_reference_after_assumed_costs_bps_sum="-0.75",
            same_side_btc_excess_reference_bps_sum="5.0",
            assumed_total_cost_quote_units="0.20",
        )
    return result


class ForwardProjection(unittest.TestCase):
    def test_zero_candidates_reconciled_as_no_pnl(self):
        r = tick._projection(future_score(1), horizon=1, future_end=END)
        self.assertEqual(r["status"], "no_observations_selected")
        self.assertIsNone(r["net_reference_after_assumed_costs_bps_sum"])
        for variant in (
            dict(future_score(1), gross_reference_bps_sum="1"),
            dict(future_score(1), orders_sent=True),
            dict(future_score(1), future_closed_end_ms=END+HOUR_MS),
            dict(future_score(1), prospective_registration_verified=True),
            dict(future_score(1), market_symbol="BTCUSDT"),
        ):
            with self.subTest(variant=variant):
                p = tick._projection(variant, horizon=1, future_end=END)
                self.assertEqual(p["status"], "abstained")
                self.assertNotIn("BTCUSDT", json.dumps(p))

    def test_aggregates_only_and_no_fabricated_positive(self):
        p = tick._projection(future_score(4, selected=2), horizon=4, future_end=END)
        self.assertEqual(p["status"], "reference_marks_scored_hypothetical_only")
        self.assertEqual(p["matured_observations"], 2)
        self.assertEqual(p["net_reference_after_assumed_costs_bps_sum"], "-0.75")
        for raw in (
            dict(future_score(4, selected=2), matured_observations=1),
            dict(future_score(4, selected=2), net_reference_after_assumed_costs_bps_sum="NaN"),
            dict(future_score(4, selected=2), decision_closed_end_ms=END-3*HOUR_MS),
            dict(future_score(4, selected=2), live_trading_authorized=True),
            dict(future_score(4, selected=2), private_symbol="BTCUSDT"),
        ):
            with self.subTest(raw=raw):
                self.assertEqual(tick._projection(raw, horizon=4, future_end=END)["status"],
                                 "abstained")


class ScoringOwnerTick(unittest.TestCase):
    def run_tick(self, *, now=NOW, pre=None, results=None, after=None):
        if pre is None:
            pre = preflight()
        if results is None:
            results = [future_score(h) for h in (1, 4, 8)]
        if after is None:
            after = [now]*4
        with patch.object(tick, "_owner_runtime", return_value=True), \
             patch.object(tick.time, "time_ns",
                          side_effect=[now*1_000_000]+[m*1_000_000 for m in after]), \
             patch.object(tick, "preflight_owner_ws_decision_once", return_value=pre) as probe, \
             patch.object(tick, "score_owner_ws_decision_once", side_effect=results) as score:
            outcome = tick.run_once(
                costs=COSTS, allow_private_readonly_research=True,
                allow_private_ledger_read=True, confirm_dedicated_owner_score_tick=True,
            )
        return outcome, probe, score

    def test_refuse_without_flags_before_owner(self):
        with patch.object(tick, "_owner_runtime", side_effect=AssertionError("owner")):
            self.assertEqual(tick.run_once(costs=COSTS)["status"],
                             "owner_score_tick_optins_required")

    def test_score_1_4_8_only_after_original_decisions(self):
        reports = [future_score(1), future_score(4, selected=2),
                   future_score(8)]
        outcome, probe, score = self.run_tick(results=reports)
        self.assertEqual(outcome["status"], "owner_score_tick_readonly_finished")
        self.assertEqual(outcome["evaluations_scored"], 1)
        self.assertEqual(outcome["empty_decisions_verified"], 2)
        self.assertEqual(outcome["horizons_abstained"], 0)
        self.assertEqual([x["horizon_hours"] for x in outcome["horizons"]], [1,4,8])
        self.assertFalse(outcome["orders_sent"])
        self.assertFalse(outcome["live_trading_authorized"])
        probe.assert_called_once_with(allow_private_readonly_research=True)
        self.assertEqual([x.kwargs["horizon_bars"] for x in score.call_args_list],
                         [1,4,8])
        self.assertTrue(all(x.kwargs["allow_private_ledger_read"]
                            for x in score.call_args_list))

    def test_missing_decisions_are_abstentions_not_returns(self):
        outcome, _, score = self.run_tick(results=[
            {"schema_version":"j2-ws-owner-ledger-status-v1",
             "status":"owner_score_abstain", "orders_sent":False,
             "live_trading_authorized":False,"database_mutation_statements":0},
            {"status":"untrusted_symbol_BTCUSDT"},
            future_score(8),
        ])
        self.assertEqual(outcome["horizons_abstained"], 2)
        self.assertEqual(outcome["empty_decisions_verified"], 1)
        self.assertEqual(outcome["evaluations_scored"], 0)
        self.assertNotIn("BTCUSDT", json.dumps(outcome))
        self.assertEqual(score.call_count,3)

    def test_closed_window_or_preflight_denies_before_scores(self):
        for now in (END+16*60_000, END+24*60_000):
            with self.subTest(now=now):
                outcome, _, score=self.run_tick(now=now)
                self.assertEqual(outcome["status"], "owner_score_tick_window_closed")
                score.assert_not_called()
        for bad in (
            dict(preflight(), capture_eligible_now=False),
            dict(preflight(), owner_ws_50x24_readonly_replayed=False),
            dict(preflight(), live_trading_authorized=True),
            dict(preflight(), database_mutation_statements=1),
        ):
            with self.subTest(pre=bad):
                outcome, _, score=self.run_tick(pre=bad)
                self.assertEqual(outcome["status"], "owner_score_tick_preflight_abstain")
                score.assert_not_called()

    def test_clock_jump_during_read_discards_all_rows(self):
        outcome, _, score = self.run_tick(after=[
            NOW, NOW, NOW+HOUR_MS, NOW,
        ])
        self.assertEqual(outcome["status"], "owner_score_tick_clock_shift_abstain")
        self.assertEqual(outcome["horizons"], [])
        self.assertEqual(score.call_count, 2)

    def test_owner_refusal_and_cost_validation(self):
        with patch.object(tick, "_owner_runtime", return_value=False), \
             patch.object(tick, "score_owner_ws_decision_once",
                          side_effect=AssertionError("must not score")):
            report=tick.run_once(
                costs=COSTS, allow_private_readonly_research=True,
                allow_private_ledger_read=True, confirm_dedicated_owner_score_tick=True,
            )
        self.assertEqual(report["status"], "owner_score_tick_nonroot_required")
        with patch.object(tick, "run_once", side_effect=AssertionError("no read")), \
             patch("sys.stdout", new_callable=StringIO) as output:
            self.assertEqual(tick.main([
                "--notional", "NaN", "--entry-fee-bps", "4",
                "--exit-fee-bps", "6", "--entry-slippage-bps", "2",
                "--exit-slippage-bps", "3",
            ]),65)
        self.assertEqual(json.loads(output.getvalue())["status"],
                         "owner_score_tick_costs_invalid")


class ReadonlySystemdCandidate(unittest.TestCase):
    def test_unit_has_no_write_permissions_and_no_persistence(self):
        s=units.service_unit(SHA)
        t=units.timer_unit()
        for field in (
            "User=cia-probe", "Group=cia-probe", "ProtectSystem=strict",
            "ProtectHome=read-only", "PrivateNetwork=yes",
            "NoNewPrivileges=yes", "Type=oneshot",
            "scripts.run_j3_ws_owner_forward_tick_once",
            "TimeoutStartSec=270", SHA[:12],
        ):
            with self.subTest(field=field):
                self.assertIn(field,s)
        self.assertNotIn("ReadWritePaths=",s)
        self.assertIn("OnCalendar=*-*-* *:17:00 UTC",t)
        self.assertIn("Persistent=false",t)
        for bad in ("a"*39, "A"*40, "main", "a"*40+";x"):
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                units.service_unit(bad)


if __name__ == "__main__":
    unittest.main()
