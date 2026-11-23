"""D465: live D464 1/50 WS failure must preserve safe LOCAL reason only."""
from __future__ import annotations
import unittest

from crypto_intelligence_agent.bybit_ws_supervisor import (
    _SAFE_REJECTION_CLASSES, _safe_ws_failure_class,
)
from crypto_intelligence_agent.market_data import DataGapError, DataValidationError


class D465PublicKlineFailureCategoryTests(unittest.TestCase):
    def test_exact_local_clock_and_kline_codes_survive_sanitization(self):
        for code in (
            "ws_kline_root_keys_invalid", "ws_kline_topic_invalid",
            "ws_kline_rows_overflow_invalid", "ws_clock_trade_stamp_invalid",
            "ws_clock_server_stale_invalid", "ws_clock_closed_before_local_end",
            "ws_clock_closed_too_old", "ws_ohlc_invalid",
        ):
            with self.subTest(code=code):
                self.assertIn(code, _SAFE_REJECTION_CLASSES)
                self.assertEqual(
                    _safe_ws_failure_class(DataValidationError(code)), code,
                )
    def test_raw_provider_and_unlisted_messages_are_never_logged(self):
        for reason in (
            "TOKEN_private_12345", "invalid 200.02 symbol ABCUSDT",
            "Unexpected provider request details \u2603",
        ):
            self.assertEqual(
                _safe_ws_failure_class(DataGapError(reason)),
                "invalid_or_gapped_market_data",
            )
            self.assertNotIn(reason, str(_safe_ws_failure_class(
                DataValidationError(reason),
            )))


if __name__=="__main__":
    unittest.main()
