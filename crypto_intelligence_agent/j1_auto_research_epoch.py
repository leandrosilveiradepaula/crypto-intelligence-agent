"""J1/D287: bind a current D286 provisional Top50 to an immutable research epoch.

This is an owner-controlled RESEARCH manifest, not authenticated identity/PIT
proof and never an execution allowlist. It contains public contract symbols;
readers must keep the manifest in an owner-only directory.
"""
from __future__ import annotations

from hashlib import sha256
import json
import re
from typing import Any, Mapping

from .bybit_tradfi_negative_evidence import NEGATIVE_EVIDENCE

SCHEMA = "j1-auto-ranked-research-scope-v1"
STATUS = "current_auto_ranked_perpetual_research_scope_only"
HOUR_MS = 3_600_000
MAX_SCOPE_AGE_MS = 48 * HOUR_MS
FILE_NAME = "j1-auto-ranked-research-scope-v1.json"
_SHA = re.compile(r"[0-9a-f]{64}\\Z")
_SYMBOL = re.compile(r"[A-Z0-9]{1,28}USDT\\Z")
_EXPECTED_KEYS = frozenset({
    "schema_version", "status", "closed_hour_end_ms",
    "catalog_pre_observed_at_ms", "catalog_post_observed_at_ms",
    "pool_candidate_count", "candidate_pool_digest_sha256",
    "closed24h_rank_digest_sha256", "ranked_research_symbols_only",
    "scope_digest_sha256", "provisional_research_only",
    "marketwide_top50_verified", "independent_crypto_identity_verified",
    "live_trading_authorized", "orders_sent",
})


def _hash(parts: list) -> str:
    return sha256(json.dumps(
        parts, ensure_ascii=True, separators=(",", ":"), sort_keys=True,
    ).encode("ascii")).hexdigest()


def _binding(scope: Mapping[str, Any]) -> str:
    return _hash([
        SCHEMA, scope["closed_hour_end_ms"],
        scope["catalog_pre_observed_at_ms"],
        scope["catalog_post_observed_at_ms"],
        scope["pool_candidate_count"],
        scope["candidate_pool_digest_sha256"],
        scope["closed24h_rank_digest_sha256"],
        scope["ranked_research_symbols_only"],
    ])


def build_ranked_research_scope(report: Mapping[str, Any], *, now_ms: int) -> dict:
    """Convert a successful D286 owner report with public symbol opt-in."""
    if (type(report) is not dict
            or report.get("schema_version") !=
                "j1-auto-current-closed24h-research-only-v1"
            or report.get("status") !=
                "current_closed24h_provisional_perpetual_rank_research_only"
            or report.get("catalog_census_matches_before_after") is not True
            or report.get("source_research_only") is not True
            or report.get("rolling_ticker_volume_used") is not False
            or report.get("database_modified") is not False
            or report.get("network_accessed") is not True
            or report.get("marketwide_top50_verified") is not False
            or report.get("current_crypto_identity_independently_verified") is not False
            or report.get("live_trading_authorized") is not False
            or report.get("orders_sent") is not False
            or report.get("ranked_research_candidates") != 50
            or type(report.get("complete_closed24h_candidates")) is not int
            or report["complete_closed24h_candidates"] < 50):
        raise ValueError("untrusted_current_research_rank")
    data = {
        "schema_version": SCHEMA, "status": STATUS,
        "closed_hour_end_ms": report.get("decision_closed_hour_end_ms"),
        "catalog_pre_observed_at_ms": report.get("catalog_pre_observed_at_ms"),
        "catalog_post_observed_at_ms": report.get("catalog_post_observed_at_ms"),
        "pool_candidate_count": report.get("current_catalog_provisional_candidates"),
        "candidate_pool_digest_sha256":
            report.get("catalog_provisional_pool_digest_sha256"),
        "closed24h_rank_digest_sha256": report.get("rank_digest_sha256"),
        "ranked_research_symbols_only":
            report.get("ranked_public_research_symbols_only"),
        "scope_digest_sha256": "",
        "provisional_research_only": True,
        "marketwide_top50_verified": False,
        "independent_crypto_identity_verified": False,
        "live_trading_authorized": False, "orders_sent": False,
    }
    data["scope_digest_sha256"] = _binding(data)
    validate_ranked_research_scope(data, now_ms=now_ms, max_assets=50)
    return data


def validate_ranked_research_scope(
    scope: Any, *, now_ms: int, max_assets: int
) -> tuple[tuple[str, ...], str]:
    """Fail closed on stale/tampered manifest or any non-Top50 research scope.

    A scope is pinned for at most 48h. A changed cohort MUST use a new
    journal/output epoch; M1's existing scope_digest protection enforces it.
    """
    if (type(scope) is not dict or set(scope) != _EXPECTED_KEYS
            or scope.get("schema_version") != SCHEMA
            or scope.get("status") != STATUS
            or type(max_assets) is not int or max_assets != 50
            or type(now_ms) is not int
            or not 1_600_000_000_000 <= now_ms < 4_102_444_800_000
            or scope.get("provisional_research_only") is not True
            or scope.get("marketwide_top50_verified") is not False
            or scope.get("independent_crypto_identity_verified") is not False
            or scope.get("live_trading_authorized") is not False
            or scope.get("orders_sent") is not False):
        raise ValueError("current_research_scope_contract_invalid")
    members = scope["ranked_research_symbols_only"]
    if (type(members) is not list or len(members) != 50
            or any(type(s) is not str or _SYMBOL.fullmatch(s) is None
                   or s in NEGATIVE_EVIDENCE for s in members)
            or len(set(members)) != 50):
        raise ValueError("current_research_scope_members_invalid")
    closed = scope["closed_hour_end_ms"]
    before = scope["catalog_pre_observed_at_ms"]
    after = scope["catalog_post_observed_at_ms"]
    pool_size = scope["pool_candidate_count"]
    if (type(closed) is not int or closed < HOUR_MS or closed % HOUR_MS
            or type(before) is not int or type(after) is not int
            or not closed + 60_000 <= before <= after <= closed + 900_000
            or not after <= now_ms <= after + MAX_SCOPE_AGE_MS
            or type(pool_size) is not int or not 50 <= pool_size <= 400
            or any(type(scope.get(k)) is not str
                   or _SHA.fullmatch(scope[k]) is None
                   for k in ("candidate_pool_digest_sha256",
                             "closed24h_rank_digest_sha256",
                             "scope_digest_sha256"))
            or scope["scope_digest_sha256"] != _binding(scope)):
        raise ValueError("current_research_scope_provenance_invalid")
    return tuple(members), scope["scope_digest_sha256"]
