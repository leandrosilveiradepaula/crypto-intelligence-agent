"""D406 — read-only bridge from current J1 owner N50 epoch into J2 public WS.

This does not rank assets again, change the owner epoch, write any J1/PAPER
journal, send account orders, authenticate crypto identity, or install a service.

The owner alone may opt in to reading J1's protected pointer/manifest/cache.
Symbols never appear in sanitized reports, logger output or exception text.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import time
from typing import Callable

from .bybit_public_ticker_state_d385 import _symbols, MAX_MONITORED
from .bybit_public_ws_once import StreamSession
from .bybit_public_ws_operational_probe_d405 import (
    observe_finite_public_ws_once,
)
from .j1_auto_research_epoch import validate_ranked_research_scope
from .j1_n50_ws_epoch_rotation import load_active_n50_ws_epoch
from .j1_n50_ws_private_cache import load_n50_ws_dynamic_admission
from .market_data import DataGapError, DataValidationError

_SOURCE = "owner_j1_revalidated_provisional_n50_not_marketwide"
_EXPECTED = 50
_MAX_UTC_MS = 4_102_444_800_000


@dataclass(frozen=True)
class CurrentResearchN50:
    """An immutable research scope; identifiers are deliberately private."""

    symbols: tuple[str, ...] = field(repr=False)
    ranked_scope_sha256: str
    metadata_sha256: str
    activated_at_ms: int

    def sanitized_report(self) -> dict:
        return {
            "schema_version": "j2-current-owner-n50-scope-d406-v1",
            "status": "owner_revalidated_provisional_scope_loaded",
            "selected_contracts": len(self.symbols),
            "ranked_scope_sha256": self.ranked_scope_sha256,
            "metadata_sha256": self.metadata_sha256,
            "activated_at_ms": self.activated_at_ms,
            "j1_private_state_modified": False,
            "ranked_scope_source": _SOURCE,
            "crypto_identity_independently_verified": False,
            "marketwide_top50_verified": False,
            "approved_for_signals": False,
            "orders_sent": False,
            "approved_for_live_use": False,
        }


def read_current_j1_n50_scope(
    *, state_directory: Path, now_ms: int,
    allow_private_pointer_read: bool = False,
) -> CurrentResearchN50:
    """Resolve current owner epoch twice; refuse rotations during the read.

    Calls the existing J1 pointer/manifest/catalog revalidators, including
    ownership, mode, digest, time and membership gates. This layer NEVER
    opens the WS transport, fetches REST, ranks by ticker or writes a file.
    """
    if (allow_private_pointer_read is not True
            or not isinstance(state_directory, Path) or not state_directory.is_absolute()
            or type(now_ms) is not int
            or not 1_600_000_000_000 <= now_ms < _MAX_UTC_MS):
        raise DataValidationError("D406 owner scope read not authorized")
    try:
        first = load_active_n50_ws_epoch(
            state_directory=state_directory,
            current_at_ms=now_ms,
            allow_private_pointer_read=True,
        )
        if (first.status != "active_n50_ws_epoch_revalidated"
                or first.manifest_directory is None
                or first.ws_directory is None
                or first.ranked_scope_sha256 is None
                or first.ws_metadata_sha256 is None
                or type(first.activated_at_ms) is not int):
            raise DataGapError("D406 J1 owner epoch unavailable")
        cache = load_n50_ws_dynamic_admission(
            directory=first.ws_directory,
            current_at_ms=now_ms,
            expected_ranked_scope_sha256=first.ranked_scope_sha256,
            allow_private_scope_read=True,
        )
        if (cache.status != "private_n50_ws_admission_loaded_revalidated"
                or cache.ranked_scope is None or cache.admission is None
                or cache.admission.ranked_scope_sha256 != first.ranked_scope_sha256
                or cache.admission.metadata_sha256 != first.ws_metadata_sha256):
            raise DataGapError("D406 J1 cached scope mismatch")
        members, digest = validate_ranked_research_scope(
            cache.ranked_scope, now_ms=now_ms, max_assets=_EXPECTED,
        )
        contracts = cache.admission.ws_scope.contracts
        if (type(members) is not tuple or len(members) != _EXPECTED
                or len(set(members)) != _EXPECTED
                or digest != first.ranked_scope_sha256
                or type(contracts) is not tuple or len(contracts) != _EXPECTED
                or {m.symbol for m in contracts} != set(members)):
            raise DataGapError("D406 J1 current scope contracts mismatch")
        again = load_active_n50_ws_epoch(
            state_directory=state_directory,
            current_at_ms=now_ms,
            allow_private_pointer_read=True,
        )
        if (again.status != first.status
                or again.activated_at_ms != first.activated_at_ms
                or again.manifest_directory != first.manifest_directory
                or again.ws_directory != first.ws_directory
                or again.ranked_scope_sha256 != first.ranked_scope_sha256
                or again.ws_metadata_sha256 != first.ws_metadata_sha256):
            raise DataGapError("D406 active N50 epoch changed during read")
        return CurrentResearchN50(
            symbols=tuple(members),
            ranked_scope_sha256=digest,
            metadata_sha256=first.ws_metadata_sha256,
            activated_at_ms=first.activated_at_ms,
        )
    except (OSError, ValueError, TypeError, KeyError, AttributeError,
            OverflowError, UnicodeError, DataValidationError, DataGapError):
        # Do not expose potentially private paths or ranked symbol identifiers
        # from lower-level exceptions to logs or public panel.
        raise DataGapError("D406 current N50 scope unavailable") from None


def probe_current_j1_n50_ws_once(
    *, state_directory: Path,
    allow_private_pointer_read: bool = False,
    allow_public_websocket: bool = False,
    confirm_personal_readonly_research: bool = False,
    confirm_region_eligible: bool = False,
    position_symbols: tuple[str, ...] = (),
    seconds: int = 20,
    session_factory: Callable[[], StreamSession] | None = None,
    clock: Callable[[], float] = time.monotonic,
    wall_ms: Callable[[], int] = lambda: time.time_ns() // 1_000_000,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict:
    """Monitor existing *provisional* J1 N50 without a second ranker.

    All permissions must be true before reading protected files OR opening
    a socket. An arbitrary position supplied by the owner remains included
    in the monitored WebSocket scope even if absent from the current N50.
    """
    if (allow_private_pointer_read is not True
            or allow_public_websocket is not True
            or confirm_personal_readonly_research is not True
            or confirm_region_eligible is not True):
        return {
            "schema_version": "j2-current-owner-n50-ws-probe-d406-v1",
            "status": "owner_scope_and_public_ws_optin_required",
            "private_state_read": False,
            "network_attempted": False,
            "orders_sent": False,
            "approved_for_live_use": False,
        }
    # Bad runtime arguments must not cause an otherwise unnecessary private
    # J1 owner file read or any public WS attempt.
    if (type(position_symbols) is not tuple
            or type(seconds) is not int or not 5 <= seconds <= 60
            or (position_symbols and len(position_symbols) > MAX_MONITORED)
            or not callable(clock) or not callable(wall_ms)
            or not callable(sleeper)
            or (session_factory is not None and not callable(session_factory))):
        raise DataValidationError("D406 market observation budget invalid")
    if position_symbols:
        _symbols(position_symbols, maximum=MAX_MONITORED)
    at_ms = wall_ms()
    scope = read_current_j1_n50_scope(
        state_directory=state_directory, now_ms=at_ms,
        allow_private_pointer_read=True,
    )
    report = observe_finite_public_ws_once(
        symbols=scope.symbols, position_symbols=position_symbols,
        allow_public_websocket=True,
        confirm_personal_readonly_research=True,
        confirm_region_eligible=True,
        seconds=seconds, session_factory=session_factory,
        clock=clock, wall_ms=wall_ms, sleeper=sleeper,
    )
    return {
        **report,
        "schema_version": "j2-current-owner-n50-ws-probe-d406-v1",
        "scope_source": _SOURCE,
        "ranked_scope_sha256": scope.ranked_scope_sha256,
        "metadata_sha256": scope.metadata_sha256,
        "owner_scope_members": _EXPECTED,
        "private_state_read": True,
        "private_state_modified": False,
        "scope_independently_verified": False,
        "crypto_identity_independently_verified": False,
        "marketwide_top50_verified": False,
        "orders_sent": False,
        "approved_for_signals": False,
        "approved_for_live_use": False,
    }
