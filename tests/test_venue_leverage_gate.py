"""Offline contract-tier leverage safety gates (synthetic schedules only).

These fixtures resemble public Kraken risk schedule classes but are NOT an
up-to-date venue download or permission to trade with 50x in any jurisdiction.
"""
from __future__ import annotations

from dataclasses import FrozenInstanceError
from decimal import Decimal
import unittest

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.venue_leverage_gate import (
    VenueNotionalTier, VenueLeverageSchedule, assess_new_research_position,
)


OBSERVED = 1_793_000_000_000
SOURCE = ("https://support.kraken.com/br/articles/"
          "360022632452-derivatives-margin-schedule-maximum-leverage")


def tier(minimum, maximum, leverage):
    return VenueNotionalTier(
        min_notional_usd=Decimal(str(minimum)),
        max_notional_usd=None if maximum is None else Decimal(str(maximum)),
        maximum_leverage=Decimal(str(leverage)),
    )


def btc_schedule(*, observed=OBSERVED):
    return VenueLeverageSchedule(
        venue="kraken_futures", symbol="PF_XBTUSD", quote_currency="USD",
        observed_at_ms=observed,
        source_url=SOURCE, source_version="synthetic-btc-tiers-v1",
        tiers=(tier("0", "1000000", "100"),
               tier("1000000", "3000000", "50"),
               tier("3000000", None, "25")),
    )


def low_cap_schedule():
    return VenueLeverageSchedule(
        venue="kraken_futures", symbol="PF_1INCHUSD", quote_currency="USD",
        observed_at_ms=OBSERVED, source_url=SOURCE,
        source_version="synthetic-class-e-v1", tiers=(tier(0, None, 10),),
    )


def assess(*, schedule=None, leverage=50, new=1000, existing=0,
           decision=OBSERVED + 1000, freshness=60000):
    return assess_new_research_position(
        schedule=btc_schedule() if schedule is None else schedule,
        requested_global_leverage=leverage,
        new_position_notional_usd=new,
        existing_symbol_exposure_usd=existing,
        decision_at_ms=decision,
        max_schedule_age_ms=freshness,
    )


class VenueLeverageSafetyTests(unittest.TestCase):
    def test_global_50x_is_rejected_when_venue_cap_is_10x(self):
        result = assess(schedule=low_cap_schedule())
        self.assertFalse(result.allowed_for_research)
        self.assertEqual(result.reason, "requested_leverage_exceeds_venue_tier")
        self.assertEqual(result.requested_leverage, Decimal(50))
        self.assertEqual(result.venue_cap_leverage, Decimal(10))
        self.assertFalse(result.guaranteed_exchange_acceptance)
        self.assertFalse(result.adjusts_existing_positions)
        self.assertFalse(result.sends_orders)

    def test_50x_is_compatible_with_100x_initial_tier_but_not_guaranteed(self):
        result = assess(leverage=50)
        self.assertTrue(result.allowed_for_research)
        self.assertEqual(result.venue_cap_leverage, Decimal(100))
        self.assertEqual(result.reason, "within_reviewed_notional_tier")
        self.assertFalse(result.guaranteed_exchange_acceptance)

    def test_aggregate_exposure_can_lower_tier_without_changing_global_leverage(self):
        safe = assess(leverage=50, new=1000, existing=998000)
        self.assertEqual(safe.aggregate_exposure_usd, Decimal(999000))
        self.assertEqual(safe.venue_cap_leverage, Decimal(100))
        boundary = assess(leverage=75, new=1000, existing=999000)
        self.assertFalse(boundary.allowed_for_research)
        self.assertEqual(boundary.venue_cap_leverage, Decimal(50))
        self.assertEqual(boundary.bracket_min_usd, Decimal(1000000))
        self.assertEqual(boundary.bracket_max_usd_exclusive, Decimal(3000000))
        self.assertEqual(boundary.requested_leverage, Decimal(75))
        self.assertEqual(boundary.new_position_notional_usd, Decimal(1000))

    def test_high_exposure_crosses_a_second_risk_tier(self):
        result = assess(leverage=50, new=500, existing=2999600)
        self.assertFalse(result.allowed_for_research)
        self.assertEqual(result.aggregate_exposure_usd, Decimal(3000100))
        self.assertEqual(result.venue_cap_leverage, Decimal(25))
        self.assertIsNone(result.bracket_max_usd_exclusive)

    def test_requested_lev_exactly_equal_to_cap_passes_without_auto_adjustment(self):
        result = assess(leverage=50, new=500000, existing=600000)
        self.assertTrue(result.allowed_for_research)
        self.assertEqual(result.venue_cap_leverage, Decimal(50))
        self.assertEqual(result.requested_leverage, Decimal(50))

    def test_nonzero_existing_exposure_is_required_for_aggregated_decision(self):
        # Tool only uses what caller declares; provenance of current
        # position/exposure is a separate J3 validation requirement.
        result = assess(leverage=20, new=Decimal("0.1"), existing=Decimal("2.1"))
        self.assertEqual(result.aggregate_exposure_usd, Decimal("2.2"))
        self.assertTrue(result.allowed_for_research)

    def test_timestamp_future_schedule_rejected_to_prevent_lookahead(self):
        with self.assertRaisesRegex(DataValidationError, "future"):
            assess(schedule=btc_schedule(observed=OBSERVED + 2000),
                   decision=OBSERVED + 1000)

    def test_schedule_freshness_inclusive_and_plus_one_invalid(self):
        self.assertTrue(assess(freshness=1000).allowed_for_research)
        with self.assertRaisesRegex(DataValidationError, "too old"):
            assess(freshness=999)

    def test_invalid_times_and_limits_rejected(self):
        for decision in (True, "1800", -1, 0, 1.23):
            with self.subTest(decision=decision):
                with self.assertRaises(DataValidationError):
                    assess(decision=decision)
        for freshness in (True, -1, 1.2, "10"):
            with self.subTest(freshness=freshness):
                with self.assertRaises(DataValidationError):
                    assess(freshness=freshness)
        for observed in (True, 0, -1, 1.23):
            with self.subTest(observed=observed):
                with self.assertRaises(DataValidationError):
                    btc_schedule(observed=observed)

    def test_bad_numeric_values_rejected_without_float_coercion(self):
        for bad in (True, 1.5, "50", float("nan"), Decimal("NaN"),
                    Decimal("Infinity"), Decimal("-Infinity"),
                    Decimal("-1"), 0, Decimal("1e100"), Decimal("1e-25")):
            with self.subTest(bad=bad):
                with self.assertRaises(DataValidationError):
                    assess(leverage=bad)
                with self.assertRaises(DataValidationError):
                    assess(new=bad)
        for bad in (True, 1.5, "2", float("nan"), Decimal("NaN"), -1,
                    Decimal("Infinity")):
            with self.subTest(existing=bad):
                with self.assertRaises(DataValidationError):
                    assess(existing=bad)

    def test_zero_existing_notional_is_accepted_but_zero_new_notional_is_not(self):
        self.assertTrue(assess(new=1, existing=0).allowed_for_research)
        with self.assertRaises(DataValidationError):
            assess(new=0)

    def test_tiers_must_start_at_zero_and_cover_all_exposure_contiguously(self):
        invalid_tiers = [
            (tier(1, None, 50),),
            (tier(0, 100, 50), tier(110, None, 20)),
            (tier(0, 100, 50), tier(90, None, 20)),
            (tier(0, None, 50), tier(100, None, 20)),
            (tier(0, 100, 50),),
            (tier(0, 100, 20), tier(100, None, 50)),
        ]
        for bad in invalid_tiers:
            with self.subTest(tiers=bad):
                with self.assertRaises(DataValidationError):
                    VenueLeverageSchedule(
                        venue="kraken_futures", symbol="PF_XBTUSD",
                        quote_currency="USD", observed_at_ms=OBSERVED,
                        source_url=SOURCE, source_version="fixture",
                        tiers=bad,
                    )

    def test_tiers_cannot_have_invalid_caps_or_bounds(self):
        for minimum, maximum, leverage in (
            (0, 0, 50), (100, 90, 50), (-1, 100, 50),
            (0, None, 0), (0, None, Decimal("NaN")),
            (0, None, Decimal("Infinity")), (0, None, 0.5),
        ):
            with self.subTest(tier=(minimum,maximum,str(leverage))):
                with self.assertRaises(DataValidationError):
                    VenueNotionalTier(minimum, maximum, leverage)

    def test_contract_symbol_venue_quote_source_version_fail_closed(self):
        valid = btc_schedule()
        baseline = dict(venue=valid.venue, symbol=valid.symbol,
                        quote_currency=valid.quote_currency,
                        observed_at_ms=valid.observed_at_ms,
                        source_url=valid.source_url,
                        source_version=valid.source_version, tiers=valid.tiers)
        for field, value in (
            ("venue", "binance"), ("symbol", "PI_XBTUSD"),
            ("symbol", "PF_XBTUSDT"), ("symbol", "PF_AAPLXUSD/../../"),
            ("quote_currency", "USDT"), ("source_version", ""),
            ("source_url", "http://example.com"),
            ("source_url", "https://username:password@support.kraken.com/docs"),
            ("source_url", "https://support.kraken.com/docs?secret=yes"),
            ("source_url", "https://localhost/data"),
        ):
            with self.subTest(field=field,value=value):
                with self.assertRaises(DataValidationError):
                    VenueLeverageSchedule(**{**baseline, field: value})

    def test_schedule_without_valid_brackets_is_rejected(self):
        p = btc_schedule()
        with self.assertRaises(DataValidationError):
            VenueLeverageSchedule(p.venue,p.symbol,p.quote_currency,p.observed_at_ms,
                                  p.source_url,p.source_version,())
        with self.assertRaises(DataValidationError):
            VenueLeverageSchedule(p.venue,p.symbol,p.quote_currency,p.observed_at_ms,
                                  p.source_url,p.source_version,("invalid",))

    def test_output_is_immutable_and_contains_exact_schedule_version(self):
        report = assess(leverage=50, new=Decimal("1.75"), existing=Decimal("0.25"))
        self.assertEqual(report.source_version, "synthetic-btc-tiers-v1")
        self.assertEqual(report.source_observed_at_ms, OBSERVED)
        self.assertEqual(report.symbol, "PF_XBTUSD")
        with self.assertRaises(FrozenInstanceError):
            report.requested_leverage = Decimal(1)


if __name__ == "__main__":
    unittest.main()
