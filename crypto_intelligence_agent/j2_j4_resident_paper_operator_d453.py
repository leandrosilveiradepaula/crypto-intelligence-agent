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
from typing import Callable
import json
import os
import stat
import time

from .bybit_public_ticker_state_d385 import BybitPublicTickerBook
from .bybit_public_ticker_supervisor_d386 import (
    TickerLeaseBudget, supervise_public_tickers,
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
from .j4_automatic_entry_materializer_d448 import _atomic_private_write


_STATUS_FILE = "paper-operator-state-d453.json"
_LOCK_FILE = ".d453-resident.lock"
_MAX_HELD = 50
_MAX_CYCLES = 10_000


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
    if not 1 <= len(held) <= _MAX_HELD:
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
    def on_quote(quote):
        fd = exclusive_paper_operator_lock(home)
        try:
            router.process(quote)
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
            else "held_paper_lease_degraded"
        ),
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
        if any(x is not None for x in (sleep, clock_ms, should_stop)):
            raise DataValidationError("D453 real resident operator has no injected clocks")
        sleep = time.sleep
        clock_ms = lambda: time.time_ns() // 1_000_000
        should_stop = lambda: False
        primary_lease = lambda: run_dynamic_public_paper_lease_once(
            private_j2_directory=j2home, private_paper_directory=home,
            config=config, budget=policy.budget,
            allow_public_network=True, allow_public_websocket=True,
            confirm_personal_readonly_research=True, confirm_region_eligible=True,
            confirm_public_data_rights=True, enable_hypothetical_paper_cycle=True,
        )
        held_fallback_lease = lambda: run_held_paper_without_n50(
            private_paper_directory=home,
            budget=policy.budget.ticker,
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
            "stale_after_ms": now + 2 * policy.budget.ticker.max_seconds * 1000 + 15_000,
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
                observed = primary_lease()
                if (type(observed) is not dict
                        or observed.get("status") != "finite_public_paper_research_closed"
                        or observed.get("orders_sent") is not False):
                    primary_error = "degraded_primary"
                else:
                    completed += 1
            except Exception:
                # A primary programming/transport failure must NEVER abandon
                # an existing PAPER position without trying its independent
                # public ticker route. Do not print the exception or private
                # symbol; do not retry the failed opening on the same tick.
                primary_error = "primary_abstained"
            if primary_error is not None:
                fallbacks += 1
                persist("held_only_fallback", last_cycle=attempts,
                        last_failure=primary_error)
                # If this fails due to private state/symlink corruption, stop
                # the resident operator instead of pretending stops function.
                try:
                    fallback = held_fallback_lease()
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
