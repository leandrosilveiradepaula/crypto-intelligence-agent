"""J1 #256: no live GET in tests; mocked archive bytes are synthetic."""
from __future__ import annotations
from contextlib import redirect_stdout
from datetime import date
import gzip
from io import StringIO
import json
import unittest
from unittest.mock import patch

from scripts.probe_bybit_archive_week import probe_week, main, ORIGIN
from test_bybit_archive_week import samples
from crypto_intelligence_agent.bybit_public_trade_archive import FIELDS


class Response:
    def __init__(self, url, blob):
        self.url, self.blob = url, blob
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def getcode(self):
        return 200
    def geturl(self):
        return self.url
    def read(self, amount):
        return self.blob[:amount]


class BybitTradeFieldProbeTests(unittest.TestCase):
    def test_default_never_calls_network_even_when_diagnostic_requested(self):
        for network, weekly in ((False, False), (False, True), (True, False)):
            result = probe_week(
                allow_public_network=network,
                allow_weekly_archive_probe=weekly,
                audit_trade_field_consistency=True,
                opened=lambda *args, **kwargs: self.fail("unapproved transport"),
            )
            self.assertEqual(result["requests_attempted"], 0)
            self.assertNotIn("trade_field_consistency", result)
        printed = StringIO()
        with patch("scripts.probe_bybit_archive_week._open",
                   side_effect=AssertionError("unexpected network")):
            with redirect_stdout(printed):
                self.assertEqual(main(["--audit-trade-field-consistency"]), 1)
        self.assertEqual(json.loads(printed.getvalue())["requests_attempted"], 0)

    def test_bounded_seven_gets_report_field_relation_counts_only(self):
        data = samples(date(2020, 3, 25))
        requests = []
        def opened(request, *, timeout):
            index = len(requests)
            requests.append(request.full_url)
            self.assertLess(index, 7)
            self.assertEqual(request.get_method(), "GET")
            self.assertEqual(request.full_url, ORIGIN + data[index][0])
            self.assertEqual(timeout, 10)
            return Response(request.full_url, data[index][1])

        with patch("socket.create_connection", side_effect=AssertionError("network")):
            report = probe_week(
                allow_public_network=True, allow_weekly_archive_probe=True,
                audit_trade_field_consistency=True, audit_hourly_quality=True,
                opened=opened,
            )
        self.assertEqual(len(requests), 7)
        self.assertEqual(report["requests_attempted"], 7)
        self.assertEqual(report["status"], "unverified_historical_week_observed")
        self.assertEqual(report["trades"], 7)
        observed = report["trade_field_consistency"]
        self.assertEqual(observed["size_equals_home_trades"], 7)
        self.assertEqual(observed["size_differs_from_home_trades"], 0)
        self.assertEqual(observed["foreign_equals_price_times_home_trades"], 7)
        self.assertEqual(observed["foreign_differs_from_price_times_home_trades"], 0)
        self.assertEqual(report["hourly_research"]["trade_derived_hour_count"], 7)
        for flag in ("units_verified", "rights_authorized",
                     "canonical_ohlcv_approved", "financial_backtest_approved",
                     "live_trading_authorized", "orders_sent"):
            self.assertFalse(observed[flag])
        output = json.dumps(report, sort_keys=True)
        for secret in ("BTCUSDT", ORIGIN, "9000.5", "11250.625", "1.25"):
            self.assertNotIn(secret, output)

    def test_mismatch_is_observational_not_rejected_or_auto_converted(self):
        items = list(samples(date(2020, 3, 25)))
        first_name, first_bytes = items[0]
        body = gzip.decompress(first_bytes).decode()
        body = body.replace(",11250.625", ",11250.624")
        items[0] = (first_name, gzip.compress(body.encode(), mtime=0))
        requests = []
        def opened(request, *, timeout):
            index = len(requests)
            requests.append(request.full_url)
            return Response(request.full_url, items[index][1])
        result = probe_week(
            allow_public_network=True, allow_weekly_archive_probe=True,
            audit_trade_field_consistency=True, opened=opened,
        )
        self.assertEqual(len(requests), 7)
        self.assertEqual(result["trade_field_consistency"]["size_equals_home_trades"], 7)
        self.assertEqual(
            result["trade_field_consistency"][
                "foreign_differs_from_price_times_home_trades"], 1)
        self.assertFalse(result["trade_field_consistency"]["units_verified"])
        self.assertFalse(result["canonical_ohlcv_approved"])

    def test_previous_mode_output_unchanged(self):
        items = samples(date(2020, 3, 25))
        calls = []
        def opened(request, *, timeout):
            n = len(calls)
            calls.append(request.full_url)
            return Response(request.full_url, items[n][1])
        result = probe_week(
            allow_public_network=True, allow_weekly_archive_probe=True,
            opened=opened,
        )
        self.assertEqual(len(calls), 7)
        self.assertNotIn("trade_field_consistency", result)
        self.assertNotIn("hourly_research", result)


if __name__ == "__main__":
    unittest.main()
