"""D445: all existing PAPER held symbols, even after leaving the N50.

This is NOT a prospective entry-universe classifier. The public Bybit REST
instrument census is validated for the exact held PAPER membership, then
the existing D425/D390/D391/AUTO4 financial journal routes real PUBLIC
ticker observations to hypothetical reduce-only reservations. No J1 read,
private exchange endpoint, venue fill, native stop, or real order.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import time
from typing import Callable

from .bybit_closed_stream_cache import (
    MAX_UTC_MS, OfflineReviewedStreamScope, _scope_contract_fingerprint,
)
from .bybit_instrument_volume_contract import BybitLinearInstrumentResearch
from .bybit_paginated_universe_research import _response, _cursor
from .bybit_public_j1_transport import (
    BoundedBybitPublicClient, J1BybitCaptureError, instruments_url, _SYMBOL,
)
from .bybit_public_ticker_supervisor_d386 import TickerLeaseBudget
from .j2_public_btc_scope_d441 import validated_public_held_row
from .j4_held_btc_public_d443 import run_held_paper_lease, _public_session_only
from .j4_private_paper_ws_operator_d425 import (
    exclusive_paper_operator_lock, load_private_paper_routes,
)
from .market_data import DataGapError, DataValidationError
from .paper_intrahour_quote_router_d391 import PaperIntrahourQuoteRouter

_MAX_PAGES = 20
_MAX_ROWS = 10_000
_MAX_HELD = 50
_MAX_SCAN_DURATION_MS = 30_000
_LABEL = "d445-held-positions-transport-only-not-n50-ranking"


def _held_symbols(values: object) -> tuple[str, ...]:
    if (type(values) is not tuple or not 1 <= len(values) <= _MAX_HELD
            or len(set(values)) != len(values)
            or any(type(s) is not str or _SYMBOL.fullmatch(s) is None
                   for s in values)):
        raise DataValidationError("D445 exact current held USDT membership required")
    return tuple(sorted(values))


def reviewed_held_instrument_pages(
    *, held_symbols: tuple[str, ...], pages: tuple[dict, ...],
    requested_cursors: tuple[str | None, ...],
    page_received_at_ms: tuple[int, ...], observed_at_ms: int,
) -> OfflineReviewedStreamScope:
    """Pure, fully paginated research only: refuses missing held contracts."""
    wanted = frozenset(_held_symbols(held_symbols))
    if (type(pages) is not tuple or not 1 <= len(pages) <= _MAX_PAGES
            or type(requested_cursors) is not tuple
            or type(page_received_at_ms) is not tuple
            or len(requested_cursors) != len(pages)
            or len(page_received_at_ms) != len(pages)
            or requested_cursors[0] is not None
            or type(observed_at_ms) is not int
            or not 1_600_000_000_000 <= observed_at_ms < MAX_UTC_MS
            or any(type(t) is not int
                   or not 1_600_000_000_000 <= t <= observed_at_ms
                   for t in page_received_at_ms)
            or any(a > b for a, b in zip(
                page_received_at_ms, page_received_at_ms[1:]))
            or observed_at_ms - page_received_at_ms[0] > _MAX_SCAN_DURATION_MS):
        raise DataValidationError("D445 complete recent public instrument census required")

    found: dict[str, tuple] = {}
    expected_cursor = None
    seen_cursors: set[str] = set()
    last_server_at = 0
    total_rows = 0
    for index, (page, requested, received) in enumerate(zip(
        pages, requested_cursors, page_received_at_ms,
    )):
        _, result, server_ms = _response(
            page, label="D445 public held instruments", at_ms=received,
            age_ms=30_000,
        )
        if server_ms + 2_000 < last_server_at:
            raise DataValidationError("D445 noncausal REST server times")
        last_server_at = max(last_server_at, server_ms)
        if requested != expected_cursor:
            raise DataValidationError("D445 incomplete instrument cursor chain")
        if requested is not None:
            _cursor(requested, terminal_ok=False)
            if requested in seen_cursors:
                raise DataValidationError("D445 repeated requested cursor")
            seen_cursors.add(requested)
        nxt = _cursor(result.get("nextPageCursor"), terminal_ok=True)
        if (nxt and (nxt == requested or nxt in seen_cursors)
                or (index == len(pages) - 1 and nxt != "")
                or (index < len(pages) - 1 and nxt == "")):
            raise DataValidationError("D445 instrument cursor unfinished or repeated")
        expected_cursor = nxt or None
        rows = result.get("list")
        if (type(rows) is not list or not 1 <= len(rows) <= 1_000
                or total_rows + len(rows) > _MAX_ROWS):
            raise DataValidationError("D445 instrument page budget invalid")
        total_rows += len(rows)
        for row in rows:
            if type(row) is not dict:
                raise DataValidationError("D445 invalid instrument row")
            symbol = row.get("symbol")
            if (type(symbol) is not str or not 1 <= len(symbol) <= 80
                    or not symbol.isascii() or not symbol.isprintable()
                    or any(ch.isspace() for ch in symbol)):
                raise DataValidationError("D445 unsafe public contract identity")
            if symbol not in wanted:
                continue
            if symbol in found:
                raise DataValidationError("D445 duplicated held contract")
            base, launch, minlev, maxlev, tick, qty = validated_public_held_row(
                row, symbol=symbol, server_ms=server_ms,
            )
            found[symbol] = (base, launch, minlev, maxlev, tick, qty, received)
    if set(found) != wanted:
        raise DataValidationError("D445 held contract missing from complete scan")

    canonical = [
        [s, str(found[s][1]), str(found[s][2]), str(found[s][3]),
         str(found[s][4]), str(found[s][5])]
        for s in sorted(found)
    ]
    digest = sha256(json.dumps(
        [_LABEL, observed_at_ms, canonical], ensure_ascii=True,
        separators=(",", ":"),
    ).encode("ascii")).hexdigest()
    contracts = tuple(
        BybitLinearInstrumentResearch(
            symbol=s, base_coin=found[s][0],
            quote_coin="USDT", settle_coin="USDT",
            observed_at_ms=found[s][6], launch_time_ms=found[s][1],
            max_leverage=found[s][3], tick_size=found[s][4],
            quantity_step=found[s][5], registry_sha256=digest,
            source="public_held_perp_contract_shape_unverified",
        ) for s in sorted(found)
    )
    result = OfflineReviewedStreamScope(
        observed_at_ms=observed_at_ms, registry_sha256=digest,
        contracts=contracts, asserted_full_catalog_rows=total_rows,
    )
    _scope_contract_fingerprint(result)
    return result


def fetch_held_scope_from_public_rest(
    held_symbols: tuple[str, ...],
) -> OfflineReviewedStreamScope:
    """Bounded public GET page walk. No per-position request storm."""
    wanted = _held_symbols(held_symbols)  # validate BEFORE network
    client = BoundedBybitPublicClient()
    pages = []
    received = []
    cursors = []
    seen: set[str] = set()
    cursor: str | None = None
    for _ in range(_MAX_PAGES):
        _, payload = client.get(instruments_url(cursor=cursor))
        at_ms = time.time_ns() // 1_000_000
        pages.append(payload)
        received.append(at_ms)
        cursors.append(cursor)
        result = payload.get("result") if type(payload) is dict else None
        if type(result) is not dict:
            raise DataValidationError("D445 public REST result invalid")
        next_cursor = _cursor(result.get("nextPageCursor"), terminal_ok=True)
        if not next_cursor:
            break
        if next_cursor == cursor or next_cursor in seen:
            raise DataValidationError("D445 public instrument pagination cycle")
        seen.add(next_cursor)
        cursor = next_cursor
    else:
        raise DataValidationError("D445 instrument public scan page budget exhausted")
    return reviewed_held_instrument_pages(
        held_symbols=wanted, pages=tuple(pages),
        requested_cursors=tuple(cursors),
        page_received_at_ms=tuple(received),
        observed_at_ms=time.time_ns() // 1_000_000,
    )


def observe_existing_held_paper_once(
    *, private_paper_directory: Path | None = None,
    allow_public_network: bool = False,
    allow_public_websocket: bool = False,
    confirm_personal_readonly_research: bool = False,
    confirm_region_eligible: bool = False,
    allow_private_paper_reservations: bool = False,
    simulate_explicit_demo_exit_fills: bool = False,
    budget: TickerLeaseBudget = TickerLeaseBudget(1, 20_000, 30),
    session_factory: Callable | None = None,
    offline_scope: OfflineReviewedStreamScope | None = None,
    offline_router: PaperIntrahourQuoteRouter | None = None,
    clock: Callable | None = None,
    wall_ms: Callable | None = None,
    sleeper: Callable | None = None,
) -> dict:
    """D425 owner lock + live REST/WS or hermetically injected offline replay."""
    gates = (allow_public_network, allow_public_websocket,
             confirm_personal_readonly_research, confirm_region_eligible,
             allow_private_paper_reservations)
    denied = {
        "status": "explicit_held_paper_and_public_market_optins_required",
        "network_attempted": False, "private_paper_journal_accessed": False,
        "j1_state_accessed": False, "orders_sent": False,
        "approved_for_live_use": False,
    }
    if (any(type(x) is not bool for x in gates)
            or type(simulate_explicit_demo_exit_fills) is not bool):
        raise DataValidationError("D445 gate types invalid")
    if not all(gates):
        return denied
    if (type(budget) is not TickerLeaseBudget
            or budget.max_sessions != 1 or budget.max_seconds > 60
            or budget.max_frames > 100_000):
        raise DataValidationError("D445 finite multi-PAPER budget required")
    real = session_factory is None
    if not real:
        if simulate_explicit_demo_exit_fills:
            # Tests inject an already-configured router. Never alter it
            # implicitly by supplying a side-channel runtime option.
            raise DataValidationError("D483 demo fill mode requires real owner routes")
        if (not callable(session_factory)
                or type(offline_router) is not PaperIntrahourQuoteRouter
                or type(offline_scope) is not OfflineReviewedStreamScope
                or any(not callable(x) for x in (clock, wall_ms, sleeper))
                or private_paper_directory is not None):
            raise DataValidationError("D445 explicit offline test seam required")
        report = run_held_paper_lease(
            router=offline_router, scope=offline_scope, budget=budget,
            session_factory=session_factory, clock=clock,
            wall_ms=wall_ms, sleeper=sleeper,
        )
        report.update(data_mode="injected_offline_protocol_replay",
                      network_attempted=False, private_paper_journal_accessed=True)
        return report
    if (offline_scope is not None or offline_router is not None
            or any(x is not None for x in (clock, wall_ms, sleeper))):
        raise DataValidationError("D445 real public WS rejects injected test hooks")
    if (os.name != "posix" or not hasattr(os, "geteuid")
            or not hasattr(os, "getuid") or os.getuid() != os.geteuid()
            or os.geteuid() == 0):
        return {**denied, "status": "unprivileged_owner_required"}
    if (not isinstance(private_paper_directory, Path)
            or not private_paper_directory.is_absolute()
            or any(part.startswith("j1-")
                   for part in private_paper_directory.parts)):
        raise DataValidationError("D445 dedicated existing PAPER journal required")
    fd = exclusive_paper_operator_lock(private_paper_directory)
    try:
        if simulate_explicit_demo_exit_fills:
            preview = load_private_paper_routes(private_paper_directory)
            if preview.monitored_position_ids != (
                "fixture_d426_ephemeral_position",
            ):
                # Opt-in is ONLY for the explicit D482 isolated demo,
                # never for ordinary PAPER journals or account-like data.
                raise DataValidationError("D483 demo-only route identity required")
        router = load_private_paper_routes(
            private_paper_directory,
            enable_hypothetical_exit_fills=simulate_explicit_demo_exit_fills,
        )
        held = tuple(sorted(router.monitored_symbols))
        try:
            scope = fetch_held_scope_from_public_rest(held)
        except (J1BybitCaptureError, DataGapError, DataValidationError,
                OSError, ValueError, TypeError):
            return {
                **denied, "status": "held_contracts_public_rest_abstained",
                "network_attempted": True, "private_paper_journal_accessed": True,
            }
        try:
            report = run_held_paper_lease(
                router=router, scope=scope, budget=budget,
                session_factory=_public_session_only,
                clock=time.monotonic,
                wall_ms=lambda: time.time_ns() // 1_000_000,
                sleeper=time.sleep,
            )
        except (DataValidationError, DataGapError, OSError,
                RuntimeError, ValueError, TypeError):
            return {
                **denied, "status": "held_paper_public_lease_failed_closed",
                "network_attempted": True, "private_paper_journal_accessed": True,
            }
        report.update(
            data_mode="public_ws_observed_unverified",
            network_attempted=True, private_paper_journal_accessed=True,
            explicit_demo_exit_fill_assumptions_enabled=simulate_explicit_demo_exit_fills,
        )
        return report
    finally:
        os.close(fd)
