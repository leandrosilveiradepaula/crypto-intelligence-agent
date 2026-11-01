"""J1/OPS3: injected transport only, no real socket, private DB or orders."""
from __future__ import annotations

from decimal import Decimal
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.bybit_closed_stream_cache import (
    HOUR_MS, OfflineReviewedStreamScope, SQLiteOfflineClosedStreamJournal,
)
from crypto_intelligence_agent.bybit_instrument_volume_contract import (
    BybitLinearInstrumentResearch,
)
from crypto_intelligence_agent.bybit_paginated_universe_research import (
    BybitInstrumentScanResearch,
)
from crypto_intelligence_agent.bybit_ws_supervisor import (
    MAX_STREAM_TOPICS, TOPICS_PER_REQUEST, MAX_FRAMES, WSRunBudget,
    _topic_batches, supervise_ws_research,
)
from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.research_registry_catalog import load_reviewed_registry
from test_j1_bybit_closed_stream_cache import (
    DECISION, scope as two_scope, message, event,
)


class FakeClock:
    def __init__(self):
        self.mono = 0.0
        self.utc = DECISION + 3000
        self.sleeps = []

    def clock(self):
        return self.mono

    def wall_ms(self):
        return self.utc

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.mono += seconds


class Session:
    """Reply to a sent request with a deterministic fixture, not network IO."""
    def __init__(self, fake_clock, *, responses=(), auto_ack=False,
                 early_before_ack=None, pong_on_ping=False):
        self.fake_clock = fake_clock
        self.responses = list(responses)
        self.auto_ack = auto_ack
        self.early_before_ack = early_before_ack
        self.pong_on_ping = pong_on_ping
        self.sent = []
        self.closed = False

    def send(self, payload):
        self.sent.append(json.loads(payload))
        request = self.sent[-1]
        if self.auto_ack and request["op"] == "subscribe":
            if self.early_before_ack is not None:
                self.responses.append(self.early_before_ack)
                self.early_before_ack = None
            self.responses.append({"op": "subscribe", "success": True,
                                   "ret_msg": "subscribe", "conn_id": "fixture",
                                   "req_id": request["req_id"]})
        if self.pong_on_ping and request["op"] == "ping":
            self.responses.append({"op": "ping", "ret_msg": "pong"})

    def recv(self, timeout):
        if not self.responses:
            self.fake_clock.mono += timeout
            raise TimeoutError("offline timeout")
        item = self.responses.pop(0)
        self.fake_clock.mono += 0.1
        if isinstance(item, Exception):
            raise item
        if isinstance(item, tuple):
            data, receipt = item
            self.fake_clock.utc = receipt
            return json.dumps(data) if isinstance(data, dict) else data
        return json.dumps(item) if isinstance(item, dict) else item

    def close(self):
        self.closed = True


class SupervisorTests(unittest.TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.journal = SQLiteOfflineClosedStreamJournal.create(
            Path(self.folder.name) / "fixture.sqlite")
        self.scope = two_scope()
        self.first = DECISION - 24 * HOUR_MS
        self.fake_clock = FakeClock()
        self.created = []

    def factory(self, *sessions):
        queue = list(sessions)
        def take():
            if not queue:
                raise OSError("offline no further sessions")
            session = queue.pop(0)
            self.created.append(session)
            return session
        return take

    def run_it(self, factory, *, scope=None, budget=None):
        with patch("socket.create_connection", side_effect=AssertionError("network")):
            return supervise_ws_research(
                session_factory=factory, scope=scope or self.scope,
                journal=self.journal, budget=budget or WSRunBudget(1, 100, 50),
                clock=self.fake_clock.clock, wall_ms=self.fake_clock.wall_ms,
                sleeper=self.fake_clock.sleep,
            )

    def seed_23(self, *symbols):
        for hour in range(23):
            for symbol in (symbols or ("BTCUSDT", "ETHUSDT")):
                self.journal.append(event(
                    symbol, self.first + hour*HOUR_MS, self.scope))

    def test_last_closed_hour_from_one_session_completes_local_24h(self):
        self.seed_23()
        last = self.first + 23*HOUR_MS
        frames = [
            {"op": "subscribe", "success": True, "ret_msg": "subscribe",
             "conn_id": "fake", "req_id": "cia-ws-1"},
            (message("BTCUSDT", last, confirmed=False), DECISION + 2000),
            (message("BTCUSDT", last), DECISION + 2000),
            (message("ETHUSDT", last), DECISION + 2000),
            OSError("EOF"),
        ]
        session = Session(self.fake_clock, responses=frames)
        result = self.run_it(self.factory(session))
        self.assertEqual(result.closed_events_appended, 2)
        self.assertEqual(result.open_updates, 1)
        self.assertEqual(result.sessions_fully_acknowledged, 1)
        self.assertTrue(session.closed)
        self.assertEqual(len(session.sent), 1)
        self.assertEqual(set(session.sent[0]["args"]),
                         {"kline.60.BTCUSDT", "kline.60.ETHUSDT"})
        audited = self.journal.audit(scope=self.scope,
                                     decision_at_ms=DECISION,
                                     as_of_ms=DECISION + 4000)
        self.assertEqual(audited.status, "offline_reviewed_24h_complete_not_top50")
        sanitized = json.dumps(result.sanitized_report())
        self.assertNotIn("BTCUSDT", sanitized)
        self.assertNotIn("10.00", sanitized)
        self.assertEqual(result.sanitized_report()["http_gets"], 0)
        self.assertFalse(result.sanitized_report()["marketwide_top50_verified"])

    def test_subscribe_52_in_order(self):
        observed = DECISION + 72*HOUR_MS
        registry = load_reviewed_registry("expanded-52", as_of_ms=observed)
        symbols = tuple(a.base + "USDT" for a in registry.assets)
        contracts = tuple(BybitLinearInstrumentResearch(
            symbol=s, base_coin=s[:-4], quote_coin="USDT", settle_coin="USDT",
            observed_at_ms=observed, launch_time_ms=observed-7*86_400_000,
            max_leverage=Decimal("50"), tick_size=Decimal("0.01"),
            quantity_step=Decimal("0.001"), registry_sha256=registry.sha256_digest,
        ) for s in symbols)
        scan = BybitInstrumentScanResearch(
            observed, registry.sha256_digest, 1, 52, observed, contracts)
        reviewed = OfflineReviewedStreamScope.from_scan(scan, registry_variant="expanded-52")
        groups = _topic_batches(reviewed)
        self.assertEqual(len(groups), 1)
        self.assertEqual(tuple(len(x) for x in groups), (52,))
        self.assertEqual(sum(map(len, groups)), MAX_STREAM_TOPICS)
        self.assertEqual(TOPICS_PER_REQUEST, 52)
        # The ACK contract is tested independently from the receiver parser.
        # A frame is quarantined until the final ACK; however the fake clock
        # still assigns its actual receipt time before storage.
        session = Session(self.fake_clock, auto_ack=True)
        result = self.run_it(self.factory(session), scope=reviewed)
        self.assertEqual(result.subscriptions_sent, 1)
        self.assertEqual(result.subscriptions_acknowledged, 1)
        self.assertEqual(result.sessions_fully_acknowledged, 1)
        subscriptions = [item for item in session.sent if item["op"] == "subscribe"]
        self.assertEqual(len(subscriptions), 1)
        self.assertEqual(len({t for request in subscriptions for t in request["args"]}), 52)
        self.assertEqual(self.journal.audit(
            scope=reviewed, decision_at_ms=observed + 24*HOUR_MS,
            as_of_ms=observed+24*HOUR_MS+2000).persisted_rows, 0)

    def test_pre_ack_frame_is_quarantined_then_validated(self):
        # Market frames can precede an ACK. They cannot be stored until the
        # complete set of subscriptions is acknowledged.
        last = self.first + 23*HOUR_MS
        session = Session(self.fake_clock, responses=[
            (message("BTCUSDT", last), DECISION+2000),
            {"op": "subscribe", "success": True, "ret_msg": "subscribe",
             "conn_id": "fake", "req_id": "cia-ws-1"},
            (message("ETHUSDT",last), DECISION+2000),
            OSError("EOF"),
        ])
        report = self.run_it(self.factory(session))
        self.assertEqual(report.early_frames_buffered,1)
        self.assertEqual(report.closed_events_appended,2)
        self.assertEqual(self.journal.audit(scope=self.scope,
            decision_at_ms=DECISION,as_of_ms=DECISION+4000).persisted_rows,2)

    def test_single_linear_subscription_accepts_blank_or_missing_req_id(self):
        # Bybit LINEAR ACK can omit req_id or reply with req_id=""; this
        # is safe only because all reviewed topics use ONE request/socket.
        observed = DECISION + 72 * HOUR_MS
        registry = load_reviewed_registry("expanded-52", as_of_ms=observed)
        symbols = tuple(a.base + "USDT" for a in registry.assets[:11])
        contracts = tuple(BybitLinearInstrumentResearch(
            symbol=s, base_coin=s[:-4], quote_coin="USDT", settle_coin="USDT",
            observed_at_ms=observed, launch_time_ms=observed-7*86_400_000,
            max_leverage=Decimal("50"), tick_size=Decimal("0.01"),
            quantity_step=Decimal("0.001"), registry_sha256=registry.sha256_digest,
        ) for s in symbols)
        scan = BybitInstrumentScanResearch(
            observed, registry.sha256_digest, 1, 11, observed, contracts)
        reviewed = OfflineReviewedStreamScope.from_scan(
            scan, registry_variant="expanded-52")
        self.assertEqual(len(_topic_batches(reviewed)), 1)
        for response in (
            {"op": "subscribe", "success": True, "ret_msg": "subscribe",
             "conn_id": "fake"},
            {"op": "subscribe", "success": True, "ret_msg": "subscribe",
             "conn_id": "fake", "req_id": ""},
            {"op": "subscribe", "success": True, "ret_msg": "subscribe",
             "conn_id": "fake", "req_id": "cia-ws-1"},
        ):
            with self.subTest(response=response):
                session = Session(self.fake_clock, responses=[response])
                result = self.run_it(self.factory(session), scope=reviewed)
                self.assertEqual(result.subscriptions_sent, 1)
                self.assertEqual(result.subscriptions_acknowledged, 1)
                self.assertEqual(result.sessions_fully_acknowledged, 1)
                self.assertEqual(result.closed_events_appended, 0)

    def test_wrong_or_duplicate_linear_ack_fails_closed(self):
        good = {"op": "subscribe", "success": True,
                "ret_msg": "subscribe", "conn_id": "fake", "req_id": ""}
        bad = dict(good, req_id="cia-ws-2")
        for responses in ([bad], [good, good]):
            with self.subTest(responses=responses):
                session = Session(self.fake_clock, responses=responses)
                result = self.run_it(self.factory(session))
                self.assertEqual(result.status, "ws_fail_closed_abstain")
                self.assertEqual(result.closed_events_appended, 0)

    def test_early_confirmed_frame_never_written_without_ack(self):
        first = self.first
        early = (message("BTCUSDT", first), first + HOUR_MS + 2000)
        session = Session(self.fake_clock, responses=[early, OSError("EOF")])
        report = self.run_it(self.factory(session))
        self.assertEqual(report.early_frames_buffered, 1)
        self.assertEqual(report.closed_events_appended, 0)
        self.assertEqual(self.journal.audit(scope=self.scope,
            decision_at_ms=DECISION, as_of_ms=DECISION+4000).persisted_rows, 0)

    def test_bad_ack_and_unknown_topic_stop_without_retry(self):
        for frames in (
            [{"op": "subscribe", "success": True, "ret_msg": "subscribe",
              "conn_id": "fake", "req_id": "wrong"}],
            [{"op": "subscribe", "success": False, "ret_msg": "failure",
              "conn_id": "fake", "req_id": "cia-ws-1"}],
            [{"topic": "kline.60.UNKNOWNUSDT", "type": "snapshot",
              "ts": DECISION+2000, "data": []}],
        ):
            with self.subTest(frames=frames):
                session = Session(self.fake_clock, responses=frames)
                report = self.run_it(self.factory(session),budget=WSRunBudget(2,50,90))
                self.assertEqual(report.status, "ws_fail_closed_abstain")
                self.assertEqual(report.sessions_attempted, 1)
                self.assertEqual(report.closed_events_appended, 0)

    def test_reconnection_reuses_persisted_journal_not_backfill(self):
        self.seed_23()
        last = self.first+23*HOUR_MS
        first_session = Session(self.fake_clock, responses=[
            {"op":"subscribe","success":True,"ret_msg":"subscribe",
             "conn_id":"fake","req_id":"cia-ws-1"},
            OSError("disconnected"),
        ])
        second = Session(self.fake_clock, responses=[
            {"op":"subscribe","success":True,"ret_msg":"subscribe",
             "conn_id":"fake","req_id":"cia-ws-1"},
            (message("BTCUSDT",last),DECISION+2000),
            (message("ETHUSDT",last),DECISION+2000),
            OSError("EOF"),
        ])
        report=self.run_it(self.factory(first_session,second),
                           budget=WSRunBudget(2,100,90))
        self.assertEqual(report.sessions_attempted,2)
        self.assertEqual(report.closed_events_appended,2)
        self.assertEqual(self.fake_clock.sleeps,[5.0])
        self.assertEqual(self.journal.audit(scope=self.scope,
            decision_at_ms=DECISION,as_of_ms=DECISION+4000).persisted_rows,48)

    def test_gap_is_abstention_not_silent_reconnect(self):
        self.journal.append(event("BTCUSDT", self.first, self.scope))
        missing = self.first + 2*HOUR_MS
        session = Session(self.fake_clock, responses=[
            {"op":"subscribe","success":True,"ret_msg":"subscribe",
             "conn_id":"fake","req_id":"cia-ws-1"},
            (message("BTCUSDT",missing),missing+HOUR_MS+2000),
        ])
        report = self.run_it(self.factory(session),budget=WSRunBudget(3,50,90))
        self.assertEqual(report.status,"ws_fail_closed_abstain")
        self.assertEqual(report.sessions_attempted,1)
        self.assertEqual(report.failure_category,"invalid_or_gapped_market_data")
        self.assertEqual(self.journal.audit(scope=self.scope,
            decision_at_ms=DECISION,as_of_ms=DECISION+4000).persisted_rows,1)

    def test_open_candle_not_saved_even_with_valid_ack(self):
        session = Session(self.fake_clock,responses=[
            {"op":"subscribe","success":True,"ret_msg":"subscribe",
             "conn_id":"fake","req_id":"cia-ws-1"},
            (message("BTCUSDT",self.first,confirmed=False),self.first+HOUR_MS+2000),
            OSError("offline end"),
        ])
        report=self.run_it(self.factory(session))
        self.assertEqual(report.open_updates,1)
        self.assertEqual(report.closed_events_appended,0)

    def test_ping_pong_does_not_create_candles(self):
        session = Session(self.fake_clock, auto_ack=True, pong_on_ping=True)
        report=self.run_it(self.factory(session),budget=WSRunBudget(1,100,50))
        self.assertGreaterEqual(report.heartbeat_pings,1)
        self.assertGreaterEqual(report.heartbeat_pongs,1)
        self.assertEqual(report.closed_events_appended,0)
        self.assertTrue(session.closed)

    def test_missing_pong_and_transient_fail_never_loop_forever(self):
        session = Session(self.fake_clock, auto_ack=True, pong_on_ping=False)
        report=self.run_it(self.factory(session),budget=WSRunBudget(1,100,90))
        self.assertEqual(report.status,"ws_reconnect_budget_exhausted_abstain")
        self.assertEqual(report.failure_category,"transport_disconnected")
        self.assertGreaterEqual(report.heartbeat_pings,1)

    def test_frame_budget_end_is_abstention_not_success(self):
        success = {"op": "subscribe", "success": True,
                   "ret_msg": "subscribe", "conn_id": "fixture",
                   "req_id": "cia-ws-1"}
        pong = {"op": "ping", "ret_msg": "pong"}
        s = Session(self.fake_clock, responses=[success] + [pong] * 12)
        out = self.run_it(self.factory(s), budget=WSRunBudget(1, 6, 90))
        self.assertEqual(out.status, "ws_frame_budget_exhausted_abstain")
        self.assertEqual(out.failure_category, "frame_budget_exhausted")
        self.assertEqual(out.frames_seen, 6)
        self.assertEqual(out.closed_events_appended, 0)
        self.assertTrue(s.closed)

    def test_default_research_budget_remains_small_but_service_budget_valid(self):
        self.assertEqual(WSRunBudget().max_frames, 4096)
        self.assertGreater(MAX_FRAMES, 52 * 3590 + 4096)
        self.assertEqual(WSRunBudget(max_frames=52 * 3300 + 4096).max_frames,
                         52 * 3300 + 4096)

    def test_bounded_caps_and_no_socket_without_factory(self):
        for params in ((0,10,30),(5,10,30),(1,0,30),
                       (1,MAX_FRAMES+1,30),(1,50,0),(1,50,3601),(1,50,1.0)):
            with self.subTest(params=params):
                with self.assertRaises(DataValidationError):
                    WSRunBudget(*params)
        with self.assertRaises(DataValidationError):
            self.run_it(None)
        self.assertEqual(self.journal.audit(scope=self.scope,
            decision_at_ms=DECISION,as_of_ms=DECISION+4000).persisted_rows,0)


if __name__ == "__main__":
    unittest.main()