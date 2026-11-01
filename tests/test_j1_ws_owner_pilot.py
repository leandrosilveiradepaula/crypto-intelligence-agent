"""OPS4: finite owner-only WS pilot, catalog bounded and no previous REST DB IO."""
from __future__ import annotations

from contextlib import closing
from decimal import Decimal
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from crypto_intelligence_agent.bybit_public_j1_transport import BoundedBybitPublicClient
from crypto_intelligence_agent.bybit_ws_owner_pilot import (
    _catalog_scope, _read_scope, _write_new_scope, run_owner_ws_pilot,
)
from crypto_intelligence_agent.bybit_ws_supervisor import WSRunBudget
from crypto_intelligence_agent.market_data import DataGapError, DataValidationError
from crypto_intelligence_agent.research_registry_catalog import load_reviewed_registry
from test_bybit_paginated_universe_research import instrument_row, instrument_page

T = 1793534405000  # 2026-11-01T12:00:05Z


class Moment:
    def __init__(self, start=0.0):
        self.now = float(start)
    def __call__(self):
        self.now += 1.0
        return self.now


class Session:
    def __init__(self):
        self.sent = []
        self.queue = []
        self.closed = False
    def send(self, text):
        data = json.loads(text)
        self.sent.append(data)
        if data.get('op') == 'subscribe':
            self.queue.append(json.dumps({
                'success': True, 'ret_msg': 'subscribe', 'conn_id': 'fixture',
                'op': 'subscribe', 'req_id': data['req_id'],
            }))
    def recv(self, timeout):
        if self.queue:
            return self.queue.pop(0)
        raise TimeoutError()
    def close(self):
        self.closed = True


class OwnerPilotTests(unittest.TestCase):
    def setUp(self):
        if os.name != 'posix':
            self.skipTest('owner-only POSIX security contract')
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.directory = Path(self.folder.name)
        self.directory.chmod(0o700)
        self.bases = tuple(a.base for a in load_reviewed_registry(
            'expanded-52', as_of_ms=T).assets)
        self.assertEqual(len(self.bases), 52)
        self.symbols = tuple(x+'USDT' for x in self.bases)
        self.clock = lambda: T
        self.sessions = []

    def client(self, *, rows=52, pagination=True, blocked=False, bad_cursor=False):
        def transport(url, limit):
            if blocked:
                return b'{"retCode":10006,"retMsg":"untrusted"}'
            q = parse_qs(urlsplit(url).query)
            cursor = q.get('cursor', [None])[0]
            if pagination:
                if cursor is None:
                    here = self.symbols[:26]
                    token = 'page-2'
                elif cursor == 'page-2':
                    here = self.symbols[26:rows]
                    token = 'page-2' if bad_cursor else ''
                else:
                    raise AssertionError('unexpected extra GET')
            else:
                here, token = self.symbols[:rows], ''
            data = instrument_page([instrument_row(s) for s in here],
                                   ms=T-200, cursor=token)
            return json.dumps(data).encode('ascii')
        return BoundedBybitPublicClient(transport=transport)

    def ws_factory(self):
        s = Session()
        self.sessions.append(s)
        return s

    def call(self, *, client=None, clock_ms=None, factory=None, allow=True):
        return run_owner_ws_pilot(
            directory=self.directory,
            allow_public_network=allow,
            allow_public_websocket=allow,
            allow_private_storage=allow,
            confirm_region_and_personal_research=allow,
            client=client,
            session_factory=factory or self.ws_factory,
            clock_ms=clock_ms or self.clock,
            monotonic=Moment(),
            sleeper=lambda s: self.fail('unexpected reconnect/backoff'),
            budget=WSRunBudget(max_sessions=1, max_frames=120, max_seconds=35),
        )

    def test_opt_in_false_is_zero_io(self):
        c = self.client()
        p = self.call(client=c, allow=False)
        self.assertEqual(p.status, 'owner_opt_in_required')
        self.assertEqual(c.requests_attempted, 0)
        self.assertFalse((self.directory/'ws-confirmed.sqlite').exists())
        self.assertFalse(self.sessions)

    def test_one_bounded_paginated_catalog_and_private_scope(self):
        c = self.client()
        scope, pages = _catalog_scope(client=c, clock_ms=self.clock)
        self.assertEqual((pages, c.requests_attempted, len(scope.contracts)), (2, 2, 52))
        self.assertEqual(scope.asserted_full_catalog_rows, 52)
        path = self.directory/'scope.json'
        _write_new_scope(path, scope)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        restored = _read_scope(path, now_ms=T + HOUR)
        self.assertEqual(restored, scope)
        with self.assertRaises(DataGapError):
            _write_new_scope(path, scope)

    def test_first_and_second_finite_lease_reuse_scope_without_get(self):
        import socket
        c = self.client()
        with patch('socket.create_connection', side_effect=AssertionError('live network')):
            one = self.call(client=c)
        self.assertEqual(one.status, 'ws_pilot_warming_up_abstain')
        self.assertEqual((one.catalog_gets, one.catalog_pages, one.reviewed_scope_assets),
                         (2, 2, 52))
        self.assertEqual(one.closed_events_appended, 0)
        self.assertEqual(one.missing_24h_assets, 52)
        self.assertTrue(self.sessions[0].closed)
        self.assertEqual(len([s for s in self.sessions[0].sent
                              if s['op'] == 'subscribe']), 6)
        self.assertEqual((self.directory/'ws-reviewed-scope.json').stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.directory/'ws-confirmed.sqlite').stat().st_mode & 0o777, 0o600)
        health = json.loads((self.directory/'ws-pilot-health.json').read_text())
        self.assertEqual(health['report']['status'], 'ws_pilot_warming_up_abstain')
        self.assertFalse(health['worker_running_verified'])
        self.assertNotIn('BTCUSDT', json.dumps(health))
        with patch('socket.create_connection', side_effect=AssertionError('live network')):
            two = self.call(client=self.client(blocked=True))
        self.assertEqual(two.catalog_gets, 0)
        self.assertEqual(two.reviewed_scope_assets, 52)
        self.assertEqual(two.status, 'ws_pilot_warming_up_abstain')
        self.assertEqual(len(self.sessions), 2)

    def test_10006_is_fail_stop_after_single_get(self):
        c = self.client(blocked=True)
        got = self.call(client=c)
        self.assertEqual(got.status, 'ws_pilot_catalog_denied_no_retry')
        self.assertEqual((got.catalog_gets, c.requests_attempted), (1, 1))
        self.assertFalse(self.sessions)
        self.assertFalse((self.directory/'ws-reviewed-scope.json').exists())

    def test_49_eligible_or_repeated_cursor_never_starts_socket(self):
        for case in ('too_few', 'cycle'):
            with self.subTest(case=case), TemporaryDirectory() as tmp:
                self.directory = Path(tmp)
                self.directory.chmod(0o700)
                c = self.client(rows=49, bad_cursor=(case == 'cycle'))
                got = self.call(client=c)
                self.assertEqual(got.status, 'ws_pilot_fail_closed_abstain')
                self.assertFalse(self.sessions)

    def test_no_rerank_get_with_cached_scope_and_no_rest_db_access(self):
        sentinel = self.directory/'historical-owner-rest.sqlite'
        sentinel.write_bytes(b'KEEP_THIS_PRIVATE_REST_DB_AS_IS')
        with patch('socket.create_connection', side_effect=AssertionError('live network')):
            self.assertEqual(self.call(client=self.client()).catalog_gets, 2)
            self.assertEqual(self.call(client=self.client(blocked=True)).catalog_gets, 0)
        self.assertEqual(sentinel.read_bytes(), b'KEEP_THIS_PRIVATE_REST_DB_AS_IS')
        self.assertEqual((self.directory/'ws-reviewed-scope.json').read_bytes().count(b'BTCUSDT'), 1)

    def test_expired_or_unsafe_scope_refused_without_new_get(self):
        self.call(client=self.client())
        snapshot = self.directory/'ws-reviewed-scope.json'
        bad_clock = lambda: T + 49 * HOUR
        c = self.client(blocked=True)
        got = self.call(client=c, clock_ms=bad_clock)
        self.assertEqual(got.status, 'ws_pilot_fail_closed_abstain')
        self.assertEqual(c.requests_attempted, 0)
        snapshot.chmod(0o644)
        got = self.call(client=c)
        self.assertEqual(got.status, 'ws_pilot_fail_closed_abstain')
        self.assertEqual(c.requests_attempted, 0)

    def test_journal_and_catalog_directory_security_preflight(self):
        self.directory.chmod(0o755)
        c = self.client()
        got = self.call(client=c)
        self.assertEqual(got.status, 'ws_pilot_fail_closed_abstain')
        self.assertEqual(c.requests_attempted, 0)
        self.directory.chmod(0o700)
        (self.directory/'ws-confirmed.sqlite').symlink_to(self.directory/'fake')
        got = self.call(client=c)
        self.assertEqual(got.status, 'ws_pilot_fail_closed_abstain')
        self.assertEqual(c.requests_attempted, 0)

    def test_owner_health_status_is_not_pid_or_trade_approval(self):
        result = self.call(client=self.client())
        fields = result.sanitized_report()
        self.assertFalse(fields['realtime_stream_verified'])
        self.assertFalse(fields['source_authenticated'])
        self.assertFalse(fields['marketwide_top50_verified'])
        self.assertFalse(fields['live_trading_authorized'])
        self.assertFalse(fields['orders_sent'])
        for symbol in self.symbols:
            self.assertNotIn(symbol, json.dumps(fields))


HOUR = 3_600_000
if __name__ == '__main__':
    unittest.main()