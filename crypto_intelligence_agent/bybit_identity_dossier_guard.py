"""D266: offline Bybit identity dossier checks, never identity certification.

A SHA-256, venue-symbol string or independent-looking references cannot
authenticate a provider, attest a token mint, reconstruct historical PIT,
classify the 822-instrument universe, or authorize any orders.
"""
from __future__ import annotations

from hashlib import sha256
import json
import re
from typing import Any

from .bybit_tradfi_negative_evidence import NEGATIVE_EVIDENCE
from .bybit_identity_crosswalk_research import research_category
from .crypto_asset_registry import _approved_https_uri
from .market_data import DataValidationError

SCHEMA = "j1-bybit-identity-dossier-d266-v1"
MAX_BYTES = 12_000
_SYMBOL = re.compile(r"[A-Z0-9]{1,28}USDT\Z")
_REF = re.compile(r"[a-z0-9][a-z0-9._:-]{1,79}\Z")
_MINT = re.compile(r"[A-Za-z0-9:._-]{8,160}\Z")
_REVIEWER = re.compile(r"[A-Za-z0-9_.-]{2,64}\Z")
_CLASSES = frozenset({"crypto_token", "tradfi", "tokenized_commodity", "unknown"})
_REQUIRED = frozenset({
    "schema_version", "venue_symbol", "canonical_asset_id",
    "asset_class", "venue_contract_id", "network_contract_id",
    "observed_at_ms", "valid_from_ms", "valid_to_ms",
    "reviewed_by", "reviewed_at_ms", "evidence", "sha256",
})
_EVIDENCE_FIELDS = frozenset({
    "publisher", "asset_ref", "url", "observed_at_ms",
})


class DossierRejected(ValueError):
    """Fail closed; never includes source payload or symbol in the message."""


def _canonical(record: Any) -> bytes:
    try:
        data = json.dumps(record, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError, RecursionError):
        raise DossierRejected("dossier_json_invalid") from None
    if len(data) > MAX_BYTES:
        raise DossierRejected("dossier_too_large")
    return data


def dossier_digest(unsigned: dict) -> str:
    if type(unsigned) is not dict or "sha256" in unsigned:
        raise DossierRejected("dossier_unsigned_invalid")
    return sha256(_canonical(unsigned)).hexdigest()


def _timestamp(value: Any) -> bool:
    return type(value) is int and 1_600_000_000_000 <= value <= 4_102_444_800_000


def _validate(d: Any) -> tuple[str, bool]:
    if type(d) is not dict or set(d) != _REQUIRED:
        raise DossierRejected("dossier_fields_invalid")
    if (d["schema_version"] != SCHEMA
            or type(d["venue_symbol"]) is not str
            or _SYMBOL.fullmatch(d["venue_symbol"]) is None
            or type(d["asset_class"]) is not str
            or d["asset_class"] not in _CLASSES):
        raise DossierRejected("dossier_identity_fields_invalid")
    ref, venue, mint, reviewer = (
        d["canonical_asset_id"], d["venue_contract_id"],
        d["network_contract_id"], d["reviewed_by"],
    )
    if (type(ref) is not str or _REF.fullmatch(ref) is None
            or type(venue) is not str or _REF.fullmatch(venue) is None
            or type(mint) is not str or (mint and _MINT.fullmatch(mint) is None)
            or type(reviewer) is not str or _REVIEWER.fullmatch(reviewer) is None):
        raise DossierRejected("dossier_proposed_contract_invalid")
    times = [d["observed_at_ms"], d["valid_from_ms"], d["reviewed_at_ms"]]
    until = d["valid_to_ms"]
    if (not all(_timestamp(t) for t in times)
            or (until is not None and not _timestamp(until))
            or times[1] > times[0] or times[0] > times[2]
            or (until is not None and until < times[1])):
        raise DossierRejected("dossier_time_invalid")
    evidence = d["evidence"]
    if type(evidence) is not list or not 1 <= len(evidence) <= 6:
        raise DossierRejected("dossier_evidence_count_invalid")
    publishers: set[str] = set()
    roots: set[str] = set()
    for row in evidence:
        if type(row) is not dict or set(row) != _EVIDENCE_FIELDS:
            raise DossierRejected("dossier_evidence_fields_invalid")
        pub, evref, ts = row["publisher"], row["asset_ref"], row["observed_at_ms"]
        if (type(pub) is not str or _REF.fullmatch(pub) is None
                or type(evref) is not str or _REF.fullmatch(evref) is None
                or not _timestamp(ts) or ts > times[2]):
            raise DossierRejected("dossier_evidence_invalid")
        try:
            _url, root = _approved_https_uri(row["url"])
        except (ValueError, DataValidationError):
            raise DossierRejected("dossier_evidence_url_invalid") from None
        if pub in publishers or root in roots:
            raise DossierRejected("dossier_source_not_independent")
        publishers.add(pub)
        roots.add(root)
    h = d["sha256"]
    if type(h) is not str or len(h) != 64 or any(c not in "0123456789abcdef" for c in h):
        raise DossierRejected("dossier_digest_invalid")
    unsigned = {k: v for k, v in d.items() if k != "sha256"}
    if dossier_digest(unsigned) != h:
        raise DossierRejected("dossier_integrity_mismatch")
    return d["venue_symbol"], len(roots) >= 2


def evaluate_dossier(raw: bytes | str | dict, *,
                     decision_at_ms: int,
                     current_provider_negative: bool = False) -> dict[str, Any]:
    """Return research gate only. Every result is explicitly not approved."""
    result: dict[str, Any] = {
        "schema_version": SCHEMA,
        "status": "abstain",
        "identity_approved": False,
        "eligible_top50": False,
        "marketwide_top50_verified": False,
        "orders_sent": False,
        "network_accessed": False,
        "database_modified": False,
    }
    if not _timestamp(decision_at_ms) or type(current_provider_negative) is not bool:
        result["reason"] = "decision_or_provider_gate_invalid"
        return result
    try:
        if isinstance(raw, (str, bytes)):
            if len(raw) > MAX_BYTES:
                raise DossierRejected("dossier_too_large")
            def unique_pairs(pairs):
                obj = {}
                for k, v in pairs:
                    if k in obj:
                        raise DossierRejected("dossier_duplicate_json_keys")
                    obj[k] = v
                return obj
            try:
                raw = json.loads(raw, object_pairs_hook=unique_pairs,
                                 parse_constant=lambda _: (_ for _ in ()).throw(
                                     DossierRejected("dossier_nonfinite_json")))
            except (UnicodeError, ValueError, RecursionError):
                raise DossierRejected("dossier_parse_invalid") from None
        symbol, two_roots = _validate(raw)
        category = research_category(symbol, False)
        if symbol in NEGATIVE_EVIDENCE or current_provider_negative:
            reason = "blocked_documented_noncrypto"
        elif category in ("ticker_collision_unresolved", "tokenized_gold_policy_gate"):
            reason = "blocked_policy_or_ambiguity"
        elif (raw["valid_from_ms"] > decision_at_ms
              or raw["observed_at_ms"] > decision_at_ms
              or raw["reviewed_at_ms"] > decision_at_ms
              or (raw["valid_to_ms"] is not None
                  and raw["valid_to_ms"] < decision_at_ms)
              or any(ev["observed_at_ms"] > decision_at_ms for ev in raw["evidence"])):
            reason = "evidence_not_pit"
        elif not two_roots:
            reason = "insufficient_independent_evidence"
        elif raw["asset_class"] != "crypto_token":
            reason = "blocked_policy_or_ambiguity"
        elif not raw["network_contract_id"]:
            reason = "requires_manual_venue_review"
        else:
            # Even two root domains + a claimed contract ID cannot establish
            # independent *authentication* of the Bybit derivative.
            reason = "research_candidate_only"
        result.update({
            "status": "research_only",
            "reason": reason,
            "dossier_sha256": raw["sha256"],
            "independent_publisher_roots_count": len(raw["evidence"]),
            "provider_contract_authenticated": False,
            "independent_source_authentication_verified": False,
            "identity_pit_authenticated": False,
        })
    except DossierRejected as exc:
        result["reason"] = str(exc)
    except (TypeError, OverflowError):
        result["reason"] = "dossier_validation_invalid"
    return result
