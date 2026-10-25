"""Kraken research selector: crypto-only evidence required and no public calls."""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
import unittest

from crypto_intelligence_agent.kraken_eligibility import (
    RESEARCH_SOURCE, select_kraken_research_universe,
)
from crypto_intelligence_agent.market_data import DataValidationError


OBSERVED = 1_792_934_600_000


def instrument(symbol: str, base: str, *,
               category=None, tradfi=False, tradeable=True, suspended=False):
    return {
        "symbol": symbol, "base": base, "quote": "USD",
        "pair": f"{base}:USD", "type": "flexible_futures",
        "tradfi": tradfi, "category": category,
        "tradeable": tradeable, "suspended": suspended,
        "contractSize": 1, "tickSize": "0.5", "isExpired": False,
    }


def ticker(symbol: str, volume: str, *,
           tag="perpetual", suspended=False, post_only=False, pair=None):
    return {
        "symbol": symbol, "tag": tag, "suspended": suspended,
        "postOnly": post_only, "volumeQuote": volume,
        **({"pair": pair} if pair is not None else {}),
    }


class KrakenEligibilityTests(unittest.TestCase):
    def setUp(self):
        self.instruments = [
            instrument("PF_XBTUSD", "BTC"),
            instrument("PF_ETHUSD", "ETH"),
            instrument("PF_AAPLXUSD", "AAPLx", category="xStocks", tradfi=False),
        ]
        self.tickers = [
            ticker("PF_XBTUSD", "331016603.1374"),
            ticker("PF_ETHUSD", "400000000.00"),
            ticker("PF_AAPLXUSD", "900000000.00"),
        ]

    def select(self, *, bases=frozenset({"BTC", "ETH"}), max_symbols=50,
               contracts=None, tickers=None, observed=OBSERVED):
        return select_kraken_research_universe(
            instruments=self.instruments if contracts is None else contracts,
            tickers=self.tickers if tickers is None else tickers,
            observed_at_ms=observed,
            verified_crypto_bases=bases,
            registry_version="research-asset-registry-fixture-v1",
            max_symbols=max_symbols,
        )

    def test_crypto_only_dynamic_volume_rank_rejects_tokenized_equity(self):
        snapshot = self.select()
        self.assertEqual(snapshot.source, RESEARCH_SOURCE)
        self.assertEqual(snapshot.observed_at_ms, OBSERVED)
        self.assertEqual(snapshot.selection_rule_version,
                         "kraken-verified-crypto-v1:research-asset-registry-fixture-v1")
        self.assertEqual([m.symbol for m in snapshot.eligible], ["PF_ETHUSD", "PF_XBTUSD"])
        self.assertEqual([m.rank for m in snapshot.eligible], [1, 2])
        self.assertEqual([m.quote_volume for m in snapshot.eligible],
                         [Decimal("400000000.00"), Decimal("331016603.1374")])
        self.assertEqual(snapshot.excluded["PF_AAPLXUSD"], "non_crypto_category")

    def test_tradfi_false_is_not_crypto_proof_even_if_stock_listed_in_registry(self):
        snapshot = self.select(bases=frozenset({"BTC", "ETH", "AAPLX"}))
        self.assertNotIn("PF_AAPLXUSD", [m.symbol for m in snapshot.eligible])
        self.assertEqual(snapshot.excluded["PF_AAPLXUSD"], "non_crypto_category")

    def test_top_rank_dynamic_without_fixed_target_number(self):
        snapshot = self.select(max_symbols=1)
        self.assertEqual([m.symbol for m in snapshot.eligible], ["PF_ETHUSD"])
        self.assertEqual(snapshot.excluded["PF_XBTUSD"], "below_dynamic_quote_volume_rank")

    def test_absent_registry_rejected_instead_of_misleading_top50(self):
        for bad in (frozenset(), None, {"BTC"}, frozenset({"BTC", "AAPLx"})):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    self.select(bases=bad)

    def test_timestamp_and_configuration_are_strict(self):
        for value in (-1, True, 1.5, "123"):
            with self.subTest(observed=value):
                with self.assertRaises(ValueError):
                    self.select(observed=value)
        for number in (0, -1, 51, 1.5, True):
            with self.subTest(max_symbols=number):
                with self.assertRaises(ValueError):
                    self.select(max_symbols=number)

    def test_binary_floats_are_rejected_for_exact_financial_fields(self):
        for field, value in (
            ("volumeQuote", 123.4567890123456789),
            ("volumeQuote", float("nan")),
            ("volumeQuote", True),
        ):
            with self.subTest(field=field, value=value):
                tickers = deepcopy(self.tickers)
                tickers[0][field] = value
                snapshot = self.select(tickers=tickers)
                self.assertNotIn("PF_XBTUSD", [m.symbol for m in snapshot.eligible])
                self.assertEqual(snapshot.excluded["PF_XBTUSD"],
                                 "invalid_quote_volume")
        for contract_field in ("tickSize", "contractSize"):
            with self.subTest(contract_field=contract_field):
                instruments = deepcopy(self.instruments)
                instruments[0][contract_field] = 0.5
                snapshot = self.select(contracts=instruments)
                self.assertEqual(snapshot.excluded["PF_XBTUSD"],
                                 "invalid_contract_precision")

    def test_exact_decimal_volume_from_raw_json_outranks_without_rounding(self):
        from crypto_intelligence_agent.decimal_json import decode_public_market_json_exact
        raw = (
            '{"tickers":['
            '{"symbol":"PF_XBTUSD","tag":"perpetual","suspended":false,'
            '"postOnly":false,"volumeQuote":1000.000000000000000002},'
            '{"symbol":"PF_ETHUSD","tag":"perpetual","suspended":false,'
            '"postOnly":false,"volumeQuote":1000.000000000000000001}'
            ']}'
        )
        decoded = decode_public_market_json_exact(raw)
        snapshot = self.select(tickers=decoded["tickers"])
        self.assertEqual([m.symbol for m in snapshot.eligible],
                         ["PF_XBTUSD", "PF_ETHUSD"])
        self.assertEqual(snapshot.eligible[0].quote_volume,
                         Decimal("1000.000000000000000002"))
        self.assertEqual(snapshot.eligible[1].quote_volume,
                         Decimal("1000.000000000000000001"))

    def test_missing_quote_volume_never_enters_ranking(self):
        tickers = [ticker("PF_XBTUSD", "Infinity"), ticker("PF_ETHUSD", "0")]
        snapshot = self.select(tickers=tickers)
        self.assertEqual(snapshot.eligible, ())
        self.assertEqual(snapshot.excluded["PF_XBTUSD"], "invalid_quote_volume")
        self.assertEqual(snapshot.excluded["PF_ETHUSD"], "invalid_quote_volume")

    def test_only_positive_finite_decimal_quote_volume_is_used(self):
        tickers = [
            ticker("PF_XBTUSD", "0.00000003"),
            ticker("PF_ETHUSD", "0.00000004"),
        ]
        result = self.select(tickers=tickers)
        self.assertEqual(result.eligible[0].quote_volume, Decimal("0.00000004"))
        self.assertEqual(result.eligible[1].quote_volume, Decimal("0.00000003"))

    def test_untrusted_unknown_base_is_excluded_even_with_crypto_category(self):
        contracts = [instrument("PF_NEWUSD", "NEW", category="DeFi")]
        t = [ticker("PF_NEWUSD", "9999999999")]
        result = self.select(contracts=contracts, tickers=t)
        self.assertEqual(result.eligible, ())
        self.assertEqual(result.excluded["PF_NEWUSD"], "base_not_verified_crypto")

    def test_missing_ticker_and_false_perpetual_tag_are_excluded(self):
        result = self.select(tickers=[ticker("PF_XBTUSD", "200", tag="dated")])
        self.assertEqual(result.eligible, ())
        self.assertEqual(result.excluded["PF_XBTUSD"], "ticker_not_perpetual")
        self.assertEqual(result.excluded["PF_ETHUSD"], "missing_current_ticker")

    def test_ticker_and_contract_statuses_are_respected(self):
        changed = deepcopy(self.instruments)
        changed[0]["tradeable"] = False
        changed[1]["suspended"] = True
        result = self.select(contracts=changed)
        self.assertEqual(result.eligible, ())
        self.assertEqual(result.excluded["PF_XBTUSD"], "not_actively_tradeable")
        self.assertEqual(result.excluded["PF_ETHUSD"], "not_actively_tradeable")

    def test_bad_quoting_precision_or_ticker_flags_fail_closed(self):
        changed = deepcopy(self.instruments)
        changed[0]["tickSize"] = "0"
        changed[1]["pair"] = "ETH:USDT"
        result = self.select(contracts=changed)
        self.assertEqual(result.excluded["PF_XBTUSD"], "invalid_contract_precision")
        self.assertEqual(result.excluded["PF_ETHUSD"], "not_comparable_usd_quote")
        result2 = self.select(tickers=[
            ticker("PF_XBTUSD", "123", post_only=True),
            ticker("PF_ETHUSD", "123", pair="OTHER:USD"),
        ])
        self.assertEqual(result2.excluded["PF_XBTUSD"], "ticker_not_actively_tradeable")
        self.assertEqual(result2.excluded["PF_ETHUSD"], "ticker_pair_mismatch")

    def test_duplicate_conflicts_fail_entire_snapshot(self):
        changed = deepcopy(self.instruments)
        changed.append({**changed[0], "tickSize": 100})
        with self.assertRaises(DataValidationError):
            self.select(contracts=changed)
        with self.assertRaises(DataValidationError):
            self.select(tickers=self.tickers + [ticker("PF_XBTUSD", "999")])

    def test_identical_duplicates_are_idempotently_normalized(self):
        snapshot1 = self.select()
        snapshot2 = self.select(
            contracts=self.instruments + [deepcopy(self.instruments[0])],
            tickers=self.tickers + [deepcopy(self.tickers[0])],
        )
        self.assertEqual(snapshot1, snapshot2)


if __name__ == "__main__":
    unittest.main()
