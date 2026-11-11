"""D277: retrospective primary venue evidence for incomplete TradFi contracts."""
import dataclasses
import json
import unittest

from crypto_intelligence_agent.j1_short_tradfi_primary import (
    SOURCES, ShortTradfiPrimary, audit_short_tradfi,
)

END = 1793970000000


class D277ShortsTests(unittest.TestCase):
    def run_audit(self, shorts=None, negative=None, show=False):
        return audit_short_tradfi(
            shorts=shorts if shorts is not None else (
                ("DUOLUSDT", 2, 1793956383000),
                ("FISVUSDT", 2, 1793956265000),
                ("FNUSDT", 2, 1793956331000),
            ),
            historical_window_end_ms=END,
            contemporary_negative_symbols=(
                frozenset({"DUOLUSDT", "FISVUSDT", "FNUSDT"})
                if negative is None else negative
            ),
            include_private_symbols=show,
        )

    def test_real_short_shapes_are_research_only(self):
        p = self.run_audit(show=True)
        self.assertEqual(p["short_census_contracts"], 3)
        self.assertEqual(p["short_observed_candles"], 6)
        self.assertEqual(p["shorts_with_venue_primary_tradfi_documentation"], 3)
        self.assertEqual(p["documented_shorts_matching_later_negative_indicator"], 3)
        self.assertEqual(p["undocumented_shorts_still_possible_crypto_rivals"], 0)
        self.assertEqual(p["primary_publisher_count"], 1)
        self.assertEqual(
            [r["symbol"] for r in p["documented_short_contracts_only"]],
            ["DUOLUSDT", "FISVUSDT", "FNUSDT"],
        )
        self.assertEqual(
            [r["underlying_equity"] for r in p["documented_short_contracts_only"]],
            ["Duolingo", "Fiserv", "Fabrinet"],
        )
        for flag in ("historical_provider_identity_pit_authenticated",
                     "all_short_rivals_independently_disqualified_pit",
                     "marketwide_top50_verified", "trading_enabled", "orders_sent",
                     "database_modified"):
            self.assertFalse(p[flag])
        self.assertEqual(p["network_requests"], 0)

    def test_unrecognized_short_never_automatically_disqualified(self):
        r = self.run_audit(
            shorts=(("UNKNOWNUSDT", 0, None), ("DUOLUSDT", 2, None)),
            negative=frozenset(),
            show=True,
        )
        self.assertEqual(r["undocumented_shorts_still_possible_crypto_rivals"], 1)
        self.assertEqual(r["documented_shorts_matching_later_negative_indicator"], 0)
        self.assertEqual(r["undocumented_short_symbols_only"], ["UNKNOWNUSDT"])
        self.assertFalse(r["all_short_rivals_independently_disqualified_pit"])

    def test_default_hides_symbols(self):
        result = self.run_audit()
        self.assertNotIn("documented_short_contracts_only", result)
        self.assertNotIn("undocumented_short_symbols_only", result)
        for sym in SOURCES:
            self.assertNotIn(sym, json.dumps(result))

    def test_fail_closed_bad_short_inputs(self):
        for shorts in (
            [("DUOLUSDT", 2, None)],
            (("DUOLUSDT", 2, None), ("DUOLUSDT", 1, None)),
            (("duolUSDT", 2, None),),
            (("DUOLUSDT", 24, None),),
            (("DUOLUSDT", 2.5, None),),
            (("DUOLUSDT", True, None),),
            (("DUOLUSDT", 2, "2026-11-06"),),
            (("DUOLUSDT", 2, END + 1),),
            (("DUOLUSDT", 2),),
        ):
            with self.subTest(shorts=shorts), self.assertRaises(ValueError):
                self.run_audit(shorts=shorts)
        for neg in ({"DUOLUSDT"}, frozenset({"badusdt"})):
            with self.assertRaises(ValueError):
                self.run_audit(negative=neg)
        for bad in (True, END + 1, 0, "1793970000000"):
            with self.assertRaises(ValueError):
                audit_short_tradfi(
                    shorts=(), historical_window_end_ms=bad,
                    contemporary_negative_symbols=frozenset(),
                )

    def test_bad_primary_source_dates_and_hosts_fail_closed(self):
        row = SOURCES["DUOLUSDT"]
        for changes in (
            {"announcement_url": "https://evil.example/en/article/x"},
            {"announcement_url": row.announcement_url + "?token=secret"},
            {"announcement_url": "https://u:pass@announcements.bybit.com/en/article/x"},
            {"underlying_equity": "Bad<TAG>"},
            {"reviewed_date": "2026-11-05"},
            {"published_date": "2026-13-99"},
            {"announced_launch_ms": True},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                dataclasses.replace(row, **changes)


if __name__ == "__main__":
    unittest.main()
