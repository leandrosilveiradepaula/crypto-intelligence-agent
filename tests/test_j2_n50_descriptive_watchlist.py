"""D308: offline adversarial tests of N50 descriptive watchlist, no I/O."""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.j1_auto_research_epoch import HOUR_MS
from crypto_intelligence_agent.j2_n50_descriptive_watchlist import (
    build_descriptive_watchlist, observe_private_n50_watchlist,
)

END = 1_794_492_000_000  # fixed closed UTC hour
D = lambda x: format(Decimal(str(x)), "f")


def valid_snapshot():
    names = ["BTCUSDT"] + [f"COIN{i:02d}USDT" for i in range(49)]
    returns = [Decimal("0")] + [
        Decimal(25-i) / Decimal(10) for i in range(49)
    ]
    # Deliberately force some bearish returns and observations as well.
    returns[-2] = Decimal("-3")
    returns[-1] = Decimal("-4")
    pairs = sorted(zip(names, returns), key=lambda x: (-x[1], x[0]))
    rows = []
    for rank, (symbol, change) in enumerate(pairs, 1):
        breakout = (
            "above_prior_23h_high" if change > 0
            else "below_prior_23h_low" if change < 0
            else "inside_prior_23h_range"
        )
        rows.append({
            "descriptive_rank": rank,
            "symbol": symbol,
            "return_24bars_pct": D(change),
            "relative_vs_btc_pct_points": D(change),
            "mean_true_range_14_pct": "1.25",
            "quote_turnover_24bars_usdt": D(1000 + rank),
            "last_quote_turnover_vs_prior23_mean": "1.5",
            "last_closed_bar_breakout": breakout,
            "approved_for_signals": False,
            "orders_sent": False,
        })
    return {
        "schema_version": "j2-private-n50-24closed-research-v1",
        "status": "descriptive_research_ready",
        "owner_journal_integrity_verified": True,
        "eligible_closed_bars_per_asset": 24,
        "audited_assets": 50,
        "btc_context_available": True,
        "btc_return_24bar_pct": "0",
        "marketwide_top50_verified": False,
        "crypto_identity_independently_verified": False,
        "source_authenticated": False,
        "approved_for_signals": False,
        "approved_for_live_use": False,
        "orders_sent": False,
        "network_requests": 0,
        "database_mutation_statements": 0,
        "systemd_modified": False,
        "epoch_id": f"epoch-{END:013d}",
        "scope_digest_sha256": "a" * 64,
        "window_digest_sha256": "b" * 64,
        "latest_published_end_ms": END,
        "as_of_ms": END + 100_000,
        "research_rows": rows,
    }


class WatchlistTests(unittest.TestCase):
    def test_closed_hour_strength_and_breakout_deterministic(self):
        original = valid_snapshot()
        result = build_descriptive_watchlist(
            original, include_private_symbols=True
        )
        self.assertEqual(result["status"], "descriptive_watchlist_ready")
        self.assertEqual(result["audited_assets"], 50)
        self.assertEqual(result["observed_up_breakout_candidates"], 25)
        self.assertEqual(result["observed_down_breakout_candidates"], 23)
        self.assertEqual(len(result["up_breakout_watchlist"]), 5)
        self.assertEqual(len(result["down_breakout_watchlist"]), 5)
        self.assertEqual(
            result["up_breakout_watchlist"][0]["symbol"], "COIN00USDT"
        )
        self.assertEqual(
            result["down_breakout_watchlist"][0]["symbol"], "COIN48USDT"
        )
        self.assertEqual(result["window_digest_sha256"], "b"*64)
        self.assertFalse(result["approved_for_signals"])
        self.assertFalse(result["approved_for_live_use"])
        self.assertFalse(result["marketwide_top50_verified"])
        self.assertEqual(result["network_requests"], 0)
        self.assertEqual(result["execution_intents_created"], 0)
        self.assertEqual(result["orders_sent"], False)
        self.assertEqual(original, valid_snapshot())

    def test_private_symbols_are_off_by_default(self):
        snapshot = valid_snapshot()
        summary = build_descriptive_watchlist(snapshot)
        self.assertEqual(summary["status"], "descriptive_watchlist_ready")
        self.assertEqual(summary["up_breakout_watchlist"], [])
        self.assertEqual(summary["down_breakout_watchlist"], [])
        self.assertNotIn("COIN00USDT", str(summary))
        self.assertNotIn("quote_turnover_24bars_usdt", summary)
        self.assertEqual(summary["observed_up_breakout_candidates"], 25)

    def test_missing_volume_or_btc_relative_gate_never_guess(self):
        s = valid_snapshot()
        s["research_rows"][0]["last_quote_turnover_vs_prior23_mean"] = None
        result = build_descriptive_watchlist(s, include_private_symbols=True)
        self.assertEqual(result["unclassified_volume_assets"], 1)
        self.assertNotIn("COIN00USDT", [
            r["symbol"] for r in result["up_breakout_watchlist"]
        ])
        s["research_rows"][1]["last_quote_turnover_vs_prior23_mean"] = "0.99"
        result = build_descriptive_watchlist(s, include_private_symbols=True)
        self.assertNotIn("COIN01USDT", [
            r["symbol"] for r in result["up_breakout_watchlist"]
        ])

    def test_no_direction_is_fabricated(self):
        s = valid_snapshot()
        for row in s["research_rows"]:
            row["last_closed_bar_breakout"] = "inside_prior_23h_range"
        result = build_descriptive_watchlist(s, include_private_symbols=True)
        self.assertEqual(result["observed_up_breakout_candidates"], 0)
        self.assertEqual(result["observed_down_breakout_candidates"], 0)
        self.assertEqual(result["up_breakout_watchlist"], [])

    def test_adversarial_snapshot_and_payload_rejections(self):
        base = valid_snapshot()
        cases = [
            ("tampered_integrity", lambda x: x.update(
                owner_journal_integrity_verified=False)),
            ("unsafe_orders", lambda x: x.update(orders_sent=True)),
            ("networked", lambda x: x.update(network_requests=1)),
            ("write", lambda x: x.update(database_mutation_statements=1)),
            ("marketwide", lambda x: x.update(marketwide_top50_verified=True)),
            ("source", lambda x: x.update(source_authenticated=True)),
            ("signals", lambda x: x.update(approved_for_signals=True)),
            ("trading", lambda x: x.update(approved_for_live_use=True)),
            ("partial_window", lambda x: x["research_rows"].pop()),
            ("duplicate", lambda x: x["research_rows"][1].update(
                symbol=x["research_rows"][0]["symbol"])),
            ("bad_suffix", lambda x: x["research_rows"][1].update(
                symbol="AAPLUSD")),
            ("price_injection", lambda x: x["research_rows"][1].update(
                return_24bars_pct="NaN")),
            ("decimal_float", lambda x: x["research_rows"][1].update(
                quote_turnover_24bars_usdt=1.5)),
            ("negative_turnover", lambda x: x["research_rows"][1].update(
                quote_turnover_24bars_usdt="-1")),
            ("bad_ratio", lambda x: x["research_rows"][1].update(
                last_quote_turnover_vs_prior23_mean="Infinity")),
            ("bad_atr", lambda x: x["research_rows"][1].update(
                mean_true_range_14_pct="-0.01")),
            ("btc_mismatch", lambda x: x.update(
                btc_return_24bar_pct="5")),
            ("relative_mismatch", lambda x: x["research_rows"][0].update(
                relative_vs_btc_pct_points="90")),
            ("ranking_tamper", lambda x: x["research_rows"][0].update(
                descriptive_rank=3)),
            ("noncausal_sort", lambda x: x["research_rows"].reverse()),
            ("unknown_breakout", lambda x: x["research_rows"][0].update(
                last_closed_bar_breakout="BUY")),
            ("future_checkpoint", lambda x: x.update(
                as_of_ms=END-HOUR_MS)),
            ("stale_checkpoint", lambda x: x.update(
                as_of_ms=END+3*HOUR_MS)),
            ("unverified_digest", lambda x: x.update(
                window_digest_sha256="fake")),
            ("symbol_permission", lambda x: x["research_rows"][0].update(
                approved_for_signals=True)),
        ]
        for name, change in cases:
            with self.subTest(name=name):
                snapshot = deepcopy(base)
                change(snapshot)
                out = build_descriptive_watchlist(
                    snapshot, include_private_symbols=True
                )
                self.assertEqual(
                    out["status"], "research_integrity_abstain", out
                )
                self.assertEqual(out["up_breakout_watchlist"], [])
                self.assertEqual(out["orders_sent"], False)

    def test_owner_entrypoint_optins_and_source_failure(self):
        self.assertEqual(
            observe_private_n50_watchlist()["status"], "owner_optin_required"
        )
        self.assertEqual(
            observe_private_n50_watchlist(
                allow_private_readonly_audit=True,
                enable_descriptive_watchlist=True,
                include_private_symbols=True,
            )["status"], "private_symbol_output_not_approved"
        )
        self.assertEqual(
            observe_private_n50_watchlist(
                allow_private_readonly_audit=True,
                enable_descriptive_watchlist=True,
                owner_ok=False,
            )["status"], "owner_environment_abstain"
        )
        with patch(
            "crypto_intelligence_agent.j2_n50_descriptive_watchlist."
            "audit_private_n50_research", return_value=valid_snapshot()
        ) as source:
            out = observe_private_n50_watchlist(
                allow_private_readonly_audit=True,
                enable_descriptive_watchlist=True,
                include_private_symbols=True,
                confirm_private_symbol_output=True,
                owner_ok=True,
                root_directory=Path.cwd(),  # absolute on Windows and POSIX fixture
                now_ms=END+100_000,
            )
        self.assertEqual(out["status"], "descriptive_watchlist_ready")
        self.assertEqual(len(out["up_breakout_watchlist"]), 5)
        self.assertEqual(source.call_count, 1)
        self.assertEqual(source.call_args.kwargs["now_ms"], END+100_000)


if __name__ == "__main__":
    unittest.main()
