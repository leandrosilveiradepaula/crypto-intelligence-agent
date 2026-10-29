"""WU46: additive observed identity registry, strictly no synthetic Top50 admission."""
from pathlib import Path
import json
import unittest

from crypto_intelligence_agent.crypto_asset_registry import (
    CryptoRegistryHistory, load_registry_json, registry_sha256,
)
from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.research_registry_catalog import (
    REGISTRY_VARIANTS, load_reviewed_registry,
)

ROOT = Path(__file__).resolve().parent.parent / "registries"
V2 = ROOT / "crypto-bases-10-20261025-v2.json"
V3 = ROOT / "crypto-bases-13-20261026-v3.json"
T = 1792982418000


class ExpandedThirteenIdentityTests(unittest.TestCase):
    def test_digest_sources_and_old_evidence_are_immutable(self):
        prior = load_registry_json(V2.read_bytes())
        current = load_registry_json(V3.read_bytes())
        self.assertEqual(current.assets[:10], prior.assets)
        self.assertEqual(len(current.assets), 13)
        self.assertEqual(current.observed_at_ms, T)
        self.assertEqual(current.sha256_digest,
                         "6b4d1de3d0d7519a3f08470b487b062cc216e3586873553b1a7029d32e6aa12b")
        self.assertEqual({x.base for x in current.assets[10:]}, {"XMR", "ETC", "ZEC"})
        for asset in current.assets[10:]:
            self.assertEqual(len({e.publisher_root for e in asset.evidence}), 2)
            self.assertEqual(asset.reviewed_at_ms, T)
            self.assertTrue(all(e.observed_at_ms == T for e in asset.evidence))
            self.assertTrue(all("kraken.com" not in e.url for e in asset.evidence))
        obj = json.loads(V3.read_text(encoding="utf-8"))
        digest = obj.pop("sha256")
        self.assertEqual(registry_sha256(obj), digest)

    def test_replay_prior_identity_without_future_injection(self):
        self.assertEqual(REGISTRY_VARIANTS, frozenset({"btc-eth", "expanded-10", "expanded-13", "expanded-52"}))
        old = load_reviewed_registry("expanded-10", as_of_ms=T)
        fresh = load_reviewed_registry("expanded-13", as_of_ms=T)
        self.assertEqual(len(old.assets), 10)
        self.assertEqual(len(fresh.assets), 13)
        self.assertEqual(load_reviewed_registry("btc-eth", as_of_ms=T).verified_crypto_bases,
                         frozenset({"BTC", "ETH"}))
        with self.assertRaises(DataValidationError):
            load_reviewed_registry("expanded-13", as_of_ms=T - 1)
        with self.assertRaises(DataValidationError):
            load_reviewed_registry("expanded-13", as_of_ms=T + 8 * 86_400_000)
        history = CryptoRegistryHistory((
            load_reviewed_registry("btc-eth", as_of_ms=T),
            old, fresh,
        ))
        self.assertEqual(history.as_of(T - 1, max_age_ms=7 * 86_400_000), old)
        self.assertEqual(history.as_of(T, max_age_ms=0), fresh)

    def test_no_crypto_instrument_or_real_market_rights_follow_from_registry(self):
        reg = load_reviewed_registry("expanded-13", as_of_ms=T)
        snapshot = CryptoRegistryHistory((reg,)).select_at(
            instruments=[], tickers=[], market_observed_at_ms=T,
            decision_at_ms=T, max_market_age_ms=0, max_registry_age_ms=0,
        )
        self.assertEqual(snapshot.eligible, ())
        self.assertEqual(len(reg.assets), 13)
        for bad in ("expanded-50", "arbitrary", ""):
            with self.assertRaises(DataValidationError):
                load_reviewed_registry(bad, as_of_ms=T)


if __name__ == "__main__":
    unittest.main()
