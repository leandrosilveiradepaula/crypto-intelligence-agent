"""J1/D314: admit exactly the D287 dynamic N50 into an *offline* WS scope.

This module accepts caller-supplied Bybit V5 instrument-page fixtures. It does
NOT fetch, authenticate, authorize crypto identity, or activate a live service.
No fixed list of 52 tokens: the immutable D287 cohort selects all 50 members.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
import os
import time
from typing import Any, Callable

from .bybit_closed_stream_cache import (
    OfflineReviewedStreamScope, _scope_contract_fingerprint,
)
from .bybit_instrument_volume_contract import (
    BybitLinearInstrumentResearch, _epoch_millis, _positive_decimal,
)
from .bybit_paginated_universe_research import _cursor, _response
from .bybit_public_j1_transport import (
    BoundedBybitPublicClient, J1BybitCaptureError, instruments_url,
)
from .j1_auto_research_epoch import validate_ranked_research_scope
from .market_data import DataValidationError

MAX_CATALOG_PAGES = 4
MAX_CATALOG_ROWS = 4000
MAX_PAGE_ROWS = 1000
MAX_SNAPSHOT_LAG_MS = 15 * 60_000
_SOURCE = "bybit_v5_dynamic_n50_provisional_metadata_unverified"
_SCHEMA = "j1-n50-ws-dynamic-provisional-scope-v1"


def _canonical(doc: Any) -> bytes:
    return json.dumps(
        doc, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("ascii")


@dataclass(frozen=True)
class DynamicN50WSAdmission:
    """Private typed scope for the existing WS supervisor/parser/journal.

    Do not expose __dict__ or repr publicly: the scope contains symbols.
    Public diagnostics only use sanitized_report().
    """
    ws_scope: OfflineReviewedStreamScope = field(repr=False)
    ranked_scope_sha256: str
    metadata_sha256: str
    observed_at_ms: int
    selected_contracts: int = 50

    def sanitized_report(self) -> dict[str, Any]:
        return {
            "schema_version": _SCHEMA,
            "status": "dynamic_n50_ws_scope_offline_research_only",
            "selected_contracts": self.selected_contracts,
            "ranked_scope_sha256": self.ranked_scope_sha256,
            "metadata_sha256": self.metadata_sha256,
            "scope_observed_at_ms": self.observed_at_ms,
            "network_requests": 0,
            "ws_connections_opened": 0,
            "database_mutation_statements": 0,
            "systemd_modified": False,
            "catalog_source_authenticated": False,
            "crypto_identity_independently_verified": False,
            "marketwide_top50_verified": False,
            "continuous_collector_verified": False,
            "approved_for_signals": False,
            "live_trading_authorized": False,
            "orders_sent": False,
        }


def admit_dynamic_n50_ws_scope(
    *, ranked_scope: dict,
    instrument_pages: tuple[dict, ...],
    requested_cursors: tuple[str | None, ...],
    page_received_at_ms: tuple[int, ...],
    now_ms: int,
) -> DynamicN50WSAdmission:
    """Bind D287 50 members to ALL matching, current, strict V5 catalog rows.

    A forged/partial pagination chain, missing/duplicated member, TradFi,
    delisted contract, invalid financial precision or lookahead fails closed.
    The source registry SHA is a *provisional binding digest*, never a reviewed
    crypto allowlist and never an assertion that the HTTP pages were fetched.
    """
    if (type(now_ms) is not int
            or type(instrument_pages) is not tuple
            or not 1 <= len(instrument_pages) <= MAX_CATALOG_PAGES
            or type(requested_cursors) is not tuple
            or type(page_received_at_ms) is not tuple
            or len(requested_cursors) != len(instrument_pages)
            or len(page_received_at_ms) != len(instrument_pages)
            or requested_cursors[0] is not None):
        raise DataValidationError("dynamic N50 WS catalog arguments invalid")
    try:
        members, ranked_digest = validate_ranked_research_scope(
            ranked_scope, now_ms=now_ms, max_assets=50,
        )
    except (ValueError, TypeError, KeyError):
        raise DataValidationError("untrusted D287 ranked N50 manifest") from None

    post = ranked_scope["catalog_post_observed_at_ms"]
    if (any(type(t) is not int
            or not post <= t <= now_ms
            or t > post + MAX_SNAPSHOT_LAG_MS
            for t in page_received_at_ms)
            or any(a > b for a, b in zip(
                page_received_at_ms, page_received_at_ms[1:],
            ))
            or page_received_at_ms[-1] - page_received_at_ms[0] > 120_000
            or now_ms - page_received_at_ms[-1] > 120_000):
        raise DataValidationError("WS metadata must follow same D287 UTC cohort")

    desired = frozenset(members)
    accepted: dict[str, dict[str, Any]] = {}
    expected_cursor: str | None = None
    seen_cursors: set[str] = set()
    rows_seen = 0
    prior_server = 0
    for i, page in enumerate(instrument_pages):
        received = page_received_at_ms[i]
        _, result, server = _response(
            page, label="N50 WS metadata", at_ms=received, age_ms=30_000,
        )
        if server < prior_server:
            raise DataValidationError("noncausal catalog metadata server timestamps")
        prior_server = server
        requested = requested_cursors[i]
        if requested != expected_cursor:
            raise DataValidationError("incomplete WS metadata pagination")
        if requested is not None:
            _cursor(requested, terminal_ok=False)
            if requested in seen_cursors:
                raise DataValidationError("repeated WS catalog cursor")
            seen_cursors.add(requested)
        next_cursor = _cursor(
            result.get("nextPageCursor"), terminal_ok=True,
        )
        if (next_cursor and (next_cursor == requested
                            or next_cursor in seen_cursors)
                or i < len(instrument_pages) - 1 and next_cursor == ""
                or i == len(instrument_pages) - 1 and next_cursor != ""):
            raise DataValidationError("WS catalog page sequence incomplete")
        expected_cursor = next_cursor or None
        rows = result.get("list")
        if (type(rows) is not list
                or not 1 <= len(rows) <= MAX_PAGE_ROWS
                or rows_seen + len(rows) > MAX_CATALOG_ROWS):
            raise DataValidationError("unbounded or empty WS catalog page")
        rows_seen += len(rows)
        for row in rows:
            if type(row) is not dict:
                raise DataValidationError("WS metadata row invalid")
            symbol = row.get("symbol")
            if (type(symbol) is not str or not 1 <= len(symbol) <= 80
                    or not symbol.isascii() or not symbol.isprintable()
                    or any(x.isspace() for x in symbol)):
                raise DataValidationError("WS catalog row symbol invalid")
            if symbol not in desired:
                continue
            if symbol in accepted:
                raise DataValidationError("duplicate dynamic ranked contract")
            base = symbol[:-4]
            if (row.get("baseCoin") != base
                    or row.get("quoteCoin") != "USDT"
                    or row.get("settleCoin") != "USDT"
                    or row.get("contractType") != "LinearPerpetual"
                    or row.get("status") != "Trading"
                    or row.get("symbolType") != ""
                    or row.get("marketRegion", "") != ""
                    or row.get("underlyingTicker", "") != ""
                    or row.get("tags") != []
                    or row.get("isPreListing") is not False
                    or row.get("preListingInfo") is not None
                    or row.get("deliveryTime") != "0"):
                raise DataValidationError("N50 member is not eligible V5 linear crypto-like perp")
            launch = _epoch_millis(row.get("launchTime"), label="launchTime")
            leverage = row.get("leverageFilter")
            price = row.get("priceFilter")
            lot = row.get("lotSizeFilter")
            if (launch > server
                    or type(leverage) is not dict
                    or type(price) is not dict
                    or type(lot) is not dict):
                raise DataValidationError("untrusted dynamic N50 contract metadata")
            minlev = _positive_decimal(leverage.get("minLeverage"), label="minLeverage")
            maxlev = _positive_decimal(leverage.get("maxLeverage"), label="maxLeverage")
            tick = _positive_decimal(price.get("tickSize"), label="tickSize")
            step = _positive_decimal(lot.get("qtyStep"), label="qtyStep")
            if minlev > maxlev:
                raise DataValidationError("inverted perpetual leverage bounds")
            accepted[symbol] = {
                "symbol": symbol, "base": base, "launch": launch,
                "observed": server, "maxlev": maxlev,
                "tick": tick, "step": step,
            }
    if set(accepted) != desired:
        raise DataValidationError("not all dynamic N50 perpetual metadata present")

    # Immutable metadata and D287 cohort digests: no implicit local registry.
    ordered = [accepted[name] for name in sorted(desired)]
    binding = {
        "schema": _SCHEMA,
        "ranked_scope_sha256": ranked_digest,
        "metadata_observed_ms": page_received_at_ms[-1],
        "page_count": len(instrument_pages),
        "catalog_rows": rows_seen,
        "members": [
            [r["symbol"], r["base"], r["launch"], r["observed"],
             format(r["maxlev"], "f"), format(r["tick"], "f"),
             format(r["step"], "f")]
            for r in ordered
        ],
    }
    metadata_sha = sha256(_canonical(binding)).hexdigest()
    ws_members = tuple(
        BybitLinearInstrumentResearch(
            symbol=r["symbol"], base_coin=r["base"],
            quote_coin="USDT", settle_coin="USDT",
            observed_at_ms=r["observed"], launch_time_ms=r["launch"],
            max_leverage=r["maxlev"], tick_size=r["tick"],
            quantity_step=r["step"], registry_sha256=metadata_sha,
            source=_SOURCE,
        )
        for r in ordered
    )
    ws_scope = OfflineReviewedStreamScope(
        page_received_at_ms[-1], metadata_sha,
        ws_members, rows_seen,
    )
    _scope_contract_fingerprint(ws_scope)
    return DynamicN50WSAdmission(
        ws_scope, ranked_digest, metadata_sha, page_received_at_ms[-1],
    )


@dataclass(frozen=True)
class DynamicN50WSMetadataCapture:
    """A bounded opt-in caller for the D314 pure admission function.

    No timers, no WS connection, no persistence, no source authentication.
    The typed, possibly private admission is never emitted by sanitized_report.
    """
    status: str
    requests_attempted: int
    failure_category: str | None = None
    admission: DynamicN50WSAdmission | None = field(default=None, repr=False)

    def sanitized_report(self) -> dict[str, Any]:
        return {
            "schema_version": "j1-n50-ws-metadata-capture-once-v1",
            "status": self.status,
            "failure_category": self.failure_category,
            "requests_attempted": self.requests_attempted,
            "selected_contracts": (
                self.admission.selected_contracts if self.admission else 0
            ),
            "metadata_sha256": (
                self.admission.metadata_sha256 if self.admission else None
            ),
            "network_accessed": self.requests_attempted > 0,
            "websocket_connections_opened": 0,
            "database_mutation_statements": 0,
            "systemd_modified": False,
            "source_authenticated": False,
            "crypto_identity_independently_verified": False,
            "marketwide_top50_verified": False,
            "live_trading_authorized": False,
            "orders_sent": False,
        }


def capture_n50_dynamic_ws_metadata_once(
    *, ranked_scope: dict,
    allow_public_network: bool = False,
    confirm_region_and_personal_research: bool = False,
    enable_n50_ws_metadata_capture: bool = False,
    owner_ok: bool | None = None,
    client: BoundedBybitPublicClient | None = None,
    clock_ms: Callable[[], int] | None = None,
) -> DynamicN50WSMetadataCapture:
    """Exactly one bounded paginated public metadata scan, no retry on 10006.

    The D286 original rank-capture remains unchanged. A separate owner caller
    may opt into reading <=4 current V5 pages. The 50 dynamic members MUST
    already be sealed in D287 before the first request. This function makes
    no journal edits and cannot activate the systemd or WS collector.
    """
    if (allow_public_network is not True
            or confirm_region_and_personal_research is not True
            or enable_n50_ws_metadata_capture is not True):
        return DynamicN50WSMetadataCapture("owner_optin_required", 0)
    permitted = ((os.name == "posix" and os.getuid() == os.geteuid()
                  and os.geteuid() != 0)
                 if owner_ok is None else owner_ok)
    if permitted is not True:
        return DynamicN50WSMetadataCapture("owner_permission_denied", 0)
    if (client is not None and type(client) is not BoundedBybitPublicClient
            or clock_ms is not None and not callable(clock_ms)):
        return DynamicN50WSMetadataCapture("invalid_metadata_capture_arguments", 0)
    clock = clock_ms or (lambda: time.time_ns() // 1_000_000)
    try:
        now = clock()
        validate_ranked_research_scope(
            ranked_scope, now_ms=now, max_assets=50,
        )
    except (ValueError, TypeError, KeyError):
        return DynamicN50WSMetadataCapture("untrusted_ranked_scope_no_get", 0)
    # Reject an injected client with a preconsumed budget. There is exactly
    # one logical catalog attempt per call, always a fresh HTTP client.
    fetch = client if client is not None else BoundedBybitPublicClient()
    if fetch.requests_attempted != 0:
        return DynamicN50WSMetadataCapture("client_budget_already_used", 0)
    pages: list[dict] = []
    cursors: list[str | None] = []
    receipts: list[int] = []
    expected: str | None = None
    try:
        for _ in range(MAX_CATALOG_PAGES):
            checked = clock()
            if (type(checked) is not int
                    or not ranked_scope["catalog_post_observed_at_ms"]
                          <= checked
                          <= ranked_scope["catalog_post_observed_at_ms"] + MAX_SNAPSHOT_LAG_MS):
                raise DataValidationError("catalog outside D287 metadata UTC window")
            _, payload = fetch.get(instruments_url(cursor=expected))
            stamp = clock()
            if type(stamp) is not int:
                raise DataValidationError("catalog receipt UTC invalid")
            _, data, _ = _response(
                payload, label="N50 WS metadata", at_ms=stamp, age_ms=30_000,
            )
            next_cursor = _cursor(data.get("nextPageCursor"), terminal_ok=True)
            if next_cursor and (next_cursor == expected or next_cursor in cursors):
                raise DataValidationError("WS catalog cursor loop")
            pages.append(payload)
            cursors.append(expected)
            receipts.append(stamp)
            if next_cursor == "":
                break
            expected = next_cursor
        else:
            raise DataValidationError("WS catalog exceeded four pages")
        admission = admit_dynamic_n50_ws_scope(
            ranked_scope=ranked_scope, instrument_pages=tuple(pages),
            requested_cursors=tuple(cursors),
            page_received_at_ms=tuple(receipts), now_ms=clock(),
        )
        return DynamicN50WSMetadataCapture(
            "dynamic_n50_ws_metadata_captured_research_only",
            fetch.requests_attempted, admission=admission,
        )
    except (J1BybitCaptureError, DataValidationError, ValueError, OSError,
            TypeError, OverflowError):
        # An error never triggers another request. Only a fixed enum is
        # echoed to logs, not a venue message, symbol, URL or access token.
        category = None
        if fetch.last_provider_retcode == 10006:
            category = "provider_rate_limit_no_retry"
        return DynamicN50WSMetadataCapture(
            "dynamic_n50_ws_metadata_abstained_no_retry",
            fetch.requests_attempted, failure_category=category,
        )
