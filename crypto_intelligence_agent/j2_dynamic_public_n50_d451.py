"""D451: dynamic, explicitly PROVISIONAL Bybit USDT perpetual volume cohort.

Fetches every paginated public linear instrument row and one ALL-linear ticker
snapshot using the existing bounded GET transport. Strictly excludes inactive,
futures, USDC, prelisting and TradFi-looking instruments. Ranked by documented
rolling turnover24h, NOT completed UTC-day candles or independent crypto ID.
No account endpoint, sender, J1 cache, order, trading approval or paid API.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from decimal import Decimal, ROUND_DOWN
from hashlib import sha256
import json
import os
import re
import time

from .bybit_closed_stream_cache import (
    MAX_UTC_MS, OfflineReviewedStreamScope, _scope_contract_fingerprint,
)
from .bybit_instrument_volume_contract import BybitLinearInstrumentResearch
from .bybit_paginated_universe_research import (
    MAX_PAGES, MAX_INSTRUMENT_ROWS, _cursor, _quantity, _response,
)
from .bybit_public_j1_transport import (
    BoundedBybitPublicClient, J1BybitCaptureError,
    instruments_url, tickers_url,
)
from .bybit_public_ticker_state_d385 import BybitTickerQuote
from .j2_public_btc_scope_d441 import validated_public_held_row
from .market_data import DataValidationError
from .paper_margin_preflight import PaperLinearContractFixture
from .synthetic_order_lifecycle import PaperVenue

_MAX_SCAN_MS = 180_000
_MAX_HTTP_AGE_MS = 30_000
_SYMBOL = re.compile(r"[A-Z0-9]{1,28}USDT\Z")
_LIMIT = 50


@dataclass(frozen=True)
class ProvisionalVolumeMember:
    symbol: str
    base: str
    rolling_turnover24h_usdt: Decimal
    launch_time_ms: int
    max_leverage_assumed: int
    tick_size: Decimal
    quantity_step: Decimal
    minimum_quantity: Decimal
    minimum_notional: Decimal
    maximum_quantity_base: Decimal


@dataclass(frozen=True)
class DynamicPublicN50:
    """Current research snapshot, NEVER a venue/identity trading certificate."""

    scope: OfflineReviewedStreamScope
    ranked: tuple[ProvisionalVolumeMember, ...]
    catalog_rows: int
    eligible_rows: int
    last_page_received_ms: int
    ticker_received_ms: int
    ticker_server_ms: int
    fingerprint_sha256: str
    btc_added_as_context: bool
    source_mode: str

    @property
    def symbols(self) -> tuple[str, ...]:
        return tuple(m.symbol for m in self.ranked)

    def contract_for_quote(self, quote: BybitTickerQuote) -> PaperLinearContractFixture:
        """Map captured public exchange SHAPE into an explicitly unverified PRE11 fixture."""
        if type(quote) is not BybitTickerQuote:
            raise DataValidationError("D451 PAPER contract requires typed public ticker")
        member = next((m for m in self.ranked if m.symbol == quote.symbol), None)
        if member is None:
            raise DataValidationError("D451 PAPER contract is outside current volume cohort")
        # Do not keep unrefreshed market metadata alive for new positions.
        if (quote.received_at_ms < self.ticker_received_ms
                or quote.received_at_ms - self.ticker_received_ms > 60_000):
            raise DataValidationError("D451 public instrument metadata expired for new PAPER open")
        # Bybit maxOrderQty is BASE units, not USDT notional.
        return PaperLinearContractFixture(
            venue=PaperVenue.BYBIT_V5, symbol=member.symbol, quote_currency="USDT",
            observed_at_ms=self.ticker_received_ms,
            fixture_version="fixture_d451_public_rest_" + self.fingerprint_sha256[:20],
            max_leverage_assumed=member.max_leverage_assumed,
            price_tick_quote=member.tick_size,
            quantity_step_base=member.quantity_step,
            min_quantity_base=member.minimum_quantity,
            min_notional_quote=member.minimum_notional,
            max_notional_quote=member.maximum_quantity_base * quote.mark_price,
        )

    def sanitized_report(self) -> dict[str, object]:
        return {
            "schema_version": "d451-dynamic-bybit-usdt-volume-cohort-v1",
            "status": "provisional_rolling_turnover_n50_selected",
            "ranked_assets": len(self.ranked),
            "catalog_rows": self.catalog_rows,
            "eligible_contract_rows": self.eligible_rows,
            "snapshot_observed_at_ms": self.ticker_received_ms,
            "scope_sha256": self.fingerprint_sha256,
            "volume_basis": "bybit_public_rolling_turnover24h_usdt_proxy",
            "btc_included_for_market_context": "BTCUSDT" in self.symbols,
            "btc_replaced_last_volume_rank": self.btc_added_as_context,
            "source_mode": self.source_mode,
            "marketwide_crypto_identity_verified": False,
            "full_24_closed_hour_rank_verified": False,
            "authenticated_bybit_market_data": False,
            "approved_for_live_trading": False,
            "orders_sent": False,
            "network_requests_by_ranker": 0,
        }


def _identity(row: object, symbol: object, server_at: int) -> tuple | None:
    if type(row) is not dict or type(symbol) is not str:
        raise DataValidationError("D451 unexpected instrument row")
    if len(symbol) > 80 or not symbol.isascii() or not symbol.isprintable() or any(c.isspace() for c in symbol):
        raise DataValidationError("D451 unsafe public instrument identity")
    if (_SYMBOL.fullmatch(symbol) is None
            or row.get("contractType") != "LinearPerpetual"
            or row.get("status") != "Trading"
            or row.get("quoteCoin") != "USDT"
            or row.get("settleCoin") != "USDT"
            or row.get("baseCoin") != symbol[:-4]):
        return None
    # Strict D441 validator prevents a syntactically USDT TradFi/futures/
    # prelisting instrument from being silently re-labelled "cryptocurrency".
    try:
        base, launch, _minimum_leverage, maxlev, tick, step = validated_public_held_row(
            row, symbol=symbol, server_ms=server_at,
        )
        if (launch > server_at - 24 * 3_600_000
                or maxlev < 1 or maxlev > 200):
            return None
        lot = row.get("lotSizeFilter")
        if type(lot) is not dict:
            return None
        minqty = _quantity(lot.get("minOrderQty"), "D451 minimum quantity")
        minnotional = _quantity(lot.get("minNotionalValue"), "D451 minimum notional")
        maxqty = _quantity(lot.get("maxOrderQty"), "D451 maximum quantity")
        if (minqty <= 0 or minnotional <= 0 or maxqty < minqty
                or minqty % step != 0):
            return None
        # Tiers are not verified; bounds are explicit assumptions for PAPER only.
        cap = int(maxlev.to_integral_value(rounding=ROUND_DOWN))
        if not 1 <= cap <= 200:
            return None
        return (base, launch, cap, tick, step, minqty, minnotional, maxqty)
    except (DataValidationError, ValueError, ArithmeticError, TypeError):
        # A malformed plausible contract may not be ranked as if valid.
        return None


def select_dynamic_public_n50(
    *, instrument_pages: tuple[dict, ...],
    page_received_at_ms: tuple[int, ...],
    requested_cursors: tuple[str | None, ...],
    ticker_payload: dict,
    ticker_received_at_ms: int,
    source_mode: str = "injected_offline_protocol_replay",
) -> DynamicPublicN50:
    """Deterministic causal selection, no HTTP. The WHOLE page chain is required."""
    if (type(instrument_pages) is not tuple or not 1 <= len(instrument_pages) <= MAX_PAGES
            or type(page_received_at_ms) is not tuple
            or type(requested_cursors) is not tuple
            or len(page_received_at_ms) != len(instrument_pages)
            or len(requested_cursors) != len(instrument_pages)
            or requested_cursors[0] is not None
            or type(ticker_received_at_ms) is not int
            or not 0 < ticker_received_at_ms < MAX_UTC_MS
            or source_mode not in ("injected_offline_protocol_replay", "public_rest_observed_unverified")):
        raise DataValidationError("D451 bounded complete public REST snapshot required")
    expected: str | None = None
    seen_cursors: set[str] = set()
    seen_symbols: set[str] = set()
    admitted: dict[str, tuple] = {}
    counted = 0
    prior_received = 0
    prior_server = 0
    for payload, at, cursor in zip(instrument_pages, page_received_at_ms, requested_cursors):
        if (type(at) is not int or not 0 < at <= ticker_received_at_ms
                or at < prior_received or at - page_received_at_ms[0] > _MAX_SCAN_MS
                or cursor != expected):
            raise DataValidationError("D451 paginated REST receive order invalid")
        _, result, server = _response(
            payload, label="D451 public instruments", at_ms=at, age_ms=_MAX_HTTP_AGE_MS,
        )
        if server + 2000 < prior_server:
            raise DataValidationError("D451 paginated provider clock regressed")
        if cursor is not None:
            _cursor(cursor, terminal_ok=False)
            if cursor in seen_cursors:
                raise DataValidationError("D451 repeated pagination cursor")
            seen_cursors.add(cursor)
        following = _cursor(result.get("nextPageCursor"), terminal_ok=True)
        if following and (following in seen_cursors or following == cursor):
            raise DataValidationError("D451 circular pagination cursor")
        rows = result.get("list")
        if type(rows) is not list or not 1 <= len(rows) <= 1000 or counted + len(rows) > MAX_INSTRUMENT_ROWS:
            raise DataValidationError("D451 public catalog page or total exceeds bounds")
        counted += len(rows)
        for row in rows:
            if type(row) is not dict:
                raise DataValidationError("D451 public instrument row not an object")
            symbol = row.get("symbol")
            if type(symbol) is not str or symbol in seen_symbols:
                raise DataValidationError("D451 missing or duplicate instrument in catalog")
            seen_symbols.add(symbol)
            identity = _identity(row, symbol, server)
            if identity is not None:
                admitted[symbol] = identity
        expected = following or None
        prior_received = at
        prior_server = max(prior_server, server)
    if expected is not None or ticker_received_at_ms < prior_received or ticker_received_at_ms - prior_received > 30_000:
        raise DataValidationError("D451 missing terminal catalog page or stale ticker correlation")
    _, ticker, ticker_server = _response(
        ticker_payload, label="D451 public tickers", at_ms=ticker_received_at_ms,
        age_ms=_MAX_HTTP_AGE_MS,
    )
    rows = ticker.get("list")
    if type(rows) is not list or not 1 <= len(rows) <= 10_000:
        raise DataValidationError("D451 aggregate ticker response incomplete")
    turnover: dict[str, Decimal] = {}
    for item in rows:
        if type(item) is not dict or type(item.get("symbol")) is not str:
            raise DataValidationError("D451 ticker row invalid")
        symbol = item["symbol"]
        if symbol not in admitted:
            continue
        if symbol in turnover:
            raise DataValidationError("D451 duplicate ticker for eligible perp")
        turnover[symbol] = _quantity(item.get("turnover24h"), "D451 rolling turnover24h")
    if set(turnover) != set(admitted):
        raise DataValidationError("D451 missing currently eligible USDT perpetual tickers")
    ranked_symbols = tuple(sorted(
        (symbol for symbol, value in turnover.items() if value > 0),
        key=lambda symbol: (-turnover[symbol], symbol),
    ))
    if len(ranked_symbols) < _LIMIT or "BTCUSDT" not in admitted or turnover["BTCUSDT"] == 0:
        raise DataValidationError("D451 insufficient liquid eligible market scope")
    selected = list(ranked_symbols[:_LIMIT])
    added_btc = "BTCUSDT" not in selected
    if added_btc:
        selected[-1] = "BTCUSDT"
    # The currently selected set never hides BTC context even if the BTC
    # rolling ticker temporarily falls below top50 (49+BTC context).
    # EPOCH identity must not change on every ticker refresh or change in
    # rank order: D434 requires an unchanged cohort/specification during
    # its 24h confirmed-candle history window. A membership/spec change
    # starts a new journal epoch instead of relabelling old candles.
    snapshot = sha256(json.dumps([
        "d451-public-provisional-epoch-membership-v1",
        tuple((s, list(map(str, admitted[s]))) for s in sorted(selected)),
    ], separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()
    members = tuple(ProvisionalVolumeMember(
        symbol, admitted[symbol][0], turnover[symbol],
        admitted[symbol][1], admitted[symbol][2],
        admitted[symbol][3], admitted[symbol][4], admitted[symbol][5],
        admitted[symbol][6], admitted[symbol][7],
    ) for symbol in selected)
    # The existing J2 WS journal needs a typed cohort fingerprint. This is
    # NOT a refreshed independent crypto-registry certification.
    scope_members = tuple(BybitLinearInstrumentResearch(
        m.symbol, m.base, "USDT", "USDT", ticker_received_at_ms,
        m.launch_time_ms, Decimal(m.max_leverage_assumed), m.tick_size,
        m.quantity_step, snapshot,
        source="public_rest_provisional_crypto_shape_unverified",
    ) for m in members)
    scope = OfflineReviewedStreamScope(
        observed_at_ms=ticker_received_at_ms, registry_sha256=snapshot,
        contracts=scope_members, asserted_full_catalog_rows=counted,
    )
    _scope_contract_fingerprint(scope)
    return DynamicPublicN50(
        scope, members, counted, len(admitted), prior_received,
        ticker_received_at_ms, ticker_server, snapshot, added_btc, source_mode,
    )


def capture_dynamic_public_n50(
    *, allow_public_network: bool = False,
    confirm_personal_readonly_research: bool = False,
    confirm_region_eligible: bool = False,
    confirm_public_data_rights: bool = False,
    client: BoundedBybitPublicClient | None = None,
    wall_ms=None,
) -> DynamicPublicN50:
    """A single bounded live-or-injected REST capture; no ambient network."""
    flags = (allow_public_network, confirm_personal_readonly_research,
             confirm_region_eligible, confirm_public_data_rights)
    if any(type(x) is not bool for x in flags) or not all(flags):
        raise DataValidationError("D451 four explicit public research authorizations required")
    injected = client is not None
    if injected and (type(client) is not BoundedBybitPublicClient
                     or client.transport is None or not callable(wall_ms)):
        raise DataValidationError("D451 injected capture needs explicit bounded transport/clock")
    if not injected:
        if (wall_ms is not None or os.name != "posix" or not hasattr(os, "geteuid")
                or os.geteuid() == 0):
            raise DataValidationError("D451 real public capture requires nonroot owner with real clock")
        client = BoundedBybitPublicClient()
        wall_ms = lambda: time.time_ns() // 1_000_000
    pages = []
    timestamps = []
    cursors = []
    requested = None
    for _ in range(MAX_PAGES):
        _, payload = client.get(instruments_url(cursor=requested))
        when = wall_ms()
        pages.append(payload)
        timestamps.append(when)
        cursors.append(requested)
        response = payload.get("result")
        if type(response) is not dict:
            raise DataValidationError("D451 public page missing response")
        following = _cursor(response.get("nextPageCursor"), terminal_ok=True)
        if not following:
            break
        if following == requested or following in cursors:
            raise DataValidationError("D451 pagination repeated cursor")
        requested = following
    else:
        raise DataValidationError("D451 public catalog exceeded page cap")
    _, ticker = client.get(tickers_url())
    when = wall_ms()
    return select_dynamic_public_n50(
        instrument_pages=tuple(pages), page_received_at_ms=tuple(timestamps),
        requested_cursors=tuple(cursors), ticker_payload=ticker,
        ticker_received_at_ms=when,
        source_mode=("injected_offline_protocol_replay" if injected
                     else "public_rest_observed_unverified"),
    )



@dataclass(frozen=True)
class PinnedDynamicN50Epoch:
    """Durable live-shape scope and journal for ONE stable membership epoch."""

    selected: DynamicPublicN50
    closed_journal_path: Path
    epoch_observed_at_ms: int
    newly_rotated: bool

    def sanitized_report(self) -> dict[str, object]:
        return {
            **self.selected.sanitized_report(),
            "schema_version": "d451-dynamic-public-n50-pinned-epoch-v1",
            "epoch_observed_at_ms": self.epoch_observed_at_ms,
            "new_isolated_closed_journal": self.newly_rotated,
            "old_confirmed_history_relabelled": False,
            "j1_accessed": False,
        }


def pin_dynamic_public_n50_epoch(
    *, snapshot: DynamicPublicN50, private_j2_directory: Path,
) -> PinnedDynamicN50Epoch:
    """Keep the 24h J2 series across refreshes while members/spec are unchanged.

    Acquires ONE non-blocking owner-only flock. On a membership change or
    six-day age limit, creates an entirely new isolated closed journal,
    preserving the old file for evidence. NEVER merges historical candles
    from a different scope, no implicit backfill or J1 activity.
    """
    from .j4_private_paper_ws_operator_d425 import (
        _private_directory, _owner_file,
    )
    from .j4_automatic_entry_materializer_d448 import (
        _atomic_private_write, _read_owner_bytes, _parse_json, _json,
    )
    from .bybit_closed_stream_cache import SQLiteOfflineClosedStreamJournal
    import fcntl  # POSIX-only: imported lazily after owner admission
    if (type(snapshot) is not DynamicPublicN50
            or not isinstance(private_j2_directory, Path)
            or any(part.startswith("j1-") for part in private_j2_directory.parts)):
        raise DataValidationError("D451 isolated owner J2 epoch and typed selection required")
    home = _private_directory(private_j2_directory)
    lockname = ".d451-epoch-owner.lock"
    flags = os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC
    fd = os.open(home / lockname, flags, 0o600)
    try:
        import stat
        info = os.fstat(fd)
        if (info.st_uid != os.geteuid() or not stat.S_ISREG(info.st_mode)
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
            raise DataValidationError("D451 private scope lock unsafe")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise DataGapError("D451 another scope rotation is in progress") from exc
        pointer_name = "current-d451-provisional-cohort.json"
        pointer = home / pointer_name
        observed = snapshot.ticker_received_ms
        current_epoch = None
        journal_name = None
        if pointer.exists() or pointer.is_symlink():
            envelope = _parse_json(_read_owner_bytes(home, pointer_name, 4096))
            if (type(envelope) is not dict or set(envelope) != {
                "schema", "payload", "sha256",
            } or envelope["schema"] != "d451-provisional-n50-epoch-pointer-v1"
                    or type(envelope["payload"]) is not dict
                    or type(envelope["sha256"]) is not str
                    or sha256(_json(envelope["payload"]).encode("ascii")).hexdigest()
                       != envelope["sha256"]):
                raise DataValidationError("D451 N50 epoch pointer integrity invalid")
            payload = envelope["payload"]
            if (set(payload) != {"epoch_ms", "cohort_sha256", "journal", "source_mode"}
                    or payload["source_mode"] not in (
                        "injected_offline_protocol_replay",
                        "public_rest_observed_unverified",
                    )
                    or type(payload["epoch_ms"]) is not int
                    or type(payload["cohort_sha256"]) is not str
                    or not re.fullmatch("[0-9a-f]{64}", payload["cohort_sha256"])
                    or type(payload["journal"]) is not str
                    or re.fullmatch(r"n50-d451-[0-9a-f]{18}-[0-9]{13}[.]sqlite",
                                    payload["journal"]) is None):
                raise DataValidationError("D451 N50 epoch pointer shape invalid")
            if (not 0 < payload["epoch_ms"] <= observed
                    or payload["journal"] != (
                        "n50-d451-" + payload["cohort_sha256"][:18]
                        + "-" + str(payload["epoch_ms"]) + ".sqlite"
                    )):
                raise DataValidationError("D451 N50 epoch pointer causality invalid")
            existing = home / payload["journal"]
            owner_fd = _owner_file(home, payload["journal"])
            os.close(owner_fd)
            if (payload["cohort_sha256"] == snapshot.fingerprint_sha256
                    and payload["source_mode"] == snapshot.source_mode
                    and observed - payload["epoch_ms"] < 6 * 86_400_000):
                current_epoch = payload["epoch_ms"]
                journal_name = payload["journal"]

        newly_rotated = current_epoch is None
        if newly_rotated:
            current_epoch = observed
            journal_name = (
                "n50-d451-" + snapshot.fingerprint_sha256[:18]
                + "-" + str(current_epoch) + ".sqlite"
            )
            journal_path = home / journal_name
            if journal_path.exists() or journal_path.is_symlink():
                raise DataGapError("D451 orphaned rotated J2 journal requires reconciliation")
            SQLiteOfflineClosedStreamJournal.create(journal_path)
            owner_fd = _owner_file(home, journal_name)
            os.close(owner_fd)
            payload = {
                "epoch_ms": current_epoch,
                "cohort_sha256": snapshot.fingerprint_sha256,
                "journal": journal_name,
                "source_mode": snapshot.source_mode,
            }
            raw = _json({
                "schema": "d451-provisional-n50-epoch-pointer-v1",
                "payload": payload,
                "sha256": sha256(_json(payload).encode("ascii")).hexdigest(),
            }).encode("ascii")
            _atomic_private_write(home, pointer_name, raw)

        scope = snapshot.scope
        pinned_scope = replace(
            scope, observed_at_ms=current_epoch,
            contracts=tuple(replace(member, observed_at_ms=current_epoch)
                            for member in scope.contracts),
        )
        _scope_contract_fingerprint(pinned_scope)
        return PinnedDynamicN50Epoch(
            selected=replace(snapshot, scope=pinned_scope),
            closed_journal_path=home / journal_name,
            epoch_observed_at_ms=current_epoch,
            newly_rotated=newly_rotated,
        )
    finally:
        os.close(fd)
