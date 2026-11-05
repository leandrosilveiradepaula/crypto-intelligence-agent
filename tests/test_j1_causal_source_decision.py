"""OPS32 pure-offline, adversarial Bybit/Binance causal-source tests."""
from __future__ import annotations

from dataclasses import replace
import json
import unittest

from crypto_intelligence_agent.j1_causal_source_decision import (
    HOUR_MS, REST_SETTLE_MS, SourceEvidence, decide_causal_source,
)

CLOSE = 1_793_847_600_000  # 2026-11-05T03:00Z, all tests synthetic
START = CLOSE - HOUR_MS
END = CLOSE - 1
RECEIVED = CLOSE + 80_000
WS_RECEIVED = CLOSE + 2_000
SYMBOL = "BTCUSDT"
O, H, L, C, V, Q = ("100.00", "105.00", "99.00", "102.00", "2.50", "250.25")


def bybit_ws(*, stamp=END-100, confirmed=True):
    return SourceEvidence("bybit_v5_linear", "ws", SYMBOL, "1h", {
        "topic": "kline.60.BTCUSDT", "type": "snapshot", "ts": CLOSE+1_000,
        "data": [{"start": START, "end": END, "interval": "60",
                  "open": O, "high": H, "low": L, "close": C,
                  "volume": V, "turnover": Q,
                  "confirm": confirmed, "timestamp": stamp}],
    }, WS_RECEIVED, ack_verified=True)


def bybit_rest():
    return SourceEvidence("bybit_v5_linear", "rest", SYMBOL, "1h", {
        "retCode": 0, "retMsg": "OK", "result": {
            "category": "linear", "symbol": SYMBOL,
            "list": [[str(START), O, H, L, C, V, Q]],
        },
    }, RECEIVED, requested_at_ms=CLOSE+REST_SETTLE_MS+1)


def binance_ws(*, final=True):
    return SourceEvidence("binance_usdm", "ws", SYMBOL, "1h", {
        "e": "kline", "E": CLOSE+1_000, "s": SYMBOL,
        "k": {"t": START, "T": END, "s": SYMBOL, "i": "1h",
              "f": 100, "L": 110, "o": O, "c": C, "h": H,
              "l": L, "v": V, "n": 10, "x": final, "q": Q,
              "V": "1.2", "Q": "120", "B": "0"},
    }, WS_RECEIVED, ack_verified=True)


def binance_rest():
    return SourceEvidence("binance_usdm", "rest", SYMBOL, "1h", [
        [START, O, H, L, C, V, END, Q, 10, "1.2", "120", "0"]
    ], RECEIVED, requested_at_ms=CLOSE+REST_SETTLE_MS+1)


def decide(e, venue=None):
    if not isinstance(e, tuple):
        e = (e,)
    return decide_causal_source(
        expected_venue=venue or e[0].venue,
        expected_symbol=SYMBOL, evidence=e,
    )


class OPS32CausalTests(unittest.TestCase):
    def test_causal_closed_bybit_ws_research_only(self):
        r = decide(bybit_ws())
        self.assertEqual((r.status, r.selected_transport, r.sources_checked),
                         ("source_closed_research_unverified", "ws", 1))
        flags = r.sanitized_report()
        self.assertFalse(any(flags[k] for k in (
            "ws_candle_approved", "canonical_ohlcv_approved",
            "source_authenticated", "continuous_collector_authorized",
            "marketwide_top50_verified", "live_trading_authorized", "orders_sent")))
        self.assertEqual((flags["network_requests"], flags["storage_writes"]), (0, 0))
        for private in ("BTCUSDT", "100.00", str(CLOSE), str(START), "Bybit"):
            self.assertNotIn(private, json.dumps(flags))

    def test_ops31_two_overruns_keep_quarantine_even_with_rest(self):
        anomalous = bybit_ws(stamp=END+200)
        for other in ((anomalous,), (anomalous, bybit_rest())):
            with self.subTest(n=len(other)):
                r = decide(other)
                self.assertEqual(r.status, "bybit_ws_stamp_overrun_quarantine")
                self.assertIsNone(r.selected_transport)
                self.assertFalse(r.values_corrob_same_venue)
        self.assertEqual(decide(bybit_ws(stamp=END+1)).status,
                         "bybit_ws_stamp_overrun_quarantine")

    def test_same_venue_equality_not_independent_authentication(self):
        for pair in ((bybit_ws(), bybit_rest()),
                     (binance_ws(), binance_rest())):
            with self.subTest(venue=pair[0].venue):
                r = decide(pair)
                self.assertEqual(r.status, "source_closed_research_unverified")
                self.assertTrue(r.values_corrob_same_venue)
                self.assertEqual(r.selected_transport, "ws")
                self.assertFalse(r.sanitized_report()["source_authenticated"])

    def test_bybit_rest_after_cutoff_without_explicit_finality(self):
        self.assertEqual(decide(bybit_rest()).selected_transport, "rest")
        self.assertEqual(decide(replace(bybit_rest(), requested_at_ms=CLOSE+REST_SETTLE_MS)).selected_transport, "rest")
        for req in (None, CLOSE-1, CLOSE, CLOSE+30_000):
            with self.subTest(req=req):
                self.assertNotEqual(decide(replace(bybit_rest(), requested_at_ms=req)).status,
                                    "source_closed_research_unverified")

    def test_binance_explicit_x_close_and_event_time(self):
        self.assertEqual(decide(binance_ws()).selected_transport, "ws")
        self.assertEqual(decide(binance_ws(final=False)).status,
                         "source_open_candle_abstain")
        p = binance_ws().payload
        for event_time in (END, CLOSE+RECEIVED, RECEIVED+1):
            with self.subTest(event_time=event_time):
                self.assertEqual(decide(replace(binance_ws(), payload={**p, "E": event_time})).status,
                                 "source_clock_abstain")

    def test_venue_mismatch_never_auto_fallback_or_mix_prices(self):
        self.assertEqual(decide((bybit_rest(), binance_rest()),
                                venue="bybit_v5_linear").status,
                         "source_venue_or_scope_abstain")
        self.assertEqual(decide(binance_ws(), venue="bybit_v5_linear").status,
                         "source_venue_or_scope_abstain")
        self.assertEqual(decide(replace(binance_ws(), symbol="ETHUSDT")).status,
                         "source_venue_or_scope_abstain")
        self.assertEqual(decide(replace(binance_ws(), interval="1m")).status,
                         "source_venue_or_scope_abstain")

    def test_no_duplicate_or_forged_transport(self):
        self.assertEqual(decide((bybit_ws(), bybit_ws())).status,
                         "source_duplicate_or_transport_abstain")
        self.assertEqual(decide(replace(bybit_ws(), transport="synthetic")).status,
                         "source_duplicate_or_transport_abstain")
        self.assertEqual(decide_causal_source(expected_venue="bad", expected_symbol=SYMBOL,
                                               evidence=(bybit_ws(),)).status,
                         "source_config_abstain")
        self.assertEqual(decide_causal_source(expected_venue="bybit_v5_linear",
                                               expected_symbol=SYMBOL,
                                               evidence=()).status,
                         "source_config_abstain")

    def test_cross_hour_false_corroboration_rejected(self):
        second = binance_rest()
        rows = [list(second.payload[0])]
        rows[0][0] += HOUR_MS
        rows[0][6] += HOUR_MS
        shifted = replace(second, payload=rows,
                          requested_at_ms=second.requested_at_ms+HOUR_MS,
                          received_at_ms=second.received_at_ms+HOUR_MS)
        self.assertEqual(decide((binance_ws(), shifted)).status,
                         "source_hours_diverge_abstain")

    def test_divergent_same_venue_ohlcv_rejected(self):
        data = binance_rest().payload
        corrupt = [list(data[0])]
        corrupt[0][4] = "101.00"
        self.assertEqual(decide((binance_ws(), replace(binance_rest(), payload=corrupt))).status,
                         "source_values_diverge_abstain")

    def test_no_lookahead_or_stale_replay(self):
        for receipt in (CLOSE-1, CLOSE, CLOSE+600_001, CLOSE+HOUR_MS+2):
            with self.subTest(receipt=receipt):
                self.assertNotEqual(decide(replace(binance_ws(), received_at_ms=receipt)).status,
                                    "source_closed_research_unverified")
        self.assertEqual(decide(replace(binance_rest(), received_at_ms=CLOSE+600_001)).status,
                         "source_window_abstain")

    def test_bad_clock_metadata_rest(self):
        for requested in (RECEIVED+1, True, -1):
            with self.subTest(requested=requested):
                self.assertNotEqual(decide(replace(binance_rest(), requested_at_ms=requested)).status,
                                    "source_closed_research_unverified")
        self.assertEqual(decide(replace(binance_rest(), ack_verified=True)).status,
                         "source_window_abstain")
        self.assertEqual(decide(replace(bybit_ws(), ack_verified=False)).status,
                         "source_ack_abstain")
        self.assertEqual(decide(replace(binance_ws(), requested_at_ms=CLOSE+2)).status,
                         "source_ack_abstain")

    def test_bybit_malformed_and_open(self):
        self.assertEqual(decide(bybit_ws(confirmed=False)).status,
                         "source_open_candle_abstain")
        p = bybit_ws().payload
        variants = (
            {**p, "topic": "kline.60.ETHUSDT"},
            {**p, "data": [*p["data"], *p["data"]]},
            {**p, "data": [{**p["data"][0], "confirm": 1}]},
            {**p, "data": [{**p["data"][0], "high": "NaN"}]},
            {**p, "data": [{**p["data"][0], "volume": "0", "turnover": Q}]},
        )
        for v in variants:
            with self.subTest(v=v):
                self.assertNotEqual(decide(replace(bybit_ws(), payload=v)).status,
                                    "source_closed_research_unverified")

    def test_bad_binance_schema_numerics(self):
        p = binance_ws().payload
        k = p["k"]
        bads = (
            {**p, "s": "ETHUSDT"},
            {**p, "k": {**k, "T": END+1}},
            {**p, "k": {**k, "q": "Infinity"}},
            {**p, "k": {**k, "h": "90.0"}},
            {**p, "k": {**k, "n": True}},
            {**p, "k": {**k, "V": "-1.0"}},
            {**p, "k": {**k, "x": 1}},
            {**p, "k": {**k, "mystery": "extra"}},
        )
        for payload in bads:
            with self.subTest(payload=payload):
                self.assertNotEqual(decide(replace(binance_ws(), payload=payload)).status,
                                    "source_closed_research_unverified")

    def test_rest_contracts_no_extra_unclosed_rows(self):
        b = bybit_rest()
        p = b.payload
        for changed in (
            {**p, "retCode": 10006},
            {**p, "result": {**p["result"], "list": []}},
            {**p, "result": {**p["result"], "list": p["result"]["list"]*2}},
            {**p, "result": {**p["result"], "category": "inverse"}},
        ):
            with self.subTest(changed=changed):
                self.assertEqual(decide(replace(b, payload=changed)).status,
                                 "source_schema_abstain")
        e = binance_rest()
        self.assertEqual(decide(replace(e, payload=[e.payload[0], e.payload[0]])).status,
                         "source_schema_abstain")
        row = list(e.payload[0]); row[6] += 1
        self.assertEqual(decide(replace(e, payload=[row])).status,
                         "source_window_abstain")

    def test_all_paths_are_offline_and_no_writes(self):
        for candidate in (bybit_ws(), bybit_rest(), binance_ws(), binance_rest()):
            with self.subTest(transport=candidate.transport, venue=candidate.venue):
                report = decide(candidate).sanitized_report()
                self.assertEqual(report["network_requests"], 0)
                self.assertEqual(report["storage_writes"], 0)
                self.assertFalse(report["orders_sent"])
                self.assertFalse(report["canonical_ohlcv_approved"])


if __name__ == "__main__":
    unittest.main()
