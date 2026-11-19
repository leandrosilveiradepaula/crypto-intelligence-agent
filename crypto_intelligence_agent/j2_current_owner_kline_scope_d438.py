"""D438: owner-only, READ-ONLY current J1 N50 -> D437 public kline scope.

No second ranker, fresh HTTP, separate J1 writer, ticker service or order.
Every launch revalidates J1's existing private epoch/cache before and after
loading the *typed* WS scope. This is still provisional research metadata.
"""
from __future__ import annotations

from pathlib import Path

from .bybit_closed_stream_cache import (
    MAX_SCOPE_AGE_MS, OfflineReviewedStreamScope, _scope_contract_fingerprint,
)
from .j1_n50_ws_dynamic_scope import DynamicN50WSAdmission
from .j1_n50_ws_epoch_rotation import load_active_n50_ws_epoch
from .j1_n50_ws_private_cache import load_n50_ws_dynamic_admission
from .j2_current_j1_n50_public_scope_d406 import (
    CurrentResearchN50, read_current_j1_n50_scope,
)
from .market_data import DataGapError, DataValidationError


def read_current_owner_n50_kline_scope(
    *, state_directory: Path, now_ms: int, allow_private_pointer_read: bool = False,
) -> OfflineReviewedStreamScope:
    """Load exactly one owner-revalidated provisional cohort for a finite pilot.

    Fail closed on epoch/metadata change during the read, stale/future data,
    absent BTCUSDT, or a malformed scope. No symbols/paths in error strings.
    """
    if (allow_private_pointer_read is not True
            or not isinstance(state_directory, Path)
            or not state_directory.is_absolute()
            or type(now_ms) is not int
            or now_ms <= 1_600_000_000_000):
        raise DataValidationError("D438 explicit owner scope read required")
    try:
        first = read_current_j1_n50_scope(
            state_directory=state_directory, now_ms=now_ms,
            allow_private_pointer_read=True,
        )
        pointer = load_active_n50_ws_epoch(
            state_directory=state_directory, current_at_ms=now_ms,
            allow_private_pointer_read=True,
        )
        if (type(first) is not CurrentResearchN50
                or pointer.status != "active_n50_ws_epoch_revalidated"
                or pointer.ws_directory is None
                or pointer.ranked_scope_sha256 != first.ranked_scope_sha256
                or pointer.ws_metadata_sha256 != first.metadata_sha256
                or pointer.activated_at_ms != first.activated_at_ms):
            raise DataGapError("D438 owner pointer changed")
        cached = load_n50_ws_dynamic_admission(
            directory=pointer.ws_directory, current_at_ms=now_ms,
            expected_ranked_scope_sha256=first.ranked_scope_sha256,
            allow_private_scope_read=True,
        )
        last = read_current_j1_n50_scope(
            state_directory=state_directory, now_ms=now_ms,
            allow_private_pointer_read=True,
        )
        if type(last) is not CurrentResearchN50 or last != first:
            raise DataGapError("D438 N50 rotated during read")
        admission = cached.admission
        if (cached.status != "private_n50_ws_admission_loaded_revalidated"
                or type(admission) is not DynamicN50WSAdmission
                or admission.ranked_scope_sha256 != first.ranked_scope_sha256
                or admission.metadata_sha256 != first.metadata_sha256
                or admission.selected_contracts != 50):
            raise DataGapError("D438 owner metadata changed")
        scope = admission.ws_scope
        if (type(scope) is not OfflineReviewedStreamScope
                or scope.registry_sha256 != first.metadata_sha256
                or scope.observed_at_ms != admission.observed_at_ms
                or not 0 <= now_ms - scope.observed_at_ms <= MAX_SCOPE_AGE_MS
                or len(scope.contracts) != 50
                or len(first.symbols) != 50):
            raise DataGapError("D438 owner scope stale or incomplete")
        _scope_contract_fingerprint(scope)
        members = frozenset(m.symbol for m in scope.contracts)
        if members != frozenset(first.symbols) or "BTCUSDT" not in members:
            raise DataGapError("D438 observed research symbol unavailable")
        return scope
    except (OSError, ValueError, TypeError, KeyError, AttributeError,
            OverflowError, DataValidationError, DataGapError):
        raise DataGapError("D438 owner N50 research scope unavailable") from None
