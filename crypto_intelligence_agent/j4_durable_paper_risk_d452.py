"""D452: real local AUTO2/AUTO4 PAPER risk state, no invented account balance.

RO snapshots replay ALL order/position journals via canonical validators,
verify opening identity/receipt and derive pending count and gross exposure
from fresh PUBLIC mark observations. A prior hypothetical fill without cost
and realized-PnL ledger is NOT proof of zero realized loss; deny new opens.
Held exits remain independently serviced by the D449/D391 quote router.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext
import os
from pathlib import Path
import threading

from .bybit_public_ticker_state_d385 import BybitTickerQuote
from .j4_private_paper_ws_operator_d425 import (
    _JOURNAL, _private_directory, _owner_file,
)
from .market_data import DataGapError, DataValidationError
from .paper_causal_fill_d394 import _checked_market
from .paper_open_health import _checked_order_entries
from .paper_operator_kill_switch import _read_locked
from .paper_order_store import (
    _TABLES as _ORDER_TABLES, _VERSION as _ORDER_VERSION,
)
from .paper_position_inspection import _crosscheck_opening, _read_database
from .paper_position_reservations import (
    SQLitePaperPositionJournal, _TABLES as _POSITION_TABLES,
    _VERSION as _POSITION_VERSION, _balance,
)
from .paper_risk_gate import PaperRiskObservation
from .synthetic_manual_exit_replay import _EXACT_CONTEXT
from .synthetic_order_lifecycle import (
    PaperOrderEffect, PaperOrderStatus, PaperVenue,
)

_ORDER_FILE = "paper-orders.sqlite"
_MAX_ROWS = 4096


@dataclass(frozen=True)
class DurablePaperRiskSnapshot:
    """Gross exposure is local PAPER only, NEVER exchange account exposure."""

    symbol_exposure_quote: Decimal
    portfolio_exposure_quote: Decimal
    pending_open_orders: int
    unreconciled_open_exists: bool
    kill_switch_active: bool
    filled_open_count: int
    filled_exit_count: int
    mark_coverage_complete: bool
    realized_loss_known_zero: bool

    def sanitized_report(self) -> dict[str, object]:
        return {
            "schema_version": "d452-local-paper-risk-snapshot-v1",
            "status": "local_paper_journals_replayed_unverified",
            "symbol_exposure_quote": format(self.symbol_exposure_quote, "f"),
            "portfolio_exposure_quote": format(self.portfolio_exposure_quote, "f"),
            "pending_open_orders": self.pending_open_orders,
            "unreconciled_open_exists": self.unreconciled_open_exists,
            "kill_switch_active": self.kill_switch_active,
            "filled_open_count": self.filled_open_count,
            "filled_exit_count": self.filled_exit_count,
            "market_mark_coverage_complete": self.mark_coverage_complete,
            "realized_loss_known_zero": self.realized_loss_known_zero,
            "venue_account_authenticated": False,
            "financial_pnl_verified": False,
            "orders_sent": False,
            "approved_for_live_use": False,
        }


class DurablePaperRiskSource:
    """Callable risk provider for D449, fed by actual D386 post-ACK quotes."""

    def __init__(self, *, private_paper_directory: Path,
                 max_quote_age_ms: int = 3000):
        if type(max_quote_age_ms) is not int or not 100 <= max_quote_age_ms <= 3000:
            raise DataValidationError("D452 market risk source freshness invalid")
        self._home = _private_directory(private_paper_directory)
        self._order_path = self._home / _ORDER_FILE
        self._position_path = self._home / _JOURNAL
        for name in (_ORDER_FILE, _JOURNAL):
            fd = _owner_file(self._home, name)
            os.close(fd)
        self._limit = max_quote_age_ms
        self._quotes: dict[str, BybitTickerQuote] = {}
        self._lock = threading.RLock()

    def usable_public_quote_clock(self, quote: BybitTickerQuote) -> bool:
        """A D385 transport-accepted quote may not be usable for PAPER.

        Reject bounded server-future or delayed events as financial inputs,
        without killing the public feed or manufacturing a fresh mark.
        """
        # D385 can legitimately deliver a type-checked server-future
        # envelope within transport skew. D394's _checked_market rejects
        # future clocks, so check the timing BEFORE invoking that stricter
        # financial validator. No skipped quote reaches PAPER actions.
        if type(quote) is not BybitTickerQuote:
            raise DataValidationError("D452 requires typed public ticker")
        age = quote.received_at_ms - quote.exchange_at_ms
        if age < 0 or age > self._limit:
            return False
        _checked_market(quote)
        return True

    def observe_public_quote(self, quote: BybitTickerQuote) -> None:
        """Only D386 post-ACK callback should call this; no provider auth claim."""
        _checked_market(quote)
        if (quote.received_at_ms < quote.exchange_at_ms
                or quote.received_at_ms - quote.exchange_at_ms > self._limit):
            raise DataValidationError("D452 invalid public quote transport clocks")
        with self._lock:
            old = self._quotes.get(quote.symbol)
            if old is not None and (
                quote.received_at_ms < old.received_at_ms
                or quote.exchange_at_ms < old.exchange_at_ms
                or quote.cross_sequence < old.cross_sequence
            ):
                raise DataValidationError("D452 out-of-order public quote")
            self._quotes[quote.symbol] = quote
            # No stale quote from an old session is ever used to admit an OPEN.
            if len(self._quotes) > 100:
                raise DataValidationError("D452 public mark coverage over budget")

    def reset_market_session(self) -> None:
        """Reconnect invalidates all previously accepted public marks."""
        with self._lock:
            self._quotes.clear()

    def _read_local(self, quote: BybitTickerQuote) -> DurablePaperRiskSnapshot:
        now = quote.received_at_ms
        with _read_database(
            self._order_path, _ORDER_TABLES, "paper_order_meta", _ORDER_VERSION,
        ) as order_conn:
            orders = _checked_order_entries(order_conn)
            switch = _read_locked(order_conn)
            with _read_database(
                self._position_path, _POSITION_TABLES,
                "paper_position_meta", _POSITION_VERSION,
            ) as pos_conn:
                ids = pos_conn.execute(
                    "SELECT position_id FROM paper_positions ORDER BY position_id LIMIT ?",
                    (_MAX_ROWS + 1,),
                ).fetchall()
                if len(ids) > _MAX_ROWS:
                    raise DataValidationError("D452 position journal exceeds bounded read")
                positions = []
                for item in ids:
                    record = SQLitePaperPositionJournal._read(
                        pos_conn, item["position_id"],
                    )
                    _crosscheck_opening(order_conn, record)
                    positions.append(_balance(record))
                orphan = pos_conn.execute(
                    "SELECT 1 FROM paper_position_order_ids i "
                    "LEFT JOIN paper_positions p ON i.position_id=p.position_id "
                    "WHERE p.position_id IS NULL LIMIT 1"
                ).fetchone()
                if orphan is not None:
                    raise DataValidationError("D452 orphan PAPER position index")

            if (any(e.snapshot.as_of_ms > now for e in orders)
                    or any(p.as_of_ms > now for p in positions)):
                raise DataGapError("D452 future PAPER state cannot authorize current risk")
            tracked = {p.opening_intent_id for p in positions}
            filled_opens = [
                e for e in orders if e.intent.effect is PaperOrderEffect.OPEN
                and e.snapshot.filled_total_units > 0
            ]
            if any(e.intent.intent_id not in tracked for e in filled_opens):
                raise DataGapError("D452 opening fill not yet materialized in AUTO4")
            pending = sum(
                1 for e in orders
                if e.intent.effect is PaperOrderEffect.OPEN
                and e.snapshot.status in (
                    PaperOrderStatus.PENDING, PaperOrderStatus.ACKNOWLEDGED,
                    PaperOrderStatus.PARTIALLY_FILLED,
                )
            )
            unresolved = any(
                e.intent.effect is PaperOrderEffect.OPEN
                and (e.snapshot.requires_reconciliation
                     or e.snapshot.status is PaperOrderStatus.UNKNOWN)
                for e in orders
            )
            if pending > 100_000:
                raise DataValidationError("D452 PAPER pending count exceeds bounds")
            symbol_total = Decimal(0)
            portfolio = Decimal(0)
            marks_good = True
            filled_exit_count = 0
            with localcontext(_EXACT_CONTEXT):
                for p in positions:
                    filled_exit_count += sum(
                        1 for x in p.exit_orders if x.snapshot.filled_total_units > 0
                    )
                    if p.confirmed_remaining_units <= 0:
                        continue
                    current = self._quotes.get(p.symbol)
                    if (current is None or current.received_at_ms > now
                            or now - current.exchange_at_ms > self._limit
                            or now - current.received_at_ms > self._limit):
                        marks_good = False
                        continue
                    notional = p.confirmed_remaining_units * current.mark_price
                    portfolio += notional
                    if p.symbol == quote.symbol:
                        symbol_total += notional
            # Opening fills incur unspecified fees; existing exit FILLs have
            # no event price in AUTO4. Thus only a completely virgin journal
            # proves zero realized losses. This prevents an incorrect fake
            # zero-PnL allowance after any executed hypothetical position.
            known_zero = not filled_opens and not filled_exit_count
            return DurablePaperRiskSnapshot(
                symbol_exposure_quote=symbol_total,
                portfolio_exposure_quote=portfolio,
                pending_open_orders=pending,
                unreconciled_open_exists=unresolved,
                kill_switch_active=switch.active,
                filled_open_count=len(filled_opens),
                filled_exit_count=filled_exit_count,
                mark_coverage_complete=marks_good,
                realized_loss_known_zero=known_zero,
            )

    def inspect(self, quote: BybitTickerQuote) -> DurablePaperRiskSnapshot:
        _checked_market(quote)
        with self._lock:
            # Ensure the quote was actually accepted through the observed
            # ticker callback; typed arbitrary values are NOT provenance.
            saved = self._quotes.get(quote.symbol)
            if saved is None or saved != quote:
                raise DataGapError("D452 no current post-ACK public ticker for risk")
            return self._read_local(quote)

    def __call__(self, quote: BybitTickerQuote) -> PaperRiskObservation:
        state = self.inspect(quote)
        if not state.mark_coverage_complete:
            raise DataGapError("D452 incomplete fresh public marks for held positions")
        if not state.realized_loss_known_zero:
            raise DataGapError("D452 realized PAPER net PnL/costs unavailable: block new opens")
        return PaperRiskObservation(
            venue=PaperVenue.BYBIT_V5, symbol=quote.symbol,
            quote_currency="USDT", observed_at_ms=quote.received_at_ms,
            mark_price_quote=quote.mark_price,
            symbol_exposure_quote=state.symbol_exposure_quote,
            portfolio_exposure_quote=state.portfolio_exposure_quote,
            realized_loss_today_quote=Decimal(0),
            pending_open_orders=state.pending_open_orders,
            unresolved_open_exists=state.unreconciled_open_exists,
            kill_switch_active=state.kill_switch_active,
        )


def build_dynamic_public_paper_cycle(
    *, snapshot, closed_journal_path: Path,
    private_paper_directory: Path, config,
    historical_rest_warmup=None,
    public_contract_source=None,
):
    """Wire D451 public metadata and D452 REAL local risk into D449.

    Returns (cycle, risk_source) for the existing finite D450 dual-WS runner.
    No fake always-zero accounts, no independent PAPER balance ledger.
    """
    from .j2_dynamic_public_n50_d451 import DynamicPublicN50
    from .j2_j4_public_paper_cycle_d449 import PaperPublicCycleConfig, PublicPaperCycle
    if (type(snapshot) is not DynamicPublicN50
            or type(config) is not PaperPublicCycleConfig
            or not isinstance(closed_journal_path, Path)
            or not isinstance(private_paper_directory, Path)):
        raise DataValidationError("D452 requires complete typed N50 and policy")
    # D449 sets up empty secured journals. The risk reader only OPENS them RO.
    cycle = PublicPaperCycle(
        scope=snapshot.scope, closed_journal_path=closed_journal_path,
        private_paper_directory=private_paper_directory,
        config=config,
        contract_for_quote=(
            public_contract_source if public_contract_source is not None
            else snapshot.contract_for_quote
        ),
        risk_for_quote=lambda _: (_ for _ in ()).throw(
            DataGapError("D452 risk source not initialized")
        ),
        historical_rest_warmup=historical_rest_warmup,
    )
    risk = DurablePaperRiskSource(
        private_paper_directory=private_paper_directory,
        max_quote_age_ms=min(3000, max(100, config.limits.max_market_age_ms)),
    )
    cycle._risk = risk  # Bind only after owner safety checks; no new authority.
    return cycle, risk
