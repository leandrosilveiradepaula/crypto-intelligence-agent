"""D391: feed quote callback -> existing D389 stop-first PAPER decision.

No private account, broker transport, real order, inferred fill or new ledger.
One position per symbol is deliberately enforced in this PAPER bridge; Bybit
one-way netting cannot be represented by multiple independent synthetic
positions on the same instrument without explicit hedge/account contracts.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .bybit_public_ticker_state_d385 import BybitTickerQuote, SOURCE
from .market_data import DataGapError, DataValidationError
from .paper_intrahour_coordinator_d389 import (
    PaperIntrahourCoordinatedStep, PaperIntrahourDecision,
    step_paper_intrahour_coordinated,
)
from .paper_intrahour_emergency_stop_d388 import PaperEmergencyStopRule
from .paper_intrahour_target_step_d387 import PaperIntrahourTargetPolicy
from .paper_position_inspection import inspect_paper_position
from .paper_causal_fill_d394 import (
    PaperObservedFillAssumptions, apply_causal_paper_fill_assumption,
)
from .synthetic_order_lifecycle import PaperOrderStatus
from .paper_runner_trailing import PaperRunnerTrailPolicy
from .paper_intrahour_runner_bridge_d395 import (
    PaperIntrahourRunnerStep, step_paper_intrahour_with_runner,
)
from .synthetic_order_lifecycle import PaperVenue

MAX_ROUTES = 100
MAX_NETWORK_LAG_MS = 3_000
MAX_EVENTS = 100_000


@dataclass(frozen=True)
class PaperQuoteRoute:
    position_id: str
    stop_rule: PaperEmergencyStopRule
    target_policy: PaperIntrahourTargetPolicy
    runner_policy: PaperRunnerTrailPolicy | None = None
    runner_path: str | Path | None = None

    def __post_init__(self) -> None:
        if (type(self.position_id) is not str or
                type(self.stop_rule) is not PaperEmergencyStopRule or
                type(self.target_policy) is not PaperIntrahourTargetPolicy or
                self.stop_rule.max_quote_age_ms != self.target_policy.max_quote_age_ms):
            raise DataValidationError("PAPER quote route requires matched typed policies")
        if (self.runner_policy is None) != (self.runner_path is None):
            raise DataValidationError("PAPER trailing requires policy and distinct journal path")
        if self.runner_policy is not None:
            if (type(self.runner_policy) is not PaperRunnerTrailPolicy
                    or not isinstance(self.runner_path, (str, Path))
                    or not str(self.runner_path)
                    or str(self.runner_path) == ":memory:"):
                raise DataValidationError("PAPER trailing route configuration invalid")


class PaperIntrahourQuoteRouter:
    """Bounded, single-writer callback for D386 public ticker supervision.

    Upstream D385 provides validated snapshots/deltas and freshness.
    This layer additionally disallows delayed transit, replayed sequences and
    wrong-position symbols. Each event invokes the D389 coordinator only once;
    persisted AUTO4 owns financial idempotency after restart. A restart of the
    router MUST be accompanied by new upstream subscribe ACK and snapshots.
    """

    def __init__(self, *, position_path: str | Path,
                 routes: tuple[PaperQuoteRoute, ...],
                 fill_assumptions: PaperObservedFillAssumptions | None = None,
                 enable_synthetic_ledger_fills: bool = False,
                 max_network_lag_ms: int = MAX_NETWORK_LAG_MS,
                 max_events: int = MAX_EVENTS):
        if (type(routes) is not tuple or not 1 <= len(routes) <= MAX_ROUTES
                or any(type(r) is not PaperQuoteRoute for r in routes)
                or type(max_network_lag_ms) is not int
                or not 100 <= max_network_lag_ms <= 30_000
                or type(max_events) is not int or not 1 <= max_events <= MAX_EVENTS
                or (fill_assumptions is not None and type(fill_assumptions) is not PaperObservedFillAssumptions)
                or type(enable_synthetic_ledger_fills) is not bool
                or (enable_synthetic_ledger_fills and fill_assumptions is None)):
            raise DataValidationError("PAPER quote router bounded configuration invalid")
        self._path = Path(position_path)
        self._by_symbol: dict[str, PaperQuoteRoute] = {}
        # Preserve manifest-selected CLOSED routes for owner-only history;
        # only NONZERO balances subscribe to public prices and own symbols.
        # A closed historical ARB may coexist with one later active ARB.
        self._routes_by_id: dict[str, PaperQuoteRoute] = {}
        for r in routes:
            if r.position_id in self._routes_by_id:
                raise DataValidationError("PAPER quote route duplicate position")
            balance = inspect_paper_position(self._path, r.position_id).balance
            if (balance.venue is not PaperVenue.BYBIT_V5
                    or balance.plan_version != r.target_policy.plan_version
                    or len(balance.tranches) != len(r.target_policy.prices)):
                raise DataValidationError("PAPER quote route mismatch")
            if r.runner_path is not None and (
                Path(r.runner_path).resolve(strict=False)
                == self._path.resolve(strict=False)
            ):
                raise DataValidationError("PAPER runner mark and financial ledgers must be separate")
            if balance.confirmed_remaining_units > 0:
                if balance.symbol in self._by_symbol:
                    raise DataValidationError("two active PAPER routes on same net symbol")
                self._by_symbol[balance.symbol] = r
            elif (balance.confirmed_remaining_units != 0
                  or balance.reserved_unfilled_units != 0
                  or balance.filled_exit_units != balance.initial_confirmed_units):
                raise DataValidationError("PAPER closed route conservation invalid")
            self._routes_by_id[r.position_id] = r
        self._last: dict[str, BybitTickerQuote] = {}
        # Preserve timestamp monotonicity across transport reconnects even
        # when exchange cross-sequence restarts with a new snapshot.
        self._last_exchange_at_ms: dict[str, int] = {}
        self._max_network_lag_ms = max_network_lag_ms
        self._max_events = max_events
        self._fill_assumptions = fill_assumptions
        self._enable_synthetic_ledger_fills = enable_synthetic_ledger_fills
        self._seen = 0
        self._duplicates = 0
        self._ignored = 0
        self._decisions: dict[str, int] = {}
        self._runner_decisions: dict[str, int] = {}
        self._fill_decisions: dict[str, int] = {}

    def _apply_later_fill_hypotheses(self, route: PaperQuoteRoute,
                                     quote: BybitTickerQuote) -> None:
        """Apply D394 only to pre-existing reconciliable AUTO4 reservations.

        The triggering quote is deliberately not special-cased: D394 itself
        enforces post-intent latency, BBO depth and idempotent event identity.
        UNKNOWN is never passed through this loop and remains reserved.
        """
        if not self._enable_synthetic_ledger_fills:
            return
        balance = inspect_paper_position(self._path, route.position_id).balance
        for order in balance.exit_orders:
            if order.snapshot.status not in (
                    PaperOrderStatus.PENDING, PaperOrderStatus.ACKNOWLEDGED,
                    PaperOrderStatus.PARTIALLY_FILLED):
                continue
            outcome = apply_causal_paper_fill_assumption(
                self._path, route.position_id, order.intent.intent_id,
                quote=quote, as_of_ms=quote.received_at_ms,
                policy=self._fill_assumptions,
                enable_synthetic_ledger_fills=True,
            )
            self._fill_decisions[outcome.decision.value] = (
                self._fill_decisions.get(outcome.decision.value, 0) + 1)

    @property
    def monitored_symbols(self) -> frozenset[str]:
        """Read-only ticker membership required by the D401 public bridge."""
        return frozenset(self._by_symbol)

    @property
    def monitored_position_ids(self) -> tuple[str, ...]:
        """Existing, explicitly routed AUTO4 IDs for owner-only UI readback.

        This is never returned in a public WS report or count-only status.
        """
        return tuple(sorted(self._routes_by_id))

    def route_for_position(self, position_id: str) -> PaperQuoteRoute | None:
        """Checked local owner route; never a public ticker or market signal."""
        if type(position_id) is not str:
            raise DataValidationError("PAPER route position id must be a string")
        return self._routes_by_id.get(position_id)

    def fresh_held_contract_count(
        self, *, at_ms: int, max_age_ms: int = MAX_NETWORK_LAG_MS,
    ) -> int:
        """Number of configured PAPER contracts fresh AT the observation end.

        Count only validated D391 quotes from the most recent ACKed socket
        session; begin_new_market_session clears this set on reconnect.
        This is NOT a claim of native stop, account protection or that the
        now CLOSED lease is still supervising. Return counts, never IDs.
        """
        if (type(at_ms) is not int
                or not 1_600_000_000_000 <= at_ms <= 4_102_444_800_000
                or type(max_age_ms) is not int
                or not 100 <= max_age_ms <= MAX_NETWORK_LAG_MS):
            raise DataValidationError("PAPER fresh held contracts clock invalid")
        return sum(
            1 for symbol in self._by_symbol
            if (symbol in self._last
                and 0 <= at_ms - self._last[symbol].exchange_at_ms <= max_age_ms
                and 0 <= at_ms - self._last[symbol].received_at_ms <= max_age_ms)
        )

    def begin_new_market_session(self) -> None:
        """Invalidate transport-specific sequence baselines, not PAPER state.

        D386 calls this before a new subscription. A new ACK + snapshot is
        still mandatory upstream; older timestamps never become new data.
        Financial reservations and runner journals are never reset.
        """
        self._last.clear()

    def process(
        self, quote: BybitTickerQuote,
    ) -> PaperIntrahourCoordinatedStep | PaperIntrahourRunnerStep | None:
        if type(quote) is not BybitTickerQuote or quote.source != SOURCE:
            raise DataValidationError("PAPER quote router requires typed unverified public quote")
        if self._seen >= self._max_events:
            raise DataGapError("PAPER quote router event budget exhausted")
        self._seen += 1
        route = self._by_symbol.get(quote.symbol)
        if route is None:
            self._ignored += 1
            return None
        if (quote.exchange_at_ms > quote.received_at_ms
                or quote.received_at_ms - quote.exchange_at_ms > self._max_network_lag_ms):
            raise DataGapError("PAPER quote router stale transport")
        old = self._last.get(quote.symbol)
        watermark = self._last_exchange_at_ms.get(quote.symbol)
        if watermark is not None and quote.exchange_at_ms <= watermark and old is None:
            raise DataGapError("PAPER quote router stale replay across sessions")
        if old is not None:
            if (quote.cross_sequence < old.cross_sequence
                    or quote.received_at_ms < old.received_at_ms
                    or quote.exchange_at_ms < old.exchange_at_ms):
                raise DataGapError("PAPER quote router regressive sequence or clock")
            if quote.cross_sequence == old.cross_sequence:
                if quote != old:
                    raise DataGapError("PAPER quote router conflicting replay")
                self._duplicates += 1
                return None
        # No shadow ledger: D389 and RUNNER3 reuse AUTO4 reservations.
        # Existing routes without trailing retain their exact D391 behavior.
        if route.runner_policy is not None:
            result = step_paper_intrahour_with_runner(
                self._path, route.runner_path, route.position_id,
                stop_rule=route.stop_rule, target_policy=route.target_policy,
                runner_policy=route.runner_policy,
                quote=quote, as_of_ms=quote.received_at_ms,
            )
            runner_state = result.runner_decision.value
            self._runner_decisions[runner_state] = (
                self._runner_decisions.get(runner_state, 0) + 1
            )
        else:
            result = step_paper_intrahour_coordinated(
                self._path, route.position_id,
                stop_rule=route.stop_rule, target_policy=route.target_policy,
                quote=quote, as_of_ms=quote.received_at_ms,
            )
        self._apply_later_fill_hypotheses(route, quote)
        self._last[quote.symbol] = quote
        self._last_exchange_at_ms[quote.symbol] = quote.exchange_at_ms
        decision = result.decision.value
        self._decisions[decision] = self._decisions.get(decision, 0) + 1
        return result

    def sanitized_report(self) -> dict:
        return {
            "schema_version": "paper-intrahour-quote-router-d391-v1",
            "status": "offline_paper_only",
            "configured_positions": len(self._by_symbol),
            "events_seen": self._seen,
            "exact_duplicates_skipped": self._duplicates,
            "other_symbols_ignored": self._ignored,
            "decision_counts": dict(sorted(self._decisions.items())),
            "runner_decision_counts": dict(sorted(self._runner_decisions.items())),
            "feed_authenticated": False,
            "marketwide_top50_verified": False,
            "native_stop_verified": False,
            "order_submission_enabled": False,
            "orders_sent": False,
            "approved_for_live_use": False,
        }
