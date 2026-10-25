"""Offline deterministic transport for development and CI. No network calls.

The files live in the repository's tests/fixtures and are NOT real historical
observations or an exchange dataset suitable for trading research.
"""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .market_data import DataValidationError, HttpResponse


class OfflineFixtureTransport:
    """Emulate read-only Binance USD-M GET endpoints with synthetic fixtures."""

    def __init__(
        self,
        fixture_dir: str | Path | None = None,
        *,
        available_symbols: tuple[str, ...] = ("BTCUSDT", "ETHUSDT"),
    ) -> None:
        path = Path(fixture_dir) if fixture_dir else Path(__file__).resolve().parent.parent / "tests" / "fixtures"
        self._exchange_info = json.loads((path / "exchange_info.json").read_text(encoding="utf-8"))
        self._tickers = json.loads((path / "ticker_24h.json").read_text(encoding="utf-8"))
        self._klines = json.loads((path / "klines.json").read_text(encoding="utf-8"))
        self._symbols = set(available_symbols)
        self.requests: list[str] = []
        if not self._symbols.issubset({"BTCUSDT", "ETHUSDT"}):
            raise ValueError("offline fixture supports BTCUSDT and ETHUSDT only")

    def get(self, url: str, timeout_seconds: float) -> HttpResponse:
        self.requests.append(url)
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        if parsed.path == "/fapi/v1/time":
            # Synthetic demo clock, not a live exchange time sample.
            value = {"serverTime": 20_000_000}
        elif parsed.path == "/fapi/v1/exchangeInfo":
            value = dict(self._exchange_info)
            value["symbols"] = [
                row for row in value["symbols"] if row["symbol"] in self._symbols
            ]
        elif parsed.path == "/fapi/v1/ticker/24hr":
            value = [
                row for row in self._tickers if row["symbol"] in self._symbols
            ]
        elif parsed.path == "/fapi/v1/klines":
            symbol = params.get("symbol", [None])[0]
            interval = params.get("interval", [None])[0]
            if symbol not in self._symbols or interval != "1h":
                raise DataValidationError(
                    "offline fixture only contains synthetic hourly BTCUSDT/ETHUSDT candles"
                )
            start = int(params.get("startTime", ["0"])[0])
            end = int(params.get("endTime", [str(2**63 - 1)])[0])
            limit = int(params.get("limit", ["500"])[0])
            value = [
                row for row in self._klines if start <= row[0] <= end
            ][:limit]
        else:
            raise DataValidationError(f"unsupported offline fixture endpoint: {parsed.path}")
        return HttpResponse(200, json.dumps(value))
