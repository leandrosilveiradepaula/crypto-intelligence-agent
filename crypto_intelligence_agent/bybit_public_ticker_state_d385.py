"""D385: Bybit V5 public linear ticker snapshot/delta state, offline-only.

A caller must supply independently admitted symbols and an ACKed public WS
session. This component never creates a socket, accesses a broker account,
queries REST, writes J1 journals, submits orders, or proves Top50 eligibility.

Bybit ticker schema: https://bybit-exchange.github.io/docs/v5/websocket/public/ticker
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import re
from typing import Iterable

from .bybit_linear_candle_research import _strict_decimal, _SYMBOL
from .decimal_json import decode_public_market_json_exact
from .market_data import DataGapError, DataValidationError

MAX_FRAME_BYTES = 16_384
MAX_RANKED = 50
MAX_MONITORED = 100
MAX_EVENT_LAG_MS = 30_000
MAX_CLOCK_SKEW_MS = 5_000
MAX_QUOTE_AGE_MS = 3_000
MAX_UTC_MS = 4_102_444_800_000
SOURCE = "bybit_v5_public_linear_ticker_unverified"
_REQUIRED = (
    "lastPrice", "markPrice", "indexPrice",
    "bid1Price", "ask1Price", "bid1Size", "ask1Size",
)
_PRICES = frozenset((
    "lastPrice", "markPrice", "indexPrice", "bid1Price", "ask1Price",
))
_AMOUNTS = frozenset(("bid1Size", "ask1Size", "turnover24h", "volume24h"))
_ALLOWED_VALUES = _PRICES | _AMOUNTS | {"fundingRate"}
_SIGNED_DECIMAL = re.compile(r"-?(?:0|[1-9][0-9]{0,29})(?:\.[0-9]{1,24})?\Z")


def _ms(value: object, label: str) -> int:
    if type(value) is not int or not 0 < value < MAX_UTC_MS:
        raise DataValidationError(label + "_utc_ms_invalid")
    return value


def _symbols(values: Iterable[str], *, maximum: int) -> tuple[str, ...]:
    if type(values) not in (tuple, list) or not 0 < len(values) <= maximum:
        raise DataValidationError("ticker_membership_count_invalid")
    if (any(type(x) is not str or not x.endswith("USDT")
            or _SYMBOL.fullmatch(x) is None for x in values)
            or len(set(values)) != len(values)):
        raise DataValidationError("ticker_membership_identity_invalid")
    return tuple(sorted(values))


def _funding(value: object) -> Decimal:
    if (type(value) is not str or len(value) > 80
            or _SIGNED_DECIMAL.fullmatch(value) is None):
        raise DataValidationError("ticker_funding_rate_invalid")
    result = Decimal(value)
    if not result.is_finite() or abs(result) > 1:
        raise DataValidationError("ticker_funding_rate_invalid")
    return result


@dataclass(frozen=True)
class BybitTickerQuote:
    symbol: str
    exchange_at_ms: int
    received_at_ms: int
    cross_sequence: int
    last_price: Decimal
    mark_price: Decimal
    index_price: Decimal
    bid_price: Decimal
    ask_price: Decimal
    bid_size: Decimal
    ask_size: Decimal
    turnover_24h: Decimal | None
    volume_24h: Decimal | None
    funding_rate: Decimal | None
    source: str = SOURCE

    @property
    def has_positive_book_depth(self) -> bool:
        return self.bid_size > 0 and self.ask_size > 0


class BybitPublicTickerBook:
    """Stateful, count-bounded *read-only* decoder for one ACKed WS session.

    Snapshot fields are required to establish an initial quote. Delta fields
    absent from a frame are unchanged, NOT zero. A reconnect invalidates ALL
    quotes until fresh snapshots arrive. No method returns trade intents.
    """

    def __init__(self, *, ranked_symbols: tuple[str, ...],
                 position_symbols: tuple[str, ...] = (),
                 universe_at_ms: int, max_quote_age_ms: int = MAX_QUOTE_AGE_MS):
        ranked = _symbols(ranked_symbols, maximum=MAX_RANKED)
        positions = (_symbols(position_symbols, maximum=MAX_MONITORED)
                     if position_symbols else ())
        monitored = frozenset(ranked) | frozenset(positions)
        if len(monitored) > MAX_MONITORED:
            raise DataValidationError("ticker_total_membership_budget_exceeded")
        self._ranked = ranked
        self._positions = positions
        self._monitored = monitored
        self._universe_at_ms = _ms(universe_at_ms, "ticker_universe")
        if (type(max_quote_age_ms) is not int
                or not 100 <= max_quote_age_ms <= MAX_EVENT_LAG_MS):
            raise DataValidationError("ticker_quote_age_budget_invalid")
        self._max_quote_age_ms = max_quote_age_ms
        self._connected = False
        self._quotes: dict[str, BybitTickerQuote] = {}
        self._last_data: dict[str, tuple] = {}
        self._snapshots = 0
        self._deltas = 0
        self._duplicates = 0
        self._invalidations = 0

    @property
    def topics(self) -> tuple[str, ...]:
        return tuple("tickers." + s for s in sorted(self._monitored))

    def topic_batches(self, *, batch_size: int = 50) -> tuple[tuple[str, ...], ...]:
        if type(batch_size) is not int or not 1 <= batch_size <= 50:
            raise DataValidationError("ticker_subscribe_batch_budget_invalid")
        topics = self.topics
        return tuple(tuple(topics[i:i + batch_size])
                     for i in range(0, len(topics), batch_size))

    def begin_acknowledged_session(self) -> None:
        """The caller must first verify subscribe ACKs for this session."""
        self._quotes.clear()
        self._last_data.clear()
        self._connected = True

    def mark_disconnected(self) -> None:
        self._connected = False
        self._quotes.clear()
        self._last_data.clear()
        self._invalidations += 1

    def rotate_membership(self, *, ranked_symbols: tuple[str, ...],
                          position_symbols: tuple[str, ...],
                          universe_at_ms: int) -> tuple[tuple[str, ...], tuple[str, ...]]:
        new_ranked = _symbols(ranked_symbols, maximum=MAX_RANKED)
        new_positions = (_symbols(position_symbols, maximum=MAX_MONITORED)
                         if position_symbols else ())
        new_monitored = frozenset(new_ranked) | frozenset(new_positions)
        observed = _ms(universe_at_ms, "ticker_universe")
        if observed <= self._universe_at_ms or len(new_monitored) > MAX_MONITORED:
            raise DataGapError("ticker_universe_rotation_invalid")
        added = tuple("tickers." + s for s in sorted(new_monitored - self._monitored))
        removed = tuple("tickers." + s for s in sorted(self._monitored - new_monitored))
        self._quotes = {s: q for s, q in self._quotes.items() if s in new_monitored}
        self._last_data = {s: d for s, d in self._last_data.items() if s in new_monitored}
        self._ranked, self._positions = new_ranked, new_positions
        self._monitored = new_monitored
        self._universe_at_ms = observed
        # New topics must obtain an upstream subscription ACK and fresh snapshot.
        return added, removed

    def ingest(self, raw: str | bytes, *, received_at_ms: int) -> BybitTickerQuote:
        if not self._connected:
            raise DataGapError("ticker_subscription_not_acknowledged")
        try:
            return self._ingest_validated(raw, received_at_ms=received_at_ms)
        except (DataGapError, DataValidationError, ValueError, TypeError):
            self.mark_disconnected()
            raise

    def _ingest_validated(self, raw: str | bytes, *, received_at_ms: int) -> BybitTickerQuote:
        at = _ms(received_at_ms, "ticker_received")
        payload = decode_public_market_json_exact(raw, max_bytes=MAX_FRAME_BYTES)
        if set(payload) != {"topic", "type", "ts", "cs", "data"}:
            raise DataValidationError("ticker_envelope_fields_invalid")
        topic, kind = payload["topic"], payload["type"]
        if type(topic) is not str or not topic.startswith("tickers."):
            raise DataValidationError("ticker_topic_invalid")
        symbol = topic[8:]
        if symbol not in self._monitored:
            raise DataGapError("ticker_outside_reviewed_membership")
        if kind not in ("snapshot", "delta"):
            raise DataValidationError("ticker_event_type_invalid")
        exchange_at = _ms(payload["ts"], "ticker_exchange")
        seq = payload["cs"]
        if type(seq) is not int or seq <= 0:
            raise DataValidationError("ticker_cross_sequence_invalid")
        if exchange_at > at + MAX_CLOCK_SKEW_MS or at - exchange_at > MAX_EVENT_LAG_MS:
            raise DataGapError("ticker_transport_clock_stale_or_future")
        data = payload["data"]
        if type(data) is not dict or data.get("symbol") != symbol:
            raise DataValidationError("ticker_payload_symbol_invalid")
        if (len(data) > 64
                or any(type(k) is not str or not 1 <= len(k) <= 48
                       or not k.isascii() for k in data)
                or any(type(v) not in (str, int, bool)
                       or type(v) is str and len(v) > 128 for v in data.values())):
            raise DataValidationError("ticker_payload_value_shape_invalid")

        old = self._quotes.get(symbol)
        fingerprint = (kind, exchange_at, seq, tuple(sorted(data.items())))
        if old is not None:
            if seq < old.cross_sequence or exchange_at < old.exchange_at_ms or at < old.received_at_ms:
                raise DataGapError("ticker_retrograde_sequence_or_time")
            if seq == old.cross_sequence:
                if fingerprint != self._last_data[symbol]:
                    raise DataGapError("ticker_same_sequence_conflicting_payload")
                self._duplicates += 1
                return old
        elif kind != "snapshot":
            raise DataGapError("ticker_delta_without_snapshot")

        if kind == "snapshot" and any(k not in data for k in _REQUIRED):
            raise DataValidationError("ticker_snapshot_price_fields_missing")
        fields = {}
        for key in _REQUIRED:
            if key in data:
                fields[key] = _strict_decimal(data[key], label=key,
                                              may_be_zero=key in _AMOUNTS)
        if kind == "delta":
            assert old is not None
            for k, previous in (
                ("lastPrice", old.last_price), ("markPrice", old.mark_price),
                ("indexPrice", old.index_price), ("bid1Price", old.bid_price),
                ("ask1Price", old.ask_price), ("bid1Size", old.bid_size),
                ("ask1Size", old.ask_size),
            ):
                fields.setdefault(k, previous)
        if fields["bid1Price"] > fields["ask1Price"]:
            raise DataGapError("ticker_crossed_best_bid_ask")

        def opt_amount(k: str, previous: Decimal | None) -> Decimal | None:
            if k in data:
                return _strict_decimal(data[k], label=k, may_be_zero=True)
            return previous if kind == "delta" and old is not None else None

        funding = (_funding(data["fundingRate"]) if "fundingRate" in data else
                   old.funding_rate if kind == "delta" and old is not None else None)
        quote = BybitTickerQuote(
            symbol=symbol, exchange_at_ms=exchange_at, received_at_ms=at,
            cross_sequence=seq,
            last_price=fields["lastPrice"], mark_price=fields["markPrice"],
            index_price=fields["indexPrice"], bid_price=fields["bid1Price"],
            ask_price=fields["ask1Price"], bid_size=fields["bid1Size"],
            ask_size=fields["ask1Size"],
            turnover_24h=opt_amount("turnover24h", old.turnover_24h if old else None),
            volume_24h=opt_amount("volume24h", old.volume_24h if old else None),
            funding_rate=funding,
        )
        self._quotes[symbol] = quote
        self._last_data[symbol] = fingerprint
        if kind == "snapshot":
            self._snapshots += 1
        else:
            self._deltas += 1
        return quote

    def current(self, symbol: str, *, at_ms: int) -> BybitTickerQuote | None:
        """Return None on stale/missing/nonexecutable quotes, never fake a fill."""
        now = _ms(at_ms, "ticker_query")
        quote = self._quotes.get(symbol) if self._connected else None
        if (quote is None or now < quote.received_at_ms
                or now - quote.received_at_ms > self._max_quote_age_ms
                or not quote.has_positive_book_depth):
            return None
        return quote

    def sanitized_report(self, *, at_ms: int) -> dict:
        now = _ms(at_ms, "ticker_report")
        fresh = sum(1 for s in self._monitored if self.current(s, at_ms=now) is not None)
        return {
            "schema_version": "bybit-public-ticker-state-d385-v1",
            "status": "public_ticker_state_offline_only",
            "connected": self._connected,
            "monitored_contracts": len(self._monitored),
            "ranked_contracts": len(self._ranked),
            "position_contracts": len(self._positions),
            "fresh_quotes": fresh,
            "unavailable_quotes": len(self._monitored) - fresh,
            "snapshots": self._snapshots,
            "deltas": self._deltas,
            "duplicates": self._duplicates,
            "invalidations": self._invalidations,
            "marketwide_top50_verified": False,
            "order_submission_enabled": False,
            "orders_sent": False,
            "live_trading_authorized": False,
        }
