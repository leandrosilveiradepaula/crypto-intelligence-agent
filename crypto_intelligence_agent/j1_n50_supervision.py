"""J1/D290: no-I/O supervisory decision gate for the D287 current N50 epoch.

This module NEVER collects data, schedules timers, writes files, or trades.
It validates an already-sealed owner research scope and an independently
audited M1 SQLite snapshot before allowing an external operator to CONSIDER
an hourly capture. Rotation is a separate, serialized operation with a NEW
immutable scope/journal; the old epoch is never rebound or overwritten.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .j1_auto_research_epoch import (
    HOUR_MS, MAX_SCOPE_AGE_MS, validate_ranked_research_scope,
)
from .j1_rest_resume_readiness import _next_safe_target

RENEWAL_DUE_MS = 36 * HOUR_MS
MIN_SAFE_PHASE_MS = 60_000
MAX_SAFE_PHASE_MS = 15 * 60_000
MAX_EXPECTED_MEMBERS = 50
_MAX_PUBLISHED = 4096


@dataclass(frozen=True)
class N50SupervisionDecision:
    status: str
    action: str
    reason: str
    selection_age_hours: int | None = None
    published_hours: int | None = None
    stored_candles: int | None = None
    last_closed_end_ms: int | None = None
    expected_closed_end_ms: int | None = None
    scope_digest_sha256: str | None = None

    def sanitized_report(self) -> dict[str, Any]:
        return {
            "schema_version": "j1-n50-supervision-plan-v1",
            "status": self.status,
            "action": self.action,
            "reason": self.reason,
            "selection_age_hours": self.selection_age_hours,
            "published_hours": self.published_hours,
            "stored_candles": self.stored_candles,
            "last_closed_end_ms": self.last_closed_end_ms,
            "expected_closed_end_ms": self.expected_closed_end_ms,
            "scope_digest_sha256": self.scope_digest_sha256,
            "operational_activation_authorized": False,
            "new_manifest_written": False,
            "new_journal_written": False,
            "network_requests": 0,
            "database_mutation_statements": 0,
            "systemd_modified": False,
            "continuous_collector_verified": False,
            "marketwide_top50_verified": False,
            "crypto_identity_independently_verified": False,
            "live_trading_authorized": False,
            "orders_sent": False,
        }


def _deny(reason: str) -> N50SupervisionDecision:
    return N50SupervisionDecision("blocked", "none", reason)


def plan_n50_supervision(
    *, now_ms: int, sealed_scope: Mapping[str, Any] | None,
    audit: Mapping[str, Any] | None,
) -> N50SupervisionDecision:
    """Plan a SINGLE decision without any IO or implicit activation.

    Absence of an audit means a brand-new epoch ONLY, never an excuse to
    ignore an inaccessible journal. The caller must attest that a new, empty
    owner-only output directory was created at a separate operational gate.
    A valid audit always binds 50 records and its cohort to the same sealed
    scope via an explicit independently obtained digest.
    """
    if (type(now_ms) is not int
            or not 1_600_000_000_000 <= now_ms < 4_102_444_800_000
            or type(sealed_scope) is not dict):
        return _deny("invalid_clock_or_manifest")
    try:
        members, digest = validate_ranked_research_scope(
            sealed_scope, now_ms=now_ms, max_assets=MAX_EXPECTED_MEMBERS
        )
        if len(members) != MAX_EXPECTED_MEMBERS:
            return _deny("not_fifty_contracts")
    except (ValueError, TypeError, KeyError, OverflowError):
        return _deny("manifest_stale_or_invalid")

    age_ms = now_ms - sealed_scope["catalog_post_observed_at_ms"]
    age_hours = age_ms // HOUR_MS
    phase = now_ms % HOUR_MS
    target = _next_safe_target(now_ms)
    common = dict(
        selection_age_hours=age_hours, scope_digest_sha256=digest,
        expected_closed_end_ms=target,
    )

    if audit is None:
        # A missing/inaccessible EXISTING journal is not an empty epoch.
        # This action is ONLY a plan for an out-of-band, verified new folder.
        if age_ms >= RENEWAL_DUE_MS:
            return N50SupervisionDecision(
                "blocked", "none", "new_epoch_scope_too_old", **common)
        if not MIN_SAFE_PHASE_MS <= phase <= MAX_SAFE_PHASE_MS:
            return N50SupervisionDecision(
                "deferred", "none", "outside_closed_utc_window", **common)
        return N50SupervisionDecision(
            "needs_external_gate", "bootstrap_new_empty_epoch",
            "require_verified_empty_isolated_owner_journal", **common)

    if type(audit) is not dict:
        return _deny("audit_payload_invalid")
    # Readiness is NOT an authorization token; enforce its complete safety
    # invariants and crosscheck time, membership, counts, gaps and statuses.
    required_false = (
        "activation_authorized", "continuous_collector_verified",
        "marketwide_top50_verified", "source_authenticated",
        "signal_authorized", "live_trading_authorized", "orders_sent",
    )
    if (audit.get("schema_version") != "j1_rest_resume_readiness_v1"
            or audit.get("journal_integrity_verified") is not True
            or any(audit.get(k) is not False for k in required_false)
            or audit.get("network_requests") != 0
            or audit.get("database_mutation_statements") != 0
            or audit.get("reviewed_research_contracts") != 50
            or audit.get("research_closed_24h_ranked_contracts") != 50
            or audit.get("rank_is_sample_only_not_marketwide") is not True
            or audit.get("historical_checkpoint_gaps_present") is not False
            or audit.get("historical_unpublished_hours") != 0
            or audit.get("status") != "no_gap"):
        return _deny("unverified_or_gap_affected_journal")
    # NOTE: the audit API does not expose the journal's scope_digest.
    # The digest must be independently obtained from the owner-controlled
    # scope table, never inferred from a prior report or symbol list.
    if audit.get("journal_scope_digest_sha256") != digest:
        return _deny("journal_scope_binding_missing_or_drifted")

    last = audit.get("last_published_end_ms")
    published = audit.get("published_hours")
    candles = audit.get("stored_candles")
    remaining = audit.get("catchup_hours")
    if (type(last) is not int or last % HOUR_MS or last > now_ms
            or type(published) is not int or not 1 <= published <= _MAX_PUBLISHED
            or type(candles) is not int
            or candles < 1200 or candles % 50 != 0
            or type(remaining) is not int or remaining not in (0, 1)
            or audit.get("catchup_within_worker_limit") is not True
            or audit.get("unobserved_closed_hours") != 0
            or audit.get("next_eligible_end_ms") != target
            or target - last != remaining * HOUR_MS
            or candles != 50 * (24 + published - 1)):
        return _deny("journal_timing_or_count_inconsistent")

    common.update(
        published_hours=published, stored_candles=candles,
        last_closed_end_ms=last,
    )
    if age_ms >= RENEWAL_DUE_MS:
        # A full D286 capture occupies most of HH:01..15. Do not run it
        # alongside the hourly N50 writer. Rotation requires serializing
        # GETs and allocating a fresh journal; never rewrite this epoch.
        return N50SupervisionDecision(
            "needs_external_gate", "serialize_rotation_to_new_epoch",
            "refresh_requires_new_manifest_and_new_journal", **common)
    if not MIN_SAFE_PHASE_MS <= phase <= MAX_SAFE_PHASE_MS:
        return N50SupervisionDecision(
            "deferred", "none", "outside_closed_utc_window", **common)
    if remaining == 0:
        return N50SupervisionDecision(
            "no_op", "none", "this_closed_hour_already_published", **common)
    return N50SupervisionDecision(
        "needs_external_gate", "run_existing_epoch_once",
        "journal_integrity_and_hourly_window_verified", **common)
