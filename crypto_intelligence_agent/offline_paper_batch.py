"""J6/PRE3: finite, unattended OFFLINE fixture batch with durable cursor.

All inputs are explicit SYNTHETIC candles and hypothetical risk snapshots.
No exchange feed, automatic real orders, scheduling, execution, fills,
financial PnL, venue approval, new database schema or provider credentials.
A successful restart can ONLY advance from the exact existing AUTO2 cursor.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Sequence

from .market_data import ClosedCandle, DataValidationError
from .offline_paper_durable_cursor import (
    _load_cursor, _verify_cursor_orders, recover_durable_offline_paper,
    step_durable_offline_paper,
)
from .paper_order_store import (
    SQLitePaperOrderJournal, _TABLES as _ORDER_TABLES, _VERSION as _ORDER_VERSION,
)
from .paper_position_inspection import _checked_path, _read_database
from .paper_risk_gate import PaperRiskLimits, PaperRiskObservation
from .synthetic_entry_hypotheses import CompressionBreakoutConfig
from .synthetic_feature_engine import MAX_CANDLES, validate_synthetic_closed_candles
from .synthetic_manual_exit_replay import _fixture_units
from .synthetic_order_lifecycle import PaperVenue

MAX_NEW_STEPS = 64


@dataclass(frozen=True)
class OfflinePaperBatchReport:
    """Only decision COUNTS; alternative PAPER intents are not executed fills."""

    input_candle_count: int
    starting_checkpoint_count: int
    final_checkpoint_count: int
    processed_steps: int
    candidate_steps: int
    reserved_open_intents: int
    risk_or_health_denials: int
    no_fresh_hypothesis_steps: int
    reasons: tuple[tuple[str, int], ...]
    recovered_prior_checkpoint: bool
    all_supplied_candles_processed: bool

    @property
    def quality(self) -> str:
        return "offline_synthetic_fixture_replay_only"

    @property
    def durable_cursor_committed(self) -> bool:
        return self.processed_steps > 0 or self.recovered_prior_checkpoint

    @property
    def orders_sent(self) -> bool:
        return False

    @property
    def exchange_feed_connected(self) -> bool:
        return False

    @property
    def financial_backtest_approved(self) -> bool:
        return False

    @property
    def live_trading_authorized(self) -> bool:
        return False

    @property
    def approved_for_live_use(self) -> bool:
        return False


def run_durable_offline_paper_batch(
    candles: Sequence[ClosedCandle], *,
    observations: Sequence[PaperRiskObservation],
    strategy: CompressionBreakoutConfig,
    venue: PaperVenue,
    requested_units: Decimal,
    limits: PaperRiskLimits,
    journal: SQLitePaperOrderJournal,
    position_journal_path: str | Path,
    bootstrap_candles: int,
    max_new_steps: int = MAX_NEW_STEPS,
    close_safety_ms: int = 1_000,
    max_candles: int = MAX_CANDLES,
) -> OfflinePaperBatchReport:
    """Advance 1..64 synthetic bars, recovering exact prior AUTO2 prefix.

    First call starts at the caller's explicit warmup prefix. Next calls
    inspect the SAME journal in read-only mode, verify the previous full
    prefix/context/OPEN inventory and continue ONE bar per atomic commit.
    A completed input is a no-op: no OPEN replay or duplicate writes.

    Risk snapshots are HYPOTHETICAL inputs, not inferred account balances,
    real marks, leverage tiers or liquidity. Every supplied snapshot must
    refer to its corresponding candle, even those already behind the cursor.
    The full supplied dataset is validated BEFORE any batch step commits.
    """
    if (type(strategy) is not CompressionBreakoutConfig
            or type(venue) is not PaperVenue
            or type(requested_units) is not Decimal
            or type(limits) is not PaperRiskLimits
            or type(journal) is not SQLitePaperOrderJournal
            or not isinstance(position_journal_path, (str, Path))
            or type(bootstrap_candles) is not int
            or type(max_new_steps) is not int
            or not 1 <= max_new_steps <= MAX_NEW_STEPS
            or type(max_candles) is not int
            or not 1 <= max_candles <= MAX_CANDLES
            or type(close_safety_ms) is not int
            or not 0 <= close_safety_ms <= 86_400_000):
        raise DataValidationError("explicit bounded offline batch configuration required")
    _fixture_units(requested_units)
    if (type(candles) not in (tuple, list)
            or not 1 <= len(candles) <= max_candles
            or not 1 <= bootstrap_candles <= len(candles)
            or type(observations) not in (tuple, list)
            or len(observations) != len(candles)):
        raise DataValidationError("complete bounded synthetic candles and risk snapshots required")

    final_at = candles[-1].close_time_ms + close_safety_ms
    cs = validate_synthetic_closed_candles(
        candles, decision_at_ms=final_at,
        close_safety_ms=close_safety_ms,
    )
    for bar, observation in zip(cs, observations):
        if (type(observation) is not PaperRiskObservation
                or observation.venue is not venue
                or observation.symbol != bar.symbol
                or observation.observed_at_ms < bar.open_time_ms
                or observation.observed_at_ms > bar.close_time_ms + close_safety_ms):
            raise DataValidationError("PAPER risk snapshot must match its fixture candle and clock")

    orders_path = _checked_path(journal.path)
    positions_path = _checked_path(position_journal_path)
    if orders_path == positions_path:
        raise DataValidationError("PAPER orders and positions must use separate SQLite files")

    # Read existing state WITHOUT starting new orders or creating any database.
    with _read_database(
        orders_path, _ORDER_TABLES, "paper_order_meta", _ORDER_VERSION,
    ) as connection:
        previous = _load_cursor(connection)
        _verify_cursor_orders(connection, previous)

    recovered = previous is not None
    if recovered:
        already = previous.seal.candle_count
        if not bootstrap_candles <= already <= len(cs):
            raise DataValidationError("PAPER historical bootstrap or cursor length differs")
        # Verify exact price-scale, strategy/risk parameters and prior OPEN ids
        # before processing anything new. A replay of the already-finished
        # input must still pass this integrity check.
        verified = recover_durable_offline_paper(
            cs[:already], strategy=strategy, venue=venue,
            requested_units=requested_units, limits=limits,
            journal=journal, close_safety_ms=close_safety_ms,
            max_candles=max_candles,
        )
        if verified != previous.seal:
            raise DataValidationError("PAPER replay checkpoint differs")
        starting = already
        next_count = already + 1
    else:
        starting = 0
        next_count = bootstrap_candles

    reasons: dict[str, int] = {}
    candidate = reserved = 0
    last_count = starting
    upper = min(len(cs), next_count + max_new_steps - 1)
    for count in range(next_count, upper + 1):
        last = cs[count - 1]
        tick = step_durable_offline_paper(
            cs[:count], strategy=strategy, venue=venue,
            requested_units=requested_units, limits=limits,
            observation=observations[count - 1], journal=journal,
            position_journal_path=positions_path,
            decision_at_ms=last.close_time_ms + close_safety_ms,
            close_safety_ms=close_safety_ms, max_candles=max_candles,
        )
        if (tick.orders_sent or tick.order_submission_enabled
                or tick.approved_for_live_use
                or tick.accepted_candle_count != count):
            raise DataValidationError("unexpected non-fixture PAPER batch result")
        candidate += int(tick.opening.candidate is not None)
        reserved += int(tick.opening.paper_intent_reserved)
        reasons[tick.opening.reason] = reasons.get(tick.opening.reason, 0) + 1
        last_count = count

    processed = max(0, upper - next_count + 1)
    denies = sum(
        n for reason, n in reasons.items()
        if reason.startswith("paper_risk_denied_")
        or reason.startswith("paper_open_health_denied_")
    )
    return OfflinePaperBatchReport(
        input_candle_count=len(cs),
        starting_checkpoint_count=starting,
        final_checkpoint_count=last_count,
        processed_steps=processed,
        candidate_steps=candidate,
        reserved_open_intents=reserved,
        risk_or_health_denials=denies,
        no_fresh_hypothesis_steps=reasons.get("no_fresh_synthetic_hypothesis", 0),
        reasons=tuple(sorted(reasons.items())),
        recovered_prior_checkpoint=recovered,
        all_supplied_candles_processed=last_count == len(cs),
    )
