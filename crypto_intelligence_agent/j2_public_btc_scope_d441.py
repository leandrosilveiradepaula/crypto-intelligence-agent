"""D441 one-symbol REST-to-WS research transport; no J1 or registry freshness gate.

One bounded public HTTPS instrument GET checks the BTCUSDT linear perpetual's
shape and clock. This is NOT the independent crypto identity review used for
N50 selection, not authenticated venue evidence, nor trading authorization.
"""
from __future__ import annotations

from hashlib import sha256
import json
import re
import time

from .bybit_closed_stream_cache import (
    MAX_UTC_MS, OfflineReviewedStreamScope, _scope_contract_fingerprint,
)
from .bybit_instrument_volume_contract import (
    BybitLinearInstrumentResearch, _epoch_millis, _positive_decimal,
)
from .bybit_public_j1_transport import BoundedBybitPublicClient, instruments_url
from .market_data import DataValidationError

_SYMBOL = "BTCUSDT"
_BASE = "BTC"
_LABEL = "d441-btcusdt-rest-ws-transport-only-not-crypto-identity"
_TRANSPORT_SYMBOL = re.compile(r"[A-Z0-9]{1,28}USDT\Z")



def validated_public_held_row(
    row: dict, *, symbol: str, server_ms: int,
) -> tuple:
    """Structural check for an EXISTING held PAPER symbol, not N50 admission."""
    if (type(symbol) is not str
            or _TRANSPORT_SYMBOL.fullmatch(symbol) is None
            or type(server_ms) is not int or server_ms <= 0
            or type(row) is not dict or row.get("symbol") != symbol
            or row.get("baseCoin") != symbol[:-4]
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
        raise DataValidationError("held PAPER instrument not supported public linear perp")
    launch = _epoch_millis(row.get("launchTime"), label="launchTime")
    leverage, price, qty = (row.get("leverageFilter"),
                            row.get("priceFilter"), row.get("lotSizeFilter"))
    if (launch > server_ms or type(leverage) is not dict
            or type(price) is not dict or type(qty) is not dict):
        raise DataValidationError("held PAPER instrument filters invalid")
    minlev = _positive_decimal(leverage.get("minLeverage"), label="minLeverage")
    maxlev = _positive_decimal(leverage.get("maxLeverage"), label="maxLeverage")
    tick = _positive_decimal(price.get("tickSize"), label="tickSize")
    step = _positive_decimal(qty.get("qtyStep"), label="qtyStep")
    if minlev > maxlev:
        raise DataValidationError("held PAPER instrument leverage bounds inverted")
    return symbol[:-4], launch, minlev, maxlev, tick, step


def reviewed_single_btc_scope(payload: dict, *, observed_at_ms: int) -> OfflineReviewedStreamScope:
    """Validate a *single named instrument*, not a current Top50 ranking.

    Do not invoke the seven-day crypto-registry PIT gate: the separate N50
    market-identity task needs it, but this bounded connectivity experiment
    never claims independent crypto verification or authorizes any signal.
    """
    if (type(payload) is not dict or payload.get("retCode") != 0
            or type(payload.get("retCode")) is not int
            or type(observed_at_ms) is not int
            or not 1_600_000_000_000 <= observed_at_ms < MAX_UTC_MS):
        raise DataValidationError("D441 public BTC REST envelope invalid")
    result = payload.get("result")
    server = payload.get("time")
    if (type(result) is not dict or result.get("category") != "linear"
            or result.get("nextPageCursor") != ""
            or type(result.get("list")) is not list
            or len(result["list"]) != 1
            or type(server) is not int or server <= 0
            or not 0 <= observed_at_ms - server <= 30_000):
        raise DataValidationError("D441 public BTC metadata missing, future or stale")
    row = result["list"][0]
    _base, launch, minlev, maxlev, tick, step = validated_public_held_row(
        row, symbol=_SYMBOL, server_ms=server,
    )
    # Binding is a one-run transport-scope fingerprint. It is NOT the
    # independently reviewed asset registry and must never be reused as one.
    fingerprint = sha256(json.dumps(
        [_LABEL, _SYMBOL, server, observed_at_ms,
         str(minlev), str(maxlev), str(tick), str(step)],
        separators=(",", ":"), ensure_ascii=True,
    ).encode("ascii")).hexdigest()
    instrument = BybitLinearInstrumentResearch(
        _SYMBOL, _BASE, "USDT", "USDT", observed_at_ms, launch,
        maxlev, tick, step, fingerprint,
        source="public_btc_contract_shape_research_unverified",
    )
    scope = OfflineReviewedStreamScope(
        observed_at_ms=observed_at_ms, registry_sha256=fingerprint,
        contracts=(instrument,), asserted_full_catalog_rows=1,
    )
    _scope_contract_fingerprint(scope)
    return scope


def fetch_single_btc_scope_from_public_rest() -> OfflineReviewedStreamScope:
    """One actual public REST GET, only after owner/region/research opt-ins."""
    client = BoundedBybitPublicClient()
    _, payload = client.get(instruments_url(symbol=_SYMBOL))
    return reviewed_single_btc_scope(
        payload, observed_at_ms=time.time_ns() // 1_000_000,
    )
