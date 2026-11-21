"""D461: dynamic 50 x 24 REST closed candles -> immutable J2 research, no WS spoofs."""
from __future__ import annotations

from decimal import Decimal
import json
import os
from pathlib import Path
import tempfile
import unittest
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from crypto_intelligence_agent.bybit_public_j1_transport import BoundedBybitPublicClient
from crypto_intelligence_agent.j2_rest_n50_history_d461 import (
    capture_rest_n50_24h, read_rest_n50_24h, research_rest_n50_24h,
    reopen_frozen_rest_n50_for_research,
)
from crypto_intelligence_agent.j2_observed_bybit_research import (
    evaluate_observed_bybit_research,
)
from crypto_intelligence_agent.j2_bybit_closed_research_bridge import (
    BybitClosedResearchSeries,
)
from crypto_intelligence_agent.market_data import DataGapError, DataValidationError
from test_j2_dynamic_public_n50_d451 import NOW, selected
from test_j2_j4_public_paper_cycle_d449 import SETTINGS

HOUR = 3_600_000
END = NOW // HOUR * HOUR


def historical_payload(symbol, start, end):
    bars = []
    for n in range(23, -1, -1):
        opened = start + n * HOUR
        v = Decimal("100") + Decimal(n) / Decimal(10)
        bars.append([
            str(opened), format(v, "f"), format(v + 1, "f"),
            format(v - 1, "f"), format(v, "f"),
            "10", "1000",
        ])
    return {"retCode": 0, "result": {
        "category": "linear", "symbol": symbol, "list": bars,
    }}


@unittest.skipUnless(
    os.name == "posix" and hasattr(os, "geteuid") and os.geteuid() != 0,
    "POSIX owner-only REST research",
)
class ImmutableRestN50Tests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="cia-d461-")
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name)
        self.home.chmod(0o700)
        self.snapshot = selected(at=NOW)
        self.calls = []
        self.broken_symbol = None

        def transport(url, limit):
            self.calls.append(url)
            qs = parse_qs(urlsplit(url).query)
            symbol = qs["symbol"][0]
            start = int(qs["start"][0])
            end = int(qs["end"][0]) + 1
            data = historical_payload(symbol, start, end)
            if symbol == self.broken_symbol:
                data["result"]["list"].pop()
            return json.dumps(data, separators=(",", ":")).encode("ascii")

        self.client = BoundedBybitPublicClient(transport=transport)
        self.flags = dict(
            allow_public_network=True,
            confirm_personal_readonly_research=True,
            confirm_region_eligible=True,
            confirm_public_data_rights=True,
        )

    def capture(self, *, client=None, snapshot=None):
        return capture_rest_n50_24h(
            snapshot=snapshot or self.snapshot,
            private_j2_directory=self.home,
            client=client or self.client,
            wall_ms=lambda: NOW + 1500,
            **self.flags,
        )

    def test_complete_1200_closed_immutable_rest_research_and_replay(self):
        with patch("socket.create_connection",
                   side_effect=AssertionError("offline transport should not network")):
            history = self.capture()
        self.assertEqual(len(self.calls), 50)
        self.assertEqual(history.sanitized_report()["validated_closed_candles"], 1200)
        self.assertEqual(history.sanitized_report()["websocket_confirmed_candles"], 0)
        self.assertTrue(history.snapshot_file.exists())
        self.assertEqual(history.snapshot_file.stat().st_mode & 0o777, 0o600)
        self.assertEqual(history.source_mode, "injected_offline_protocol_replay")
        self.assertFalse(tuple(self.home.glob("*.sqlite")))
        reopened = read_rest_n50_24h(
            snapshot=self.snapshot, private_j2_directory=self.home,
            window_end_ms=END,
        )
        self.assertEqual(history, reopened)
        # The original frozen REST history must remain usable after the
        # ticker cohort/membership/clock moves; research reads no new GETs.
        frozen = reopen_frozen_rest_n50_for_research(
            private_j2_directory=self.home,
            filename=history.snapshot_file.name,
        )
        self.assertEqual(frozen, history)
        self.assertEqual(len(self.calls), 50)
        report = research_rest_n50_24h(history=history,
                                       config=SETTINGS.research)
        self.assertEqual(report["closed_candles_analyzed"], 1200)
        self.assertEqual(report["members_analyzed"], 50)
        self.assertEqual(len(report["rows"]), 50)
        self.assertEqual(report["total_quote_turnover_usdt"], "1200000")
        self.assertFalse(report["approved_for_signals"])
        self.assertFalse(report["orders_sent"])
        self.assertTrue(all(row["provenance"].startswith("public_rest")
                            for row in report["rows"]))
        self.assertFalse(tuple(self.home.glob("paper-*.sqlite")))

    def test_hourly_worker_reuses_same_frozen_1200_candles_after_new_n50_clock(self):
        initial = self.capture()
        first_calls = len(self.calls)
        from test_j2_dynamic_public_n50_d451 import selected
        refreshed = selected(
            received=(NOW+9500,NOW+9700),
            at=NOW+10_000,
        )
        self.assertEqual(refreshed.fingerprint_sha256,
                         self.snapshot.fingerprint_sha256)
        from crypto_intelligence_agent.j2_rest_n50_history_d461 import (
            capture_rest_n50_24h,
        )
        reused = capture_rest_n50_24h(
            snapshot=refreshed,private_j2_directory=self.home,
            client=self.client,wall_ms=lambda:NOW+10_050,**self.flags,
        )
        self.assertEqual(reused.digest_sha256,initial.digest_sha256)
        self.assertEqual(reused.snapshot_file,initial.snapshot_file)
        self.assertEqual(reused.captured_at_ms,initial.captured_at_ms)
        self.assertEqual(len(self.calls),first_calls)
        self.assertEqual(len(tuple(self.home.glob("rest-history-d461-*.json"))),1)

    def test_malformed_symbol_fails_all_or_none_without_snapshot(self):
        self.broken_symbol = "ALT25USDT"
        with self.assertRaises(DataGapError):
            self.capture()
        self.assertEqual(list(self.home.iterdir()), [])

    def test_frozen_replay_is_not_a_fresh_ws_or_auto2_signal(self):
        history = self.capture()
        replayed = reopen_frozen_rest_n50_for_research(
            private_j2_directory=self.home,
            filename=history.snapshot_file.name,
        )
        scan = research_rest_n50_24h(
            history=replayed, config=SETTINGS.research,
        )
        self.assertEqual(scan["closed_candles_analyzed"], 1200)
        self.assertEqual(scan["websocket_confirmed_candles"], 0)
        self.assertFalse(scan["approved_for_signals"])
        with self.assertRaises(DataValidationError):
            reopen_frozen_rest_n50_for_research(
                private_j2_directory=self.home,
                filename="../" + history.snapshot_file.name,
            )

    def test_tamper_and_duplicate_json_fail_without_refetch(self):
        history = self.capture()
        prior = len(self.calls)
        history.snapshot_file.write_text('{"schema":"broken"}')
        history.snapshot_file.chmod(0o600)
        with self.assertRaises(DataGapError):
            read_rest_n50_24h(
                snapshot=self.snapshot, private_j2_directory=self.home,
                window_end_ms=END,
            )
        with self.assertRaises(DataGapError):
            self.capture()
        self.assertEqual(len(self.calls), prior)

    def test_explicit_rest_research_does_not_admit_rest_candles_into_ws_only(self):
        history = self.capture()
        rows = dict(history.series)
        self.assertEqual(rows["BTCUSDT"][-1].quality,
                         "bybit_public_rest_historical_closed_unverified")
        fake_from_rest = BybitClosedResearchSeries(
            rows["BTCUSDT"], history.digest_sha256, history.scope_sha256,
            "research_only_public_closed_series",
        )
        # D447 invokes the D435 default, never the explicit REST history
        # flag. Rejecting this prevents retroactive REST from becoming WS.
        with self.assertRaises(DataValidationError):
            evaluate_observed_bybit_research(
                fake_from_rest, config=SETTINGS.research,
                decision_at_ms=END,
            )
        expected = evaluate_observed_bybit_research(
            fake_from_rest, config=SETTINGS.research,
            decision_at_ms=END, allow_rest_historical_research=True,
        )
        self.assertEqual(expected.evaluated_candle_count, 24)
        self.assertFalse(expected.approved_for_signals)

    def test_denied_auth_does_not_issue_even_one_request(self):
        with self.assertRaises(DataValidationError):
            capture_rest_n50_24h(
                snapshot=self.snapshot,
                private_j2_directory=self.home,
                client=self.client, wall_ms=lambda: NOW+1500,
                allow_public_network=True,
                confirm_personal_readonly_research=True,
                confirm_region_eligible=True,
            )
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
