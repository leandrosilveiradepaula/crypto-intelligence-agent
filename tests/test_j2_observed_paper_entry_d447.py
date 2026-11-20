"""D447: genuine persisted AUTO2 PENDING outcomes, no exchange requests."""
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from crypto_intelligence_agent.bybit_public_ticker_state_d385 import BybitTickerQuote, SOURCE
from crypto_intelligence_agent.j2_bybit_closed_research_bridge import BybitClosedResearchSeries
from crypto_intelligence_agent.j2_observed_paper_entry_d447 import (
    ObservedPaperEntryPolicy, reserve_observed_paper_entry,
)
from crypto_intelligence_agent.market_data import ClosedCandle, DataValidationError
from crypto_intelligence_agent.paper_margin_preflight import (
    PaperLinearContractFixture, PaperMarginPreflightRequest,
)
from crypto_intelligence_agent.paper_order_store import SQLitePaperOrderJournal
from crypto_intelligence_agent.paper_position_reservations import SQLitePaperPositionJournal
from crypto_intelligence_agent.paper_risk_gate import PaperRiskLimits, PaperRiskObservation
from crypto_intelligence_agent.synthetic_entry_hypotheses import CompressionBreakoutConfig
from crypto_intelligence_agent.synthetic_feature_engine import FeatureConfig
from crypto_intelligence_agent.synthetic_order_lifecycle import PaperOrderStatus, PaperVenue
from crypto_intelligence_agent.synthetic_position_state import SyntheticLeverageSettings

HOUR = 3_600_000
FIRST = 1_792_998_000_000
CONFIG = CompressionBreakoutConfig(
    FeatureConfig(2, 2, 2, 2), 2, 2, Decimal("1"), Decimal("1"),
)
POLICY = ObservedPaperEntryPolicy(
    Decimal("200"), Decimal("50"), Decimal("0.30"),
    Decimal("6"), Decimal("6"), Decimal("3"), Decimal("3"),
)
LIMITS = PaperRiskLimits(
    max_order_notional_quote=Decimal("1000"),
    max_symbol_exposure_quote=Decimal("2000"),
    max_portfolio_exposure_quote=Decimal("5000"),
    max_realized_loss_today_quote=Decimal("50"),
    max_pending_open_orders=1, max_market_age_ms=3000,
)


def inputs(side="LONG"):
    cs = []
    for i in range(24):
        last = i == 23
        close = ("105" if side == "LONG" else "95") if last and side else "100"
        high = "106" if last and side == "LONG" else "101"
        low = "94" if last and side == "SHORT" else "99"
        opened = FIRST + i * HOUR
        cs.append(ClosedCandle(
            exchange="bybit_v5_public", market="linear_perpetual",
            symbol="BTCUSDT", interval="1h",
            open_time_ms=opened, close_time_ms=opened + HOUR - 1,
            open=Decimal("100"), high=Decimal(high), low=Decimal(low),
            close=Decimal(close), base_volume=Decimal("10"),
            quote_volume=Decimal("4" if last else "2"),
            quality="bybit_public_ws_confirmed_unverified",
        ))
    series = BybitClosedResearchSeries(
        tuple(cs), "a" * 64, "b" * 64, "research_only_public_closed_series",
    )
    decision = cs[-1].close_time_ms + 1
    received = decision + 2000
    quote = BybitTickerQuote(
        symbol="BTCUSDT", exchange_at_ms=received - 100,
        received_at_ms=received, cross_sequence=10,
        last_price=Decimal("100"), mark_price=Decimal("100"),
        index_price=Decimal("100"), bid_price=Decimal("99.9"),
        ask_price=Decimal("100.1"), bid_size=Decimal("5"),
        ask_size=Decimal("5"), turnover_24h=Decimal("200000"),
        volume_24h=Decimal("2000"), funding_rate=Decimal("0"),
        source=SOURCE,
    )
    observation = PaperRiskObservation(
        venue=PaperVenue.BYBIT_V5, symbol="BTCUSDT",
        quote_currency="USDT", observed_at_ms=received,
        mark_price_quote=quote.mark_price,
        symbol_exposure_quote=Decimal("0"),
        portfolio_exposure_quote=Decimal("0"),
        realized_loss_today_quote=Decimal("0"),
        pending_open_orders=0, unresolved_open_exists=False,
        kill_switch_active=False,
    )
    contract = PaperLinearContractFixture(
        venue=PaperVenue.BYBIT_V5, symbol="BTCUSDT",
        quote_currency="USDT", observed_at_ms=received - 1000,
        fixture_version="fixture_d447_public_shape_unverified",
        max_leverage_assumed=50, price_tick_quote=Decimal("0.1"),
        quantity_step_base=Decimal("0.01"),
        min_quantity_base=Decimal("0.01"),
        min_notional_quote=Decimal("5"), max_notional_quote=None,
    )
    margin = PaperMarginPreflightRequest(
        SyntheticLeverageSettings(50), Decimal("5"), contract, 60_000,
    )
    return dict(
        series=series, config=CONFIG, quote=quote, observation=observation,
        limits=LIMITS, margin=margin, policy=POLICY,
        requested_units=Decimal("2.50"), now_ms=received,
        allow_hypothetical_paper_open=True,
    )


class ObservedPaperEntryTests(unittest.TestCase):
    def execute(self, args, directory):
        orders = SQLitePaperOrderJournal(Path(directory) / "orders.sqlite")
        positions = Path(directory) / "positions.sqlite"
        SQLitePaperPositionJournal(positions)
        result = reserve_observed_paper_entry(
            **args, journal=orders, position_journal_path=positions,
        )
        return result, orders

    def test_long_short_pending_and_replay_protection(self):
        for side in ("LONG", "SHORT"):
            with self.subTest(side=side), TemporaryDirectory() as folder:
                args = inputs(side)
                result, orders = self.execute(args, folder)
                self.assertEqual(result.status, "paper_open_intent_reserved_only")
                self.assertGreater(result.hypothetical_first_target_net_quote, 0)
                self.assertGreater(result.hypothetical_stop_margin_buffer_quote, 0)
                stored = orders.load(result.intent_id)
                self.assertEqual(stored.intent.position_side.value, side)
                self.assertEqual(stored.snapshot.status, PaperOrderStatus.PENDING)
                self.assertEqual(stored.events, ())
                self.assertEqual(stored.snapshot.filled_total_units, Decimal(0))
                self.assertIsNotNone(orders.read_margin_receipt(result.intent_id))
                report = result.sanitized_report()
                self.assertTrue(report["paper_intent_pending_only"])
                self.assertEqual(report["fills_created"], 0)
                self.assertEqual(report["positions_created"], 0)
                for field in ("orders_sent", "approved_for_signals",
                              "approved_for_live_use", "financial_backtest_approved"):
                    self.assertIs(report[field], False)
                with self.assertRaises(DataValidationError):
                    reserve_observed_paper_entry(
                        **args, journal=orders,
                        position_journal_path=Path(folder) / "positions.sqlite",
                    )
                self.assertEqual(orders.load(result.intent_id).events, ())

    def test_no_signal_or_optin_no_open(self):
        with TemporaryDirectory() as folder:
            result, orders = self.execute(inputs(None), folder)
            self.assertEqual(result.status, "no_current_observed_hypothesis")
            args = inputs()
            args["allow_hypothetical_paper_open"] = False
            result = reserve_observed_paper_entry(
                **args, journal=orders,
                position_journal_path=Path(folder) / "positions.sqlite",
            )
            self.assertEqual(result.status, "hypothetical_paper_open_optin_required")

    def test_causality_and_identity(self):
        baseline = inputs()
        bad = (
            ({"quote": replace(baseline["quote"],
               exchange_at_ms=baseline["series"].candles[-1].close_time_ms)},
             "observed_ticker_or_signal_stale"),
            ({"now_ms": baseline["now_ms"] + 5000}, "observed_ticker_or_signal_stale"),
            ({"now_ms": baseline["now_ms"] - 1}, "observed_ticker_or_signal_stale"),
            ({"quote": replace(baseline["quote"], symbol="ETHUSDT")}, None),
            ({"quote": replace(baseline["quote"], source="fixture")}, None),
            ({"quote": replace(baseline["quote"], bid_price=Decimal("101"))}, None),
            ({"observation": replace(baseline["observation"],
                mark_price_quote=Decimal("99"))}, None),
        )
        for changes, status in bad:
            with self.subTest(changes=str(changes)[:80]), TemporaryDirectory() as folder:
                if status is None:
                    with self.assertRaises(DataValidationError):
                        self.execute({**baseline, **changes}, folder)
                else:
                    result, _ = self.execute({**baseline, **changes}, folder)
                    self.assertEqual(result.status, status)

    def test_cost_stop_and_kill_switch_veto(self):
        baseline = inputs()
        cases = (
            ({"policy": replace(POLICY, entry_fee_bps=Decimal("100"),
                                exit_fee_bps=Decimal("100"))},
             "hypothetical_target_cost_veto"),
            ({"policy": replace(POLICY, stop_distance_bps=Decimal("500"))},
             "hypothetical_stop_margin_veto"),
            ({"observation": replace(
                baseline["observation"], kill_switch_active=True)},
             "paper_margin_denied_paper_risk_gate_blocked"),
        )
        for changes, expected in cases:
            with self.subTest(expected=expected), TemporaryDirectory() as folder:
                result, _ = self.execute({**baseline, **changes}, folder)
                self.assertEqual(result.status, expected)
                self.assertIsNone(result.intent_id)

    def test_fake_history_not_relabelled(self):
        args = inputs()
        original = args["series"]
        forged = replace(original, candles=original.candles[:-1] + (
            replace(original.candles[-1], quality="synthetic_fixture"),))
        with TemporaryDirectory() as folder, self.assertRaises(DataValidationError):
            self.execute({**args, "series": forged}, folder)


if __name__ == "__main__":
    unittest.main()
