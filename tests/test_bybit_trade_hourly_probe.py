"""J1 #253: fake transport only; the production probe is owner-only."""
from __future__ import annotations

from datetime import date
import unittest
from unittest.mock import patch

from scripts.probe_bybit_archive_week import probe_week, ORIGIN
from test_bybit_archive_week import samples


class FakeResponse:
    def __init__(self, url, payload):
        self.url = url
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def getcode(self):
        return 200

    def geturl(self):
        return self.url

    def read(self, size):
        return self.payload[:size]


class WeeklyHourlyQualityProbeTests(unittest.TestCase):
    def test_unapproved_options_never_contact_network(self):
        for network, weekly in ((False, False), (False, True), (True, False)):
            out = probe_week(
                allow_public_network=network, allow_weekly_archive_probe=weekly,
                audit_hourly_quality=True,
                opened=lambda *args, **kwargs: self.fail("unapproved network"),
            )
            self.assertEqual(out["requests_attempted"], 0)
            self.assertFalse(out["orders_sent"])

    def test_exact_seven_get_receipt_never_contains_price_or_volume(self):
        data = samples(date(2020, 3, 25))
        calls = []

        def open_archive(request, *, timeout):
            i = len(calls)
            calls.append(request.full_url)
            self.assertEqual(request.get_method(), "GET")
            self.assertEqual(request.full_url, ORIGIN + data[i][0])
            self.assertEqual(timeout, 10)
            return FakeResponse(request.full_url, data[i][1])

        with patch("socket.create_connection", side_effect=AssertionError("network")):
            receipt = probe_week(
                allow_public_network=True, allow_weekly_archive_probe=True,
                audit_hourly_quality=True, opened=open_archive,
            )
        self.assertEqual(receipt["status"], "unverified_historical_week_observed")
        self.assertEqual(len(calls), 7)
        self.assertEqual(receipt["requests_attempted"], 7)
        hourly = receipt["hourly_research"]
        self.assertEqual(hourly["trade_derived_hour_count"], 7)
        self.assertEqual(hourly["hours_without_trades_observed"], 161)
        self.assertEqual(hourly["ambiguous_boundary_hour_count"], 0)
        self.assertEqual(hourly["unambiguous_boundary_hour_count"], 7)
        for gate in (
            "rights_authorized", "source_authenticated",
            "canonical_ohlcv_approved", "financial_backtest_approved",
            "live_trading_authorized", "orders_sent",
        ):
            self.assertFalse(hourly[gate])
        for secret in ("9000.5", "1.25", "11250.625", "BTCUSDT", ORIGIN):
            self.assertNotIn(secret, str(receipt))

    def test_legacy_weekly_mode_does_not_export_hourly_data(self):
        fixtures = samples(date(2020, 3, 25))
        calls = []

        def open_archive(request, *, timeout):
            i = len(calls)
            calls.append(request.full_url)
            return FakeResponse(request.full_url, fixtures[i][1])

        receipt = probe_week(
            allow_public_network=True, allow_weekly_archive_probe=True,
            opened=open_archive,
        )
        self.assertEqual(len(calls), 7)
        self.assertNotIn("hourly_research", receipt)
        self.assertFalse(receipt["canonical_ohlcv_approved"])


if __name__ == "__main__":
    unittest.main()
