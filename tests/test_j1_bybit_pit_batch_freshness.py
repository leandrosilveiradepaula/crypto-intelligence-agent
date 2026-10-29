"""J1 #310 regression: slow *valid* Bybit PIT ranking must not age itself out.

A conservative 2-second GET pace over a reviewed set can last longer than
30 seconds. Each paginated instrument page still needs a fresh server clock
at its actual receipt. The complete PIT batch has a strict 120-second cap.
No provider HTTP requests, SQLite modifications or credentials in tests.
"""
from unittest.mock import patch
import unittest

from crypto_intelligence_agent.bybit_pit_research import (
    DEFAULT_CONTRACT_MAX_AGE_MS, MAX_PIT_BATCH_CONTRACT_AGE_MS,
    select_bybit_reviewed_sample_pit,
)
from crypto_intelligence_agent.bybit_public_j1_transport import (
    BoundedBybitPublicClient, J1BybitCaptureError,
)
from crypto_intelligence_agent.market_data import DataValidationError
from scripts.capture_private_bybit_j1 import _observe
from test_j1_bybit_exit_vertical import H, T, DECISION, pages, kline
from test_j1_private_bybit_capture import FakeFeed


def aged_pit(*, age_ms=40_000, extended=False, receipts=True):
    source = pages(T - age_ms)
    kwargs = {
        "instrument_pages": source,
        "requested_cursors": (None, "next"),
        "kline_pages": {
            symbol: kline(symbol, DECISION - 24 * H, 24, "100")
            for symbol in ("BTCUSDT", "ETHUSDT")
        },
        "observed_at_ms": T,
        "decision_at_ms": DECISION,
        "max_candidates": 2,
    }
    if receipts:
        # Timestamps were captured at the time of the corresponding GET,
        # not invented from the final ranking-completion timestamp.
        kwargs["instrument_page_received_at_ms"] = (
            T - age_ms - 250, T - age_ms - 150,
        )
    if extended:
        kwargs["max_contract_age_ms"] = MAX_PIT_BATCH_CONTRACT_AGE_MS
    return select_bybit_reviewed_sample_pit(**kwargs)


class BybitPITBatchClockTests(unittest.TestCase):
    def test_strict_original_30s_default_remains_unchanged(self):
        self.assertEqual(DEFAULT_CONTRACT_MAX_AGE_MS, 30_000)
        with self.assertRaisesRegex(DataValidationError, "stale"):
            aged_pit(age_ms=40_000)
        self.assertEqual(len(aged_pit(age_ms=15_000).ranked), 2)

    def test_bounded_paged_observation_rejects_offline_clock_fabrication(self):
        with self.assertRaises(DataValidationError):
            aged_pit(age_ms=40_000, extended=True, receipts=False)
        self.assertEqual(len(aged_pit(age_ms=40_000, extended=True).ranked), 2)
        with self.assertRaisesRegex(DataValidationError, "exceeds 120s"):
            aged_pit(age_ms=120_100, extended=True)
        with self.assertRaises(DataValidationError):
            aged_pit(age_ms=120_100, extended=False)

    def test_extended_age_cannot_be_unbounded_or_noninteger(self):
        source = pages(T-500)
        kwargs = dict(
            instrument_pages=source, requested_cursors=(None, "next"),
            kline_pages={
                symbol: kline(symbol, DECISION - 24*H, 24, "1")
                for symbol in ("BTCUSDT", "ETHUSDT")
            },
            observed_at_ms=T, decision_at_ms=DECISION,
            instrument_page_received_at_ms=(T-450, T-350),
        )
        for bad in (True, False, -1, 120_001, 1.5, "120000", None):
            with self.subTest(age=bad):
                with self.assertRaises(DataValidationError):
                    select_bybit_reviewed_sample_pit(
                        **kwargs, max_contract_age_ms=bad)

    def test_owner_observe_accepts_40s_valid_pacing_with_no_real_network(self):
        fake = FakeFeed()
        waits = [False]

        def delayed_get(url, limit):
            if "/kline" in url and not waits[0]:
                fake.observed += 40_000
                waits[0] = True
            return fake.get(url, limit)

        with patch("socket.create_connection",
                   side_effect=AssertionError("unexpected network")):
            choice, row_count = _observe(
                BoundedBybitPublicClient(transport=delayed_get),
                fake.now, max_assets=2,
            )
        self.assertEqual(len(choice.ranked), 2)
        self.assertEqual(choice.decision_at_ms, DECISION)
        self.assertFalse(choice.verified_market_top50)
        self.assertTrue(waits[0])
        self.assertGreaterEqual(row_count, 2)

    def test_owner_observe_fails_over_120s_even_if_hour_unchanged(self):
        fake = FakeFeed()
        waits = [False]

        def delayed_get(url, limit):
            if "/kline" in url and not waits[0]:
                fake.observed += 120_100
                waits[0] = True
            return fake.get(url, limit)

        with patch("socket.create_connection",
                   side_effect=AssertionError("unexpected network")):
            with self.assertRaisesRegex(
                J1BybitCaptureError, "pit_paged_observation_exceeds_120s"
            ):
                _observe(BoundedBybitPublicClient(transport=delayed_get),
                         fake.now, max_assets=2)


if __name__ == "__main__":
    unittest.main()
