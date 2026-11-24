"""D449: closed-kline and post-ACK ticker callbacks -> existing PAPER lifecycle.

This is a SINGLE owner-only event coordinator for an independently admitted,
mutable 1..50-contract Bybit research scope. It does not rank/verify the
marketwide N50, create sockets, send orders or accept private credentials.
J2 journal and AUTO2/AUTO4 remain the ONLY source of research/financial state.
The caller must connect D449 to the existing validated D386/WS supervisors.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN, localcontext
from hashlib import sha256
import os
from pathlib import Path
import threading
import time
from typing import Callable

from .bybit_closed_stream_cache import HOUR_MS, OfflineReviewedStreamScope
from .bybit_public_ticker_state_d385 import BybitTickerQuote
from .j2_bybit_closed_research_bridge import (
    BybitClosedResearchSeries, read_bybit_closed_research_series,
)
from .j2_observed_bybit_research import evaluate_observed_bybit_research
from .j2_observed_paper_entry_d447 import (
    ObservedPaperEntryPolicy, reserve_observed_paper_entry,
)
from .j4_automatic_entry_materializer_d448 import (
    PaperEntryExitPolicy, arm_observed_paper_entry,
    materialize_observed_paper_entry,
)
from .j4_private_paper_ws_operator_d425 import (
    _MANIFEST, _JOURNAL, _private_directory, _owner_file,
    exclusive_paper_operator_lock, load_private_paper_routes,
)
from .market_data import DataGapError, DataValidationError
from .j2_rest_n50_history_d461 import RestN50History
from .j2_rest_ws_causal_warmup_d462 import read_causal_rest_warmup_ws_close
from .paper_causal_fill_d394 import _checked_market
from .paper_intrahour_quote_router_d391 import PaperIntrahourQuoteRouter
from .paper_margin_preflight import (
    PaperLinearContractFixture, PaperMarginPreflightRequest,
)
from .paper_order_store import SQLitePaperOrderJournal, _TABLES as _ORDER_TABLES, _VERSION as _ORDER_VERSION
from .paper_position_inspection import _read_database
from .paper_position_reservations import SQLitePaperPositionJournal
from .paper_risk_gate import PaperRiskLimits, PaperRiskObservation
from .synthetic_entry_hypotheses import CompressionBreakoutConfig
from .synthetic_manual_exit_replay import _EXACT_CONTEXT, _utc_ms
from .synthetic_order_lifecycle import PaperOrderStatus, PaperVenue
from .synthetic_position_state import SyntheticLeverageSettings, SyntheticSide

_ORDER_FILE = "paper-orders.sqlite"
_MAX_OPEN = 4096
_MAX_COHORT = 50


@dataclass(frozen=True)
class PaperPublicCycleConfig:
    """Current strategy/finance configuration, never inferred from a venue."""

    research: CompressionBreakoutConfig
    entry: ObservedPaperEntryPolicy
    exits: PaperEntryExitPolicy
    limits: PaperRiskLimits
    leverage: SyntheticLeverageSettings
    margin_quote: Decimal
    max_contract_age_ms: int = 30_000
    paper_demo_ignore_book_depth: bool = False

    def __post_init__(self) -> None:
        if (type(self.research) is not CompressionBreakoutConfig
                or type(self.entry) is not ObservedPaperEntryPolicy
                or type(self.exits) is not PaperEntryExitPolicy
                or type(self.limits) is not PaperRiskLimits
                or type(self.leverage) is not SyntheticLeverageSettings
                or type(self.margin_quote) is not Decimal
                or not self.margin_quote.is_finite()
                or not Decimal("0.01") <= self.margin_quote <= Decimal("10000")
                or type(self.max_contract_age_ms) is not int
                or not 1 <= self.max_contract_age_ms <= 60_000
                or type(self.paper_demo_ignore_book_depth) is not bool):
            raise DataValidationError("D449 complete bounded PAPER policy required")
        first = self.exits.tranches[0]
        if (self.entry.target_distance_bps != self.exits.target_distances_bps[0]
                or self.entry.stop_distance_bps != self.exits.stop_distance_bps
                or self.entry.first_tranche_fraction * Decimal(100) != first.percent
                or self.entry.entry_fee_bps != self.exits.entry_fee_bps
                or self.entry.exit_fee_bps != self.exits.exit_fee_bps
                or self.entry.entry_adverse_slippage_bps != self.exits.entry_adverse_slippage_bps
                or self.entry.exit_adverse_slippage_bps != self.exits.exit_adverse_slippage_bps):
            raise DataValidationError("D449 J2/J3/PAPER exit economic assumptions disagree")


@dataclass(frozen=True)
class _Candidate:
    symbol: str
    series: BybitClosedResearchSeries
    side: SyntheticSide
    relative_return_pct: Decimal
    quote_turnover: Decimal
    volume_intensity: Decimal


def _stable_intent(symbol: str, close_ms: int) -> str:
    value = "d447-observed-compression-bybit-v1|" + symbol + "|" + str(close_ms)
    return "fixture_observed_open_" + sha256(value.encode("ascii")).hexdigest()[:24]


def _effective_size(
    mark: Decimal, contract: PaperLinearContractFixture,
    config: PaperPublicCycleConfig,
) -> tuple[Decimal, Decimal] | None:
    """Never silently raise margin to satisfy lot step or market minimum."""
    if type(contract) is not PaperLinearContractFixture:
        raise DataValidationError("D449 public contract assumptions must be typed")
    with localcontext(_EXACT_CONTEXT):
        leverage = Decimal(config.leverage.for_new_positions)
        notional = config.margin_quote * leverage
        # Floor to the actual declared step (not just its decimal exponent).
        units = (notional / mark // contract.quantity_step_base) * contract.quantity_step_base
        if units <= 0:
            return None
        margin = units * mark / leverage
        # The configured margin is a CAP, not a minimum use threshold.
        # A coarse lot step may leave an honest, unused remainder. PRE11
        # independently enforces min size/notional and available leverage.
        if margin <= 0 or margin > config.margin_quote:
            return None
        return units, margin


def _read_observed_opens(path: Path):
    """Bounded, verified AUTO2 readback, NOT a second opening ledger."""
    from .paper_order_store import SQLitePaperOrderJournal
    with _read_database(path, _ORDER_TABLES, "paper_order_meta", _ORDER_VERSION) as conn:
        names = conn.execute(
            "SELECT intent_id FROM paper_order_intents WHERE effect='OPEN' "
            "AND intent_id LIKE 'fixture_observed_open_%' "
            "ORDER BY intent_id LIMIT ?", (_MAX_OPEN + 1,),
        ).fetchall()
        if len(names) > _MAX_OPEN:
            raise DataValidationError("D449 open intent inventory over bounded limit")
        items = []
        for row in names:
            entry = SQLitePaperOrderJournal._checked_entry(conn, row["intent_id"])
            if not entry.intent.intent_id.startswith("fixture_observed_open_"):
                raise DataValidationError("D449 wrong observed PAPER intent")
            items.append(entry)
        return tuple(items)


class PublicPaperCycle:
    """Route all held exits first; only then admit NEW PAPER entries.

    Supply risk observations from an EXPLICIT independent PAPER risk source:
    an omitted/stale or fabricated account snapshot must not default to zero.
    All methods are synchronous and lock-protected for dual public feeds.
    """

    def __init__(
        self, *, scope: OfflineReviewedStreamScope,
        closed_journal_path: Path, private_paper_directory: Path,
        config: PaperPublicCycleConfig,
        contract_for_quote: Callable[[BybitTickerQuote], PaperLinearContractFixture],
        risk_for_quote: Callable[[BybitTickerQuote], PaperRiskObservation],
        historical_rest_warmup: RestN50History | None = None,
    ):
        if (type(scope) is not OfflineReviewedStreamScope
                or not 1 <= len(scope.contracts) <= _MAX_COHORT
                or "BTCUSDT" not in {m.symbol for m in scope.contracts}
                or len({m.symbol for m in scope.contracts}) != len(scope.contracts)
                or type(config) is not PaperPublicCycleConfig
                or not isinstance(closed_journal_path, Path)
                or not isinstance(private_paper_directory, Path)
                or not callable(contract_for_quote) or not callable(risk_for_quote)
                or (historical_rest_warmup is not None
                    and (type(historical_rest_warmup) is not RestN50History
                         or historical_rest_warmup.scope_sha256 != scope.registry_sha256
                         or historical_rest_warmup.snapshot_file is None))):
            raise DataValidationError("D449 typed independent public cohort and PAPER inputs required")
        self._home = _private_directory(private_paper_directory)
        if (closed_journal_path.resolve(strict=True) == (self._home / _ORDER_FILE).resolve(strict=False)
                or closed_journal_path.resolve(strict=True) == (self._home / _JOURNAL).resolve(strict=False)
                or any(p.startswith("j1-") for p in self._home.parts)):
            raise DataValidationError("D449 J2 and PAPER must be isolated from J1")
        self._closed = closed_journal_path
        self._scope = scope
        self._rest_warmup = historical_rest_warmup
        self._symbols = frozenset(m.symbol for m in scope.contracts)
        self._config = config
        self._contract = contract_for_quote
        self._risk = risk_for_quote
        self._lock = threading.RLock()
        self._closes: dict[str, tuple[int, int]] = {}
        self._ranked: tuple[_Candidate, ...] = ()
        self._prepared_close_ms: int | None = None
        self._attempted: set[str] = set()
        self._pending: dict[str, str] = {}
        self._router: PaperIntrahourQuoteRouter | None = None
        self._counts: dict[str, int] = {}
        # Reuse existing durable order/position files. A bare coordinator
        # never initializes an account, credentials, or N50 ranking service.
        for filename in (_ORDER_FILE, _JOURNAL):
            target = self._home / filename
            if not target.exists() and not target.is_symlink():
                directory_fd = os.open(
                    self._home, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                )
                try:
                    fd = os.open(
                        filename, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                        0o600, dir_fd=directory_fd,
                    )
                    os.close(fd)
                finally:
                    os.close(directory_fd)
            # Reject unsafe existing files: no relaxing chmod on someone
            # else's journal and no symlink or surprise hard link.
            fd = _owner_file(self._home, filename)
            os.close(fd)
        self._orders = SQLitePaperOrderJournal(self._home / _ORDER_FILE)
        self._positions = SQLitePaperPositionJournal(self._home / _JOURNAL)
        self._reload_held()
        self.recover_observed_openings()

    @property
    def monitored_symbols(self) -> frozenset[str]:
        """Ticker subscriptions: the current scope PLUS held/pending assets."""
        with self._lock:
            held = self._router.monitored_symbols if self._router else frozenset()
            return self._symbols | held | frozenset(self._pending)

    def _count(self, name: str) -> None:
        self._counts[name] = self._counts.get(name, 0) + 1

    def _reload_held(self) -> None:
        manifest = self._home / _MANIFEST
        self._router = (
            load_private_paper_routes(
                self._home, enable_hypothetical_exit_fills=True,
            ) if manifest.exists() or manifest.is_symlink() else None
        )

    def recover_observed_openings(self) -> None:
        """After restart, continue ONLY previously armed PAPER strategies.

        A crash between AUTO2 reservation and strategy arming leaves an
        unarmed PENDING entry: fail closed; never invent a new stop or
        sidecar with possibly changed user settings.
        """
        with self._lock:
            for entry in _read_observed_opens(self._home / _ORDER_FILE):
                if entry.snapshot.status not in (
                    PaperOrderStatus.PENDING, PaperOrderStatus.FILLED,
                ):
                    continue
                try:
                    # D448 verifies strategy, exact receipt and existing AUTO2.
                    result = materialize_observed_paper_entry(
                        private_paper_directory=self._home,
                        intent_id=entry.intent.intent_id,
                        quote=None, as_of_ms=max(
                            entry.intent.created_at_ms, entry.snapshot.as_of_ms,
                            time.time_ns() // 1_000_000,
                        ), enable_hypothetical_open_fill=True,
                    )
                except DataValidationError:
                    # Missing/corrupt strategy is a BLOCKER, not a reason to
                    # send anything, bypass health or guess protections.
                    raise
                if result["status"] == "await_post_latency_bbo":
                    self._pending[entry.intent.symbol] = entry.intent.intent_id
                elif result["status"] == "paper_position_routed_for_continuous_held_monitor":
                    self._reload_held()
                    self._count("recovered_position")
                elif result["status"] == "paper_open_expired_cancelled":
                    self._count("recovered_expired_paper_open")
                else:
                    raise DataValidationError("D449 unknown recovered OPEN state")

    def on_confirmed_close(self, *, symbol: str, open_ms: int, received_ms: int) -> str:
        """Call ONLY after D386/J2's proven post-ACK journal append callback."""
        with self._lock:
            if (symbol not in self._symbols or type(open_ms) is not int
                    or open_ms % HOUR_MS or type(received_ms) is not int
                    or received_ms < open_ms + HOUR_MS
                    or received_ms > open_ms + HOUR_MS + 120_000):
                raise DataValidationError("D449 untrusted confirmed close callback")
            before = self._closes.get(symbol)
            if before is not None and open_ms < before[0]:
                raise DataGapError("D449 old close cannot regress cohort")
            if before is not None and open_ms == before[0]:
                return "duplicate_closed_hour_no_effect"
            self._closes[symbol] = (open_ms, received_ms)
            self._ranked = ()
            self._prepared_close_ms = None
            self._attempted.clear()
            self._count("confirmed_close_observed")
            return "confirmed_close_buffered"

    def _prepare(self, *, now_ms: int) -> str:
        if self._prepared_close_ms is not None:
            return "same_cohort"
        # All 1..50 *independently admitted* members must be from ONE close
        # epoch; no partial scope may bootstrap a fresh entry.
        if set(self._closes) != self._symbols:
            return "closed_cohort_incomplete"
        opens = {event[0] for event in self._closes.values()}
        if len(opens) != 1:
            return "closed_cohort_mixed_hours"
        close = next(iter(opens)) + HOUR_MS - 1
        if not 0 < now_ms - close <= self._config.entry.max_signal_age_ms:
            return "closed_cohort_stale"
        studies = {}
        for symbol in sorted(self._symbols):
            try:
                if self._rest_warmup is not None:
                    joined = read_causal_rest_warmup_ws_close(
                        history=self._rest_warmup,
                        scope=self._scope, journal_path=self._closed,
                        symbol=symbol, open_ms=close+1-HOUR_MS,
                        received_ms=self._closes[symbol][1],
                    )
                    series = joined.series
                else:
                    series = read_bybit_closed_research_series(
                        self._closed, scope=self._scope, symbol=symbol,
                        decision_at_ms=close + 1, as_of_ms=now_ms,
                    )
                observed = evaluate_observed_bybit_research(
                    series, config=self._config.research, decision_at_ms=close + 1,
                    close_safety_ms=1,
                    allow_causal_rest_ws_warmup=self._rest_warmup is not None,
                )
            except (DataGapError, DataValidationError):
                return "closed_history_incomplete"
            if series.candles[-1].close_time_ms != close:
                return "last_closed_bar_mismatch"
            studies[symbol] = (series, observed)
        btc = studies["BTCUSDT"][0].candles
        with localcontext(_EXACT_CONTEXT):
            btc_return = (btc[-1].close / btc[-24].open - 1) * 100
            candidates: list[_Candidate] = []
            for symbol, (series, study) in studies.items():
                if symbol == "BTCUSDT" or not study.hypotheses:
                    continue
                h = study.hypotheses[0]
                bars = series.candles
                relative = (bars[-1].close / bars[-24].open - 1) * 100 - btc_return
                if ((h.side is SyntheticSide.LONG and relative <= 0)
                        or (h.side is SyntheticSide.SHORT and relative >= 0)):
                    continue
                candidates.append(_Candidate(
                    symbol, series, h.side, relative,
                    sum((x.quote_volume for x in bars[-24:]), Decimal(0)),
                    h.quote_volume_to_prior_mean,
                ))
            candidates.sort(key=lambda c: (
                -abs(c.relative_return_pct), -c.volume_intensity,
                -c.quote_turnover, c.symbol,
            ))
        self._ranked = tuple(candidates)
        self._prepared_close_ms = close
        self._count("cohort_researched")
        return "cohort_ready"

    def on_public_quote(self, quote: BybitTickerQuote) -> str:
        """D385 post-ACK ticker. EXIT reservations precede all new openings."""
        with self._lock:
            _checked_market(quote)
            if quote.symbol not in self.monitored_symbols:
                return "noncohort_quote_ignored"
            # This path is called only from validated D385 post-ACK callbacks.
            # Exchange-clock freshness is not replaced by receipt freshness.
            if quote.received_at_ms - quote.exchange_at_ms > 3_000:
                return "stale_exchange_quote_abstain"
            if self._router is not None and quote.symbol in self._router.monitored_symbols:
                lock = exclusive_paper_operator_lock(self._home)
                try:
                    try:
                        self._router.process(quote)
                    except DataGapError:
                        # A reconnect may replay an older exchange timestamp
                        # after the new WS ACK. This quote is noncausal and
                        # must NOT reserve an exit, but it must not tear down
                        # all 50 public subscriptions either. Financial
                        # validation/other unexpected errors still fail closed.
                        self._count("held_quote_noncausal_abstained")
                        return "held_quote_noncausal_abstained"
                finally:
                    os.close(lock)
                self._count("held_exit_quote_processed")
            # A pending opening was already screened at a PREVIOUS quote.
            # It may fill only after the explicit D448 latency and rechecks.
            pending_id = self._pending.get(quote.symbol)
            if pending_id is not None:
                outcome = materialize_observed_paper_entry(
                    private_paper_directory=self._home,
                    intent_id=pending_id, quote=quote,
                    as_of_ms=quote.received_at_ms,
                    enable_hypothetical_open_fill=True,
                    paper_demo_ignore_book_depth=self._config.paper_demo_ignore_book_depth,
                )
                if outcome["status"] == "paper_position_routed_for_continuous_held_monitor":
                    del self._pending[quote.symbol]
                    self._reload_held()
                    self._count("paper_position_created")
                elif outcome["status"] == "paper_open_expired_cancelled":
                    del self._pending[quote.symbol]
                    self._count("paper_open_expired_cancelled")
                else:
                    self._count(outcome["status"])
                return outcome["status"]
            if quote.symbol not in self._symbols:
                return "held_only_quote_processed"
            state = self._prepare(now_ms=quote.received_at_ms)
            if state not in ("same_cohort", "cohort_ready"):
                return state
            candidates = [c for c in self._ranked if c.symbol == quote.symbol]
            if not candidates or quote.symbol in self._attempted:
                return "no_new_paper_candidate"
            candidate = candidates[0]
            self._attempted.add(quote.symbol)
            try:
                contract = self._contract(quote)
            except DataGapError:
                # D463: an asynchronous PUBLIC contract refresh was queued.
                # No intent/sidecar has been written, so a later, newer BBO
                # can retry only after the unchanged 0600 contract is fresh.
                self._attempted.discard(quote.symbol)
                self._count("public_contract_refresh_pending")
                return "public_contract_refresh_pending"
            except DataValidationError:
                return "public_contract_or_paper_risk_unavailable"
            try:
                risk = self._risk(quote)
            except (DataGapError, DataValidationError):
                return "public_contract_or_paper_risk_unavailable"
            if (type(contract) is not PaperLinearContractFixture
                    or type(risk) is not PaperRiskObservation
                    or contract.symbol != quote.symbol
                    or risk.symbol != quote.symbol
                    or contract.venue is not PaperVenue.BYBIT_V5):
                raise DataValidationError("D449 forged public contract or PAPER risk")
            size = _effective_size(quote.mark_price, contract, self._config)
            if size is None:
                return "configured_margin_does_not_fit_contract_lot"
            qty, effective_margin = size
            receipt = PaperMarginPreflightRequest(
                self._config.leverage, effective_margin, contract,
                self._config.max_contract_age_ms,
            )
            expected_intent = _stable_intent(
                quote.symbol, candidate.series.candles[-1].close_time_ms,
            )
            try:
                result = reserve_observed_paper_entry(
                    candidate.series, config=self._config.research,
                    quote=quote, observation=risk, limits=self._config.limits,
                    margin=receipt, policy=self._config.entry,
                    requested_units=qty, journal=self._orders,
                    position_journal_path=self._home / _JOURNAL,
                    now_ms=quote.received_at_ms,
                    allow_hypothetical_paper_open=True,
                    allow_causal_rest_ws_warmup=self._rest_warmup is not None,
                )
            except DataValidationError:
                # A crash between AUTO2 and sidecar might leave a PENDING.
                # Never re-arm an unknown policy; report as unresolved.
                return "paper_entry_replay_or_validation_blocked"
            if result.status != "paper_open_intent_reserved_only":
                self._count(result.status)
                return result.status
            if result.intent_id != expected_intent:
                raise DataValidationError("D449 noncanonical observed entry identity")
            armed = arm_observed_paper_entry(
                private_paper_directory=self._home,
                intent_id=result.intent_id, policy=self._config.exits,
                allow_paper_entry_strategy=True,
            )
            if armed["status"] != "paper_entry_plan_armed":
                raise DataValidationError("D449 strategy not durable after OPEN")
            self._pending[quote.symbol] = result.intent_id
            self._count("paper_open_pending_armed")
            return "paper_open_pending_armed"

    def on_ticker_session_reset(self) -> None:
        """D386 reconnect: invalidate ephemeral venue sequence context."""
        with self._lock:
            if self._router is not None:
                self._router.begin_new_market_session()

    def sanitized_report(self) -> dict:
        with self._lock:
            return {
                "schema_version": "j2-j4-provisional-n50-paper-cycle-d449-v1",
                "mode": "public_data_unverified_paper_only",
                "research_cohort_contracts": len(self._symbols),
                "research_cohort_complete":
                    set(self._closes) == self._symbols
                    and len({x[0] for x in self._closes.values()}) == 1,
                "last_researched_closed_ms": self._prepared_close_ms,
                "eligible_relative_btc_hypotheses": len(self._ranked),
                "research_profile": (
                    self._config.research.entry_mode
                    if self._config.research.entry_mode != "breakout"
                    else "experimental_paper_relaxed_breakout"
                    if self._config.research.experimental_paper_relaxation
                    else "strict_compression_breakout"
                ),
                "pending_paper_open_count": len(self._pending),
                "held_paper_contract_count":
                    len(self._router.monitored_symbols) if self._router else 0,
                "event_counts": dict(sorted(self._counts.items())),
                "historical_rest_warmup_enabled": self._rest_warmup is not None,
                "paper_demo_depth_assumption_enabled": self._config.paper_demo_ignore_book_depth,
                "marketwide_n50_independently_verified": False,
                "financial_backtest_approved": False,
                "real_fills_verified": False,
                "exchange_stops_installed": False,
                "source_authenticated": False,
                "no_automatic_live_trading": True,
                "orders_sent": False, "approved_for_live_use": False,
            }
