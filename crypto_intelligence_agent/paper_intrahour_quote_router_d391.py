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
from .synthetic_order_lifecycle import PaperVenue

MAX_ROUTES = 100
MAX_NETWORK_LAG_MS = 3_000
MAX_EVENTS = 100_000


@dataclass(frozen=True)
class PaperQuoteRoute:
    position_id: str
    stop_rule: PaperEmergencyStopRule
    target_policy: PaperIntrahourTargetPolicy

    def __post_init__(self) -> None:
        if (type(self.position_id) is not str or
                type(self.stop_rule) is not PaperEmergencyStopRule or
                type(self.target_policy) is not PaperIntrahourTargetPolicy or
                self.stop_rule.max_quote_age_ms != self.target_policy.max_quote_age_ms):
            raise DataValidationError("PAPER quote route requires matched typed policies")


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
                 max_network_lag_ms: int = MAX_NETWORK_LAG_MS,
                 max_events: int = MAX_EVENTS):
        if (type(routes) is not tuple or not 1 <= len(routes) <= MAX_ROUTES
                or any(type(r) is not PaperQuoteRoute for r in routes)
                or type(max_network_lag_ms) is not int
                or not 100 <= max_network_lag_ms <= 30_000
                or type(max_events) is not int or not 1 <= max_events <= MAX_EVENTS):
            raise DataValidationError("PAPER quote router bounded configuration invalid")
        self._path = Path(position_path)
        self._by_symbol: dict[str, PaperQuoteRoute] = {}
        identities = set()
        for r in routes:
            if r.position_id in identities:
                raise DataValidationError("PAPER quote route duplicate position")
            identities.add(r.position_id)
            balance = inspect_paper_position(self._path, r.position_id).balance
            if (balance.venue is not PaperVenue.BYBIT_V5
                    or balance.symbol in self._by_symbol
                    or balance.plan_version != r.target_policy.plan_version
                    or len(balance.tranches) != len(r.target_policy.prices)):
                raise DataValidationError("PAPER quote route mismatch or duplicate net symbol")
            self._by_symbol[balance.symbol] = r
        self._last: dict[str, BybitTickerQuote] = {}
        self._max_network_lag_ms = max_network_lag_ms
        self._max_events = max_events
        self._seen = 0
        self._duplicates = 0
        self._ignored = 0
        self._decisions: dict[str, int] = {}

    def process(self, quote: BybitTickerQuote) -> PaperIntrahourCoordinatedStep | None:
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
        # No shadow ledger: D389 uses AUTO4 BEGIN IMMEDIATE on each requested
        # exit and refuses duplicate or competing stop/target reservations.
        result = step_paper_intrahour_coordinated(
            self._path, route.position_id,
            stop_rule=route.stop_rule, target_policy=route.target_policy,
            quote=quote, as_of_ms=quote.received_at_ms,
        )
        self._last[quote.symbol] = quote
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
            "feed_authenticated": False,
            "marketwide_top50_verified": False,
            "native_stop_verified": False,
            "order_submission_enabled": False,
            "orders_sent": False,
            "approved_for_live_use": False,
        }
