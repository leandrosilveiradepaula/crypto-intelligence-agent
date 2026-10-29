"""J1 #319: opt-in 52-base registry, historical PIT causality unchanged.

No network is contacted by this suite. External independent publisher URLs
are reviewed references, not a licensed exchange feed or trading permission.
"""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from crypto_intelligence_agent.crypto_asset_registry import (
    CryptoRegistryHistory, load_registry_json, registry_sha256,
)
from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.research_registry_catalog import (
    REGISTRY_VARIANTS, load_reviewed_registry,
)
from crypto_intelligence_agent.bybit_paginated_universe_research import (
    scan_bybit_linear_instruments_offline,
)
from test_bybit_paginated_universe_research import instrument_page, instrument_row

ROOT = Path(__file__).resolve().parent.parent / "registries"
OLD = ROOT / "crypto-bases-13-20261026-v3.json"
NEW = ROOT / "crypto-bases-52-20261029-v4.json"
AT = 1793287659000
SHA = "810e90d6fb24a3f4e7a6f402efa67abf71eb2e45a328bdfabcc7104d12537f30"

EXPECTED_39 = frozenset((
    "HYPE NEAR ENA SUI WLD INIT BNB AAVE UNI ONDO ZRO BCH BLUR "
    "INJ ARB TAO TIA STRK XLM QNT APT HBAR OP PENGU MNT FIL CRV "
    "SAND AERO ICP SEI JASMY DASH STX LDO PYTH JUP VIRTUAL TRX"
).split())


class ReviewedFiftyTwoCryptoIdentitiesTests(unittest.TestCase):
    def test_append_only_manifest_integrity_and_independent_review_publishers(self):
        previous = load_registry_json(OLD.read_bytes())
        expanded = load_registry_json(NEW.read_bytes())
        self.assertEqual(len(previous.assets), 13)
        self.assertEqual(len(expanded.assets), 52)
        self.assertEqual(expanded.assets[:13], previous.assets)
        self.assertEqual(expanded.observed_at_ms, AT)
        self.assertEqual(expanded.sha256_digest, SHA)
        self.assertEqual(
            {a.base for a in expanded.assets[13:]}, EXPECTED_39)
        self.assertEqual(expanded.verified_crypto_bases,
                         previous.verified_crypto_bases | EXPECTED_39)
        for asset in expanded.assets[13:]:
            with self.subTest(base=asset.base):
                self.assertEqual(asset.reviewed_at_ms, AT)
                self.assertEqual(asset.reviewed_by, "assistant-technical-review")
                self.assertTrue(all(e.observed_at_ms == AT for e in asset.evidence))
                self.assertGreaterEqual(len({e.publisher_root for e in asset.evidence}), 2)
                self.assertIn("coingecko", {e.publisher for e in asset.evidence})
                self.assertIn("coinmarketcap", {e.publisher for e in asset.evidence})
                self.assertTrue(all("kraken.com" not in e.url for e in asset.evidence))
        raw = json.loads(NEW.read_text(encoding="utf-8"))
        actual = raw.pop("sha256")
        self.assertEqual(registry_sha256(raw), actual)
        self.assertEqual(actual, SHA)

    def test_no_scaled_asset_or_tokenized_gold_or_ambiguous_symbol_promotion(self):
        current = load_reviewed_registry("expanded-52", as_of_ms=AT)
        self.assertTrue({"NEAR", "HYPE", "SUI", "BNB", "UNI"} <=
                        current.verified_crypto_bases)
        self.assertFalse({
            "1000PEPE", "1000BONK", "XAUT", "LIT", "AKE",
            "PONS", "XPLUS", "AAPL", "PUMPFUN"
        } & current.verified_crypto_bases)
        self.assertEqual(len(current.assets), 52)

    def test_backdating_old_three_pits_is_impossible(self):
        self.assertIn("expanded-52", REGISTRY_VARIANTS)
        earlier = load_reviewed_registry("expanded-13", as_of_ms=AT)
        future = load_reviewed_registry("expanded-52", as_of_ms=AT)
        self.assertEqual(len(earlier.assets), 13)
        self.assertEqual(len(future.assets), 52)
        self.assertEqual(
            earlier.sha256_digest,
            "6b4d1de3d0d7519a3f08470b487b062cc216e3586873553b1a7029d32e6aa12b",
        )
        with self.assertRaises(DataValidationError):
            load_reviewed_registry("expanded-52", as_of_ms=AT - 1)
        with self.assertRaises(DataValidationError):
            load_reviewed_registry("expanded-52", as_of_ms=AT + 8 * 86_400_000)
        history = CryptoRegistryHistory([earlier, future])
        self.assertEqual(history.as_of(AT-1, max_age_ms=86_400_000),
                         earlier)
        self.assertEqual(history.as_of(AT, max_age_ms=0), future)
        # No historical database is migrated or rewritten by this registry.

    def test_new_candidates_are_seen_only_if_new_revision_explicitly_selected(self):
        pages = (
            instrument_page(
                [instrument_row("NEARUSDT"),
                 instrument_row("HYPEUSDT"),
                 instrument_row("AAPLUSDT", symbolType="tradfi")],
                ms=AT-400, cursor="",
            ),
        )
        params = dict(
            instrument_pages=pages,
            requested_cursors=(None,),
            observed_at_ms=AT,
            page_received_at_ms=(AT-100,),
        )
        prior = scan_bybit_linear_instruments_offline(
            **params, registry_variant="expanded-13",
        )
        later = scan_bybit_linear_instruments_offline(
            **params, registry_variant="expanded-52",
        )
        self.assertEqual(prior.instruments, ())
        self.assertEqual({x.symbol for x in later.instruments},
                         {"HYPEUSDT", "NEARUSDT"})
        self.assertFalse(later.historical_top50_verified)
        self.assertFalse(later.rights_authorized)

    def test_tamper_append_evidence_is_detected(self):
        raw = json.loads(NEW.read_text(encoding="utf-8"))
        tampered = deepcopy(raw)
        tampered["assets"][-1]["evidence"][0]["url"] = (
            "https://www.coingecko.com/en/coins/fake-mismatched")
        with self.assertRaisesRegex(DataValidationError, "hash"):
            load_registry_json(json.dumps(tampered))
        tampered = deepcopy(raw)
        tampered["assets"][-1]["evidence"][1]["publisher"] = "coingecko"
        with self.assertRaises(DataValidationError):
            load_registry_json(json.dumps(tampered))


if __name__ == "__main__":
    unittest.main()
