"""D448: materialize a D447 PAPER intent into AUTO4 and D425's held monitor.

One explicit, strictly post-intent *simulated* BBO fill. No exchange ACK or
FILL is inferred or sent. AUTO2 owns opening fills; AUTO4 owns positions and
exits; D425's original manifest is the only route source for D444/D445/J5.
An immutable, owner-only strategy sidecar is NOT a second financial ledger:
it records stop/targets before an assumed fill, allowing crash recovery.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from .bybit_public_ticker_state_d385 import BybitTickerQuote
from .j4_private_paper_ws_operator_d425 import (
    _MANIFEST, _JOURNAL, _SCHEMA, _owner_file, _private_directory,
    exclusive_paper_operator_lock, load_private_paper_routes,
)
from .market_data import DataValidationError
from .paper_causal_fill_d394 import _checked_market
from .paper_margin_receipt import PaperMarginIntentReceipt
from .paper_order_store import SQLitePaperOrderJournal
from .paper_position_reservations import SQLitePaperPositionJournal
from .paper_intrahour_target_step_d387 import _levels_valid
from .synthetic_cost_scenarios import (
    BPS_DENOMINATOR, SyntheticCostScenario, _rate, evaluate_synthetic_costs,
)
from .synthetic_intrabar_barriers import ResearchDirection
from .synthetic_manual_exit_replay import _EXACT_CONTEXT, _utc_ms
from .synthetic_order_lifecycle import (
    PaperOrderEffect, PaperOrderEvent, PaperOrderEventKind,
    PaperOrderStatus, PaperVenue,
)
from .synthetic_partial_exits import (
    SyntheticExitPlan, SyntheticExitTranche, ExitBasis,
    plan_synthetic_partial_exits,
)
from .synthetic_position_state import SyntheticSide

_ORDER_FILE = "paper-orders.sqlite"
_PLAN_SCHEMA = "j4-observed-paper-entry-plan-d448-v1"
_MAX_PLAN_BYTES = 8192
_MAX_MANIFEST_BYTES = 32_768
_MAX_POSITIONS = 50
_MAX_TIME_AGE_MS = 3_000
_FILL_PREFIX = "fixture_d448_assumed_"
_EXPIRE_PREFIX = "fixture_d448_expired_"


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise DataValidationError("D448 duplicate private JSON field")
        result[key] = value
    return result


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def _dec(value: object, label: str, *, positive: bool = True) -> Decimal:
    if (type(value) is not Decimal or not value.is_finite()
            or len(value.as_tuple().digits) > 35
            or value.as_tuple().exponent < -18
            or value.adjusted() > 24 or value < 0
            or positive and value == 0):
        raise DataValidationError("D448 invalid " + label)
    return value


@dataclass(frozen=True)
class PaperEntryExitPolicy:
    """Immutable exit and assumed BBO fill terms for one PAPER opening."""

    stop_distance_bps: Decimal
    target_distances_bps: tuple[Decimal, ...]
    tranches: tuple[SyntheticExitTranche, ...]
    runner_floor_percent: Decimal
    synthetic_lot_step_units: Decimal
    entry_fee_bps: Decimal
    exit_fee_bps: Decimal
    entry_adverse_slippage_bps: Decimal
    exit_adverse_slippage_bps: Decimal
    max_spread_bps: Decimal = Decimal("30")
    max_book_participation_bps: Decimal = Decimal("2500")
    min_fill_latency_ms: int = 150
    max_fill_wait_ms: int = 60_000

    def __post_init__(self) -> None:
        if (type(self.target_distances_bps) is not tuple
                or not 1 <= len(self.target_distances_bps) <= 8
                or type(self.tranches) is not tuple
                or len(self.tranches) != len(self.target_distances_bps)
                or any(type(t) is not SyntheticExitTranche for t in self.tranches)):
            raise DataValidationError("D448 exit tranches/targets inconsistent")
        for field in (
            "stop_distance_bps", "max_spread_bps",
            "max_book_participation_bps", "entry_fee_bps", "exit_fee_bps",
            "entry_adverse_slippage_bps", "exit_adverse_slippage_bps",
        ):
            _rate(getattr(self, field), field, signed=False)
        for target in self.target_distances_bps:
            _rate(target, "target_distance", signed=False)
        if (not 0 < self.stop_distance_bps <= 1_000
                or any(not 0 < x <= 1_000 for x in self.target_distances_bps)
                or any(a >= b for a, b in zip(
                    self.target_distances_bps, self.target_distances_bps[1:]))
                or not 0 < self.max_book_participation_bps <= 10_000
                or self.max_spread_bps > 100
                or any(getattr(self, name) > 1_000 for name in (
                    "entry_fee_bps", "exit_fee_bps", "entry_adverse_slippage_bps",
                    "exit_adverse_slippage_bps",
                ))
                or type(self.min_fill_latency_ms) is not int
                or not 1 <= self.min_fill_latency_ms <= 60_000
                or type(self.max_fill_wait_ms) is not int
                or not self.min_fill_latency_ms <= self.max_fill_wait_ms <= 3_600_000):
            raise DataValidationError("D448 unsafe or unbounded PAPER fill terms")
        _dec(self.synthetic_lot_step_units, "lot step")
        # Existing PRE1 checks runner percentage bounds and conservation.
        SyntheticExitPlan(
            Decimal(1), self.tranches, self.runner_floor_percent,
        )


def _policy_payload(policy: PaperEntryExitPolicy) -> dict:
    return {
        "stop_distance_bps": str(policy.stop_distance_bps),
        "target_distances_bps": [str(x) for x in policy.target_distances_bps],
        "tranches": [
            {"basis": t.basis.value, "percent": str(t.percent)}
            for t in policy.tranches
        ],
        "runner_floor_percent": str(policy.runner_floor_percent),
        "synthetic_lot_step_units": str(policy.synthetic_lot_step_units),
        "entry_fee_bps": str(policy.entry_fee_bps),
        "exit_fee_bps": str(policy.exit_fee_bps),
        "entry_adverse_slippage_bps": str(policy.entry_adverse_slippage_bps),
        "exit_adverse_slippage_bps": str(policy.exit_adverse_slippage_bps),
        "max_spread_bps": str(policy.max_spread_bps),
        "max_book_participation_bps": str(policy.max_book_participation_bps),
        "min_fill_latency_ms": policy.min_fill_latency_ms,
        "max_fill_wait_ms": policy.max_fill_wait_ms,
    }


def _read_policy(value: object) -> PaperEntryExitPolicy:
    required = {
        "stop_distance_bps", "target_distances_bps", "tranches",
        "runner_floor_percent", "synthetic_lot_step_units", "max_spread_bps",
        "entry_fee_bps", "exit_fee_bps", "entry_adverse_slippage_bps",
        "exit_adverse_slippage_bps", "max_book_participation_bps",
        "min_fill_latency_ms", "max_fill_wait_ms",
    }
    if type(value) is not dict or set(value) != required:
        raise DataValidationError("D448 immutable entry policy schema invalid")
    def d(raw: object) -> Decimal:
        if type(raw) is not str or len(raw) > 44:
            raise DataValidationError("D448 policy decimal text invalid")
        try:
            return Decimal(raw)
        except (ValueError, ArithmeticError) as exc:
            raise DataValidationError("D448 policy decimal invalid") from exc
    try:
        targets = value["target_distances_bps"]
        tranches = value["tranches"]
        if (type(targets) is not list or type(tranches) is not list
                or len(targets) != len(tranches) or not 1 <= len(targets) <= 8):
            raise DataValidationError("D448 policy tranches invalid")
        for row in tranches:
            if type(row) is not dict or set(row) != {"basis", "percent"}:
                raise DataValidationError("D448 policy tranche invalid")
        policy = PaperEntryExitPolicy(
            stop_distance_bps=d(value["stop_distance_bps"]),
            target_distances_bps=tuple(d(x) for x in targets),
            tranches=tuple(
                SyntheticExitTranche(ExitBasis(t["basis"]), d(t["percent"]))
                for t in tranches
            ),
            runner_floor_percent=d(value["runner_floor_percent"]),
            synthetic_lot_step_units=d(value["synthetic_lot_step_units"]),
            entry_fee_bps=d(value["entry_fee_bps"]),
            exit_fee_bps=d(value["exit_fee_bps"]),
            entry_adverse_slippage_bps=d(value["entry_adverse_slippage_bps"]),
            exit_adverse_slippage_bps=d(value["exit_adverse_slippage_bps"]),
            max_spread_bps=d(value["max_spread_bps"]),
            max_book_participation_bps=d(value["max_book_participation_bps"]),
            min_fill_latency_ms=value["min_fill_latency_ms"],
            max_fill_wait_ms=value["max_fill_wait_ms"],
        )
        if _policy_payload(policy) != value:
            raise DataValidationError("D448 noncanonical policy decimal encoding")
        return policy
    except (ValueError, KeyError, TypeError, ArithmeticError) as exc:
        raise DataValidationError("D448 invalid stored PAPER entry policy") from exc


def _plan_filename(intent_id: str) -> str:
    if (type(intent_id) is not str or not intent_id.startswith("fixture_observed_open_")
            or len(intent_id) > 64 or not intent_id[22:].isalnum()):
        raise DataValidationError("D448 only D447 observed PAPER OPEN supported")
    return "paper-entry-plan-" + sha256(intent_id.encode("ascii")).hexdigest()[:32] + ".json"


def _paths(home: Path) -> tuple[Path, Path]:
    directory = _private_directory(home)
    if any(piece.startswith("j1-") for piece in directory.parts):
        raise DataValidationError("D448 must remain outside J1")
    for name in (_ORDER_FILE, _JOURNAL):
        fd = _owner_file(directory, name)
        os.close(fd)
    return directory / _ORDER_FILE, directory / _JOURNAL


def _planned(intent, receipt: PaperMarginIntentReceipt,
             policy: PaperEntryExitPolicy) -> dict:
    if (intent.effect is not PaperOrderEffect.OPEN
            or intent.venue is not PaperVenue.BYBIT_V5
            or type(policy) is not PaperEntryExitPolicy
            or type(receipt) is not PaperMarginIntentReceipt
            or receipt.quote_currency != "USDT"):
        raise DataValidationError("D448 exact Bybit PAPER opening and receipt required")
    receipt.verify_intent(intent)
    units = intent.requested_units
    if units % policy.synthetic_lot_step_units != 0:
        raise DataValidationError("D448 entry units misaligned with declared lot")
    exit_plan = SyntheticExitPlan(
        initial_units=units, tranches=policy.tranches,
        residual_floor_percent=policy.runner_floor_percent,
    )
    schedule = plan_synthetic_partial_exits(exit_plan)
    if any(x.exit_units % policy.synthetic_lot_step_units != 0
           for x in schedule.allocations) or (
               schedule.residual_floor_units % policy.synthetic_lot_step_units != 0):
        raise DataValidationError("D448 PAPER exit/runner quantities not lot-aligned")
    mark = receipt.hypothetical_mark_quote
    long = intent.position_side is SyntheticSide.LONG
    with localcontext(_EXACT_CONTEXT):
        stop = mark * (
            1 - policy.stop_distance_bps / BPS_DENOMINATOR
            if long else 1 + policy.stop_distance_bps / BPS_DENOMINATOR)
        targets = tuple(
            mark * (
                1 + bps / BPS_DENOMINATOR if long
                else 1 - bps / BPS_DENOMINATOR)
            for bps in policy.target_distances_bps
        )
    if min(stop, *targets) <= 0 or not _levels_valid(targets, intent.position_side):
        raise DataValidationError("D448 invalid stop/target price levels")
    if (stop >= mark if long else stop <= mark):
        raise DataValidationError("D448 protective stop not adverse")
    token = sha256(intent.intent_id.encode("ascii")).hexdigest()[:24]
    payload = {
        "intent_id": intent.intent_id,
        "position_id": "fixture_d448_pos_" + token,
        "symbol": intent.symbol,
        "side": intent.position_side.value,
        "reference_mark_quote": str(mark),
        "stop_mark_price": str(stop),
        "target_prices": [str(p) for p in targets],
        "policy": _policy_payload(policy),
    }
    payload["plan_version"] = "d448-" + sha256(_json(payload).encode("ascii")).hexdigest()[:24]
    return payload


def _parse_json(raw: bytes) -> object:
    try:
        return json.loads(
            raw.decode("utf-8"), object_pairs_hook=_unique_pairs,
            parse_float=lambda _: (_ for _ in ()).throw(ValueError("floats forbidden")),
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("constants forbidden")),
        )
    except (ValueError, UnicodeError, TypeError) as exc:
        raise DataValidationError("D448 invalid private JSON") from exc


def _read_owner_bytes(home: Path, name: str, limit: int) -> bytes:
    fd = _owner_file(home, name)
    with os.fdopen(fd, "rb") as source:
        raw = source.read(limit + 1)
    if not 2 <= len(raw) <= limit:
        raise DataValidationError("D448 private file size invalid")
    return raw


def _atomic_private_write(home: Path, name: str, raw: bytes) -> None:
    """Caller holds D425 single-writer lock; atomic replace, mode 0600."""
    if (not 2 <= len(raw) <= _MAX_MANIFEST_BYTES
            or "/" in name or "\\" in name or name.startswith(".")):
        raise DataValidationError("D448 output bounds invalid")
    target = home / name
    if target.exists() or target.is_symlink():
        fd = _owner_file(home, name)
        os.close(fd)
    descriptor, tmp = tempfile.mkstemp(prefix=".d448-atomic-", dir=home)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, target)
        directory_fd = os.open(home, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _read_plan(home: Path, intent, receipt: PaperMarginIntentReceipt) -> dict:
    name = _plan_filename(intent.intent_id)
    envelope = _parse_json(_read_owner_bytes(home, name, _MAX_PLAN_BYTES))
    if (type(envelope) is not dict
            or set(envelope) != {"schema_version", "payload", "sha256"}
            or envelope["schema_version"] != _PLAN_SCHEMA
            or type(envelope["payload"]) is not dict
            or type(envelope["sha256"]) is not str):
        raise DataValidationError("D448 entry strategy sidecar schema invalid")
    payload = envelope["payload"]
    if (sha256(_json(payload).encode("ascii")).hexdigest() != envelope["sha256"]
            or set(payload) != {"intent_id", "position_id", "symbol", "side",
                                "reference_mark_quote", "stop_mark_price",
                                "target_prices", "policy", "plan_version"}
            or payload["intent_id"] != intent.intent_id):
        raise DataValidationError("D448 entry strategy integrity invalid")
    policy = _read_policy(payload["policy"])
    expected = _planned(intent, receipt, policy)
    if payload != expected:
        raise DataValidationError("D448 strategy sidecar differs from AUTO2 receipt")
    return payload


def _owner_locked(home: Path):
    fd = exclusive_paper_operator_lock(home)
    return fd


def arm_observed_paper_entry(
    *, private_paper_directory: Path, intent_id: str,
    policy: PaperEntryExitPolicy, allow_paper_entry_strategy: bool = False,
) -> dict:
    """Persist immutable stop/target plan before any hypothetical OPEN fill."""
    if type(allow_paper_entry_strategy) is not bool:
        raise DataValidationError("D448 explicit arming gate invalid")
    if not allow_paper_entry_strategy:
        return _report("paper_strategy_optin_required")
    if type(policy) is not PaperEntryExitPolicy:
        raise DataValidationError("D448 typed exit policy required")
    home = _private_directory(private_paper_directory)
    _plan_filename(intent_id)
    lock = _owner_locked(home)
    try:
        order_path, _ = _paths(home)
        orders = SQLitePaperOrderJournal(order_path)
        entry = orders.load(intent_id)
        if entry.snapshot.status is not PaperOrderStatus.PENDING or entry.events:
            raise DataValidationError("D448 only a new AUTO2 PENDING may be armed")
        receipt = orders.read_margin_receipt(intent_id)
        if receipt is None:
            raise DataValidationError("D448 requires existing PRE11 margin receipt")
        payload = _planned(entry.intent, receipt, policy)
        name = _plan_filename(intent_id)
        digest = sha256(_json(payload).encode("ascii")).hexdigest()
        raw = _json({
            "schema_version": _PLAN_SCHEMA, "payload": payload,
            "sha256": digest,
        }).encode("ascii")
        if len(raw) > _MAX_PLAN_BYTES:
            raise DataValidationError("D448 entry plan too large")
        target = home / name
        if target.exists() or target.is_symlink():
            if _read_owner_bytes(home, name, _MAX_PLAN_BYTES) != raw:
                raise DataValidationError("D448 cannot change an armed entry strategy")
        else:
            _atomic_private_write(home, name, raw)
        _read_plan(home, entry.intent, receipt)
        return _report("paper_entry_plan_armed", position_count=0)
    finally:
        os.close(lock)



def _net_target_and_stop_buffer(
    planned: dict, policy: PaperEntryExitPolicy, quote: BybitTickerQuote,
    units: Decimal, margin_quote: Decimal,
) -> tuple[Decimal, Decimal]:
    """Recheck the fixed D447-reference exits against the LATER entry BBO.

    Never use a signal-close price as an executable fill. Stop at its exact
    hypothetical level is optimistic: zero/negative buffer is a veto, not a
    liquidity or liquidation approval.
    """
    long = planned["side"] == "LONG"
    direction = ResearchDirection.LONG if long else ResearchDirection.SHORT
    with localcontext(_EXACT_CONTEXT):
        entry_price = quote.ask_price if long else quote.bid_price
        target = Decimal(planned["target_prices"][0])
        stop = Decimal(planned["stop_mark_price"])
        gross_first = target - entry_price if long else entry_price - target
        loss_per_unit = entry_price - stop if long else stop - entry_price
        if gross_first <= 0 or loss_per_unit <= 0:
            return Decimal(-1), Decimal(-1)
        first = policy.tranches[0]
        first_qty = units * first.percent / Decimal(100)
        def cost(qty: Decimal, exit_price: Decimal) -> Decimal:
            return evaluate_synthetic_costs(SyntheticCostScenario(
                direction=direction,
                entry_at_ms=quote.received_at_ms,
                exit_at_ms=quote.received_at_ms + 1,
                entry_hypothetical_notional_quote_units=qty * entry_price,
                exit_hypothetical_notional_quote_units=qty * exit_price,
                entry_fee_bps=policy.entry_fee_bps,
                exit_fee_bps=policy.exit_fee_bps,
                entry_adverse_slippage_bps=policy.entry_adverse_slippage_bps,
                exit_adverse_slippage_bps=policy.exit_adverse_slippage_bps,
            )).total_signed_cost_units
        net_first = first_qty * gross_first - cost(first_qty, target)
        stop_buffer = margin_quote - units * loss_per_unit - cost(units, stop)
        return net_first, stop_buffer


def _read_routes(home: Path) -> list[dict]:
    target = home / _MANIFEST
    if not target.exists() and not target.is_symlink():
        return []
    raw = _read_owner_bytes(home, _MANIFEST, _MAX_MANIFEST_BYTES)
    data = _parse_json(raw)
    if (type(data) is not dict or set(data) != {"schema_version", "positions"}
            or data["schema_version"] != _SCHEMA
            or type(data["positions"]) is not list
            or not 1 <= len(data["positions"]) <= _MAX_POSITIONS):
        raise DataValidationError("D448 existing route manifest invalid")
    # Reuse the exact D425 loader before any mutation; validates each
    # position and security-relevant manifest field.
    load_private_paper_routes(home)
    return data["positions"]


def _route_position(home: Path, planned: dict) -> None:
    existing = _read_routes(home)
    policy = _read_policy(planned["policy"])
    route = {
        "position_id": planned["position_id"],
        "plan_version": planned["plan_version"],
        "stop_mark_price": planned["stop_mark_price"],
        "target_prices": planned["target_prices"],
        "max_spread_bps": str(policy.max_spread_bps),
        "runner": None,
    }
    named = [x for x in existing if x["position_id"] == planned["position_id"]]
    if named:
        if len(named) != 1 or named[0] != route:
            raise DataValidationError("D448 existing PAPER route conflicts with saved plan")
    else:
        if len(existing) >= _MAX_POSITIONS:
            raise DataValidationError("D448 held position capacity reached")
        # D391 enforces one-way netting: no two active routes for a symbol.
        if existing:
            book = load_private_paper_routes(home)
            if planned["symbol"] in book.monitored_symbols:
                raise DataValidationError("D448 another PAPER position already owns symbol")
        existing.append(route)
        _atomic_private_write(
            home, _MANIFEST, _json({
                "schema_version": _SCHEMA,
                "positions": sorted(existing, key=lambda x: x["position_id"]),
            }).encode("ascii"),
        )
    # When returned, D444/D445 and J5 can really load the new existing AUTO4.
    loaded = load_private_paper_routes(home)
    if planned["position_id"] not in loaded.monitored_position_ids:
        raise DataValidationError("D448 route was not visible to held worker")


def _report(status: str, *, position_count: int = 0,
            wrote_fill: bool = False) -> dict:
    return {
        "schema_version": "j4-observed-paper-materialization-d448-v1",
        "status": status, "positions_ready_for_held_worker": position_count,
        "hypothetical_open_fill_written": wrote_fill,
        "fills_at_exchange_verified": False, "native_stop_installed": False,
        "financial_pnl_verified": False, "market_data_authenticated": False,
        "new_financial_ledger_created": False, "j1_accessed": False,
        "orders_sent": False, "approved_for_live_use": False,
    }


def materialize_observed_paper_entry(
    *, private_paper_directory: Path, intent_id: str,
    quote: BybitTickerQuote | None, as_of_ms: int,
    enable_hypothetical_open_fill: bool = False,
    paper_demo_ignore_book_depth: bool = False,
) -> dict:
    """Full-simulated-fill or recover FULL AUTO2 -> AUTO4 -> held D425 route.

    The strategy sidecar MUST already exist. On a crash after AUTO2 FILL, a
    retry with quote=None reconstructs the SAME position without another FILL.
    A PAPER entry is not tradable, and a route is NOT a venue-native stop.
    """
    if (type(enable_hypothetical_open_fill) is not bool
            or type(paper_demo_ignore_book_depth) is not bool):
        raise DataValidationError("D448 simulated fill opt-ins must be boolean")
    if not enable_hypothetical_open_fill:
        return _report("hypothetical_open_fill_optin_required")
    now = _utc_ms(as_of_ms, "D448 accounting timestamp")
    home = _private_directory(private_paper_directory)
    _plan_filename(intent_id)
    lock = _owner_locked(home)
    try:
        order_path, position_path = _paths(home)
        orders = SQLitePaperOrderJournal(order_path)
        entry = orders.load(intent_id)
        receipt = orders.read_margin_receipt(intent_id)
        if receipt is None:
            raise DataValidationError("D448 missing PRE11 receipt")
        planned = _read_plan(home, entry.intent, receipt)
        policy = _read_policy(planned["policy"])
        if entry.intent.effect is not PaperOrderEffect.OPEN:
            raise DataValidationError("D448 only OPEN can materialize")
        saved = entry
        wrote_fill = False
        if saved.snapshot.status in (
            PaperOrderStatus.PENDING, PaperOrderStatus.ACKNOWLEDGED,
        ):
            if saved.events:
                raise DataValidationError("D448 unexpected OPEN state requires reconciliation")
            # Expired PAPER openings must become terminal in the SAME AUTO2
            # journal. No phantom FILL, position or broker order.
            expired_at = (
                now if quote is None else quote.received_at_ms
            )
            if expired_at - entry.intent.created_at_ms > policy.max_fill_wait_ms:
                if quote is not None:
                    _checked_market(quote)
                    if quote.symbol != entry.intent.symbol:
                        raise DataValidationError("D448 quote conflicts with OPEN expiry")
                event = PaperOrderEvent(
                    _EXPIRE_PREFIX + sha256(intent_id.encode("ascii")).hexdigest()[:24],
                    PaperOrderEventKind.CANCELLED, expired_at,
                )
                # CANCELLED is never a fill: omit the health flag reserved
                # for guarded hypothetical OPEN FILLs. AUTO2 still enforces
                # monotonic timestamp, idempotency and status transitions.
                orders.append_events(
                    intent_id, (event,), as_of_ms=expired_at,
                )
                return _report("paper_open_expired_cancelled")
            if quote is None:
                return _report("await_post_latency_bbo")
            _checked_market(quote)
            if quote.symbol != entry.intent.symbol:
                raise DataValidationError("D448 quote symbol conflicts with OPEN")
            if (quote.exchange_at_ms < entry.intent.created_at_ms + policy.min_fill_latency_ms
                    or quote.received_at_ms < entry.intent.created_at_ms + policy.min_fill_latency_ms):
                return _report("await_post_latency_bbo")
            if (quote.received_at_ms - entry.intent.created_at_ms > policy.max_fill_wait_ms
                    or now - quote.received_at_ms > _MAX_TIME_AGE_MS
                    or now - quote.exchange_at_ms > _MAX_TIME_AGE_MS
                    or quote.received_at_ms > now):
                return _report("open_fill_window_or_quote_stale")
            with localcontext(_EXACT_CONTEXT):
                spread_bps = (
                    (quote.ask_price - quote.bid_price)
                    * BPS_DENOMINATOR / quote.mark_price
                )
                if spread_bps > policy.max_spread_bps:
                    return _report("paper_entry_spread_veto")
                depth = (quote.ask_size if entry.intent.position_side is SyntheticSide.LONG
                         else quote.bid_size)
                simulated_available = (
                    depth * policy.max_book_participation_bps / BPS_DENOMINATOR
                )
                if (not paper_demo_ignore_book_depth
                        and simulated_available < entry.intent.requested_units):
                    return _report("paper_entry_top_book_liquidity_veto")
                # D491: only a PAPER demo may assume unlimited matching depth;
                # all inputs still come from a real, fresh public quote.
                # The resulting FILL is HYPOTHETICAL, never a broker event.
            target_net, stop_buffer = _net_target_and_stop_buffer(
                planned, policy, quote, entry.intent.requested_units,
                receipt.requested_margin_quote,
            )
            if target_net <= 0:
                return _report("paper_entry_target_after_costs_veto")
            if stop_buffer <= 0:
                return _report("paper_entry_stop_margin_veto")
            # Full-fills only: the existing AUTO4 opening record has immutable
            # opening events, so no partial/final double registration is possible.
            token = sha256(_json([
                intent_id, quote.exchange_at_ms, quote.cross_sequence,
            ]).encode("ascii")).hexdigest()[:30]
            event = PaperOrderEvent(
                _FILL_PREFIX + token, PaperOrderEventKind.FILL,
                quote.received_at_ms, entry.intent.requested_units,
                hypothetical_reference_price_quote=(
                    quote.ask_price if entry.intent.position_side is SyntheticSide.LONG
                    else quote.bid_price
                ),
            )
            saved = orders.append_events(
                intent_id, (event,), as_of_ms=quote.received_at_ms,
                opening_paper_health_path=position_path,
            )
            wrote_fill = True
        if (saved.snapshot.status is not PaperOrderStatus.FILLED
                or len(saved.events) != 1
                or saved.events[0].kind is not PaperOrderEventKind.FILL
                or not saved.events[0].event_id.startswith(_FILL_PREFIX)
                or saved.events[0].filled_units != saved.intent.requested_units
                or saved.snapshot.filled_total_units != saved.intent.requested_units):
            raise DataValidationError("D448 unresolved or foreign OPEN; never infer fill")
        plan = SyntheticExitPlan(
            initial_units=saved.intent.requested_units,
            tranches=policy.tranches,
            residual_floor_percent=policy.runner_floor_percent,
        )
        # Existing AUTO4 is the SOLE position and exit ledger. It compares
        # original registration on replay without undoing later PAPER exits.
        positions = SQLitePaperPositionJournal(position_path)
        view = positions.create_position(
            position_id=planned["position_id"], opening_intent=saved.intent,
            opening_events=saved.events, exit_plan=plan,
            plan_version=planned["plan_version"],
            synthetic_lot_step_units=policy.synthetic_lot_step_units,
            as_of_ms=saved.events[0].event_at_ms,
            opening_order_path=order_path,
        )
        if (view.opening_intent_id != intent_id
                or view.leverage_at_intent != receipt.leverage_at_intent
                or view.requested_margin_quote != receipt.requested_margin_quote
                or view.plan_version != planned["plan_version"]):
            raise DataValidationError("D448 position receipt or plan does not match")
        _route_position(home, planned)
        return _report(
            "paper_position_routed_for_continuous_held_monitor",
            position_count=1, wrote_fill=wrote_fill,
        )
    finally:
        os.close(lock)
