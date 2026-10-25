"""Owner-only private Kraken price smoke: entirely offline fake-reader tests."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest

from crypto_intelligence_agent.kraken_candle_validation import stage_kraken_trade_candles
from crypto_intelligence_agent.kraken_public_readonly import KrakenCapturedCandleResearchPage
from crypto_intelligence_agent.market_data import ExchangeAccessError
from scripts.probe_kraken_price_archive import (
    HOUR_MS, PriceProbeError, inspect_once,
)

NOW = 100 * HOUR_MS + 2000
TOP = (NOW // HOUR_MS) * HOUR_MS


class FakeReader:
    def __init__(self, *, error=None, invalid=False):
        self.calls = []
        self.error = error
        self.invalid = invalid

    def staged_closed_candles(self, *, symbol, interval, start_open_ms, end_open_ms):
        self.calls.append((symbol, interval, start_open_ms, end_open_ms))
        if self.error is not None:
            raise self.error
        payload = {
            "more_candles": False,
            "candles": [
                {"time": start_open_ms + i * HOUR_MS,
                 "open": "100.00000000000001",
                 "high": "105", "low": "90", "close": "101.234567890123456789",
                 "volume": "35.123456789123456789"}
                for i in range(3)
            ],
        }
        if self.invalid:
            payload["candles"].pop()
            # Invalid source cannot be re-staged; mimic a corrupt dataclass
            # only after a valid one was constructed.
            good = {**payload, "candles": payload["candles"] + [
                {"time": start_open_ms + 2 * HOUR_MS,
                 "open": "100", "high": "105", "low": "90",
                 "close": "101", "volume": "3"}]}
            stage = stage_kraken_trade_candles(
                good, symbol=symbol, interval=interval,
                start_open_ms=start_open_ms, end_open_ms=end_open_ms,
                observed_at_ms=NOW,
            )
            from dataclasses import replace
            stage = replace(stage, candles=stage.candles[:2])
        else:
            stage = stage_kraken_trade_candles(
                payload, symbol=symbol, interval=interval,
                start_open_ms=start_open_ms, end_open_ms=end_open_ms,
                observed_at_ms=NOW,
            )
        return KrakenCapturedCandleResearchPage(observed_at_ms=NOW, staged=stage)


def run(reader):
    return inspect_once(
        allow_public_network=True, allow_private_kraken_prices=True,
        client=reader, clock_ms=lambda: NOW,
    )


class PrivatePriceSmokeTests(unittest.TestCase):
    def test_real_path_persists_then_discards_ephemeral_db(self):
        reader = FakeReader()
        result = run(reader)
        self.assertEqual(result["status"], "private_price_only_archive_validated")
        self.assertEqual(result["requests_attempted"], 1)
        self.assertEqual(reader.calls, [
            ("PF_XBTUSD", "1h", TOP - 4 * HOUR_MS, TOP - HOUR_MS)])
        self.assertEqual(result["closed_prices_stored_ephemerally"], 3)
        self.assertEqual(result["price_only_coverage"], "complete")
        self.assertFalse(result["canonical_ohlcv_approved"])
        self.assertFalse(result["volume_unit_verified"])
        self.assertFalse(result["market_data_published"])
        self.assertFalse(result["retained_market_data_after_run"])
        self.assertNotIn("101.234567890123456789", json.dumps(result))
        self.assertNotIn("35.123456789123456789", json.dumps(result))

    def test_no_network_without_double_optin(self):
        reader = FakeReader()
        for a, b in ((False, False), (True, False), (False, True)):
            with self.subTest(a=a, b=b), self.assertRaises(PriceProbeError):
                inspect_once(allow_public_network=a,
                             allow_private_kraken_prices=b,
                             client=reader, clock_ms=lambda: NOW)
        self.assertEqual(reader.calls, [])

    def test_access_restriction_never_retries(self):
        reader = FakeReader(error=ExchangeAccessError("HTTP 451"))
        result = run(reader)
        self.assertEqual(result["status"], "access_restricted_no_retry")
        self.assertEqual(result["requests_attempted"], 1)
        self.assertEqual(len(reader.calls), 1)

    def test_invalid_page_rejected_no_canonical_claims(self):
        reader = FakeReader(invalid=True)
        result = run(reader)
        self.assertEqual(result["status"], "invalid_chart_or_price_only_page")
        self.assertFalse(result["canonical_ohlcv_approved"])
        self.assertEqual(len(reader.calls), 1)

    def test_clock_cannot_be_future_bool_or_nonpositive(self):
        reader = FakeReader()
        for value in (True, "100", -1, 0):
            with self.subTest(value=value), self.assertRaises(PriceProbeError):
                inspect_once(allow_public_network=True,
                             allow_private_kraken_prices=True,
                             client=reader, clock_ms=lambda: value)
        self.assertEqual(reader.calls, [])

    def test_entrypoint_runs_as_module_without_network(self):
        root = Path(__file__).resolve().parent.parent
        result = subprocess.run(
            [sys.executable, "-m", "scripts.probe_kraken_price_archive", "--help"],
            cwd=root, text=True, capture_output=True, timeout=10, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--allow-private-kraken-prices", result.stdout)


if __name__ == "__main__":
    unittest.main()
