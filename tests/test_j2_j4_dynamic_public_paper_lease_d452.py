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
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.bybit_closed_stream_cache import HOUR_MS
from crypto_intelligence_agent.bybit_public_j1_transport import (
    BoundedBybitPublicClient, instruments_url, tickers_url,
)
from crypto_intelligence_agent.j2_j4_dual_public_supervisor_d450 import (
    run_dynamic_public_paper_lease_once,
)
from test_j2_dynamic_public_n50_d451 import NOW, scenario
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

    def run_once(self, *, hour=0, allow=True):
        opened = ((NOW // HOUR_MS) + 1 + hour) * HOUR_MS
        closed = opened + HOUR_MS - 1
        received = closed + 2001
        members = ["BTCUSDT"] + [f"ALT{i}USDT" for i in range(1, 60)]
        # The public rolling 24h selector omits the weakest member, ALT59.
        # ALT1..ALT49 + BTC form the 50 subscribed cohort.
        chosen = members[:50]
        frames = [(ack(), received - 100)]
        for symbol in chosen:
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
        ksession = Session(kc, frames)
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
        tsession = Session(tc, ticker_frames)
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

    def test_missing_explicit_operator_optin_is_zero_io(self):
        denied, k, t = self.run_once(allow=False)
        self.assertEqual(denied["status"], "six_explicit_paper_public_data_optins_required")
        self.assertEqual(self.calls, [])
        self.assertEqual(k.sent, [])
        self.assertEqual(t.sent, [])
        self.assertFalse(tuple(self.j2.glob("n50-d451-*.sqlite")))


if __name__ == "__main__":
    unittest.main()
