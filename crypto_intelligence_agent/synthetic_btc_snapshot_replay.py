"""J2/PRE5: point-in-time synthetic BTC breakout screening replay.

Exactly the earlier PRE4 screen is run with closed-candle prefixes at each
explicitly recorded UTC universe snapshot. This is NOT a backtest with
positions/fills/PnL and confers no source authentication, edge or trade grant.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Mapping, Sequence

from .market_data import (
    ClosedCandle, DataValidationError, interval_duration_ms,
)
from .synthetic_btc_breakout_screen import (
    MAX_RESEARCH_ASSETS, ScreenDisposition, SyntheticScreenConfig,
    screen_synthetic_btc_breakouts,
)

MAX_REPLAY_SNAPSHOTS = 96
MAX_REPLAY_CANDLES = 1000
MAX_REPLAY_ASSETS = 50
GENESIS = "0" * 64


@dataclass(frozen=True)
class SyntheticUniverseAtClose:
    """A hypothetical universe actually observed after this closed UTC bar."""

    closed_at_ms: int
    recorded_at_ms: int
    members: tuple[str, ...]


@dataclass(frozen=True)
class SyntheticReplayRow:
    closed_at_ms: int
    recorded_at_ms: int
    members: tuple[str, ...]
    ranked_symbols: tuple[str, ...]
    dispositions: tuple[tuple[str, str], ...]
    digest_sha256: str

    @property
    def approved_for_signals(self) -> bool:
        return False


@dataclass(frozen=True)
class SyntheticReplayReport:
    exchange: str
    interval: str
    as_of_ms: int
    rows: tuple[SyntheticReplayRow, ...]
    replay_digest_sha256: str

    @property
    def quality(self) -> str:
        return "synthetic_fixture_hypothesis_only"

    @property
    def approved_for_live_use(self) -> bool:
        return False

    @property
    def approved_for_signals(self) -> bool:
        return False

    @property
    def order_capable(self) -> bool:
        return False

    @property
    def orders_sent(self) -> bool:
        return False


def _prefix_to_closed(
    candles: Sequence[ClosedCandle], closed_at_ms: int,
) -> tuple[ClosedCandle, ...]:
    """Only take the observed closed prefix; never inspect later row values."""
    if type(candles) not in (list, tuple) or not candles or len(candles) > MAX_REPLAY_CANDLES:
        raise DataValidationError("bounded nonempty synthetic history required")
    prefix = []
    for candle in candles:
        if type(candle) is not ClosedCandle:
            raise DataValidationError("canonical ClosedCandle required")
        if type(candle.close_time_ms) is not int:
            raise DataValidationError("UTC close must be integer")
        if candle.close_time_ms > closed_at_ms:
            break
        prefix.append(candle)
    if not prefix or prefix[-1].close_time_ms != closed_at_ms:
        raise DataValidationError("missing closed candle at recorded universe hour")
    return tuple(prefix)


def _digest(previous: str, snapshot: SyntheticUniverseAtClose,
            disposition: tuple[tuple[str, str], ...],
            ranked: tuple[str, ...]) -> str:
    payload = json.dumps(
        [previous, snapshot.closed_at_ms, snapshot.recorded_at_ms,
         list(snapshot.members), [list(row) for row in disposition],
         list(ranked)],
        separators=(",", ":"), ensure_ascii=True,
    )
    return sha256(payload.encode("ascii")).hexdigest()


def replay_synthetic_btc_universe(
    btc_candles: Sequence[ClosedCandle],
    assets: Mapping[str, Sequence[ClosedCandle]],
    snapshots: Sequence[SyntheticUniverseAtClose],
    *,
    config: SyntheticScreenConfig,
    as_of_ms: int,
    close_safety_ms: int = 1000,
) -> SyntheticReplayReport:
    """Reproduce bounded snapshots, never use future bars or survivorship lists.

    The caller supplies a timestamped synthetic universe *for each* UTC step.
    Each snapshot was recorded no earlier than the bar close + safety delay;
    the decision uses this recorded instant, not the report's final as_of time.
    Symbol omissions are explicit membership changes, not a derived Top50.
    Every selected history MUST include that checkpoint's UTC close.
    """
    if type(config) is not SyntheticScreenConfig:
        raise DataValidationError("explicit synthetic screening config required")
    if type(as_of_ms) is not int or as_of_ms <= 0:
        raise DataValidationError("as_of_ms must be positive UTC integer")
    if type(close_safety_ms) is not int or not 0 <= close_safety_ms <= 86_400_000:
        raise DataValidationError("invalid close safety")
    if type(snapshots) not in (list, tuple) or not 1 <= len(snapshots) <= MAX_REPLAY_SNAPSHOTS:
        raise DataValidationError("bounded nonempty universe snapshots required")
    if type(assets) is not dict or not 1 <= len(assets) <= MAX_REPLAY_ASSETS:
        raise DataValidationError("bounded mapping of research histories required")
    if type(btc_candles) not in (list, tuple) or not btc_candles:
        raise DataValidationError("BTC fixture history is required")
    if type(btc_candles[0]) is not ClosedCandle:
        raise DataValidationError("BTC must use canonical candles")
    duration = interval_duration_ms(btc_candles[0].interval)
    if len(btc_candles) > MAX_REPLAY_CANDLES:
        raise DataValidationError("BTC history exceeds replay bound")

    output: list[SyntheticReplayRow] = []
    previous_close: int | None = None
    previous_record: int | None = None
    digest = GENESIS
    venue: str | None = None
    interval: str | None = None
    for snapshot in snapshots:
        if type(snapshot) is not SyntheticUniverseAtClose:
            raise DataValidationError("recorded synthetic universe snapshot required")
        end, record, members = snapshot.closed_at_ms, snapshot.recorded_at_ms, snapshot.members
        if (type(end) is not int or type(record) is not int
                or end <= 0 or record < end + close_safety_ms
                or record > as_of_ms
                or (previous_close is not None and end != previous_close + duration)
                or (previous_record is not None and record <= previous_record)):
            raise DataValidationError("noncausal or noncontiguous UTC universe snapshots")
        if (type(members) is not tuple or not 1 <= len(members) <= MAX_REPLAY_ASSETS
                or len(members) > MAX_RESEARCH_ASSETS
                or len(set(members)) != len(members)
                or members != tuple(sorted(members))
                or any(type(symbol) is not str or symbol == "BTCUSDT"
                       or not symbol or len(symbol) > 32 for symbol in members)):
            raise DataValidationError("universe members must be unique, sorted non-BTC symbols")
        if any(symbol not in assets for symbol in members):
            raise DataValidationError("universe member absent from supplied frozen histories")
        btc_prefix = _prefix_to_closed(btc_candles, end)
        asset_prefixes = [_prefix_to_closed(assets[symbol], end) for symbol in members]
        if any(series[0].symbol != symbol for symbol, series in zip(members, asset_prefixes)):
            raise DataValidationError("universe identity and series identity differ")
        selected = screen_synthetic_btc_breakouts(
            btc_prefix, asset_prefixes, config=config, decision_at_ms=record,
            close_safety_ms=close_safety_ms,
        )
        if venue is None:
            venue, interval = selected.exchange, selected.interval
        elif (venue, interval) != (selected.exchange, selected.interval):
            raise DataValidationError("replay must retain one venue and interval")
        if selected.last_closed_at_ms != end:
            raise DataValidationError("screen used a nonmatching UTC checkpoint")
        dispositions = tuple((item.symbol, item.disposition.value)
                             for item in selected.items)
        digest = _digest(digest, snapshot, dispositions, selected.ranked_symbols)
        output.append(SyntheticReplayRow(
            closed_at_ms=end, recorded_at_ms=record, members=members,
            ranked_symbols=selected.ranked_symbols, dispositions=dispositions,
            digest_sha256=digest,
        ))
        previous_close = end
        previous_record = record

    assert venue is not None and interval is not None
    return SyntheticReplayReport(
        exchange=venue, interval=interval, as_of_ms=as_of_ms,
        rows=tuple(output), replay_digest_sha256=digest,
    )
