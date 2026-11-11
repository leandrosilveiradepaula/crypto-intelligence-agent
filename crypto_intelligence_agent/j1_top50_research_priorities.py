"""J1 D274: annotate existing closed-candle rank with offline identity leads.

This is *review triage*, never crypto classification or an allowlist.
Annotations on raw Top50 are not evidence that a contract belongs to a
crypto-only Top50. Do not auto-apply D264 contemporary exclusions to PIT.
"""
from __future__ import annotations

from collections import Counter
import re
from typing import Any

from .bybit_identity_crosswalk_research import research_category
from .bybit_primary_identity_research import PRIMARY_LEADS, primary_research_details

_SYMBOL = re.compile(r"[A-Z0-9]{1,28}USDT\Z")
_RESEARCH_TYPES = frozenset({
    "identity_unresolved",
    "crypto_token_candidate_unverified",
    "ticker_collision_unresolved",
    "tokenized_gold_policy_gate",
    "bybit_tradfi_documented_retrospective",
})


def annotate_raw_rank_research(
    raw_ranked_symbols: tuple[str, ...], *,
    market_window_end_ms: int,
    include_symbols: bool = False,
) -> dict[str, Any]:
    """Count research burdens in an already validated, sorted 1..50 raw rank.

    Caller must independently verify volume totals, snapshot, and scope.
    Positive classification is deliberately impossible in this function.
    """
    if (type(raw_ranked_symbols) is not tuple
            or not 1 <= len(raw_ranked_symbols) <= 50
            or len(set(raw_ranked_symbols)) != len(raw_ranked_symbols)
            or any(type(s) is not str or _SYMBOL.fullmatch(s) is None
                   for s in raw_ranked_symbols)
            or type(include_symbols) is not bool
            or type(market_window_end_ms) is not int
            or not 1_600_000_000_000 <= market_window_end_ms <= 4_102_444_800_000):
        raise ValueError("rank research input invalid")
    counts: Counter[str] = Counter()
    rows: list[dict[str, Any]] = []
    for ordinal, symbol in enumerate(raw_ranked_symbols, 1):
        label = research_category(symbol, False)
        if label not in _RESEARCH_TYPES:
            # May have other historical documentation categories, none
            # implies an independently authenticated identity.
            label = "unapproved_historical_reference"
        evidence = None
        if symbol in PRIMARY_LEADS:
            evidence = primary_research_details(
                symbol, market_window_end_ms=market_window_end_ms
            )
        counts[label] += 1
        if evidence is not None:
            counts["primary_crosswalk_research_count"] += 1
            if evidence["status"] == "historical_pit_not_established":
                counts["primary_crosswalk_not_pit_count"] += 1
        if include_symbols:
            rows.append({
                "position_in_raw_closed_rank": ordinal,
                "symbol": symbol,
                "identity_research_category": label,
                "primary_crosswalk_research_only": evidence is not None,
                "identity_approved": False,
            })
    result: dict[str, Any] = {
        "schema_version": "j1-top50-raw-rank-research-overlay-v1",
        "status": "raw_rank_research_annotations_not_eligibility",
        "raw_ranked_contracts": len(raw_ranked_symbols),
        "research_category_counts": dict(sorted(counts.items())),
        "crypto_identity_independently_verified": False,
        "identity_pit_authenticated": False,
        "marketwide_top50_verified": False,
        "trading_enabled": False,
        "orders_sent": False,
        "network_requests": 0,
        "database_modified": False,
    }
    if include_symbols:
        result["raw_rank_research_symbols_only"] = rows
    return result
