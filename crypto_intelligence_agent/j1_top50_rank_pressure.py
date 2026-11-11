"""J1/#319: rank-pressure frontier, not an identity or market authentication gate.

When 50 crypto contracts have actually been independently reviewed, only
UNRESOLVED contracts which could outrank the 50th reviewed contract need
further classification. Lower-volume unknowns cannot displace a Top 50.
An unmeasured contract always remains a blocker unless independently excluded.
No network, storage, credential, or trading side effects.
"""
from __future__ import annotations

from collections.abc import Collection, Mapping
from decimal import Decimal
from hashlib import sha256
import json
import re
from typing import Any

MAX_CONTRACTS = 5000
TOP_N = 50
_SYMBOL = re.compile(r"[A-Z0-9]{1,28}USDT\Z")
_AMOUNT = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]{1,24})?\Z")


class Top50PressureRejected(ValueError):
    """Invalid input; do not propagate a provider symbol or financial value."""


def _symbols(value: Collection[str], label: str) -> frozenset[str]:
    if type(value) not in (list, tuple, set, frozenset):
        raise Top50PressureRejected(label + "_invalid")
    if (len(value) > MAX_CONTRACTS or
            any(type(s) is not str or _SYMBOL.fullmatch(s) is None for s in value)):
        raise Top50PressureRejected(label + "_invalid")
    unique = frozenset(value)
    if len(unique) != len(value):
        raise Top50PressureRejected(label + "_duplicate")
    return unique


def _decimal(value: Any) -> Decimal:
    if type(value) is Decimal:
        amount = value
    elif type(value) is str and len(value) <= 80 and _AMOUNT.fullmatch(value):
        amount = Decimal(value)
    else:
        raise Top50PressureRejected("turnover_invalid")
    if not amount.is_finite() or amount < 0 or len(amount.as_tuple().digits) > 50:
        raise Top50PressureRejected("turnover_invalid")
    return amount


def _digest(rows: list[list[str]]) -> str:
    raw = json.dumps(rows, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=True).encode("ascii")
    return sha256(raw).hexdigest()


def pressure_from_closed_turnover(
    *, catalog_symbols: Collection[str],
    closed_turnover_usdt: Mapping[str, Decimal | str],
    positively_reviewed_crypto: Collection[str],
    independently_excluded_noncrypto: Collection[str],
    include_public_symbols: bool = False,
) -> dict[str, Any]:
    """Report the *minimum next candidates* for a complete observed Top 50.

    Each turnover must already be a verified sum of exactly 24 UTC-closed
    hourly USDT candles for that symbol, from the same observation end.
    The caller supplies independently reviewed classifications. These inputs
    are claims, NOT independently authenticated by this pure function.

    If 50 reviewed positives exist, any unknown ranking ahead of the 50th
    reviewed positive must be resolved. If fewer than 50 exist, review the
    next highest unknowns first; iterate as classifications are resolved.
    Missing turnovers for any symbol not excluded are always blockers.
    """
    if type(include_public_symbols) is not bool:
        raise Top50PressureRejected("visibility_invalid")
    catalog = _symbols(catalog_symbols, "catalog")
    positive = _symbols(positively_reviewed_crypto, "positive")
    negative = _symbols(independently_excluded_noncrypto, "negative")
    if not 50 <= len(catalog) <= MAX_CONTRACTS:
        raise Top50PressureRejected("catalog_size_invalid")
    if not positive <= catalog or not negative <= catalog or positive & negative:
        raise Top50PressureRejected("classifications_conflict")
    if type(closed_turnover_usdt) is not dict or len(closed_turnover_usdt) > MAX_CONTRACTS:
        raise Top50PressureRejected("turnover_map_invalid")
    if not set(closed_turnover_usdt) <= catalog:
        raise Top50PressureRejected("turnover_not_in_catalog")
    totals = {s: _decimal(v) for s, v in closed_turnover_usdt.items()}
    unmeasured = catalog - frozenset(totals) - negative

    def key(symbol: str) -> tuple[Decimal, str]:
        return (-totals[symbol], symbol)

    measured_positive = sorted(positive & totals.keys(), key=key)
    unknown = sorted(totals.keys() - positive - negative, key=key)
    missing_positives = max(0, TOP_N - len(measured_positive))
    if missing_positives:
        priority = unknown[:missing_positives]
    else:
        cutoff_key = key(measured_positive[TOP_N - 1])
        priority = [s for s in unknown if key(s) < cutoff_key]
    mathematical_dominance = (
        len(measured_positive) >= TOP_N and not priority and not unmeasured
    )

    # A digest is an integrity summary, never a source attestation.
    def rows(symbols: list[str]) -> list[list[str]]:
        return [[s, format(totals[s], "f")] for s in symbols]

    result: dict[str, Any] = {
        "schema_version": "j1-top50-rank-pressure-v1",
        "status": (
            "conditional_top50_dominance_without_source_authentication"
            if mathematical_dominance else "identity_or_market_coverage_incomplete"
        ),
        "catalog_contracts": len(catalog),
        "closed_24h_contracts": len(totals),
        "excluded_claimed_noncrypto": len(negative),
        "reviewed_crypto_with_closed_24h": len(measured_positive),
        "reviewed_crypto_missing_24h": len(positive - totals.keys()),
        "unresolved_measured_contracts": len(unknown),
        "unresolved_unmeasured_contracts": len(unmeasured),
        "additional_crypto_reviews_needed_at_least": missing_positives,
        "highest_priority_review_count": len(priority),
        "highest_priority_review_sha256": _digest(rows(priority)),
        "conditional_selected_count": min(TOP_N, len(measured_positive)),
        "conditional_selected_sha256": _digest(rows(measured_positive[:TOP_N])),
        "conditional_mathematical_dominance": mathematical_dominance,
        # No amount of sorting proves a provider, vintage, identity or trade.
        "source_authenticated": False,
        "identity_pit_authenticated": False,
        "marketwide_top50_verified": False,
        "trading_enabled": False,
        "orders_sent": False,
        "network_requests": 0,
        "database_modified": False,
    }
    if include_public_symbols:
        result["review_priority_symbols_only"] = priority
        result["unmeasured_unresolved_symbols_only"] = sorted(unmeasured)
        result["conditional_selected_research_only"] = measured_positive[:TOP_N]
    return result
