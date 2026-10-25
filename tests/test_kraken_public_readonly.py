"""Purely offline conformance of bounded Kraken public GET research adapter."""
from __future__ import annotations

from decimal import Decimal
import json
from urllib.error import HTTPError, URLError
import unittest

from crypto_intelligence_agent.kraken_public_readonly import (
    KrakenPublicReadOnlyResearch, SOURCE,
)
from crypto_intelligence_agent.kraken_eligibility import (
    select_kraken_research_universe,
)
from crypto_intelligence_agent.market_data import (
    DataGapError, DataValidationError, ExchangeAccessError, HttpResponseError,
    DataTimeoutError, ClosedCandle,
)


HOUR = 3_600_000
START = 10 * HOUR
END = START + 3 * HOUR
CAPTURED = END + 2_000


def instruments_payload():
    return {
        "result": "success",
        "instruments": [
            {"symbol": "PF_XBTUSD", "base": "BTC", "quote": "USD",
             "pair": "BTC:USD", "category": None, "tradfi": False,
             "type": "flexible_futures", "tradeable": True,
             "suspended": False, "isExpired": False,
             "tickSize": "1", "contractSize": 1,
             "rawSecret": "NEVER_EXPORT_INSTRUMENT"},
            {"symbol": "PF_AAPLXUSD", "base": "AAPLX", "quote": "USD",
             "pair": "AAPLX:USD", "category": "xStocks",
             "tradfi": False, "type": "flexible_futures",
             "tradeable": True, "suspended": False,
             "isExpired": False, "tickSize": "0.01",
             "contractSize": 1},
        ],
    }


def ticker_body_bytes():
    # Deliberate source numeric text cannot be represented by binary float
    # without losing low-order significant digits.
    return (
        b'{"result":"success","tickers":['
        b'{"symbol":"PF_XBTUSD","tag":"perpetual","pair":"BTC:USD",'
        b'"suspended":false,"postOnly":false,'
        b'"volumeQuote":314801204.566112345678901234,'
        b'"vol24h":3928.249900000000123456},'
        b'{"symbol":"PF_AAPLXUSD","tag":"perpetual",'
        b'"suspended":false,"postOnly":false,'
        b'"volumeQuote":999999999.99999}'
        b']}'
    )


def chart_payload(*, incomplete=False, open_candle=False):
    rows = [
        {"time": START + i * HOUR, "open": str(65000 + i),
         "high": str(65020 + i), "low": str(64990 + i),
         "close": str(65001 + i), "volume": "12.750000000000"}
        for i in range(3)
    ]
    if incomplete:
        rows.pop(1)
    if open_candle:
        rows[-1]["time"] = END
    return {"candles": rows, "more_candles": False}


class FakeResponse:
    def __init__(self, payload, *, status=200, as_raw=False):
        self.status = status
        self.data = payload if as_raw else json.dumps(payload).encode("utf-8")

    def getcode(self):
        return self.status

    def read(self, n):
        return self.data[:n]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeOpener:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, request, *, timeout):
        self.calls.append((request.full_url, request.get_method(), timeout,
                           dict(request.header_items())))
        if not self.responses:
            raise AssertionError("unexpected extra GET")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def client(*, opener, clock=None, **kwargs):
    return KrakenPublicReadOnlyResearch(
        allow_public_network=True, opener=opener,
        clock_ms=clock or (lambda: CAPTURED),
        **kwargs,
    )


class KrakenPublicReadOnlyTests(unittest.TestCase):
    def test_zero_network_by_default_even_with_injected_opener(self):
        opener = FakeOpener()
        no_access = KrakenPublicReadOnlyResearch(opener=opener)
        with self.assertRaises(ExchangeAccessError):
            no_access.current_market_snapshot()
        with self.assertRaises(ExchangeAccessError):
            no_access.staged_closed_candles(
                symbol="PF_XBTUSD", interval="1h",
                start_open_ms=START, end_open_ms=END,
            )
        self.assertEqual(opener.calls, [])

    def test_exact_decimal_public_snapshot_with_crypto_and_tokenized_equity(self):
        opener = FakeOpener(
            FakeResponse(instruments_payload()),
            FakeResponse(ticker_body_bytes(), as_raw=True),
        )
        times = iter((CAPTURED - 1_000, CAPTURED))
        result = client(opener=opener, clock=lambda: next(times)).current_market_snapshot()
        self.assertEqual(result.source, SOURCE)
        self.assertEqual(result.captured_start_ms, CAPTURED - 1000)
        self.assertEqual(result.observed_at_ms, CAPTURED)
        self.assertEqual(len(opener.calls), 2)
        self.assertEqual(
            [call[1] for call in opener.calls], ["GET", "GET"],
        )
        self.assertEqual(
            [call[0] for call in opener.calls],
            ["https://futures.kraken.com/derivatives/api/v3/instruments",
             "https://futures.kraken.com/derivatives/api/v3/tickers"],
        )
        self.assertEqual(
            result.tickers[0]["volumeQuote"],
            Decimal("999999999.99999"),
        )
        btc_ticker = next(x for x in result.tickers if x["symbol"] == "PF_XBTUSD")
        self.assertEqual(
            btc_ticker["volumeQuote"], Decimal("314801204.566112345678901234")
        )
        self.assertIs(type(btc_ticker["volumeQuote"]), Decimal)
        self.assertNotIn("NEVER_EXPORT_INSTRUMENT", repr(result))

        ranked = select_kraken_research_universe(
            instruments=result.instruments, tickers=result.tickers,
            observed_at_ms=result.observed_at_ms,
            verified_crypto_bases=frozenset({"BTC", "AAPLX"}),
            registry_version="synthetic-research-fixture",
        )
        self.assertEqual([x.symbol for x in ranked.eligible], ["PF_XBTUSD"])
        self.assertEqual(ranked.excluded["PF_AAPLXUSD"], "non_crypto_category")

    def test_snapshot_clock_must_not_reverse_or_age_out(self):
        for times in ((2000, 1999), (1, 50_000)):
            with self.subTest(times=times):
                opener = FakeOpener(FakeResponse(instruments_payload()),
                                    FakeResponse(ticker_body_bytes(), as_raw=True))
                clock = iter(times)
                with self.assertRaises(DataValidationError):
                    client(opener=opener, clock=lambda: next(clock)).current_market_snapshot()
                self.assertEqual(len(opener.calls), 2)

    def test_instrument_schema_conflicting_duplicate_and_empty_rejected(self):
        for changed in (
            {"result": "error", "instruments": instruments_payload()["instruments"]},
            {"result": "success", "instruments": []},
            {"result": "success", "instruments": [{"symbol": None}]},
            {"result": "success", "instruments": ["not an object"]},
            {"result": "success", "instruments": [
                instruments_payload()["instruments"][0],
                {**instruments_payload()["instruments"][0], "tradeable": False},
            ]},
        ):
            with self.subTest(payload=repr(changed)[:80]):
                opener = FakeOpener(FakeResponse(changed))
                with self.assertRaises(DataValidationError):
                    client(opener=opener).current_market_snapshot()
                self.assertEqual(len(opener.calls), 1)

    def test_identical_duplicates_are_idempotent_and_sorted(self):
        src = instruments_payload()
        src["instruments"].append(dict(src["instruments"][0]))
        opener = FakeOpener(FakeResponse(src), FakeResponse(ticker_body_bytes(), as_raw=True))
        result = client(opener=opener).current_market_snapshot()
        self.assertEqual(len(result.instruments), 2)
        self.assertEqual([r["symbol"] for r in result.instruments],
                         ["PF_AAPLXUSD", "PF_XBTUSD"])

    def test_sanitized_rows_are_readonly_and_no_sensitive_fields(self):
        opener = FakeOpener(FakeResponse(instruments_payload()),
                            FakeResponse(ticker_body_bytes(), as_raw=True))
        result = client(opener=opener).current_market_snapshot()
        with self.assertRaises(TypeError):
            result.instruments[0]["apiSecret"] = "MUTATED"
        for row in result.instruments + result.tickers:
            self.assertNotIn("rawSecret", row)
            self.assertNotIn("apiSecret", row)

    def test_bounded_complete_candles_are_staged_not_canonical(self):
        opener = FakeOpener(FakeResponse(chart_payload()))
        result = client(opener=opener).staged_closed_candles(
            symbol="PF_XBTUSD", interval="1h",
            start_open_ms=START, end_open_ms=END,
        )
        self.assertEqual(result.observed_at_ms, CAPTURED)
        self.assertEqual(len(result.staged.candles), 3)
        self.assertEqual(result.staged.candles[0].raw_trade_volume_unverified,
                         Decimal("12.750000000000"))
        self.assertEqual(result.staged.candles[0].raw_volume_unit, "unverified")
        self.assertNotIsInstance(result.staged.candles[0], ClosedCandle)
        self.assertFalse(hasattr(result.staged.candles[0], "base_volume"))
        self.assertFalse(hasattr(result.staged.candles[0], "quote_volume"))
        self.assertEqual(len(opener.calls), 1)
        self.assertEqual(opener.calls[0][1], "GET")
        self.assertIn("?from=36000&to=46799", opener.calls[0][0])
        self.assertNotIn("to=46800", opener.calls[0][0])

    def test_gaps_and_open_candles_fail_without_second_request(self):
        for state in ({"incomplete": True}, {"open_candle": True}):
            with self.subTest(state=state):
                opener = FakeOpener(FakeResponse(chart_payload(**state)))
                with self.assertRaises((DataGapError, DataValidationError)):
                    client(opener=opener).staged_closed_candles(
                        symbol="PF_XBTUSD", interval="1h",
                        start_open_ms=START, end_open_ms=END,
                    )
                self.assertEqual(len(opener.calls), 1)

    def test_untrusted_symbols_intervals_and_windows_have_zero_gets(self):
        for symbol, interval in (
            ("PF_XBTUSD/../../private", "1h"),
            ("PI_XBTUSD", "1h"), ("PF_XBTusd", "1h"),
            ("PF_XBTUSD", "10s"),
        ):
            with self.subTest(symbol=symbol, interval=interval):
                opener = FakeOpener()
                with self.assertRaises(DataValidationError):
                    client(opener=opener).staged_closed_candles(
                        symbol=symbol, interval=interval,
                        start_open_ms=START, end_open_ms=END,
                    )
                self.assertEqual(opener.calls, [])
        opener = FakeOpener()
        with self.assertRaises(DataValidationError):
            client(opener=opener).staged_closed_candles(
                symbol="PF_XBTUSD", interval="1h",
                start_open_ms=START + 1, end_open_ms=END,
            )
        self.assertEqual(len(opener.calls), 0)

    def test_private_get_helper_refuses_unapproved_paths_and_query_extensions(self):
        for url in (
            "http://futures.kraken.com/derivatives/api/v3/instruments",
            "https://other.example.com/api/charts/v1/trade/PF_XBTUSD/1h?from=1&to=2",
            "https://futures.kraken.com/derivatives/api/v3/orders",
            "https://futures.kraken.com/api/charts/v1/trade/PF_XBTUSD/1h?from=1&to=2&secret=1",
            "https://futures.kraken.com/api/charts/v1/trade/PF_XBTUSD/1h?from=1&to=2/../private",
            "https://futures.kraken.com/api/charts/v1/trade/PF_XBTUSD/30s?from=1&to=2",
        ):
            with self.subTest(url=url):
                opener = FakeOpener()
                with self.assertRaises(ExchangeAccessError):
                    client(opener=opener)._read_public(url)
                self.assertEqual(len(opener.calls), 0)

    def test_policy_http_451_is_single_terminal_error(self):
        opener = FakeOpener(HTTPError("https://futures.kraken.com", 451,
                                      "Unavailable For Legal Reasons", None, None))
        with self.assertRaises(ExchangeAccessError):
            client(opener=opener).current_market_snapshot()
        self.assertEqual(len(opener.calls), 1)

    def test_redirect_http302_is_not_followed(self):
        opener = FakeOpener(HTTPError("https://futures.kraken.com", 302,
                                      "Redirect", None, None))
        with self.assertRaises(HttpResponseError):
            client(opener=opener).current_market_snapshot()
        self.assertEqual(len(opener.calls), 1)

    def test_timeout_does_not_retry_or_leak_network_details(self):
        opener = FakeOpener(URLError("private-error-location"))
        with self.assertRaises(DataTimeoutError) as case:
            client(opener=opener).current_market_snapshot()
        self.assertNotIn("private-error-location", str(case.exception))
        self.assertEqual(len(opener.calls), 1)

    def test_server_http200_invalid_payloads_are_rejected(self):
        invalid = [b'not json', b'{"tickers":NaN}',
                   b'{"result":"success","instruments":[],"instruments":[]}',
                   b'[]', b'\xff']
        for body in invalid:
            with self.subTest(body=body):
                opener = FakeOpener(FakeResponse(body, as_raw=True))
                with self.assertRaises(DataValidationError):
                    client(opener=opener).current_market_snapshot()
                self.assertEqual(len(opener.calls), 1)

    def test_response_limit_blocks_without_caching_or_second_get(self):
        opener = FakeOpener(FakeResponse(b"x"*600, as_raw=True))
        with self.assertRaises(DataValidationError):
            client(opener=opener, max_response_bytes=200).current_market_snapshot()
        self.assertEqual(len(opener.calls), 1)

    def test_configuration_requires_bounded_exact_opt_ins(self):
        for kwargs in (
            {"allow_public_network": "true"},
            {"timeout_seconds": -1},
            {"timeout_seconds": 11},
            {"timeout_seconds": True},
            {"max_response_bytes": 0},
            {"max_response_bytes": 99_000_000},
            {"max_snapshot_span_ms": -1},
            {"close_safety_ms": -1},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    KrakenPublicReadOnlyResearch(**kwargs)


if __name__ == "__main__":
    unittest.main()
