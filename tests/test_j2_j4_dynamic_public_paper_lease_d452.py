"""D451/D452/D450 complete high-level TWO-lease owner run, offline sockets.

Proves dynamic public catalog -> frozen/renewed J2 candle epoch -> both
existing WSS protocols -> real durable PAPER risk wired, no live calls.
The initial 24h warmup is intentional, never forged from historical REST.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.bybit_closed_stream_cache import HOUR_MS
from crypto_intelligence_agent.bybit_public_j1_transport import (
    BoundedBybitPublicClient, instruments_url, tickers_url,
)
from crypto_intelligence_agent.j2_j4_dual_public_supervisor_d450 import (
    run_dynamic_public_paper_lease_once,
)
from test_j2_dynamic_public_n50_d451 import NOW, scenario, selected
from test_j2_rest_n50_history_d461 import historical_payload
from crypto_intelligence_agent.j2_rest_n50_history_d461 import capture_rest_n50_24h
from test_j2_j4_dual_public_supervisor_d450 import (
    BUDGET, Clock, Session, ack, market_quote,
)
from test_j2_j4_public_paper_cycle_d449 import SETTINGS


@unittest.skipUnless(
    os.name == "posix" and hasattr(os, "geteuid") and os.geteuid() != 0,
    "owner-only POSIX J2 and PAPER",
)
class DynamicEndToEndPublicPaperLeaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="cia-d451-d452-full-")
        self.addCleanup(self.tmp.cleanup)
        home = Path(self.tmp.name)
        self.j2 = home / "j2"
        self.j2.mkdir(mode=0o700)
        self.paper = home / "paper"
        self.paper.mkdir(mode=0o700)
        pages, ticker = scenario()
        self.urls = [
            instruments_url(), instruments_url(cursor="cursor2"),
            tickers_url(),
        ]
        self.responses = dict(zip(self.urls, (pages[0],pages[1],ticker)))
        self.calls = []

        def transport(url, max_size):
            self.calls.append(url)
            return json.dumps(self.responses[url]).encode("ascii")

        self.client = BoundedBybitPublicClient(transport=transport)

    def run_once(self, *, hour=0, allow=True,
                 rest_warmup_filename=None, auto_capture_rest_warmup=False,
                 omit_close=None):
        opened = ((NOW // HOUR_MS) + (
            0 if rest_warmup_filename or auto_capture_rest_warmup else 1
        ) + hour) * HOUR_MS
        closed = opened + HOUR_MS - 1
        received = closed + 2001
        members = ["BTCUSDT"] + [f"ALT{i}USDT" for i in range(1, 60)]
        # The public rolling 24h selector omits the weakest member, ALT59.
        # ALT1..ALT49 + BTC form the 50 subscribed cohort.
        chosen = members[:50]
        frames = [(ack(), received - 100)]
        for symbol in chosen:
            if symbol == omit_close:
                continue
            frames.append((json.dumps({
                "topic": "kline.60." + symbol, "type": "snapshot",
                "ts": closed + 1000,
                "data": [{
                    "start": opened, "end": closed, "interval": "60",
                    "open": "100", "high": "101", "low": "99",
                    "close": "100", "volume": "10", "turnover": "20",
                    "confirm": True, "timestamp": closed,
                }],
            }), received))
        kc, tc = Clock(), Clock()
        ready = threading.Event()
        ksession = Session(kc, frames, signal_done=ready)
        ticker_frames = [
            (ack("cia-ticker-1"), received - 100),
            (json.dumps({
                **json.loads(market_quote(ts=received - 100, cs=10, mark="100")),
                "topic": "tickers.ALT1USDT",
                "data": {
                    **json.loads(market_quote(ts=received - 100, cs=10, mark="100"))["data"],
                    "symbol": "ALT1USDT",
                },
            }), received),
        ]
        tsession = Session(
            tc, ticker_frames,
            after_close=ready if (
                rest_warmup_filename or auto_capture_rest_warmup
            ) else None,
        )
        args = dict(
            private_j2_directory=self.j2,
            private_paper_directory=self.paper,
            config=SETTINGS, budget=BUDGET,
            allow_public_network=allow,
            allow_public_websocket=allow,
            confirm_personal_readonly_research=allow,
            confirm_region_eligible=allow,
            confirm_public_data_rights=allow,
            enable_hypothetical_paper_cycle=allow,
            public_rest_client=self.client,
            public_rest_clock=lambda: NOW + hour * 1500,
            kline_session_factory=lambda: ksession,
            ticker_session_factory=lambda: tsession,
            kline_clock_args={
                "clock": kc.monotonic, "wall_ms": kc.wall, "sleeper": kc.sleeper,
            },
            ticker_clock_args={
                "clock": tc.monotonic, "wall_ms": tc.wall, "sleeper": tc.sleeper,
            },
            rest_warmup_filename=rest_warmup_filename,
            auto_capture_rest_warmup=auto_capture_rest_warmup,
        )
        with patch(
            "socket.create_connection",
            side_effect=AssertionError("D451 test must not open network"),
        ):
            outcome = run_dynamic_public_paper_lease_once(**args)
        return outcome, ksession, tsession

    def test_dynamic_rest_and_dual_public_protocols_preserve_candle_epoch(self):
        first, ks, ts = self.run_once()
        self.assertEqual(first["status"], "finite_public_paper_research_closed")
        self.assertEqual(first["rolling_volume_selection"]["ranked_assets"], 50)
        self.assertTrue(
            first["rolling_volume_selection"]["new_isolated_closed_journal"],
        )
        self.assertEqual(first["dual_public_streams"]["kline_acks"], 1)
        self.assertEqual(first["dual_public_streams"]["ticker_acks"], 1)
        self.assertEqual(first["dual_public_streams"]["accepted_closed_callbacks"], 50)
        self.assertEqual(first["dual_public_streams"]["accepted_public_ticker_callbacks"], 1)
        self.assertEqual(len(ks.sent[0]["args"]), 50)
        self.assertEqual(len(ts.sent[0]["args"]), 50)
        self.assertEqual(len(self.calls), 3)
        self.assertFalse(first["orders_sent"])
        self.assertFalse(first["public_feed_confirmed_24h_continuous"])
        self.assertFalse(first["marketwide_crypto_identity_verified"])
        self.assertEqual(first["dual_public_streams"]["paper_cycle"]["held_paper_contract_count"], 0)
        files = tuple(self.j2.glob("n50-d451-*.sqlite"))
        self.assertEqual(len(files), 1)
        with sqlite3.connect(files[0]) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM confirmed").fetchone()[0], 50)

        second, _, _ = self.run_once(hour=1)
        self.assertFalse(second["rolling_volume_selection"]["new_isolated_closed_journal"])
        self.assertEqual(len(tuple(self.j2.glob("n50-d451-*.sqlite"))), 1)
        with sqlite3.connect(files[0]) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM confirmed").fetchone()[0], 100)
        self.assertEqual(len(self.calls), 6)
        self.assertEqual(second["dual_public_streams"]["paper_cycle"]["held_paper_contract_count"], 0)
        self.assertFalse(second["orders_sent"])

    def test_50_member_real_modules_join_24_rest_plus_confirmed_ws_without_fake_24h(self):
        from urllib.parse import urlsplit, parse_qs
        old_replies = self.responses.copy()
        def extended_transport(url, max_size):
            self.calls.append(url)
            if "/v5/market/kline?" in url:
                q = parse_qs(urlsplit(url).query)
                return json.dumps(historical_payload(
                    q["symbol"][0], int(q["start"][0]), int(q["end"][0]) + 1,
                )).encode("ascii")
            return json.dumps(old_replies[url]).encode("ascii")
        self.client = BoundedBybitPublicClient(transport=extended_transport)
        with patch("socket.create_connection",
                   side_effect=AssertionError("D462 all WS and REST are injected")):
            history = capture_rest_n50_24h(
                snapshot=selected(), private_j2_directory=self.j2,
                client=self.client, wall_ms=lambda:NOW+1500,
                allow_public_network=True,
                confirm_personal_readonly_research=True,
                confirm_region_eligible=True,
                confirm_public_data_rights=True,
            )
        self.assertEqual(len(history.series),50)
        result, kline, ticker = self.run_once(
            rest_warmup_filename=history.snapshot_file.name,
        )
        self.assertEqual(result["status"],"finite_public_paper_research_closed")
        self.assertTrue(result["preclosed_rest_history_warmup_enabled"])
        self.assertEqual(result["historical_rest_validated_closed_candles"],1200)
        self.assertEqual(len(result["historical_rest_digest_sha256"]),64)
        self.assertEqual(result["dual_public_streams"]["accepted_closed_callbacks"],50)
        from crypto_intelligence_agent.j2_rest_ws_causal_warmup_d462 import (
            read_causal_rest_warmup_ws_close,
        )
        joined = read_causal_rest_warmup_ws_close(
            history=history, scope=selected().scope,
            journal_path=next(self.j2.glob("n50-d451-*.sqlite")),
            symbol="BTCUSDT", open_ms=history.window_end_ms,
            received_ms=history.window_end_ms + HOUR_MS + 2000,
        )
        self.assertEqual(len(joined.series.candles),25)
        from crypto_intelligence_agent.j2_observed_bybit_research import (
            evaluate_observed_bybit_research,
        )
        btc_result = evaluate_observed_bybit_research(
            joined.series, config=SETTINGS.research,
            decision_at_ms=history.window_end_ms+HOUR_MS,
            close_safety_ms=1, allow_causal_rest_ws_warmup=True,
        )
        self.assertEqual(btc_result.evaluated_candle_count,25)
        counts = result["dual_public_streams"]["paper_cycle"]["event_counts"]
        self.assertEqual(
            result["dual_public_streams"]["accepted_public_ticker_callbacks"],
            1, result["dual_public_streams"],
        )
        self.assertEqual(counts.get("cohort_researched"),1, result["dual_public_streams"])
        self.assertTrue(result["dual_public_streams"]["paper_cycle"]["historical_rest_warmup_enabled"])
        self.assertFalse(result["orders_sent"])
        self.assertFalse(result["public_feed_confirmed_24h_continuous"])
        self.assertEqual(len(tuple(self.j2.glob("rest-history-d461-*.json"))),1)
        self.assertEqual(len(tuple(self.j2.glob("n50-d451-*.sqlite"))),1)
        with sqlite3.connect(next(self.j2.glob("n50-d451-*.sqlite"))) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM confirmed").fetchone()[0],50)
        self.assertEqual(len(self.calls),53)  # 50 historical REST + 3 new N50 selection

    def test_one_command_auto_selects_and_captures_rest_before_ws_closed_paper(self):
        from urllib.parse import urlsplit, parse_qs
        existing = self.responses.copy()
        def complete_transport(url, max_size):
            self.calls.append(url)
            if "/v5/market/kline?" in url:
                args = parse_qs(urlsplit(url).query)
                return json.dumps(historical_payload(
                    args["symbol"][0],
                    int(args["start"][0]), int(args["end"][0])+1,
                )).encode("ascii")
            return json.dumps(existing[url]).encode("ascii")
        self.client = BoundedBybitPublicClient(transport=complete_transport)
        result, ks, ts = self.run_once(auto_capture_rest_warmup=True)
        self.assertEqual(result["status"], "finite_public_paper_research_closed")
        self.assertTrue(result["preclosed_rest_history_warmup_enabled"])
        self.assertEqual(result["dual_public_streams"]["accepted_closed_callbacks"],50)
        self.assertEqual(result["dual_public_streams"]["paper_cycle"]["event_counts"].get(
            "cohort_researched"),1)
        self.assertEqual(len(self.calls),53)
        self.assertEqual(len(tuple(self.j2.glob("rest-history-d461-*.json"))),1)
        self.assertFalse(result["orders_sent"])
        self.assertFalse(result["public_feed_confirmed_24h_continuous"])

    def test_auto_warmup_refuses_incomplete_last_closed_ws_cohort(self):
        from urllib.parse import urlsplit, parse_qs
        old = self.responses.copy()
        def transport(url, max_size):
            self.calls.append(url)
            if "/v5/market/kline?" in url:
                args = parse_qs(urlsplit(url).query)
                return json.dumps(historical_payload(
                    args["symbol"][0], int(args["start"][0]),
                    int(args["end"][0])+1,
                )).encode("ascii")
            return json.dumps(old[url]).encode("ascii")
        self.client = BoundedBybitPublicClient(transport=transport)
        result, _, _ = self.run_once(
            auto_capture_rest_warmup=True, omit_close="ALT1USDT",
        )
        paper = result["dual_public_streams"]["paper_cycle"]
        self.assertEqual(result["dual_public_streams"]["accepted_closed_callbacks"],49)
        self.assertFalse(paper["research_cohort_complete"])
        self.assertEqual(paper["eligible_relative_btc_hypotheses"],0)
        self.assertEqual(paper["pending_paper_open_count"],0)
        self.assertFalse(result["orders_sent"])

    def test_missing_explicit_operator_optin_is_zero_io(self):
        denied, k, t = self.run_once(allow=False)
        self.assertEqual(denied["status"], "six_explicit_paper_public_data_optins_required")
        self.assertEqual(self.calls, [])
        self.assertEqual(k.sent, [])
        self.assertEqual(t.sent, [])
        self.assertFalse(tuple(self.j2.glob("n50-d451-*.sqlite")))


if __name__ == "__main__":
    unittest.main()
