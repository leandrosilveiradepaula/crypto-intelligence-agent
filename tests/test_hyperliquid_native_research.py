"""Adversarial offline tests: Hyperliquid /info is never called by these tests."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal
import unittest

from crypto_intelligence_agent.hyperliquid_native_research import (
    DOCUMENTED_RECENT_HISTORY_CANDLES, MAX_RESEARCH_PAGE, SOURCE,
    NativeCandleResearch, stage_hyperliquid_native_perp_candles,
)
from crypto_intelligence_agent.market_data import (
    ClosedCandle, DataGapError, DataValidationError,
)

HOUR = 3_600_000
DAY = 86_400_000
START = 10 * HOUR
END = START + 3 * HOUR
CAPTURE = END + 1000


def market_metadata():
    return [
        {"universe": [{"name": "BTC", "maxLeverage": 50, "szDecimals": 5}],
         "marginTables": [], "collateralToken": 0},
        [{"dayNtlVlm": "12000000.123456789012345678",
          "markPx": "77777.12345678901234",
          "openInterest": "1234.123",
          "funding": "-0.000000123"}],
    ]


def candle_fixture():
    return [
        {"t": START + i * HOUR, "T": START + (i + 1) * HOUR - 1,
         "s": "BTC", "i": "1h", "o": str(60000+i),
         "h": str(60100+i), "l": str(59900+i), "c": str(60001+i),
         "v": f"1.{i}2345678912345678912", "n": i+100}
        for i in range(3)
    ]


NOT_PROVIDED = object()


def stage(ctx=NOT_PROVIDED, rows=NOT_PROVIDED, **opts):
    return stage_hyperliquid_native_perp_candles(
        market_metadata() if ctx is NOT_PROVIDED else ctx,
        candle_fixture() if rows is NOT_PROVIDED else rows,
        symbol=opts.get("symbol", "BTC"),
        dex_scope=opts.get("dex", ""),
        interval=opts.get("interval", "1h"),
        start_open_ms=opts.get("start", START),
        end_open_ms=opts.get("end", END),
        context_observed_at_ms=opts.get("ctx_observed", START),
        observed_at_ms=opts.get("observed", CAPTURE),
        max_context_age_ms=opts.get("max_ctx_age", CAPTURE-START),
        close_safety_ms=opts.get("safety", 1000),
        max_candles=opts.get("max_candles", 500),
    )


class HyperliquidNativeResearchTests(unittest.TestCase):
    def test_reports_causal_closed_candles_and_precise_unverified_volume(self):
        page = stage()
        self.assertEqual(page.source, SOURCE)
        self.assertEqual(page.interval, "1h")
        self.assertEqual([row.open_time_ms for row in page.candles],
                         [START, START+HOUR, START+2*HOUR])
        row = page.candles[0]
        self.assertIsInstance(row, NativeCandleResearch)
        self.assertNotIsInstance(row, ClosedCandle)
        self.assertEqual(row.raw_volume_unit_unverified, Decimal("1.02345678912345678912"))
        self.assertEqual(row.reported_trade_count, 100)
        self.assertFalse(row.base_volume_verified)
        self.assertFalse(row.quote_volume_verified)
        self.assertFalse(hasattr(row, "base_volume"))
        self.assertFalse(hasattr(row, "quote_volume"))
        self.assertNotEqual(row.close * row.raw_volume_unit_unverified,
                            row.raw_volume_unit_unverified)

    def test_perp_context_is_reported_only_not_trade_authorization(self):
        m = stage().metadata
        self.assertEqual(m.max_leverage_reported, 50)
        self.assertEqual(m.size_decimals_reported, 5)
        self.assertEqual(m.day_notional_reported, Decimal("12000000.123456789012345678"))
        self.assertEqual(m.funding_rate_reported, Decimal("-0.000000123"))
        self.assertFalse(m.crypto_identity_verified)
        self.assertFalse(m.venue_leverage_verified)
        self.assertFalse(m.rights_for_distribution)
        self.assertFalse(stage().ready_for_canonical_ohlcv)
        self.assertFalse(stage().ready_for_live_top50)
        self.assertFalse(stage().rights_for_distribution)
        self.assertEqual(DOCUMENTED_RECENT_HISTORY_CANDLES, 5000)

    def test_no_traded_bar_without_positive_volume_and_n(self):
        for value in (0, -1, True, "1", None):
            rows = candle_fixture()
            rows[1]["n"] = value
            with self.subTest(n=value), self.assertRaises(DataValidationError):
                stage(rows=rows)
        for volume in ("0", "-1", "NaN", "Infinity", "1e3", 1.0, None, True):
            rows = candle_fixture()
            rows[0]["v"] = volume
            with self.subTest(volume=volume), self.assertRaises(DataValidationError):
                stage(rows=rows)

    def test_reject_fabricated_ohlc_rounded_or_float_fields(self):
        invalid = ("0", "-1", "NaN", "Infinity", "1e3", "+1", "01.2",
                   "1.1234567890123456789012345", float("nan"), 1.5, True, None)
        for value in invalid:
            rows = candle_fixture()
            rows[2]["o"] = value
            with self.subTest(value=str(value)), self.assertRaises(DataValidationError):
                stage(rows=rows)

    def test_reject_extrema_inconsistent_with_close_open(self):
        for field, value in (("h", "1"), ("l", "99999"), ("c", "99999")):
            rows = candle_fixture()
            rows[2][field] = value
            with self.subTest(field=field), self.assertRaises(DataValidationError):
                stage(rows=rows)

    def test_exact_row_schema_prevents_smuggling_authorization_fields(self):
        for mutation in ("missing", "extra", "wrong-type"):
            rows = candle_fixture()
            if mutation == "missing":
                rows[0].pop("v")
            elif mutation == "extra":
                rows[0]["authorized_for_trading"] = True
            else:
                rows[0] = {"t": "0"}
            with self.subTest(mutation=mutation), self.assertRaises(DataValidationError):
                stage(rows=rows)

    def test_gaps_duplicates_reverse_and_epoch_mismatch_fail(self):
        for mutation in ("missing", "extra", "duplicate", "reverse", "shift", "close"):
            rows = candle_fixture()
            if mutation == "missing":
                rows.pop(1)
            elif mutation == "extra":
                rows.append(deepcopy(rows[-1]))
            elif mutation == "duplicate":
                rows[1]["t"] = rows[0]["t"]
            elif mutation == "reverse":
                rows.reverse()
            elif mutation == "shift":
                rows[1]["t"] += 1
            else:
                rows[0]["T"] += 1
            with self.subTest(mutation=mutation), self.assertRaises(DataGapError):
                stage(rows=rows)

    def test_reject_candles_of_other_coin_or_interval(self):
        for field, value in (("s", "ETH"), ("i", "1d"), ("s", "xyz:AAPL"), ("i", "1w")):
            rows = candle_fixture()
            rows[1][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(DataValidationError):
                stage(rows=rows)

    def test_future_or_unclosed_candle_requires_capture_safety(self):
        with self.assertRaisesRegex(DataValidationError, "future/unclosed"):
            stage(observed=END + 998)
        self.assertEqual(len(stage(observed=END + 999).candles), 3)
        with self.assertRaises(DataValidationError):
            stage(safety=True)
        with self.assertRaises(DataValidationError):
            stage(safety=HOUR+1)

    def test_context_future_and_stale_fail_closed(self):
        with self.assertRaises(DataValidationError):
            stage(ctx_observed=CAPTURE + 1)
        with self.assertRaisesRegex(DataValidationError, "stale"):
            stage(max_ctx_age=CAPTURE-START-1)
        self.assertEqual(stage(max_ctx_age=CAPTURE-START).metadata.observed_at_ms, START)
        for val in (True, -1, 1.25, "3600", 86_400_001):
            with self.subTest(val=val), self.assertRaises(DataValidationError):
                stage(max_ctx_age=val)

    def test_bad_times_and_window_alignment_fail(self):
        for key, val in (("start", START+1), ("end", END-1), ("start", END),
                         ("start", True), ("observed", True),
                         ("ctx_observed", 0), ("end", 1.0)):
            with self.subTest(key=key, value=val), self.assertRaises(DataValidationError):
                stage(**{key:val})

    def test_unsupported_week_month_or_unknown_intervals_fail_closed(self):
        for interval in ("1w", "1M", "3d", "6h", "1H", "", "0m", None):
            with self.subTest(interval=interval), self.assertRaises(DataValidationError):
                stage(interval=interval)

    def test_explicit_utc_day_is_allowed(self):
        start = 10 * DAY
        row = candle_fixture()[0]
        row["t"], row["T"], row["i"] = start, start+DAY-1, "1d"
        page = stage(rows=[row], interval="1d", start=start, end=start+DAY,
                     ctx_observed=start+1000, observed=start+DAY+1000, max_ctx_age=DAY)
        self.assertEqual(page.candles[0].close_time_ms, start+DAY-1)

    def test_metadata_universe_contexts_must_be_one_to_one(self):
        bad = [
            [], [{}, []], [market_metadata()[0], []],
            [market_metadata()[0], "not-list"],
            [market_metadata()[0], [{"markPx": "1"}]],
        ]
        for ctx in bad:
            with self.subTest(ctx=str(ctx)[:80]), self.assertRaises(DataValidationError):
                stage(ctx=ctx)

    def test_not_in_native_universe_delisted_or_hip3_rejected(self):
        with self.assertRaises(DataValidationError):
            stage(symbol="ETH")
        ctx = market_metadata()
        ctx[0]["universe"][0]["isDelisted"] = True
        with self.assertRaises(DataValidationError):
            stage(ctx=ctx)
        for name in ("xyz:AAPL", "@107", "BTC-USDT", "BTC/USDC", "btc", ""):
            ctx = market_metadata()
            ctx[0]["universe"][0]["name"] = name
            with self.subTest(name=name), self.assertRaises(DataValidationError):
                stage(ctx=ctx)

    def test_unrelated_native_k_prefix_does_not_disqualify_btc_context(self):
        context = market_metadata()
        context[0]["universe"].append({
            "name": "kBONK", "maxLeverage": 10, "szDecimals": 0,
        })
        context[1].append({
            "dayNtlVlm": "5", "markPx": "0.001",
            "openInterest": "3", "funding": "0",
        })
        result = stage(ctx=context)
        self.assertEqual(result.symbol, "BTC")
        self.assertFalse(result.metadata.crypto_identity_verified)
        self.assertFalse(result.ready_for_canonical_ohlcv)

    def test_native_scope_only_not_hip3(self):
        for val in ("xyz", "HIP3", "native", 0, None, False):
            with self.subTest(scope=val), self.assertRaises(DataValidationError):
                stage(dex=val)

    def test_duplicate_universe_names_cannot_be_accepted(self):
        ctx = market_metadata()
        ctx[0]["universe"].append(deepcopy(ctx[0]["universe"][0]))
        ctx[1].append(deepcopy(ctx[1][0]))
        with self.assertRaises(DataValidationError):
            stage(ctx=ctx)

    def test_metadata_numeric_and_type_mismatches_rejected(self):
        changes = (
            ("maxLeverage", 0), ("maxLeverage", True), ("maxLeverage", "50"),
            ("maxLeverage", 201), ("szDecimals", 19), ("szDecimals", 0.5),
        )
        for key, value in changes:
            ctx = market_metadata()
            ctx[0]["universe"][0][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(DataValidationError):
                stage(ctx=ctx)
        for field, value in (
            ("dayNtlVlm", 1.5), ("dayNtlVlm", "-2"), ("markPx", "0"),
            ("markPx", "NaN"), ("openInterest", "-1"), ("funding", 0.001),
            ("funding", "1e3"),
        ):
            ctx = market_metadata()
            ctx[1][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(DataValidationError):
                stage(ctx=ctx)

    def test_page_limit_and_input_sequence_types_rejected(self):
        for limit in (0, -1, True, 1.5, 501, 2):
            with self.subTest(limit=limit), self.assertRaises(DataValidationError):
                stage(max_candles=limit)
        for values in ("bad", None, {}, []):
            with self.subTest(values=repr(values)), self.assertRaises(DataGapError):
                stage(rows=values)

    def test_output_immutability_and_flags_not_constructor_overrides(self):
        page = stage()
        with self.assertRaises(FrozenInstanceError):
            page.candles[0].raw_volume_unit_unverified = Decimal("1")
        for obj, field in (
            (page, "ready_for_canonical_ohlcv"),
            (page, "rights_for_distribution"),
            (page.metadata, "crypto_identity_verified"),
            (page.metadata, "venue_leverage_verified"),
            (page.candles[0], "base_volume_verified"),
        ):
            with self.subTest(field=field), self.assertRaises(TypeError):
                replace(obj, **{field:True})

    def test_replay_is_deterministic_and_never_executes_api(self):
        self.assertEqual(stage(), stage(ctx=deepcopy(market_metadata()),
                                       rows=deepcopy(candle_fixture())))


if __name__ == "__main__":
    unittest.main()
