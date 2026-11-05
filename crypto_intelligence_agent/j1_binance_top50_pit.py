"""OPS34: pure Binance USD-M instrument/crypto identity/PIT 24h ranking.

Caller-provided snapshots are research fixtures, never authenticated GETs.
A digest proves equality of local bytes, not marketwide completeness or rights.
No socket, HTTP, disk, database, environment or order access.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Context, Decimal, localcontext
from hashlib import sha256
import json
import re
from typing import Any, Mapping

from .crypto_asset_registry import CryptoRegistryHistory, CryptoRegistrySnapshot
from .j1_causal_source_decision import (
    SourceEvidence, _Veto, _decimal, _ohlcv, decide_causal_source,
)
from .market_data import DataGapError, DataValidationError

HOUR_MS = 3_600_000
WINDOW_HOURS = 24
TOP_N = 50
MAX_UTC_MS = 4_102_444_800_000
MAX_REGISTRY_AGE_MS = 7 * 86_400_000
MAX_BATCH_MS = 600_000
MAX_CLOCK_SKEW_MS = 30_000
REST_SETTLE_MS = 60_000
MAX_CATALOG_ROWS = 6000
MAX_BYTES = 4_000_000
_SYMBOL = re.compile(r"[A-Z0-9]{2,24}USDT\Z")
_BASE = re.compile(r"[A-Z0-9]{2,24}\Z")


def _clock(value: Any, *, label: str) -> int:
    if type(value) is not int or not 0 < value < MAX_UTC_MS:
        raise DataValidationError(f"OPS34 {label} invalid UTC-ms")
    return value


def content_sha256(payload: Any) -> str:
    """Canonical local integrity only; neither signature nor provenance."""
    try:
        data = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                          allow_nan=False, ensure_ascii=True).encode("ascii")
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise DataValidationError("OPS34 noncanonical JSON") from exc
    if len(data) > MAX_BYTES:
        raise DataValidationError("OPS34 oversized capture")
    return sha256(data).hexdigest()


@dataclass(frozen=True)
class BinanceCatalogCapture:
    payload: Any
    requested_at_ms: int
    received_at_ms: int
    payload_sha256: str
    endpoint: str = "/fapi/v1/exchangeInfo"
    caller_declares_full_response: bool = False


@dataclass(frozen=True)
class BinanceKlineCapture:
    symbol: str
    payload: Any
    requested_at_ms: int
    received_at_ms: int
    payload_sha256: str
    endpoint: str = "/fapi/v1/klines"
    interval: str = "1h"
    venue: str = "binance_usdm"


@dataclass(frozen=True)
class ReviewedBinanceRankMember:
    rank: int
    symbol: str
    base: str
    turnover_24h_usdt: Decimal


@dataclass(frozen=True)
class OfflineBinanceTop50Research:
    registry_sha256: str
    catalog_sha256: str
    decision_at_ms: int
    catalog_rows: int
    reviewed_eligible: int
    reviewed_new_listings: int
    plausible_unreviewed: int
    ranked: tuple[ReviewedBinanceRankMember, ...]

    def sanitized_report(self, *, include_public_symbols: bool = False) -> dict:
        if type(include_public_symbols) is not bool:
            raise DataValidationError("OPS34 symbol visibility opt-in invalid")
        canonical = [[m.rank, m.symbol, format(m.turnover_24h_usdt, "f")]
                     for m in self.ranked]
        digest = content_sha256(canonical)
        report = {
            "status": ("binance_reviewed_50_closed_hours_research_only"
                       if len(self.ranked) == TOP_N
                       else "binance_reviewed_rank_below_50_research_only"),
            "reviewed_eligible_contracts": self.reviewed_eligible,
            "reviewed_insufficient_listing_history": self.reviewed_new_listings,
            "reviewed_24h_windows_complete": len(self.ranked),
            "plausible_unreviewed_contracts": self.plausible_unreviewed,
            "catalog_instrument_rows": self.catalog_rows,
            "registry_integrity_sha256": self.registry_sha256,
            "catalog_membership_sha256": self.catalog_sha256,
            "reviewed_rank_digest_sha256": digest,
            "quote_turnover_currency": "USDT",
            "rolling_ticker_used_for_rank": False,
            "catalog_completeness_authenticated": False,
            "catalog_server_time_used_for_pit": False,
            "crypto_identity_independently_authenticated": False,
            "usdm_contract_verified": False,
            "marketwide_top50_verified": False,
            "canonical_ohlcv_approved": False,
            "continuous_collector_authorized": False,
            "source_authenticated": False,
            "orders_sent": False,
            "network_requests": 0,
            "storage_writes": 0,
        }
        if include_public_symbols:
            report["reviewed_public_symbols_only"] = [x.symbol for x in self.ranked]
        return report


def _registry_known(registry: CryptoRegistrySnapshot, *, as_of_ms: int) -> frozenset[str]:
    # The existing history validator reconstructs the signed-format manifest,
    # detects forged dataclass fields and checks time of independent review.
    if type(registry) is not CryptoRegistrySnapshot:
        raise DataValidationError("OPS34 requires validated crypto registry")
    history = CryptoRegistryHistory((registry,))
    selected = history.as_of(as_of_ms, max_age_ms=MAX_REGISTRY_AGE_MS)
    return selected.verified_crypto_bases


def _catalog(capture: BinanceCatalogCapture) -> tuple[dict[str, dict], str]:
    if type(capture) is not BinanceCatalogCapture:
        raise DataValidationError("OPS34 untyped catalog")
    start = _clock(capture.requested_at_ms, label="catalog request")
    end = _clock(capture.received_at_ms, label="catalog receipt")
    if (capture.endpoint != "/fapi/v1/exchangeInfo"
            or capture.caller_declares_full_response is not True
            or not start <= end <= start + MAX_CLOCK_SKEW_MS):
        raise DataValidationError("OPS34 catalog endpoint or capture incomplete")
    if (type(capture.payload_sha256) is not str
            or content_sha256(capture.payload) != capture.payload_sha256):
        raise DataValidationError("OPS34 catalog integrity mismatch")
    p = capture.payload
    if (type(p) is not dict or p.get("timezone") != "UTC"
            or type(p.get("serverTime")) is not int
            or type(p.get("symbols")) is not list
            or not 1 <= len(p["symbols"]) <= MAX_CATALOG_ROWS
            # Binance docs say exchangeInfo.serverTime is to be ignored.
            # Causality uses separately audited request/receipt sidecars.
            ):
        raise DataValidationError("OPS34 catalog schema/clock rejected")
    result: dict[str, dict] = {}
    mandatory = {"symbol", "pair", "baseAsset", "quoteAsset", "marginAsset",
                 "contractType", "status", "onboardDate", "underlyingType",
                 "deliveryDate"}
    for row in p["symbols"]:
        if type(row) is not dict or not mandatory <= row.keys():
            raise DataValidationError("OPS34 catalog row incomplete")
        sym = row["symbol"]
        if (type(sym) is not str or len(sym) > 50 or not sym.isascii()
                or not sym.isupper() or sym in result
                or any(type(row[k]) is not str for k in (
                    "pair", "baseAsset", "quoteAsset", "marginAsset",
                    "contractType", "status", "underlyingType"))
                or type(row["onboardDate"]) is not int
                or type(row["deliveryDate"]) is not int
                or not 0 < row["onboardDate"] < MAX_UTC_MS
                or row["deliveryDate"] < 0):
            raise DataValidationError("OPS34 catalog row corrupt or duplicate")
        result[sym] = row
    # Ignore expected changing serverTime and response order; reject ALL other
    # instrument metadata drift across capture (including unreviewed contracts).
    membership = content_sha256([[key, result[key]] for key in sorted(result)])
    return result, membership


def _eligible_shape(row: dict) -> bool:
    base, symbol = row["baseAsset"], row["symbol"]
    return (type(base) is str and _BASE.fullmatch(base) is not None
            and type(symbol) is str and _SYMBOL.fullmatch(symbol) is not None
            and symbol == base + "USDT" and row["pair"] == symbol
            and row["contractType"] == "PERPETUAL"
            and row["status"] == "TRADING"
            and row["quoteAsset"] == "USDT"
            and row["marginAsset"] == "USDT"
            and row["underlyingType"] == "COIN")


def _parse_window(capture: BinanceKlineCapture, *,
                  symbol: str, decision_at_ms: int,
                  earliest_request_ms: int, latest_receipt_ms: int) -> Decimal:
    if type(capture) is not BinanceKlineCapture:
        raise DataValidationError("OPS34 untyped kline capture")
    req = _clock(capture.requested_at_ms, label="kline request")
    recv = _clock(capture.received_at_ms, label="kline receipt")
    if (capture.venue != "binance_usdm" or capture.endpoint != "/fapi/v1/klines"
            or capture.interval != "1h" or capture.symbol != symbol
            or not earliest_request_ms <= req <= recv <= latest_receipt_ms
            or recv - req > MAX_CLOCK_SKEW_MS):
        raise DataValidationError("OPS34 kline source or capture clock rejected")
    if type(capture.payload_sha256) is not str or (
            content_sha256(capture.payload) != capture.payload_sha256):
        raise DataValidationError("OPS34 kline integrity mismatch")
    rows = capture.payload
    if type(rows) is not list or len(rows) != WINDOW_HOURS:
        raise DataGapError("OPS34 requires exactly 24 closed hourly candles")
    with localcontext(Context(prec=120)):
        total = Decimal(0)
        for idx, row in enumerate(rows):
            start = decision_at_ms - (WINDOW_HOURS - idx) * HOUR_MS
            if (type(row) is not list or len(row) != 12
                    or type(row[0]) is not int or row[0] != start
                    or type(row[6]) is not int
                    or row[6] != start + HOUR_MS - 1):
                raise DataGapError("OPS34 gap, duplicate, reordered or unfinished hour")
            try:
                o, h, l, c, v, quote = _ohlcv((
                    row[1], row[2], row[3], row[4], row[5], row[7],
                ))
                taker_base = _decimal(row[9], positive=False)
                taker_quote = _decimal(row[10], positive=False)
            except _Veto as exc:
                raise DataValidationError("OPS34 invalid OHLCV Decimal") from exc
            if (type(row[8]) is not int or row[8] < 0
                    or taker_base > v or taker_quote > quote
                    or type(row[11]) not in (int, str)):
                raise DataValidationError("OPS34 kline trade/taker volume rejected")
            total += quote  # Binance [7] is USDT quote volume, NOT base [5].
        if not total.is_finite() or total < 0:
            raise DataValidationError("OPS34 nonfinite quote turnover")
    return total


def rank_binance_reviewed_24h_offline(*,
    before: BinanceCatalogCapture, after: BinanceCatalogCapture,
    registry: CryptoRegistrySnapshot,
    klines: Mapping[str, BinanceKlineCapture],
    decision_at_ms: int,
) -> OfflineBinanceTop50Research:
    """All catalog-reviewed, 24h-old crypto perps must have every closed bar.

    This is NEVER a marketwide Top50, even for >50 complete candidates.
    """
    boundary = _clock(decision_at_ms, label="decision")
    if boundary % HOUR_MS:
        raise DataValidationError("OPS34 decision must be a whole UTC hour")
    before_rows, before_digest = _catalog(before)
    after_rows, after_digest = _catalog(after)
    if before_digest != after_digest or before_rows != after_rows:
        raise DataValidationError("OPS34 catalog membership/metadata changed")
    if (before.requested_at_ms < boundary + REST_SETTLE_MS
            or after.received_at_ms > boundary + MAX_BATCH_MS
            or before.received_at_ms >= after.requested_at_ms):
        raise DataValidationError("OPS34 catalog not in closed-hour capture window")
    bases = _registry_known(registry, as_of_ms=before.requested_at_ms)
    candidates = [row for row in before_rows.values() if _eligible_shape(row)]
    reviewed = [row for row in candidates if row["baseAsset"] in bases]
    unreviewed = len(candidates) - len(reviewed)
    old = [row for row in reviewed if row["onboardDate"] <= boundary - WINDOW_HOURS*HOUR_MS]
    if not old:
        raise DataGapError("OPS34 no reviewed contract with full listing window")
    young = len(reviewed) - len(old)
    expected = {row["symbol"] for row in old}
    if (not isinstance(klines, dict) or set(klines) != expected):
        raise DataGapError("OPS34 missing/extra/replayed kline symbol window")
    results: list[tuple[str, str, Decimal]] = []
    first_receipt = before.received_at_ms
    last_receipt = before.received_at_ms
    with localcontext(Context(prec=120)):
        for member in sorted(old, key=lambda r: r["symbol"]):
            sample = klines[member["symbol"]]
            if (type(sample) is not BinanceKlineCapture
                    or sample.requested_at_ms < first_receipt
                    or sample.requested_at_ms < last_receipt
                    or sample.received_at_ms > after.requested_at_ms):
                raise DataValidationError("OPS34 kline chronology/replay rejected")
            value = _parse_window(
                sample, symbol=member["symbol"], decision_at_ms=boundary,
                earliest_request_ms=max(boundary+REST_SETTLE_MS, first_receipt),
                latest_receipt_ms=after.requested_at_ms,
            )
            last_receipt = sample.received_at_ms
            results.append((member["symbol"], member["baseAsset"], value))
        results.sort(key=lambda item: (-item[2], item[0]))
    ranking = tuple(ReviewedBinanceRankMember(i, sym, base, volume)
                    for i, (sym, base, volume) in enumerate(results[:TOP_N], 1))
    return OfflineBinanceTop50Research(
        registry_sha256=registry.sha256_digest,
        catalog_sha256=before_digest,
        decision_at_ms=boundary,
        catalog_rows=len(before_rows),
        reviewed_eligible=len(reviewed),
        reviewed_new_listings=young,
        plausible_unreviewed=unreviewed,
        ranked=ranking,
    )


def bind_binance_ws_close_to_catalog_offline(*,
    evidence: SourceEvidence, catalog: BinanceCatalogCapture,
    registry: CryptoRegistrySnapshot,
) -> dict:
    """Bind *caller-supplied* post-ACK x=true WS to metadata, never certify feed.

    OPS33 aggregate counters lack raw candle identity: cannot be retrospectively
    bound to a contract, and should NOT be passed to this API.
    """
    abstain = {"status": "binance_causal_contract_abstain",
               "usdm_contract_verified": False, "canonical_ohlcv_approved": False,
               "marketwide_top50_verified": False, "network_requests": 0,
               "storage_writes": 0, "orders_sent": False}
    if type(evidence) is not SourceEvidence or type(catalog) is not BinanceCatalogCapture:
        return abstain
    try:
        rows, _ = _catalog(catalog)
        bases = _registry_known(registry, as_of_ms=catalog.requested_at_ms)
        if (evidence.venue != "binance_usdm" or evidence.transport != "ws"
                or evidence.interval != "1h" or evidence.symbol not in rows
                or not _eligible_shape(rows[evidence.symbol])
                or rows[evidence.symbol]["baseAsset"] not in bases
                or not catalog.received_at_ms <= evidence.received_at_ms
                <= catalog.received_at_ms + MAX_BATCH_MS):
            return abstain
        outcome = decide_causal_source(
            expected_venue="binance_usdm", expected_symbol=evidence.symbol,
            evidence=(evidence,),
        )
        if outcome.status != "source_closed_research_unverified":
            return abstain
        # Validated WS source hour must be on or after instrument onboarding.
        start = evidence.payload["k"]["t"]
        if start < rows[evidence.symbol]["onboardDate"]:
            return abstain
    except (DataValidationError, KeyError, TypeError, ValueError, AttributeError):
        return abstain
    return {**abstain, "status": "binance_causal_metadata_link_research_only",
            "metadata_eligible_candidate": True}
