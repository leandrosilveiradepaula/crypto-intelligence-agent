"""D441: a single, current Bybit REST BTCUSDT contract for an isolated J2 pilot.

No J1 checkout, N50 pointer/cache, turnover ranking, trade API or credentials.
One bounded official public HTTPS GET; a distinct WSS subscriber owns its
isolated SQLite journal. This does NOT prove venue authenticity or data rights.
"""
from __future__ import annotations

import time

from .bybit_closed_stream_cache import OfflineReviewedStreamScope
from .bybit_instrument_volume_contract import validate_bybit_linear_instrument
from .bybit_paginated_universe_research import BybitInstrumentScanResearch
from .bybit_public_j1_transport import BoundedBybitPublicClient, instruments_url
from .market_data import DataValidationError

_SYMBOL = "BTCUSDT"
_REGISTRY = "expanded-13"


def reviewed_single_btc_scope(payload: dict, *, observed_at_ms: int) -> OfflineReviewedStreamScope:
    """Offline pure validation of REST instrument metadata, never a live claim."""
    instrument = validate_bybit_linear_instrument(
        payload, symbol=_SYMBOL, observed_at_ms=observed_at_ms,
        registry_variant=_REGISTRY,
    )
    if instrument.symbol != _SYMBOL or instrument.base_coin != "BTC":
        raise DataValidationError("D441 unexpected public pilot contract")
    result = payload["result"]
    scope = OfflineReviewedStreamScope.from_scan(
        BybitInstrumentScanResearch(
            observed_at_ms=observed_at_ms,
            registry_sha256=instrument.registry_sha256,
            page_count=1,
            instrument_row_count=1,
            last_server_time_ms=payload["time"],
            instruments=(instrument,),
        ), registry_variant=_REGISTRY,
    )
    if len(scope.contracts) != 1 or scope.member(_SYMBOL) != instrument:
        raise DataValidationError("D441 single reviewed scope required")
    return scope


def fetch_single_btc_scope_from_public_rest() -> OfflineReviewedStreamScope:
    """Actual no-key REST transport, bounded to exactly one metadata request.

    Call only after all public-network/region/owner gates in the operator.
    Never run this function as a CI fixture or from a module import.
    """
    client = BoundedBybitPublicClient()
    _, payload = client.get(instruments_url(symbol=_SYMBOL))
    observed_at_ms = time.time_ns() // 1_000_000
    return reviewed_single_btc_scope(payload, observed_at_ms=observed_at_ms)
