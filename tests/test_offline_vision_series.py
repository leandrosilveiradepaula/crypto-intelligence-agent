"""J1 #239 synthetic month chain: strict UTC continuity, no live promotion."""
from __future__ import annotations
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone
from decimal import Decimal
import unittest

from crypto_intelligence_agent.market_data import ClosedCandle, DataValidationError
from crypto_intelligence_agent.offline_vision_month import OfflineVisionMonth, OfflineVisionCandle
from crypto_intelligence_agent.offline_vision_series import (
    OfflineVisionResearchSeries, assemble_offline_vision_months,
)

D = Decimal
HOUR = 3600000


def month(year, n, symbol="BTCUSDT"):
    start = int(datetime(year, n, 1, tzinfo=timezone.utc).timestamp() * 1000)
    y, m = (year + 1, 1) if n == 12 else (year, n + 1)
    end = int(datetime(y, m, 1, tzinfo=timezone.utc).timestamp() * 1000)
    candles = tuple(
        OfflineVisionCandle(
            opened, opened + HOUR - 1, D(100), D(102), D(99),
            D("101.00"), D("1.0"), D("101.00"),
        )
        for opened in range(start, end, HOUR)
    )
    return OfflineVisionMonth(
        f"{symbol}-1h-{year:04d}-{n:02d}.zip", "a" * 64,
        symbol, "1h", start, end, candles,
    )


def assemble(months, **kwargs):
    return assemble_offline_vision_months(
        months, as_of_ms=months[-1].end_open_exclusive_ms + 1000,
        **kwargs,
    )


class VisionResearchSeriesTests(unittest.TestCase):
    def test_december_to_january_and_leap_february(self):
        a, b, c = month(2023, 12), month(2024, 1), month(2024, 2)
        result = assemble((a, b, c))
        self.assertIsInstance(result, OfflineVisionResearchSeries)
        self.assertEqual(len(result.candles), 744 + 744 + 696)
        self.assertEqual(result.candles[744].open_time_ms, b.first_open_ms)
        self.assertEqual(result.candles[-1].close_time_ms, c.end_open_exclusive_ms - 1)
        self.assertEqual(len(result.series_manifest_sha256), 64)
        self.assertEqual(result.quality, "unverified_offline_personal_nonproduction_research_only")
        for gate in (
            "dataset_rights_authorized", "provider_authenticated",
            "historical_top50_verified", "canonical_ohlcv_approved",
            "financial_backtest_approved", "live_trading_authorized", "orders_sent",
        ):
            self.assertIs(getattr(result, gate), False)
        self.assertFalse(isinstance(result.candles[0], ClosedCandle))
        with self.assertRaises(FrozenInstanceError):
            result.symbol = "ETHUSDT"

    def test_missing_duplicate_reordered_and_mixed_months(self):
        jan, feb, mar = month(2024, 1), month(2024, 2), month(2024, 3)
        for candidate in (
            (jan, mar), (feb, jan), (jan, jan),
            (jan, month(2024, 2, "ETHUSDT")),
        ):
            with self.subTest(names=[x.archive_name for x in candidate]):
                with self.assertRaises(DataValidationError):
                    assemble(candidate)
        self.assertEqual(len(assemble((jan, feb, mar)).month_names), 3)

    def test_header_digest_time_and_partial_month_forgery_fail_closed(self):
        jan, feb = month(2024, 1), month(2024, 2)
        bad = (
            replace(feb, interval="15m"),
            replace(feb, symbol="ETHUSDT"),
            replace(feb, first_open_ms=feb.first_open_ms + HOUR),
            replace(feb, end_open_exclusive_ms=feb.end_open_exclusive_ms + HOUR),
            replace(feb, zip_sha256="Invalid"),
            replace(feb, candles=feb.candles[:-1]),
            replace(feb, archive_name="ETHUSDT-1h-2024-02.zip"),
        )
        for item in bad:
            with self.subTest(item=str(item)[:90]), self.assertRaises(DataValidationError):
                assemble((jan, item))

    def test_interior_timestamp_tamper_and_bad_ohlc_volume_fail(self):
        jan, feb = month(2024, 1), month(2024, 2)
        originals = list(feb.candles)
        edited = (
            replace(originals[4], open_time_ms=originals[3].open_time_ms),
            replace(originals[4], high=D(98)),
            replace(originals[4], documented_base_volume=D("-1")),
            replace(originals[4], close=D("NaN")),
            replace(originals[4], low=D("100.0001")),
            replace(originals[4], documented_quote_volume=D("Infinity")),
        )
        for bad in edited:
            with self.subTest(repr=repr(bad)), self.assertRaises(DataValidationError):
                changed = list(originals)
                changed[4] = bad
                assemble((jan, replace(feb, candles=tuple(changed))))

    def test_future_close_safety_and_input_budget_fail_closed(self):
        jan, feb = month(2024, 1), month(2024, 2)
        with self.assertRaises(DataValidationError):
            assemble_offline_vision_months(
                (jan, feb), as_of_ms=feb.end_open_exclusive_ms + 999,
            )
        for wrong in ((jan,), (jan,)*25, [jan, feb], ()):
            with self.subTest(size=len(wrong)), self.assertRaises(DataValidationError):
                assemble_offline_vision_months(
                    wrong, as_of_ms=feb.end_open_exclusive_ms + 1000,
                )
        for bad in (True, 2.0, -1):
            with self.subTest(bad=bad), self.assertRaises(DataValidationError):
                assemble_offline_vision_months((jan, feb), as_of_ms=bad)
        with self.assertRaises(DataValidationError):
            assemble_offline_vision_months(
                (jan, feb), as_of_ms=feb.end_open_exclusive_ms + 1000,
                close_safety_ms=True,
            )

    def test_unchanged_deterministic_receipt_is_not_provider_signature(self):
        pair = (month(2024, 1), month(2024, 2))
        x, y = assemble(pair), assemble(pair)
        self.assertEqual(x, y)
        other = assemble((replace(pair[0], zip_sha256="b" * 64), pair[1]))
        self.assertNotEqual(x.series_manifest_sha256, other.series_manifest_sha256)
        self.assertFalse(other.provider_authenticated)
        self.assertFalse(other.dataset_rights_authorized)


if __name__ == "__main__":
    unittest.main()
