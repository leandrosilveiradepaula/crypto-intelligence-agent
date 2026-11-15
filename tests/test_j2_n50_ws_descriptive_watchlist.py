"""J2 #638: audited WS 50x24 research -> existing D308 ranking, without orders."""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
import json
import os
import socket
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.bybit_closed_stream_cache import HOUR_MS
from crypto_intelligence_agent.j2_n50_descriptive_watchlist import (
    build_descriptive_watchlist,
)
from crypto_intelligence_agent.j2_n50_ws_descriptive_watchlist import (
    build_ws_descriptive_watchlist,
    observe_active_ws_n50_descriptive_watchlist,
)

T = 1_800_000_000_000
END = T + 24 * HOUR_MS
NOW = END + 240_000


def source_ws():
    symbols = [f"TST{i:02d}USDT" for i in range(50)]
    symbols[25] = "BTCUSDT"
    rows = []
    for i, symbol in enumerate(symbols):
        change = Decimal(25-i)
        breakout = ("above_prior_23h_high" if i % 3 == 0 else
                    "below_prior_23h_low" if i % 3 == 1 else
                    "inside_prior_23h_range")
        rows.append({
            "descriptive_rank": i+1,
            "symbol": symbol,
            "return_24bars_pct": format(change, "f"),
            "relative_vs_btc_pct_points": format(change, "f"),
            "mean_true_range_14_pct": "1.2",
            "quote_turnover_24bars_usdt": str(200_000 - i * 1000),
            "last_quote_turnover_vs_prior23_mean": ("1.5" if i % 4 != 0 else None),
            "last_closed_bar_breakout": breakout,
            "approved_for_signals": False,
            "orders_sent": False,
        })
    return {
        "schema_version": "j2-ws-n50-descriptive-24closed-v1",
        "status": "ws_n50_descriptive_24h_ready",
        "quality": "private_ws_24h_descriptive_research_only",
        "latest_closed_end_ms": END,
        "audited_assets": 50,
        "eligible_closed_bars_per_asset": 24,
        "btc_context_available": True,
        "descriptive_up_breakouts": sum(
            row["last_closed_bar_breakout"] == "above_prior_23h_high" for row in rows),
        "descriptive_down_breakouts": sum(
            row["last_closed_bar_breakout"] == "below_prior_23h_low" for row in rows),
        "descriptive_inside_bars": sum(
            row["last_closed_bar_breakout"] == "inside_prior_23h_range" for row in rows),
        "research_rows": rows,
        "ws_journal_integrity_replayed": True,
        "window_digest_sha256": "a" * 64,
        "ranked_scope_sha256": "b" * 64,
        "ws_metadata_sha256": "c" * 64,
        "formal_d323_24h_verified": False,
        "continuous_collector_verified": False,
        "rotation_36h_live_verified": False,
        "marketwide_top50_verified": False,
        "crypto_identity_independently_verified": False,
        "source_authenticated": False,
        "approved_for_signals": False,
        "approved_for_live_use": False,
        "financial_backtest_approved": False,
        "orders_sent": False,
        "network_requests": 0,
        "database_mutation_statements": 0,
        "systemd_modified": False,
    }


def run(source=None, *, private=False, now=NOW):
    if source is None:
        source = source_ws()
    return build_ws_descriptive_watchlist(
        source, now_ms=now, include_private_symbols=private,
    )


class PureWSWatchlistTests(unittest.TestCase):
    def test_50x24_source_creates_deterministic_private_research_not_signals(self):
        original = source_ws()
        safe = run(original)
        self.assertEqual(safe["status"], "ws_descriptive_watchlist_ready", safe)
        self.assertEqual(safe["audited_assets"], 50)
        self.assertEqual(safe["eligible_closed_bars_per_asset"], 24)
        self.assertTrue(safe["ws_journal_integrity_replayed"])
        self.assertTrue(safe["btc_context_available"])
        self.assertGreater(safe["observed_up_breakout_candidates"], 0)
        self.assertGreater(safe["observed_down_breakout_candidates"], 0)
        self.assertEqual(safe["up_breakout_watchlist"], [])
        self.assertEqual(safe["down_breakout_watchlist"], [])
        self.assertNotIn("BTCUSDT", json.dumps(safe))
        self.assertNotIn("TST00USDT", json.dumps(safe))
        self.assertNotIn("b"*64, json.dumps(safe))
        self.assertNotIn("c"*64, json.dumps(safe))
        detailed = run(original, private=True)
        self.assertEqual(detailed["status"], safe["status"])
        self.assertLessEqual(len(detailed["up_breakout_watchlist"]), 5)
        self.assertLessEqual(len(detailed["down_breakout_watchlist"]), 5)
        self.assertEqual(detailed["observed_up_breakout_candidates"],
                         safe["observed_up_breakout_candidates"])
        for direction in ("up", "down"):
            for item in detailed[f"{direction}_breakout_watchlist"]:
                self.assertFalse(item["approved_for_signals"])
                self.assertFalse(item["orders_sent"])
                self.assertIn(item["breakout"],
                              ("above_prior_23h_high", "below_prior_23h_low"))
                self.assertNotIn("price", item)
        self.assertEqual(run(original, private=True), detailed)
        for k in (
            "formal_d323_24h_verified", "continuous_collector_verified",
            "rotation_36h_live_verified", "marketwide_top50_verified",
            "crypto_identity_independently_verified", "source_authenticated",
            "approved_for_signals", "approved_for_live_use",
            "financial_backtest_approved", "orders_sent", "systemd_modified",
        ):
            self.assertFalse(safe[k], k)
        self.assertEqual(safe["execution_intents_created"], 0)
        self.assertEqual(safe["network_requests"], 0)
        self.assertEqual(safe["database_mutation_statements"], 0)

    def test_same_d308_observations_for_rest_vs_ws_when_metrics_are_identical(self):
        ws = source_ws()
        rest = {
            "schema_version": "j2-private-n50-24closed-research-v1",
            "status": "descriptive_research_ready",
            "quality": "provisional_private_research_only",
            "epoch_id": "epoch-1800000000000",
            "scope_digest_sha256": ws["ranked_scope_sha256"],
            "window_digest_sha256": ws["window_digest_sha256"],
            "latest_published_end_ms": ws["latest_closed_end_ms"],
            "as_of_ms": NOW,
            "eligible_closed_bars_per_asset": 24,
            "audited_assets": 50,
            "btc_context_available": True,
            "btc_return_24bar_pct": "0",
            "research_rows": ws["research_rows"],
            "owner_journal_integrity_verified": True,
            "marketwide_top50_verified": False,
            "crypto_identity_independently_verified": False,
            "source_authenticated": False,
            "approved_for_signals": False,
            "approved_for_live_use": False,
            "orders_sent": False,
            "network_requests": 0,
            "database_mutation_statements": 0,
            "systemd_modified": False,
        }
        rest_result = build_descriptive_watchlist(
            rest, include_private_symbols=True,
        )
        ws_result = run(ws, private=True)
        self.assertEqual(rest_result["status"], "descriptive_watchlist_ready")
        self.assertEqual(ws_result["status"], "ws_descriptive_watchlist_ready")
        for name in (
            "observed_up_breakout_candidates", "observed_down_breakout_candidates",
            "unclassified_volume_assets", "up_breakout_watchlist",
            "down_breakout_watchlist",
        ):
            self.assertEqual(rest_result[name], ws_result[name], name)

    def test_tamper_to_provenance_time_and_50x24_denied(self):
        mutations = {
            "schema_version": "j1-not-j2",
            "status": "ws_24h_readonly_integrity_abstain",
            "quality": "fake",
            "ws_journal_integrity_replayed": False,
            "audited_assets": 49,
            "eligible_closed_bars_per_asset": 23,
            "btc_context_available": False,
            "window_digest_sha256": "invalid",
            "ranked_scope_sha256": "A" * 64,
            "ws_metadata_sha256": None,
            "marketwide_top50_verified": True,
            "source_authenticated": True,
            "approved_for_signals": True,
            "approved_for_live_use": True,
            "orders_sent": True,
            "network_requests": 1,
            "database_mutation_statements": 1,
            "systemd_modified": True,
            "formal_d323_24h_verified": True,
            "financial_backtest_approved": True,
            "descriptive_up_breakouts": 0,
            "descriptive_down_breakouts": 0,
        }
        for key, value in mutations.items():
            with self.subTest(field=key):
                bad = source_ws()
                bad[key] = value
                rejected = run(bad)
                self.assertEqual(rejected["status"], "ws_research_integrity_abstain")
                self.assertEqual(rejected["up_breakout_watchlist"], [])
                self.assertEqual(rejected["audited_assets"], 0)
        for utc in (END-1, END+HOUR_MS, END+179_999,
                    END+HOUR_MS-60_000, True, float(END)):
            with self.subTest(now=utc):
                self.assertEqual(run(now=utc)["status"], "ws_research_integrity_abstain")
        for close in (END-1, END+HOUR_MS, END-3*HOUR_MS):
            bad = source_ws()
            bad["latest_closed_end_ms"] = close
            self.assertEqual(run(bad)["status"], "ws_research_integrity_abstain")

    def test_invalid_private_rows_and_btc_provenance_denied(self):
        bad_versions = [
            lambda s: s["research_rows"].pop(),
            lambda s: s["research_rows"][25].update(symbol="ETHUSDT"),
            lambda s: s["research_rows"][24].update(symbol="BTCUSDT"),
            lambda s: s["research_rows"][1].update(descriptive_rank=1),
            lambda s: s["research_rows"][0].update(return_24bars_pct="-1"),
            lambda s: s["research_rows"][0].update(relative_vs_btc_pct_points="999"),
            lambda s: s["research_rows"][0].update(return_24bars_pct="NaN"),
            lambda s: s["research_rows"][0].update(quote_turnover_24bars_usdt="-3"),
            lambda s: s["research_rows"][0].update(mean_true_range_14_pct="Infinity"),
            lambda s: s["research_rows"][0].update(last_closed_bar_breakout="filled"),
            lambda s: s["research_rows"][0].update(approved_for_signals=True),
            lambda s: s["research_rows"][0].update(orders_sent=True),
            lambda s: s["research_rows"][0].update(
                last_quote_turnover_vs_prior23_mean="1e309"),
        ]
        for tamper in bad_versions:
            with self.subTest(case=str(tamper)):
                src = source_ws()
                tamper(src)
                out = run(src, private=True)
                self.assertEqual(out["status"], "ws_research_integrity_abstain")
                self.assertEqual(out["down_breakout_watchlist"], [])
                self.assertEqual(out["up_breakout_watchlist"], [])

    def test_no_market_network_storage_order_or_scheduler_path(self):
        original = source_ws()
        with patch("socket.create_connection", side_effect=AssertionError("network")), \
             patch("urllib.request.urlopen", side_effect=AssertionError("http")), \
             patch("sqlite3.connect", side_effect=AssertionError("db")):
            out = run(original, private=True)
        self.assertEqual(out["status"], "ws_descriptive_watchlist_ready")
        self.assertNotIn("api.bybit.com", json.dumps(out))


@unittest.skipUnless(os.name == "posix", "owner entrypoint uses POSIX getuid")
class OwnerCompositionTests(unittest.TestCase):
    def _call(self, **kwargs):
        from crypto_intelligence_agent import j2_n50_ws_descriptive_watchlist as mod
        with patch.object(mod.os, "getuid", return_value=1234), \
             patch.object(mod.os, "geteuid", return_value=1234), \
             patch.object(mod, "observe_active_private_ws_n50_24closed",
                          return_value=source_ws()) as reader:
            out = observe_active_ws_n50_descriptive_watchlist(**kwargs)
        return out, reader

    def test_no_default_read_and_private_symbol_confirmation(self):
        for opts in (
            {},
            {"allow_private_readonly_research": True},
            {"enable_descriptive_watchlist": True},
            {"allow_private_readonly_research": True,
             "enable_descriptive_watchlist": True,
             "include_private_symbols": True},
        ):
            result, reader = self._call(**opts)
            self.assertNotEqual(result["status"], "ws_descriptive_watchlist_ready")
            reader.assert_not_called()

    def test_owner_wrapper_reuses_ws_only_without_reopening_journal(self):
        out, reader = self._call(
            allow_private_readonly_research=True,
            enable_descriptive_watchlist=True,
            include_private_symbols=True,
            confirm_private_symbol_output=True,
            now_ms=NOW,
        )
        self.assertEqual(out["status"], "ws_descriptive_watchlist_ready")
        self.assertGreater(out["observed_up_breakout_candidates"], 0)
        reader.assert_called_once_with(
            allow_private_readonly_research=True,
            include_private_symbols=True,
            now_ms=NOW,
        )

    def test_owner_source_abstention_is_empty_without_forged_watchlist(self):
        from crypto_intelligence_agent import j2_n50_ws_descriptive_watchlist as mod
        bad = source_ws()
        bad["status"] = "owner_active_ws_epoch_changed_abstain"
        with patch.object(mod.os, "getuid", return_value=1234), \
             patch.object(mod.os, "geteuid", return_value=1234), \
             patch.object(mod, "observe_active_private_ws_n50_24closed",
                          return_value=bad):
            out = mod.observe_active_ws_n50_descriptive_watchlist(
                allow_private_readonly_research=True,
                enable_descriptive_watchlist=True,
                now_ms=NOW,
            )
        self.assertEqual(out["status"], "ws_research_integrity_abstain")
        self.assertFalse(out["ws_journal_integrity_replayed"])


if __name__ == "__main__":
    unittest.main()
