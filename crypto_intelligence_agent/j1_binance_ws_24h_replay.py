"""OPS36: offline 24-hour Binance WS x=true continuity for reviewed samples.

No network, database, order sender, worker, or proof of source authenticity.
Reuses OPS32 causal checks and OPS34 instrument/crypto PIT validation.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, Context, localcontext
from hashlib import sha256
import json
import re

from .crypto_asset_registry import CryptoRegistrySnapshot
from .j1_binance_top50_pit import (
    HOUR_MS, WINDOW_HOURS, BinanceCatalogCapture,
    _catalog, _eligible_shape, _registry_known,
    bind_binance_ws_close_to_catalog_offline, content_sha256,
)
from .j1_causal_source_decision import (
    SourceEvidence, _Veto, _ohlcv, decide_causal_source,
)
from .market_data import DataGapError, DataValidationError

_SYMBOL = re.compile(r"[A-Z0-9]{2,24}USDT\Z")
_MAX_UTC_MS = 4_102_444_800_000


@dataclass(frozen=True)
class BinanceWSClosedEpoch:
    """Contemporaneous pre-close catalog followed by post-ACK WS final frames."""
    catalog: BinanceCatalogCapture
    closes: tuple[SourceEvidence, ...]


@dataclass(frozen=True)
class BinanceWS24hMember:
    symbol: str
    turnover_24h_quote_usdt: Decimal


@dataclass(frozen=True)
class BinanceWS24hReplay:
    decision_at_ms: int
    selected_contract_count: int
    epochs_checked: int
    ranked: tuple[BinanceWS24hMember, ...]
    replay_digest_sha256: str
    rank_digest_sha256: str

    def sanitized_report(self, *, include_public_symbols: bool = False) -> dict:
        if type(include_public_symbols) is not bool:
            raise DataValidationError("OPS36 symbol visibility opt-in must be bool")
        result = {
            "schema_version": "j1_ops36_binance_ws_24h_v1",
            "status": "binance_ws_closed24h_reviewed_sample_unverified",
            "epochs_checked": self.epochs_checked,
            "reviewed_selected_contracts": self.selected_contract_count,
            "reviewed_complete_24h_contracts": self.selected_contract_count,
            "ranked_up_to_50": len(self.ranked),
            "quote_turnover_currency": "USDT",
            "replay_digest_sha256": self.replay_digest_sha256,
            "rank_digest_sha256": self.rank_digest_sha256,
            "source_authenticated": False,
            "usdm_contract_verified": False,
            "crypto_identity_verified_live": False,
            "marketwide_top50_verified": False,
            "canonical_ohlcv_approved": False,
            "continuous_collector_authorized": False,
            "financial_backtest_approved": False,
            "live_trading_authorized": False,
            "orders_sent": False,
            "network_requests": 0,
            "storage_writes": 0,
        }
        if include_public_symbols:
            result["reviewed_public_symbols_only"] = [
                item.symbol for item in self.ranked
            ]
        return result


def audit_binance_ws_closed_24h_offline(*,
    epochs: tuple[BinanceWSClosedEpoch, ...],
    symbols: tuple[str, ...],
    registry: CryptoRegistrySnapshot,
    decision_at_ms: int,
) -> BinanceWS24hReplay:
    """All 24 UTC hours and every selected contract must be accepted together.

    Catalog is a caller-provided pre-close PIT observation (not proof of venue
    origin). A post-close x=true WS event must pass OPS32 and OPS34. Full
    market coverage is NOT inferred from a caller-selected sample.
    """
    if (type(epochs) is not tuple or len(epochs) != WINDOW_HOURS
            or type(symbols) is not tuple or not 1 <= len(symbols) <= 52
            or any(type(s) is not str or _SYMBOL.fullmatch(s) is None
                   for s in symbols)
            or len(symbols) != len(set(symbols))
            or type(registry) is not CryptoRegistrySnapshot
            or type(decision_at_ms) is not int
            or not HOUR_MS <= decision_at_ms < _MAX_UTC_MS
            or decision_at_ms % HOUR_MS):
        raise DataValidationError("OPS36 bounded 24h configuration required")

    expected = set(symbols)
    totals = {s: Decimal(0) for s in symbols}
    prior_identity: dict[str, str] = {}
    last_receipt = 0
    commitments = []
    with localcontext(Context(prec=120)):
        for idx, epoch in enumerate(epochs):
            close = decision_at_ms - (WINDOW_HOURS - idx - 1) * HOUR_MS
            if type(epoch) is not BinanceWSClosedEpoch or type(epoch.closes) is not tuple:
                raise DataValidationError("OPS36 invalid hourly epoch")
            catalog = epoch.catalog
            rows, _ = _catalog(catalog)
            # Fetch identity shortly BEFORE this close, not after the first
            # post-close WS final frame. Do not time-travel catalog state.
            if (not close - 60_000 <= catalog.requested_at_ms < close
                    or catalog.received_at_ms >= close
                    or catalog.requested_at_ms <= last_receipt):
                raise DataValidationError("OPS36 catalog PIT hour or order mismatch")
            bases = _registry_known(registry, as_of_ms=catalog.requested_at_ms)
            if len(epoch.closes) != len(expected):
                raise DataGapError("OPS36 missing/duplicate hourly close")
            seen = set()
            for event in epoch.closes:
                if type(event) is not SourceEvidence or event.symbol not in expected:
                    raise DataValidationError("OPS36 foreign selected event")
                if event.symbol in seen:
                    raise DataGapError("OPS36 duplicate event hides missing close")
                seen.add(event.symbol)
                if (event.venue != "binance_usdm" or event.transport != "ws"
                        or event.interval != "1h" or event.ack_verified is not True
                        or event.requested_at_ms is not None
                        or type(event.received_at_ms) is not int
                        or not close <= event.received_at_ms <= close + 30_000
                        or event.received_at_ms <= last_receipt):
                    raise DataValidationError("OPS36 event clock/source not causal")
                instrument = rows.get(event.symbol)
                if (instrument is None or not _eligible_shape(instrument)
                        or instrument["baseAsset"] not in bases):
                    raise DataValidationError("OPS36 selected contract not reviewed")
                identity = content_sha256(instrument)
                if (event.symbol in prior_identity
                        and prior_identity[event.symbol] != identity):
                    raise DataValidationError("OPS36 selected contract metadata drift")
                prior_identity[event.symbol] = identity
                causal = decide_causal_source(
                    expected_venue="binance_usdm",
                    expected_symbol=event.symbol, evidence=(event,),
                )
                if causal.status != "source_closed_research_unverified":
                    raise DataValidationError("OPS36 OPS32 causal veto")
                linked = bind_binance_ws_close_to_catalog_offline(
                    evidence=event, catalog=catalog, registry=registry,
                )
                if linked["status"] != "binance_causal_metadata_link_research_only":
                    raise DataValidationError("OPS36 OPS34 contract link veto")
                try:
                    k = event.payload["k"]
                    values = _ohlcv(tuple(k[x] for x in ("o", "h", "l", "c", "v", "q")))
                    start = k["t"]
                except (_Veto, KeyError, TypeError) as exc:
                    raise DataValidationError("OPS36 malformed close") from exc
                if start != close - HOUR_MS or start < instrument["onboardDate"]:
                    raise DataGapError("OPS36 closed hour or listing mismatch")
                totals[event.symbol] += values[5]  # Binance k.q: quote turnover, not k.v
                commitments.append((idx, event.symbol, start,
                                    tuple(format(v, "f") for v in values), identity))
                last_receipt = event.received_at_ms
            if seen != expected:
                raise DataGapError("OPS36 incomplete selected hour")

        ordered = sorted(totals.items(), key=lambda item: (-item[1], item[0]))
        ranked = tuple(BinanceWS24hMember(s, v) for s, v in ordered[:50])
        digest = content_sha256([
            [symbol, format(value, "f")] for symbol, value in ordered
        ])
        replay_digest = sha256(json.dumps(
            ["j1-ops36-replay-v1", decision_at_ms, commitments, digest],
            ensure_ascii=True, sort_keys=True, separators=(",", ":"),
        ).encode("ascii")).hexdigest()
        return BinanceWS24hReplay(decision_at_ms, len(symbols), 24, ranked,
                                  replay_digest, digest)
