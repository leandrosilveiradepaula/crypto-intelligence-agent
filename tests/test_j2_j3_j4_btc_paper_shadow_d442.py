"""D442 integrated J2/J3/J4 BTC research: one contract, cost gate, AUTO4."""
from decimal import Decimal
import json
import os
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.bybit_public_ticker_supervisor_d386 import TickerLeaseBudget
from crypto_intelligence_agent.j2_public_btc_scope_d441 import reviewed_single_btc_scope
from crypto_intelligence_agent.j2_j3_j4_btc_paper_shadow_d442 import (
    CostedShadowPolicy, observe_costed_btc_paper_shadow_once,
)
from crypto_intelligence_agent.j4_shadow_public_paper_pilot_d426 import ShadowPaperPolicy
from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.synthetic_position_state import SyntheticSide
from test_j2_j4_current_n50_paper_lease_d410 import Clock, Socket, ack
from test_j4_shadow_public_paper_pilot_d426 import frame
from test_j2_public_btc_scope_d441 import response

MODULE = "crypto_intelligence_agent.j2_j3_j4_btc_paper_shadow_d442"
D = Decimal


def policy(*, side=SyntheticSide.LONG, fee="1", slip="1", target="10", stop="100", leverage=50):
    return CostedShadowPolicy(
        ShadowPaperPolicy(
            "BTCUSDT", side, margin_quote=D("3"), leverage=leverage,
            target1_distance_bps=D(target), stop_distance_bps=D(stop),
        ),
        D(fee), D(fee), D(slip), D(slip),
    )


def scope_at(now: int, *, leverage="50"):
    payload = response()
    payload["time"] = now - 250
    payload["result"]["list"][0]["launchTime"] = str(now - 200_000)
    payload["result"]["list"][0]["leverageFilter"]["maxLeverage"] = leverage
    return reviewed_single_btc_scope(payload, observed_at_ms=now - 100)


class IntegratedBtcCostedPaperD442Tests(unittest.TestCase):
    def simulate(self, frames, *, cfg=None, flags=True, leverage="50", seconds=3):
        clk = Clock()
        sock = Socket(clk, frames)
        opts = dict(
            allow_public_network=flags,
            allow_public_websocket=flags,
            confirm_personal_readonly_research=flags,
            confirm_region_eligible=flags,
            allow_hypothetical_paper_open=flags,
        )
        with patch(MODULE + ".fetch_single_btc_scope_from_public_rest",
                   side_effect=AssertionError("offline test fetched public REST")):
            with patch("socket.create_connection",
                       side_effect=AssertionError("offline test opened public WS")):
                result = observe_costed_btc_paper_shadow_once(
                    policy=cfg or policy(),
                    budget=TickerLeaseBudget(1, 120, seconds),
                    offline_scope=scope_at(clk.now, leverage=leverage),
                    session_factory=lambda: sock,
                    clock=clk.mono, wall_ms=clk.wall, sleeper=clk.sleep,
                    **opts,
                )
        return result, sock

    def test_long_cheap_cost_partial_reservation_without_fill_or_orders(self):
        result, sock = self.simulate([
            ack(), frame(), ("delay", 1),
            frame(seq=2, delta=1000, mark="101", bid="101", ask="101.02"),
        ])
        self.assertTrue(sock.closed)
        self.assertEqual(sock.sent[0]["args"], ["tickers.BTCUSDT"])
        self.assertEqual(result["status"], "public_quote_routed_to_costed_paper_reservations")
        self.assertEqual(result["ticker_subscription_acks"], 1)
        self.assertEqual(result["ticker_frames_accepted"], 2)
        self.assertEqual(result["j3_cost_hurdle_evaluated"], 1)
        self.assertEqual(result["j3_first_partial_cost_hurdle_blocked"], 0)
        self.assertEqual(result["j4_quote_events_after_open"], 1)
        self.assertEqual(result["j4_reduce_only_reservations"], 1)
        self.assertEqual(result["j4_decision_counts"]["paper_target_reserved"], 1)
        self.assertTrue(result["j4_hypothetical_filled_open_injected_explicitly"])
        self.assertFalse(result["j4_order_fills_inferred_from_quotes"])
        self.assertFalse(result["orders_sent"])
        self.assertFalse(result["j3_liquidation_path_verified"])
        self.assertFalse(result["paper_position_persisted"])
        self.assertFalse(result["j1_state_accessed"])
        self.assertNotIn("BTCUSDT", json.dumps(result))
        self.assertNotIn("101.02", json.dumps(result))

    def test_cost_hurdle_blocks_fake_entry_not_existing_stop(self):
        result, _ = self.simulate([ack(), frame()], cfg=policy(fee="12", slip="4"))
        self.assertEqual(result["status"], "assumed_first_partial_cost_hurdle_blocked")
        self.assertEqual(result["j3_first_partial_cost_hurdle_blocked"], 1)
        self.assertEqual(result["j4_reduce_only_reservations"], 0)
        self.assertFalse(result["j4_hypothetical_filled_open_injected_explicitly"])

    def test_j3_hypothetical_stop_loss_exhausts_margin_before_paper_open(self):
        # At 50x, a hypothetical 250-bps fully filled stop would already
        # exceed the three-unit synthetic margin; this is only a veto.
        result, _ = self.simulate([ack(), frame()], cfg=policy(stop="250"))
        self.assertEqual(result["status"], "assumed_stop_margin_exhaustion_blocked")
        self.assertEqual(result["j3_assumed_stop_margin_exhaustion_blocked"], 1)
        self.assertEqual(result["j3_first_partial_cost_hurdle_blocked"], 0)
        self.assertEqual(result["j4_reduce_only_reservations"], 0)
        self.assertFalse(result["j4_hypothetical_filled_open_injected_explicitly"])
        self.assertFalse(result["j3_real_margin_balance_verified"])
        self.assertFalse(result["j3_liquidation_path_verified"])

    def test_short_and_stop_first_use_existing_auto4(self):
        short, _ = self.simulate([
            ack(), frame(), ("delay", 1),
            frame(seq=2, delta=1000, mark="98", bid="98", ask="98.02"),
        ], cfg=policy(side=SyntheticSide.SHORT))
        self.assertEqual(short["j4_decision_counts"]["paper_target_reserved"], 1)
        stop, _ = self.simulate([
            ack(), frame(), ("delay", 1),
            frame(seq=2, delta=1000, mark="98", bid="98", ask="98.02"),
        ])
        self.assertEqual(stop["j4_decision_counts"]["paper_stop_reserved"], 1)
        self.assertNotIn("paper_target_reserved", stop["j4_decision_counts"])

    def test_no_post_ack_quote_never_fabricates_open(self):
        result, sock = self.simulate([frame(), ack()])
        self.assertTrue(sock.closed)
        self.assertEqual(result["ticker_subscription_acks"], 1)
        self.assertEqual(result["j4_reduce_only_reservations"], 0)
        self.assertFalse(result["j4_hypothetical_filled_open_injected_explicitly"])

    def test_no_followup_is_not_an_exit(self):
        result, _ = self.simulate([ack(), frame()])
        self.assertEqual(result["status"], "hypothetical_shadow_open_no_followup_quote")
        self.assertEqual(result["j4_reduce_only_reservations"], 0)

    def test_stale_feed_abstains_after_shadow_open(self):
        result, _ = self.simulate([ack(), frame(), ("delay", 4)], seconds=5)
        self.assertEqual(result["status"], "public_ticker_lease_abstained")
        self.assertEqual(result["ticker_failure_category"], "held_paper_feed_silent")
        self.assertFalse(result["orders_sent"])

    def test_observed_contract_max_leverage_gate_before_socket(self):
        result, sock = self.simulate([ack(), frame()], leverage="20")
        self.assertEqual(result["status"], "declared_leverage_exceeds_observed_contract_cap")
        self.assertFalse(result["network_attempted"])
        self.assertFalse(sock.sent)

    def test_no_optins_makes_no_rest_ws_or_paper_io(self):
        with patch(MODULE + ".fetch_single_btc_scope_from_public_rest",
                   side_effect=AssertionError("REST called without gate")):
            with patch(MODULE + ".supervise_public_tickers",
                       side_effect=AssertionError("WSS without gate")):
                result = observe_costed_btc_paper_shadow_once(policy=policy())
        self.assertEqual(result["status"], "explicit_btc_paper_research_optins_required")
        self.assertFalse(result["network_attempted"])
        self.assertFalse(result["orders_sent"])

    def test_real_socket_rejects_test_clock_scope_and_root(self):
        opts = dict(
            allow_public_network=True, allow_public_websocket=True,
            confirm_personal_readonly_research=True,
            confirm_region_eligible=True, allow_hypothetical_paper_open=True,
        )
        with self.assertRaises(DataValidationError):
            observe_costed_btc_paper_shadow_once(
                policy=policy(), offline_scope=scope_at(Clock().now), **opts)
        with patch(MODULE + ".os.geteuid", return_value=0, create=True):
            result = observe_costed_btc_paper_shadow_once(
                policy=policy(), **opts)
        self.assertEqual(result["status"], "unprivileged_owner_required")
        self.assertFalse(result["network_attempted"])

    def test_cli_no_optin_and_bad_cost_deny_before_network(self):
        from contextlib import redirect_stdout
        from io import StringIO
        from scripts.run_j2_j3_j4_btc_shadow_d442_once import main
        costs = [
            "--entry-fee-bps", "1", "--exit-fee-bps", "1",
            "--entry-adverse-slippage-bps", "1",
            "--exit-adverse-slippage-bps", "1",
        ]
        with patch(MODULE + ".fetch_single_btc_scope_from_public_rest",
                   side_effect=AssertionError("network before gate")):
            output = StringIO()
            with redirect_stdout(output):
                rc = main(costs)
            self.assertEqual(rc, 77)
            self.assertEqual(json.loads(output.getvalue())["network_attempted"], False)
            output = StringIO()
            with redirect_stdout(output):
                rc = main(costs + ["--entry-fee-bps", "NaN"] + [
                    "--allow-public-network", "--allow-public-websocket",
                    "--confirm-personal-readonly-research",
                    "--confirm-region-eligible",
                    "--allow-hypothetical-paper-open",
                ])
            self.assertEqual(rc, 2)
            self.assertEqual(json.loads(output.getvalue())["network_attempted"], False)

    @unittest.skipUnless(os.name == "posix" and hasattr(os, "geteuid")
                         and os.geteuid() != 0, "unprivileged POSIX only")
    def test_real_rest_scope_is_checked_after_network_capture_not_before(self):
        clk = Clock()
        # The REST observation is captured after the call begins. A pre-GET
        # wall clock would incorrectly declare even fresh metadata "future".
        now = {"value": clk.now - 1000}
        def get_scope():
            now["value"] = clk.now + 100
            return scope_at(clk.now)
        def read_time():
            return now["value"] * 1_000_000
        opts = dict(
            allow_public_network=True, allow_public_websocket=True,
            confirm_personal_readonly_research=True,
            confirm_region_eligible=True, allow_hypothetical_paper_open=True,
        )
        with patch(MODULE + ".fetch_single_btc_scope_from_public_rest",
                   side_effect=get_scope) as fetch:
            with patch(MODULE + ".time.time_ns", side_effect=read_time):
                with patch(MODULE + ".supervise_public_tickers",
                           side_effect=RuntimeError("supervisor reached")) as receiver:
                    with self.assertRaisesRegex(RuntimeError, "supervisor reached"):
                        observe_costed_btc_paper_shadow_once(
                            policy=policy(), budget=TickerLeaseBudget(1, 3, 3),
                            **opts,
                        )
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(receiver.call_count, 1)

    def test_invalid_cost_policy_or_frames_rejected(self):
        for v in (D("-1"), D("NaN"), D("1001"), 1.0, True):
            with self.subTest(value=v), self.assertRaises(DataValidationError):
                CostedShadowPolicy(ShadowPaperPolicy("BTCUSDT", SyntheticSide.LONG),
                                   v, D("1"), D("1"), D("1"))
        with self.assertRaises(DataValidationError):
            policy(target="0")
