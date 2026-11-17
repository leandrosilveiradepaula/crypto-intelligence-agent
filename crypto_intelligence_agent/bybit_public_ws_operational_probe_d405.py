"""D405: bounded, explicitly authorized PUBLIC Bybit WS market-observation probe.

No account, API key, private socket, orders, position journal or persistent
service. One finite D390/D386 lease; read-only and count-only evidence.
Offline tests inject the existing session factory and fake clock.
"""
from __future__ import annotations

import time
from typing import Callable

from .bybit_public_ticker_supervisor_d386 import TickerLeaseBudget
from .bybit_public_ticker_optin_d390 import run_readonly_bybit_ticker_lease
from .bybit_public_ws_once import StreamSession
from .market_data import DataValidationError

MAX_PROBE_SECONDS = 60
MAX_PROBE_FRAMES = 100_000


def _lag_bucket(report: dict, percentile: int) -> str | None:
    if percentile not in (95, 99):
        raise DataValidationError("D405 latency percentile invalid")
    bins = (
        ("latency_0_to_100ms", "0_to_100ms"),
        ("latency_101_to_1000ms", "101_to_1000ms"),
        ("latency_1001_to_5000ms", "1001_to_5000ms"),
        ("latency_over_5000ms", "over_5000ms"),
    )
    total = sum(report.get(name, 0) for name, _ in bins)
    if total == 0:
        return None
    target = (total * percentile + 99) // 100
    count = 0
    for name, label in bins:
        count += report[name]
        if count >= target:
            return label
    raise DataValidationError("D405 latency histogram inconsistent")


def observe_finite_public_ws_once(
    *, symbols: tuple[str, ...],
    position_symbols: tuple[str, ...] = (),
    allow_public_websocket: bool = False,
    confirm_personal_readonly_research: bool = False,
    confirm_region_eligible: bool = False,
    seconds: int = 20,
    max_frames: int = 12_000,
    max_sessions: int = 1,
    session_factory: Callable[[], StreamSession] | None = None,
    clock: Callable[[], float] = time.monotonic,
    wall_ms: Callable[[], int] = lambda: time.time_ns() // 1_000_000,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict:
    """Quantify distinct causal positive-depth quotes and age after a lease.

    The input symbols are NOT ranked or certified by this function. Real
    public transport is opened only by D390 following all three explicit
    gates; no credentials, persistence or trading functions are available.
    """
    if (type(symbols) is not tuple or type(position_symbols) is not tuple
            or not 1 <= len(symbols) <= 50
            or type(seconds) is not int
            or not 5 <= seconds <= MAX_PROBE_SECONDS
            or type(max_frames) is not int
            or not 1 <= max_frames <= MAX_PROBE_FRAMES
            or type(max_sessions) is not int or not 1 <= max_sessions <= 2
            or not callable(clock) or not callable(wall_ms) or not callable(sleeper)):
        raise DataValidationError("D405 probe input budget invalid")
    # No network and no provider-symbol leakage when any consent gate is
    # missing: validate mode before the transport can be constructed.
    if (allow_public_websocket is not True
            or confirm_personal_readonly_research is not True
            or confirm_region_eligible is not True):
        return {
            "schema_version": "bybit-public-ws-network-probe-d405-v1",
            "status": "explicit_network_and_region_optin_required",
            "network_attempted": False,
            "orders_sent": False,
            "approved_for_live_use": False,
        }
    before_ms = wall_ms()
    if type(before_ms) is not int or not 1_600_000_000_000 <= before_ms < 4_102_444_800_000:
        raise DataValidationError("D405 wall clock invalid")
    elapsed_start = clock()
    # At most one minute before the actual lease. This is merely a
    # locally chosen causal bound, NOT a PIT market ranking attestation.
    snapshot = run_readonly_bybit_ticker_lease(
        ranked_symbols=symbols,
        position_symbols=position_symbols,
        universe_at_ms=before_ms - 60_000,
        allow_public_websocket=True,
        confirm_personal_readonly_research=True,
        confirm_region_eligible=True,
        measure_public_coverage=True,
        budget=TickerLeaseBudget(
            max_sessions=max_sessions, max_frames=max_frames,
            max_seconds=seconds,
        ),
        session_factory=session_factory,
        clock=clock, wall_ms=wall_ms, sleeper=sleeper,
    )
    duration = max(0, clock() - elapsed_start)
    if duration > MAX_PROBE_SECONDS + 20:
        raise DataValidationError("D405 clock duration invalid")
    result = {
        "schema_version": "bybit-public-ws-network-probe-d405-v1",
        "status": snapshot["status"],
        # Injected sockets are synthetic even when ACK/frames are accepted.
        # Never present an offline fixture as real Bybit network evidence.
        "data_mode": ("real_public_websocket" if session_factory is None
                      else "injected_offline_fixture"),
        "network_attempted": session_factory is None,
        "real_market_frames_verified": (
            session_factory is None
            and snapshot["subscriptions_acknowledged"] >= 1
            and snapshot["ticker_frames_accepted"] > 0),
        "scope_source": "operator_supplied_symbols_not_independently_ranked",
        "requested_contracts": snapshot["requested_distinct_contracts"],
        "ranked_input_count": snapshot["requested_ranked_contracts"],
        "position_input_count": snapshot["requested_position_contracts"],
        "received_distinct_contracts": snapshot["unique_distinct_contracts_observed"],
        "received_ranked_input_count": snapshot["unique_ranked_contracts_observed"],
        "received_position_input_count": snapshot["unique_position_contracts_observed"],
        "fresh_contracts_at_end": snapshot["fresh_distinct_contracts_at_end"],
        "finite_coverage_observed_once": snapshot["finite_coverage_observed_once"],
        "finite_coverage_fresh_at_end": snapshot["finite_coverage_fresh_at_end"],
        "subscription_acks": snapshot["subscriptions_acknowledged"],
        "market_frames_accepted": snapshot["ticker_frames_accepted"],
        "frames_seen": snapshot["frames_seen"],
        "preack_frames_discarded": snapshot["preack_frames_discarded"],
        "preack_frames_bootstrapped_after_ack":
            snapshot["preack_frames_bootstrapped_after_ack"],
        "sessions_attempted": snapshot["sessions_attempted"],
        "reconnects": snapshot["reconnects"],
        "ping_frames": snapshot["heartbeat_pings"],
        "pong_frames": snapshot["heartbeat_pongs"],
        "p95_event_lag_bucket": _lag_bucket(snapshot, 95),
        "p99_event_lag_bucket": _lag_bucket(snapshot, 99),
        "elapsed_seconds": round(duration, 3),
        "failure_category": snapshot["failure_category"],
        "quotes_persisted": False,
        "paper_position_state_changed": False,
        "scope_independently_verified": False,
        "continuous_24x7_verified": False,
        "marketwide_top50_verified": False,
        "no_service_installed": True,
        "orders_sent": False,
        "approved_for_signals": False,
        "approved_for_live_use": False,
    }
    return result
