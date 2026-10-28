"""J4/AUTO9: immutable PAPER intent-margin receipt, NOT a collateral ledger.

Canonical, bounded, locally SHA256-hashed evidence of a *synthetic* preflight.
Never authenticates the source, exchange rules, mark, cash or order execution.
A SHA256 of caller-owned bytes detects accidental corruption, not forgery.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext
from hashlib import sha256
import json
import re
from typing import Any

from .market_data import DataValidationError
from .paper_margin_preflight import (
    PaperMarginAssessment, PaperMarginReason, _FIXTURE_VERSION,
)
from .paper_risk_gate import PaperRiskReason, _quote
from .synthetic_manual_exit_replay import _EXACT_CONTEXT, _utc_ms
from .synthetic_order_lifecycle import PaperOrderEffect, PaperOrderIntent, PaperVenue

VERSION = "paper-margin-intent-v1"
META_PREFIX = VERSION + ":"
MAX_RECEIPT_BYTES = 4096
MAX_RECEIPTS_PER_JOURNAL = 4096
_HASH = re.compile(r"[0-9a-f]{64}")
_FIELDS = frozenset({
    "intent_id", "intent_sha256", "quote_currency",
    "leverage_at_intent", "requested_margin_quote", "requested_units_base",
    "hypothetical_mark_quote", "assumed_notional_quote",
    "contract_fixture_version", "assessed_at_ms",
})


def _canonical(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    )


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DataValidationError("duplicate PAPER margin receipt JSON key")
        result[key] = value
    return result


def _intent_digest(intent: PaperOrderIntent) -> str:
    # Same canonical bytes as AUTO2: a separate, divergent fingerprint
    # implementation could incorrectly attach a receipt to another intent.
    from .paper_order_store import _intent_json
    return sha256(_intent_json(intent).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PaperMarginIntentReceipt:
    """A preflight of the requested OPEN, never actual position collateral."""

    intent_id: str
    intent_sha256: str
    quote_currency: str
    leverage_at_intent: int
    requested_margin_quote: Decimal
    requested_units_base: Decimal
    hypothetical_mark_quote: Decimal
    assumed_notional_quote: Decimal
    contract_fixture_version: str
    assessed_at_ms: int

    def __post_init__(self) -> None:
        if (type(self.intent_id) is not str
                or not re.fullmatch(r"fixture_[A-Za-z0-9_-]{1,56}", self.intent_id)
                or type(self.intent_sha256) is not str
                or _HASH.fullmatch(self.intent_sha256) is None
                or type(self.quote_currency) is not str
                or self.quote_currency not in ("USDT", "USDC")
                or type(self.leverage_at_intent) is not int
                or not 1 <= self.leverage_at_intent <= 200
                or type(self.contract_fixture_version) is not str
                or _FIXTURE_VERSION.fullmatch(self.contract_fixture_version) is None):
            raise DataValidationError("invalid PAPER margin receipt identity/terms")
        _utc_ms(self.assessed_at_ms, "margin receipt assessed_at_ms")
        margin = _quote(self.requested_margin_quote, "receipt margin", allow_zero=False)
        units = _quote(self.requested_units_base, "receipt units", allow_zero=False)
        mark = _quote(self.hypothetical_mark_quote, "receipt mark", allow_zero=False)
        notion = _quote(self.assumed_notional_quote, "receipt notional", allow_zero=False)
        with localcontext(_EXACT_CONTEXT):
            if (margin * Decimal(self.leverage_at_intent) != notion
                    or units * mark != notion):
                raise DataValidationError("PAPER margin receipt fails exact arithmetic")

    @property
    def key(self) -> str:
        return META_PREFIX + self.intent_id

    @property
    def quality(self) -> str:
        return "synthetic_requested_margin_at_intent_only"

    @property
    def actual_venue_margin_verified(self) -> bool:
        return False

    @property
    def leverage_installed_on_exchange(self) -> bool:
        return False

    @property
    def position_collateral_verified(self) -> bool:
        return False

    @property
    def funding_liquidation_verified(self) -> bool:
        return False

    @property
    def live_trading_authorized(self) -> bool:
        return False

    @property
    def orders_sent(self) -> bool:
        return False

    @property
    def cross_file_atomic(self) -> bool:
        return False

    def verify_intent(self, intent: PaperOrderIntent) -> None:
        if (type(intent) is not PaperOrderIntent
                or intent.effect is not PaperOrderEffect.OPEN
                or intent.intent_id != self.intent_id
                or _intent_digest(intent) != self.intent_sha256
                or intent.requested_units.as_tuple()
                   != self.requested_units_base.as_tuple()
                or intent.created_at_ms != self.assessed_at_ms
                or not intent.symbol.endswith(self.quote_currency)
                or (intent.venue is PaperVenue.BINANCE_USDM
                    and self.quote_currency != "USDT")):
            raise DataValidationError("PAPER margin receipt not bound to exact OPEN intent")

    @classmethod
    def from_assessment(
        cls, intent: PaperOrderIntent, assessment: PaperMarginAssessment,
    ) -> "PaperMarginIntentReceipt":
        if (type(intent) is not PaperOrderIntent
                or type(assessment) is not PaperMarginAssessment
                or assessment.reason is not PaperMarginReason.FEASIBLE_PAPER_ONLY
                or not assessment.allowed_for_paper_research_only
                or assessment.risk_reason is not PaperRiskReason.OPEN_ALLOWED_PAPER_ONLY
                or assessment.actual_intent_notional_quote.as_tuple()
                   != assessment.assumed_notional_quote.as_tuple()):
            raise DataValidationError("non-admitted PAPER margin assessment cannot be persisted")
        receipt = cls(
            intent_id=intent.intent_id, intent_sha256=_intent_digest(intent),
            quote_currency=assessment.quote_currency,
            leverage_at_intent=assessment.leverage_captured_for_new_intent,
            requested_margin_quote=assessment.requested_margin_quote,
            requested_units_base=assessment.requested_units_base,
            hypothetical_mark_quote=assessment.assessed_mark_price_quote,
            assumed_notional_quote=assessment.assumed_notional_quote,
            contract_fixture_version=assessment.contract_fixture_version,
            assessed_at_ms=assessment.assessed_at_ms,
        )
        receipt.verify_intent(intent)
        return receipt

    def serialize(self) -> str:
        payload = {
            "intent_id": self.intent_id, "intent_sha256": self.intent_sha256,
            "quote_currency": self.quote_currency,
            "leverage_at_intent": self.leverage_at_intent,
            "requested_margin_quote": str(self.requested_margin_quote),
            "requested_units_base": str(self.requested_units_base),
            "hypothetical_mark_quote": str(self.hypothetical_mark_quote),
            "assumed_notional_quote": str(self.assumed_notional_quote),
            "contract_fixture_version": self.contract_fixture_version,
            "assessed_at_ms": self.assessed_at_ms,
        }
        digest = sha256(_canonical(payload).encode("utf-8")).hexdigest()
        raw = _canonical({
            "schema_version": VERSION, "payload": payload,
            "payload_sha256": digest,
        })
        if len(raw.encode("utf-8")) > MAX_RECEIPT_BYTES:
            raise DataValidationError("PAPER margin receipt exceeds byte limit")
        return raw

    @classmethod
    def deserialize(cls, raw: str) -> "PaperMarginIntentReceipt":
        if (type(raw) is not str or len(raw.encode("utf-8")) > MAX_RECEIPT_BYTES):
            raise DataValidationError("PAPER margin receipt missing or oversized")
        try:
            env = json.loads(
                raw, object_pairs_hook=_no_duplicates,
                parse_constant=lambda x: (_ for _ in ()).throw(
                    DataValidationError("PAPER margin receipt rejects nonfinite JSON")
                ),
            )
            if (type(env) is not dict
                    or set(env) != {"schema_version", "payload", "payload_sha256"}
                    or env["schema_version"] != VERSION
                    or type(env["payload"]) is not dict
                    or set(env["payload"]) != _FIELDS
                    or type(env["payload_sha256"]) is not str
                    or _HASH.fullmatch(env["payload_sha256"]) is None):
                raise DataValidationError("unknown PAPER margin receipt envelope")
            payload = env["payload"]
            if (any(type(payload[key]) is not str for key in (
                "intent_id", "intent_sha256", "quote_currency",
                "requested_margin_quote", "requested_units_base",
                "hypothetical_mark_quote", "assumed_notional_quote",
                "contract_fixture_version",
            )) or type(payload["leverage_at_intent"]) is not int
                    or type(payload["assessed_at_ms"]) is not int):
                raise DataValidationError("PAPER margin receipt types must be exact")
            if sha256(_canonical(payload).encode("utf-8")).hexdigest() != env["payload_sha256"]:
                raise DataValidationError("PAPER margin receipt checksum differs")
            value = cls(
                intent_id=payload["intent_id"],
                intent_sha256=payload["intent_sha256"],
                quote_currency=payload["quote_currency"],
                leverage_at_intent=payload["leverage_at_intent"],
                requested_margin_quote=Decimal(payload["requested_margin_quote"]),
                requested_units_base=Decimal(payload["requested_units_base"]),
                hypothetical_mark_quote=Decimal(payload["hypothetical_mark_quote"]),
                assumed_notional_quote=Decimal(payload["assumed_notional_quote"]),
                contract_fixture_version=payload["contract_fixture_version"],
                assessed_at_ms=payload["assessed_at_ms"],
            )
            if value.serialize() != raw:
                raise DataValidationError("noncanonical PAPER margin receipt")
            return value
        except (ValueError, TypeError, KeyError, ArithmeticError, OverflowError, UnicodeError) as exc:
            raise DataValidationError("invalid PAPER margin receipt") from exc
