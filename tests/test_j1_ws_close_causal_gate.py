"""OPS27: causal rollover quarantine is offline, atomic and non-authorizing."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import json
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.bybit_linear_candle_research import (
    BybitLinearCandlePageResearch, BybitLinearCandleResearch,
)
from crypto_intelligence_agent.j1_ws_close_causal_gate import (
    audit_causal_rollover_offline, MAX_AUDIT_FRAMES,
)

HOUR = 3_600_000
START = (1_800_000_000_000 // HOUR) * HOUR
END = START + HOUR - 1
RECEIVED = END + 2001
TOPIC = "kline.60.BTCUSDT"


def frame(*, confirm=True, stamp=None, server=RECEIVED - 400):
    return {
        "topic": TOPIC, "type": "snapshot", "ts": server,
        "data": [{
            "start": START, "end": END, "interval": "60",
            "open": "1.00", "high": "1.03", "low": "0.99",
            "close": "1.01", "volume": "2.50", "turnover": "3.00",
            "confirm": confirm,
            "timestamp": END + 500 if stamp is None else stamp,
        }],
    }


def reference():
    candle = BybitLinearCandleResearch(
        symbol="BTCUSDT", quote_currency="USDT", interval="1h",
        open_time_ms=START, close_time_ms=END,
        open=Decimal("1.00"), high=Decimal("1.03"),
        low=Decimal("0.99"), close=Decimal("1.01"),
        documented_base_volume=Decimal("2.5"),
        documented_quote_turnover=Decimal("3"))
    return BybitLinearCandlePageResearch(
        symbol="BTCUSDT", quote_currency="USDT", interval="1h",
        start_open_ms=START, end_open_ms=START + HOUR,
        observed_at_ms=RECEIVED + 1000, candles=(candle,))


class OPS27CausalGateTests(unittest.TestCase):
    def audit(self, frames=None, **opts):
        events = ((frame(), RECEIVED),) if frames is None else frames
        with patch("socket.create_connection",
                   side_effect=AssertionError("network forbidden")):
            return audit_causal_rollover_offline(
                events=events, expected_topic=TOPIC,
                ack_verified=True, **opts)

    def test_match_is_quarantined_and_never_authorizes(self):
        result = self.audit(reference=reference())
        self.assertEqual(result.status, "causal_gate_same_venue_match_quarantined")
        self.assertEqual((result.fields_compared, result.fields_equal), (6, 6))
        report = result.sanitized_report()
        self.assertEqual(report["closed_stamp_after_2_to_1000ms"], 1)
        self.assertFalse(report["ws_candle_approved"])
        self.assertFalse(report["continuous_collector_authorized"])
        self.assertFalse(report["marketwide_top50_verified"])
        self.assertEqual(report["network_requests"], 0)
        self.assertEqual(report["storage_writes"], 0)
        self.assertFalse(report["orders_sent"])
        payload = json.dumps(report)
        for secret in ("BTCUSDT", str(START), str(END), "1.03", "2.50"):
            self.assertNotIn(secret, payload)

    def test_stamp_overrun_bands_are_disjoint(self):
        for over, key in (
            (1, "closed_stamp_after_1ms"),
            (2, "closed_stamp_after_2_to_1000ms"),
            (1000, "closed_stamp_after_2_to_1000ms"),
            (1001, "closed_stamp_after_1001_to_5000ms"),
            (5000, "closed_stamp_after_1001_to_5000ms"),
            (5001, "closed_stamp_after_over_5000ms"),
        ):
            with self.subTest(over=over):
                f = frame(stamp=END + over, server=END + over + 500)
                at = END + over + 1000
                z = self.audit(frames=((f, at),))
                self.assertEqual(z.status, "causal_gate_stamp_overrun_quarantined")
                self.assertEqual(z.sanitized_report()[key], 1)
                self.assertEqual(sum(z.bands), 1)

    def test_strict_stamp_does_not_activate_collection(self):
        f = frame(stamp=END)
        z = self.audit(frames=((f, RECEIVED),))
        self.assertEqual(z.status, "causal_gate_strict_stamp_observed_unverified")
        self.assertFalse(z.sanitized_report()["continuous_collector_authorized"])

    def test_open_update_and_close_in_same_frame_are_counted(self):
        f = frame()
        opening = dict(f["data"][0], confirm=False, timestamp=END)
        f["data"].append(opening)
        z = self.audit(frames=((f, RECEIVED),), reference=reference())
        self.assertEqual(z.status, "causal_gate_same_venue_match_quarantined")
        self.assertEqual(z.sanitized_report()["open_stamp_within_interval"], 1)
        self.assertEqual(z.rows_validated, 2)

    def test_open_overrun_is_observed_but_not_approved(self):
        f = frame(confirm=False)
        z = self.audit(frames=((f, RECEIVED),))
        self.assertEqual(z.status, "causal_gate_no_closed_candle_abstain")
        self.assertEqual(z.sanitized_report()["open_stamp_after_2_to_1000ms"], 1)
        self.assertEqual(z.fields_compared, 0)

    def test_six_financial_mismatches_remain_quarantined(self):
        for field, bad in (
            ("open", "1.001"), ("high", "1.031"),
            ("low", "0.989"), ("close", "1.011"),
            ("volume", "2.501"), ("turnover", "3.001"),
        ):
            with self.subTest(field=field):
                f = frame()
                f["data"][0][field] = bad
                z = self.audit(frames=((f, RECEIVED),), reference=reference())
                self.assertEqual(z.status, "causal_gate_same_venue_diverge_abstain")
                self.assertEqual((z.fields_compared, z.fields_equal), (6, 5))

    def test_duplicate_close_and_invalid_second_row_zero_counts(self):
        f = frame()
        f["data"].append(dict(f["data"][0]))
        z = self.audit(frames=((f, RECEIVED),), reference=reference())
        self.assertEqual(z.status, "causal_gate_duplicate_close_abstain")
        self.assertEqual(sum(z.bands), 0)
        self.assertEqual(z.fields_compared, 0)
        f = frame()
        f["data"].append(dict(f["data"][0], high="-1", confirm=False))
        z = self.audit(frames=((f, RECEIVED),), reference=reference())
        self.assertEqual(z.status, "causal_gate_row_abstain")
        self.assertEqual(sum(z.bands), 0)

    def test_bad_clocks_time_grid_and_stale_close_reject(self):
        cases = (
            (frame(server=RECEIVED + 1), RECEIVED),
            (frame(server=RECEIVED - 30_001), RECEIVED),
            (frame(stamp=START - 1), RECEIVED),
            (frame(), END + 120_002),
            (frame(), START + HOUR // 2),
            (frame(), RECEIVED),
        )
        for idx, (f, at) in enumerate(cases):
            if idx == 5:
                f["data"][0]["start"] = START + 1
            with self.subTest(case=idx):
                z = self.audit(frames=((f, at),))
                self.assertTrue(z.status.endswith("_abstain"))
                self.assertEqual(sum(z.bands), 0)
        first = frame()
        second = frame()
        z = self.audit(frames=((first, RECEIVED), (second, RECEIVED - 1)))
        self.assertEqual(z.status, "causal_gate_clock_abstain")

    def test_bad_shape_topic_types_and_fields_reject(self):
        cases = (
            {"topic": "kline.60.ETHUSDT"},
            {"type": "delta"},
            {"unexpected": "secret"},
            {"data": []},
            {"data": [frame()["data"][0]] * 9},
            {"data": ["corrupt"]},
        )
        for mutate in cases:
            with self.subTest(keys=list(mutate)):
                f = frame()
                f.update(mutate)
                z = self.audit(frames=((f, RECEIVED),))
                self.assertTrue(z.status.endswith("_abstain"))
                self.assertEqual(sum(z.bands), 0)
                self.assertNotIn("secret", json.dumps(z.sanitized_report()))
        for key, bad in (
            ("confirm", 1), ("timestamp", True),
            ("high", "0.9"), ("volume", "NaN"),
            ("interval", "15"),
        ):
            with self.subTest(field=key):
                f = frame()
                f["data"][0][key] = bad
                z = self.audit(frames=((f, RECEIVED),))
                self.assertEqual(z.status, "causal_gate_row_abstain")

    def test_reference_mismatch_or_fabrication_blocks(self):
        wrong = replace(reference(), symbol="ETHUSDT")
        z = self.audit(reference=wrong)
        self.assertEqual(z.status, "causal_gate_reference_abstain")
        self.assertEqual(sum(z.bands), 0)
        wrong = replace(reference(), observed_at_ms=RECEIVED - 1)
        self.assertEqual(self.audit(reference=wrong).status,
                         "causal_gate_reference_abstain")

    def test_ack_absence_and_caps_block_without_partial_output(self):
        missing = audit_causal_rollover_offline(
            events=((frame(), RECEIVED),), expected_topic=TOPIC)
        self.assertEqual(missing.status, "causal_gate_ack_or_topic_abstain")
        self.assertEqual(missing.rows_validated, 0)
        self.assertEqual(self.audit(frames=()).status,
                         "causal_gate_input_abstain")
        self.assertEqual(self.audit(frames=tuple((frame(), RECEIVED)
                             for _ in range(MAX_AUDIT_FRAMES + 1))).status,
                         "causal_gate_input_abstain")
        self.assertEqual(self.audit(frames=((frame(), RECEIVED),),
                                   reference=object()).status,
                         "causal_gate_reference_abstain")


if __name__ == "__main__":
    unittest.main()
