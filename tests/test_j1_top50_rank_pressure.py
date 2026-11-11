"""J1/#319: Top50 ranking pressure uses synthetic 24h totals only."""
from decimal import Decimal
import unittest

from crypto_intelligence_agent.j1_top50_rank_pressure import (
    Top50PressureRejected, pressure_from_closed_turnover,
)


def sample(*, unknown_high: bool = False, missing: bool = False):
    reviewed = [f"C{i:03d}USDT" for i in range(50)]
    unknown = ["U000USDT", "U001USDT"]
    excluded = ["STKUSDT"]
    catalog = reviewed + unknown + excluded
    amounts = {s: str(1000 - i * 10) for i, s in enumerate(reviewed)}
    amounts["U000USDT"] = "900.00" if unknown_high else "1"
    amounts["U001USDT"] = "2"
    if not missing:
        amounts["STKUSDT"] = "999999"
    return catalog, amounts, reviewed, excluded


class Top50PressureTests(unittest.TestCase):
    def run_rank(self, *, catalog=None, amounts=None, reviewed=None,
                 excluded=None, show=False):
        if catalog is None:
            catalog, amounts, reviewed, excluded = sample()
        return pressure_from_closed_turnover(
            catalog_symbols=catalog, closed_turnover_usdt=amounts,
            positively_reviewed_crypto=reviewed,
            independently_excluded_noncrypto=excluded,
            include_public_symbols=show,
        )

    def test_lower_unknown_and_excluded_giant_do_not_displace(self):
        r = self.run_rank(show=True)
        self.assertEqual(r["status"],
                         "conditional_top50_dominance_without_source_authentication")
        self.assertEqual(r["conditional_selected_count"], 50)
        self.assertEqual(r["review_priority_symbols_only"], [])
        self.assertTrue(r["conditional_mathematical_dominance"])
        self.assertFalse(r["marketwide_top50_verified"])
        self.assertFalse(r["source_authenticated"])
        self.assertFalse(r["trading_enabled"])

    def test_high_unresolved_has_priority_but_is_never_automatically_crypto(self):
        c, a, p, n = sample(unknown_high=True)
        r = self.run_rank(catalog=c, amounts=a, reviewed=p, excluded=n, show=True)
        self.assertFalse(r["conditional_mathematical_dominance"])
        self.assertEqual(r["review_priority_symbols_only"], ["U000USDT"])
        self.assertEqual(r["highest_priority_review_count"], 1)

    def test_unmeasured_unknown_is_always_a_blocker(self):
        c, a, p, n = sample()
        del a["U000USDT"]
        r = self.run_rank(catalog=c, amounts=a, reviewed=p, excluded=n, show=True)
        self.assertEqual(r["unresolved_unmeasured_contracts"], 1)
        self.assertEqual(r["unmeasured_unresolved_symbols_only"], ["U000USDT"])
        self.assertFalse(r["conditional_mathematical_dominance"])

    def test_fewer_than_50_positive_prioritizes_remaining_candidates(self):
        c, a, p, n = sample()
        r = self.run_rank(catalog=c, amounts=a, reviewed=p[:49], excluded=n,
                          show=True)
        self.assertEqual(r["additional_crypto_reviews_needed_at_least"], 1)
        self.assertEqual(r["review_priority_symbols_only"], ["C049USDT"])
        self.assertFalse(r["conditional_mathematical_dominance"])

    def test_excluded_instrument_need_not_have_turnover(self):
        c, a, p, n = sample(missing=True)
        r = self.run_rank(catalog=c, amounts=a, reviewed=p, excluded=n)
        self.assertEqual(r["unresolved_unmeasured_contracts"], 0)
        self.assertTrue(r["conditional_mathematical_dominance"])

    def test_equal_turnover_deterministic_tie_is_safely_reviewed(self):
        c, a, p, n = sample()
        a["U000USDT"] = a["C049USDT"]
        r = self.run_rank(catalog=c, amounts=a, reviewed=p, excluded=n,
                          show=True)
        self.assertFalse(r["conditional_mathematical_dominance"])
        self.assertIn("U000USDT", r["review_priority_symbols_only"])

    def test_digest_stable_under_order_permutation_and_decimal_spelling(self):
        c, a, p, n = sample()
        r = self.run_rank(catalog=c, amounts=a, reviewed=p, excluded=n)
        a2 = dict(reversed(list(a.items())))
        r2 = self.run_rank(catalog=list(reversed(c)), amounts=a2,
                           reviewed=list(reversed(p)), excluded=n)
        self.assertEqual(r["conditional_selected_sha256"],
                         r2["conditional_selected_sha256"])

    def test_no_symbol_leak_by_default(self):
        r = self.run_rank()
        data = repr(r)
        self.assertNotIn("C000USDT", data)
        self.assertNotIn("U000USDT", data)
        self.assertNotIn("STKUSDT", data)
        self.assertEqual(r["network_requests"], 0)
        self.assertFalse(r["database_modified"])

    def test_rejects_false_claims_untrusted_money_or_tainted_catalog(self):
        c, a, p, n = sample()
        cases = [
            (c, {**a, "U000USDT": 2.5}, p, n),
            (c, {**a, "U000USDT": "NaN"}, p, n),
            (c, {**a, "U000USDT": "Infinity"}, p, n),
            (c, {**a, "U000USDT": "-1"}, p, n),
            (c, {**a, "U000USDT": "1e309"}, p, n),
            (c, {**a, "U000USDT": Decimal("NaN")}, p, n),
            (c, {**a, "U000USDT": Decimal("-1")}, p, n),
            (c + ["C000USDT"], a, p, n),
            (c, a, p + ["STKUSDT"], n),
            (c, a, p + ["X123USDT"], n),
            (c, {**a, "WRONGUSDT": "2"}, p, n),
            (c, a, p, n + ["U000USDT", "U000USDT"]),
        ]
        for cat, amounts, positive, negative in cases:
            with self.subTest(case=(len(cat), str(amounts.get("U000USDT")))):
                with self.assertRaises(Top50PressureRejected):
                    self.run_rank(catalog=cat, amounts=amounts,
                                  reviewed=positive, excluded=negative)

    def test_never_claims_pit_or_global_verification_for_fixtures(self):
        c, a, p, n = sample()
        for result in (
            self.run_rank(catalog=c, amounts=a, reviewed=p, excluded=n),
            self.run_rank(catalog=c, amounts=a,
                          reviewed=p[:5], excluded=n),
        ):
            self.assertFalse(result["identity_pit_authenticated"])
            self.assertFalse(result["marketwide_top50_verified"])
            self.assertFalse(result["orders_sent"])


if __name__ == "__main__":
    unittest.main()
