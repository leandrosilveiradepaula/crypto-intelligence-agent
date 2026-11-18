"""D437 public pilot command contract: no live network in CI."""
import argparse
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from crypto_intelligence_agent.market_data import DataValidationError
from scripts.run_j2_public_kline_session_d437_once import (
    _OPTINS, _successful_finite_public_close, build_reviewed_scope,
    read_private_manifest, run_once,
)
from scripts.demo_j2_prospective_bybit_research_d436 import _scope
import json
import os
import tempfile


def _manifest(observed_ms):
    scope = _scope()
    contract = scope.contracts[0]
    return {
        "schema": "d437-reviewed-single-kline-scope-v1",
        "registry_variant": "expanded-13",
        "registry_sha256": scope.registry_sha256,
        "observed_at_ms": observed_ms,
        "page_count": 1, "instrument_row_count": 1,
        "last_server_time_ms": observed_ms,
        "contracts": [{
            "symbol": contract.symbol, "base_coin": contract.base_coin,
            "quote_coin": contract.quote_coin, "settle_coin": contract.settle_coin,
            "observed_at_ms": observed_ms, "launch_time_ms": contract.launch_time_ms,
            "max_leverage": str(contract.max_leverage),
            "tick_size": str(contract.tick_size),
            "quantity_step": str(contract.quantity_step),
        }],
    }


def _bytes(obj):
    return json.dumps(obj, sort_keys=True).encode("ascii")


def _args(directory, **overrides):
    defaults = dict(scope_file=directory / "manifest.json", output_dir=directory,
                    max_seconds=1, max_frames=1)
    defaults.update({key: False for key in _OPTINS})
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


class D437CommandTests(TestCase):
    def test_all_optins_required_before_any_io(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)
            for field in _OPTINS:
                flags = {key: True for key in _OPTINS}
                flags[field] = False
                with self.subTest(field=field):
                    with patch("scripts.run_j2_public_kline_session_d437_once.read_private_manifest",
                               side_effect=AssertionError("I/O attempted")):
                        result = run_once(_args(path, **flags))
                    self.assertEqual(result["status"], "explicit_public_research_optin_required")
                    self.assertFalse(result["network_attempted"])

    def test_unsupported_platform_or_root_owner_always_blocked(self):
        with tempfile.TemporaryDirectory() as root:
            args = _args(Path(root), **{k: True for k in _OPTINS})
            if os.name != "posix":
                # Windows has no os.geteuid; the platform gate must stop first.
                self.assertEqual(run_once(args)["status"], "unprivileged_owner_required")
            else:
                with patch("scripts.run_j2_public_kline_session_d437_once.os.geteuid", return_value=0):
                    self.assertEqual(run_once(args)["status"], "unprivileged_owner_required")


    def test_only_completed_acknowledged_public_lease_can_claim_close(self):
        good = {"status": "ws_budget_ended_research_only",
                "sessions_fully_acknowledged": 1,
                "subscriptions_acknowledged": 1,
                "closed_events_appended": 1}
        self.assertTrue(_successful_finite_public_close(good))
        for key, value in (
            ("status", "ws_fail_closed_abstain"),
            ("status", "ws_frame_budget_exhausted_abstain"),
            ("status", "ws_reconnect_budget_exhausted_abstain"),
            ("sessions_fully_acknowledged", 0),
            ("subscriptions_acknowledged", 0),
            ("closed_events_appended", 0),
        ):
            with self.subTest(key=key, value=value):
                self.assertFalse(_successful_finite_public_close({**good, key: value}))
        self.assertFalse(_successful_finite_public_close({"status": "ws_budget_ended_research_only"}))

    def test_manifest_rejects_future_expired_and_duplicate(self):
        old = _manifest(1_792_998_000_000)
        self.assertEqual(build_reviewed_scope(_bytes(old), now_ms=old["observed_at_ms"]).contracts[0].symbol,
                         "BTCUSDT")
        with self.assertRaises(DataValidationError):
            build_reviewed_scope(_bytes(old), now_ms=old["observed_at_ms"] - 1)
        with self.assertRaises(DataValidationError):
            build_reviewed_scope(_bytes(old), now_ms=old["observed_at_ms"] + 8 * 86_400_000)
        with self.assertRaises(DataValidationError):
            build_reviewed_scope(b'{"schema":"a","schema":"b"}', now_ms=old["observed_at_ms"])

    def test_manifest_invalid_contract_and_float_rejected(self):
        good = _manifest(1_792_998_000_000)
        bad = json.loads(json.dumps(good))
        bad["contracts"][0]["symbol"] = "ETHUSDT"
        with self.assertRaises(DataValidationError):
            build_reviewed_scope(_bytes(bad), now_ms=good["observed_at_ms"])
        bad = json.loads(json.dumps(good))
        bad["contracts"][0]["max_leverage"] = 50.0
        with self.assertRaises(DataValidationError):
            build_reviewed_scope(_bytes(bad), now_ms=good["observed_at_ms"])

    def test_owner_file_rejects_symlink_and_unsafe_mode(self):
        if os.name != "posix" or os.geteuid() == 0:
            self.skipTest("non-root POSIX owner only")
        now = 1_792_998_000_000
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            os.chmod(folder, 0o700)
            file = folder / "manifest.json"
            file.write_bytes(_bytes(_manifest(now)))
            os.chmod(file, 0o644)
            with self.assertRaises(DataValidationError):
                read_private_manifest(file, now_ms=now)
            os.chmod(file, 0o600)
            self.assertEqual(read_private_manifest(file, now_ms=now).contracts[0].symbol, "BTCUSDT")
            alias = folder / "alias.json"
            alias.symlink_to(file)
            with self.assertRaises(DataValidationError):
                read_private_manifest(alias, now_ms=now)
