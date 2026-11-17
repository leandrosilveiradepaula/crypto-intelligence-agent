"""D402: executable complete PUBLIC-ADAPTER -> PAPER J4 lifecycle proof.

All public WS frames are synthetic and injected. This is a reproducible
offline exercise of the actual D390/D386/D385/D391 adapter-to-ledger path.
It does not access Bybit, send orders, make fills from prices, or alter J1.
"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import json

from crypto_intelligence_agent.bybit_public_ticker_optin_d390 import (
    run_readonly_bybit_ticker_lease,
)
from crypto_intelligence_agent.bybit_public_ticker_supervisor_d386 import (
    TickerLeaseBudget,
)
from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.paper_intrahour_coordinator_d389 import (
    PaperIntrahourDecision,
)
from crypto_intelligence_agent.paper_intrahour_proof_d392 import (
    HOUR_START_MS, MINUTE_MS, POSITION_ID, SYMBOL, _frame, _new_position,
    _route, _explicit_fill,
)
from crypto_intelligence_agent.paper_position_reservations import (
    SQLitePaperPositionJournal,
)
from crypto_intelligence_agent.synthetic_order_lifecycle import (
    PaperOrderEvent, PaperOrderEventKind,
)

_ACK = json.dumps({
    "success": True, "ret_msg": "subscribe", "conn_id": "fixture",
    "op": "subscribe", "req_id": "cia-ticker-1",
})


class _Clock:
    def __init__(self, at_ms: int):
        self.utc_ms = at_ms
        self.monotonic_seconds = 0.0

    def mono(self) -> float:
        return self.monotonic_seconds

    def wall(self) -> int:
        return self.utc_ms

    def sleep(self, seconds: float) -> None:
        self.monotonic_seconds += seconds
        self.utc_ms += round(seconds * 1000)


class _FixtureSocket:
    def __init__(self, clock: _Clock, frame: str):
        self.clock = clock
        self.frames = [_ACK, frame]
        self.closed = False
        self.sent: list[dict] = []

    def send(self, raw: str) -> None:
        message = json.loads(raw)
        if message.get("op") not in ("subscribe", "ping"):
            raise DataValidationError("D402 cannot submit non-public WS operations")
        self.sent.append(message)

    def recv(self, timeout: float) -> str:
        if self.frames:
            return self.frames.pop(0)
        self.clock.sleep(timeout)
        raise TimeoutError()

    def close(self) -> None:
        self.closed = True


def _lease(router, *, minute: int, mark: str, bid: str, ask: str) -> dict:
    at_ms = HOUR_START_MS + minute * MINUTE_MS
    clock = _Clock(at_ms)
    frame = _frame(at_ms=at_ms, cs=1, kind="snapshot",
                   mark=mark, bid=bid, ask=ask)
    socket = _FixtureSocket(clock, frame)
    report = run_readonly_bybit_ticker_lease(
        ranked_symbols=(SYMBOL,),
        universe_at_ms=HOUR_START_MS + MINUTE_MS,
        allow_public_websocket=True,
        confirm_personal_readonly_research=True,
        confirm_region_eligible=True,
        paper_router=router,
        session_factory=lambda: socket,
        clock=clock.mono,
        wall_ms=clock.wall,
        sleeper=clock.sleep,
        budget=TickerLeaseBudget(max_sessions=1, max_frames=16, max_seconds=2),
    )
    if (not socket.closed or
            report["status"] != "lease_completed" or
            report["ticker_frames_accepted"] != 1 or
            report["subscriptions_acknowledged"] != 1 or
            report["orders_sent"] or
            report["paper_monitoring"]["orders_sent"]):
        raise DataValidationError("D402 synthetic WS/PAPER session failed")
    return report


def _step(store: SQLitePaperPositionJournal, minute: int, decision: str) -> dict:
    b = store.load(POSITION_ID)
    return {
        "minute_of_hour": minute,
        "decision": decision,
        "exit_intents": len(b.exit_orders),
        "filled_exit_units": str(b.filled_exit_units),
        "reserved_unfilled_units": str(b.reserved_unfilled_units),
        "remaining_units": str(b.confirmed_remaining_units),
    }


def demonstrate_adapter_to_paper_cycle(
    *, scenario: str = "closed",
) -> dict:
    """Verify two target intents and a stop, or UNKNOWN blocking all later exits.

    Position opening and any fill receipts are explicitly injected synthetic
    events. There is NO inference of executions from ticker frames.
    """
    if scenario not in ("closed", "unknown"):
        raise DataValidationError("D402 scenario must be closed or unknown")
    with TemporaryDirectory(prefix="cia-d402-offline-paper-") as dirname:
        path = Path(dirname) / "paper.sqlite"
        store = _new_position(path, short=False)
        router = _route(path, short=False)
        steps = []
        reports = []
        for minute, mark, bid, ask, decision in (
            (12, "100.5", "101", "101.02",
             PaperIntrahourDecision.TARGET_RESERVED),
            (19, "102.5", "103", "103.02",
             PaperIntrahourDecision.TARGET_RESERVED if scenario == "closed"
             else PaperIntrahourDecision.TARGET_PENDING),
            (27, "98", "98", "98.02",
             PaperIntrahourDecision.STOP_RESERVED if scenario == "closed"
             else PaperIntrahourDecision.STOP_UNRESOLVED),
        ):
            report = _lease(router, minute=minute, mark=mark, bid=bid, ask=ask)
            reports.append(report)
            counts = report["paper_monitoring"]["decision_counts"]
            if counts.get(decision.value, 0) != 1:
                raise DataValidationError("D402 expected PAPER decision not recorded")
            steps.append(_step(store, minute, decision.value))
            balance = store.load(POSITION_ID)
            if minute == 12:
                intent = balance.exit_orders[-1].intent.intent_id
                if scenario == "closed":
                    _explicit_fill(
                        store, minute=12, intent_id=intent,
                        event_id="fixture_d402_first_fill", units=Decimal(30),
                    )
                else:
                    at_ms = HOUR_START_MS + 12 * MINUTE_MS + 1
                    store.append_exit_events(
                        POSITION_ID, intent,
                        (PaperOrderEvent(
                            "fixture_d402_unknown", PaperOrderEventKind.UNKNOWN,
                            at_ms,
                        ),),
                        as_of_ms=at_ms,
                    )
            elif minute == 19 and scenario == "closed":
                intent = balance.exit_orders[-1].intent.intent_id
                _explicit_fill(
                    store, minute=19, intent_id=intent,
                    event_id="fixture_d402_second_fill", units=Decimal(20),
                )
            elif minute == 27 and scenario == "closed":
                intent = balance.exit_orders[-1].intent.intent_id
                _explicit_fill(
                    store, minute=27, intent_id=intent,
                    event_id="fixture_d402_stop_fill", units=Decimal(50),
                )
        # Read from a new journal reader, verifying durable PAPER state.
        final = SQLitePaperPositionJournal(path).load(POSITION_ID)
        expected = ((Decimal(100), Decimal(0), Decimal(0), 3)
                    if scenario == "closed"
                    else (Decimal(0), Decimal(30), Decimal(100), 1))
        actual = (final.filled_exit_units, final.reserved_unfilled_units,
                  final.confirmed_remaining_units, len(final.exit_orders))
        if actual != expected:
            raise DataValidationError("D402 PAPER ledger reconciliation mismatch")
        if sum(r["ticker_frames_accepted"] for r in reports) != 3:
            raise DataValidationError("D402 market frames missing")
        return {
            "schema_version": "cia-paper-public-adapter-proof-d402-v1",
            "status": ("synthetic_cycle_closed" if scenario == "closed"
                       else "unknown_requires_reconciliation"),
            "scenario": scenario,
            "same_hour": True,
            "source": "SYNTHETIC_INJECTED_BYBIT_PUBLIC_TICKER",
            "subscription_sessions": len(reports),
            "post_ack_quotes": sum(r["ticker_frames_accepted"] for r in reports),
            "steps": steps,
            "final_filled_units": str(final.filled_exit_units),
            "final_reserved_units": str(final.reserved_unfilled_units),
            "final_remaining_units": str(final.confirmed_remaining_units),
            "reconciliation_required": scenario == "unknown",
            "fills_are_explicit_fixtures_only": True,
            "real_market_connected": False,
            "real_fills_verified": False,
            "native_stop_verified": False,
            "risk_safety_verified": False,
            "order_submission_enabled": False,
            "orders_sent": False,
            "approved_for_live_use": False,
        }
