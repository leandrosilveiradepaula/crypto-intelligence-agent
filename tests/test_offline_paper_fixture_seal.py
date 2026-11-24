"""J6/PRE2-A: offline integrity only; deliberate absence of cursor writes."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.market_data import DataGapError, DataValidationError
from crypto_intelligence_agent.offline_paper_fixture_seal import (
    SEAL_VERSION, OfflinePaperFixtureSeal, seal_offline_paper_prefix,
    verify_offline_paper_extension,
)
from crypto_intelligence_agent.synthetic_order_lifecycle import PaperVenue
from test_causal_paper_open import limits
from test_synthetic_research_cycle import H, candles, config

D = Decimal


class OfflineFixtureSealTests(unittest.TestCase):
    def setUp(self):
        self.rows = candles(n=10)
        self.strategy = config().strategy
        self.limits = limits()

    def seal(self, rows, **changes):
        args = dict(
            strategy=self.strategy, venue=PaperVenue.BINANCE_USDM,
            requested_units=D("2.00"), limits=self.limits,
            close_safety_ms=1_000, max_candles=20,
            decision_at_ms=rows[-1].close_time_ms + 1_000,
        )
        args.update(changes)
        return seal_offline_paper_prefix(tuple(rows), **args)

    def extend(self, previous, rows, **changes):
        args = dict(
            strategy=self.strategy, venue=PaperVenue.BINANCE_USDM,
            requested_units=D("2.00"), limits=self.limits,
            close_safety_ms=1_000, max_candles=20,
            decision_at_ms=rows[-1].close_time_ms + 1_000,
        )
        args.update(changes)
        return verify_offline_paper_extension(previous, tuple(rows), **args)

    def test_stable_complete_prefix_and_explicitly_non_durable(self):
        a = self.seal(self.rows[:5])
        b = self.seal(list(self.rows[:5]))
        self.assertEqual(a, b)
        self.assertIsInstance(a, OfflinePaperFixtureSeal)
        self.assertEqual(a.version, SEAL_VERSION)
        self.assertEqual(len(a.prefix_sha256), 64)
        self.assertEqual(len(a.context_sha256), 64)
        self.assertEqual(a.candle_count, 5)
        self.assertEqual(a.last_close_time_ms, self.rows[4].close_time_ms)
        for flag in (
            "durable_session_checkpoint_available", "order_submission_enabled",
            "orders_sent", "market_data_verified", "approved_for_live_use",
        ):
            self.assertFalse(getattr(a, flag))

    def test_public_indicators_are_never_encoded_as_legacy_breakout(self):
        from crypto_intelligence_agent.j2_configurable_indicators_d513 import (
            IndicatorSelection, MovingAverageSlot, PivotSuperTrend,
        )
        off = tuple(MovingAverageSlot(False, n) for n in (10, 30, 60))
        selection = IndicatorSelection(off, off, PivotSuperTrend(False, 2, 10, D(3)))
        for mode in ("breakout", "indicator_combo"):
            with self.subTest(mode=mode), self.assertRaisesRegex(
                    DataValidationError, "prefix v1 requires breakout"):
                self.seal(self.rows[:5], strategy=replace(
                    self.strategy, entry_mode=mode, indicators=selection))
        # The v1 digest remains the exact legacy projection, without new fields.
        from dataclasses import fields
        from crypto_intelligence_agent.offline_paper_fixture_seal import (
            _record, _scalar, _canonical_digest,
        )
        context = {
            "version": SEAL_VERSION, "strategy_id": "synthetic_compression_breakout_v1",
            "features": _record(self.strategy.features, type(self.strategy.features)),
            "strategy": {field.name: _scalar(getattr(self.strategy, field.name))
                         for field in fields(type(self.strategy))
                         if field.name in ("compression_bars", "baseline_bars",
                                           "max_atr_ratio", "min_quote_volume_ratio",
                                           "cooldown_bars", "experimental_paper_relaxation")},
            "venue_candidate": PaperVenue.BINANCE_USDM.value,
            "requested_units": _scalar(D("2.00")),
            "risk_limits": _record(self.limits, type(self.limits)),
            "close_safety_ms": 1000, "max_candles": 20,
        }
        from crypto_intelligence_agent.synthetic_entry_hypotheses import STRATEGY_ID
        context["strategy_id"] = STRATEGY_ID
        self.assertEqual(self.seal(self.rows[:5]).context_sha256,
                         _canonical_digest(context))

    def test_prefix_integrity_includes_decimal_scale_not_just_value(self):
        a = self.seal(self.rows[:5])
        edited = list(self.rows[:5])
        edited[0] = replace(edited[0], open=D("100.0"))
        b = self.seal(edited)
        self.assertNotEqual(a.prefix_sha256, b.prefix_sha256)
        self.assertEqual(a.context_sha256, b.context_sha256)
        with self.assertRaisesRegex(DataValidationError, "digest diverged"):
            self.extend(a, edited + [self.rows[5]])

    def test_context_changes_are_visible_even_when_candles_match(self):
        baseline = self.seal(self.rows[:5])
        altered_strategy = replace(
            self.strategy, min_quote_volume_ratio=D("9.00")
        )
        altered_limits = replace(
            self.limits, max_market_age_ms=self.limits.max_market_age_ms + 1
        )
        variants = (
            {"strategy": altered_strategy},
            {"venue": PaperVenue.BYBIT_V5},
            {"requested_units": D("2.0")},
            {"limits": altered_limits},
            {"close_safety_ms": 2_000,
             "decision_at_ms": self.rows[4].close_time_ms + 2_000},
            {"max_candles": 21},
        )
        for variant in variants:
            with self.subTest(variant=variant):
                changed = self.seal(self.rows[:5], **variant)
                self.assertNotEqual(baseline.context_sha256, changed.context_sha256)
                with self.assertRaisesRegex(DataValidationError, "digest diverged"):
                    self.extend(baseline, self.rows[:6], **{
                        **variant,
                        "decision_at_ms": self.rows[5].close_time_ms
                                          + variant.get("close_safety_ms", 1_000),
                    })

    def test_exact_single_candle_forward_verified(self):
        first = self.seal(self.rows[:5])
        second = self.extend(first, self.rows[:6])
        self.assertEqual(second, self.seal(self.rows[:6]))
        third = self.extend(second, self.rows[:7])
        self.assertEqual(third.candle_count, 7)
        self.assertNotEqual(first.prefix_sha256, second.prefix_sha256)

    def test_replay_jump_rollback_and_truncation_fail_closed(self):
        first = self.seal(self.rows[:5])
        for prefix in (self.rows[:5], self.rows[:7], self.rows[:4]):
            with self.subTest(length=len(prefix)):
                with self.assertRaises(DataValidationError):
                    self.extend(first, prefix)
        with self.assertRaisesRegex(DataValidationError, "digest diverged"):
            self.extend(first, self.rows[2:8])

    def test_candle_corruption_gap_and_future_clock_block(self):
        previous = self.seal(self.rows[:5])
        gap = list(self.rows[:6])
        gap[-1] = replace(
            gap[-1], open_time_ms=gap[-1].open_time_ms + H,
            close_time_ms=gap[-1].close_time_ms + H,
        )
        with self.assertRaises(DataGapError):
            self.extend(previous, gap)
        bad_quality = list(self.rows[:6])
        bad_quality[-1] = replace(bad_quality[-1], quality="unverified_provider")
        with self.assertRaises(DataValidationError):
            self.extend(previous, bad_quality)
        with self.assertRaises(DataValidationError):
            self.extend(
                previous, self.rows[:6],
                decision_at_ms=self.rows[5].close_time_ms + 999,
            )

    def test_recomputed_prior_seal_rejects_metadata_tampering(self):
        previous = self.seal(self.rows[:5])
        for bad in (
            replace(previous, candle_count=4),
            replace(previous, last_close_time_ms=previous.last_close_time_ms+1),
            replace(previous, prefix_sha256="0"*64),
            replace(previous, version="unknown"),
        ):
            with self.subTest(bad=bad), self.assertRaises(DataValidationError):
                self.extend(bad, self.rows[:6])

    def test_invalid_types_and_resource_limit_fail_closed(self):
        for changes in (
            {"strategy": None}, {"venue": "Binance"},
            {"requested_units": 2}, {"requested_units": D("NaN")},
            {"max_candles": True}, {"max_candles": 3},
            {"close_safety_ms": -1}, {"limits": None},
        ):
            with self.subTest(changes=changes), self.assertRaises(DataValidationError):
                self.seal(self.rows[:5], **changes)
        with self.assertRaises(DataValidationError):
            self.extend("digest", self.rows[:6])

    def test_sealing_is_pure_no_network_or_sqlite_creation(self):
        with patch("urllib.request.urlopen", side_effect=AssertionError("network")):
            with patch("socket.create_connection", side_effect=AssertionError("network")):
                seal = self.seal(self.rows[:5])
                self.assertFalse(self.extend(seal, self.rows[:6]).orders_sent)


if __name__ == "__main__":
    unittest.main()
