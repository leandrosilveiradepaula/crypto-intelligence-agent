"""J1/WU25: all smoke tests are mocked, NO real network."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

from crypto_intelligence_agent.hyperliquid_native_research import (
    stage_hyperliquid_native_perp_candles,
)
from scripts.probe_hyperliquid_native_info import (
    HOUR_MS, INFO_URL, MAX_META_BYTES, InfoSmokeError,
    _post_info, inspect_once, main,
)


NOW = int(datetime(2026, 10, 25, 17, 30, tzinfo=timezone.utc).timestamp() * 1000)
BASE = NOW // HOUR_MS * HOUR_MS
START = BASE - 4 * HOUR_MS
END = BASE - HOUR_MS


def meta():
    return [
        {"universe": [
            {"name": "BTC", "maxLeverage": 40, "szDecimals": 5},
            {"name": "kPEPE", "maxLeverage": 10, "szDecimals": 0},
        ]},
        [
            {"dayNtlVlm": "12345678.99999999", "markPx": "100000.1111",
             "openInterest": "10.123", "funding": "-0.0001"},
            {"dayNtlVlm": "50", "markPx": "0.001", "openInterest": "20",
             "funding": "0"},
        ],
    ]


def candles():
    return [
        {"t": START + k * HOUR_MS, "T": START + (k+1) * HOUR_MS - 1,
         "s": "BTC", "i": "1h", "o": str(100000+k),
         "h": str(100100+k), "l": str(99900+k),
         "c": str(100001+k), "v": f"1.{k}876543210", "n": 100+k}
        for k in range(3)
    ]


class FakeReply:
    def __init__(self, data, status=200, mime="application/json", url=INFO_URL):
        self.data = data if type(data) is bytes else json.dumps(data).encode()
        self.status = status
        self.url = url
        self.headers = {"Content-Type": mime}

    def getcode(self):
        return self.status

    def geturl(self):
        return self.url

    def read(self, max_bytes):
        return self.data[:max_bytes]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class Responses:
    def __init__(self, first=None, second=None):
        self.queue = [first or FakeReply(meta()), second or FakeReply(candles())]
        self.calls = []

    def __call__(self, req, *, timeout):
        self.calls.append((req, timeout))
        return self.queue[len(self.calls)-1]


def probe(opener=None, *, at=NOW, **flags):
    return inspect_once(
        allow_public_network=flags.get("network", True),
        allow_hyperliquid_info=flags.get("info", True),
        clock_ms=lambda: at, opened=opener or Responses(),
    )


class HyperliquidInfoSmokeTests(unittest.TestCase):
    def test_fixed_order_two_informational_posts_only(self):
        fake = Responses()
        result = probe(fake)
        self.assertEqual(result["status"], "schema_observed_no_live_readiness")
        self.assertEqual(result["requests_attempted"], 2)
        self.assertEqual(result["native_instrument_count"], 2)
        self.assertEqual(result["closed_candle_count"], 3)
        self.assertEqual(result["coin"], "BTC")
        self.assertEqual(result["interval"], "1h")
        self.assertEqual(result["requested_window_start_ms"], START)
        self.assertEqual(result["requested_window_end_ms_exclusive"], END)
        self.assertEqual(len(result["metaAndAssetCtxs_sha256"]), 64)
        self.assertEqual(len(result["candleSnapshot_sha256"]), 64)
        reqs = [req for req, timeout in fake.calls]
        self.assertEqual([req.get_method() for req in reqs], ["POST", "POST"])
        self.assertEqual([req.full_url for req in reqs], [INFO_URL, INFO_URL])
        self.assertEqual([timeout for _, timeout in fake.calls], [8, 8])
        first, second = [json.loads(req.data) for req in reqs]
        self.assertEqual(first, {"type": "metaAndAssetCtxs", "dex": ""})
        self.assertEqual(second, {"type": "candleSnapshot", "req": {
            "coin": "BTC", "interval": "1h", "startTime": START,
            "endTime": END - 1,
        }})
        for request in reqs:
            self.assertEqual(request.get_header("Content-type"), "application/json")
            self.assertEqual(request.get_header("Accept"), "application/json")
            headers = {key.lower() for key in request.headers}
            for prohibited in ("authorization", "cookie", "x-api-key"):
                self.assertNotIn(prohibited, headers)

    def test_report_contains_no_prices_wallets_or_volume_values(self):
        report = probe()
        output = json.dumps(report, sort_keys=True).lower()
        for prohibited in ("100000.1111", "12345678.99999999", "0.0001",
                           "kpepe", "openinterest", "funding", "wallet",
                           "position", "public_feed_authorized"):
            self.assertNotIn(prohibited, output)
        for gate in ("crypto_identity_verified", "volume_unit_verified",
                     "external_data_rights_verified", "ready_for_live_top50",
                     "ready_for_canonical_ohlcv", "credentials_used",
                     "orders_sent", "raw_responses_persisted"):
            self.assertIs(report[gate], False)

    def test_same_input_replay_is_deterministic_except_transient_no_data(self):
        self.assertEqual(probe(), probe())
        self.assertEqual(probe()["observed_at_utc"], "2026-10-25T17:30:00+00:00")

    def test_double_opt_in_prevents_all_network(self):
        for network, info in ((False, False), (True, False), (False, True), (1, True)):
            with self.subTest(network=network, info=info):
                fake = Mock(side_effect=AssertionError("network must not be used"))
                with self.assertRaisesRegex(InfoSmokeError, "double_opt_in_required"):
                    inspect_once(allow_public_network=network,
                                 allow_hyperliquid_info=info,
                                 clock_ms=lambda: NOW, opened=fake)
                fake.assert_not_called()

    def test_invalid_clock_rejected_before_first_request(self):
        for val in (True, 0, None, "now", 1.5, -5):
            fake = Mock()
            with self.subTest(val=val), self.assertRaises(InfoSmokeError):
                probe(fake, at=val)
            fake.assert_not_called()

    def test_meta_http_fail_does_not_request_candles(self):
        for status in (403, 418, 429, 451, 503, 302):
            fake = Responses(first=FakeReply({}, status=status))
            result = probe(fake)
            self.assertEqual(result["requests_attempted"], 1)
            self.assertEqual(len(fake.calls), 1)
            self.assertIn(result["status"], (
                "unexpected_http_status", "access_or_rate_restricted",
            ))

    def test_first_payload_errors_are_fail_closed_with_one_request(self):
        for data in (
            b"", b"\xff", b"{", b'{"x":1,"x":2}', b'{"a":NaN}',
            b'{"price":1.5}', b"{}",
        ):
            fake = Responses(first=FakeReply(data))
            result = probe(fake)
            with self.subTest(data=data[:15]):
                self.assertEqual(result["requests_attempted"], 1)
                self.assertNotEqual(result["status"], "schema_observed_no_live_readiness")

    def test_metadata_btc_missing_delisted_or_duplicate_stops_second(self):
        first = meta()
        missing = deepcopy(first)
        missing[0]["universe"][0]["name"] = "ETH"
        delisted = deepcopy(first)
        delisted[0]["universe"][0]["isDelisted"] = True
        duplicate = deepcopy(first)
        duplicate[0]["universe"][1]["name"] = "BTC"
        for data in (missing, delisted, duplicate):
            fake = Responses(first=FakeReply(data))
            with self.subTest(data=data):
                out = probe(fake)
                self.assertEqual(out["status"], "invalid_provider_schema")
                self.assertEqual(len(fake.calls), 1)

    def test_k_prefixed_native_universe_is_not_hip3(self):
        native = meta()
        out = stage_hyperliquid_native_perp_candles(
            native, candles(), symbol="BTC", dex_scope="", interval="1h",
            start_open_ms=START, end_open_ms=END,
            context_observed_at_ms=NOW, observed_at_ms=NOW,
            max_context_age_ms=0, close_safety_ms=1000, max_candles=3)
        self.assertEqual(len(out.candles), 3)
        self.assertFalse(out.ready_for_live_top50)
        with_colon = deepcopy(native)
        with_colon[0]["universe"][1]["name"] = "xyz:NVDA"
        bad = Responses(first=FakeReply(with_colon))
        self.assertEqual(probe(bad)["requests_attempted"], 1)
        self.assertEqual(probe(bad)["status"], "invalid_provider_schema")

    def test_meta_bad_status_mime_host_size(self):
        bad_replies = (
            FakeReply(meta(), mime="text/html"),
            FakeReply(meta(), url="https://evil.example/info"),
            FakeReply(b"X"*(MAX_META_BYTES+1)),
            FakeReply(meta(), status=201),
        )
        for resp in bad_replies:
            fake = Responses(first=resp)
            with self.subTest(url=resp.url, status=resp.status):
                result = probe(fake)
                self.assertEqual(result["requests_attempted"], 1)
                self.assertNotEqual(result["status"], "schema_observed_no_live_readiness")

    def test_candle_http_or_json_error_returns_only_sanitized_status(self):
        for reply in (FakeReply({}, status=429), FakeReply({}, mime="text/html"),
                      FakeReply(b"not valid JSON"), FakeReply([])):
            fake = Responses(second=reply)
            with self.subTest(reply=reply):
                self.assertNotEqual(
                    probe(fake)["status"], "schema_observed_no_live_readiness"
                )
                self.assertEqual(len(fake.calls), 2)

    def test_candle_no_trades_or_gap_is_not_approved(self):
        one = candles()
        one[1]["n"] = 0
        two = candles()
        two[1]["t"] += 1
        three = candles()
        three.pop()
        for rows in (one, two, three):
            fake = Responses(second=FakeReply(rows))
            result = probe(fake)
            self.assertEqual(result["status"], "invalid_provider_schema")
            self.assertFalse(result["ready_for_canonical_ohlcv"])

    def test_candle_future_partial_price_float_and_zero_volume(self):
        for field, value in (("T", END + HOUR_MS), ("o", 1.234),
                             ("v", "0"), ("s", "ETH"), ("n", True)):
            rows = candles()
            rows[2][field] = value
            with self.subTest(field=field):
                self.assertNotEqual(
                    probe(Responses(second=FakeReply(rows)))["status"],
                    "schema_observed_no_live_readiness",
                )

    def test_bounded_meta_and_candle_bytes(self):
        rows = candles()
        huge = json.dumps(rows).encode() + b" " * 40_000
        fake = Responses(second=FakeReply(huge))
        self.assertEqual(probe(fake)["status"], "response_size_invalid")

    def test_network_errors_are_sanitized(self):
        for error in (TimeoutError("PRIVATE_TOKEN"), OSError("SECRET_HIDDEN")):
            for fail_at in (1, 2):
                fake = Responses()
                underlying = fake.__call__
                def opened(req, *, timeout):
                    if len(fake.calls)+1 == fail_at:
                        fake.calls.append((req, timeout))
                        raise error
                    return underlying(req, timeout=timeout)
                result = probe(opened)
                self.assertEqual(result["status"], "network_failure")
                self.assertEqual(result["requests_attempted"], fail_at)
                self.assertNotIn("PRIVATE_TOKEN", str(result))
                self.assertNotIn("SECRET_HIDDEN", str(result))

    def test_duplicate_second_json_key_is_rejected(self):
        fake = Responses(second=FakeReply(b'[{"t":1,"t":2}]'))
        self.assertEqual(probe(fake)["status"], "duplicate_json_key")

    def test_unapproved_post_request_type_cannot_be_sent(self):
        fake = Mock()
        with self.assertRaisesRegex(InfoSmokeError, "unapproved_info_request"):
            _post_info({"type": "order"}, size_limit=1,
                       opened=fake, audit={"requests_attempted": 0})
        fake.assert_not_called()

    def test_cli_requires_both_flags_without_attempt(self):
        for flags in ([], ["--allow-public-network"],
                      ["--allow-hyperliquid-info-probe"]):
            with self.subTest(flags=flags), self.assertRaises(SystemExit) as e:
                main(flags)
            self.assertEqual(e.exception.code, 2)

    def test_cli_emits_sanitized_one_line_json_only(self):
        sanitized = probe()
        buf = io.StringIO()
        with patch("scripts.probe_hyperliquid_native_info.inspect_once",
                   return_value=sanitized), redirect_stdout(buf):
            self.assertEqual(main(["--allow-public-network",
                                   "--allow-hyperliquid-info-probe"]), 0)
        self.assertEqual(json.loads(buf.getvalue()), sanitized)

    def test_no_response_body_exposed_on_wrong_json(self):
        fake = Responses(first=FakeReply(b'{"password":"SHOULD_NOT_PRINT"}'))
        out = probe(fake)
        self.assertEqual(out["status"], "invalid_provider_schema")
        self.assertNotIn("SHOULD_NOT_PRINT", json.dumps(out))

    def test_only_two_requests_no_redirect_aware_custom_host(self):
        fake = Responses()
        probe(fake)
        self.assertEqual(len(fake.calls), 2)
        self.assertTrue(all(x.full_url == INFO_URL for x, _ in fake.calls))


if __name__ == "__main__":
    unittest.main()
