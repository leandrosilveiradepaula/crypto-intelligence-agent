"""D418: bounded sustained Bybit public N50 observation with owner revalidation.

Research-only transport using the existing D385/D386/D390 receiver and J1
owner cohort reader. No account endpoint, secrets, order sender, SQLite,
service installation, synthetic PAPER reservation, or second J1 writer.
This can observe longer than D406's <=60s diagnostic, but does NOT constitute
a continuous 24x7 worker or attest trading readiness.
"""
from __future__ import annotations

from pathlib import Path
import time
from typing import Callable

from .bybit_public_ticker_optin_d390 import run_readonly_bybit_ticker_lease
from .bybit_public_ticker_state_d385 import MAX_MONITORED, _symbols
from .bybit_public_ticker_supervisor_d386 import TickerLeaseBudget
from .bybit_public_ws_once import StreamSession
from .j2_current_j1_n50_public_scope_d406 import read_current_j1_n50_scope
from .market_data import DataGapError, DataValidationError

_SCHEMA = "j2-current-n50-sustained-market-observation-d418-v1"
_SCOPE = "owner_j1_revalidated_provisional_n50_not_marketwide"
_MAX_UTC_MS = 4_102_444_800_000


def observe_current_n50_sustained_once(
    *, state_directory: Path,
    allow_private_pointer_read: bool = False,
    allow_public_websocket: bool = False,
    confirm_personal_readonly_research: bool = False,
    confirm_region_eligible: bool = False,
    position_symbols: tuple[str, ...] = (),
    seconds: int = 120,
    max_frames: int = 200_000,
    max_sessions: int = 2,
    session_factory: Callable[[], StreamSession] | None = None,
    clock: Callable[[], float] = time.monotonic,
    wall_ms: Callable[[], int] = lambda: time.time_ns() // 1_000_000,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict:
    """Observe 60-900s, then revalidate the current J1 cohort.

    Subscription is public and read-only. PAPER positions outside the N50 can
    be *included* by the caller, but no position journal is opened and no
    signal/exit/fill action is performed. A quiet contract is not rewritten
    with a synthetic or REST replacement tick.

    Changing owner epoch during the lease invalidates the final cohort proof
    rather than silently treating both epochs as one stable population.
    The last-session count-only freshness partition uses EXCHANGE timestamps.
    """
    gates = (
        allow_private_pointer_read, allow_public_websocket,
        confirm_personal_readonly_research, confirm_region_eligible,
    )
    if any(type(v) is not bool for v in gates):
        raise DataValidationError("D418 owner and public gate type invalid")
    if not all(gates):
        return {
            "schema_version": _SCHEMA,
            "status": "owner_and_public_network_optin_required",
            "private_state_read": False,
            "network_attempted": False,
            "orders_sent": False,
            "approved_for_live_use": False,
        }
    if (not isinstance(state_directory, Path) or not state_directory.is_absolute()
            or type(position_symbols) is not tuple
            or len(position_symbols) > MAX_MONITORED
            or type(seconds) is not int or not 60 <= seconds <= 900
            or type(max_frames) is not int or not 1_000 <= max_frames <= 200_000
            or type(max_sessions) is not int or not 1 <= max_sessions <= 2
            or (session_factory is not None and not callable(session_factory))
            or not all(callable(fn) for fn in (clock, wall_ms, sleeper))):
        raise DataValidationError("D418 sustained public observation budget invalid")
    if position_symbols:
        _symbols(position_symbols, maximum=MAX_MONITORED)

    before_ms = wall_ms()
    if (type(before_ms) is not int
            or not 1_600_000_000_000 <= before_ms < _MAX_UTC_MS):
        raise DataValidationError("D418 wall clock invalid")
    before_clock = clock()
    if type(before_clock) not in (float, int):
        raise DataValidationError("D418 monotonic clock invalid")
    # J1 owner scope/metadata admission is loaded read-only, exactly once
    # before network. This function does not re-rank or query REST.
    before = read_current_j1_n50_scope(
        state_directory=state_directory, now_ms=before_ms,
        allow_private_pointer_read=True,
    )
    if (len(before.symbols) != 50
            or len(set(before.symbols) | set(position_symbols)) > MAX_MONITORED):
        raise DataValidationError("D418 N50 and held-position membership invalid")

    report = run_readonly_bybit_ticker_lease(
        ranked_symbols=before.symbols,
        position_symbols=position_symbols,
        universe_at_ms=before_ms - 60_000,
        allow_public_websocket=True,
        confirm_personal_readonly_research=True,
        confirm_region_eligible=True,
        measure_public_coverage=True,
        diagnose_public_freshness=True,
        budget=TickerLeaseBudget(
            max_sessions=max_sessions, max_frames=max_frames,
            max_seconds=seconds,
        ),
        session_factory=session_factory,
        clock=clock, wall_ms=wall_ms, sleeper=sleeper,
    )
    after_ms = wall_ms()
    after_clock = clock()
    if (type(after_ms) is not int or after_ms < before_ms
            or after_ms >= _MAX_UTC_MS
            or type(after_clock) not in (float, int)
            or not 0 <= after_clock - before_clock <= seconds + 30):
        raise DataValidationError("D418 observation clock invalid")
    unchanged = False
    try:
        after = read_current_j1_n50_scope(
            state_directory=state_directory, now_ms=after_ms,
            allow_private_pointer_read=True,
        )
        unchanged = (
            after.activated_at_ms == before.activated_at_ms
            and after.ranked_scope_sha256 == before.ranked_scope_sha256
            and after.metadata_sha256 == before.metadata_sha256
            and after.symbols == before.symbols
        )
    except (DataGapError, DataValidationError, OSError, ValueError, TypeError):
        # Scope rotation or unreadability is a degraded SAMPLE, not a reason
        # to invent a ticker-to-position mapping or to return private paths.
        pass

    network = session_factory is None
    completed = (
        report["status"] == "lease_completed"
        and report["subscriptions_acknowledged"] >= 1
    )
    observed_all = (
        completed and unchanged
        and report["finite_coverage_observed_once"] is True
    )
    status = (
        "sustained_owner_scope_changed_or_unavailable" if not unchanged
        else "sustained_market_observed_once" if observed_all
        else "sustained_market_degraded_or_partial"
    )
    # D390 emits a bounded, count-only report. Never return private symbols,
    # prices, position IDs, WS raw packets or the private directory.
    return {
        **report,
        "schema_version": _SCHEMA,
        "status": status,
        "underlying_ws_status": report["status"],
        "observation_elapsed_seconds": round(after_clock - before_clock, 3),
        "requested_observation_seconds": seconds,
        "data_mode": (
            "real_public_websocket" if network else "injected_offline_fixture"
        ),
        "network_attempted": network,
        "real_market_frames_verified": (
            network and report["subscriptions_acknowledged"] > 0
            and report["ticker_frames_accepted"] > 0
        ),
        "scope_source": _SCOPE,
        "owner_scope_members": 50,
        "ranked_scope_sha256": before.ranked_scope_sha256,
        "metadata_sha256": before.metadata_sha256,
        "positions_outside_n50_subscribed": len(
            set(position_symbols) - set(before.symbols)
        ),
        "owner_scope_unchanged_after_lease": unchanged,
        "finite_current_owner_scope_observed_once": observed_all,
        "private_state_read": True,
        "private_state_modified": False,
        "paper_position_state_changed": False,
        "paper_reservations_enabled": False,
        "quotes_persisted": False,
        "no_service_installed": True,
        "scope_independently_verified": False,
        "marketwide_top50_verified": False,
        "crypto_identity_independently_verified": False,
        "continuous_24x7_verified": False,
        "approved_for_signals": False,
        "orders_sent": False,
        "approved_for_live_use": False,
    }
