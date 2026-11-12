"""D313: join 50 closed WS events to one *already sealed* D287 N50 cohort.

Strictly an offline/read-only proof of the observed UTC hour; this does NOT
publish a REST checkpoint, certify a live websocket, authenticate a provider,
or reopen any halted N50 journal. Persistence/cutover require separate gates.
"""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any

from .bybit_closed_stream_cache import (
    HOUR_MS, OfflineReviewedStreamScope, SQLiteOfflineClosedStreamJournal,
)
from .j1_auto_research_epoch import validate_ranked_research_scope
from .market_data import DataGapError, DataValidationError

MAX_WS_TOPICS = 52


def _empty(status: str) -> dict[str, Any]:
    return {
        "schema_version": "j1-n50-ws-observed-hour-v1",
        "status": status,
        "utc_closed_hour_end_ms": None,
        "expected_contracts": 50,
        "confirmed_contracts": 0,
        "missing_contracts": 50,
        "evidence_sha256": None,
        "network_requests": 0,
        "database_mutation_statements": 0,
        "systemd_modified": False,
        "published_rest_pit": False,
        "continuous_collector_verified": False,
        "marketwide_top50_verified": False,
        "crypto_identity_independently_verified": False,
        "source_authenticated": False,
        "approved_for_signals": False,
        "live_trading_authorized": False,
        "orders_sent": False,
    }


def attest_n50_ws_hour_once(
    *, ranked_scope: dict, ws_scope: OfflineReviewedStreamScope,
    journal: SQLiteOfflineClosedStreamJournal,
    decision_at_ms: int, observed_at_ms: int,
) -> dict[str, Any]:
    """One atomic SQLite snapshot read: require the exactly sealed 50 members.

    The WS scope may contain 50..52 previously reviewed instruments but MUST
    include each current ranked member, and must have existed before this
    hour closed. Future catalog revisions cannot validate earlier candles.
    No duplicate/partial ACK or 49/50 can appear as a complete observation.
    """
    out = _empty("ws_closed_hour_abstain")
    if (type(ws_scope) is not OfflineReviewedStreamScope
            or type(journal) is not SQLiteOfflineClosedStreamJournal
            or type(decision_at_ms) is not int or decision_at_ms % HOUR_MS
            or type(observed_at_ms) is not int
            or not decision_at_ms + 1000 <= observed_at_ms
                   <= decision_at_ms + 120_000
            or not 50 <= len(ws_scope.contracts) <= MAX_WS_TOPICS):
        return out
    try:
        # Full D287 provenance/TTL and negative-evidence guard, not a
        # user-provided "top50" assertion or a ticker-suffix heuristic.
        members, digest = validate_ranked_research_scope(
            ranked_scope, now_ms=observed_at_ms, max_assets=50,
        )
        chosen = tuple(sorted(members))
        ws_members = {item.symbol for item in ws_scope.contracts}
        if (len(ws_members) != len(ws_scope.contracts)
                or not set(chosen).issubset(ws_members)
                or ws_scope.observed_at_ms >= decision_at_ms
                or ranked_scope["catalog_post_observed_at_ms"] >= decision_at_ms):
            return out
        # audit() replays hashes, UTC receipts, identities and gap markers,
        # and computes 50/50 for decision_at_ms within the SAME BEGIN snapshot.
        audit = journal.audit(
            scope=ws_scope, decision_at_ms=decision_at_ms,
            as_of_ms=observed_at_ms, hour_evidence_symbols=chosen,
        )
        if (audit.hour_evidence_expected != 50
                or type(audit.hour_evidence_confirmed) is not int
                or not 0 <= audit.hour_evidence_confirmed <= 50):
            return out
        out["utc_closed_hour_end_ms"] = decision_at_ms
        out["confirmed_contracts"] = audit.hour_evidence_confirmed
        out["missing_contracts"] = 50 - audit.hour_evidence_confirmed
        if audit.hour_evidence_confirmed != 50:
            out["status"] = "ws_closed_hour_incomplete_no_pit"
            return out
        if (type(audit.hour_evidence_sha256) is not str
                or len(audit.hour_evidence_sha256) != 64
                or type(audit.journal_digest_sha256) is not str
                or len(audit.journal_digest_sha256) != 64):
            return _empty("ws_closed_hour_abstain")
        combined = {
            "schema": "j1-n50-ws-attested-hour-v1",
            "closed_end_ms": decision_at_ms,
            "ranked_scope_sha256": digest,
            "ws_registry_sha256": ws_scope.registry_sha256,
            "ws_journal_sha256": audit.journal_digest_sha256,
            "ws_hour_sha256": audit.hour_evidence_sha256,
        }
        out["evidence_sha256"] = sha256(
            json.dumps(combined, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True).encode("ascii")
        ).hexdigest()
        out["status"] = "ws_hour_50_observed_local_only_not_marketwide"
        return out
    except (DataValidationError, DataGapError, ValueError, OSError, TypeError,
            OverflowError, UnicodeError):
        return _empty("ws_closed_hour_abstain")
