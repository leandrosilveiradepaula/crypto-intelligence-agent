"""J4/RUNNER3: local PAPER runner-trigger preview, never a submission.

A deterministic synthetic REDUCE_ONLY intent can be *prepared* after the
RUNNER2 replay certifies a hypothetical trigger. No writer or exchange
transport is imported. Actual PAPER reservation remains a separate caller
action and always rechecks AUTO4 under its own SQLite transaction.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path

from .market_data import DataValidationError
from .paper_position_inspection import inspect_paper_position
from .paper_runner_journal import load_paper_runner_journal
from .paper_runner_trailing import PaperRunnerTrailPolicy, PaperRunnerTrailState
from .synthetic_manual_exit_replay import _utc_ms
from .synthetic_order_lifecycle import (
    PaperOrderEffect, PaperOrderIntent, PaperOrderSide,
)
from .synthetic_position_state import SyntheticSide


@dataclass(frozen=True)
class PaperRunnerClosePreview:
    """An offline research intent. Not a native stop or fill."""

    intent: PaperOrderIntent
    position_id: str
    runner_report_digest_sha256: str
    runner_tick_count: int
    source_checkpoint_ms: int

    @property
    def orders_sent(self) -> bool:
        return False

    @property
    def native_stop_verified(self) -> bool:
        return False

    @property
    def approved_for_live_use(self) -> bool:
        return False

    @property
    def order_submission_enabled(self) -> bool:
        return False


def preview_paper_runner_close(
    runner_path: str | Path,
    position_path: str | Path,
    position_id: str,
    *,
    policy: PaperRunnerTrailPolicy,
    as_of_ms: int,
) -> PaperRunnerClosePreview:
    """Prepare but NEVER reserve/send a residual PAPER exit.

    RUNNER2 and AUTO4 live in separate SQLite databases. A before/after
    inspection detects observed checkpoint drift; it cannot guarantee an
    atomic cross-file snapshot. A later reservation must check its own
    entire AUTO4 state atomically, including any competing pending exit.
    """
    cutoff = _utc_ms(as_of_ms, "runner close preview cutoff")
    before = inspect_paper_position(position_path, position_id)
    report = load_paper_runner_journal(
        runner_path, position_path, position_id, policy=policy,
        as_of_ms=cutoff,
    )
    after = inspect_paper_position(position_path, position_id)
    if before != after:
        raise DataValidationError("PAPER position drift during runner close preview")
    b = after.balance
    if (report.state is not PaperRunnerTrailState.TRIGGERED_HYPOTHETICAL_ONLY
            or report.triggered_tick_number is None
            or b.as_of_ms > cutoff
            or b.runner_floor_units <= 0
            or b.confirmed_remaining_units != b.runner_floor_units
            or b.unreserved_units != b.runner_floor_units
            or b.runner_filled_units != 0
            or b.runner_reserved_unfilled_units != 0
            or any(t.filled_units != t.target_units or
                   t.reserved_unfilled_units != 0 or t.unallocated_units != 0
                   for t in b.tranches)
            or any(x.snapshot.requires_reconciliation for x in b.exit_orders)):
        raise DataValidationError("runner not fully confirmed or hypothetical trigger absent")
    fingerprint = json.dumps(
        {
            "position": b.position_id,
            "checkpoint": b.as_of_ms,
            "runner_digest": report.digest_sha256,
            "cutoff": cutoff,
            "remaining": str(b.confirmed_remaining_units),
            "plan": b.plan_version,
        },
        separators=(",", ":"), sort_keys=True,
    ).encode("ascii")
    digest = sha256(fingerprint).hexdigest()[:32]
    if b.side is SyntheticSide.LONG:
        direction = PaperOrderSide.SELL
    elif b.side is SyntheticSide.SHORT:
        direction = PaperOrderSide.BUY
    else:
        raise DataValidationError("unsupported synthetic PAPER runner direction")
    intent = PaperOrderIntent(
        intent_id="fixture_runner_close_" + digest,
        fixture_signal_id="fixture_runner_signal_" + digest,
        venue=b.venue, symbol=b.symbol, position_side=b.side,
        side=direction, effect=PaperOrderEffect.REDUCE_ONLY,
        requested_units=b.runner_floor_units,
        max_reducible_units=b.confirmed_remaining_units,
        created_at_ms=cutoff,
    )
    return PaperRunnerClosePreview(
        intent=intent, position_id=b.position_id,
        runner_report_digest_sha256=report.digest_sha256,
        runner_tick_count=report.observed_tick_count,
        source_checkpoint_ms=b.as_of_ms,
    )
