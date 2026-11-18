"""J2 read-only boundary over the existing confirmed Bybit closed-kline journal.

It intentionally does not call the synthetic J2 signal engine or AUTO2: public
WS provenance remains unverified even when the local journal is consistent.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from .bybit_closed_stream_cache import (
    HOUR_MS, OfflineReviewedStreamScope, SQLiteOfflineClosedStreamJournal,
    _validated_payload,
)
from .market_data import ClosedCandle, DataGapError, DataValidationError


@dataclass(frozen=True)
class BybitClosedResearchSeries:
    candles: tuple[ClosedCandle, ...]
    journal_digest_sha256: str
    scope_registry_sha256: str
    status: str

    @property
    def approved_for_signals(self) -> bool: return False
    @property
    def orders_sent(self) -> bool: return False
    @property
    def source_authenticated(self) -> bool: return False


def read_bybit_closed_research_series(
    path: str | Path, *, scope: OfflineReviewedStreamScope, symbol: str,
    decision_at_ms: int, as_of_ms: int,
) -> BybitClosedResearchSeries:
    """Return a contiguous confirmed public series only after existing audit.

    Gaps, stale receipts, membership drift and journal tampering fail closed in
    the reused audit before any candle reaches research code.
    """
    if type(symbol) is not str or not symbol.endswith("USDT"):
        raise DataValidationError("explicit Bybit USDT research symbol required")
    journal = SQLiteOfflineClosedStreamJournal(Path(path))
    audit = journal.audit(scope=scope, decision_at_ms=decision_at_ms,
                          as_of_ms=as_of_ms, research_symbol=symbol)
    if audit.status != "offline_reviewed_24h_complete_not_top50":
        raise DataGapError("confirmed public closed series incomplete: abstain")
    # These bytes were verified in the SAME SQLite read snapshot as the digest
    # and PIT/clock/gap checks. A second database connection would create
    # an audit/read time-of-check-time-of-use window.
    values = []
    for open_ms, received_ms, raw, digest in audit.private_j2_confirmed_rows:
        item = _validated_payload(raw, digest)
        if item["open_ms"] != open_ms or item["received_ms"] != received_ms:
            raise DataGapError("research snapshot identity mismatch")
        if received_ms > as_of_ms or open_ms >= decision_at_ms:
            continue
        values.append(ClosedCandle(
            exchange="bybit_v5_public", market="linear_perpetual", symbol=symbol,
            interval="1h", open_time_ms=item["open_ms"], close_time_ms=item["end_ms"],
            open=Decimal(item["open"]), high=Decimal(item["high"]),
            low=Decimal(item["low"]), close=Decimal(item["close"]),
            base_volume=Decimal(item["volume_base"]), quote_volume=Decimal(item["turnover_usdt"]),
            quality="bybit_public_ws_confirmed_unverified",
        ))
    if len(values) < 24 or any(b.open_time_ms != a.open_time_ms + HOUR_MS for a,b in zip(values, values[1:])):
        raise DataGapError("confirmed public series has a gap: abstain")
    return BybitClosedResearchSeries(tuple(values), audit.journal_digest_sha256,
                                     scope.registry_sha256, "research_only_public_closed_series")
