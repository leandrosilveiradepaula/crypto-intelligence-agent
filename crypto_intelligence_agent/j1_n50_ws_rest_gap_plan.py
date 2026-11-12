"""D324: select only genuinely missing N50 WS closed bars for bounded REST.

Pure offline plan, derived from D313's SAME full SQLite read-only snapshot.
No client, HTTP GET, retries, mutation, REST->WS relabeling, or orders.
Provider access and any REST reconciliation require an independent owner gate.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
import re
from typing import Any

from .bybit_closed_stream_cache import (
    HOUR_MS, OfflineReviewedStreamScope, SQLiteOfflineClosedStreamJournal,
)
from .bybit_public_j1_transport import J1BybitCaptureError, kline_url
from .j1_auto_research_epoch import validate_ranked_research_scope
from .market_data import DataGapError, DataValidationError

MAX_GAP_GETS = 3
MIN_SETTLE_DELAY_MS = 180_000
MAX_SETTLE_DELAY_MS = 900_000
_SHA = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class N50WSRESTGapPlan:
    status: str
    closed_hour_end_ms: int | None = None
    confirmed_ws_contracts: int = 0
    missing_ws_contracts: int = 50
    planned_rest_gets: int = 0
    plan_digest_sha256: str | None = None
    ws_journal_digest_sha256: str | None = None
    ranked_scope_sha256: str | None = None
    # Contains URL + member symbol: private only and excluded from repr,
    # equality and sanitized report. MUST NEVER be treated as executed GETs.
    private_get_urls: tuple[str, ...] = field(default_factory=tuple, repr=False, compare=False)

    def sanitized_report(self) -> dict[str, Any]:
        return {
            "schema_version": "j1-n50-ws-rest-gap-target-plan-v1",
            "status": self.status,
            "closed_hour_end_ms": self.closed_hour_end_ms,
            "expected_ws_contracts": 50,
            "confirmed_ws_contracts": self.confirmed_ws_contracts,
            "missing_ws_contracts": self.missing_ws_contracts,
            "max_rest_gets_per_hour": MAX_GAP_GETS,
            "planned_rest_gets": self.planned_rest_gets,
            "plan_digest_sha256": self.plan_digest_sha256,
            "ws_journal_digest_sha256": self.ws_journal_digest_sha256,
            "ranked_scope_sha256": self.ranked_scope_sha256,
            "rest_gets_executed": 0,
            "retry_after_rate_limit_enabled": False,
            "rest_rows_inserted_as_ws": 0,
            "published_rest_pit": False,
            "ws_24h_continuity_verified": False,
            "marketwide_top50_verified": False,
            "crypto_identity_independently_verified": False,
            "source_authenticated": False,
            "approved_for_signals": False,
            "live_trading_authorized": False,
            "orders_sent": False,
            "database_mutation_statements": 0,
            "systemd_modified": False,
        }


def plan_n50_ws_rest_gap_targets(
    *, ranked_scope: dict, ws_scope: OfflineReviewedStreamScope,
    journal: SQLiteOfflineClosedStreamJournal,
    decision_at_ms: int, observed_at_ms: int,
    max_gets: int = MAX_GAP_GETS,
) -> N50WSRESTGapPlan:
    """Return missing-hour REST target URLs only after a full WS SQLite audit.

    Avoid the former 50 GET/h pattern: zero when 50/50 WS, 1-3 only
    when verified missing, and zero if >3 gaps (human review). Returns
    symbolic private request URLs, not GETs or REST market-data receipts.
    """
    abstain = N50WSRESTGapPlan("rest_gap_plan_integrity_abstain")
    if (type(ranked_scope) is not dict
            or type(ws_scope) is not OfflineReviewedStreamScope
            or type(journal) is not SQLiteOfflineClosedStreamJournal
            or type(decision_at_ms) is not int
            or decision_at_ms <= HOUR_MS or decision_at_ms % HOUR_MS
            or type(observed_at_ms) is not int
            or not decision_at_ms + MIN_SETTLE_DELAY_MS
                   <= observed_at_ms <= decision_at_ms + MAX_SETTLE_DELAY_MS
            or type(max_gets) is not int or not 1 <= max_gets <= MAX_GAP_GETS
            or len(ws_scope.contracts) != 50
            or ws_scope.observed_at_ms >= decision_at_ms):
        return abstain
    try:
        members, digest = validate_ranked_research_scope(
            ranked_scope, now_ms=observed_at_ms, max_assets=50,
        )
        chosen = tuple(sorted(members))
        if (len(chosen) != 50
                or {item.symbol for item in ws_scope.contracts} != set(chosen)
                or ranked_scope["catalog_post_observed_at_ms"] >= decision_at_ms):
            return abstain
        audit = journal.audit(
            scope=ws_scope, decision_at_ms=decision_at_ms,
            as_of_ms=observed_at_ms, hour_evidence_symbols=chosen,
        )
        missing = audit.private_missing_hour_members
        if (type(missing) is not tuple
                or any(type(name) is not str for name in missing)
                or tuple(sorted(set(missing))) != missing
                or not set(missing).issubset(set(chosen))
                or audit.hour_evidence_expected != 50
                or type(audit.hour_evidence_confirmed) is not int
                or audit.hour_evidence_confirmed + len(missing) != 50
                or type(audit.journal_digest_sha256) is not str
                or _SHA.fullmatch(audit.journal_digest_sha256) is None):
            return abstain
        base = {
            "closed_hour_end_ms": decision_at_ms,
            "confirmed_ws_contracts": audit.hour_evidence_confirmed,
            "missing_ws_contracts": len(missing),
            "ws_journal_digest_sha256": audit.journal_digest_sha256,
            "ranked_scope_sha256": digest,
        }
        if not missing:
            if (audit.hour_evidence_sha256 is None
                    or not _SHA.fullmatch(audit.hour_evidence_sha256)):
                return abstain
            return N50WSRESTGapPlan("ws_50_complete_no_rest_needed", **base)
        if len(missing) > max_gets:
            return N50WSRESTGapPlan("ws_gaps_exceed_rest_budget_no_get", **base)
        urls = tuple(kline_url(symbol, decision_at_ms - HOUR_MS,
                               decision_at_ms) for symbol in missing)
        sealed = json.dumps({
            "schema": "j1-n50-rest-gap-target-v1",
            "decision_at_ms": decision_at_ms,
            "scope_sha256": digest,
            "ws_registry_sha256": ws_scope.registry_sha256,
            "ws_journal_sha256": audit.journal_digest_sha256,
            "missing_symbols": list(missing),
        }, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
        return N50WSRESTGapPlan(
            "ws_rest_gap_targets_private_ready",
            planned_rest_gets=len(urls),
            plan_digest_sha256=sha256(sealed).hexdigest(),
            private_get_urls=urls, **base,
        )
    except (OSError, ValueError, TypeError, DataGapError,
            DataValidationError, J1BybitCaptureError, OverflowError,
            KeyError, UnicodeError):
        return abstain
