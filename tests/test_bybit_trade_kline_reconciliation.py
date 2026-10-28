"""J1 #256: reference and trade observations are 100% synthetic."""
from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, timezone
from decimal import Decimal
import gzip
import unittest

from crypto_intelligence_agent.bybit_linear_candle_research import stage_bybit_linear_kline
from crypto_intelligence_agent.bybit_trade_hourly_research import reconstruct_weekly_trade_hours
from crypto_intelligence_agent.bybit_trade_kline_reconciliation import (
    reconcile_weekly_trades_with_v5_kline,
)
from crypto_intelligence_agent.bybit_public_trade_archive import FIELDS
from crypto_intelligence_agent.market_data import DataValidationError
from test_bybit_archive_week import samples

HOUR = 3_600_000
START = int(datetime(2020, 4, 5, tzinfo=timezone.utc).timestamp() * 1000)
END = START + 168 * HOUR


def reference_page(*, changed_hour=None, changed_high="9001"):
    rows = []
    for i in reversed(range(168)):
        start = START + i * HOUR
        high = changed_high if changed_hour == i else "9000.5"
        rows.append([str(start), "9000.5", high, "9000.5", "9000.5", "0", "0"])
    return stage_bybit_linear_kline(
        {"retCode": 0, "result": {"category": "linear", "symbol": "BTCUSDT",
                                   "list": rows}},
        symbol="BTCUSDT", quote_currency="USDT",
        contract_type="LinearPerpetual", contract_status="Trading",
        contract_observed_at_ms=START, observed_at_ms=END + 1000,
        max_contract_age_ms=END - START + 1000, interval="1h",
        start_open_ms=START, end_open_ms=END, max_candles=168,
    )


def archive_with_first_day_rows(rows):
    week = samples(date(2020, 4, 5))
    body = ",".join(FIELDS) + "\n" + "\n".join(rows) + "\n"
    return ((week[0][0], gzip.compress(body.encode("ascii"), mtime=0)),
            *week[1:])


def trade_row(ts, price, size="1.25", home="1.25", foreign="11250.625"):
    return ",".join((
        str(ts), "BTCUSDT", "Buy", size, price,
        "PlusTick", "synthetic-trade-id", "100000000",
        home, foreign,
    ))


class BybitTradeReferenceReconciliationTests(unittest.TestCase):
    def test_exact_comparison_only_for_observed_hours_without_leak(self):
        week = reconstruct_weekly_trade_hours(samples(date(2020, 4, 5)))
        receipt = reconcile_weekly_trades_with_v5_kline(week, reference_page())
        self.assertEqual(receipt.reference_hours, 168)
        self.assertEqual(receipt.hours_with_trades_observed, 7)
        self.assertEqual(receipt.hours_without_trades_observed, 161)
        self.assertEqual(receipt.fully_comparable_ohlc_hours, 7)
        self.assertEqual(receipt.fully_equal_ohlc_hours, 7)
        self.assertEqual(receipt.divergent_ohlc_hours, 0)
        self.assertEqual(receipt.high_compared, 7)
        self.assertEqual(receipt.open_compared, 7)
        self.assertEqual(receipt.quote_volume_compared, 0)
        for gate in (
            "volume_units_verified", "source_authenticated",
            "rights_authorized", "canonical_ohlcv_approved",
            "historical_top50_approved", "financial_backtest_approved",
            "live_trading_authorized", "orders_sent",
        ):
            self.assertFalse(getattr(receipt, gate))
        self.assertNotIn("9000.5", str(receipt))
        with self.assertRaises(FrozenInstanceError):
            receipt.high_divergent = 12

    def test_price_differences_are_counts_not_market_values(self):
        week = reconstruct_weekly_trade_hours(samples(date(2020, 4, 5)))
        result = reconcile_weekly_trades_with_v5_kline(
            week, reference_page(changed_hour=0))
        self.assertEqual(result.high_divergent, 1)
        self.assertEqual(result.divergent_ohlc_hours, 1)
        self.assertEqual(result.fully_equal_ohlc_hours, 6)
        self.assertEqual(result.open_divergent, 0)
        self.assertEqual(result.close_divergent, 0)

    def test_ambiguous_open_not_counted_as_price_mismatch(self):
        ts = START // 1000
        sample = archive_with_first_day_rows([
            trade_row(ts, "9000.5"),
            trade_row(ts, "9000.6"),
            trade_row(ts + 1, "9000.5"),
        ])
        series = reconstruct_weekly_trade_hours(sample)
        compare = reconcile_weekly_trades_with_v5_kline(series, reference_page())
        self.assertEqual(compare.ambiguous_boundary_hours, 1)
        self.assertEqual(compare.fully_comparable_ohlc_hours, 6)
        self.assertEqual(compare.open_compared, 6)
        self.assertEqual(compare.close_compared, 7)
        self.assertEqual(compare.high_divergent, 1)
        self.assertEqual(compare.divergent_ohlc_hours, 0)

    def test_reference_window_contract_and_integrity_fail_closed(self):
        week = reconstruct_weekly_trade_hours(samples(date(2020, 4, 5)))
        ref = reference_page()
        invalid = [
            replace(ref, symbol="BTCUSDC"),
            replace(ref, quote_currency="USDC"),
            replace(ref, interval="5m"),
            replace(ref, start_open_ms=START + HOUR),
            replace(ref, end_open_ms=END - HOUR),
            replace(ref, candles=ref.candles[:-1]),
            replace(ref, candles=(replace(ref.candles[0], open_time_ms=START + 1),
                                  *ref.candles[1:])),
        ]
        for case in invalid:
            with self.subTest(case=case.symbol+case.interval), self.assertRaises(DataValidationError):
                reconcile_weekly_trades_with_v5_kline(week, case)
        with self.assertRaises(DataValidationError):
            reconcile_weekly_trades_with_v5_kline(
                replace(week, missing_hour_open_ms=()), ref)

    def test_reported_trade_field_relations_are_observations_not_units(self):
        pure = reconstruct_weekly_trade_hours(samples(date(2020, 4, 5)))
        self.assertEqual(pure.reported_size_equals_home_trades, 7)
        self.assertEqual(pure.reported_size_differs_from_home_trades, 0)
        self.assertEqual(pure.reported_foreign_equals_price_times_home_trades, 7)
        self.assertEqual(pure.reported_foreign_differs_from_price_times_home_trades, 0)
        ts = START // 1000
        altered = archive_with_first_day_rows([
            trade_row(ts, "9000.5", "1.25", "1.24", "11250.625"),
            trade_row(ts + 1, "9000.5", "1.25", "1.25", "11250.625"),
        ])
        result = reconstruct_weekly_trade_hours(altered)
        self.assertEqual(result.reported_size_differs_from_home_trades, 1)
        self.assertEqual(result.reported_foreign_differs_from_price_times_home_trades, 1)
        self.assertEqual(result.reported_size_equals_home_trades, 7)
        self.assertEqual(result.reported_foreign_equals_price_times_home_trades, 7)
        self.assertFalse(result.canonical_ohlcv_approved)
        self.assertFalse(result.rights_authorized)


if __name__ == "__main__":
    unittest.main()
