"""Offline transport/schema regression tests for bounded OKX private probe."""
from __future__ import annotations

from copy import deepcopy
from io import BytesIO
import json
import unittest
from urllib.error import HTTPError

from scripts.probe_okx_personal_candles import (
    CANDLES_URL, HOUR_MS, INSTRUMENTS_URL, ProbeError, _get, inspect_once,
)

NOW = 1_800_000_000_000
TOP = (NOW // HOUR_MS) * HOUR_MS


def metadata():
    return {"code": "0", "msg": "", "data": [{
        "instId": "BTC-USDT-SWAP", "instType": "SWAP",
        "ctType": "linear", "state": "live", "settleCcy": "USDT",
    }]}


def history():
    rows = []
    for i in range(6):
        opened = TOP - i * HOUR_MS
        rows.append([str(opened), "100", "110", "90", "101",
                     "3.001", "0.05", "7.999", "0" if i == 0 else "1"])
    return {"code": "0", "msg": "", "data": rows}


class Response:
    def __init__(self, payload, *, status=200, url=None,
                 content_type="application/json; charset=utf-8"):
        self.body = BytesIO(payload if isinstance(payload, bytes)
                            else json.dumps(payload).encode("utf-8"))
        self.status = status
        self.url = url
        self.headers = {"Content-Type": content_type}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def getcode(self):
        return self.status

    def geturl(self):
        return self.url or self._requested_url

    def read(self, limit):
        return self.body.read(limit)


class FakeOpen:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request, *, timeout):
        self.requests.append(request)
        assert timeout == 8
        assert request.get_method() == "GET"
        assert request.full_url in (INSTRUMENTS_URL, CANDLES_URL)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        response._requested_url = request.full_url
        return response


def run(opened, *, timepoints=(NOW, NOW + 100, NOW + 200)):
    times = iter(timepoints)
    return inspect_once(allow_public_network=True, allow_okx_personal_probe=True,
                        opened=opened, clock_ms=lambda: next(times))


class OkxPrivateProbeTests(unittest.TestCase):
    def test_two_bounded_gets_conformance_but_no_readiness(self):
        opened = FakeOpen(Response(metadata()), Response(history()))
        result = run(opened)
        self.assertEqual(result["status"], "observed_private_schema_only")
        self.assertEqual(result["requests_attempted"], 2)
        self.assertEqual(result["closed_candles_validated"], 3)
        self.assertEqual(result["documented_quote_currency"], "USDT")
        self.assertEqual([r.full_url for r in opened.requests],
                         [INSTRUMENTS_URL, CANDLES_URL])
        self.assertEqual(len(result["instruments_response_sha256"]), 64)
        self.assertEqual(len(result["candles_response_sha256"]), 64)
        for key in ("crypto_identity_verified", "canonical_ohlcv_approved",
                    "commercial_or_public_rights_verified", "ready_for_live_top50",
                    "ready_for_trading", "orders_sent", "credentials_used",
                    "raw_responses_persisted"):
            with self.subTest(key=key):
                self.assertFalse(result[key])
        self.assertNotIn("7.999", json.dumps(result))
        self.assertNotIn("documented_quote_volume", result)

    def test_double_optin_required_before_any_io(self):
        opened = FakeOpen()
        for a, b in ((False, False), (True, False), (False, True)):
            with self.subTest(a=a, b=b), self.assertRaisesRegex(
                ProbeError, "double_opt_in_required"
            ):
                inspect_once(allow_public_network=a, allow_okx_personal_probe=b,
                             opened=opened, clock_ms=lambda: NOW)
        self.assertEqual(opened.requests, [])

    def test_metadata_fail_closed_before_candle_get(self):
        for field, value in (("instId", "AAPL-USDT-SWAP"),
                             ("instType", "SPOT"), ("ctType", "inverse"),
                             ("state", "suspend"), ("settleCcy", "USD")):
            candidate = metadata()
            candidate["data"][0][field] = value
            opener = FakeOpen(Response(candidate))
            with self.subTest(field=field):
                result = run(opener)
                self.assertEqual(result["status"], "invalid_instrument_schema")
                self.assertEqual(result["requests_attempted"], 1)
                self.assertEqual(len(opener.requests), 1)

    def test_rejects_extra_or_missing_metadata(self):
        for data in ([], [metadata()["data"][0]] * 2):
            obj = metadata()
            obj["data"] = data
            result = run(FakeOpen(Response(obj)))
            self.assertEqual(result["status"], "invalid_instrument_envelope")

    def test_rejects_http451_without_second_call_or_retry(self):
        error = HTTPError(INSTRUMENTS_URL, 451, "blocked", {}, None)
        opener = FakeOpen(error)
        result = run(opener)
        self.assertEqual(result["status"], "access_or_rate_restricted")
        self.assertEqual(result["requests_attempted"], 1)
        self.assertEqual(len(opener.requests), 1)

    def test_rejects_untrusted_redirect_and_mime(self):
        opener = FakeOpen(Response(metadata(), url="https://elsewhere.invalid/"))
        self.assertEqual(run(opener)["status"], "redirect_or_wrong_host")
        opener = FakeOpen(Response(metadata(), content_type="text/html"))
        self.assertEqual(run(opener)["status"], "unexpected_content_type")

    def test_rejects_duplicate_json_keys(self):
        raw = b'{"code":"0","code":"0","msg":"","data":[]}'
        result = run(FakeOpen(Response(raw)))
        self.assertEqual(result["status"], "duplicate_json_key")
        self.assertEqual(result["requests_attempted"], 1)

    def test_incomplete_window_and_unconfirmed_bar(self):
        incomplete = history()
        incomplete["data"] = [row for row in incomplete["data"]
                              if row[0] != str(TOP - 3 * HOUR_MS)]
        self.assertEqual(
            run(FakeOpen(Response(metadata()), Response(incomplete)))["status"],
            "closed_window_incomplete")
        unconfirmed = history()
        unconfirmed["data"][3][8] = "0"
        self.assertEqual(
            run(FakeOpen(Response(metadata()), Response(unconfirmed)))["status"],
            "staged_candle_contract_rejected")

    def test_noncontiguous_and_invalid_volume_are_not_filled(self):
        shifted = history()
        shifted["data"][3][0] = str(TOP - 3 * HOUR_MS + 1)
        self.assertEqual(
            run(FakeOpen(Response(metadata()), Response(shifted)))["status"],
            "closed_window_incomplete")
        invalid = history()
        invalid["data"][3][7] = "NaN"
        self.assertEqual(
            run(FakeOpen(Response(metadata()), Response(invalid)))["status"],
            "staged_candle_contract_rejected")

    def test_clock_regression_or_span_exhausted(self):
        self.assertEqual(
            run(FakeOpen(Response(metadata())), timepoints=(NOW, NOW - 1))["status"],
            "capture_window_expired")
        self.assertEqual(
            run(FakeOpen(Response(metadata())), timepoints=(NOW, NOW + 30_001))["status"],
            "capture_window_expired")

    def test_get_disallows_other_hosts_even_with_injected_opener(self):
        report = {"requests_attempted": 0}
        with self.assertRaisesRegex(ProbeError, "unapproved_public_url"):
            _get("https://okx.com/other", opened=FakeOpen(),
                 report=report, digest_field="test")
        self.assertEqual(report["requests_attempted"], 0)

    def test_zero_volume_does_not_prove_live_trade(self):
        zero = deepcopy(history())
        for row in zero["data"]:
            row[5:8] = ["0", "0", "0"]
        self.assertEqual(
            run(FakeOpen(Response(metadata()), Response(zero)))["status"],
            "zero_observed_quote_volume")


if __name__ == "__main__":
    unittest.main()
