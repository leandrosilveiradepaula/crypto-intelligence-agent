"""J4/PRE3: offline synthetic position contract; no real trading or accounts."""
from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from decimal import Decimal, localcontext
from pathlib import Path
import unittest

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.synthetic_partial_exits import (
    ExitBasis, SyntheticExitPlan, SyntheticExitTranche,
)
from crypto_intelligence_agent.synthetic_manual_exit_replay import (
    MAX_FIXTURE_EVENTS, SyntheticManualExitEvent,
)
from crypto_intelligence_agent.synthetic_position_state import (
    MAX_RESEARCH_LEVERAGE, SyntheticLeverageSettings,
    SyntheticSide, SyntheticPosition, SyntheticPositionExitFill,
    SyntheticPositionSnapshot, open_synthetic_position,
    replay_synthetic_position,
)

D = Decimal
OPEN_AT = 1_800_000_000_000
NOW = OPEN_AT + 10_000
R = ExitBasis.REMAINING_BALANCE
I = ExitBasis.INITIAL_POSITION


def make_plan(initial="100", floor="6"):
    return SyntheticExitPlan(
        initial_units=D(str(initial)),
        tranches=(
            SyntheticExitTranche(R, D(50)),
            SyntheticExitTranche(R, D(60)),
            SyntheticExitTranche(R, D(70)),
        ),
        residual_floor_percent=D(str(floor)),
    )


def position(id="fixture_A", leverage=50, margin="3", side=SyntheticSide.LONG,
             opened=OPEN_AT, exit_plan=None, settings=None):
    return open_synthetic_position(
        fixture_position_id=id, side=side, opened_at_ms=opened,
        exit_plan=make_plan() if exit_plan is None else exit_plan,
        synthetic_margin_units=D(str(margin)) if type(margin) is str else margin,
        settings=(SyntheticLeverageSettings(leverage) if settings is None else settings),
    )


def fill(position_id="fixture_A", id="evt_1", step=1,
         quantity="10", when=OPEN_AT+1):
    e = SyntheticManualExitEvent(
        event_id=id, tranche_step=step, filled_units=D(str(quantity)),
        event_at_ms=when,
    )
    return SyntheticPositionExitFill(fixture_position_id=position_id, event=e)


def replay(events=(), pos=None, as_of=NOW):
    return replay_synthetic_position(
        position() if pos is None else pos, events, as_of_ms=as_of,
    )


class SyntheticPositionStateTests(unittest.TestCase):
    def test_default_is_fifty_x_as_research_setting_only(self):
        s = SyntheticLeverageSettings()
        self.assertEqual(s.for_new_positions, 50)
        p = position(settings=s)
        self.assertEqual(p.leverage_at_open, 50)
        self.assertEqual(replay(pos=p).leverage_at_open, 50)
        self.assertFalse(p.approved_for_live_use)
        self.assertFalse(p.venue_lot_step_verified)

    def test_updated_setting_changes_only_future_positions(self):
        old_settings = SyntheticLeverageSettings()
        p1 = position(id="fixture_old", settings=old_settings)
        new_settings = old_settings.with_new_position_leverage(20)
        p2 = position(id="fixture_new", settings=new_settings)
        self.assertIsNot(old_settings, new_settings)
        self.assertEqual(old_settings.for_new_positions, 50)
        self.assertEqual(p1.leverage_at_open, 50)
        self.assertEqual(p2.leverage_at_open, 20)
        self.assertEqual(replay(pos=p1).leverage_at_open, 50)
        self.assertEqual(replay(pos=p2).leverage_at_open, 20)

    def test_per_position_margins_are_independent_not_usd(self):
        small = position(id="fixture_small", margin="1")
        normal = position(id="fixture_normal", margin="5")
        large = position(id="fixture_large", margin="250.123456")
        self.assertEqual(small.synthetic_margin_units, D(1))
        self.assertEqual(normal.synthetic_margin_units, D(5))
        self.assertEqual(large.synthetic_margin_units, D("250.123456"))
        self.assertEqual(replay(pos=large).synthetic_margin_units,
                         large.synthetic_margin_units)
        self.assertFalse(hasattr(large, "collateral_currency"))
        self.assertFalse(hasattr(large, "notional_usd"))
        self.assertFalse(hasattr(large, "liquidation_price"))

    def test_side_requires_explicit_enum_but_does_not_compute_pnl(self):
        for side in SyntheticSide:
            with self.subTest(side=side):
                p = position(side=side)
                snap = replay(pos=p)
                self.assertEqual(snap.side, side)
                self.assertFalse(hasattr(snap, "pnl"))
                self.assertFalse(hasattr(snap, "fees"))
        for raw in ("LONG", "SHORT", True, None, 1):
            with self.subTest(raw=raw), self.assertRaises(DataValidationError):
                position(side=raw)

    def test_no_events_never_fabricate_fill_or_change_margin(self):
        p = position(margin="1.123456789")
        res = replay(pos=p)
        self.assertEqual(res.initial_units, D(100))
        self.assertEqual(res.remaining_units, D(100))
        self.assertEqual(res.filled_total_units, D(0))
        self.assertEqual(res.synthetic_margin_units, p.synthetic_margin_units)
        self.assertEqual(res.residual_floor_units, D(6))
        self.assertEqual([x.outstanding_units for x in res.progress],
                         [D(50), D(30), D(14)])

    def test_fifty_sixty_seventy_remaining_leaves_six_after_explicit_fills(self):
        events = (
            fill(id="a", step=1, quantity="50"),
            fill(id="b", step=2, quantity="30", when=OPEN_AT+2),
            fill(id="c", step=3, quantity="14", when=OPEN_AT+3),
        )
        res = replay(events)
        self.assertEqual(res.filled_total_units, D(94))
        self.assertEqual(res.remaining_units, D(6))
        self.assertEqual(res.remaining_units, res.residual_floor_units)
        self.assertTrue(all(x.outstanding_units == 0 for x in res.progress))
        self.assertEqual(res.unique_event_count, 3)

    def test_partial_fill_and_duplicate_do_not_reduce_balance_twice(self):
        e = fill(id="a", step=1, quantity="30")
        res = replay((e, e))
        self.assertEqual(res.remaining_units, D(70))
        self.assertEqual(res.filled_total_units, D(30))
        self.assertEqual(res.unique_event_count, 1)
        self.assertEqual(res.exact_duplicate_count, 1)
        self.assertEqual(res.progress[0].outstanding_units, D(20))
        self.assertFalse(res.persistent_idempotency_verified)

    def test_partial_can_complete_step_then_advance(self):
        events = (
            fill(id="a", step=1, quantity=30),
            fill(id="b", step=1, quantity=20, when=OPEN_AT+2),
            fill(id="c", step=2, quantity=10, when=OPEN_AT+3),
        )
        res = replay(events)
        self.assertEqual(res.remaining_units, D(40))
        self.assertEqual(res.progress[1].outstanding_units, D(20))
        self.assertEqual(res.latest_unique_event_at_ms, OPEN_AT+3)

    def test_cross_position_fill_rejected(self):
        other = position(id="fixture_B")
        with self.assertRaisesRegex(DataValidationError, "different fixture"):
            replay((fill(position_id="fixture_A"),), pos=other)
        with self.assertRaisesRegex(DataValidationError, "different fixture"):
            replay((fill(position_id="fixture_B"),))

    def test_mixed_position_tuple_fails_not_merged(self):
        batch = (fill(position_id="fixture_A"),
                 fill(position_id="fixture_B", id="two", when=OPEN_AT+2))
        with self.assertRaises(DataValidationError):
            replay(batch)

    def test_same_event_id_across_distinct_positions_is_not_globally_unique(self):
        first = position(id="fixture_A")
        second = position(id="fixture_B")
        a = replay((fill(position_id="fixture_A", id="repeat"),), pos=first)
        b = replay((fill(position_id="fixture_B", id="repeat"),), pos=second)
        self.assertEqual(a.filled_total_units, b.filled_total_units)
        self.assertFalse(a.persistent_idempotency_verified)
        self.assertFalse(b.persistent_idempotency_verified)

    def test_conflicting_duplicate_event_id_rejected_by_pre2(self):
        a = fill(id="same", quantity="10")
        b = fill(id="same", quantity="11")
        with self.assertRaisesRegex(DataValidationError, "conflicting"):
            replay((a, b))

    def test_decimal_representation_conflict_rejected_by_pre2(self):
        with self.assertRaisesRegex(DataValidationError, "conflicting"):
            replay((fill(id="same", quantity="10.0"),
                    fill(id="same", quantity="10")))

    def test_later_tranche_before_previous_completed_rejected(self):
        with self.assertRaisesRegex(DataValidationError, "prior tranche"):
            replay((fill(step=2, quantity="1"),))

    def test_overfill_rejected_by_reused_pre2_contract(self):
        with self.assertRaisesRegex(DataValidationError, "exceeds allocated"):
            replay((fill(step=1, quantity="51"),))

    def test_event_before_open_and_after_as_of_rejected(self):
        with self.assertRaisesRegex(DataValidationError, "outside"):
            replay((fill(when=OPEN_AT-1),))
        with self.assertRaisesRegex(DataValidationError, "outside"):
            replay((fill(when=NOW+1),))
        with self.assertRaisesRegex(DataValidationError, "precedes"):
            replay(as_of=OPEN_AT-1)

    def test_bad_global_leverage_types_fail_closed(self):
        for val in (0, -1, MAX_RESEARCH_LEVERAGE+1, False, True,
                    50.0, "50", None, D(50)):
            with self.subTest(value=val), self.assertRaises(DataValidationError):
                SyntheticLeverageSettings(val)
        self.assertEqual(SyntheticLeverageSettings(MAX_RESEARCH_LEVERAGE).for_new_positions,
                         MAX_RESEARCH_LEVERAGE)

    def test_change_configuration_requires_valid_replacement(self):
        s = SyntheticLeverageSettings()
        with self.assertRaises(DataValidationError):
            s.with_new_position_leverage(True)
        self.assertEqual(s.for_new_positions, 50)
        with self.assertRaises(FrozenInstanceError):
            s.for_new_positions = 80
        with self.assertRaises(DataValidationError):
            position(settings="50")

    def test_margin_requires_bounded_positive_exact_decimal(self):
        for bad in (D(0), D(-1), D("NaN"), D("Infinity"),
                    D("1E-19"), D("1E25"), D("1"*41),
                    3, 3.0, True, None):
            with self.subTest(value=str(bad)[:30]), self.assertRaises(DataValidationError):
                position(margin=bad)
        self.assertEqual(position(margin=D("1E-18")).synthetic_margin_units,
                         D("1E-18"))

    def test_no_single_global_target_for_count_of_positions(self):
        positions = tuple(position(id=f"fixture_{i}", margin=str(i+1))
                          for i in range(23))
        self.assertEqual(len(positions), 23)
        self.assertEqual(len({p.fixture_position_id for p in positions}), 23)
        self.assertEqual(len([replay(pos=p) for p in positions]), 23)

    def test_invalid_fixture_ids_fail_closed(self):
        for bad in ("BTC", "fixture_", "fixture_a.b", "fixture_é",
                    "fixture_🔥", "fixture_" + "a"*49,
                    "fixture_a\n", "", None, True, 123):
            with self.subTest(bad=bad), self.assertRaises(DataValidationError):
                position(id=bad)
        self.assertEqual(position(id="fixture_BTC_12").fixture_position_id,
                         "fixture_BTC_12")

    def test_direct_position_constructor_cannot_skip_invariants(self):
        p = position()
        for field, bad in (
            ("opened_at_ms", True), ("opened_at_ms", 0),
            ("opened_at_ms", 253_402_300_800_000),
            ("leverage_at_open", "50"), ("leverage_at_open", 0),
            ("plan", None), ("fixture_position_id", "not_fixture"),
            ("synthetic_margin_units", D("NaN")), ("side", "LONG"),
        ):
            with self.subTest(field=field, bad=bad), self.assertRaises(DataValidationError):
                replace(p, **{field: bad})

    def test_bound_fill_rejects_bad_ids_and_non_pre2(self):
        for bad in ("BTC", "fixture_", None, True, "fixture_a/b"):
            with self.subTest(bad=bad), self.assertRaises(DataValidationError):
                SyntheticPositionExitFill(bad, fill().event)
        with self.assertRaises(DataValidationError):
            SyntheticPositionExitFill("fixture_A", {"id": "one"})

    def test_input_event_tuple_exact_and_bounded(self):
        with self.assertRaises(DataValidationError):
            replay([fill()])
        with self.assertRaises(DataValidationError):
            replay((fill().event,))
        with self.assertRaises(DataValidationError):
            replay((fill(),) * (MAX_FIXTURE_EVENTS + 1))
        with self.assertRaises(DataValidationError):
            replay((), pos={"fixture_position_id": "fixture_A"})

    def test_precision_global_context_cannot_change_replay(self):
        events = (
            fill(id="a", quantity="0.000000000000000001"),
            fill(id="b", quantity="0.000000000000000001", when=OPEN_AT+2),
        )
        with localcontext() as context:
            context.prec = 3
            a = replay(events)
        with localcontext() as context:
            context.prec = 300
            b = replay(events)
        self.assertEqual(a, b)
        with localcontext() as context:
            context.prec = 2048
            self.assertEqual(a.initial_units, a.filled_total_units + a.remaining_units)

    def test_plan_identity_and_margin_not_inferred_from_leverage(self):
        p = position(margin="5", leverage=50)
        r = replay(pos=p)
        self.assertEqual(r.initial_units, p.plan.initial_units)
        self.assertEqual(r.synthetic_margin_units, D(5))
        self.assertEqual(r.leverage_at_open, 50)
        for name in ("notional", "price", "cash", "currency",
                     "market_symbol", "wallet", "funding"):
            self.assertFalse(hasattr(p, name))
            self.assertFalse(hasattr(r, name))

    def test_all_live_and_provenance_flags_are_readonly_false(self):
        p = position()
        s = SyntheticLeverageSettings()
        snapshot = replay()
        for obj in (p, s, snapshot):
            self.assertEqual(obj.quality, "synthetic_fixture_only")
            for name in ("orders_sent", "approved_for_live_use",
                         "venue_lot_step_verified", "collateral_currency_verified",
                         "market_data_rights_verified", "persistent_idempotency_verified"):
                self.assertIs(getattr(obj, name), False)
                with self.subTest(kind=type(obj).__name__, field=name):
                    with self.assertRaises(TypeError):
                        replace(obj, **{name: True})
                    with self.assertRaises(FrozenInstanceError):
                        setattr(obj, name, True)
            with self.assertRaises(TypeError):
                replace(obj, quality="live")
        with self.assertRaises(FrozenInstanceError):
            snapshot.remaining_units = D(1)
        with self.assertRaises(FrozenInstanceError):
            p.leverage_at_open = 100

    def test_mutable_global_settings_cannot_mutate_existing_frozen_position(self):
        s = SyntheticLeverageSettings(50)
        p = position(settings=s)
        s2 = s.with_new_position_leverage(25)
        self.assertEqual(p.leverage_at_open, 50)
        self.assertEqual(s2.for_new_positions, 25)
        self.assertEqual(replay(pos=p).leverage_at_open, 50)

    def test_replay_is_pure_and_deterministic(self):
        p = position(id="fixture_B", side=SyntheticSide.SHORT)
        e = fill(position_id="fixture_B")
        a = replay((e,), pos=p)
        b = replay((e,), pos=p)
        self.assertEqual(a, b)
        self.assertEqual(p.leverage_at_open, 50)
        self.assertEqual(p.plan.initial_units, D(100))

    def test_no_trading_network_or_persistent_dependencies(self):
        source = (Path(__file__).resolve().parent.parent
                  / "crypto_intelligence_agent/synthetic_position_state.py").read_text()
        for forbidden in ("urllib.request", "requests.", "socket", "sqlite3",
                          "open(", "create_order(", "send_order(", "subprocess",
                          "futures.kraken.com", "api.hyperliquid.xyz"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
