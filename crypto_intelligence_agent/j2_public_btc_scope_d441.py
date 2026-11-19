"""D441 one-symbol REST-to-WS research transport; no J1 or registry freshness gate.

One bounded public HTTPS instrument GET checks the BTCUSDT linear perpetual's
shape and clock. This is NOT the independent crypto identity review used for
N50 selection, not authenticated venue evidence, nor trading authorization.
"""
from __future__ import annotations

from hashlib import sha256
import json
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
    if (type(row) is not dict or row.get("symbol") != _SYMBOL
            or row.get("baseCoin") != _BASE
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
        raise DataValidationError("D441 public BTC instrument not eligible for pilot")
    launch = _epoch_millis(row.get("launchTime"), label="launchTime")
    leverage = row.get("leverageFilter")
    price = row.get("priceFilter")
    quantity = row.get("lotSizeFilter")
    if (launch > server or type(leverage) is not dict
            or type(price) is not dict or type(quantity) is not dict):
        raise DataValidationError("D441 public BTC filters invalid")
    minlev = _positive_decimal(leverage.get("minLeverage"), label="minLeverage")
    maxlev = _positive_decimal(leverage.get("maxLeverage"), label="maxLeverage")
    tick = _positive_decimal(price.get("tickSize"), label="tickSize")
    step = _positive_decimal(quantity.get("qtyStep"), label="qtyStep")
    if minlev > maxlev:
        raise DataValidationError("D441 public BTC leverage bounds inverted")
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
