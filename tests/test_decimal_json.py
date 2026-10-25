"""Exact financial JSON decoding; no exchange, credentials or float rounding."""
from __future__ import annotations

from decimal import Decimal
import unittest

from crypto_intelligence_agent.decimal_json import (
    MAX_PUBLIC_JSON_BYTES, decode_public_market_json_exact,
    positive_market_decimal,
)
from crypto_intelligence_agent.market_data import DataValidationError


class ExactJsonMarketTests(unittest.TestCase):
    def test_big_decimal_fractions_survive_direct_json_decode(self):
        raw = b'{"tickers":[{"symbol":"PF_XBTUSD","volumeQuote":331016603.137412345678901234,"vol24h":3928.249900000000123456}]}'
        payload = decode_public_market_json_exact(raw)
        row = payload["tickers"][0]
        self.assertEqual(row["volumeQuote"], Decimal("331016603.137412345678901234"))
        self.assertEqual(row["vol24h"], Decimal("3928.249900000000123456"))
        self.assertIs(type(row["vol24h"]), Decimal)
        self.assertEqual(
            positive_market_decimal(row["volumeQuote"], "quote"),
            Decimal("331016603.137412345678901234"),
        )

    def test_ordinary_json_ints_remain_exact_integers(self):
        p = decode_public_market_json_exact(
            b'{"observed_at_ms":1792936800000,"size":1,"tiny":0.000000000000000001}'
        )
        self.assertIs(type(p["observed_at_ms"]), int)
        self.assertEqual(p["tiny"], Decimal("0.000000000000000001"))
        self.assertEqual(p["size"], 1)

    def test_scientific_json_numbers_are_exact_decimals_not_binary_floats(self):
        p = decode_public_market_json_exact('{"v":1e-18,"w":9.876543210987654321e+7}')
        self.assertEqual(p["v"], Decimal("1e-18"))
        self.assertEqual(p["w"], Decimal("9.876543210987654321e+7"))

    def test_float_from_any_previous_decoder_is_rejected(self):
        rounded = float("331016603.137412345678901234")
        with self.assertRaisesRegex(DataValidationError, "never float"):
            positive_market_decimal(rounded, "volumeQuote")
        with self.assertRaises(DataValidationError):
            positive_market_decimal(float("nan"), "volumeQuote")
        with self.assertRaises(DataValidationError):
            positive_market_decimal(True, "volumeQuote")
        with self.assertRaises(DataValidationError):
            positive_market_decimal(None, "volumeQuote")

    def test_finite_decimal_string_and_integer_are_supported_without_precision_loss(self):
        self.assertEqual(
            positive_market_decimal("0.000000000000000000000001", "volume"),
            Decimal("0.000000000000000000000001"),
        )
        self.assertEqual(positive_market_decimal(20, "volume"), Decimal(20))
        self.assertEqual(positive_market_decimal(Decimal("22.500000"), "volume"),
                         Decimal("22.500000"))
        for invalid in ("", "0", "NaN", "Infinity", "-10.2", "1e3", "+12", "01.5",
                        "1.0000000000000000000000001", Decimal("Infinity")):
            with self.subTest(value=invalid):
                with self.assertRaises(DataValidationError):
                    positive_market_decimal(invalid, "volume")

    def test_reject_duplicate_json_keys_to_avoid_ambiguous_fields(self):
        for raw in (
            '{"volumeQuote":12.5,"volumeQuote":999999999}',
            '{"tickers":[{"symbol":"PF_XBTUSD","symbol":"PF_AAPLXUSD"}]}',
        ):
            with self.subTest(raw=raw):
                with self.assertRaisesRegex(DataValidationError, "duplicate"):
                    decode_public_market_json_exact(raw)

    def test_reject_nonstandard_nan_infinity_and_overlong_exponents(self):
        for raw in (
            '{"volumeQuote":NaN}', '{"volumeQuote":Infinity}',
            '{"volumeQuote":-Infinity}', '{"volumeQuote":1e9999}',
            '{"volumeQuote":1e-9999}',
            '{"volumeQuote":0.0000000000000000000000001}',
            '{"volumeQuote":12345678901234567890123456789012345678901234567890}',
        ):
            with self.subTest(raw=raw):
                with self.assertRaises(DataValidationError):
                    decode_public_market_json_exact(raw)

    def test_payload_size_and_json_root_are_constrained(self):
        with self.assertRaises(DataValidationError):
            decode_public_market_json_exact(b"", max_bytes=10)
        with self.assertRaises(DataValidationError):
            decode_public_market_json_exact(b"{} " + b"x" * 25, max_bytes=10)
        for raw in (b'[]', b'"hello"', b'null', b'invalid'):
            with self.subTest(raw=raw):
                with self.assertRaises(DataValidationError):
                    decode_public_market_json_exact(raw)
        with self.assertRaises(DataValidationError):
            decode_public_market_json_exact(b"{\xff}")
        with self.assertRaises(DataValidationError):
            decode_public_market_json_exact("unpaired_surrogate:\ud800")
        for size in (True, -1, 0, 1.3, MAX_PUBLIC_JSON_BYTES + 1):
            with self.subTest(size=size):
                with self.assertRaises(ValueError):
                    decode_public_market_json_exact("{}", max_bytes=size)

    def test_decimal_source_is_not_automatically_a_verified_market_unit(self):
        data = decode_public_market_json_exact(
            b'{"volume":415.123456789123456789,"quote":"USD"}'
        )
        self.assertEqual(data["volume"], Decimal("415.123456789123456789"))
        self.assertNotIn("base_volume", data)
        self.assertNotIn("quote_volume", data)
        self.assertNotIn("unit_proof", data)


if __name__ == "__main__":
    unittest.main()
