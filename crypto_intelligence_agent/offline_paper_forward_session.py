"""J6/PRE1: bounded forward-only fixture replay into the existing PAPER gate.

This is not a live stream, a durable cursor, an exchange order engine or
proof of prospective performance. Input is synthetic and supplied entirely
by the caller. There is NO network, scheduler, pricing or fill generation.
"""
from __future__ import annotations

from dataclasses import dataclass, fields
from decimal import Decimal
from pathlib import Path
from threading import Lock
from typing import Sequence

from .causal_paper_open import (
    MAX_CLOSE_SAFETY_MS, CausalPaperOpening, reserve_causal_paper_open,
)
from .market_data import ClosedCandle, DataValidationError
from .paper_order_store import SQLitePaperOrderJournal
from .paper_risk_gate import PaperRiskLimits, PaperRiskObservation
from .synthetic_entry_hypotheses import CompressionBreakoutConfig
from .synthetic_feature_engine import MAX_CANDLES, _checked_candles
from .synthetic_manual_exit_replay import _fixture_units, _utc_ms
from .synthetic_order_lifecycle import PaperVenue


@dataclass(frozen=True)
class OfflineForwardPaperTick:
    """One accepted fixture step. The opening, if any, is PENDING only."""

    sequence_number: int
    accepted_candle_count: int
    decision_at_ms: int
    opening: CausalPaperOpening

    @property
    def source_quality(self) -> str:
        return "offline_fixture_forward_replay_only"

    @property
    def paper_intent_reserved(self) -> bool:
        return self.opening.paper_intent_reserved

    @property
    def orders_sent(self) -> bool:
        return False

    @property
    def live_feed_connected(self) -> bool:
        return False

    @property
    def market_data_verified(self) -> bool:
        return False

    @property
    def stop_native_verified(self) -> bool:
        return False

    @property
    def real_pnl_available(self) -> bool:
        return False

    @property
    def approved_for_live_use(self) -> bool:
        return False

    @property
    def cross_database_atomic_snapshot_available(self) -> bool:
        return False

    @property
    def durable_session_checkpoint_available(self) -> bool:
        return False

    @property
    def prospectively_homologated(self) -> bool:
        return False


def _exact_candle(left: ClosedCandle, right: ClosedCandle) -> bool:
    """Do not allow silently rewritten Decimal precision on prior candles."""
    if type(left) is not ClosedCandle or type(right) is not ClosedCandle:
        return False
    for item in fields(ClosedCandle):
        a, b = getattr(left, item.name), getattr(right, item.name)
        if type(a) is not type(b):
            return False
        if type(a) is Decimal:
            if a.as_tuple() != b.as_tuple():
                return False
        elif a != b:
            return False
    return True


class OfflinePaperForwardSession:
    """Monotonic in-memory fixture decisions; NEVER a durable market runner.

    First step is a user-supplied historical prefix, NOT verified observed
    prospectively. Each following step must append EXACTLY one synthetic
    closed candle and reproduce every previously accepted candle verbatim.
    A restart loses this in-memory cursor: only the AUTO6/AUTO8 order journal
    remains durable for OPEN dedup and risk, and external recovery is needed.
    """

    def __init__(
        self, *, strategy: CompressionBreakoutConfig, venue: PaperVenue,
        requested_units: Decimal, limits: PaperRiskLimits,
        journal: SQLitePaperOrderJournal, position_journal_path: str | Path,
        close_safety_ms: int = 1_000, max_candles: int = MAX_CANDLES,
    ) -> None:
        if (type(strategy) is not CompressionBreakoutConfig
                or type(venue) is not PaperVenue
                or type(requested_units) is not Decimal
                or type(limits) is not PaperRiskLimits
                or type(journal) is not SQLitePaperOrderJournal
                or type(position_journal_path) not in (str, Path)
                or not str(position_journal_path).strip()
                or type(close_safety_ms) is not int
                or not 0 <= close_safety_ms <= MAX_CLOSE_SAFETY_MS
                or type(max_candles) is not int
                or not 1 <= max_candles <= MAX_CANDLES):
            raise DataValidationError("explicit typed, bounded offline PAPER session required")
        _fixture_units(requested_units)
        self.strategy = strategy
        self.venue = venue
        self.requested_units = requested_units
        self.limits = limits
        self.journal = journal
        self.position_journal_path = Path(position_journal_path)
        self.close_safety_ms = close_safety_ms
        self.max_candles = max_candles
        self._prefix: tuple[ClosedCandle, ...] | None = None
        self._accepted_ticks = 0
        self._paper_intents = 0
        self._step_lock = Lock()

    @property
    def accepted_ticks(self) -> int:
        return self._accepted_ticks

    @property
    def reserved_paper_intents(self) -> int:
        """Only intents accepted through THIS session, not a journal total."""
        return self._paper_intents

    @property
    def last_accepted_candle_open_ms(self) -> int | None:
        return None if self._prefix is None else self._prefix[-1].open_time_ms

    @property
    def durable_session_checkpoint_available(self) -> bool:
        return False

    @property
    def live_feed_connected(self) -> bool:
        return False

    @property
    def order_submission_enabled(self) -> bool:
        return False

    @property
    def orders_sent(self) -> bool:
        return False

    def step(
        self, closed_prefix: Sequence[ClosedCandle], *,
        observation: PaperRiskObservation, decision_at_ms: int,
    ) -> OfflineForwardPaperTick:
        """Accept one next closed prefix and call the existing atomic gate.

        No session counters/prefix update occurs on malformed input or an
        exception (including journal corruption). A valid risk denial or
        no-signal result DOES advance the in-memory candle checkpoint.
        """
        if not self._step_lock.acquire(blocking=False):
            raise DataValidationError("concurrent PAPER session step refused")
        try:
            now = _utc_ms(decision_at_ms, "decision_at_ms")
            if (type(closed_prefix) not in (tuple, list)
                    or not 1 <= len(closed_prefix) <= self.max_candles):
                raise DataValidationError("bounded closed fixture prefix required")
            candles = _checked_candles(
                closed_prefix, decision_at_ms=now,
                close_safety_ms=self.close_safety_ms,
            )
            if now != candles[-1].close_time_ms + self.close_safety_ms:
                raise DataValidationError(
                    "forward PAPER decision must match last close plus safety"
                )
            previous = self._prefix
            if previous is not None:
                if len(candles) != len(previous) + 1:
                    raise DataValidationError(
                        "one and only one new closed candle per PAPER step"
                    )
                if any(not _exact_candle(left, right)
                       for left, right in zip(previous, candles)):
                    raise DataValidationError(
                        "prior PAPER candle prefix was modified or reordered"
                    )

            opening = reserve_causal_paper_open(
                candles, strategy=self.strategy, venue=self.venue,
                requested_units=self.requested_units, limits=self.limits,
                observation=observation, journal=self.journal,
                position_journal_path=self.position_journal_path,
                decision_at_ms=now, close_safety_ms=self.close_safety_ms,
            )
            if opening.orders_sent or opening.order_submission_enabled:
                raise DataValidationError("an offline PAPER step attempted real execution")
            # Commit the in-memory checkpoint only after the entire invocation
            # has safely returned. The AUTO2 SQLite journal is independent.
            self._prefix = candles
            self._accepted_ticks += 1
            self._paper_intents += opening.paper_intent_count
            return OfflineForwardPaperTick(
                self._accepted_ticks, len(candles), now, opening,
            )
        finally:
            self._step_lock.release()
