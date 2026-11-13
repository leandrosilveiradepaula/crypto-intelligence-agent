"""J3 #617: paired synthetic OOS breakout/confluence ablation."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal as D, localcontext
import json
import socket
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.synthetic_ab_costed_oos import SyntheticABCostAssumptions
from crypto_intelligence_agent.synthetic_confluence_costed_oos import (
    compare_synthetic_confluence_costed_oos,
)
from crypto_intelligence_agent.synthetic_label_purging import (
    SyntheticLabelHorizonConfig, purge_synthetic_label_horizons,
)
from crypto_intelligence_agent.synthetic_walk_forward import (
    SyntheticWalkForwardConfig, plan_synthetic_walk_forward,
)
from test_synthetic_btc_breakout_screen import (
    HOUR, btc, long, candles,
)
from test_synthetic_entry_confluence import config

def extend(cs, new_close=None):
    last = cs[-1]
    close = last.close if new_close is None else D(new_close)
    return cs + (replace(
        last, open_time_ms=last.open_time_ms + HOUR,
        close_time_ms=last.close_time_ms + HOUR,
        open=close, high=max(close, last.high),
        low=min(close, last.low), close=close,
    ),)


def sources():
    benchmark = extend(btc())
    confirmed = candles("ETHUSDT", (
        (100, 110, 90, 10),
        (101, 111, 91, 10),
        (103, 104, 102, 10),
        (104, 105, 103, 10),
        (102, 103, 101, 10),
        (107, 108, 106, 50),
    ))
    breakout_only = long("SOLUSDT", 105, 50)
    return benchmark, (extend(confirmed, 110), extend(breakout_only, 106))


def compare(b=None, assets=None, **overrides):
    btc_series, asset_series = sources()
    if b is not None:
        btc_series = b
    if assets is not None:
        asset_series = assets
    p = plan_synthetic_walk_forward(
        asset_series[0],
        config=SyntheticWalkForwardConfig(3, 1, 3, 3),
        decision_at_ms=btc_series[-1].close_time_ms + 1000,
    )
    h = SyntheticLabelHorizonConfig(1)
    q = purge_synthetic_label_horizons(asset_series[0], plan=p, config=h)
    args = dict(
        plan=p, purged=q, horizon=h, config=config(),
        costs=SyntheticABCostAssumptions(
            entry_notional_quote_units=D(1000),
            entry_fee_bps=D(3), exit_fee_bps=D(3),
            entry_slippage_bps=D(2), exit_slippage_bps=D(2),
        ),
    )
    args.update(overrides)
    return compare_synthetic_confluence_costed_oos(
        btc_series, asset_series, **args,
    )


class PairedConfluenceOOSTests(unittest.TestCase):
    def test_same_oos_opportunities_and_confluence_strict_subset(self):
        audit = compare()
        self.assertEqual(len(audit.folds), 1)
        fold = audit.folds[0]
        self.assertEqual(fold.eligible_indices, (4, 5))
        self.assertEqual(len(fold.baseline_events), 2)
        self.assertEqual(len(fold.confluence_events), 1)
        self.assertEqual(fold.confluence_events[0].entry_index, 5)
        self.assertEqual(fold.confluence_events[0].outcome_index, 6)
        self.assertEqual(
            fold.confluence_events[0].ex_post_net_mark_change_quote_units,
            next(e.ex_post_net_mark_change_quote_units
                 for e in fold.baseline_events if e.entry_index == 5
                 and e.ex_post_gross_mark_change_quote_units > D(0)),
        )
        report = audit.sanitized_report()
        self.assertEqual(report["same_calendar_opportunities"], 4)
        self.assertEqual(report["excluded_by_confluence"], 1)
        self.assertEqual(report["baseline"]["count"], 2)
        self.assertEqual(report["confluence"]["count"], 1)
        self.assertFalse(report["financial_backtest_approved"])
        self.assertFalse(report["approved_for_signals"])
        self.assertFalse(report["approved_for_live_use"])
        self.assertFalse(report["orders_sent"])
        self.assertEqual(report["network_requests"], 0)
        for forbidden in ("ETHUSDT", "SOLUSDT", "BTCUSDT", "fixture", "bybit"):
            self.assertNotIn(forbidden, json.dumps(report))

    def test_future_close_changes_marks_not_selection(self):
        original = compare()
        b, assets = sources()
        changed = (extend(assets[0][:6], 80), assets[1])
        other = compare(b=b, assets=changed)
        before = original.folds[0].confluence_events[0]
        after = other.folds[0].confluence_events[0]
        self.assertEqual(before.entry_index, after.entry_index)
        self.assertEqual(before.side, after.side)
        self.assertGreater(before.ex_post_net_mark_change_quote_units, D(0))
        self.assertLess(after.ex_post_net_mark_change_quote_units, D(0))

    def test_higher_costs_change_marks_not_eligibility(self):
        base = compare()
        expensive = compare(costs=SyntheticABCostAssumptions(
            entry_notional_quote_units=D(1000),
            entry_fee_bps=D(1000), exit_fee_bps=D(1000),
            entry_slippage_bps=D(500), exit_slippage_bps=D(500),
        ))
        self.assertEqual(
            [e.entry_index for e in base.folds[0].confluence_events],
            [e.entry_index for e in expensive.folds[0].confluence_events],
        )
        self.assertGreater(
            base.folds[0].confluence_events[0].ex_post_net_mark_change_quote_units,
            expensive.folds[0].confluence_events[0].ex_post_net_mark_change_quote_units,
        )

    def test_reject_mixed_quality_timeline_duplicate_and_forged_plan(self):
        b, assets = sources()
        for invalid in (
            (assets[0], assets[0]),
            (assets[0], tuple(replace(c, quality="real") for c in assets[1])),
            (assets[0], assets[1][:-1]),
            (assets[0], (replace(assets[1][0], symbol="BTCUSDT"),) + assets[1][1:]),
            (assets[0], (replace(assets[1][0], open_time_ms=assets[1][0].open_time_ms+HOUR),)+assets[1][1:]),
        ):
            with self.subTest(case=str(invalid[1][0])[:70]):
                with self.assertRaises(DataValidationError):
                    compare(assets=invalid)
        plan = plan_synthetic_walk_forward(
            assets[0], config=SyntheticWalkForwardConfig(3, 1, 3, 3),
            decision_at_ms=b[-1].close_time_ms+1000,
        )
        horizon = SyntheticLabelHorizonConfig(1)
        purged = purge_synthetic_label_horizons(assets[0], plan=plan, config=horizon)
        with self.assertRaises(DataValidationError):
            compare(purged=replace(purged, folds=()))
        with self.assertRaises(DataValidationError):
            compare(plan=replace(plan, folds=()))
        with self.assertRaises(DataValidationError):
            compare(horizon="bad")
        with self.assertRaises(DataValidationError):
            compare(config="bad")

    def test_input_order_decimal_context_and_no_external_actions(self):
        b, assets = sources()
        expected = compare(b=b, assets=assets).sanitized_report()
        with patch("urllib.request.urlopen", side_effect=AssertionError("http")), patch(
            "socket.create_connection", side_effect=AssertionError("network")
        ), patch("sqlite3.connect", side_effect=AssertionError("database")):
            for precision in (3, 6, 28):
                with localcontext() as ctx:
                    ctx.prec = precision
                    report = compare(b=b, assets=assets[::-1]).sanitized_report()
                self.assertEqual(expected["baseline"], report["baseline"])
                self.assertEqual(expected["confluence"], report["confluence"])


if __name__ == "__main__":
    unittest.main()
