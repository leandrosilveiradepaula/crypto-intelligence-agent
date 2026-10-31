"""PRE26: adversarial OOS robustness research; deterministic/no real feeds."""
from dataclasses import replace
from decimal import Decimal as D
from unittest.mock import patch
import json
import unittest

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.vision_oos_robustness import (
    OOSRobustnessPolicy, audit_oos_robustness,
)
from crypto_intelligence_agent.vision_stress_sensitivity import (
    compare_costed_vision_oos_stress_scenarios,
)
from test_vision_dynamic_replay import fixture
from test_vision_intrabar_stress import terms


def policy(**kwargs):
    values = dict(
        min_test_folds=1, min_exposures_per_fold=1,
        max_liquidation_proxy_fraction=D("0"),
        max_intrabar_ambiguity_fraction=D("0"),
        max_single_bar_loss_over_margin=D("0.2"),
        max_worst_drawdown_quote=D("1"),
        require_nonnegative_adverse_fold=True,
    )
    values.update(kwargs)
    return OOSRobustnessPolicy(**values)


class OOSRobustnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a, cls.b = fixture("BTCUSDT"), fixture("ETHUSDT")
        cls.as_of = cls.a[-1].end_open_exclusive_ms + 3_600_000

    def grid(self, groups=None, costs="0"):
        return compare_costed_vision_oos_stress_scenarios(
            groups if groups is not None else (self.a, self.b),
            as_of_ms=self.as_of, cost_bps_per_side=D("0"),
            assumptions_grid=(terms(1, fee=costs), terms(50, fee=costs)))

    def test_flat_market_no_exposures_cannot_pass_even_under_lenient_limits(self):
        g = self.grid()
        p = policy(min_exposures_per_fold=1,
                   max_liquidation_proxy_fraction=D(1),
                   max_intrabar_ambiguity_fraction=D(1),
                   max_single_bar_loss_over_margin=D(1000),
                   max_worst_drawdown_quote=D("999999"))
        with patch("socket.create_connection", side_effect=AssertionError("network")), \
             patch("urllib.request.urlopen", side_effect=AssertionError("network")):
            r = audit_oos_robustness(g, policy=p)
        self.assertFalse(r.sanitized_report()["all_synthetic_conditions_met"])
        self.assertEqual(len(r.scenario_reports), 2)
        for case in r.scenario_reports:
            self.assertIn("insufficient_exposures_per_fold", case.rejection_codes)
            self.assertIn("no_oos_exposure", case.rejection_codes)
            self.assertEqual(case.exposure_count, 0)
        self.assertEqual(r, audit_oos_robustness(g, policy=p))
        self.assertFalse(r.sanitized_report()["financial_backtest_approved"])
        self.assertIsNone(r.sanitized_report()["recommended_leverage"])
        serialized = json.dumps(r.sanitized_report())
        for forbidden in ("BTCUSDT", "ETHUSDT", "sqlite", "/home/", "https://"):
            self.assertNotIn(forbidden, serialized)

    def test_actual_exposures_1x_and_50x_are_not_averaged_across_scenarios(self):
        # Prior CLOSE direction changes inside a coherent fabricated OHLC.
        def trending(group):
            n = 0
            result = []
            for month in group:
                candles = []
                for candle in month.candles:
                    candles.append(replace(
                        candle, close=D("101") + D(n) / D("1000"),
                        high=D("104"), low=D("99")))
                    n += 1
                result.append(replace(month, candles=tuple(candles)))
            return tuple(result)
        a,b = trending(self.a), trending(self.b)
        g = self.grid((a,b))
        self.assertGreater(g.scenarios[0].audit.stressed_count, 0)
        strict = audit_oos_robustness(g, policy=policy())
        self.assertFalse(strict.sanitized_report()["all_synthetic_conditions_met"])
        self.assertEqual(strict.scenario_reports[0].exposure_count,
                         strict.scenario_reports[1].exposure_count)
        # OHLC 99..104 does not touch the 50x liquidation proxy;
        # it does touch the stop and target and is intrabar ambiguous.
        self.assertIn("intrabar_ambiguity_fraction_exceeded",
                      strict.scenario_reports[1].rejection_codes)
        self.assertNotIn("liquidation_proxy_fraction_exceeded",
                         strict.scenario_reports[1].rejection_codes)
        # Controlled counterfactual evidence with an actual proxy count:
        # modify both fold and aggregate consistently so the risk auditor
        # must detect liquidation, not a broken reconciliation.
        cases = []
        for case in g.scenarios:
            folds = tuple(replace(
                f, strategy_liquidation_possible_count=f.strategy_exposures)
                for f in case.audit.fold_reports)
            cases.append(replace(case, audit=replace(
                case.audit, fold_reports=folds,
                liquidation_possible_count=case.audit.stressed_count)))
        forced_liq = audit_oos_robustness(
            replace(g, scenarios=tuple(cases)), policy=policy())
        self.assertIn("liquidation_proxy_fraction_exceeded",
                      forced_liq.scenario_reports[1].rejection_codes)
        relaxed = policy(
            max_liquidation_proxy_fraction=D(1),
            max_intrabar_ambiguity_fraction=D(1),
            max_single_bar_loss_over_margin=D(1000),
            max_worst_drawdown_quote=D("999999"),
            require_nonnegative_adverse_fold=False)
        good = audit_oos_robustness(g, policy=relaxed)
        self.assertTrue(good.sanitized_report()["all_synthetic_conditions_met"])
        self.assertEqual(good.scenario_reports[0].rejection_codes, ())
        self.assertEqual(good.scenario_reports[1].rejection_codes, ())
        higher_fee = self.grid((a,b), costs="10")
        costly = audit_oos_robustness(higher_fee, policy=policy(
            max_liquidation_proxy_fraction=D(1),
            max_intrabar_ambiguity_fraction=D(1),
            max_single_bar_loss_over_margin=D(1000),
            max_worst_drawdown_quote=D("999999"),
            require_nonnegative_adverse_fold=True))
        self.assertFalse(costly.sanitized_report()["all_synthetic_conditions_met"])
        self.assertIn("negative_adverse_fold", costly.scenario_reports[-1].rejection_codes)
        self.assertEqual(good, audit_oos_robustness(self.grid((b,a)),policy=relaxed))
        self.assertNotEqual(good.digest_sha256, strict.digest_sha256)

    def test_fail_closed_policy_types_counts_and_scenario_fingerprints(self):
        g = self.grid()
        for wrong in (
            dict(min_test_folds=True),
            dict(min_test_folds=0),
            dict(min_exposures_per_fold=0),
            dict(max_liquidation_proxy_fraction=D("NaN")),
            dict(max_liquidation_proxy_fraction=D("-0.1")),
            dict(max_intrabar_ambiguity_fraction=D("1.01")),
            dict(max_single_bar_loss_over_margin=0.1),
            dict(max_worst_drawdown_quote=D("Infinity")),
            dict(require_nonnegative_adverse_fold=1),
        ):
            with self.subTest(wrong=wrong), self.assertRaises(DataValidationError):
                policy(**wrong)
        with self.assertRaises(DataValidationError):
            audit_oos_robustness(g, policy=None)
        a,b=g.scenarios
        forged=replace(g,scenarios=(a,replace(b,audit=replace(
            b.audit,decision_fingerprint_sha256="0"*64))))
        with self.assertRaisesRegex(DataValidationError,"different decisions"):
            audit_oos_robustness(forged,policy=policy())
        badfold=replace(a.audit.fold_reports[0],strategy_exposures=1)
        tampered=replace(a,audit=replace(a.audit,fold_reports=(badfold,)))
        with self.assertRaises(DataValidationError):
            audit_oos_robustness(replace(g,scenarios=(tampered,b)),policy=policy())
        invalid_matched=replace(a.audit,matched_long=replace(
            a.audit.matched_long,exposures=1))
        with self.assertRaises(DataValidationError):
            audit_oos_robustness(replace(g,scenarios=(replace(a,audit=invalid_matched),b)),
                                 policy=policy())


if __name__=="__main__":
    unittest.main()
