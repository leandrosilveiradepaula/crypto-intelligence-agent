from __future__ import annotations

import json
from pathlib import Path
import unittest

from crypto_intelligence_agent.market_data import (
    BinanceFuturesPublicAdapter,
    DataGapError,
    DataTimeoutError,
    HttpResponse,
    HttpResponseError,
    IneligibleSymbolError,
    MarketDataCheckpoint,
    RateLimitError,
)


FIXTURES = Path(__file__).parent / "fixtures"


class FixtureTransport:
    def __init__(self, routes: dict[str, HttpResponse | Exception]):
        self.routes = routes
        self.urls: list[str] = []

    def get(self, url: str, timeout_seconds: float) -> HttpResponse:
        self.urls.append(url)
        for suffix, result in self.routes.items():
            if suffix in url:
                if isinstance(result, Exception):
                    raise result
                return result
        raise AssertionError(f"unexpected URL: {url}")


def fixture(name: str) -> HttpResponse:
    return HttpResponse(200, (FIXTURES / name).read_text(encoding="utf-8"))


class PublicAdapterTests(unittest.TestCase):
    def adapter(self, routes: dict[str, HttpResponse | Exception], *, clock_ms=None) -> BinanceFuturesPublicAdapter:
        return BinanceFuturesPublicAdapter(FixtureTransport(routes), close_safety_ms=1_000, clock_ms=clock_ms)

    def test_contracts_are_typed_decimal_and_utc_milliseconds(self) -> None:
        contracts = self.adapter({"exchangeInfo": fixture("exchange_info.json")}).contracts(observed_at_ms=10_000)
        self.assertEqual(contracts[0].symbol, "BTCUSDT")
        self.assertEqual(str(contracts[0].tick_size), "0.10")
        self.assertEqual(contracts[0].observed_at_ms, 10_000)

    def test_checkpoint_preserves_a_utc_replay_boundary(self) -> None:
        checkpoint = MarketDataCheckpoint(
            data_type="closed_candle", exchange="binance", symbol="BTCUSDT", interval="1h",
            confirmed_start_ms=0, confirmed_end_ms=3_599_999, source="fixture", contract_version="j1-v1", integrity="verified",
        )
        self.assertEqual(checkpoint.confirmed_end_ms, 3_599_999)

    def test_universe_filters_and_ranks_quote_volume_at_observation_time(self) -> None:
        universe = self.adapter({"exchangeInfo": fixture("exchange_info.json"), "ticker/24hr": fixture("ticker_24h.json")}, clock_ms=lambda: 10_000).universe(
            observed_at_ms=10_000, min_onboard_age_ms=1_000
        )
        self.assertEqual([member.symbol for member in universe.eligible], ["BTCUSDT"])
        self.assertEqual(universe.excluded["ETHUSDT"], "below_minimum_onboard_age")
        self.assertEqual(universe.excluded["OLDUSDT"], "not_linear_perpetual")
        self.assertEqual(universe.excluded["PAUSEDUSDT"], "not_trading")

    def test_closed_candles_are_ordered_and_incomplete_candle_is_excluded(self) -> None:
        candles = self.adapter({"klines": fixture("klines.json")}).closed_candles(
            "BTCUSDT", "1h", observed_at_ms=20_000_000, eligible_symbols={"BTCUSDT"}
        )
        self.assertEqual([candle.open_time_ms for candle in candles], [0, 3_600_000, 7_200_000])
        self.assertEqual(candles[0].close_time_ms, 3_599_999)
        self.assertEqual(str(candles[0].quote_volume), "950.0")
        partial = self.adapter({"klines": fixture("klines.json")}).closed_candles(
            "BTCUSDT", "1h", observed_at_ms=10_000_000 - 2_000_000, eligible_symbols={"BTCUSDT"}
        )
        self.assertEqual([candle.open_time_ms for candle in partial], [0, 3_600_000])

    def test_replay_is_idempotent_and_conflicting_duplicates_are_rejected(self) -> None:
        replay = json.loads((FIXTURES / "klines.json").read_text(encoding="utf-8"))
        replay.append(replay[1])
        adapter = self.adapter({"klines": HttpResponse(200, json.dumps(replay))})
        first = adapter.closed_candles("BTCUSDT", "1h", observed_at_ms=20_000_000)
        second = adapter.closed_candles("BTCUSDT", "1h", observed_at_ms=20_000_000)
        self.assertEqual(first, second)
        conflict = json.loads((FIXTURES / "klines.json").read_text(encoding="utf-8"))
        altered = list(conflict[1])
        altered[4] = "100.20"
        conflict.append(altered)
        from crypto_intelligence_agent.market_data import DuplicateCandleError
        with self.assertRaises(DuplicateCandleError):
            self.adapter({"klines": HttpResponse(200, json.dumps(conflict))}).closed_candles("BTCUSDT", "1h", observed_at_ms=20_000_000)

    def test_gap_and_ineligible_symbol_are_explicit(self) -> None:
        gap = json.loads((FIXTURES / "klines.json").read_text(encoding="utf-8"))
        del gap[0]
        with self.assertRaises(DataGapError):
            self.adapter({"klines": HttpResponse(200, json.dumps(gap))}).closed_candles("BTCUSDT", "1h", observed_at_ms=20_000_000)
        with self.assertRaises(IneligibleSymbolError):
            self.adapter({"klines": fixture("klines.json")}).closed_candles("ETHUSDT", "1h", observed_at_ms=20_000_000, eligible_symbols={"BTCUSDT"})

    def test_http_rate_limit_and_timeout_are_explicit(self) -> None:
        with self.assertRaises(RateLimitError):
            self.adapter({"klines": HttpResponse(429, "{}")}).closed_candles("BTCUSDT", "1h", observed_at_ms=20_000_000)
        with self.assertRaises(HttpResponseError):
            self.adapter({"klines": HttpResponse(500, "{}")}).closed_candles("BTCUSDT", "1h", observed_at_ms=20_000_000)
        with self.assertRaises(DataTimeoutError):
            self.adapter({"klines": DataTimeoutError("fixture timeout")}).closed_candles("BTCUSDT", "1h", observed_at_ms=20_000_000)


if __name__ == "__main__":
    unittest.main()
