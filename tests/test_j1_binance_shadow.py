"""OPS33: strict Binance /market stream with finite, sanitized, no-I/O proof."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
import json
import math
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase, skipUnless

from crypto_intelligence_agent.j1_binance_ws_shadow_observer import (
    URL, STREAMS, BinanceShadowReport, observe_binance_shadow_once,
)
from crypto_intelligence_agent.j1_ops33_binance_timer import (
    CLAIM_NAME, Ops33LaunchReport, launch_binance_once,
    no_competing_collectors_ops33, validated_observer_report,
)
from scripts.observe_j1_binance_shadow_once import run_owner_binance_shadow
from scripts.render_j1_ops33_binance_timer import render_units

H = int(datetime(2026, 11, 5, 3, tzinfo=timezone.utc).timestamp() * 1000)
SHA = "a" * 40
TARGET = "2026-11-05T03:00:00Z"


def candle(symbol="BTCUSDT", *, x=True, t=None, E=None, **changes):
    t = H - 3_600_000 if t is None else t
    E = H + 30 if E is None else E
    k = {"t": t, "T": t + 3_600_000 - 1, "s": symbol,
         "i": "1h", "f": 100, "L": 200, "o": "12", "h": "14",
         "l": "11", "c": "13", "v": "20", "n": 101,
         "x": x, "q": "260", "V": "10", "Q": "130", "B": "0"}
    k.update(changes)
    return {"stream": symbol.lower() + "@kline_1h",
            "data": {"e": "kline", "E": E, "s": symbol, "k": k}}


def ack(id=33):
    return {"result": None, "id": id}


class FakeSession:
    def __init__(self, script, *, base_ms=H):
        self.script = list(script)
        self.sent = []
        self.closed = False
        self.current_ms = base_ms
        self.elapsed = 0.0

    def send(self, value):
        self.sent.append(value)

    def recv(self, timeout):
        if not self.script:
            self.elapsed += timeout
            raise TimeoutError
        item = self.script.pop(0)
        if type(item) is tuple:
            self.current_ms, item = item
        if isinstance(item, Exception):
            raise item
        return item if type(item) in (str, bytes) else json.dumps(item)

    def close(self):
        self.closed = True


def probe(items, *, seconds=180, frames=1024, base_ms=H):
    session = FakeSession(items, base_ms=base_ms)
    result = observe_binance_shadow_once(
        session_factory=lambda: session,
        clock=lambda: session.elapsed,
        wall_ms=lambda: session.current_ms,
        max_seconds=seconds, max_frames=frames)
    return result, session


def raw_observer_report(**changes):
    d = BinanceShadowReport("binance_closes_observed_unverified", frames_seen=4,
                            subscription_acknowledged=True,
                            postack_market_frames=2, topics_observed=2,
                            unique_closed=2).sanitized_report()
    d.update(changes)
    return d


class ObserverTests(TestCase):
    def test_documented_routed_market_endpoint_and_protocol(self):
        self.assertEqual(URL, "wss://fstream.binance.com/market/stream")
        result, session = probe([ack(), (H + 90, candle()),
                                 (H + 100, candle("ETHUSDT"))])
        self.assertEqual(result.status, "binance_closes_observed_unverified")
        self.assertEqual((result.frames_seen, result.unique_closed), (3, 2))
        self.assertTrue(session.closed)
        self.assertEqual(len(session.sent), 1)
        self.assertEqual(json.loads(session.sent[0]), {
            "method": "SUBSCRIBE", "params": list(STREAMS), "id": 33})
        report = json.dumps(result.sanitized_report())
        for data in ("BTCUSDT", "ETHUSDT", str(H), '"260"', '"12"'):
            self.assertNotIn(data, report)
        self.assertFalse(result.sanitized_report()["canonical_ohlcv_approved"])
        self.assertFalse(result.sanitized_report()["usdm_contract_verified"])

    def test_preack_closed_discarded_without_retro_promotion(self):
        result, _ = probe([candle("ETHUSDT"), ack(),
                           (H + 100, candle("BTCUSDT"))], seconds=10)
        self.assertEqual(result.status, "binance_partial_close_abstain")
        self.assertEqual(result.unique_closed, 1)
        self.assertEqual(result.preack_discarded, 1)

    def test_preack_budget_and_no_ack(self):
        noack, _ = probe([candle()] * 3, seconds=5)
        self.assertEqual(noack.status, "binance_no_ack_abstain")
        self.assertFalse(noack.subscription_acknowledged)
        bad, _ = probe([candle()] * 129)
        self.assertEqual(bad.status, "binance_preack_budget_abstain")
        self.assertEqual(bad.preack_discarded, 129)

    def test_wrong_ack_duplicate_and_extra_keys(self):
        for frames, status in (
            ([ack(42)], "binance_ack_invalid_abstain"),
            ([ack(True)], "binance_ack_invalid_abstain"),
            ([ack(), ack()], "binance_ack_invalid_abstain"),
            ([{"id": 33, "result": None, "other": 1}], "binance_control_abstain"),
            ([{"code": 401, "msg": "secret"}], "binance_control_abstain"),
        ):
            with self.subTest(frames=frames):
                r, _ = probe(frames)
                self.assertEqual(r.status, status)

    def test_structural_rejections_and_topic_matching(self):
        bad = candle()
        bad["stream"] = "ethusdt@kline_1h"
        bad2 = candle()
        bad2["data"]["k"]["i"] = "1m"
        bad3 = candle()
        bad3["data"]["k"]["x"] = 1
        bad4 = candle()
        bad4["data"]["k"]["private"] = "internal"
        bad5 = candle()
        bad5["data"]["e"] = "trade"
        for frame, expected in ((bad, "binance_envelope_abstain"),
                                (bad2, "binance_row_abstain"),
                                (bad3, "binance_row_abstain"),
                                (bad4, "binance_envelope_abstain"),
                                (bad5, "binance_envelope_abstain")):
            with self.subTest(expected=expected):
                result, _ = probe([ack(), (H + 100, frame)])
                self.assertEqual(result.status, expected)

    def test_future_or_stale_server_event(self):
        for stamp, receipt in ((H + 2000, H + 100),
                               (H + 1, H + 40_000)):
            with self.subTest(stamp=stamp):
                r, _ = probe([ack(), (receipt, candle(E=stamp))])
                self.assertEqual(r.status, "binance_clock_abstain")

    def test_causal_closed_hour_validation_no_lookahead(self):
        for frame, receipt, status in (
            (candle(), H - 1, "binance_clock_abstain"),
            (candle(t=H - 7_200_000), H + 100, "binance_closed_causal_abstain"),
            (candle(E=H - 100), H + 100, "binance_closed_causal_abstain"),
            (candle(t=H), H + 100, "binance_closed_causal_abstain"),
        ):
            with self.subTest(frame=frame):
                r, _ = probe([ack(), (receipt, frame)])
                self.assertEqual(r.status, status)

    def test_open_update_valid_and_stale_or_invalid(self):
        open_frame = candle(x=False, E=H - 5_000)
        r, _ = probe([ack(), (H - 1000, open_frame),
                      (H + 50, candle()),
                      (H + 70, candle("ETHUSDT"))])
        self.assertEqual(r.status, "binance_closes_observed_unverified")
        self.assertEqual(r.open_updates, 1)
        stale = candle(x=False, E=H - 20_000)
        r2, _ = probe([ack(), (H + 8000, stale)])
        self.assertEqual(r2.status, "binance_open_invalid_abstain")
        invalid = candle(x=False, E=H - 5_000, o="0")
        r3, _ = probe([ack(), (H - 1000, invalid)])
        self.assertEqual(r3.status, "binance_open_invalid_abstain")

    def test_duplicate_identical_vs_conflicting(self):
        ok, _ = probe([ack(), (H + 70, candle()),
                       (H + 80, candle()),
                       (H + 90, candle("ETHUSDT"))])
        self.assertEqual(ok.status, "binance_closes_observed_unverified")
        self.assertEqual(ok.duplicate_closes, 1)
        conflicting = candle(c="12")
        denied, _ = probe([ack(), (H + 70, candle()),
                           (H + 80, conflicting)])
        self.assertEqual(denied.status, "binance_duplicate_conflict_abstain")

    def test_invalid_ohlc_base_quote_and_aux_fields(self):
        for changes in (dict(h="11"), dict(v="0", q="260"),
                        dict(V="nan"), dict(n=-1), dict(f=300, L=200)):
            with self.subTest(changes=changes):
                r, _ = probe([ack(), (H + 100, candle(**changes))])
                self.assertIn(r.status, ("binance_row_abstain",
                                         "binance_closed_causal_abstain"))

    def test_frame_budget_and_partial_close(self):
        r, _ = probe([ack(), (H + 70, candle()), (H + 80, candle())], frames=3)
        self.assertEqual(r.status, "binance_frame_budget_abstain")
        self.assertEqual(r.unique_closed, 1)
        r2, _ = probe([ack(), (H + 100, candle())], seconds=5)
        self.assertEqual(r2.status, "binance_partial_close_abstain")

    def test_owner_gate_network_off_without_import(self):
        self.assertEqual(run_owner_binance_shadow().status,
                         "binance_owner_optin_required")
        self.assertEqual(run_owner_binance_shadow(
            allow_public_network=True, allow_public_websocket=True,
            confirm_region_and_personal_research=True,
            owner_check=lambda: False).status, "binance_nonroot_required")
        r = run_owner_binance_shadow(
            allow_public_network=True, allow_public_websocket=True,
            confirm_region_and_personal_research=True,
            owner_check=lambda: True,
            session_factory=lambda: FakeSession([
                ack(), (H + 30, candle()), (H + 40, candle("ETHUSDT"))]),
            clock=lambda: 0.0, wall_ms=lambda: H + 100)
        self.assertEqual(r.status, "binance_closes_observed_unverified")

    def test_frozen_clock_receive_budget_without_infinite_loop(self):
        stalled = FakeSession([])
        r = observe_binance_shadow_once(
            session_factory=lambda: stalled, clock=lambda: 0.0,
            wall_ms=lambda: H + 100, max_seconds=1, max_frames=2)
        self.assertEqual(r.status, "binance_receive_budget_abstain")

    def test_transport_failure_and_invalid_configs(self):
        for opts in (dict(max_frames=1), dict(max_seconds=181),
                     dict(max_frames=True), dict(max_seconds=0)):
            self.assertEqual(observe_binance_shadow_once(
                session_factory=lambda: FakeSession([]), **opts).status,
                "binance_configuration_abstain")
        r, _ = probe([OSError("secret payload")])
        self.assertEqual(r.status, "binance_transport_or_validation_abstain")
        self.assertNotIn("secret payload", str(r.sanitized_report()))
        nan = observe_binance_shadow_once(session_factory=lambda: FakeSession([]),
                                           clock=lambda: math.nan)
        self.assertEqual(nan.status, "binance_clock_abstain")


class LauncherTests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / "repo"
        self.state = Path(self.temp.name) / "state"
        self.repo.mkdir(mode=0o700)
        self.state.mkdir(mode=0o700)
        self.calls = []

    def execute(self, **options):
        def runner(args, **kw):
            self.calls.append((args, kw))
            return SimpleNamespace(returncode=0, stdout=json.dumps(raw_observer_report()),
                                   stderr="PRIVATE_MARKET_VALUES")
        args = {
            "target_utc": TARGET, "expected_sha": SHA,
            "repo_root": str(self.repo), "python_bin": "/usr/bin/python3",
            "state_dir": str(self.state),
            "now": lambda: datetime(2026, 11, 5, 2, 59, tzinfo=timezone.utc),
            "ntp_check": lambda: True, "git_check": lambda *_: True,
            "concurrency_check": lambda: True,
            "owner_check": lambda: True, "runner": runner,
        }
        args.update(options)
        return launch_binance_once(**args)

    @skipUnless(os.name == "posix", "private POSIX claim")
    def test_one_claim_before_network_and_no_retry(self):
        def runner(args, **kw):
            self.assertTrue((self.state / CLAIM_NAME).is_file())
            self.calls.append((args, kw))
            return SimpleNamespace(returncode=0, stdout=json.dumps(raw_observer_report()),
                                   stderr="PRIVATE_PRICE")
        r = self.execute(runner=runner)
        self.assertEqual(r.status, "ops33_shadow_observed_unverified")
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.execute().status, "ops33_already_attempted_abstain")
        self.assertEqual(len(self.calls), 1)
        self.assertEqual((self.state / CLAIM_NAME).stat().st_mode & 0o777, 0o600)
        a, kw = self.calls[0]
        self.assertEqual(kw["timeout"], 205)
        self.assertEqual(kw["cwd"], self.repo)
        self.assertIn("scripts.observe_j1_binance_shadow_once", a)
        self.assertEqual(a.count("--allow-public-network"), 1)
        self.assertFalse(kw.get("shell", False))
        self.assertNotIn("PRIVATE_PRICE", json.dumps(r.sanitized_report()))

    @skipUnless(os.name == "posix", "private POSIX claim")
    def test_preflight_fail_closed_does_not_consume(self):
        candidates = (
            (dict(owner_check=lambda: False), "ops33_config_abstain"),
            (dict(expected_sha="bad"), "ops33_config_abstain"),
            (dict(ntp_check=lambda: False), "ops33_ntp_abstain"),
            (dict(git_check=lambda *_: False), "ops33_sha_or_tree_abstain"),
            (dict(concurrency_check=lambda: False), "ops33_concurrent_abstain"),
            (dict(now=lambda: datetime(2026, 11, 5, 2, 58, tzinfo=timezone.utc)),
             "ops33_window_abstain"),
        )
        for changes, expected in candidates:
            with self.subTest(expected=expected):
                self.assertEqual(self.execute(**changes).status, expected)
                self.assertFalse((self.state / CLAIM_NAME).exists())
                self.assertFalse(self.calls)

    @skipUnless(os.name == "posix", "private POSIX claim")
    def test_symlink_and_insecure_state_rejected(self):
        self.state.chmod(0o755)
        self.assertEqual(self.execute().status, "ops33_state_permissions_abstain")
        self.state.chmod(0o700)
        self.state.rmdir()
        self.state.symlink_to(self.repo)
        self.assertEqual(self.execute().status, "ops33_state_permissions_abstain")
        self.assertFalse(self.calls)

    def test_report_tampering_and_return_code(self):
        for change in (dict(orders_sent=True), dict(storage_writes=1),
                       dict(canonical_ohlcv_approved=True),
                       dict(frames_seen=9999), dict(unique_closed=3),
                       dict(unique_closed=True),
                       dict(unique_closed=1),
                       dict(subscription_acknowledged=False),
                       dict(closed_event_delay_over_1000ms=3)):
            with self.subTest(change=change):
                self.assertIsNone(validated_observer_report(
                    raw_observer_report(**change), returncode=0))
        self.assertIsNone(validated_observer_report(raw_observer_report(), returncode=1))
        self.assertIsNotNone(validated_observer_report(raw_observer_report(), returncode=0))

    def test_known_competing_units_and_fail_on_unknown_systemd(self):
        def inactive(args, **kw):
            return SimpleNamespace(returncode=3, stdout="inactive\n")
        self.assertTrue(no_competing_collectors_ops33(run=inactive))
        def active(args, **kw):
            if args[-1] == "cia-j1-ops31-shadow-once.timer":
                return SimpleNamespace(returncode=0, stdout="active\n")
            return inactive(args, **kw)
        self.assertFalse(no_competing_collectors_ops33(run=active))
        self.assertFalse(no_competing_collectors_ops33(run=lambda *a, **kw:
                         SimpleNamespace(returncode=1, stdout="weird")))

    def test_one_shot_units_render_only(self):
        opts = dict(owner="cia-probe", target_utc=TARGET, expected_sha=SHA,
                    repo_root="/home/cia-probe/agent/repo",
                    python_bin="/home/cia-probe/agent/ws-venv/bin/python",
                    state_dir="/home/cia-probe/agent/ops33-binance-claims")
        service, timer = render_units(**opts)
        self.assertIn("User=cia-probe", service)
        self.assertIn("Restart=no", service)
        self.assertIn("ReadWritePaths=" + opts["state_dir"], service)
        self.assertIn("--expected-sha " + SHA, service)
        self.assertIn("OnCalendar=2026-11-05 02:59:00 UTC", timer)
        self.assertIn("Persistent=false", timer)
        self.assertIn("Unit=cia-j1-ops33-binance-once.service", timer)
        self.assertNotIn("OnUnitActiveSec", timer)
        self.assertNotIn("OnBootSec", timer)
        self.assertNotIn("\\", timer + service)
        for change in (dict(owner="root"), dict(owner="cia-probe;bad"),
                       dict(expected_sha="invalid"),
                       dict(python_bin="/bin/sh --hack"),
                       dict(state_dir=opts["repo_root"] + "/nested")):
            with self.subTest(change=change), self.assertRaises(ValueError):
                render_units(**(opts | change))
