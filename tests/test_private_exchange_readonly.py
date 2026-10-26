"""AUTH1 never talks to real exchanges during CI."""
import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from scripts.probe_private_exchange_readonly import (
    _sign_binance, _sign_bybit, diagnose, _strict_json,
)


class Response:
    status = 200
    headers = {"Content-Type": "application/json"}
    def __init__(self, body):
        self.stream = io.BytesIO(body)
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, limit):
        return self.stream.read(limit)


class FakeOpener:
    def __init__(self, body=b'{"dualSidePosition":false}', exc=None):
        self.body = body
        self.exc = exc
        self.calls = []
    def open(self, request, timeout):
        self.calls.append((request, timeout))
        if self.exc:
            raise self.exc
        return Response(self.body)


class ReadonlyProbeTests(unittest.TestCase):
    def setUp(self):
        self.binance = dict(BINANCE_READONLY_API_KEY="public_key", BINANCE_READONLY_API_SECRET="secret")
        self.bybit = dict(BYBIT_READONLY_API_KEY="public_key", BYBIT_READONLY_API_SECRET="secret")

    def test_network_off_without_both_flags(self):
        for a, b in ((False, False), (True, False), (False, True)):
            for venue in ("binance", "bybit"):
                client = FakeOpener()
                result = diagnose(venue, allow_private_read=a,
                                  confirm_read_only_key=b, opener=client,
                                  env=self.binance if venue == "binance" else self.bybit)
                self.assertEqual(result["status"], "offline_network_disabled")
                self.assertFalse(client.calls)

    def test_signed_binance_get_one_fixed_host_without_export(self):
        client = FakeOpener()
        out = diagnose("binance", allow_private_read=True,
                       confirm_read_only_key=True, env=self.binance,
                       now_ms=1700000000000, opener=client)
        self.assertEqual(out["status"], "authenticated_permissions_not_attested")
        self.assertEqual(len(client.calls), 1)
        req, timeout = client.calls[0]
        self.assertEqual(req.get_method(), "GET")
        self.assertEqual(req.full_url.split("?")[0], "https://fapi.binance.com/fapi/v1/positionSide/dual")
        self.assertIn("recvWindow=5000", req.full_url)
        self.assertIn("timestamp=1700000000000", req.full_url)
        self.assertIn("signature=", req.full_url)
        self.assertEqual(req.get_header("X-mbx-apikey"), "public_key")
        self.assertEqual(timeout, 8)
        self.assertFalse(out["orders_sent"])
        self.assertFalse(out["private_account_details_exported"])
        self.assertNotIn("dualSidePosition", out)
        self.assertNotIn("public_key", str(out))

    def test_signed_bybit_readonly_and_no_private_fields(self):
        client = FakeOpener(b'{"retCode":0,"result":{"readOnly":1,"uid":"sensitive"}}')
        out = diagnose("bybit", allow_private_read=True,
                       confirm_read_only_key=True, env=self.bybit,
                       now_ms=1700000000000, opener=client)
        self.assertEqual(out["status"], "authenticated_read_only_key_confirmed")
        req, _ = client.calls[0]
        self.assertEqual(req.full_url, "https://api.bybit.com/v5/user/query-api")
        self.assertEqual(req.get_method(), "GET")
        self.assertEqual(req.get_header("X-bapi-sign-type"), "2")
        self.assertEqual(req.get_header("X-bapi-timestamp"), "1700000000000")
        self.assertNotIn("sensitive", str(out))
        self.assertFalse(out["trading_enabled"])

    def test_bybit_non_readonly_is_blocked(self):
        for value in (0, "1", True, None):
            with self.subTest(value=value):
                body=json.dumps({"retCode":0,"result":{"readOnly":value}}).encode()
                out=diagnose("bybit",allow_private_read=True,
                             confirm_read_only_key=True,env=self.bybit,
                             opener=FakeOpener(body),now_ms=1700000000000)
                self.assertEqual(out["status"], "key_not_confirmed_read_only")

    def test_secret_absence_or_malformed_rejects_without_network(self):
        for env in ({}, {"BINANCE_READONLY_API_KEY":"x"},
                    {"BINANCE_READONLY_API_KEY":"x\n", "BINANCE_READONLY_API_SECRET":"y"},
                    {"BINANCE_READONLY_API_KEY":"x", "BINANCE_READONLY_API_SECRET":"x"*513}):
            client=FakeOpener()
            diagnose("binance",allow_private_read=True,
                     confirm_read_only_key=True,env=env,opener=client)
            self.assertEqual(client.calls, [])

    def test_http_errors_sanitized(self):
        for code, expected in ((401,"access_or_region_restricted"),
                               (403,"access_or_region_restricted"),
                               (418,"access_or_region_restricted"),
                               (451,"access_or_region_restricted"),
                               (429,"rate_limited"),
                               (500,"provider_http_error")):
            with self.subTest(code=code):
                exc=HTTPError("https://secret.invalid",code,"confidential",{},None)
                out=diagnose("binance",allow_private_read=True,
                             confirm_read_only_key=True,env=self.binance,
                             opener=FakeOpener(exc=exc))
                self.assertEqual(out["status"],expected)
                self.assertNotIn("confidential",str(out))

    def test_unavailable_network_sanitized(self):
        client=FakeOpener(exc=URLError("private secret"))
        out=diagnose("bybit",allow_private_read=True,
                     confirm_read_only_key=True,env=self.bybit,opener=client)
        self.assertEqual(out["status"],"network_unavailable")
        self.assertNotIn("private secret",str(out))

    def test_invalid_json_and_response_bounded(self):
        for body in (b'not-json',b'[]',b'{"a":1,"a":2}',b'{"dualSidePosition":1}',
                     b'{"dualSidePosition":NaN}',b'{"dualSidePosition":true}'+b"x"*9000):
            with self.subTest(body=body[:20]):
                out=diagnose("binance",allow_private_read=True,
                             confirm_read_only_key=True,env=self.binance,
                             opener=FakeOpener(body))
                self.assertEqual(out["status"],"invalid_provider_response")

    def test_production_client_has_no_proxy_and_no_redirect(self):
        with patch("scripts.probe_private_exchange_readonly.build_opener") as build:
            build.return_value=FakeOpener()
            diagnose("binance",allow_private_read=True,
                     confirm_read_only_key=True,env=self.binance)
            handlers=build.call_args.args
            self.assertEqual(handlers[0].proxies,{})
            self.assertIsNone(handlers[1].redirect_request(None,None,302,None,None,None))

    def test_signatures_deterministic_and_no_key_in_result(self):
        a=_sign_binance("secret",1700000000000)
        b=_sign_binance("secret",1700000000000)
        self.assertEqual(a,b)
        self.assertEqual(len(a.rsplit("=",1)[1]),64)
        self.assertEqual(len(_sign_bybit("public_key","secret",1700000000000)),64)
        for mode in ("binance","bybit"):
            self.assertNotIn("secret",str(diagnose(mode)))


if __name__=="__main__":
    unittest.main()
