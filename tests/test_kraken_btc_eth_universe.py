"""J1/WU35: real registry seed + fake current Kraken market, offline only."""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import subprocess
import sys
import unittest

from crypto_intelligence_agent.crypto_asset_registry import load_registry_json
from crypto_intelligence_agent.kraken_public_readonly import (
    KrakenCurrentResearchSnapshot, SOURCE,
)
from crypto_intelligence_agent.market_data import ExchangeAccessError
from scripts.probe_kraken_btc_eth_universe import (
    REGISTRY_PATH, MAX_CAPTURE_AGE_MS, UniverseProbeError, inspect_once,
)

REGISTRY = load_registry_json(REGISTRY_PATH.read_bytes())
T = REGISTRY.observed_at_ms + 60_000


def contract(symbol, base, *, category=None, pair=None):
    return {
        "symbol": symbol, "base": base, "quote": "USD", "pair": pair or f"{base}:USD",
        "type": "flexible_futures", "tradeable": True, "suspended": False,
        "isExpired": False, "tradfi": False, "category": category,
        "contractSize": "1", "tickSize": "0.5",
    }


def ticker(symbol, quote_volume):
    return {"symbol": symbol, "tag": "perpetual", "postOnly": False,
            "suspended": False, "volumeQuote": quote_volume}


def sample(*, start=T + 5, end=T + 30, forged=False, only_equity=False):
    instruments = [
        contract("PF_XBTUSD", "BTC", pair="XBT:USD"),
        contract("PF_ETHUSD", "ETH"),
        contract("PF_AAPLXUSD", "AAPLX", category="xStocks"),
    ]
    if forged:
        instruments[0] = contract("PF_XBTUSD", "AAPLX", pair="AAPLX:USD")
    if only_equity:
        instruments = [instruments[-1]]
    tickers = [
        ticker("PF_XBTUSD", Decimal("150000000.010000001")),
        ticker("PF_ETHUSD", Decimal("90000000.3")),
        ticker("PF_AAPLXUSD", Decimal("99999999999")),
    ]
    return KrakenCurrentResearchSnapshot(
        captured_start_ms=start, captured_end_ms=end,
        instruments=tuple(instruments), tickers=tuple(tickers),
    )


class FakeReader:
    def __init__(self, response=None, *, error=None):
        self.calls = 0
        self.response = sample() if response is None else response
        self.error = error

    def current_market_snapshot(self):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.response


def run(reader, *, start=T, decide=T + 40, registry_data=None):
    clocks = iter((start, decide))
    return inspect_once(
        allow_public_network=True, allow_private_kraken_universe=True,
        client=reader, clock_ms=lambda: next(clocks), registry_data=registry_data,
    )


class RealSeedCurrentMarketTests(unittest.TestCase):
    def test_private_snapshot_selects_only_btc_eth_despite_tokenized_volume(self):
        reader = FakeReader()
        result = run(reader)
        self.assertEqual(result["status"], "private_current_universe_validated")
        self.assertEqual(reader.calls, 1)
        self.assertEqual(result["requests_attempted_exact"], 2)
        self.assertEqual(result["registry_sha256"], REGISTRY.sha256_digest)
        self.assertEqual(result["registry_bases_count"], 2)
        self.assertEqual(result["eligible_contracts_count"], 2)
        self.assertEqual(result["ranking_quote_currency"], "USD")
        self.assertTrue(result["ephemeral_sqlite_roundtrip"])
        self.assertFalse(result["historical_top50_approved"])
        self.assertFalse(result["commercial_or_public_rights_verified"])
        self.assertFalse(result["canonical_ohlcv_approved"])
        self.assertFalse(result["market_data_published"])
        self.assertFalse(result["retained_market_data_after_run"])
        self.assertFalse(result["orders_sent"])
        self.assertNotIn("150000000.010000001", json.dumps(result))
        self.assertNotIn("99999999999", json.dumps(result))
        self.assertNotIn("PF_AAPLXUSD", json.dumps(result))

    def test_forged_base_does_not_borrow_btc_identity(self):
        bad = FakeReader(response=sample(forged=True))
        result = run(bad)
        self.assertEqual(result["status"], "private_current_universe_validated")
        self.assertEqual(result["eligible_contracts_count"], 1)

    def test_no_eligible_contract_is_explicit_failure_not_fake_top50(self):
        reader = FakeReader(response=sample(only_equity=True))
        result = run(reader)
        self.assertEqual(result["status"], "no_eligible_crypto_contracts_in_current_sample")
        self.assertEqual(result["eligible_contracts_count"], 0)
        self.assertFalse(result["historical_top50_approved"])

    def test_do_not_call_network_without_both_optins(self):
        reader = FakeReader()
        for a, b in ((False, False), (True, False), (False, True)):
            with self.subTest(a=a, b=b), self.assertRaises(UniverseProbeError):
                inspect_once(allow_public_network=a,
                             allow_private_kraken_universe=b, client=reader,
                             clock_ms=lambda: T)
        self.assertEqual(reader.calls, 0)

    def test_restricted_public_feed_does_not_retry(self):
        reader = FakeReader(error=ExchangeAccessError("HTTP451"))
        result = run(reader)
        self.assertEqual(result["status"], "access_restricted_no_retry")
        self.assertIsNone(result["requests_attempted_exact"])
        self.assertEqual(result["max_gets"], 2)
        self.assertEqual(reader.calls, 1)

    def test_registry_cannot_approve_historical_market_before_its_birth(self):
        reader = FakeReader()
        with self.assertRaises(UniverseProbeError):
            run(reader, start=REGISTRY.observed_at_ms - 1)
        self.assertEqual(reader.calls, 0)

    def test_stale_registry_fails_closed_without_renewal(self):
        now = REGISTRY.observed_at_ms + 8 * 86_400_000
        reader = FakeReader(response=sample(start=now + 5, end=now + 30))
        result = run(reader, start=now, decide=now + 40)
        self.assertEqual(result["status"], "market_metadata_or_registry_validation_rejected")

    def test_clock_regression_and_old_capture_fail_without_sqlite(self):
        for original in (
            sample(start=T - 1, end=T + 30),
            sample(start=T + 5, end=T + MAX_CAPTURE_AGE_MS + 1),
        ):
            with self.subTest(kind=original.captured_start_ms):
                result = run(FakeReader(response=original))
                self.assertEqual(result["status"], "invalid_live_capture_timing_or_source")
        result = run(FakeReader(), start=T, decide=T + 10)
        self.assertEqual(result["status"], "invalid_decision_clock")

    def test_wrong_source_rejected(self):
        from dataclasses import replace
        wrong = replace(sample(), source="untrusted_exchange")
        self.assertEqual(
            run(FakeReader(response=wrong))["status"],
            "invalid_live_capture_timing_or_source",
        )

    def test_owner_only_module_entrypoint_imports_offline(self):
        root = Path(__file__).resolve().parent.parent
        run_help = subprocess.run(
            [sys.executable, "-m", "scripts.probe_kraken_btc_eth_universe", "--help"],
            cwd=root, text=True, capture_output=True, timeout=10, check=False,
        )
        self.assertEqual(run_help.returncode, 0, run_help.stderr)
        self.assertIn("--allow-private-kraken-universe", run_help.stdout)


if __name__ == "__main__":
    unittest.main()
