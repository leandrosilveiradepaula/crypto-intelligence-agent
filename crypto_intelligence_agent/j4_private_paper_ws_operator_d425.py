"""D425: private PAPER route manifest -> existing D410 real public WS bridge.

Finite opt-in operator, NOT a service. Public Bybit ticker quotes may create
only hypothetical AUTO4 exit reservations in an existing private PAPER journal.
This module never creates positions, executes fills, touches J1 as a writer,
authenticates a venue or sends financial orders.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
try:
    import fcntl  # POSIX-only private PAPER owner lock
except ImportError:  # Windows offline CI imports this module but never runs it
    fcntl = None
import json
import os
from pathlib import Path
import re
import stat
from typing import Callable

from .bybit_public_ticker_supervisor_d386 import TickerLeaseBudget
from .j2_j4_current_n50_paper_lease_d410 import run_current_n50_paper_lease_once
from .market_data import DataValidationError
from .paper_intrahour_emergency_stop_d388 import PaperEmergencyStopRule
from .paper_causal_fill_d394 import PaperObservedFillAssumptions
from .paper_intrahour_quote_router_d391 import (
    PaperIntrahourQuoteRouter, PaperQuoteRoute,
)
from .paper_intrahour_target_step_d387 import (
    PaperIntrahourTargetPolicy, _levels_valid,
)
from .paper_position_inspection import inspect_paper_position
from .paper_runner_trailing import PaperRunnerTrailPolicy

_SCHEMA = "j4-private-paper-routes-d425-v1"
_MANIFEST = "paper-routes.json"
_JOURNAL = "paper-positions.sqlite"
_LOCK = ".paper-ws-operator.lock"
_RUNNER_NAME = re.compile(r"runner-[A-Za-z0-9_-]{1,48}\.sqlite\Z")
_LIMIT = 32_768
_MAX_POSITIONS = 50


def _private_directory(directory: Path) -> Path:
    if (not isinstance(directory, Path) or not directory.is_absolute()
            or directory.is_symlink() or os.name != "posix"
            or os.geteuid() == 0):
        raise DataValidationError("D425 requires nonroot owner private directory")
    try:
        info = directory.stat()
    except OSError as exc:
        raise DataValidationError("D425 private directory not available") from exc
    if (not stat.S_ISDIR(info.st_mode)
            or stat.S_IMODE(info.st_mode) != 0o700
            or info.st_uid != os.geteuid()):
        raise DataValidationError("D425 private directory owner/mode invalid")
    return directory


def _owner_file(directory: Path, name: str) -> int:
    """Open only an owned, one-link 0600 regular file, with no symlink."""
    fd_dir = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd_dir)
    finally:
        os.close(fd_dir)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode)
                or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_uid != os.geteuid() or info.st_nlink != 1):
            raise DataValidationError("D425 private file owner/mode invalid")
        return fd
    except BaseException:
        os.close(fd)
        raise


def _decimal(value: object) -> Decimal:
    if (type(value) is not str or not 1 <= len(value) <= 44):
        raise DataValidationError("D425 Decimal must be a bounded string")
    try:
        amount = Decimal(value)
    except (InvalidOperation, ValueError):
        raise DataValidationError("D425 invalid Decimal price") from None
    if (not amount.is_finite() or amount <= 0
            or len(amount.as_tuple().digits) > 40
            or not -24 <= amount.as_tuple().exponent <= 24):
        raise DataValidationError("D425 invalid positive Decimal")
    return amount


def _spread(value: object) -> Decimal:
    if value == "0":
        return Decimal("0")
    return _decimal(value)


def _no_duplicate_pairs(pairs: list[tuple[str, object]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("D425 duplicate manifest field")
        result[key] = value
    return result


def load_private_paper_routes(
    directory: Path, *,
    enable_hypothetical_exit_fills: bool = False,
    exit_fill_policy: PaperObservedFillAssumptions | None = None,
) -> PaperIntrahourQuoteRouter:
    """Map EXISTING AUTO4 positions to exact stop/target/runner policies.

    The manifest contains only private PAPER identifiers and hypothetical
    trigger prices; there is no account identity or venue secret. All routes
    are verified before opening the WebSocket or changing PAPER reservations.
    """
    if (type(enable_hypothetical_exit_fills) is not bool
            or (exit_fill_policy is not None
                and type(exit_fill_policy) is not PaperObservedFillAssumptions)
            or (not enable_hypothetical_exit_fills
                and exit_fill_policy is not None)):
        raise DataValidationError("D425 explicit PAPER-only fill modeling gate invalid")
    home = _private_directory(directory)
    try:
        fd = _owner_file(home, _MANIFEST)
        with os.fdopen(fd, "rb") as source:
            raw = source.read(_LIMIT + 1)
        if not 2 <= len(raw) <= _LIMIT:
            raise DataValidationError("D425 private manifest too large")
        data = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_no_duplicate_pairs,
            parse_float=lambda _: (_ for _ in ()).throw(ValueError("float")),
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("constant")),
        )
        if (type(data) is not dict or set(data) != {"schema_version", "positions"}
                or data["schema_version"] != _SCHEMA
                or type(data["positions"]) is not list
                or not 1 <= len(data["positions"]) <= _MAX_POSITIONS):
            raise DataValidationError("D425 routes manifest schema invalid")
        journal_fd = _owner_file(home, _JOURNAL)
        os.close(journal_fd)
        journal = home / _JOURNAL
        routes: list[PaperQuoteRoute] = []
        runner_names: set[str] = set()
        for item in data["positions"]:
            if (type(item) is not dict
                    or set(item) != {
                        "position_id", "plan_version", "stop_mark_price",
                        "target_prices", "max_spread_bps", "runner",
                    } or type(item["position_id"]) is not str
                    or type(item["plan_version"]) is not str
                    or type(item["target_prices"]) is not list
                    or not 1 <= len(item["target_prices"]) <= 64):
                raise DataValidationError("D425 position route fields invalid")
            stop = PaperEmergencyStopRule(
                _decimal(item["stop_mark_price"]), max_quote_age_ms=3_000,
            )
            targets = PaperIntrahourTargetPolicy(
                item["plan_version"],
                tuple(_decimal(p) for p in item["target_prices"]),
                max_quote_age_ms=3_000,
                max_spread_bps=_spread(item["max_spread_bps"]),
            )
            # Fail before any market connection if the actual stored position
            # is absent, not Bybit PAPER, has wrong plan or target direction.
            balance = inspect_paper_position(journal, item["position_id"]).balance
            if (balance.plan_version != targets.plan_version
                    or len(balance.tranches) != len(targets.prices)
                    or not _levels_valid(targets.prices, balance.side)):
                raise DataValidationError("D425 private PAPER position plan mismatch")
            runner_policy = None
            runner_path = None
            runner = item["runner"]
            if runner is not None:
                if (type(runner) is not dict or set(runner) != {
                        "file", "activation_bps", "trail_distance_bps",
                        "max_tick_gap_ms", "max_last_tick_age_ms",
                    } or type(runner["file"]) is not str
                        or not _RUNNER_NAME.fullmatch(runner["file"])
                        or runner["file"] in runner_names
                        or type(runner["max_tick_gap_ms"]) is not int
                        or not 1 <= runner["max_tick_gap_ms"] <= 30_000
                        or type(runner["max_last_tick_age_ms"]) is not int
                        or not 3_000 <= runner["max_last_tick_age_ms"] <= 30_000):
                    raise DataValidationError("D425 runner manifest invalid")
                runner_names.add(runner["file"])
                runner_path = home / runner["file"]
                if runner_path.is_symlink():
                    raise DataValidationError("D425 runner cannot be symlink")
                if runner_path.exists():
                    runner_fd = _owner_file(home, runner["file"])
                    os.close(runner_fd)
                runner_policy = PaperRunnerTrailPolicy(
                    _decimal(runner["activation_bps"]) if runner["activation_bps"] != "0" else Decimal(0),
                    _decimal(runner["trail_distance_bps"]),
                    runner["max_tick_gap_ms"],
                    runner["max_last_tick_age_ms"],
                )
            routes.append(PaperQuoteRoute(
                item["position_id"], stop, targets,
                runner_policy=runner_policy, runner_path=runner_path,
            ))
        return PaperIntrahourQuoteRouter(
            position_path=journal, routes=tuple(routes),
            enable_synthetic_ledger_fills=enable_hypothetical_exit_fills,
            fill_assumptions=(
                exit_fill_policy or PaperObservedFillAssumptions()
                if enable_hypothetical_exit_fills else None
            ),
        )
    except (OSError, ValueError, UnicodeError, TypeError,
            ArithmeticError, OverflowError) as exc:
        raise DataValidationError("D425 private PAPER route manifest invalid") from exc


def exclusive_paper_operator_lock(directory: Path) -> int:
    """Prevent competing D425 processes on the SAME private journal."""
    home = _private_directory(directory)
    dirfd = os.open(home, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fd = os.open(
            _LOCK, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600,
            dir_fd=dirfd,
        )
    finally:
        os.close(dirfd)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_nlink != 1):
            raise DataValidationError("D425 local PAPER lock unsafe")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fd
    except BaseException:
        os.close(fd)
        raise


def observe_existing_paper_positions_once(
    *, state_directory: Path,
    private_paper_directory: Path,
    allow_private_pointer_read: bool = False,
    allow_public_websocket: bool = False,
    confirm_personal_readonly_research: bool = False,
    confirm_region_eligible: bool = False,
    allow_synthetic_paper_reservations: bool = False,
    budget: TickerLeaseBudget = TickerLeaseBudget(
        max_sessions=1, max_frames=100_000, max_seconds=30,
    ),
    session_factory: Callable | None = None,
    clock: Callable | None = None,
    wall_ms: Callable | None = None,
    sleeper: Callable | None = None,
) -> dict:
    """One bounded real-public or injected WS session, never a daemon.

    No owner read, socket or PAPER mutation unless all five opt-ins are true.
    The per-directory flock covers building routes and the full D410 lease.
    """
    gates = (
        allow_private_pointer_read, allow_public_websocket,
        confirm_personal_readonly_research, confirm_region_eligible,
        allow_synthetic_paper_reservations,
    )
    if any(type(x) is not bool for x in gates):
        raise DataValidationError("D425 research gate types invalid")
    if not all(gates):
        return {
            "schema_version": "j4-current-paper-ws-observation-d425-v1",
            "status": "owner_market_and_paper_optin_required",
            "owner_scope_read": False,
            "network_attempted": False,
            "paper_journal_mutation_attempted": False,
            "orders_sent": False,
            "approved_for_live_use": False,
        }
    if (type(budget) is not TickerLeaseBudget
            or budget.max_sessions > 2 or budget.max_seconds > 60
            or budget.max_frames > 100_000
            or not isinstance(state_directory, Path)
            or not state_directory.is_absolute()
            or (session_factory is not None and not callable(session_factory))):
        raise DataValidationError("D425 finite bounds or owner state invalid")
    fd = exclusive_paper_operator_lock(private_paper_directory)
    try:
        router = load_private_paper_routes(private_paper_directory)
        kwargs = {}
        if clock is not None:
            kwargs["clock"] = clock
        if wall_ms is not None:
            kwargs["wall_ms"] = wall_ms
        if sleeper is not None:
            kwargs["sleeper"] = sleeper
        return run_current_n50_paper_lease_once(
            state_directory=state_directory,
            paper_router=router,
            allow_private_pointer_read=True,
            allow_public_websocket=True,
            confirm_personal_readonly_research=True,
            confirm_region_eligible=True,
            allow_synthetic_paper_reservations=True,
            budget=budget,
            session_factory=session_factory,
            **kwargs,
        )
    finally:
        os.close(fd)
