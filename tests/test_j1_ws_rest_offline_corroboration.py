"""J1/OPS21 regression: offline-only, no REST/socket/journal dependency."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import json
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.bybit_linear_candle_research import (
    BybitLinearCandlePageResearch, BybitLinearCandleResearch,
)
from crypto_intelligence_agent.bybit_ws_rest_offline_corroboration import (
    HOUR_MS, corroborate_anomalous_close_offline,
)
from crypto_intelligence_agent.market_data import DataValidationError

START = (1_800_000_000_000 // HOUR_MS) * HOUR_MS
END = START + HOUR_MS - 1
RECEIVED = END + 2001
SYMBOL = "BTCUSDT"


def ws():
    return {
        "topic": "kline.60." + SYMBOL, "type": "snapshot",
        "ts": RECEIVED - 500,
        "data": [{
            "start": START, "end": END, "interval": "60",
            "open": "1.00", "high": "1.03", "low": "0.99",
            "close": "1.01", "volume": "2.50", "turnover": "3.00",
            "confirm": True, "timestamp": END + 500,
        }],
    }


def rest():
    candle = BybitLinearCandleResearch(
        symbol=SYMBOL, quote_currency="USDT", interval="1h",
        open_time_ms=START, close_time_ms=END,
        open=Decimal("1"), high=Decimal("1.03"),
        low=Decimal("0.99"), close=Decimal("1.01"),
        documented_base_volume=Decimal("2.5"),
        documented_quote_turnover=Decimal("3"),
    )
    return BybitLinearCandlePageResearch(
        symbol=SYMBOL, quote_currency="USDT", interval="1h",
        start_open_ms=START, end_open_ms=START + HOUR_MS,
        observed_at_ms=RECEIVED + 1000, candles=(candle,),
    )


class OfflineCorroborationTests(unittest.TestCase):
    def compare(self, frame=None, reference=None, received=RECEIVED):
        with patch("socket.create_connection", side_effect=AssertionError("network forbidden")):
            return corroborate_anomalous_close_offline(
                frame=ws() if frame is None else frame,
                reference=rest() if reference is None else reference,
                received_at_ms=received,
            )

    def test_exact_six_fields_match_without_any_approval(self):
        a = self.compare()
        self.assertEqual(a.status, "offline_values_match_unverified")
        self.assertEqual((a.fields_compared, a.fields_equal), (6, 6))
        report = a.sanitized_report()
        self.assertFalse(report["ws_candle_approved"])
        self.assertFalse(report["historical_reference_authenticated"])
        self.assertFalse(report["canonical_ohlcv_approved"])
        self.assertFalse(report["live_trading_authorized"])
        self.assertEqual((report["network_requests"], report["storage_writes"], report["orders_sent"]), (0, 0, False))
        for secret in (SYMBOL, str(START), str(END), "1.03", "2.50"):
            self.assertNotIn(secret, json.dumps(report))

    def test_each_financial_difference_remains_abstention(self):
        mutations = {
            "open": "1.002", "high": "1.031", "low": "0.989",
            "close": "1.011", "volume": "2.5001", "turnover": "3.001",
        }
        for key, value in mutations.items():
            with self.subTest(field=key):
                f = ws()
                f["data"][0][key] = value
                r = self.compare(frame=f)
                self.assertEqual(r.status, "offline_values_diverge_abstain")
                self.assertEqual((r.fields_compared, r.fields_equal), (6, 5))
                self.assertFalse(r.sanitized_report()["ws_candle_approved"])

    def test_wrong_hour_symbol_contract_and_reference_observation(self):
        original = rest()
        variants = [
            replace(original, symbol="ETHUSDT"),
            replace(original, quote_currency="USDC"),
            replace(original, interval="5m"),
            replace(original, start_open_ms=START - HOUR_MS),
            replace(original, end_open_ms=START + 2 * HOUR_MS),
            replace(original, observed_at_ms=RECEIVED - 1),
            replace(original, observed_at_ms=RECEIVED + 86_400_001),
            replace(original, candles=()),
            replace(original, candles=(original.candles[0],) * 2),
            replace(original, candles=(replace(original.candles[0], symbol="ETHUSDT"),)),
            replace(original, candles=(replace(original.candles[0], open_time_ms=START + HOUR_MS),)),
            replace(original, candles=(replace(original.candles[0], close_time_ms=END - 1),)),
        ]
        for value in variants:
            with self.subTest(value=str(value)[:80]):
                with self.assertRaises(DataValidationError):
                    self.compare(reference=value)

    def test_closed_stamp_must_actually_be_after_end(self):
        for stamp in (START - 1, START, END):
            with self.subTest(stamp=stamp):
                f = ws()
                f["data"][0]["timestamp"] = stamp
                with self.assertRaises(DataValidationError):
                    self.compare(frame=f)

    def test_ws_server_and_receipt_chronology(self):
        for receipt, server in (
            (END + 500, END + 300),
            (RECEIVED, END),
            (RECEIVED, RECEIVED + 1),
            (RECEIVED, RECEIVED - 30_001),
            (END + 120_002, END + 120_001),
        ):
            with self.subTest(receipt=receipt, server=server):
                f = ws()
                f["ts"] = server
                with self.assertRaises(DataValidationError):
                    self.compare(frame=f, received=receipt)

    def test_malformed_or_open_row_never_matches(self):
        cases = (
            ("confirm", False), ("confirm", 1), ("timestamp", True),
            ("interval", "5"), ("volume", "NaN"), ("high", "0.98"),
            ("turnover", "-1"), ("open", 1.0),
        )
        for name, value in cases:
            with self.subTest(field=name):
                f = ws()
                f["data"][0][name] = value
                with self.assertRaises(DataValidationError):
                    self.compare(frame=f)
        for rows in ([], ws()["data"] * 2):
            f = ws()
            f["data"] = rows
            with self.assertRaises(DataValidationError):
                self.compare(frame=f)

    def test_extra_frame_keys_and_unsupported_symbol_fail_closed(self):
        for mutate in (
            lambda f: f.update(secret="do-not-log"),
            lambda f: f.update(topic="kline.60.ETHUSDT"),
            lambda f: f.update(topic="kline.15.BTCUSDT"),
            lambda f: f.update(type="delta"),
        ):
            f = ws()
            mutate(f)
            with self.assertRaises(DataValidationError):
                self.compare(frame=f)

    def test_invalid_reference_financial_values_fail_closed(self):
        base = rest()
        for candle in (
            replace(base.candles[0], high=Decimal("0.98")),
            replace(base.candles[0], low=Decimal("1.04")),
            replace(base.candles[0], open=Decimal("NaN")),
            replace(base.candles[0], documented_base_volume=Decimal("-1")),
        ):
            with self.assertRaises(DataValidationError):
                self.compare(reference=replace(base, candles=(candle,)))

    def test_invalid_types_and_fake_rest_source_fail_closed(self):
        with self.assertRaises(DataValidationError):
            self.compare(received=True)
        with self.assertRaises(DataValidationError):
            self.compare(frame="not-an-object")
        with self.assertRaises(DataValidationError):
            self.compare(reference=replace(rest(), source="private_or_unverified"))
        with self.assertRaises(DataValidationError):
            self.compare(reference=replace(rest(), candles=(replace(rest().candles[0], unit_basis="wrong"),)))


if __name__ == "__main__":
    unittest.main()
