"""J1/WU21: strictly offline, self-asserted evidence provenance checks.

A digest protects *claim bytes*, not an underlying source or its authenticity.
Neither a valid claim nor an asserted review approves live data, license,
identity, historical coverage, canonical OHLCV or a production release.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re
from typing import Any
from urllib.parse import urlsplit

from .market_data import DataValidationError
from .provider_usage_gate import Dataset, UsagePurpose

MAX_EVIDENCE_BYTES = 65_536
MAX_CLAIMS = 20
DEFAULT_MAX_AGE_MS = 30 * 86_400_000
_VERSION = re.compile(r"[A-Za-z0-9_.:-]{1,80}")
_REVIEWER = re.compile(r"[A-Za-z0-9_.-]{2,64}")
_HEX = re.compile(r"[0-9a-f]{64}")
_DNS_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
_PROVIDERS = frozenset({"kraken_futures", "bybit_v5", "binance_usdm", "okx_v5", "hyperliquid_native"})
_ORIGINS = frozenset({"synthetic_fixture", "documented_schema", "observed_summary"})
_ISSUE_BY_CAPABILITY = {
    "crypto_only_identity": 32,
    "kraken_candle_volume_units": 36,
    "provider_external_rights": 48,
    "binance_network_access": 19,
    "historical_coverage": 2,
    "closed_candle_parser": 34,
    "bybit_quote_currency": 50,
    "okx_quote_currency": 60,
    "hyperliquid_native_candle_schema": 69,
}
_CLAIM_KEYS = frozenset({
    "capability", "provider", "dataset", "purpose", "origin",
    "quote_currency", "source_url", "source_version", "reviewed_by",
    "observed_at_ms", "reviewed_at_ms", "valid_until_ms", "claim_sha256",
})


def _timestamp(value: Any, name: str) -> int:
    if type(value) is not int or value <= 0:
        raise DataValidationError(name + " must be positive UTC-ms integer")
    return value


def _public_source_url(value: Any) -> str:
    """Format check only; never request, trust or follow the URL."""
    if type(value) is not str or not 15 <= len(value) <= 300 or not value.isascii():
        raise DataValidationError("source_url must be bounded ASCII public HTTPS")
    try:
        parsed = urlsplit(value)
        hostname = (parsed.hostname or "").lower()
        port = parsed.port
    except ValueError as error:
        raise DataValidationError("invalid source_url") from error
    labels = hostname.split(".")
    if (parsed.scheme != "https" or len(labels) < 2
            or any(_DNS_LABEL.fullmatch(label) is None for label in labels)
            or len(labels[-1]) < 2 or hostname.endswith((".local", ".internal", ".localhost"))
            or parsed.username is not None or parsed.password is not None
            or port is not None or parsed.query or parsed.fragment
            or "@" in parsed.netloc or "%" in parsed.netloc or "\\" in value
            or any(c.isspace() for c in value)
            or hostname.replace(".", "").isdigit()):
        raise DataValidationError("source_url is not an uncredentialed public HTTPS reference")
    return value


# WU28: Distinct Kraken product families are NOT interchangeable.
# This list recognizes ONLY stable, official page paths with clear products.
# Everything else remains unverified, not implicitly an approved reference.
_KRAKEN_SUPPORT = "support.kraken.com"
_KRAKEN_DOCS = frozenset({"docs.kraken.com", "docs-legacy.kraken.com"})


def _known_kraken_product_surface(source_url: str) -> str:
    """Classify an official URL's *document scope*, NOT its content/rights.

    No fetching, redirects, reading remote metadata or vendor authentication.
    Host/path spoofing cannot grant an attestation: unknown stays unverified.
    """
    p = urlsplit(source_url)
    host = (p.hostname or "").lower()
    if host not in _KRAKEN_DOCS and host != _KRAKEN_SUPPORT:
        return "unknown_reference"
    # Do not let percent-encoded paths evade product-mismatch checks.
    if "%" in p.path:
        raise DataValidationError("ambiguous encoded Kraken source path")
    path = p.path.lower().rstrip("/")
    if host == _KRAKEN_SUPPORT:
        pieces = path.split("/")
        if "articles" not in pieces:
            return "unknown_reference"
        slug = pieces[-1]
        if slug in ("market-data", "contract-specifications"):
            return "kraken_derivatives_us_cme_bitnomial"
        if slug.startswith("360047124832-"):
            return "kraken_spot_ohlcvt"
        if slug.startswith("4844359082772-"):
            return "kraken_futures_perp_contract_specs"
    if host in _KRAKEN_DOCS:
        if path == "/api/docs/futures-api/charts/candles":
            return "kraken_futures_candle_chart_schema"
        if path == "/api/docs/guides/global-intro":
            return "kraken_api_usage_notices"
    return "unknown_reference"


def _source_applicability(
    *, capability: str, provider: str, dataset: Dataset,
    source_url: str, origin: str,
) -> str:
    """Reject known cross-product citations; never assert a positive grant.

    A valid HTTPS URL, even from Kraken itself, never proves crypto identity,
    futures candle volume unit, actual historical membership or redistribution.
    """
    surface = _known_kraken_product_surface(source_url)
    if surface == "unknown_reference":
        return "unknown_reference_requires_independent_review"
    if provider != "kraken_futures":
        raise DataValidationError("Kraken documentation cannot prove another provider scope")
    if surface in ("kraken_spot_ohlcvt", "kraken_derivatives_us_cme_bitnomial"):
        raise DataValidationError("Kraken source is a different product, not PF futures")
    if origin == "observed_summary":
        raise DataValidationError("a documentation page is not an observed market run")
    if surface == "kraken_futures_candle_chart_schema":
        if dataset is not Dataset.CANDLES:
            raise DataValidationError("Futures candle chart source is not an instrument or rights grant")
        if capability == "kraken_candle_volume_units":
            return "chart_volume_field_documented_unit_not_defined"
        if capability == "closed_candle_parser":
            return "candle_schema_only_not_live_conformance"
        raise DataValidationError("Kraken candle schema cannot certify this capability")
    if surface == "kraken_futures_perp_contract_specs":
        if capability == "crypto_only_identity" and dataset is Dataset.INSTRUMENTS:
            return "instrument_list_includes_non_crypto_no_positive_registry_proof"
        if capability == "kraken_candle_volume_units" and dataset is Dataset.CANDLES:
            return "current_contract_lot_not_historical_candle_volume_unit"
        raise DataValidationError("contract table does not support requested evidence scope")
    if surface == "kraken_api_usage_notices":
        if capability == "provider_external_rights":
            return "terms_notice_requires_permission_not_a_rights_grant"
        raise DataValidationError("Kraken API usage notice does not prove market schema")
    raise DataValidationError("unrecognized official source scope")


def canonical_claim_sha256(unsigned_claim: dict[str, Any]) -> str:
    """Hash only the unsigned JSON claim: integrity, NOT a vendor signature."""
    if type(unsigned_claim) is not dict or set(unsigned_claim) != (_CLAIM_KEYS - {"claim_sha256"}):
        raise DataValidationError("unsigned claim must contain exact schema fields")
    try:
        raw = json.dumps(unsigned_claim, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, RecursionError, UnicodeEncodeError) as error:
        raise DataValidationError("claim cannot be canonically serialized") from error
    if len(raw) > MAX_EVIDENCE_BYTES:
        raise DataValidationError("claim exceeds size limit")
    return sha256(raw).hexdigest()


def _validate_scope(
    capability: str, provider: str, dataset: Dataset, purpose: UsagePurpose,
    quote_currency: str,
) -> None:
    if capability not in _ISSUE_BY_CAPABILITY or provider not in _PROVIDERS:
        raise DataValidationError("unknown capability or provider")
    if dataset is Dataset.CANDLES:
        allowed_quote = (
            {"unverified"} if provider in ("kraken_futures", "hyperliquid_native") else {"USDT", "USDC"}
        )
        if quote_currency not in allowed_quote:
            raise DataValidationError("candle quote cannot be inferred or converted across providers")
    elif quote_currency != "not_applicable":
        raise DataValidationError("non-candle claim cannot assert a candle quote currency")

    if capability == "crypto_only_identity":
        valid = (provider == "kraken_futures" and dataset is Dataset.INSTRUMENTS
                 and purpose is UsagePurpose.INTERNAL_RESEARCH)
    elif capability in ("kraken_candle_volume_units", "closed_candle_parser"):
        valid = (provider == "kraken_futures" and dataset is Dataset.CANDLES
                 and purpose is UsagePurpose.INTERNAL_RESEARCH)
    elif capability == "bybit_quote_currency":
        valid = (provider == "bybit_v5" and dataset is Dataset.CANDLES
                 and purpose is UsagePurpose.INTERNAL_RESEARCH)
    elif capability == "okx_quote_currency":
        valid = (provider == "okx_v5" and dataset is Dataset.CANDLES
                 and purpose is UsagePurpose.INTERNAL_RESEARCH)
    elif capability == "hyperliquid_native_candle_schema":
        valid = (provider == "hyperliquid_native" and dataset is Dataset.CANDLES
                 and purpose is UsagePurpose.INTERNAL_RESEARCH)
    elif capability == "binance_network_access":
        valid = (provider == "binance_usdm" and dataset is Dataset.INSTRUMENTS
                 and purpose is UsagePurpose.INTERNAL_RESEARCH)
    elif capability == "historical_coverage":
        valid = (dataset is Dataset.CANDLES and purpose is UsagePurpose.INTERNAL_RESEARCH)
    else:  # provider_external_rights: all relevant datasets and external purposes
        valid = purpose in (
            UsagePurpose.PRIVATE_DASHBOARD, UsagePurpose.PUBLIC_DISPLAY,
            UsagePurpose.PUBLIC_API, UsagePurpose.COMMERCIAL,
        )
    if not valid:
        raise DataValidationError("claim provenance does not match capability/provider/dataset/purpose")


@dataclass(frozen=True)
class EvidenceClaim:
    capability: str
    provider: str
    dataset: Dataset
    purpose: UsagePurpose
    origin: str
    quote_currency: str
    source_url: str
    source_version: str
    reviewed_by: str
    observed_at_ms: int
    reviewed_at_ms: int
    valid_until_ms: int
    claim_sha256: str

    @classmethod
    def from_dict(
        cls, raw: Any, *, decision_at_ms: int, max_age_ms: int,
    ) -> "EvidenceClaim":
        if type(raw) is not dict or set(raw) != _CLAIM_KEYS:
            raise DataValidationError("claim fields differ from exact schema")
        capability, provider, origin = raw["capability"], raw["provider"], raw["origin"]
        dataset, purpose, quote = raw["dataset"], raw["purpose"], raw["quote_currency"]
        if (type(capability) is not str or type(provider) is not str
                or type(origin) is not str or origin not in _ORIGINS
                or type(dataset) is not str or type(purpose) is not str
                or type(quote) is not str):
            raise DataValidationError("claim scope and origin require exact string types")
        try:
            dataset_enum, purpose_enum = Dataset(dataset), UsagePurpose(purpose)
        except ValueError as error:
            raise DataValidationError("unknown dataset or purpose") from error
        _validate_scope(capability, provider, dataset_enum, purpose_enum, quote)
        source_url = _public_source_url(raw["source_url"])
        _source_applicability(
            capability=capability, provider=provider, dataset=dataset_enum,
            source_url=source_url, origin=origin,
        )
        version, reviewer = raw["source_version"], raw["reviewed_by"]
        if (type(version) is not str or _VERSION.fullmatch(version) is None
                or type(reviewer) is not str or _REVIEWER.fullmatch(reviewer) is None):
            raise DataValidationError("invalid source version or reviewer metadata")
        observed = _timestamp(raw["observed_at_ms"], "observed_at_ms")
        reviewed = _timestamp(raw["reviewed_at_ms"], "reviewed_at_ms")
        expires = _timestamp(raw["valid_until_ms"], "valid_until_ms")
        if not (observed <= reviewed <= decision_at_ms < expires and reviewed < expires):
            raise DataValidationError("future, expired or causally inconsistent evidence claim")
        if decision_at_ms - observed > max_age_ms:
            raise DataValidationError("stale evidence claim")
        actual = raw["claim_sha256"]
        if type(actual) is not str or _HEX.fullmatch(actual) is None:
            raise DataValidationError("invalid claim SHA256")
        expected = canonical_claim_sha256({k: v for k, v in raw.items() if k != "claim_sha256"})
        if actual != expected:
            raise DataValidationError("claim bytes changed after digest generation")
        return cls(
            capability, provider, dataset_enum, purpose_enum, origin, quote, source_url,
            version, reviewer, observed, reviewed, expires, actual,
        )


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    d: dict[str, Any] = {}
    for key, value in pairs:
        if key in d:
            raise DataValidationError("duplicate evidence JSON keys are forbidden")
        d[key] = value
    return d


def _bad_constant(value: str) -> None:
    raise DataValidationError("nonfinite evidence JSON number is forbidden")


def _bad_float(value: str) -> None:
    raise DataValidationError("fractional evidence JSON number is forbidden")


def audit_evidence_json(
    raw_json: str | bytes, *, decision_at_ms: int,
    max_age_ms: int = DEFAULT_MAX_AGE_MS,
) -> dict[str, Any]:
    """Inspect asserted provenance; never authenticate it or approve readiness."""
    moment = _timestamp(decision_at_ms, "decision_at_ms")
    if type(max_age_ms) is not int or not 0 <= max_age_ms <= 365 * 86_400_000:
        raise DataValidationError("max_age_ms must be bounded nonnegative integer")
    if type(raw_json) not in (str, bytes):
        raise DataValidationError("evidence JSON must be UTF-8 text or bytes")
    try:
        content = raw_json.encode("utf-8") if type(raw_json) is str else raw_json
    except UnicodeEncodeError as error:
        raise DataValidationError("invalid UTF-8 evidence JSON") from error
    if not 1 <= len(content) <= MAX_EVIDENCE_BYTES:
        raise DataValidationError("evidence JSON is empty or oversized")
    try:
        data = json.loads(content, object_pairs_hook=_unique_object,
                          parse_constant=_bad_constant, parse_float=_bad_float)
    except (UnicodeDecodeError, ValueError, RecursionError) as error:
        raise DataValidationError("malformed evidence JSON") from error
    if (type(data) is not dict or set(data) != {"schema_version", "claims"}
            or type(data["schema_version"]) is not int or data["schema_version"] != 1
            or type(data["claims"]) is not list or len(data["claims"]) > MAX_CLAIMS):
        raise DataValidationError("unknown or oversized evidence claim envelope")
    claims = tuple(
        EvidenceClaim.from_dict(item, decision_at_ms=moment, max_age_ms=max_age_ms)
        for item in data["claims"]
    )
    scopes = [(c.capability, c.provider, c.dataset, c.purpose, c.quote_currency) for c in claims]
    if len(set(scopes)) != len(scopes):
        raise DataValidationError("conflicting or replayed evidence scope")
    rows = [
        {
            "capability": c.capability, "provider": c.provider,
            "dataset": c.dataset.value, "purpose": c.purpose.value,
            "origin": c.origin, "quote_currency": c.quote_currency,
            "source_url": c.source_url, "source_version": c.source_version,
            "observed_at_ms": c.observed_at_ms, "reviewed_at_ms": c.reviewed_at_ms,
            "valid_until_ms": c.valid_until_ms, "claim_sha256": c.claim_sha256,
            "issue": _ISSUE_BY_CAPABILITY[c.capability],
            "verification": "metadata_valid_only_not_authenticated",
            "source_applicability": _source_applicability(
                capability=c.capability, provider=c.provider, dataset=c.dataset,
                source_url=c.source_url, origin=c.origin,
            ),
        }
        for c in sorted(claims, key=lambda c: (c.capability, c.provider, c.dataset.value, c.claim_sha256))
    ]
    return {
        "schema_version": "j1-evidence-audit-v1",
        "status": "no_claims" if not rows else "unverified_claims_for_manual_review",
        "claim_count": len(rows),
        "claims": rows,
        "independent_source_verified": False,
        "live_evidence_authenticated": False,
        "external_rights_authorized": False,
    }
