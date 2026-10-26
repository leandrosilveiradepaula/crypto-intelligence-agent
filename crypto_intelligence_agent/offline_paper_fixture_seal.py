"""J6/PRE2-A: deterministic synthetic candle/context seal; NO durable cursor.

A pure, offline prerequisite for a future atomic AUTO2 checkpoint. This module
neither reads nor writes SQLite, invokes a trading gate, or sends orders.
SHA-256 detects divergent fixtures; it does NOT authenticate a provider or
protect against a writer capable of rewriting both bytes and their digest.
"""
from __future__ import annotations

from dataclasses import dataclass, fields
from decimal import Decimal
from hashlib import sha256
import json
from typing import Sequence

from .market_data import ClosedCandle, DataValidationError
from .paper_risk_gate import PaperRiskLimits
from .synthetic_entry_hypotheses import CompressionBreakoutConfig, STRATEGY_ID
from .synthetic_feature_engine import MAX_CANDLES, _checked_candles
from .synthetic_manual_exit_replay import _fixture_units, _utc_ms
from .synthetic_order_lifecycle import PaperVenue


SEAL_VERSION = "offline-paper-forward-seal-v1"


@dataclass(frozen=True)
class OfflinePaperFixtureSeal:
    """Integrity evidence in memory only; never an execution authorization."""

    version: str
    context_sha256: str
    prefix_sha256: str
    candle_count: int
    first_open_time_ms: int
    last_open_time_ms: int
    last_close_time_ms: int
    decision_at_ms: int

    @property
    def source_quality(self) -> str:
        return "offline_fixture_integrity_only"

    @property
    def durable_session_checkpoint_available(self) -> bool:
        return False

    @property
    def order_submission_enabled(self) -> bool:
        return False

    @property
    def orders_sent(self) -> bool:
        return False

    @property
    def market_data_verified(self) -> bool:
        return False

    @property
    def approved_for_live_use(self) -> bool:
        return False


def _scalar(value: object) -> object:
    """Encode finite Decimals with sign, digits AND exponent (including scale)."""
    if type(value) is Decimal:
        if not value.is_finite():
            raise DataValidationError("non-finite PAPER fixture Decimal")
        t = value.as_tuple()
        return {"decimal": [t.sign, "".join(str(d) for d in t.digits), t.exponent]}
    if type(value) in (str, int, bool):
        return value
    raise DataValidationError("unsupported PAPER fixture seal field type")


def _record(value: object, model: type) -> dict[str, object]:
    if type(value) is not model:
        raise DataValidationError("invalid typed PAPER fixture seal input")
    return {
        field.name: _scalar(getattr(value, field.name))
        for field in fields(model)
    }


def _canonical_digest(value: dict[str, object]) -> str:
    raw = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    )
    return sha256(raw.encode("utf-8")).hexdigest()


def seal_offline_paper_prefix(
    closed_prefix: Sequence[ClosedCandle], *,
    strategy: CompressionBreakoutConfig,
    venue: PaperVenue,
    requested_units: Decimal,
    limits: PaperRiskLimits,
    decision_at_ms: int,
    close_safety_ms: int = 1_000,
    max_candles: int = MAX_CANDLES,
) -> OfflinePaperFixtureSeal:
    """Seal the complete fixed synthetic prefix and its versioned assumptions.

    This does not store a cursor or reserve an OPEN. The entire prefix is
    required: a truncated rolling window is not a valid continuation.
    """
    if (type(strategy) is not CompressionBreakoutConfig
            or type(venue) is not PaperVenue
            or type(requested_units) is not Decimal
            or type(limits) is not PaperRiskLimits
            or type(max_candles) is not int
            or not 1 <= max_candles <= MAX_CANDLES
            or type(closed_prefix) not in (tuple, list)
            or not 1 <= len(closed_prefix) <= max_candles
            or type(close_safety_ms) is not int
            or not 0 <= close_safety_ms <= 86_400_000):
        raise DataValidationError("typed bounded offline fixture seal required")
    _fixture_units(requested_units)
    now = _utc_ms(decision_at_ms, "decision_at_ms")
    candles = _checked_candles(
        closed_prefix, decision_at_ms=now,
        close_safety_ms=close_safety_ms,
    )
    if now != candles[-1].close_time_ms + close_safety_ms:
        raise DataValidationError("fixture seal needs exact last-close decision time")

    context = {
        "version": SEAL_VERSION,
        "strategy_id": STRATEGY_ID,
        "features": _record(strategy.features, type(strategy.features)),
        "strategy": {
            field.name: _scalar(getattr(strategy, field.name))
            for field in fields(CompressionBreakoutConfig)
            if field.name != "features"
        },
        "venue_candidate": venue.value,
        "requested_units": _scalar(requested_units),
        "risk_limits": _record(limits, PaperRiskLimits),
        "close_safety_ms": close_safety_ms,
        "max_candles": max_candles,
    }
    context_hash = _canonical_digest(context)
    prefix_hash = _canonical_digest({
        "version": SEAL_VERSION,
        "context_sha256": context_hash,
        "candles": [_record(c, ClosedCandle) for c in candles],
    })
    return OfflinePaperFixtureSeal(
        version=SEAL_VERSION,
        context_sha256=context_hash,
        prefix_sha256=prefix_hash,
        candle_count=len(candles),
        first_open_time_ms=candles[0].open_time_ms,
        last_open_time_ms=candles[-1].open_time_ms,
        last_close_time_ms=candles[-1].close_time_ms,
        decision_at_ms=now,
    )


def verify_offline_paper_extension(
    previous: OfflinePaperFixtureSeal,
    closed_prefix: Sequence[ClosedCandle], *,
    strategy: CompressionBreakoutConfig,
    venue: PaperVenue,
    requested_units: Decimal,
    limits: PaperRiskLimits,
    decision_at_ms: int,
    close_safety_ms: int = 1_000,
    max_candles: int = MAX_CANDLES,
) -> OfflinePaperFixtureSeal:
    """Verify the preceding FULL prefix before accepting exactly one new bar.

    The caller must eventually persist/compare the previous digest UNDER the
    same AUTO2 write transaction as risk+OPEN and new cursor. This pure helper
    must not be confused with that unimplemented transaction protocol.
    """
    if (type(previous) is not OfflinePaperFixtureSeal
            or previous.version != SEAL_VERSION
            or type(closed_prefix) not in (list, tuple)
            or len(closed_prefix) != previous.candle_count + 1):
        raise DataValidationError("exactly one new PAPER fixture candle required")
    next_seal = seal_offline_paper_prefix(
        closed_prefix, strategy=strategy, venue=venue,
        requested_units=requested_units, limits=limits,
        decision_at_ms=decision_at_ms, close_safety_ms=close_safety_ms,
        max_candles=max_candles,
    )
    prior_candles = closed_prefix[:-1]
    prior_seal = seal_offline_paper_prefix(
        prior_candles, strategy=strategy, venue=venue,
        requested_units=requested_units, limits=limits,
        decision_at_ms=prior_candles[-1].close_time_ms + close_safety_ms,
        close_safety_ms=close_safety_ms, max_candles=max_candles,
    )
    if previous != prior_seal:
        raise DataValidationError(
            "prior PAPER prefix or configuration digest diverged"
        )
    return next_seal
