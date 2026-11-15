"""J2/J3 #640: freeze WS N50 watchlist observations, grade later closed marks.

No storage, scheduling, venue data access, fill simulation or orders. This is
a causal *interface* for ex-post reference marks, not proof that an observation
was registered prospectively, financial backtesting, or profitable execution.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Context, Decimal, InvalidOperation, localcontext
from hashlib import sha256
import json
import re
from typing import Any, Mapping

from .bybit_closed_stream_cache import HOUR_MS
from .market_data import DataValidationError
from .synthetic_cost_scenarios import (
    SyntheticCostScenario, SyntheticFundingEvent, _amount, _rate,
    evaluate_synthetic_costs,
)
from .synthetic_intrabar_barriers import ResearchDirection

_SHA = re.compile(r"[0-9a-f]{64}\Z")
_SYMBOL = re.compile(r"[A-Z0-9]{1,28}USDT\Z")
_DECIMAL = re.compile(r"(?:0|[1-9][0-9]{0,39})(?:\.[0-9]{1,18})?\Z")
_CONTEXT = Context(prec=256)
_MAX = 5
_MIN_MS = 1_600_000_000_000
_MAX_MS = 4_102_444_800_000


def _positive(raw: object, *, context: str) -> Decimal:
    if type(raw) is not str or _DECIMAL.fullmatch(raw) is None:
        raise DataValidationError(f"{context}: finite positive decimal text required")
    try:
        value = Decimal(raw)
    except (InvalidOperation, ValueError):
        raise DataValidationError(f"{context}: malformed decimal") from None
    if not value.is_finite() or value <= 0:
        raise DataValidationError(f"{context}: nonpositive value")
    return value


def _digest(raw: object) -> str:
    if type(raw) is not str or _SHA.fullmatch(raw) is None:
        raise DataValidationError("bounded SHA256 hex digest required")
    return raw


def _time(raw: object, *, aligned: bool = False) -> int:
    if (type(raw) is not int or not _MIN_MS <= raw < _MAX_MS
            or aligned and raw % HOUR_MS):
        raise DataValidationError("bounded UTC-ms / hour alignment required")
    return raw


@dataclass(frozen=True)
class FrozenCandidateReference:
    symbol: str
    direction: ResearchDirection
    decision_close: Decimal


@dataclass(frozen=True)
class FrozenWSWatchlistReference:
    """Volatile source reference. A SHA does NOT prove early registration."""

    decision_end_ms: int
    registered_at_ms: int
    scope_sha256: str
    window_sha256: str
    btc_decision_close: Decimal
    candidates: tuple[FrozenCandidateReference, ...]
    decision_commitment_sha256: str

    @property
    def prospective_registration_verified(self) -> bool:
        return False

    @property
    def approved_for_signals(self) -> bool:
        return False

    @property
    def orders_sent(self) -> bool:
        return False


@dataclass(frozen=True)
class ForwardCostAssumptions:
    """User-declared hypothetical quote notional and J3 cost schedule."""

    hypothetical_notional_quote_units: Decimal
    entry_fee_bps: Decimal
    exit_fee_bps: Decimal
    entry_adverse_slippage_bps: Decimal
    exit_adverse_slippage_bps: Decimal

    def __post_init__(self) -> None:
        _amount(self.hypothetical_notional_quote_units, "hypothetical notional")
        for name in (
            "entry_fee_bps", "exit_fee_bps",
            "entry_adverse_slippage_bps", "exit_adverse_slippage_bps",
        ):
            _rate(getattr(self, name), name, signed=False)


def _commitment(ref: FrozenWSWatchlistReference) -> str:
    payload = {
        "decision_end_ms": ref.decision_end_ms,
        "registered_at_ms": ref.registered_at_ms,
        "scope_sha256": ref.scope_sha256,
        "window_sha256": ref.window_sha256,
        "btc_decision_close": format(ref.btc_decision_close, "f"),
        "candidates": [
            [candidate.symbol, candidate.direction.value,
             format(candidate.decision_close, "f")]
            for candidate in ref.candidates
        ],
    }
    return sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("ascii")).hexdigest()


def freeze_ws_watchlist_reference(
    snapshot: object, *,
    registered_at_ms: int,
    ranked_scope_sha256: str,
    decision_closes: Mapping[str, str],
) -> FrozenWSWatchlistReference:
    """Freeze only a READY PRIVATE J2 shortlist at the original UTC close.

    Prices are passed separately by a trusted owner caller; the watchlist
    itself does not include OHLC. No new SQLite or network reader is created.
    """
    if (type(snapshot) is not dict
            or snapshot.get("schema_version") != "j2-n50-ws-descriptive-watchlist-v1"
            or snapshot.get("status") != "ws_descriptive_watchlist_ready"
            or snapshot.get("quality") != "private_ws_observations_not_trading_signals"
            or snapshot.get("ws_journal_integrity_replayed") is not True
            or snapshot.get("audited_assets") != 50
            or type(snapshot.get("audited_assets")) is not int
            or snapshot.get("eligible_closed_bars_per_asset") != 24
            or type(snapshot.get("eligible_closed_bars_per_asset")) is not int
            or snapshot.get("btc_context_available") is not True
            or any(snapshot.get(field) is not False for field in (
                "formal_d323_24h_verified", "continuous_collector_verified",
                "rotation_36h_live_verified", "marketwide_top50_verified",
                "crypto_identity_independently_verified", "source_authenticated",
                "approved_for_signals", "approved_for_live_use",
                "financial_backtest_approved", "orders_sent", "systemd_modified",
            ))
            or snapshot.get("execution_intents_created") != 0
            or type(snapshot.get("execution_intents_created")) is not int
            or snapshot.get("network_requests") != 0
            or type(snapshot.get("network_requests")) is not int
            or snapshot.get("database_mutation_statements") != 0
            or type(snapshot.get("database_mutation_statements")) is not int
            or type(decision_closes) is not dict):
        raise DataValidationError("J2 private watchlist replay required")
    end = _time(snapshot.get("latest_closed_end_ms"), aligned=True)
    registered = _time(registered_at_ms)
    if not end + 180_000 <= registered < end + HOUR_MS - 60_000:
        raise DataValidationError("observation was not registered in causal close window")
    scope = _digest(ranked_scope_sha256)
    window = _digest(snapshot.get("window_digest_sha256"))
    selected: list[FrozenCandidateReference] = []
    directions = (
        ("up", ResearchDirection.LONG, "above_prior_23h_high"),
        ("down", ResearchDirection.SHORT, "below_prior_23h_low"),
    )
    previous_symbols: set[str] = set()
    for key, direction, breakout in directions:
        count = snapshot.get(f"observed_{key}_breakout_candidates")
        reported = snapshot.get(f"{key}_breakout_watchlist")
        if (type(count) is not int or not 0 <= count <= 50
                or type(reported) is not list
                or len(reported) != min(count, _MAX)):
            raise DataValidationError("only complete top-five private shortlist can be frozen")
        last_key: tuple[Decimal, Decimal, Decimal, str] | None = None
        for row in reported:
            if (type(row) is not dict
                    or type(row.get("symbol")) is not str
                    or _SYMBOL.fullmatch(row["symbol"]) is None
                    or row["symbol"] in previous_symbols
                    or row.get("breakout") != breakout
                    or row.get("approved_for_signals") is not False
                    or row.get("orders_sent") is not False):
                raise DataValidationError("invalid shortlist row or duplicate")
            sym = row["symbol"]
            previous_symbols.add(sym)
            # These are observational filters from D308; not alpha scores.
            try:
                rel = Decimal(row["relative_vs_btc_pct_points"])
                ratio = Decimal(row["last_quote_turnover_vs_prior23_mean"])
                turnover = Decimal(row["quote_turnover_24bars_usdt"])
            except (InvalidOperation, TypeError, ValueError, KeyError):
                raise DataValidationError("invalid candidate indicators") from None
            if (not all(x.is_finite() for x in (rel, ratio, turnover))
                    or ratio < 1 or turnover <= 0
                    or direction is ResearchDirection.LONG and rel <= 0
                    or direction is ResearchDirection.SHORT and rel >= 0):
                raise DataValidationError("candidate violates D308 filters")
            sort_key = (
                -rel if direction is ResearchDirection.LONG else rel,
                -ratio, -turnover, sym,
            )
            if last_key is not None and sort_key < last_key:
                raise DataValidationError("private shortlist not causally ranked")
            last_key = sort_key
            selected.append(FrozenCandidateReference(
                symbol=sym, direction=direction,
                decision_close=_positive(decision_closes.get(sym),
                                         context="candidate decision close"),
            ))
    if (type(snapshot.get("unclassified_volume_assets")) is not int
            or not 0 <= snapshot["unclassified_volume_assets"] <= 50
            or sum(snapshot[f"observed_{key}_breakout_candidates"]
                   for key in ("up", "down")) > 50
            or set(decision_closes) != previous_symbols | {"BTCUSDT"}
            or any(type(k) is not str or _SYMBOL.fullmatch(k) is None
                   for k in decision_closes)):
        raise DataValidationError("decision close universe not identical to selected shortlist plus BTC")
    btc = _positive(decision_closes.get("BTCUSDT"), context="BTC decision close")
    provisional = FrozenWSWatchlistReference(
        end, registered, scope, window, btc, tuple(selected), "",
    )
    return FrozenWSWatchlistReference(
        end, registered, scope, window, btc, tuple(selected),
        _commitment(provisional),
    )


def _empty(status: str, *, selected: int, horizon_bars: int) -> dict[str, Any]:
    return {
        "schema_version": "j3-ws-watchlist-forward-reference-v1",
        "status": status,
        "quality": "ex_post_closed_mark_cost_assumptions_not_fills",
        "horizon_bars": horizon_bars,
        "selected_observations": selected,
        "matured_observations": 0,
        "aligned_observations": 0,
        "contrary_observations": 0,
        "unchanged_observations": 0,
        "gross_reference_bps_sum": None,
        "net_reference_after_assumed_costs_bps_sum": None,
        "same_side_btc_excess_reference_bps_sum": None,
        "assumed_total_cost_quote_units": None,
        "funding_events_hypothetical": 0,
        "prospective_registration_verified": False,
        "intrabar_path_verified": False,
        "venue_fees_verified": False,
        "funding_schedule_verified": False,
        "out_of_sample_results_validated": False,
        "financial_backtest_approved": False,
        "marketwide_top50_verified": False,
        "approved_for_signals": False,
        "live_trading_authorized": False,
        "orders_sent": False,
        "network_requests": 0,
        "database_accessed": False,
        "database_mutation_statements": 0,
        "systemd_modified": False,
    }


def evaluate_ws_watchlist_forward_marks(
    frozen: FrozenWSWatchlistReference, *,
    horizon_bars: int,
    observed_at_ms: int,
    future_scope_sha256: str,
    future_journal_digest_sha256: str,
    future_closes: Mapping[str, str] | None,
    costs: ForwardCostAssumptions,
    hypothetical_funding_events: Mapping[str, tuple[SyntheticFundingEvent, ...]] | None = None,
) -> dict[str, Any]:
    """Grade only matured CLOSED reference prices; never infer a fill.

    One frozen decision, one fixed horizon. A pure scorer cannot attest that
    decision and future prices were sourced live or registered beforehand.
    Missing futures or changed epoch abstain; they do NOT count as zero PnL.
    Funding events are synthetic user inputs to the existing J3 cost engine.
    """
    if (type(frozen) is not FrozenWSWatchlistReference
            or type(costs) is not ForwardCostAssumptions
            or type(horizon_bars) is not int or horizon_bars not in (1, 4, 24)):
        raise DataValidationError("frozen J2 decision and declared 1/4/24h J3 cost plan required")
    if (_commitment(frozen) != frozen.decision_commitment_sha256
            or _digest(frozen.scope_sha256) != frozen.scope_sha256
            or _digest(frozen.window_sha256) != frozen.window_sha256
            or _time(frozen.decision_end_ms, aligned=True) != frozen.decision_end_ms
            or _time(frozen.registered_at_ms) != frozen.registered_at_ms
            or not frozen.decision_end_ms + 180_000 <= frozen.registered_at_ms
            < frozen.decision_end_ms + HOUR_MS - 60_000):
        raise DataValidationError("frozen decision commitment or temporal integrity rejected")
    _digest(future_scope_sha256)
    _digest(future_journal_digest_sha256)
    _time(observed_at_ms)
    if (type(frozen.candidates) is not tuple
            or len(frozen.candidates) > 10
            or any(type(c) is not FrozenCandidateReference for c in frozen.candidates)
            or not all(type(c.symbol) is str and _SYMBOL.fullmatch(c.symbol)
                       and type(c.direction) is ResearchDirection
                       and type(c.decision_close) is Decimal
                       and c.decision_close.is_finite() and c.decision_close > 0
                       for c in frozen.candidates)):
        raise DataValidationError("frozen candidate values invalid")
    end = frozen.decision_end_ms + horizon_bars * HOUR_MS
    out = _empty("awaiting_future_closed_hour", selected=len(frozen.candidates),
                 horizon_bars=horizon_bars)
    if observed_at_ms < end + 180_000:
        return out
    if observed_at_ms >= end + HOUR_MS - 60_000:
        out["status"] = "future_observation_stale_abstain"
        return out
    if future_scope_sha256 != frozen.scope_sha256:
        out["status"] = "cohort_changed_forward_abstain"
        return out
    if type(future_closes) is not dict:
        out["status"] = "future_observations_unavailable"
        return out
    expected = {c.symbol for c in frozen.candidates} | {"BTCUSDT"}
    if set(future_closes) != expected:
        out["status"] = "future_observations_unavailable"
        return out
    funding = {} if hypothetical_funding_events is None else hypothetical_funding_events
    if type(funding) is not dict or not set(funding) <= expected:
        raise DataValidationError("unapproved funding event scope")
    if not frozen.candidates:
        out["status"] = "no_observations_selected"
        return out
    with localcontext(_CONTEXT):
        btc_future = _positive(future_closes["BTCUSDT"], context="future BTC close")
        btc_pct = btc_future / frozen.btc_decision_close - 1
        gross_total = Decimal(0)
        net_total = Decimal(0)
        relative_total = Decimal(0)
        cost_total = Decimal(0)
        aligned = contrary = unchanged = funding_events = 0
        for item in frozen.candidates:
            future = _positive(future_closes[item.symbol],
                               context="candidate future close")
            change = future / item.decision_close - 1
            sign = Decimal(1 if item.direction is ResearchDirection.LONG else -1)
            gross = sign * change
            events = funding.get(item.symbol, ())
            if type(events) is not tuple:
                raise DataValidationError("funding events must be a tuple")
            scenario = SyntheticCostScenario(
                direction=item.direction,
                entry_at_ms=frozen.decision_end_ms,
                exit_at_ms=end,
                entry_hypothetical_notional_quote_units=costs.hypothetical_notional_quote_units,
                exit_hypothetical_notional_quote_units=(
                    costs.hypothetical_notional_quote_units
                    * future / item.decision_close
                ),
                entry_fee_bps=costs.entry_fee_bps,
                exit_fee_bps=costs.exit_fee_bps,
                entry_adverse_slippage_bps=costs.entry_adverse_slippage_bps,
                exit_adverse_slippage_bps=costs.exit_adverse_slippage_bps,
                funding_events=events,
            )
            charged = evaluate_synthetic_costs(scenario)
            bps = Decimal(10000)
            gross_total += gross * bps
            net_total += (
                gross - charged.total_signed_cost_units
                / costs.hypothetical_notional_quote_units
            ) * bps
            relative_total += sign * (change - btc_pct) * bps
            cost_total += charged.total_signed_cost_units
            funding_events += charged.unique_funding_count
            if gross > 0:
                aligned += 1
            elif gross < 0:
                contrary += 1
            else:
                unchanged += 1
        out.update(
            status="ex_post_reference_marks_scored_not_a_backtest",
            matured_observations=len(frozen.candidates),
            aligned_observations=aligned,
            contrary_observations=contrary,
            unchanged_observations=unchanged,
            gross_reference_bps_sum=format(gross_total, "f"),
            net_reference_after_assumed_costs_bps_sum=format(net_total, "f"),
            same_side_btc_excess_reference_bps_sum=format(relative_total, "f"),
            assumed_total_cost_quote_units=format(cost_total, "f"),
            funding_events_hypothetical=funding_events,
        )
        return out
