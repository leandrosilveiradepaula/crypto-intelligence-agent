"""D463: strict recent public single-instrument contract-shape recheck.

Never a tier certification, a private endpoint or a venue trading approval.
"""
from __future__ import annotations

from .bybit_paginated_universe_research import _response
from .j2_dynamic_public_n50_d451 import (
    ProvisionalVolumeMember, _identity,
)
from .market_data import DataGapError, DataValidationError


def _check_contract_identity(
    payload: dict, *, symbol: str, received_at_ms: int,
    expected: ProvisionalVolumeMember,
) -> None:
    if (type(expected) is not ProvisionalVolumeMember
            or type(symbol) is not str or symbol != expected.symbol
            or type(received_at_ms) is not int):
        raise DataValidationError("D463 exact previously admitted N50 member required")
    _, result, server = _response(
        payload, label="D463 public current contract",
        at_ms=received_at_ms, age_ms=30_000,
    )
    if (result.get("category") != "linear"
            or type(result.get("list")) is not list
            or len(result["list"]) != 1):
        raise DataGapError("D463 public single-contract response incomplete")
    row = result["list"][0]
    if type(row) is not dict or row.get("symbol") != symbol:
        raise DataGapError("D463 public instrument symbol changed")
    fresh = _identity(row, symbol, server)
    old = (
        expected.base,
        expected.launch_time_ms,
        expected.max_leverage_assumed,
        expected.tick_size,
        expected.quantity_step,
        expected.minimum_quantity,
        expected.minimum_notional,
        expected.maximum_quantity_base,
    )
    if fresh is None or fresh != old:
        raise DataGapError("D463 owner PAPER contract terms changed; no new open")
