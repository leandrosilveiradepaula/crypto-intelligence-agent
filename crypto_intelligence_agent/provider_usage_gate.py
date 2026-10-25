"""Conservative, offline provider-data *usage purpose* gate (J1/WU19).

This is not legal advice, a license-verification service, or a publishing API.
It cannot prove authenticity of evidence: a release human gate must validate
the actual grant and coverage before any external/commercial use.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from urllib.parse import urlsplit

from .market_data import DataValidationError


class UsagePurpose(str, Enum):
    INTERNAL_RESEARCH = "internal_research"
    PRIVATE_DASHBOARD = "private_dashboard"
    PUBLIC_DISPLAY = "public_display"
    PUBLIC_API = "public_api"
    COMMERCIAL = "commercial"


class Dataset(str, Enum):
    INSTRUMENTS = "instruments"
    CANDLES = "candles"
    TICKERS = "tickers"
    FUNDING = "funding"
    DERIVED_ALERTS = "derived_alerts"


_PROVIDERS = frozenset({"kraken_futures", "bybit_v5", "binance_usdm", "okx_v5", "hyperliquid_native"})
_VERSION = re.compile(r"[A-Za-z0-9_.:-]{1,80}")
_REVIEWER = re.compile(r"[A-Za-z0-9_.-]{2,64}")
_MAX_GRANTS = 20


def _uri(value: str) -> str:
    if not isinstance(value, str) or len(value) > 400 or len(value) < 16:
        raise DataValidationError("rights evidence requires bounded public HTTPS URL")
    try:
        p = urlsplit(value)
        host, port = (p.hostname or "").lower(), p.port
    except ValueError as exc:
        raise DataValidationError("invalid rights evidence URL") from exc
    if (p.scheme != "https" or "." not in host or p.username is not None
            or p.password is not None or port is not None or p.query or p.fragment
            or "@" in p.netloc or "\\" in value or any(c.isspace() for c in value)
            or host in {"localhost", "127.0.0.1"} or host.endswith(".local")
            or host.replace(".", "").isdigit()):
        raise DataValidationError("rights evidence URL is not an uncredentialed public HTTPS URL")
    return value


def _timestamp(value: int, name: str) -> int:
    if type(value) is not int or value <= 0:
        raise DataValidationError(f"{name} requires positive integer UTC-ms")
    return value


@dataclass(frozen=True)
class RightsGrantEvidence:
    """User-supplied assertion, NOT a verified legal authorization."""

    provider: str
    dataset: Dataset
    permitted_purpose: UsagePurpose
    reviewed_at_ms: int
    valid_until_ms: int
    evidence_url: str
    evidence_version: str
    reviewed_by: str
    grant_confirmed: bool

    def __post_init__(self) -> None:
        if self.provider not in _PROVIDERS or type(self.provider) is not str:
            raise DataValidationError("unknown market-data provider")
        if type(self.dataset) is not Dataset or type(self.permitted_purpose) is not UsagePurpose:
            raise DataValidationError("dataset and purpose must use explicit enums")
        reviewed = _timestamp(self.reviewed_at_ms, "reviewed_at_ms")
        expires = _timestamp(self.valid_until_ms, "valid_until_ms")
        if expires <= reviewed:
            raise DataValidationError("rights evidence expires before or at review")
        _uri(self.evidence_url)
        if (not isinstance(self.evidence_version, str)
                or _VERSION.fullmatch(self.evidence_version) is None):
            raise DataValidationError("rights evidence requires explicit version")
        if (not isinstance(self.reviewed_by, str)
                or _REVIEWER.fullmatch(self.reviewed_by) is None):
            raise DataValidationError("rights evidence requires explicit reviewer")
        if type(self.grant_confirmed) is not bool:
            raise DataValidationError("grant_confirmed must be explicit boolean")


@dataclass(frozen=True)
class UsageGateDecision:
    purpose: UsagePurpose
    dataset: Dataset
    provider: str
    allowed: bool
    reason: str
    review_version: str | None
    evidence_is_authentic: bool = False
    publishes_data: bool = False
    releases_to_production: bool = False


def assess_provider_usage(
    *,
    provider: str,
    dataset: Dataset,
    purpose: UsagePurpose,
    decision_at_ms: int,
    grants: tuple[RightsGrantEvidence, ...] = (),
    externally_reviewed_release_gate: bool = False,
) -> UsageGateDecision:
    """Fail closed: no API/public/commercial release from an asserted grant.

    Even a syntactically valid, claimant-asserted grant cannot turn on
    external distribution. A *separate*, audited production release process
    must verify the actual permission, applicable territory, user and scope.
    This function only identifies eligibility for further review.
    """
    if type(provider) is not str or provider not in _PROVIDERS:
        raise DataValidationError("unknown market-data provider")
    if type(dataset) is not Dataset or type(purpose) is not UsagePurpose:
        raise DataValidationError("dataset and purpose must be explicit enum types")
    moment = _timestamp(decision_at_ms, "decision_at_ms")
    if type(grants) is not tuple or len(grants) > _MAX_GRANTS:
        raise DataValidationError("rights grants must be a bounded immutable tuple")
    if not all(isinstance(grant, RightsGrantEvidence) for grant in grants):
        raise DataValidationError("rights grant contains invalid record")
    if type(externally_reviewed_release_gate) is not bool:
        raise DataValidationError("release gate must be boolean")
    # A Boolean flag is not a real production release capability; never
    # authorize distribution via this research-only gate.
    if purpose is UsagePurpose.INTERNAL_RESEARCH:
        return UsageGateDecision(
            purpose, dataset, provider, False,
            "internal_research_subject_to_current_terms_review", None,
        )
    matching = [
        grant for grant in grants
        if grant.provider == provider and grant.dataset is dataset
        and grant.permitted_purpose is purpose
        and grant.reviewed_at_ms <= moment < grant.valid_until_ms
        and grant.grant_confirmed is True
    ]
    if not matching:
        reason = "no_current_scope_specific_verified_rights_claim"
        version = None
    else:
        reason = "license_claim_requires_external_verification_and_release_gate"
        version = sorted(matching, key=lambda grant: grant.reviewed_at_ms)[-1].evidence_version
    # The flag intentionally does NOT release; it is not an authenticated
    # attestation, a permission token, or a human approval.
    return UsageGateDecision(purpose, dataset, provider, False, reason, version)
