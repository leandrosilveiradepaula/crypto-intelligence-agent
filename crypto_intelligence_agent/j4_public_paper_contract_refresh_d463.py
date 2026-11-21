"""D463: refresh PAPER contract shapes asynchronously without stale WS quotes.

The REST 24h historical bootstrap can last >100s; the original D451 metadata
must not be relabelled fresh. Queue a bounded single-symbol public REST
instruments-info GET in a separate thread, require the *same* immutable
contract terms and a newer BBO quote after refresh. No private API, live
orders, account access, J1 journal, or trust in leverage tiers.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import os
from queue import Empty, Full, Queue
import threading
import time

from .bybit_dynamic_contract_shape_d463 import _check_contract_identity
from .bybit_public_j1_transport import (
    BoundedBybitPublicClient, instruments_url,
)
from .bybit_public_ticker_state_d385 import BybitTickerQuote
from .j2_dynamic_public_n50_d451 import DynamicPublicN50
from .market_data import DataGapError, DataValidationError
from .paper_margin_preflight import PaperLinearContractFixture
from .synthetic_order_lifecycle import PaperVenue

_CAP = 50
_RETRY_MS = 15_000


class AsyncPublicPaperContractTerms:
    """No GET on a ticker callback. One worker handles max 50 queued symbols."""

    def __init__(
        self, *, snapshot: DynamicPublicN50, max_age_ms: int,
        enable_public_contract_refresh: bool = False,
        client: BoundedBybitPublicClient | None = None,
        wall_ms=None,
    ):
        if (enable_public_contract_refresh is not True
                or type(snapshot) is not DynamicPublicN50
                or type(max_age_ms) is not int
                or not 1 <= max_age_ms <= 60_000):
            raise DataValidationError("D463 explicit bounded PAPER contract refresh required")
        self._injected = client is not None
        if self._injected:
            if (type(client) is not BoundedBybitPublicClient
                    or client.transport is None
                    or not callable(wall_ms)
                    or snapshot.source_mode != "injected_offline_protocol_replay"):
                raise DataValidationError("D463 offline injected REST source required")
        else:
            if (wall_ms is not None
                    or snapshot.source_mode != "public_rest_observed_unverified"
                    or os.name != "posix" or os.geteuid() == 0):
                raise DataValidationError("D463 real REST refresh needs nonroot owner clock")
            client = BoundedBybitPublicClient()
            wall_ms = lambda: time.time_ns() // 1_000_000
        self._snapshot = snapshot
        self._client = client
        self._wall_ms = wall_ms
        self._ttl_ms = max_age_ms
        self._members = {member.symbol: member for member in snapshot.ranked}
        if len(self._members) != 50:
            raise DataValidationError("D463 requires exactly 50 cohort contracts")
        self._q = Queue(maxsize=_CAP)
        self._queued: set[str] = set()
        self._refreshed: dict[str, int] = {}
        self._last_requested: dict[str, int] = {}
        self._lock = threading.RLock()
        self._requested = 0
        self._succeeded = 0
        self._rejected = 0

    def __call__(self, quote: BybitTickerQuote) -> PaperLinearContractFixture:
        if type(quote) is not BybitTickerQuote:
            raise DataValidationError("D463 typed public market BBO needed")
        member = self._members.get(quote.symbol)
        if member is None:
            raise DataValidationError("D463 symbol not admitted into fixed current N50")
        with self._lock:
            at = self._refreshed.get(quote.symbol)
            if (at is None or at > quote.received_at_ms
                    or quote.received_at_ms - at > self._ttl_ms):
                old = self._last_requested.get(quote.symbol)
                if (quote.symbol not in self._queued and
                        (old is None or quote.received_at_ms - old >= _RETRY_MS)):
                    try:
                        self._q.put_nowait(quote.symbol)
                    except Full:
                        pass
                    else:
                        self._queued.add(quote.symbol)
                raise DataGapError("D463 fresh PAPER contract pending; abstain")
        return PaperLinearContractFixture(
            venue=PaperVenue.BYBIT_V5, symbol=member.symbol,
            quote_currency="USDT", observed_at_ms=at,
            fixture_version="fixture_d463_rest_shape_" +
                            self._snapshot.fingerprint_sha256[:20],
            max_leverage_assumed=member.max_leverage_assumed,
            price_tick_quote=member.tick_size,
            quantity_step_base=member.quantity_step,
            min_quantity_base=member.minimum_quantity,
            min_notional_quote=member.minimum_notional,
            max_notional_quote=member.maximum_quantity_base * quote.mark_price,
        )

    def refresh_one(self) -> bool:
        """Single bounded GET; tests may call synchronously with injected REST."""
        try:
            symbol = self._q.get_nowait()
        except Empty:
            return False
        try:
            now = self._wall_ms()
            if type(now) is not int or now < self._snapshot.ticker_received_ms:
                raise DataValidationError("D463 metadata time regressed")
            with self._lock:
                self._last_requested[symbol] = now
                self._requested += 1
            _, payload = self._client.get(instruments_url(symbol=symbol))
            received = self._wall_ms()
            _check_contract_identity(
                payload, symbol=symbol, received_at_ms=received,
                expected=self._members[symbol],
            )
            if received < now or received - now > 30_000:
                raise DataGapError("D463 contract GET took too long")
            with self._lock:
                self._refreshed[symbol] = received
                self._succeeded += 1
        except (DataGapError, DataValidationError, ValueError, TypeError,
                OSError, ConnectionError, KeyError):
            with self._lock:
                self._rejected += 1
        finally:
            with self._lock:
                self._queued.discard(symbol)
            self._q.task_done()
        return True

    def run(self, stop_event: threading.Event) -> None:
        if not callable(getattr(stop_event, "is_set", None)) or not callable(getattr(stop_event, "wait", None)):
            raise DataValidationError("D463 bounded lifecycle event required")
        while not stop_event.is_set():
            if not self.refresh_one():
                stop_event.wait(0.2)

    def sanitized_report(self) -> dict:
        with self._lock:
            return {
                "schema_version": "d463-public-paper-contract-refresh-v1",
                "requested_public_contract_gets": self._requested,
                "unchanged_rules_refreshed": self._succeeded,
                "stale_or_changed_contracts_rejected": self._rejected,
                "pending_refresh": len(self._queued),
                "rules_verified_for_live_trading": False,
                "orders_sent": False,
            }
