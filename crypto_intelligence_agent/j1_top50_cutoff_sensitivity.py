"""D276/J1: sensitivity of the *research* Top50 cutoff to explicit exclusions.

Pure function for an already validated descending 24h USDT-turnover ranking.
No ticker classification, no source authentication, no network or storage.
The frozen D264 negative indicators are contemporary, NOT PIT evidence.
"""
from __future__ import annotations

from hashlib import sha256
import json
import re
from typing import Any

_SYMBOL = re.compile(r"[A-Z0-9]{1,28}USDT\Z")
_TOP = 50
_MAX = 5000
_SCENARIOS: tuple[tuple[str, frozenset[str]], ...] = (
    ("frozen_d264_research_baseline", frozenset()),
    ("exclude_tokenized_gold_if_out_of_scope", frozenset({"XAUTUSDT"})),
    ("exclude_gold_and_unverified_collisions", frozenset({
        "XAUTUSDT", "LITUSDT", "ARIAUSDT", "BIRBUSDT", "CLANKERUSDT",
    })),
)


def _symbols(values: object, *, label: str) -> tuple[str, ...]:
    if (type(values) is not tuple or len(values) > _MAX
            or any(type(x) is not str or _SYMBOL.fullmatch(x) is None
                   for x in values)
            or len(values) != len(set(values))):
        raise ValueError(label + "_invalid")
    return values


def _digest(values: tuple[str, ...]) -> str:
    # Source authenticated? No. Digest is deterministic, not an attestation.
    return sha256(json.dumps(values, separators=(",", ":"), ensure_ascii=True)
                  .encode("ascii")).hexdigest()


def cutoff_sensitivity(
    *, all_complete_ranked_symbols: tuple[str, ...],
    retrospectively_excluded_symbols: frozenset[str],
    incomplete_candle_contracts: int,
    include_private_symbols: bool = False,
) -> dict[str, Any]:
    """Report how the D264 research frontier moves when policy changes.

    Input is already ranked using verified same-UTC 24x1h turnover and
    deterministic tie breaking; this function cannot prove its order.
    Extra scenarios are *conditional*, not implied product scope decisions.
    Incomplete contracts always block a global Top50 conclusion.
    """
    ordered = _symbols(all_complete_ranked_symbols, label="ordered")
    if (len(ordered) < _TOP
            or type(retrospectively_excluded_symbols) is not frozenset
            or len(retrospectively_excluded_symbols) > _MAX
            or any(type(x) is not str or _SYMBOL.fullmatch(x) is None
                   for x in retrospectively_excluded_symbols)
            or type(incomplete_candle_contracts) is not int
            or not 0 <= incomplete_candle_contracts <= _MAX
            or type(include_private_symbols) is not bool):
        raise ValueError("cutoff_sensitivity_input_invalid")
    baseline = tuple(s for s in ordered
                     if s not in retrospectively_excluded_symbols)
    if len(baseline) < _TOP:
        raise ValueError("not_enough_research_candidates")
    baseline_top = baseline[:_TOP]
    baseline_set = frozenset(baseline_top)
    scenarios: list[dict[str, Any]] = []
    for name, additional_exclusions in _SCENARIOS:
        eligible = tuple(s for s in baseline if s not in additional_exclusions)
        if len(eligible) < _TOP:
            raise ValueError("scenario_has_fewer_than_50")
        top = eligible[:_TOP]
        new = tuple(s for s in top if s not in baseline_set)
        lost = tuple(s for s in baseline_top if s not in top)
        if len(new) != len(lost):
            raise ValueError("boundary_replacement_invariant_failed")
        scenario: dict[str, Any] = {
            "scenario": name,
            "conditional_only": True,
            "ranked_complete_candidates_remaining": len(eligible),
            "changed_positions_count": len(new),
            "excluded_from_original_frontier_count": len(lost),
            "replacements_in_top50_count": len(new),
            "retrospective_top50_symbol_order_digest": _digest(top),
            "displaced_symbol_set_digest": _digest(tuple(sorted(lost))),
            "replacement_symbol_set_digest": _digest(tuple(sorted(new))),
        }
        if include_private_symbols:
            scenario["displaced_original_symbols_only"] = list(lost)
            scenario["replacement_symbols_only"] = [
                {"research_position": top.index(s) + 1, "symbol": s}
                for s in new
            ]
            scenario["next_10_research_symbols_only"] = [
                {"research_position": i + _TOP + 1, "symbol": s}
                for i, s in enumerate(eligible[_TOP:_TOP + 10])
            ]
        scenarios.append(scenario)
    return {
        "schema_version": "j1-d276-private-cutoff-sensitivity-v1",
        "status": "retrospective_research_scenarios_not_crypto_top50",
        "complete_candle_contracts": len(ordered),
        "incomplete_candle_contracts": incomplete_candle_contracts,
        "retrospectively_excluded_complete_contracts": (
            len(ordered) - len(baseline)
        ),
        "baseline_research_frontier_count": len(baseline_top),
        "scenarios": scenarios,
        "retrospective_exclusions_are_not_historical_pit": True,
        "incomplete_contracts_remain_possible_rivals": (
            incomplete_candle_contracts > 0
        ),
        "identity_pit_authenticated": False,
        "marketwide_top50_verified": False,
        "trading_enabled": False,
        "orders_sent": False,
        "network_requests": 0,
        "database_modified": False,
    }
