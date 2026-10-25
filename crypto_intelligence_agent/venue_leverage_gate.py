"""Offline, fail-closed gate for research leverage versus venue notional tiers.

Important: Kraken contract leverage varies by instrument and aggregate USD
exposure. These schedules MUST be injected from an independently reviewed
point-in-time source; no current/real schedule is shipped in this module.

This gate is research-only. It does NOT trade, choose leverage automatically,
estimate maintenance/liquidation, or verify exchange/jurisdiction permissions.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import re
from typing import Any
from urllib.parse import urlsplit

from .market_data import DataValidationError


_SYMBOL = re.compile(r"^PF_[A-Z0-9]{2,40}$")
_VERSION = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")
_ALLOWED_VENUES = frozenset({"kraken_futures"})
_MAX_DIGITS = 35


def _strict_decimal(value: Any, name: str, *, allow_zero: bool) -> Decimal:
    """No implicit float conversion or ill-formed/astronomical decimals."""
    if isinstance(value, bool) or not isinstance(value, (Decimal, int)):
        raise DataValidationError(f"{name} must be Decimal or exact integer, never float")
    number = Decimal(value)
    if not number.is_finite() or number < 0 or (not allow_zero and number == 0):
        raise DataValidationError(f"{name} must be finite and {'nonnegative' if allow_zero else 'positive'}")
    if len(number.as_tuple().digits) > _MAX_DIGITS or number.adjusted() > 24:
        raise DataValidationError(f"{name} exceeds research precision/range budget")
    if number.as_tuple().exponent < -18:
        raise DataValidationError(f"{name} has excessive fractional precision")
    return number


def _safe_public_https_source(raw: str) -> str:
    if not isinstance(raw, str) or not 16 <= len(raw) <= 400:
        raise DataValidationError("venue leverage source must be a public HTTPS URL")
    try:
        p = urlsplit(raw)
        host = (p.hostname or "").lower()
        port = p.port
    except ValueError as exc:
        raise DataValidationError("venue leverage source URL is malformed") from exc
    if (p.scheme != "https" or not host or "." not in host
            or p.username is not None or p.password is not None or port is not None
            or p.query or p.fragment or "\\" in raw or "@" in p.netloc
            or any(char.isspace() for char in raw)
            or host in {"localhost", "127.0.0.1"} or host.endswith(".local")
            or host.replace(".", "").isdigit()):
        raise DataValidationError("venue leverage source URL is not an acceptable public HTTPS link")
    return raw


@dataclass(frozen=True)
class VenueNotionalTier:
    """[min_notional_usd, max_notional_usd), final max=None is unbounded."""

    min_notional_usd: Decimal
    max_notional_usd: Decimal | None
    maximum_leverage: Decimal

    def __post_init__(self) -> None:
        lower = _strict_decimal(self.min_notional_usd, "tier.min_notional_usd", allow_zero=True)
        upper = (None if self.max_notional_usd is None
                 else _strict_decimal(self.max_notional_usd, "tier.max_notional_usd", allow_zero=False))
        cap = _strict_decimal(self.maximum_leverage, "tier.maximum_leverage", allow_zero=False)
        if upper is not None and upper <= lower:
            raise DataValidationError("tier upper bound must exceed lower bound")
        if cap < 1:
            raise DataValidationError("tier max leverage must be at least 1x")
        object.__setattr__(self, "min_notional_usd", lower)
        object.__setattr__(self, "max_notional_usd", upper)
        object.__setattr__(self, "maximum_leverage", cap)


@dataclass(frozen=True)
class VenueLeverageSchedule:
    """Reviewed public schedule snapshot; provenance is CLAIMED not certified."""

    venue: str
    symbol: str
    quote_currency: str
    observed_at_ms: int
    source_url: str
    source_version: str
    tiers: tuple[VenueNotionalTier, ...]

    def __post_init__(self) -> None:
        if self.venue not in _ALLOWED_VENUES:
            raise DataValidationError("unknown venue; cannot apply Kraken tiers to another provider")
        if not isinstance(self.symbol, str) or _SYMBOL.fullmatch(self.symbol) is None:
            raise DataValidationError("invalid USD linear Kraken perpetual symbol")
        if self.quote_currency != "USD" or not self.symbol.endswith("USD"):
            raise DataValidationError("tier schedule is not for USD-quoted Kraken research")
        if type(self.observed_at_ms) is not int or self.observed_at_ms <= 0:
            raise DataValidationError("source observation must be positive integer UTC-ms")
        _safe_public_https_source(self.source_url)
        if not isinstance(self.source_version, str) or _VERSION.fullmatch(self.source_version) is None:
            raise DataValidationError("invalid/absent reviewed source version")
        if not isinstance(self.tiers, tuple) or len(self.tiers) < 1 or len(self.tiers) > 32:
            raise DataValidationError("tier schedule requires 1..32 brackets")
        if not all(isinstance(tier, VenueNotionalTier) for tier in self.tiers):
            raise DataValidationError("tier schedule has invalid rows")
        if self.tiers[0].min_notional_usd != 0:
            raise DataValidationError("notional tiers must start at zero")
        for previous, current in zip(self.tiers, self.tiers[1:]):
            if previous.max_notional_usd is None or previous.max_notional_usd != current.min_notional_usd:
                raise DataValidationError("tiers must be contiguous, nonoverlapping, ascending")
            if current.maximum_leverage > previous.maximum_leverage:
                raise DataValidationError("leverage caps cannot rise with larger notional")
        if self.tiers[-1].max_notional_usd is not None:
            raise DataValidationError("final notional tier must include all larger exposures")


@dataclass(frozen=True)
class NewPositionLeverageAssessment:
    """Advisory refusal/acceptance for NEW hypothetical position only."""

    allowed_for_research: bool
    reason: str
    requested_leverage: Decimal
    venue_cap_leverage: Decimal
    new_position_notional_usd: Decimal
    existing_symbol_exposure_usd: Decimal
    aggregate_exposure_usd: Decimal
    bracket_min_usd: Decimal
    bracket_max_usd_exclusive: Decimal | None
    source_version: str
    source_observed_at_ms: int
    symbol: str
    venue: str
    guaranteed_exchange_acceptance: bool = False
    adjusts_existing_positions: bool = False
    sends_orders: bool = False


def assess_new_research_position(
    *,
    schedule: VenueLeverageSchedule,
    requested_global_leverage: Decimal | int,
    new_position_notional_usd: Decimal | int,
    existing_symbol_exposure_usd: Decimal | int,
    decision_at_ms: int,
    max_schedule_age_ms: int,
) -> NewPositionLeverageAssessment:
    """Refuse impossible research configurations without silently capping 50x.

    Caller must independently establish instrument crypto identity, quote USD,
    official bracket provenance, current exposure and regional permissions.
    Leverage tier limits are NOT equivalent to exact maintenance or liquidation.
    """
    if not isinstance(schedule, VenueLeverageSchedule):
        raise DataValidationError("verified schedule snapshot is required")
    if type(decision_at_ms) is not int or decision_at_ms <= 0:
        raise DataValidationError("decision_at_ms must be integer UTC-ms")
    if type(max_schedule_age_ms) is not int or max_schedule_age_ms < 0:
        raise DataValidationError("max_schedule_age_ms must be nonnegative integer")
    if schedule.observed_at_ms > decision_at_ms:
        raise DataValidationError("cannot apply future leverage schedule retrospectively")
    if decision_at_ms - schedule.observed_at_ms > max_schedule_age_ms:
        raise DataValidationError("leverage schedule too old for the research decision")

    requested = _strict_decimal(requested_global_leverage, "requested_global_leverage", allow_zero=False)
    new_notional = _strict_decimal(new_position_notional_usd, "new_position_notional_usd", allow_zero=False)
    existing = _strict_decimal(existing_symbol_exposure_usd, "existing_symbol_exposure_usd", allow_zero=True)
    if requested < 1:
        raise DataValidationError("leverage less than 1x is outside this gate")
    aggregate = new_notional + existing
    _strict_decimal(aggregate, "aggregate_exposure_usd", allow_zero=False)
    selected = next((
        tier for tier in schedule.tiers
        if aggregate >= tier.min_notional_usd
        and (tier.max_notional_usd is None or aggregate < tier.max_notional_usd)
    ), None)
    if selected is None:
        raise DataValidationError("aggregate exposure is outside reviewed tier schedule")
    allowed = requested <= selected.maximum_leverage
    return NewPositionLeverageAssessment(
        allowed_for_research=allowed,
        reason=("within_reviewed_notional_tier"
                if allowed else "requested_leverage_exceeds_venue_tier"),
        requested_leverage=requested,
        venue_cap_leverage=selected.maximum_leverage,
        new_position_notional_usd=new_notional,
        existing_symbol_exposure_usd=existing,
        aggregate_exposure_usd=aggregate,
        bracket_min_usd=selected.min_notional_usd,
        bracket_max_usd_exclusive=selected.max_notional_usd,
        source_version=schedule.source_version,
        source_observed_at_ms=schedule.observed_at_ms,
        symbol=schedule.symbol,
        venue=schedule.venue,
    )
