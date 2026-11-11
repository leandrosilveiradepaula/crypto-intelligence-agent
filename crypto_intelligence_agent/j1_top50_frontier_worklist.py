"""J1/D275: one offline identity-review worklist for the *existing* D264 frontier.

The D264 list is retrospectively filtered using later metadata. This module
only prioritizes research: no member is automatically proved crypto/PIT,
and neither archived labels nor two public URLs become a trading allowlist.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
import re
from typing import Any

from .bybit_identity_crosswalk_research import research_category, research_details
from .bybit_primary_identity_research import primary_research_details
from .bybit_tradfi_negative_evidence import NEGATIVE_EVIDENCE

_SYMBOL = re.compile(r"[A-Z0-9]{1,28}USDT\Z")
_BASE = re.compile(r"[A-Z0-9]{1,24}\Z")
_CATEGORIES = {
    "archived_crypto_reference_only": "renew_archived_identity_and_venue_contract",
    "crypto_token_candidate_unverified": "verify_venue_contract_and_token_identity",
    "ticker_collision_unresolved": "resolve_collision_with_exact_contract_or_mint",
    "tokenized_gold_policy_gate": "requires_explicit_product_policy_decision",
    "identity_unresolved": "find_primary_venue_and_independent_asset_sources",
}
_SCHEMA = "j1-d275-private-frontier-review-worklist-v1"


def frontier_review_worklist(
    frontier: tuple[str, ...], *,
    frozen_market_window_end_ms: int,
    archived_crypto_bases: frozenset[str],
    include_private_symbols: bool = False,
) -> dict[str, Any]:
    """Produce a deterministic 50-row worklist from *validated* D264 inputs.

    Caller must already have replayed the immutable private census, checked the
    D264 negative snapshot, selected the 50-member research frontier and loaded
    the older reference registry. This function cannot authenticate any input.
    """
    if (type(frontier) is not tuple or len(frontier) != 50
            or len(set(frontier)) != 50
            or any(type(x) is not str or _SYMBOL.fullmatch(x) is None
                   for x in frontier)
            or type(archived_crypto_bases) is not frozenset
            or len(archived_crypto_bases) > 2000
            or any(type(x) is not str or _BASE.fullmatch(x) is None
                   for x in archived_crypto_bases)
            or type(frozen_market_window_end_ms) is not int
            or not 1_600_000_000_000 <= frozen_market_window_end_ms <= 4_102_444_800_000
            or type(include_private_symbols) is not bool):
        raise ValueError("invalid D275 research worklist input")
    categories: Counter[str] = Counter()
    actions: Counter[str] = Counter()
    primary_count = 0
    primary_not_pit = 0
    rows: list[dict[str, Any]] = []
    digested: list[list[str]] = []
    for rank, symbol in enumerate(frontier, 1):
        if symbol in NEGATIVE_EVIDENCE:
            raise ValueError("documented negative slipped into D264 frontier")
        category = research_category(symbol, symbol[:-4] in archived_crypto_bases)
        action = _CATEGORIES.get(category)
        if action is None:
            # A new category cannot be silently treated as crypto.
            raise ValueError("unknown D275 research category")
        categories[category] += 1
        actions[action] += 1
        lead = primary_research_details(
            symbol, market_window_end_ms=frozen_market_window_end_ms
        )
        if lead:
            primary_count += 1
            if lead["identity_pit_authenticated"] is not False:
                raise ValueError("primary research must not be PIT approved")
            if not lead["research_reviewed_before_market_window"]:
                primary_not_pit += 1
        digested.append([
            symbol, category, action,
            "primary" if lead else "no_primary",
        ])
        if include_private_symbols:
            hints = research_details(symbol)
            row: dict[str, Any] = {
                "position_in_retrospective_research_frontier": rank,
                "symbol": symbol,
                "category_unverified": category,
                "next_identity_review_action": action,
                "research_hypothesis_refs_only":
                    (hints or {}).get("proposed_asset_refs_unverified", []),
                "public_research_urls_only":
                    (hints or {}).get("candidate_research_urls", []),
                "has_two_primary_source_research_lead": lead is not None,
                "identity_approved": False,
                "eligible_top50": False,
            }
            if lead:
                row["primary_venue_url_research_only"] = lead["venue_primary_url"]
                row["independent_asset_url_research_only"] = (
                    lead["independent_token_primary_url"]
                )
                row["network_contract_research_only"] = lead[
                    "network_contract_research"
                ]
                row["first_party_review_not_pit"] = (
                    not lead["research_reviewed_before_market_window"]
                )
            rows.append(row)
    raw = json.dumps(
        digested, ensure_ascii=True, separators=(",", ":")
    ).encode("ascii")
    report: dict[str, Any] = {
        "schema_version": _SCHEMA,
        "status": "retrospective_frontier_identity_review_required",
        "research_frontier_count": len(frontier),
        "category_counts": dict(sorted(categories.items())),
        "review_action_counts": dict(sorted(actions.items())),
        "two_primary_sources_research_leads_count": primary_count,
        "two_primary_sources_not_reviewed_pit_count": primary_not_pit,
        "identity_review_pending_count": len(frontier),
        "identity_approved_count": 0,
        "research_queue_sha256": sha256(raw).hexdigest(),
        "snapshot_source_authenticated": False,
        "identity_pit_authenticated": False,
        "marketwide_top50_verified": False,
        "trading_enabled": False,
        "orders_sent": False,
        "network_requests": 0,
        "database_modified": False,
    }
    if include_private_symbols:
        report["private_research_worklist_only"] = rows
    return report
