"""J1/D314: admit exactly the D287 dynamic N50 into an *offline* WS scope.

This module accepts caller-supplied Bybit V5 instrument-page fixtures. It does
NOT fetch, authenticate, authorize crypto identity, or activate a live service.
No fixed list of 52 tokens: the immutable D287 cohort selects all 50 members.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
from typing import Any

from .bybit_closed_stream_cache import (
    OfflineReviewedStreamScope, _scope_contract_fingerprint,
)
from .bybit_instrument_volume_contract import (
    BybitLinearInstrumentResearch, _epoch_millis, _positive_decimal,
)
from .bybit_paginated_universe_research import _cursor, _response
from .j1_auto_research_epoch import (
    HOUR_MS, MAX_SCOPE_AGE_MS, validate_ranked_research_scope,
)
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
