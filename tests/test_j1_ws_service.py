"""OPS6: off-by-default service config, exit policy and private health tests."""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import re
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts.render_j1_ws_service import render_j1_ws_unit
from scripts.run_j1_ws_service import (
    OK, INVALID_ARGUMENTS, PROVIDER_DENIED, INTEGRITY_FAIL_STOP,
    OWNER_GATE_REQUIRED, TRANSIENT_TRANSPORT, STOPPED,
    classify_owner_pilot_result, execute_owner_service_lease, main as run_main,
)
from crypto_intelligence_agent.j1_ws_service_health import (
    read_owner_ws_health, MAX_HEALTH_AGE_MS,
)
from scripts.read_j1_ws_service_health import main as health_main

T = 1_793_534_400_000


class Result:
    def __init__(self, status, failure_category=None):
        self.status = status
        self.failure_category = failure_category


class ServiceExitPolicyTests(unittest.TestCase):
    def test_successful_finite_leases_are_not_trading_approval(self):
        for status in (
            'ws_pilot_sample_rank_ready_not_marketwide',
            'ws_pilot_warming_up_abstain',
            'ws_pilot_scope_refreshed_waiting_next_closed_hour',
        ):
            self.assertEqual(classify_owner_pilot_result(Result(status))[0], OK)

    def test_rate_limit_cannot_restart_by_service_manager(self):
        self.assertEqual(classify_owner_pilot_result(
            Result('ws_pilot_catalog_denied_no_retry', 'provider_or_quota'))[0],
            PROVIDER_DENIED)

    def test_integrity_and_unknown_status_fail_stop(self):
        for result in (
            Result('ws_pilot_fail_closed_abstain', 'scope_journal_or_clock'),
            Result('ws_pilot_degraded_abstain', 'invalid_or_gapped_market_data'),
            Result('surprisingly_ready_marketwide'),
            Result(None),
        ):
            with self.subTest(status=result.status):
                self.assertEqual(classify_owner_pilot_result(result)[0], INTEGRITY_FAIL_STOP)

    def test_transport_only_is_bounded_restart_eligible(self):
        for category in ('transport_disconnected', 'reconnection_deferred',
                         'receive_budget'):
            self.assertEqual(classify_owner_pilot_result(
                Result('ws_pilot_degraded_abstain', category))[0],
                TRANSIENT_TRANSPORT)
        self.assertEqual(classify_owner_pilot_result(Result('owner_opt_in_required'))[0],
                         OWNER_GATE_REQUIRED)
        self.assertEqual(classify_owner_pilot_result(Result('pilot_arguments_invalid'))[0],
                         INVALID_ARGUMENTS)

    def test_absent_optin_returns_before_runner_or_budget_or_owner(self):
        def forbidden(**kwargs):
            self.fail('I/O forbidden before all opt-ins')
        args = dict(directory='/private/ws', seconds=3300, runner=forbidden,
                    budget_factory=forbidden, owner_check=lambda: self.fail('owner check'))
        self.assertEqual(execute_owner_service_lease(**args)[0], OWNER_GATE_REQUIRED)
        args['allow_public_network'] = True
        self.assertEqual(execute_owner_service_lease(**args)[0], OWNER_GATE_REQUIRED)

    def test_allowed_injected_lease_maps_status_and_budget(self):
        calls = []
        def runner(**kwargs):
            calls.append(kwargs)
            return Result('ws_pilot_warming_up_abstain')
        result = execute_owner_service_lease(
            directory='/private/ws', seconds=3300,
            allow_public_network=True, allow_public_websocket=True,
            allow_private_storage=True, confirm_region_and_personal_research=True,
            owner_check=lambda: True, runner=runner,
            budget_factory=lambda **kw: kw,
        )
        self.assertEqual(result[0], OK)
        self.assertEqual(calls[0]['budget'], {'max_seconds': 3300})
        self.assertTrue(calls[0]['allow_public_websocket'])
        self.assertEqual(len(calls), 1)

    def test_bad_duration_root_user_and_path_cannot_run(self):
        def forbidden(**kwargs):
            self.fail('runtime cannot run')
        opt = dict(allow_public_network=True, allow_public_websocket=True,
                   allow_private_storage=True,
                   confirm_region_and_personal_research=True,
                   runner=forbidden, budget_factory=forbidden)
        for secs in (-1, 0, 299, 3591, 4000, True, 300.0):
            self.assertEqual(execute_owner_service_lease(
                directory='/private', seconds=secs, owner_check=lambda: True,
                **opt)[0], INVALID_ARGUMENTS)
        self.assertEqual(execute_owner_service_lease(
            directory='relative', seconds=3300,
            owner_check=lambda: True, **opt)[0], INVALID_ARGUMENTS)
        self.assertEqual(execute_owner_service_lease(
            directory='/private', seconds=3300,
            owner_check=lambda: False, **opt)[0], OWNER_GATE_REQUIRED)

    def test_unexpected_exception_sanitized_and_interrupt(self):
        def broken(**kwargs):
            raise RuntimeError('PRIVATE_SYMBOL SECRET_KEY /private/path')
        opts = dict(directory='/private', seconds=3300, owner_check=lambda: True,
                    allow_public_network=True, allow_public_websocket=True,
                    allow_private_storage=True,
                    confirm_region_and_personal_research=True,
                    budget_factory=lambda **kwargs: kwargs)
        status = execute_owner_service_lease(runner=broken, **opts)
        self.assertEqual(status[0], INTEGRITY_FAIL_STOP)
        self.assertNotIn('SECRET', repr(status))
        def stop(**kwargs):
            raise KeyboardInterrupt
        self.assertEqual(execute_owner_service_lease(runner=stop, **opts)[0], STOPPED)

    def test_cli_has_no_implict_optin_and_prints_sanitized_only(self):
        out = StringIO()
        with redirect_stdout(out):
            code = run_main(['--directory', '/not-used'])
        self.assertEqual(code, OWNER_GATE_REQUIRED)
        doc = json.loads(out.getvalue())
        self.assertFalse(doc['orders_sent'])
        self.assertFalse(doc['marketwide_top50_verified'])
        self.assertEqual(doc['status'], 'owner_opt_in_required')
        self.assertNotIn('/not-used', out.getvalue())


class RenderUnitTests(unittest.TestCase):
    def render(self, **updates):
        kw = dict(username='probe-research', repo_root='/opt/cia/repo',
                  python_bin='/opt/cia/venv/bin/python3',
                  private_dir='/var/lib/cia-research-ws')
        kw.update(updates)
        return render_j1_ws_unit(**kw)

    def test_template_is_off_by_default_and_has_all_failure_gates(self):
        out = self.render()
        self.assertIn('User=probe-research', out)
        self.assertIn('WorkingDirectory=/opt/cia/repo', out)
        self.assertIn('ReadWritePaths=/var/lib/cia-research-ws', out)
        for flag in ('--allow-public-network', '--allow-public-websocket',
                     '--allow-private-storage', '--confirm-region-and-personal-research'):
            self.assertIn(flag, out)
        self.assertIn('Restart=always', out)
        self.assertIn('RestartPreventExitStatus=64 65 66 77 130', out)
        self.assertIn('StartLimitBurst=6', out)
        self.assertIn('ProtectSystem=strict', out)
        self.assertIn('KillSignal=SIGINT', out)
        self.assertIn('UMask=0077', out)
        self.assertNotIn('systemctl enable', out)
        self.assertNotIn('systemctl start', out)
        self.assertNotIn('@', out)
        self.assertNotIn('\\', out, 'systemd Linux paths must be POSIX even on Windows')
        self.assertNotIn('api_key', out.lower())

    def test_reject_injection_unsafe_paths_and_public_repo_writer(self):
        for params in (
            {'username': 'name with spaces'},
            {'username': 'root;order'},
            {'repo_root': '/opt/../repo'},
            {'python_bin': '/opt/bin/python;touch'},
            {'private_dir': '/opt/cia/repo/private'},
            {'private_dir': '/opt/cia/repo'},
            {'private_dir': '/var/lib/private dir'},
            {'private_dir': '/var/lib/x%h'},
            {'private_dir': 'relative'},
        ):
            with self.subTest(params=params), self.assertRaises(ValueError):
                self.render(**params)


@unittest.skipUnless(os.name == 'posix', 'owner-only POSIX filesystem tests')
class ReadOnlyHealthTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.directory.chmod(0o700)
        self.path = self.directory / 'ws-pilot-health.json'
        self.report = {
            'status': 'ws_pilot_warming_up_abstain',
            'missing_24h_assets': 52,
            'complete_24h_assets': 0,
            'realtime_stream_verified': False,
            'source_authenticated': False,
            'marketwide_top50_verified': False,
            'live_trading_authorized': False,
            'orders_sent': False,
        }

    def write(self, *, when=T, report=None):
        document = {
            'schema': 'j1-owner-ws-last-observation-v1',
            'observed_at_utc_ms': when,
            'worker_running_verified': False,
            'report': self.report if report is None else report,
        }
        self.path.write_text(json.dumps(document, sort_keys=True,
                                        separators=(',', ':')), encoding='ascii')
        self.path.chmod(0o600)

    def audit(self, **updates):
        return read_owner_ws_health(self.directory, now_ms=updates.pop('now', T+60_000),
                                    **updates)

    def test_missing_is_never_running(self):
        got = self.audit()
        self.assertEqual(got['status'], 'health_missing_abstain')
        self.assertFalse(got['worker_running_verified'])
        self.assertFalse(got['orders_sent'])

    def test_recent_report_is_observation_not_service_uptime(self):
        self.write()
        got = self.audit()
        self.assertEqual(got['status'], 'health_recent_unverified')
        self.assertEqual(got['last_sample_status'], 'ws_pilot_warming_up_abstain')
        self.assertEqual(got['missing_24h_assets'], 52)
        self.assertEqual(got['age_ms'], 60_000)
        self.assertFalse(got['worker_running_verified'])
        self.assertFalse(got['realtime_stream_verified'])

    def test_stale_sample_never_counts_as_current(self):
        self.write()
        got = self.audit(now=T + MAX_HEALTH_AGE_MS + 1)
        self.assertEqual(got['status'], 'health_stale_abstain')
        self.assertFalse(got['worker_running_verified'])

    def test_untrusted_mode_symlink_hardlink_parent(self):
        self.write()
        self.path.chmod(0o644)
        self.assertEqual(self.audit()['status'], 'health_untrusted_abstain')
        self.path.chmod(0o600)
        self.assertEqual(self.audit()['status'], 'health_recent_unverified')
        hardlink = self.directory / 'other'
        os.link(self.path, hardlink)
        self.assertEqual(self.audit()['status'], 'health_untrusted_abstain')
        hardlink.unlink()
        self.path.unlink()
        self.path.symlink_to(self.directory / 'other')
        self.assertEqual(self.audit()['status'], 'health_untrusted_abstain')
        self.path.unlink()
        self.write()
        self.directory.chmod(0o755)
        self.assertEqual(self.audit()['status'], 'health_untrusted_abstain')

    def test_duplicate_key_and_marketwide_true_rejected(self):
        self.path.write_bytes(b'{"schema":"x","schema":"x"}')
        self.path.chmod(0o600)
        self.assertEqual(self.audit()['status'], 'health_untrusted_abstain')
        bad = dict(self.report, marketwide_top50_verified=True)
        self.write(report=bad)
        self.assertEqual(self.audit()['status'], 'health_untrusted_abstain')
        self.write(report=dict(self.report, status='live_and_trading'))
        self.assertEqual(self.audit()['status'], 'health_untrusted_abstain')

    def test_future_clock_malformed_and_oversized_rejected(self):
        self.write(when=T+100_000)
        self.assertEqual(self.audit()['status'], 'health_untrusted_abstain')
        self.path.write_bytes(b'{"not":"a health document"}' + b' ' * 5000)
        self.assertEqual(self.audit()['status'], 'health_untrusted_abstain')
        self.write(report=dict(self.report, missing_24h_assets=-1))
        self.assertEqual(self.audit()['status'], 'health_untrusted_abstain')


if __name__ == '__main__':
    unittest.main()