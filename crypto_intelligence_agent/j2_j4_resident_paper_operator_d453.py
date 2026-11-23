"""D453: resident PAPER-only public observation with held-position priority.

Unlike a finite D450 research window, this owner process can repeat leases
across hours and restarts. On N50/REST failure it independently subscribes to
EXISTING held PAPER symbols using D386 (no fresh N50 catalog needed). No
exchange accounts, private Bybit API, real fills, live stop or real order.

This module is deliberately NOT an installer, daemon registration or release.
The caller must invoke it in a dedicated unprivileged owner process.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Event, Thread
from typing import Callable
import json
import os
import stat
import time

from .bybit_public_ticker_state_d385 import BybitPublicTickerBook
from .bybit_public_ticker_supervisor_d386 import (
    TickerLeaseBudget, supervise_public_tickers,
    _FAILURE_CLASSES as _TICKER_FAILURE_CLASSES,
)
from .bybit_public_ws_once import ENDPOINT
from .j2_j4_dual_public_supervisor_d450 import (
    DualPaperLeaseBudget, run_dynamic_public_paper_lease_once,
)
from .j2_j4_public_paper_cycle_d449 import PaperPublicCycleConfig
from .j4_private_paper_ws_operator_d425 import (
    _MANIFEST, _private_directory, exclusive_paper_operator_lock,
    load_private_paper_routes,
)
from .market_data import DataGapError, DataValidationError
from .bybit_ws_supervisor import _SAFE_REJECTION_CLASSES
from .j4_automatic_entry_materializer_d448 import _atomic_private_write


_STATUS_FILE = "paper-operator-state-d453.json"
_LEASE_DIAGNOSTICS_FILE = "paper-last-public-lease-d459.json"
_LOCK_FILE = ".d453-resident.lock"
_SAFE_KLINE_STATES = frozenset((
    "ws_budget_ended_research_only", "ws_budget_ended_abstain",
    "ws_fail_closed_abstain", "ws_frame_budget_exhausted_abstain",
    "ws_reconnect_budget_exhausted_abstain",
))
_SAFE_TICKER_STATES = frozenset((
    "lease_completed", "lease_degraded", "lease_abstained",
    "ticker_fail_closed_abstain",
    "ticker_reconnect_budget_exhausted_abstain",
))
_MAX_HELD = 50
_MAX_CYCLES = 10_000
_HEARTBEAT_INTERVAL_SECONDS = 15.0
_ACTIVE_STATUS_TTL_MS = 45_000
_TERMINAL_STATUS_TTL_MS = 375_000


def _optins(
    *, allow_public_network: bool,
    allow_public_websocket: bool,
    confirm_personal_readonly_research: bool,
    confirm_region_eligible: bool,
    confirm_public_data_rights: bool,
    enable_hypothetical_paper_cycle: bool,
) -> bool:
    controls = (
        allow_public_network, allow_public_websocket,
        confirm_personal_readonly_research, confirm_region_eligible,
        confirm_public_data_rights, enable_hypothetical_paper_cycle,
    )
    if any(type(flag) is not bool for flag in controls):
        raise DataValidationError("D453 explicit PAPER-only access flags must be bool")
    return all(controls)


def _owner_process(home: Path) -> None:
    if (os.name != "posix" or not hasattr(os, "geteuid")
            or os.geteuid() == 0 or not home.is_absolute()):
        raise DataValidationError("D453 resident mode only for unprivileged POSIX owner")


def _resident_lock(home: Path) -> int:
    """One whole-process lock, independent of D425 per-quote lock."""
    import fcntl
    dfd = os.open(home, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fd = os.open(
            _LOCK_FILE, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
            0o600, dir_fd=dfd,
        )
    finally:
        os.close(dfd)
    try:
        s = os.fstat(fd)
        if (not stat.S_ISREG(s.st_mode) or s.st_uid != os.geteuid()
                or stat.S_IMODE(s.st_mode) != 0o600 or s.st_nlink != 1):
            raise DataValidationError("D453 resident lock is not owner-only")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fd
    except BaseException:
        os.close(fd)
        raise


def run_held_paper_without_n50(
    *, private_paper_directory: Path,
    budget: TickerLeaseBudget,
    allow_public_network: bool = False,
    allow_public_websocket: bool = False,
    confirm_personal_readonly_research: bool = False,
    confirm_region_eligible: bool = False,
    confirm_public_data_rights: bool = False,
    enable_hypothetical_paper_cycle: bool = False,
    session_factory: Callable | None = None,
    clock_args: dict | None = None,
) -> dict:
    """Keep existing PAPER stops/partials listening if N50 REST is unavailable.

    The HELD set comes from the owner-only D425 manifest. D385/D386 still
    require subscribe ACK + ticker snapshot. Nothing may create a new OPEN.
    Each callback takes the existing D425 single-writer lock.
    """
    allowed = _optins(
        allow_public_network=allow_public_network,
        allow_public_websocket=allow_public_websocket,
        confirm_personal_readonly_research=confirm_personal_readonly_research,
        confirm_region_eligible=confirm_region_eligible,
        confirm_public_data_rights=confirm_public_data_rights,
        enable_hypothetical_paper_cycle=enable_hypothetical_paper_cycle,
    )
    denied = {
        "schema_version": "d453-held-only-public-paper-fallback-v1",
        "status": "six_explicit_paper_public_data_optins_required",
        "network_attempted": False, "orders_sent": False,
        "approved_for_live_use": False,
    }
    if not allowed:
        return denied
    if (type(budget) is not TickerLeaseBudget
            or budget.max_sessions != 1
            or budget.max_seconds > 180
            or not isinstance(private_paper_directory, Path)):
        raise DataValidationError("D453 bounded held-only budget and owner path required")
    home = _private_directory(private_paper_directory)
    _owner_process(home)
    if (home / _MANIFEST).is_symlink():
        raise DataValidationError("D453 held manifest cannot be a symlink")
    if not (home / _MANIFEST).exists():
        return {**denied, "status": "no_held_paper_positions"}
    router = load_private_paper_routes(
        home, enable_hypothetical_exit_fills=True,
    )
    held = tuple(sorted(router.monitored_symbols))
    if not held:
        # Manifest may contain only CLOSED historical PAPER positions.
        # No active quote subscription or false fallback success needed.
        return {**denied, "status": "no_held_paper_positions",
                "private_paper_journal_accessed": True}
    if len(held) > _MAX_HELD:
        raise DataValidationError("D453 held-only subscription exceeds bounded scope")
    injected = session_factory is not None
    if injected:
        if (not callable(session_factory)
                or type(clock_args) is not dict
                or set(clock_args) != {"clock", "wall_ms", "sleeper"}
                or not all(callable(v) for v in clock_args.values())):
            raise DataValidationError("D453 exact held-only offline session seam required")
        wall_ms = clock_args["wall_ms"]
    else:
        if clock_args is not None or ENDPOINT != "wss://stream.bybit.com/v5/public/linear":
            raise DataValidationError("D453 only approved Bybit public WS endpoint")
        from .bybit_public_ws_once import _real_session_factory
        session_factory = _real_session_factory
        wall_ms = lambda: time.time_ns() // 1_000_000
        clock_args = {}
    start_at = wall_ms()
    book = BybitPublicTickerBook(
        ranked_symbols=held, universe_at_ms=start_at,
    )
    callbacks_accepted = [0]
    noncausal_abstentions = [0]
    def on_quote(quote):
        fd = exclusive_paper_operator_lock(home)
        try:
            try:
                router.process(quote)
            except DataGapError:
                # Old exchange timestamps/replayed sequences cannot be used
                # for a PAPER exit. Abstain on this specific quote, not the
                # entire valid held-only public subscription.
                noncausal_abstentions[0] += 1
                return
            callbacks_accepted[0] += 1
        finally:
            os.close(fd)
    report = supervise_public_tickers(
        session_factory=session_factory, book=book, budget=budget,
        on_quote=on_quote,
        on_session_reset=router.begin_new_market_session,
        **clock_args,
    )
    return {
        "schema_version": "d453-held-only-public-paper-fallback-v1",
        "status": (
            "held_paper_lease_completed"
            if report.status == "lease_completed"
            and callbacks_accepted[0] > 0
            else "held_paper_lease_degraded"
        ),
        "held_financial_quote_callbacks": callbacks_accepted[0],
        "held_noncausal_quote_abstentions": noncausal_abstentions[0],
        "data_mode": (
            "injected_offline_protocol_replay"
            if injected else "public_ws_observed_unverified"
        ),
        "network_attempted": not injected,
        "held_contract_count": len(held),
        "ticker_acks": report.subscriptions_acknowledged,
        "ticker_frames_accepted": report.ticker_frames_accepted,
        "native_stop_installed": False,
        "session_continues_after_return": False,
        "orders_sent": False, "approved_for_live_use": False,
    }


@dataclass(frozen=True)
class ResidentPaperRunPolicy:
    budget: DualPaperLeaseBudget
    restart_pause_seconds: float = 1.0
    max_cycles: int | None = None

    def __post_init__(self) -> None:
        if (type(self.budget) is not DualPaperLeaseBudget
                or type(self.restart_pause_seconds) not in (float, int)
                or not 0 <= self.restart_pause_seconds <= 30
                or (self.max_cycles is not None
                    and (type(self.max_cycles) is not int
                         or not 1 <= self.max_cycles <= _MAX_CYCLES))):
            raise DataValidationError("D453 bounded resident PAPER policy required")


def run_resident_paper_observer(
    *, private_j2_directory: Path,
    private_paper_directory: Path,
    config: PaperPublicCycleConfig,
    policy: ResidentPaperRunPolicy,
    allow_public_network: bool = False,
    allow_public_websocket: bool = False,
    confirm_personal_readonly_research: bool = False,
    confirm_region_eligible: bool = False,
    confirm_public_data_rights: bool = False,
    enable_hypothetical_paper_cycle: bool = False,
    primary_lease: Callable | None = None,
    held_fallback_lease: Callable | None = None,
    sleep: Callable | None = None,
    clock_ms: Callable | None = None,
    should_stop: Callable | None = None,
    rest_warmup_filename: str | None = None,
    auto_capture_rest_warmup: bool = False,
) -> dict:
    """Repeat real D451/D450 + D452 across leases with fail-closed held fallback.

    Never claims 24x7 venue protection: even while this local process is up,
    PAPER routes only reserve synthetic exits on incoming public quotes.
    Status is durable and has TTL; a stale status is not proof the service
    is running. No credentials, exchange orders, J1 or installation.
    """
    allowed = _optins(
        allow_public_network=allow_public_network,
        allow_public_websocket=allow_public_websocket,
        confirm_personal_readonly_research=confirm_personal_readonly_research,
        confirm_region_eligible=confirm_region_eligible,
        confirm_public_data_rights=confirm_public_data_rights,
        enable_hypothetical_paper_cycle=enable_hypothetical_paper_cycle,
    )
    if not allowed:
        return {
            "status": "six_explicit_paper_public_data_optins_required",
            "cycles_completed": 0, "orders_sent": False,
            "approved_for_live_use": False,
        }
    if (type(config) is not PaperPublicCycleConfig
            or type(policy) is not ResidentPaperRunPolicy
            or not isinstance(private_j2_directory, Path)
            or not isinstance(private_paper_directory, Path)):
        raise DataValidationError("D453 typed resident PAPER configuration required")
    home = _private_directory(private_paper_directory)
    j2home = _private_directory(private_j2_directory)
    _owner_process(home)
    if j2home == home or any(p.startswith("j1-") for p in home.parts + j2home.parts):
        raise DataValidationError("D453 dedicated distinct PAPER and J2 directories required")
    offline = primary_lease is not None or held_fallback_lease is not None
    if offline:
        if (not callable(primary_lease) or not callable(held_fallback_lease)
                or not all(callable(x) for x in (sleep, clock_ms, should_stop))
                or policy.max_cycles is None):
            raise DataValidationError("D453 offline test hooks require bounded owner test")
    else:
        if (sleep is not None or clock_ms is not None
                or (should_stop is not None and not callable(should_stop))):
            raise DataValidationError("D453 real resident mode forbids injected clocks")
        sleep = time.sleep
        clock_ms = lambda: time.time_ns() // 1_000_000
        if should_stop is None:
            should_stop = lambda: False
        primary_lease = lambda: run_dynamic_public_paper_lease_once(
            private_j2_directory=j2home, private_paper_directory=home,
            config=config, budget=policy.budget,
            allow_public_network=True, allow_public_websocket=True,
            confirm_personal_readonly_research=True, confirm_region_eligible=True,
            confirm_public_data_rights=True, enable_hypothetical_paper_cycle=True,
            rest_warmup_filename=rest_warmup_filename,
            auto_capture_rest_warmup=auto_capture_rest_warmup,
        )
        held_fallback_lease = lambda: run_held_paper_without_n50(
            private_paper_directory=home,
            # D459: D453 held-only explicitly caps fallback at 180s,
            # whereas the primary owner may use a bounded 3600s lease.
            # Pass a separately bounded budget instead of making failover
            # impossible after a long primary observation.
            budget=TickerLeaseBudget(
                max_sessions=1,
                max_frames=policy.budget.ticker.max_frames,
                max_seconds=min(180, policy.budget.ticker.max_seconds),
            ),
            allow_public_network=True, allow_public_websocket=True,
            confirm_personal_readonly_research=True, confirm_region_eligible=True,
            confirm_public_data_rights=True, enable_hypothetical_paper_cycle=True,
        )
    fd = _resident_lock(home)
    attempts = completed = fallbacks = 0
    final = "stopped"
    def persist(state: str, *, last_cycle: int, last_failure: str | None = None):
        now = clock_ms()
        if type(now) is not int or now <= 1_600_000_000_000:
            raise DataValidationError("D453 resident status needs UTC wall clock")
        payload = {
            "schema_version": "d453-resident-paper-status-v1",
            "state": state,
            "updated_at_ms": now,
            # D468: the J5/D456 reader accepts AT MOST 375 seconds.
            # A long 55m lease must refresh a short TTL; it cannot claim
            # that a silent/dead process is still actively observed for hours.
            "stale_after_ms": now + (
                _ACTIVE_STATUS_TTL_MS if state in (
                    "starting", "observing_public_lease", "held_only_fallback",
                ) else _TERMINAL_STATUS_TTL_MS
            ),
            "cycles_attempted": attempts,
            "primary_leases_completed": completed,
            "held_only_fallbacks": fallbacks,
            "last_cycle": last_cycle,
            "last_failure_class": last_failure,
            "mode": "offline_injected_test" if offline else "public_research_unverified",
            "native_protective_orders": False,
            "position_monitoring_guaranteed": False,
            "real_orders_sent": False,
        }
        _atomic_private_write(
            home, _STATUS_FILE,
            json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("ascii"),
        )
    def persist_lease_diagnostics(outcome: object, *, returned: bool) -> None:
        """One owner-only safe summary; never save raw Bybit frames or errors.

        D459 distinguishes an error raised before dual-WS supervision from
        which public subscription degraded after a valid REST/N50 cohort.
        """
        envelope = outcome if type(outcome) is dict else {}
        stream = envelope.get("dual_public_streams")
        stream = stream if type(stream) is dict else {}
        raw_status = envelope.get("status")
        observed_status = (raw_status if raw_status in (
            "finite_public_paper_research_closed",
            "finite_public_paper_research_degraded",
        ) else "not_reported")
        def allowed_status(key: str, known: frozenset[str]) -> str:
            value = stream.get(key)
            return value if type(value) is str and value in known else "not_reported"
        def bounded_failure(key: str) -> str:
            value = stream.get(key)
            safe = set(_SAFE_REJECTION_CLASSES.values())
            safe.update((
                "transport_disconnected", "frame_budget_exhausted",
                "reconnection_deferred", "receive_budget",
                "invalid_or_gapped_market_data",
                "paired_public_stream_stopped",
            ))
            return value if type(value) is str and value in safe else "none_or_unknown"
        # D469: the D466 evidence retained 50/50 real confirmed closes
        # but lost the ticker's lease_abstained reason in D459. Only admit
        # local, fixed diagnostic categories, never raw provider exceptions.
        def ticker_failure() -> str:
            value = stream.get("ticker_failure_category")
            safe = set(_TICKER_FAILURE_CLASSES.values())
            safe.update((
                "reconnect_budget_exhausted", "reconnect_deferred",
                "frame_budget_exceeded", "receive_loop_budget_exceeded",
                "no_subscription_ack", "time_budget_exceeded",
                "paired_public_stream_stopped", "internal_validation_failure",
                "invalid_market_data",
                # D475: D473's PAPER callback status was omitted from
                # D469 owner-only diagnostics, hiding the useful cause.
                "paper_cycle_callback_failed",
                "paper_risk_callback_failed", "paper_execution_callback_failed",
            ))
            return value if type(value) is str and value in safe else "none_or_unknown"
        paper = stream.get("paper_cycle")
        paper = paper if type(paper) is dict else {}
        events = paper.get("event_counts")
        events = events if type(events) is dict else {}
        contract = stream.get("public_contract_refresh")
        contract = contract if type(contract) is dict else {}
        def bounded(value) -> int | None:
            if type(value) is int and 0 <= value <= 5_000_000:
                return value
            return None
        def contract_counter(key: str) -> int | None:
            return bounded(contract.get(key))
        def counter(key: str) -> int | None:
            value = stream.get(key)
            if type(value) is int and 0 <= value <= 5_000_000:
                return value
            return None
        summary = {
            "schema_version": "d459-operator-public-lease-diagnostic-v1",
            "observed_at_ms": clock_ms(),
            "primary_result": ("returned" if returned else "raised_exception"),
            "primary_status": observed_status,
            "kline_lease_status": allowed_status(
                "kline_lease_status", _SAFE_KLINE_STATES,
            ),
            "ticker_lease_status": allowed_status(
                "ticker_lease_status", _SAFE_TICKER_STATES,
            ),
            "kline_subscription_acks": counter("kline_acks"),
            "ticker_subscription_acks": counter("ticker_acks"),
            "accepted_confirmed_close_callbacks": counter("accepted_closed_callbacks"),
            "accepted_public_ticker_callbacks": counter("accepted_public_ticker_callbacks"),
            "ticker_failure_category": ticker_failure(),
            "ticker_frames_seen": counter("ticker_frames_seen"),
            "ticker_sessions_attempted": counter("ticker_sessions_attempted"),
            "ticker_reconnects": counter("ticker_reconnects"),
            "paper_research_cohort_contracts": bounded(
                paper.get("research_cohort_contracts"),
            ),
            "paper_research_cohort_complete": (
                paper["research_cohort_complete"]
                if type(paper.get("research_cohort_complete")) is bool
                else None
            ),
            "paper_relative_btc_hypotheses": bounded(
                paper.get("eligible_relative_btc_hypotheses"),
            ),
            "paper_pending_open_count": bounded(
                paper.get("pending_paper_open_count"),
            ),
            "paper_cohort_researched_count": bounded(
                events.get("cohort_researched"),
            ),
            "kline_failure_category": bounded_failure("kline_failure_category"),
            "kline_confirmed_events_appended": counter("kline_confirmed_events_appended"),
            "kline_postclose_trade_clock_accepted": counter("kline_postclose_trade_clock_accepted"),
            "kline_temporal_discard_count": counter("kline_temporal_discard_count"),
            "historical_rest_validated_closed_candles": bounded(
                envelope.get("historical_rest_validated_closed_candles")
            ),
            "paper_contract_public_gets": contract_counter(
                "requested_public_contract_gets"
            ),
            "paper_contract_rules_unchanged": contract_counter(
                "unchanged_rules_refreshed"
            ),
            "paper_contract_rule_changes_denied": contract_counter(
                "stale_or_changed_contracts_rejected"
            ),
            "real_orders_sent": False,
            "protected_positions_at_venue": False,
        }
        _atomic_private_write(
            home, _LEASE_DIAGNOSTICS_FILE,
            json.dumps(summary, sort_keys=True, separators=(",", ":")).encode("ascii"),
        )
    def observe_with_heartbeat(
        state: str, operation: Callable[[], object],
        *, last_failure: str | None = None,
    ) -> object:
        """Keep J5's owner-only process state fresh during a long REST/WSS lease.

        This proves only the local operator is still executing: not feed
        quality, exchange stops, positions, or any public data response.
        Stop and join BEFORE any state transition so a late pulse never
        overwrites a terminal failure. A write error must not be reported
        as a healthy completed primary lease.
        """
        stop_pulse = Event()
        failures: list[Exception] = []

        def pulse() -> None:
            while not stop_pulse.wait(_HEARTBEAT_INTERVAL_SECONDS):
                try:
                    persist(state, last_cycle=attempts,
                            last_failure=last_failure)
                except Exception as error:
                    failures.append(error)
                    stop_pulse.set()
                    break

        worker = Thread(target=pulse, name="cia-paper-status-pulse",
                        daemon=True)
        worker.start()
        try:
            result = operation()
        finally:
            stop_pulse.set()
            worker.join()
        if failures:
            raise DataValidationError("D468 owner status heartbeat unavailable")
        return result

    try:
        persist("starting", last_cycle=0)
        while policy.max_cycles is None or attempts < policy.max_cycles:
            if should_stop():
                break
            attempts += 1
            persist("observing_public_lease", last_cycle=attempts)
            # A degraded research return is NOT a healthy listener, even if
            # it did not raise. Fail over to independent held ticker feed.
            primary_error: str | None = None
            try:
                observed = observe_with_heartbeat(
                    "observing_public_lease", primary_lease,
                )
                persist_lease_diagnostics(observed, returned=True)
                if (type(observed) is not dict
                        or observed.get("status") != "finite_public_paper_research_closed"
                        or observed.get("orders_sent") is not False):
                    primary_error = "degraded_primary"
                else:
                    completed += 1
            except Exception:
                # A primary programming/transport failure must NEVER abandon
                # an existing PAPER position without trying its independent
                # public ticker route. Do not print exception content.
                persist_lease_diagnostics(None, returned=False)
                primary_error = "primary_abstained"
            if primary_error is not None:
                fallbacks += 1
                persist("held_only_fallback", last_cycle=attempts,
                        last_failure=primary_error)
                # If this fails due to private state/symlink corruption, stop
                # the resident operator instead of pretending stops function.
                try:
                    fallback = observe_with_heartbeat(
                        "held_only_fallback", held_fallback_lease,
                        last_failure=primary_error,
                    )
                except Exception:
                    # An unreadable/symlinked private manifest or failing held
                    # socket is a terminal loss of PAPER quote observation.
                    # Persist failure explicitly instead of a stale "active".
                    fallback = None
                if (type(fallback) is not dict
                        or fallback.get("orders_sent") is not False
                        or fallback.get("status") not in (
                            "held_paper_lease_completed",
                            "no_held_paper_positions",
                        )):
                    final = "degraded_no_held_coverage"
                    persist(final, last_cycle=attempts,
                            last_failure=primary_error)
                    break
            persist("lease_ended_not_protected", last_cycle=attempts,
                    last_failure=primary_error)
            if policy.max_cycles is None or attempts < policy.max_cycles:
                if should_stop():
                    break
                sleep(policy.restart_pause_seconds)
        else:
            final = "bounded_run_completed"
        persist(final, last_cycle=attempts)
        return {
            "schema_version": "d453-resident-paper-observer-v1",
            "status": final,
            "cycles_attempted": attempts,
            "primary_leases_completed": completed,
            "held_only_fallbacks": fallbacks,
            "last_status_is_not_native_stop": True,
            "orders_sent": False,
            "approved_for_live_use": False,
            "session_continues_after_return": False,
        }
    finally:
        os.close(fd)
