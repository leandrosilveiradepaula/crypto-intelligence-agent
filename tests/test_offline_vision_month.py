"""J1/HIST #229: synthetic monthly ZIP only; no market download."""
from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO, StringIO
import calendar
import csv
import unittest
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile

from crypto_intelligence_agent.market_data import DataValidationError, ClosedCandle
from crypto_intelligence_agent.offline_vision_month import (
    OfflineVisionMonth, OfflineVisionCandle, inspect_offline_vision_month,
)

HOUR = 3_600_000


def synthetic_zip(*, year=2025, month=2, symbol="BTCUSDT", omit=None,
                  duplicate=None, mutate=None, member=None, compression=ZIP_DEFLATED):
    name = f"{symbol}-1h-{year:04d}-{month:02d}"
    start = int(datetime(year, month, 1, tzinfo=timezone.utc).timestamp() * 1000)
    count = calendar.monthrange(year, month)[1] * 24
    rows = []
    for index in range(count):
        if index == omit:
            continue
        tick = start + index * HOUR
        row = [str(tick), "100", "105", "95", "101", "12.5",
               str(tick + HOUR - 1), "1250", "20", "5", "505", "0"]
        if mutate is not None and mutate[0] == index:
            row[mutate[1]] = mutate[2]
        rows.append(row)
        if index == duplicate:
            rows.append(row)
    sink = StringIO(newline="")
    csv.writer(sink, lineterminator="\n").writerows(rows)
    output = BytesIO()
    with ZipFile(output, "w", compression=compression) as zf:
        zf.writestr(member if member is not None else name + ".csv",
                    sink.getvalue().encode("ascii"))
    blob = output.getvalue()
    end = start + count * HOUR
    return blob, name + ".zip", sha256(blob).hexdigest(), end + 1000


def parse(blob, name, digest, as_of):
    return inspect_offline_vision_month(
        blob, archive_name=name, expected_sha256=digest, as_of_ms=as_of,
    )


class OfflineVisionMonthTests(unittest.TestCase):
    def test_complete_month_february_and_december_are_unverified_only(self):
        for year, month in ((2025, 2), (2024, 2), (2025, 12)):
            with self.subTest(year=year, month=month):
                blob, name, digest, cutoff = synthetic_zip(year=year, month=month)
                with patch("socket.create_connection",
                           side_effect=AssertionError("network forbidden")):
                    month_report = parse(blob, name, digest, cutoff)
                self.assertIsInstance(month_report, OfflineVisionMonth)
                self.assertEqual(len(month_report.candles),
                                 calendar.monthrange(year, month)[1] * 24)
                self.assertIsInstance(month_report.candles[0], OfflineVisionCandle)
                self.assertNotIsInstance(month_report.candles[0], ClosedCandle)
                self.assertEqual(month_report.candles[0].documented_quote_volume, 1250)
                self.assertEqual(month_report.candles[-1].close_time_ms,
                                 month_report.end_open_exclusive_ms - 1)
                for flag in ("provider_authenticated", "dataset_rights_authorized",
                             "canonical_ohlcv_approved", "ready_for_trading",
                             "live_trading_authorized", "orders_sent"):
                    self.assertFalse(getattr(month_report, flag))
                    with self.assertRaises(TypeError):
                        replace(month_report, **{flag: True})
                with self.assertRaises(FrozenInstanceError):
                    month_report.quality = "approved"

    def test_refuse_truncated_duplicate_and_wrong_timestamp(self):
        for variant in (
            {"omit": 12}, {"duplicate": 12},
            {"mutate": (12, 0, "1700000000000")},
            {"mutate": (12, 6, "1700000000001")},
        ):
            with self.subTest(variant=variant):
                blob, name, digest, cutoff = synthetic_zip(**variant)
                with self.assertRaises(DataValidationError):
                    parse(blob, name, digest, cutoff)

    def test_bad_ohlc_volume_nan_and_wrong_column_count(self):
        for field, bad in ((1, "NaN"), (2, "99"), (3, "120"),
                           (5, "-1"), (7, "-1"), (4, "Infinity")):
            with self.subTest(field=field, value=bad):
                blob, name, digest, cutoff = synthetic_zip(mutate=(2, field, bad))
                with self.assertRaises(DataValidationError):
                    parse(blob, name, digest, cutoff)
        blob, name, digest, cutoff = synthetic_zip(mutate=(2, 7, ""))
        with self.assertRaises(DataValidationError):
            parse(blob, name, digest, cutoff)

    def test_exact_observed_vision_headers_and_months_accepted(self):
        # Header-only aliases are observed from SSH; the data column order is
        # unchanged and must still pass the canonical OHLC validator.
        legacy = ("open_time,open,high,low,close,volume,close_time,"
                  "quote_asset_volume,number_of_trades,taker_buy_base_asset_volume,"
                  "taker_buy_quote_asset_volume,ignore")
        observed = ("open_time,open,high,low,close,volume,close_time,"
                    "quote_volume,count,taker_buy_volume,taker_buy_quote_volume,ignore")

        def modify(year, month, prefix="", suffix=""):
            blob, name, _, cutoff = synthetic_zip(year=year, month=month)
            with ZipFile(BytesIO(blob)) as src:
                payload = src.read(name[:-4] + ".csv").decode("ascii")
            output = BytesIO()
            with ZipFile(output, "w", compression=ZIP_DEFLATED) as zf:
                zf.writestr(name[:-4] + ".csv",
                            (prefix + payload + suffix).encode("utf-8"))
            data = output.getvalue()
            return data, name, sha256(data).hexdigest(), cutoff

        for year, month, count in ((2025, 2, 672), (2026, 8, 744),
                                    (2026, 9, 720)):
            for header in (legacy, observed):
                with self.subTest(year=year, month=month, variant=header[60:83]):
                    blob, name, digest, cutoff = modify(
                        year, month, prefix=header + "\n"
                    )
                    report = parse(blob, name, digest, cutoff)
                    self.assertEqual(len(report.candles), count)
                    self.assertEqual(report.candles[0].documented_quote_volume, 1250)
                    self.assertFalse(report.canonical_ohlcv_approved)
                    self.assertFalse(report.live_trading_authorized)

        # Never silently skip unknown/mixed headers. Numeric rows must still be
        # exact and a known header may occur only once at the beginning.
        malformed = (
            observed + "\n" + observed + "\n",  # repeated header
            observed.replace("quote_volume,count", "quote_asset_volume,count") + "\n",
            observed.replace("quote_volume,count", "count,quote_volume") + "\n",
            observed.replace("taker_buy_volume", "taker_buy_base_asset_volume") + "\n",
            observed + ",extra\n",
            observed.replace("volume", "size", 1) + "\n",
            "\ufeff" + observed + "\n",
        )
        for prefix in malformed:
            with self.subTest(bad=prefix[:50]):
                blob, name, digest, cutoff = modify(2026, 8, prefix=prefix)
                with self.assertRaises(DataValidationError):
                    parse(blob, name, digest, cutoff)

        for header in (legacy, observed):
            blob, name, digest, cutoff = modify(2026, 9, suffix="\n" + header)
            with self.assertRaises(DataValidationError):
                parse(blob, name, digest, cutoff)

    def test_archive_path_and_digest_must_match(self):
        for member in ("../BTCUSDT.csv", "random.csv", "BTCUSDT-1h-2025-02.csv/"):
            blob, name, digest, cutoff = synthetic_zip(member=member)
            with self.subTest(member=member), self.assertRaises(DataValidationError):
                parse(blob, name, digest, cutoff)
        blob, name, digest, cutoff = synthetic_zip()
        with self.assertRaisesRegex(DataValidationError, "digest mismatch"):
            parse(blob, name, "0"*64, cutoff)
        with self.assertRaises(DataValidationError):
            parse(blob, "../" + name, digest, cutoff)

    def test_reject_future_archive_wrong_input_type_and_size(self):
        blob, name, digest, cutoff = synthetic_zip()
        for moment in (cutoff - 1, True, "1750000000000"):
            with self.subTest(moment=moment), self.assertRaises(DataValidationError):
                parse(blob, name, digest, moment)
        for bad in ("zip", None, bytearray(blob), b""):
            with self.subTest(type=type(bad).__name__), self.assertRaises(DataValidationError):
                parse(bad, name, digest, cutoff)
        with self.assertRaises(DataValidationError):
            parse(b"x"*8_000_001, name, digest, cutoff)

    def test_cannot_self_certify_a_source_or_licence(self):
        blob, name, digest, cutoff = synthetic_zip()
        result = parse(blob, name, digest, cutoff)
        self.assertEqual(result.quality, "unverified_offline_personal_research_only")
        self.assertFalse(hasattr(result, "source_authenticated"))
        self.assertFalse(hasattr(result, "approved_for_live_use"))
        with self.assertRaises(TypeError):
            replace(result, provider_authenticated=True)
        self.assertEqual(parse(blob, name, digest, cutoff), result)

    def test_member_not_allowed_when_zip_metadata_is_bomb_or_encrypted(self):
        blob, name, digest, cutoff = synthetic_zip()
        tampered = bytearray(blob)
        # Local header flag bits: encryption; central directory bits also set.
        pos = tampered.find(bytes.fromhex("504b0102"))
        self.assertGreaterEqual(pos, 0)
        tampered[pos+8] |= 1
        digest2 = sha256(tampered).hexdigest()
        with self.assertRaises(DataValidationError):
            parse(bytes(tampered), name, digest2, cutoff)


if __name__ == "__main__":
    unittest.main()
