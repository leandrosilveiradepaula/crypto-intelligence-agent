"""Immutable, offline-only crypto-asset identity registry for research (J1/WU10).

An integrity hash is NOT an authenticity signature. Two distinct public identity
references and explicit review metadata are necessary but NOT sufficient to
prove an asset is crypto; a human review of the sources remains required.
No registry is shipped as "approved", and no remote service is called here.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit

from .kraken_eligibility import select_kraken_research_universe
from .market_data import DataValidationError, UniverseSnapshot


_BASE = re.compile(r"^[A-Z0-9]{2,24}$")
_IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9._:-]{1,79}$")
_REVIEWER = re.compile(r"^[A-Za-z0-9_.-]{2,64}$")
_HASH = re.compile(r"^[0-9a-f]{64}$")
_LABEL = re.compile(r"^[A-Za-z0-9_.-]{1,60}$")
MAX_ASSETS = 2000
MAX_MANIFEST_BYTES = 1_000_000
SOURCE_POLICY = "internal_research_only"


def _positive_utc_ms(value: Any, name: str) -> int:
    if type(value) is not int or value <= 0:
        raise DataValidationError(f"{name} must be a positive integer UTC-ms timestamp")
    return value


def _exact_fields(raw: Any, names: frozenset[str], label: str) -> Mapping[str, Any]:
    if not isinstance(raw, dict) or set(raw) != names:
        raise DataValidationError(f"{label} must contain exactly the approved fields")
    return raw


def _approved_https_uri(raw: Any) -> tuple[str, str]:
    if not isinstance(raw, str) or not 12 <= len(raw) <= 300:
        raise DataValidationError("identity evidence must be a short public HTTPS URL")
    try:
        parsed = urlsplit(raw)
        hostname = (parsed.hostname or "").lower()
        port = parsed.port
    except ValueError as error:
        raise DataValidationError("invalid evidence URL") from error
    if (parsed.scheme != "https" or not hostname or "." not in hostname
            or parsed.username is not None or parsed.password is not None
            or port is not None or parsed.query or parsed.fragment
            or "\\" in raw or "@" in parsed.netloc
            or any(c.isspace() for c in raw)):
        raise DataValidationError("identity evidence must be an uncredentialed public HTTPS URL")
    if (hostname in ("localhost", "127.0.0.1") or hostname.endswith(".local")
            or hostname.replace(".", "").isdigit() or hostname.endswith(".kraken.com")
            or hostname == "kraken.com"):
        raise DataValidationError("identity proof cannot use private hosts or Kraken itself")
    # Conservative publisher grouping: *.example.com counts as one publisher.
    # This may collapse unrelated co.uk hostnames, safely failing closed.
    publisher_root = ".".join(hostname.removeprefix("www.").split(".")[-2:])
    return raw, publisher_root


@dataclass(frozen=True)
class IdentityEvidence:
    publisher: str
    asset_ref: str
    url: str
    observed_at_ms: int
    publisher_root: str

    @classmethod
    def from_dict(cls, raw: Any) -> "IdentityEvidence":
        d = _exact_fields(raw, frozenset({
            "publisher", "asset_ref", "url", "observed_at_ms",
        }), "identity evidence")
        publisher, ref = d["publisher"], d["asset_ref"]
        if (not isinstance(publisher, str) or not _IDENTIFIER.fullmatch(publisher)
                or not isinstance(ref, str) or not _IDENTIFIER.fullmatch(ref)):
            raise DataValidationError("evidence publisher and asset_ref must be explicit IDs")
        url, publisher_root = _approved_https_uri(d["url"])
        observed = _positive_utc_ms(d["observed_at_ms"], "evidence.observed_at_ms")
        return cls(publisher, ref, url, observed, publisher_root)


@dataclass(frozen=True)
class VerifiedAsset:
    base: str
    canonical_id: str
    reviewed_by: str
    reviewed_at_ms: int
    evidence: tuple[IdentityEvidence, ...]

    @classmethod
    def from_dict(cls, raw: Any, *, registry_observed_at_ms: int) -> "VerifiedAsset":
        d = _exact_fields(raw, frozenset({
            "base", "canonical_id", "reviewed_by", "reviewed_at_ms", "evidence",
        }), "verified asset")
        base, asset_id, reviewer = d["base"], d["canonical_id"], d["reviewed_by"]
        if not isinstance(base, str) or not _BASE.fullmatch(base):
            raise DataValidationError("asset base must be uppercase normalized")
        if not isinstance(asset_id, str) or not _IDENTIFIER.fullmatch(asset_id):
            raise DataValidationError("canonical asset ID is missing or malformed")
        if not isinstance(reviewer, str) or not _REVIEWER.fullmatch(reviewer):
            raise DataValidationError("asset must specify its reviewer")
        reviewed = _positive_utc_ms(d["reviewed_at_ms"], "asset.reviewed_at_ms")
        if reviewed > registry_observed_at_ms:
            raise DataValidationError("review cannot happen after registry capture")
        raw_evidence = d["evidence"]
        if not isinstance(raw_evidence, list) or not 2 <= len(raw_evidence) <= 6:
            raise DataValidationError("each asset requires 2-6 independent identity references")
        evidence = tuple(IdentityEvidence.from_dict(item) for item in raw_evidence)
        if (len({e.publisher for e in evidence}) != len(evidence)
                or len({e.publisher_root for e in evidence}) != len(evidence)
                or any(e.observed_at_ms > reviewed for e in evidence)):
            raise DataValidationError("identity references must be independent and known by review time")
        return cls(base, asset_id, reviewer, reviewed, evidence)


def registry_sha256(unsigned_manifest: Mapping[str, Any]) -> str:
    """Deterministic payload integrity digest; not a signature or rights grant."""
    if not isinstance(unsigned_manifest, dict) or "sha256" in unsigned_manifest:
        raise DataValidationError("digest input must be an unsigned registry manifest")
    try:
        encoded = json.dumps(
            unsigned_manifest, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False,
        ).encode("utf-8")
    except (ValueError, TypeError, RecursionError) as error:
        raise DataValidationError("manifest is not canonical JSON") from error
    if len(encoded) > MAX_MANIFEST_BYTES:
        raise DataValidationError("registry manifest exceeds allowed byte size")
    return sha256(encoded).hexdigest()


@dataclass(frozen=True)
class CryptoRegistrySnapshot:
    observed_at_ms: int
    label: str
    sha256_digest: str
    assets: tuple[VerifiedAsset, ...]

    @property
    def verified_crypto_bases(self) -> frozenset[str]:
        return frozenset(asset.base for asset in self.assets)

    @property
    def selector_version(self) -> str:
        return "sha256-" + self.sha256_digest

    @classmethod
    def from_manifest(cls, payload: Any) -> "CryptoRegistrySnapshot":
        raw = _exact_fields(payload, frozenset({
            "schema_version", "observed_at_ms", "label", "usage_policy",
            "assets", "sha256",
        }), "registry manifest")
        if type(raw["schema_version"]) is not int or raw["schema_version"] != 1:
            raise DataValidationError("unknown registry schema version")
        if raw["usage_policy"] != SOURCE_POLICY:
            raise DataValidationError("registry must remain internal research only")
        observed = _positive_utc_ms(raw["observed_at_ms"], "registry.observed_at_ms")
        label = raw["label"]
        if not isinstance(label, str) or not _LABEL.fullmatch(label):
            raise DataValidationError("registry label is invalid")
        assets = raw["assets"]
        if not isinstance(assets, list) or not 1 <= len(assets) <= MAX_ASSETS:
            raise DataValidationError("registry must contain 1-2000 reviewed assets")
        actual_sha = raw["sha256"]
        if not isinstance(actual_sha, str) or not _HASH.fullmatch(actual_sha):
            raise DataValidationError("registry SHA256 must contain 64 lowercase hex characters")
        expected_sha = registry_sha256({k: v for k, v in raw.items() if k != "sha256"})
        if actual_sha != expected_sha:
            raise DataValidationError("registry content hash mismatch (no silent edits)")
        rows = tuple(VerifiedAsset.from_dict(row, registry_observed_at_ms=observed) for row in assets)
        if (len({row.base for row in rows}) != len(rows)
                or len({row.canonical_id for row in rows}) != len(rows)):
            raise DataValidationError("ambiguous base symbols or canonical asset identities")
        return cls(observed, label, actual_sha, rows)


def load_registry_json(raw_json: str | bytes) -> CryptoRegistrySnapshot:
    """Parse a bounded local JSON manifest. No network, disk or account access."""
    if not isinstance(raw_json, (str, bytes)) or len(raw_json) > MAX_MANIFEST_BYTES:
        raise DataValidationError("registry input is missing or too large")
    try:
        def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            result: dict[str, Any] = {}
            for key, value in pairs:
                if key in result:
                    raise DataValidationError("duplicate registry JSON keys are forbidden")
                result[key] = value
            return result

        payload = json.loads(raw_json, object_pairs_hook=reject_duplicate_keys,
                             parse_constant=lambda x: (_ for _ in ()).throw(
                                 DataValidationError("non-finite JSON numbers forbidden")
                             ))
    except (ValueError, UnicodeDecodeError, RecursionError) as error:
        raise DataValidationError("malformed registry JSON") from error
    return CryptoRegistrySnapshot.from_manifest(payload)


def _revalidate_snapshot_for_history(snapshot: CryptoRegistrySnapshot) -> None:
    """Reject direct dataclass instances that bypassed manifest validation.

    Rebuild the *same* v1 manifest from immutable records and run the single
    existing from_manifest validator. Equality also detects falsified derived
    publisher_root fields that were not stored in the hashed JSON. This is
    integrity checking ONLY, not independent source authentication.
    """
    if (type(snapshot) is not CryptoRegistrySnapshot
            or type(snapshot.assets) is not tuple
            or not 1 <= len(snapshot.assets) <= MAX_ASSETS):
        raise DataValidationError("history requires a validated immutable crypto registry snapshot")
    records: list[dict[str, Any]] = []
    for asset in snapshot.assets:
        if (type(asset) is not VerifiedAsset or type(asset.evidence) is not tuple
                or not 2 <= len(asset.evidence) <= 6
                or any(type(item) is not IdentityEvidence for item in asset.evidence)):
            raise DataValidationError("registry snapshot contains unvalidated identity record")
        records.append({
            "base": asset.base, "canonical_id": asset.canonical_id,
            "reviewed_by": asset.reviewed_by,
            "reviewed_at_ms": asset.reviewed_at_ms,
            "evidence": [
                {
                    "publisher": item.publisher, "asset_ref": item.asset_ref,
                    "url": item.url, "observed_at_ms": item.observed_at_ms,
                }
                for item in asset.evidence
            ],
        })
    # No extra 'verified' flag can substitute a content hash. Use exactly the
    # versioned schema already accepted by load_registry_json / from_manifest.
    canonical = CryptoRegistrySnapshot.from_manifest({
        "schema_version": 1,
        "observed_at_ms": snapshot.observed_at_ms,
        "label": snapshot.label,
        "usage_policy": SOURCE_POLICY,
        "assets": records,
        "sha256": snapshot.sha256_digest,
    })
    if canonical != snapshot:
        raise DataValidationError("registry snapshot differs from canonical validated evidence")


class CryptoRegistryHistory:
    """Append-only observed snapshots. No retrospective identity injection."""

    def __init__(self, snapshots: Sequence[CryptoRegistrySnapshot] = ()) -> None:
        self._snapshots: list[CryptoRegistrySnapshot] = []
        for snapshot in snapshots:
            self.append(snapshot)

    def append(self, snapshot: CryptoRegistrySnapshot) -> None:
        # A public dataclass constructor must not bypass mandatory manifest
        # SHA/evidence checks before a snapshot becomes historical truth.
        _revalidate_snapshot_for_history(snapshot)
        if self._snapshots:
            previous = self._snapshots[-1]
            if snapshot.observed_at_ms < previous.observed_at_ms:
                raise DataValidationError("registry observations must be append-only")
            if snapshot.observed_at_ms == previous.observed_at_ms:
                if snapshot != previous:
                    raise DataValidationError("conflicting registry snapshot at same observed time")
                return
            if any(item.label == snapshot.label for item in self._snapshots):
                raise DataValidationError("immutable registry label cannot be reused in later history")
        self._snapshots.append(snapshot)

    def as_of(self, market_observed_at_ms: int, *, max_age_ms: int) -> CryptoRegistrySnapshot:
        observed = _positive_utc_ms(market_observed_at_ms, "market_observed_at_ms")
        if type(max_age_ms) is not int or max_age_ms < 0:
            raise ValueError("max_age_ms must be a nonnegative integer")
        for snapshot in reversed(self._snapshots):
            if snapshot.observed_at_ms <= observed:
                if observed - snapshot.observed_at_ms > max_age_ms:
                    raise DataValidationError("known crypto registry is too old for the market sample")
                return snapshot
        raise DataValidationError("no reviewed crypto registry existed at market observation time")

    def select_at(
        self, *,
        instruments: Sequence[Mapping[str, Any]],
        tickers: Sequence[Mapping[str, Any]],
        market_observed_at_ms: int,
        decision_at_ms: int,
        max_market_age_ms: int,
        max_registry_age_ms: int,
        max_symbols: int = 50,
    ) -> UniverseSnapshot:
        """Use a registry known by the MARKET observation, never a later one.

        Source timestamps are caller-supplied and must originate from
        authenticated collection audit. This cannot prove their authenticity.
        """
        market_time = _positive_utc_ms(market_observed_at_ms, "market_observed_at_ms")
        decision_time = _positive_utc_ms(decision_at_ms, "decision_at_ms")
        if type(max_market_age_ms) is not int or max_market_age_ms < 0:
            raise ValueError("max_market_age_ms must be a nonnegative integer")
        if market_time > decision_time:
            raise DataValidationError("future market observation cannot inform an earlier decision")
        if decision_time - market_time > max_market_age_ms:
            raise DataValidationError("market observation is stale at the decision time")
        registry = self.as_of(market_time, max_age_ms=max_registry_age_ms)
        return select_kraken_research_universe(
            instruments=instruments, tickers=tickers,
            observed_at_ms=market_time,
            verified_crypto_bases=registry.verified_crypto_bases,
            registry_version=registry.selector_version,
            max_symbols=max_symbols,
        )
