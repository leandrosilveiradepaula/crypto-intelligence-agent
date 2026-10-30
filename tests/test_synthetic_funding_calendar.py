"""J3 #371: synthetic funding calendar does not silently skip settlement."""
from dataclasses import replace
from decimal import Decimal as D, localcontext
from unittest.mock import patch
import unittest

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.synthetic_funding_calendar import (
    SyntheticFundingCalendar, validate_synthetic_funding_coverage,
)
from crypto_intelligence_agent.synthetic_cost_scenarios import SyntheticFundingEvent
from crypto_intelligence_agent.synthetic_mark_replay import (
    SyntheticReplayState, replay_synthetic_mark_path,
)
from crypto_intelligence_agent.synthetic_intrabar_barriers import ResearchDirection
from test_synthetic_mark_replay import T, plan, tick


def calendar():
    return SyntheticFundingCalendar(
        "fixture_synthetic_usdt","fixture_calendar_v1",T+60_000,60_000)


def paid():
    return SyntheticFundingEvent("fixture_funding_calendar_first",
                                 T+60_000,D("200"),D("100"))


def research_path(side=ResearchDirection.LONG, events=(None,), cal=None):
    return replay_synthetic_mark_path(
        plan(side,leverage=10,margin="20"),
        (tick("100","100",T+40_000),tick("100","100",T+119_000)),
        tuple() if events == (None,) else events,
        as_of_ms=T+119_000,
        funding_calendar=calendar() if cal is None else cal)


class FundingCalendarTests(unittest.TestCase):
    def test_complete_long_and_short_event_accounting(self):
        for direction, signed in (
            (ResearchDirection.LONG,D("2")),
            (ResearchDirection.SHORT,D("-2")),
        ):
            with self.subTest(direction=direction):
                result=research_path(direction,events=(paid(),))
                self.assertEqual(result.state,SyntheticReplayState.OPEN_UNRESOLVED)
                self.assertEqual(result.observations[0].signed_funding_paid_quote,D("0"))
                self.assertEqual(result.observations[1].signed_funding_paid_quote,signed)
                self.assertIsNone(result.conditional_net_quote)
                self.assertFalse(result.financial_backtest_approved)
                self.assertFalse(result.orders_sent)

    def test_missing_extra_and_duplicate_settlements_rejected(self):
        with self.assertRaises(DataValidationError):
            research_path(events=())
        unexpected=replace(paid(),event_at_ms=T+90_000,
                          event_id="fixture_funding_calendar_extra")
        with self.assertRaises(DataValidationError):
            research_path(events=(unexpected,))
        with self.assertRaises(DataValidationError):
            research_path(events=(paid(),unexpected))
        with self.assertRaises(DataValidationError):
            research_path(events=(paid(),paid()))

    def test_empty_window_requires_no_events(self):
        clean=replay_synthetic_mark_path(
            plan(leverage=10,margin="20"),(tick("100","100",T+10_000),),
            as_of_ms=T+10_000,funding_calendar=calendar())
        self.assertEqual(clean.observations[0].signed_funding_paid_quote,D(0))
        with self.assertRaises(DataValidationError):
            replay_synthetic_mark_path(
                plan(leverage=10,margin="20"),(tick("100","100",T+10_000),),
                as_of_ms=T+10_000,funding_events=(paid(),),
                funding_calendar=calendar())

    def test_tick_at_settlement_refused_even_without_supplied_event(self):
        with self.assertRaises(DataValidationError):
            replay_synthetic_mark_path(
                plan(leverage=10,margin="20"),(tick("100","100",T+60_000),),
                as_of_ms=T+60_000,funding_calendar=calendar())
        with self.assertRaises(DataValidationError):
            replay_synthetic_mark_path(
                plan(leverage=10,margin="20"),(
                    tick("100","100",T+60_000),tick("100","100",T+119_000)),
                as_of_ms=T+119_000,funding_calendar=calendar(),
                funding_events=(paid(),))

    def test_calendar_contract_and_budget(self):
        with self.assertRaises(DataValidationError):
            SyntheticFundingCalendar("BTCUSDT","fixture_v1",T+60_000,60_000)
        with self.assertRaises(DataValidationError):
            SyntheticFundingCalendar("fixture_synthetic_usdt","fixture_v1",T+60_000,30_000)
        with self.assertRaises(DataValidationError):
            research_path(events=(paid(),),cal=replace(calendar(),
                          instrument_id="fixture_unrelated"))
        with self.assertRaises(DataValidationError):
            research_path(events=(paid(),),cal=replace(calendar(),
                          anchor_at_ms=T+120_001))
        with self.assertRaises(DataValidationError):
            validate_synthetic_funding_coverage(calendar(),
                instrument_id="fixture_synthetic_usdt",
                entry_at_ms=T,last_tick_at_ms=T+65*60_000+1,
                tick_times=(T+65*60_000+1,), funding_events=())

    def test_legacy_path_unchanged_and_no_network(self):
        path=(tick("100","100",T+40_000),tick("100","100",T+119_000))
        expected=replay_synthetic_mark_path(
            plan(leverage=10,margin="20"),path,as_of_ms=T+119_000)
        with patch("socket.create_connection",side_effect=AssertionError("network")):
            self.assertEqual(expected,replay_synthetic_mark_path(
                plan(leverage=10,margin="20"),path,as_of_ms=T+119_000))
            complete=research_path(events=(paid(),))
            self.assertNotEqual(expected.observations[-1].equity_at_mark_quote,
                                complete.observations[-1].equity_at_mark_quote)
        for precision in (2,5,28):
            with localcontext() as c:
                c.prec=precision
                self.assertEqual(complete,research_path(events=(paid(),)))


if __name__=="__main__":
    unittest.main()
