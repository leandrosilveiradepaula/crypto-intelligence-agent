"""Adversarial monthly OOS stress integration fixtures."""
from decimal import Decimal as D
import unittest
from test_vision_dynamic_replay import fixture
from test_vision_intrabar_stress import terms
from crypto_intelligence_agent.vision_stress_oos import audit_costed_vision_intrabar_oos
from crypto_intelligence_agent.market_data import DataValidationError

class VisionStressOOSTests(unittest.TestCase):
    def test_deterministic_frozen_months_privacy_and_gates(self):
        a,b=fixture("BTCUSDT"),fixture("ETHUSDT")
        end=a[-1].end_open_exclusive_ms+3600000
        def run(groups):
            return audit_costed_vision_intrabar_oos(groups,as_of_ms=end,
                        cost_bps_per_side=D("0"),assumptions=terms())
        first=run((a,b))
        self.assertEqual(first,run((b,a)))
        result=first.sanitized_report()
        self.assertFalse(result["financial_backtest_approved"])
        self.assertFalse(result["orders_sent"])
        self.assertNotIn("BTCUSDT",str(result))
        self.assertGreaterEqual(first.best_net_quote,first.worst_net_quote)
        self.assertLessEqual(first.liquidation_possible_count,first.stressed_count)
        self.assertLessEqual(first.ambiguous_count,first.stressed_count)

    def test_requires_explicit_and_valid_stress_terms(self):
        a,b=fixture("BTCUSDT"),fixture("ETHUSDT")
        end=a[-1].end_open_exclusive_ms+3600000
        with self.assertRaises(DataValidationError):
            audit_costed_vision_intrabar_oos((a,b),as_of_ms=end,
                         cost_bps_per_side=D("0"),assumptions=None)
        with self.assertRaises(DataValidationError):
            audit_costed_vision_intrabar_oos((a,a),as_of_ms=end,
                         cost_bps_per_side=D("0"),assumptions=terms())
