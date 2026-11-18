"""D436: persisted confirmed closes drive a new J2 evaluation, safely."""
import unittest
from scripts.demo_j2_prospective_bybit_research_d436 import run

class D436Tests(unittest.TestCase):
    def test_public_launcher_requires_all_gates_before_transport(self):
        from crypto_intelligence_agent.j2_prospective_bybit_research_d436 import run_authorized_public_kline_session
        from scripts.demo_j2_prospective_bybit_research_d436 import _scope, CONFIG
        from crypto_intelligence_agent.bybit_ws_supervisor import WSRunBudget
        from tempfile import TemporaryDirectory
        from pathlib import Path
        with TemporaryDirectory() as root:
            result, update = run_authorized_public_kline_session(
                journal_path=Path(root) / "never.sqlite", scope=_scope(), symbol="BTCUSDT",
                config=CONFIG, budget=WSRunBudget(max_seconds=1, max_frames=1),
                session_factory=lambda: (_ for _ in ()).throw(AssertionError("network")))
        self.assertEqual(result["status"], "explicit_public_research_optin_required")
        self.assertFalse(result["network_attempted"])
        self.assertIsNone(update)
    def test_real_public_transport_refuses_fake_owner_and_clock(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        import crypto_intelligence_agent.j2_prospective_bybit_research_d436 as module
        from scripts.demo_j2_prospective_bybit_research_d436 import _scope, CONFIG
        from crypto_intelligence_agent.bybit_ws_supervisor import WSRunBudget
        flags = {
            "allow_public_network": True, "allow_public_websocket": True,
            "confirm_personal_readonly_research": True,
            "confirm_region_eligible": True,
        }
        with TemporaryDirectory() as root:
            args = dict(journal_path=Path(root) / "never-created.sqlite",
                        scope=_scope(), symbol="BTCUSDT", config=CONFIG,
                        budget=WSRunBudget(1, 2, 1), **flags)
            for injected in ({"owner_check": lambda: True},
                             {"wall_ms": lambda: 1_792_998_000_000}):
                with self.subTest(hooks=tuple(injected)):
                    result, update = module.run_authorized_public_kline_session(**args, **injected)
                    self.assertEqual(result["status"], "public_test_hooks_forbidden")
                    self.assertFalse(result["network_attempted"])
                    self.assertIsNone(update)
            with patch.object(module.os, "geteuid", return_value=0, create=True):
                result, update = module.run_authorized_public_kline_session(**args)
                self.assertEqual(result["status"], "unprivileged_owner_required")
                self.assertFalse(result["network_attempted"])
                self.assertIsNone(update)

    def test_gated_injected_socket_stays_offline_even_with_all_flags_true(self):
        import json
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from crypto_intelligence_agent.bybit_closed_stream_cache import SQLiteOfflineClosedStreamJournal
        from crypto_intelligence_agent.bybit_ws_supervisor import WSRunBudget
        from crypto_intelligence_agent.j2_prospective_bybit_research_d436 import run_authorized_public_kline_session
        from scripts.demo_j2_prospective_bybit_research_d436 import (
            _scope, _frame, _fake_ack, CONFIG, FakeClock, FakeSession,
        )

        candle, received_ms = _frame(0)
        clock = FakeClock(received_ms)
        fake = FakeSession(clock, ((_fake_ack(), received_ms), (candle, received_ms)))
        with TemporaryDirectory() as root:
            journal = Path(root) / "isolated.sqlite"
            SQLiteOfflineClosedStreamJournal.create(journal)
            report, update = run_authorized_public_kline_session(
                journal_path=journal, scope=_scope(), symbol="BTCUSDT",
                config=CONFIG, budget=WSRunBudget(1, 12, 2),
                allow_public_network=True, allow_public_websocket=True,
                confirm_personal_readonly_research=True, confirm_region_eligible=True,
                session_factory=lambda: fake, owner_check=lambda: True,
                clock=clock.clock, wall_ms=clock.wall_ms, sleeper=clock.sleeper,
            )
        self.assertTrue(fake.closed)
        self.assertEqual(report.subscriptions_acknowledged, 1)
        self.assertEqual(report.closed_events_appended, 1)
        self.assertIsNotNone(update)
        self.assertEqual(update.status, "observed_data_insufficient")
        self.assertEqual(update.data_mode, "offline_protocol_replay")
        self.assertFalse(update.sanitized_report()["network_attempted"])
        self.assertFalse(report.sanitized_report()["orders_sent"])

    def test_replay_is_end_to_end_and_never_calls_financial_paths(self):
        first, restarted = run(), run()
        self.assertEqual(first, restarted)
        self.assertEqual(first["status"], "observed_long_hypothesis_not_authorized")
        self.assertEqual(first["closed_events_appended"], 1)
        self.assertTrue(first["journal_digest_sha256"])
        for key in ("approved_for_signals", "orders_sent", "risk_gate_called", "auto2_called", "auto4_called", "live_trading_authorized"):
            self.assertFalse(first[key])


    def test_supervised_fake_socket_end_to_end_and_restart(self):
        from scripts.demo_j2_prospective_bybit_research_d436 import run_supervised_cycle
        for side, status in (
            ("LONG", "observed_long_hypothesis_not_authorized"),
            ("SHORT", "observed_short_hypothesis_not_authorized"),
            ("FLAT", "observed_no_hypothesis"),
        ):
            with self.subTest(side=side):
                first = run_supervised_cycle(scenario=side)
                second = run_supervised_cycle(scenario=side)
                self.assertEqual(first, second)
                self.assertEqual(first["research"]["status"], status)
                self.assertFalse(first["research"]["network_attempted"])
                self.assertEqual(first["session"]["closed_events_appended"], 1)
                self.assertEqual(first["session"]["open_updates"], 1)
                self.assertEqual(first["journal_replay_append_count"], 0)
                if first["terminal"] is not None:
                    self.assertTrue(first["terminal"]["session_ended"])
                    self.assertEqual(first["terminal"]["status"], "observed_session_ended")
                for marker in ("orders_sent", "network_attempted"):
                    self.assertFalse(first[marker])

if __name__ == "__main__":
    unittest.main()
