"""WU37 - real ten-asset identity evidence and point-in-time Kraken selector.

Public links are *references*, not raw market feed imports, trading approvals,
human certifications or licenses. No HTTP requests are made by these tests.
"""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import json
from pathlib import Path
import unittest

from crypto_intelligence_agent.crypto_asset_registry import (
    CryptoRegistryHistory, load_registry_json, registry_sha256,
)
from crypto_intelligence_agent.kraken_public_readonly import KrakenCurrentResearchSnapshot
from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.research_registry_catalog import (
    REGISTRY_VARIANTS, load_reviewed_registry,
)
from scripts.probe_kraken_btc_eth_universe import UniverseProbeError, inspect_once

ROOT = Path(__file__).resolve().parent.parent / "registries"
V1 = ROOT / "crypto-btc-eth-20261025-v1.json"
V2 = ROOT / "crypto-bases-10-20261025-v2.json"
BASES = frozenset({"BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "LTC",
                   "AVAX", "LINK", "DOT"})
T = 1792968148000
HOUR = 3_600_000


def instrument(base: str, *, symbol: str | None = None,
               category: str | None = None, pair: str | None = None):
    s = symbol or f"PF_{base}USD"
    return {
        "symbol": s, "base": base, "quote": "USD",
        "pair": pair or f"{base}:USD",
        "type": "flexible_futures", "tradfi": False,
        "tradeable": True, "suspended": False, "isExpired": False,
        "category": category, "tickSize": "0.1", "contractSize": "1",
    }


def ticker(symbol: str, volume: Decimal):
    return {"symbol": symbol, "tag": "perpetual",
            "suspended": False, "postOnly": False, "volumeQuote": volume}


def current_sample(*, at: int):
    # Synthetic venue rows, NOT an assertion that these contracts exist live.
    rows = [instrument("BTC", symbol="PF_XBTUSD", pair="XBT:USD")]
    rows += [instrument(base) for base in
             ("ETH", "SOL", "XRP", "ADA", "DOGE", "LTC", "AVAX", "LINK", "DOT")]
    rows += [instrument("AAPLX", category="Tokenized Equities"),
             instrument("PEPE"),
             instrument("BTC", symbol="PF_TSLAUSD", pair="BTC:USD")]
    quotes = [Decimal("1000.012345678901234567") + Decimal(idx)
              for idx in range(10)]
    tickers = [
        ticker(row["symbol"], volume)
        for row, volume in zip(rows[:10], quotes)
    ]
    tickers += [
        ticker("PF_AAPLXUSD", Decimal("99999999999999")),
        ticker("PF_PEPEUSD", Decimal("88888888888888")),
    ]
    return KrakenCurrentResearchSnapshot(
        captured_start_ms=at + 5, captured_end_ms=at + 30,
        instruments=tuple(rows), tickers=tuple(tickers),
    )


class FakeReader:
    def __init__(self, sample):
        self.value = sample
        self.calls = 0

    def current_market_snapshot(self):
        self.calls += 1
        return self.value


class ExpandedRegistryTests(unittest.TestCase):
    def test_signed_manifest_has_exactly_ten_and_preserves_old_evidence(self):
        old = load_registry_json(V1.read_bytes())
        current = load_registry_json(V2.read_bytes())
        self.assertEqual(current.verified_crypto_bases, BASES)
        self.assertEqual(len(current.assets), 10)
        self.assertEqual(current.observed_at_ms, T)
        self.assertEqual(current.label, "crypto-bases-10-20261025-review-v2")
        self.assertEqual(current.sha256_digest,
                         "a95179a342289833f3b14f0c2442163acdcb32f1ca0c9569fa01adeaa3534746")
        self.assertEqual(current.assets[:2], old.assets)
        for item in current.assets[2:]:
            with self.subTest(base=item.base):
                self.assertEqual(item.reviewed_by, "assistant-technical-review")
                self.assertEqual(item.reviewed_at_ms, T)
                self.assertEqual({e.observed_at_ms for e in item.evidence}, {T})
                self.assertEqual(len({e.publisher_root for e in item.evidence}), 2)
                self.assertEqual(len({e.publisher for e in item.evidence}), 2)
                self.assertTrue(all(e.url.startswith("https://") for e in item.evidence))
                self.assertIn("coingecko", {e.publisher for e in item.evidence})
                self.assertNotIn("kraken.com", {e.publisher_root for e in item.evidence})
        unsigned = json.loads(V2.read_text(encoding="utf-8"))
        hash_value = unsigned.pop("sha256")
        self.assertEqual(registry_sha256(unsigned), hash_value)
        self.assertEqual(current.sha256_digest, hash_value)

    def test_history_preserves_point_in_time_and_old_version(self):
        first = load_registry_json(V1.read_bytes())
        expanded = load_registry_json(V2.read_bytes())
        history = CryptoRegistryHistory([first, expanded])
        self.assertEqual(
            history.as_of(T - 1, max_age_ms=7 * 86_400_000),
            first)
        self.assertEqual(history.as_of(T, max_age_ms=0), expanded)
        self.assertEqual(load_reviewed_registry("btc-eth", as_of_ms=T),
                         first)
        self.assertEqual(load_reviewed_registry("expanded-10", as_of_ms=T),
                         expanded)
        with self.assertRaises(DataValidationError):
            load_reviewed_registry("expanded-10", as_of_ms=T - 1)
        with self.assertRaises(DataValidationError):
            load_reviewed_registry("expanded-10", as_of_ms=T + 8 * 86_400_000)
        for bad in ("default", "", "v2.json", None, 2, True):
            with self.subTest(variant=bad), self.assertRaises(DataValidationError):
                load_reviewed_registry(bad, as_of_ms=T)
        self.assertEqual(REGISTRY_VARIANTS, frozenset({"btc-eth", "expanded-10", "expanded-13", "expanded-52"}))

    def test_hash_tamper_rejected_instead_of_silently_reidentifying(self):
        raw = json.loads(V2.read_text(encoding="utf-8"))
        for field, new_value in (("base", "AAPLX"),
                                 ("canonical_id", "fake-asset"),
                                 ("reviewed_by", "fake-auditor")):
            tampered = json.loads(json.dumps(raw))
            tampered["assets"][4][field] = new_value
            with self.subTest(field=field), self.assertRaises(DataValidationError):
                load_registry_json(json.dumps(tampered))
        raw["assets"][2]["evidence"][1]["url"] = "https://solana.com/learn/what-is-solana"
        with self.assertRaises(DataValidationError):
            load_registry_json(json.dumps(raw))

    def test_ten_crypto_bases_do_not_promote_tokenized_stock_or_unknown(self):
        now = T + 60_000
        result = inspect_once(
            allow_public_network=True, allow_private_kraken_universe=True,
            registry_variant="expanded-10",
            client=FakeReader(current_sample(at=now)),
            clock_ms=iter([now, now + 40]).__next__,
        )
        self.assertEqual(result["status"], "private_current_universe_validated")
        self.assertEqual(result["registry_bases_count"], 10)
        self.assertEqual(result["eligible_contracts_count"], 10)
        self.assertEqual(result["excluded_contracts_count"], 3)
        self.assertEqual(result["schema_version"], "j1-kraken-private-universe-v2")
        self.assertTrue(result["ephemeral_sqlite_roundtrip"])
        self.assertFalse(result["historical_top50_approved"])
        self.assertFalse(result["canonical_ohlcv_approved"])
        self.assertFalse(result["ready_for_trading"])
        self.assertFalse(result["commercial_or_public_rights_verified"])
        self.assertEqual(result["max_gets"], 2)
        self.assertNotIn("1000.012345678901234567", json.dumps(result))
        self.assertNotIn("PF_AAPLXUSD", json.dumps(result))
        self.assertNotIn("PF_SOLUSD", json.dumps(result))

    def test_v1_same_market_caps_at_two_identities(self):
        now = T + 60_000
        result = inspect_once(
            allow_public_network=True, allow_private_kraken_universe=True,
            registry_variant="btc-eth",
            client=FakeReader(current_sample(at=now)),
            clock_ms=iter([now, now + 40]).__next__,
        )
        self.assertEqual(result["registry_bases_count"], 2)
        self.assertEqual(result["eligible_contracts_count"], 2)
        self.assertEqual(result["excluded_contracts_count"], 11)

    def test_ask_v2_before_it_existed_never_calls_exchange(self):
        old_time = T - 1000
        reader = FakeReader(current_sample(at=T + HOUR))
        with self.assertRaises(UniverseProbeError):
            inspect_once(
                allow_public_network=True, allow_private_kraken_universe=True,
                registry_variant="expanded-10",
                client=reader, clock_ms=lambda: old_time,
            )
        self.assertEqual(reader.calls, 0)

    def test_forged_symbol_cannot_reuse_trusted_sol_registry(self):
        current = load_reviewed_registry("expanded-10", as_of_ms=T)
        history = CryptoRegistryHistory((current,))
        now = T + 60_000
        ranked = history.select_at(
            instruments=[
                instrument("SOL", symbol="PF_AAPLXUSD", pair="SOL:USD"),
                instrument("SOL", symbol="PF_SOLUSD", category="X-STOCKS"),
            ],
            tickers=[ticker("PF_AAPLXUSD", Decimal("999999999")),
                     ticker("PF_SOLUSD", Decimal("400"))],
            market_observed_at_ms=now, decision_at_ms=now,
            max_market_age_ms=0, max_registry_age_ms=86_400_000,
        )
        self.assertEqual([x.symbol for x in ranked.eligible], [])
        self.assertEqual(ranked.excluded["PF_AAPLXUSD"], "symbol_base_mismatch")
        self.assertEqual(ranked.excluded["PF_SOLUSD"], "non_crypto_category")


if __name__ == "__main__":
    unittest.main()
