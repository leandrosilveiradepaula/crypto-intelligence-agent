"""J1/OPS11 deterministic UTC lease rotation policy tests: no network."""
import unittest

from crypto_intelligence_agent.j1_ws_utc_lease_rotation import (
    plan_post_close_lease,
)
from crypto_intelligence_agent.market_data import DataValidationError
from scripts.run_j1_ws_service import (
    execute_owner_service_lease, OWNER_GATE_REQUIRED, INVALID_ARGUMENTS, OK,
    SERVICE_FRAME_CONTROL_RESERVE,
)


class LeasePlannerTests(unittest.TestCase):
    def test_all_second_phases_end_within_safe_post_close_window(self):
        base = 500_000 * 3_600_000
        for phase in range(3600):
            now_ms = base + phase * 1000
            lease = plan_post_close_lease(now_utc_ms=now_ms)
            self.assertTrue(300 <= lease <= 3590, phase)
            end_phase = (phase + lease) % 3600
            self.assertTrue(180 <= end_phase <= 489, (phase, lease, end_phase))

    def test_boundaries_and_fractional_milliseconds(self):
        base = 500_000 * 3_600_000
        for phase in (0, 1, 189, 190, 191, 3479, 3480, 3481, 3599):
            for ms in (0, 1, 999):
                lease = plan_post_close_lease(now_utc_ms=base + phase*1000 + ms)
                elapsed = phase + ms/1000 + lease
                end_phase = elapsed % 3600
                self.assertTrue(180 <= end_phase < 490, (phase, ms, lease))

    def test_malformed_clock_and_caps_fail_closed(self):
        for timestamp in (0, -1, True, 1.2, "1793534400000", None):
            with self.subTest(timestamp=timestamp), self.assertRaises(DataValidationError):
                plan_post_close_lease(now_utc_ms=timestamp)
        for cap in (300, 3300, 3591, True, 3590.0):
            with self.subTest(cap=cap), self.assertRaises(DataValidationError):
                plan_post_close_lease(now_utc_ms=1_800_000_000_000, max_seconds=cap)

    def test_no_consent_means_no_clock_or_runner(self):
        def forbidden():
            self.fail("clock read without opt-in")
        code, _, _ = execute_owner_service_lease(
            directory="/private/ws", seconds=3590, rotate_after_close=True,
            clock_ms=forbidden,
            runner=lambda **kw: self.fail("runner called"),
            budget_factory=lambda **kw: self.fail("budget created"),
            owner_check=lambda: self.fail("owner check"),
        )
        self.assertEqual(code, OWNER_GATE_REQUIRED)

    def test_only_explicit_3590_mode_can_rotate(self):
        for seconds in (300, 3300, 3591, True):
            code, _, _ = execute_owner_service_lease(
                directory="/private/ws", seconds=seconds,
                rotate_after_close=True,
                allow_public_network=True, allow_public_websocket=True,
                allow_private_storage=True,
                confirm_region_and_personal_research=True,
                runner=lambda **kw: self.fail("runner called"),
                owner_check=lambda: True,
            )
            self.assertEqual(code, INVALID_ARGUMENTS)

    def test_live_adapter_uses_planned_seconds_without_network(self):
        base = 500_000 * 3_600_000
        for phase in (0, 100, 190, 1800, 3481, 3599):
            calls = []
            def runner(**kwargs):
                calls.append(kwargs)
                class Report:
                    status = "ws_pilot_warming_up_abstain"
                    failure_category = None
                return Report()
            actual = execute_owner_service_lease(
                directory="/private/ws", seconds=3590, rotate_after_close=True,
                clock_ms=lambda: base + phase*1000,
                allow_public_network=True, allow_public_websocket=True,
                allow_private_storage=True,
                confirm_region_and_personal_research=True,
                runner=runner, budget_factory=lambda **kw: kw,
                owner_check=lambda: True,
            )
            self.assertEqual(actual[0], OK)
            planned = plan_post_close_lease(now_utc_ms=base+phase*1000)
            self.assertEqual(calls[0]["budget"]["max_seconds"], planned)
            self.assertEqual(calls[0]["budget"]["max_frames"],
                             52*planned+SERVICE_FRAME_CONTROL_RESERVE)

    def test_legacy_mode_does_not_read_clock(self):
        calls = []
        def runner(**kwargs):
            calls.append(kwargs)
            class Report:
                status = "ws_pilot_warming_up_abstain"
                failure_category = None
            return Report()
        code, _, _ = execute_owner_service_lease(
            directory="/private/ws", seconds=3300, clock_ms=lambda: self.fail("clock"),
            allow_public_network=True, allow_public_websocket=True,
            allow_private_storage=True,
            confirm_region_and_personal_research=True,
            runner=runner, budget_factory=lambda **kw: kw, owner_check=lambda: True,
        )
        self.assertEqual(code, OK)
        self.assertEqual(calls[0]["budget"]["max_seconds"], 3300)


if __name__ == "__main__":
    unittest.main()
