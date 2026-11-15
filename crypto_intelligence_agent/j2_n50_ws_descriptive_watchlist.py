"""J2/WS-WATCH1: owner-only WS N50 observations -> D308 shortlist (no signals).

The SOURCE is the existing J2/WS-READ1 50x24 SQLite replay, never logs,
REST or fresh venue requests. Reuse D308 Decimal/ranking rules; do not infer
probabilities, entries, fills, risk approvals or marketwide crypto identity.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import os
import re
import time
from typing import Any

from .bybit_closed_stream_cache import HOUR_MS
from .j2_n50_descriptive_watchlist import (
    _DIGEST, _MAX_ITEMS, _parse_decimal, _validated_descriptive_rows,
    _rank_descriptive_candidates, _display_descriptive_candidate,
)
from .j2_n50_ws_private_screen import observe_active_private_ws_n50_24closed

_MIN_MS = 1_600_000_000_000
_MAX_MS = 4_102_444_800_000
_BREAKOUTS = frozenset({
    "above_prior_23h_high", "below_prior_23h_low", "inside_prior_23h_range",
})
_PROTECTED_FALSE = (
    "formal_d323_24h_verified", "continuous_collector_verified",
    "rotation_36h_live_verified", "marketwide_top50_verified",
    "crypto_identity_independently_verified", "source_authenticated",
    "approved_for_signals", "approved_for_live_use",
    "financial_backtest_approved", "orders_sent", "systemd_modified",
)


def _empty(status: str) -> dict[str, Any]:
    """Never leak raw source rows or digests on a failed owner audit."""
    return {
        "schema_version": "j2-n50-ws-descriptive-watchlist-v1",
        "status": status,
        "quality": "private_ws_observations_not_trading_signals",
        "latest_closed_end_ms": None,
        "window_digest_sha256": None,
        "audited_assets": 0,
        "eligible_closed_bars_per_asset": 0,
        "btc_context_available": False,
        "observed_up_breakout_candidates": 0,
        "observed_down_breakout_candidates": 0,
        "unclassified_volume_assets": 0,
        "up_breakout_watchlist": [],
        "down_breakout_watchlist": [],
        "rules": {
            "up": "last_close_above_previous_23h_high_AND_outperform_BTC_AND_volume_ratio_ge_1",
            "down": "last_close_below_previous_23h_low_AND_underperform_BTC_AND_volume_ratio_ge_1",
            "rank": "BTC_relative_change_then_turnover_intensity_then_turnover_then_symbol",
            "window": "24_closed_1h_bars_from_same_WS_epoch_only",
            "risk": "ATR_context_only_not_stop_liquidation_or_probability",
        },
        "ws_journal_integrity_replayed": False,
        "formal_d323_24h_verified": False,
        "continuous_collector_verified": False,
        "rotation_36h_live_verified": False,
        "marketwide_top50_verified": False,
        "crypto_identity_independently_verified": False,
        "source_authenticated": False,
        "approved_for_signals": False,
        "approved_for_live_use": False,
        "financial_backtest_approved": False,
        "execution_intents_created": 0,
        "orders_sent": False,
        "network_requests": 0,
        "database_mutation_statements": 0,
        "systemd_modified": False,
    }


def _validated_ws_source(
    source: object, *, now_ms: int,
) -> list[dict[str, Any]]:
    if type(source) is not dict:
        raise ValueError("ws_source_not_a_mapping")
    if (
        source.get("schema_version") != "j2-ws-n50-descriptive-24closed-v1"
        or source.get("status") != "ws_n50_descriptive_24h_ready"
        or source.get("quality") != "private_ws_24h_descriptive_research_only"
        or source.get("ws_journal_integrity_replayed") is not True
        or type(source.get("audited_assets")) is not int
        or source["audited_assets"] != 50
        or type(source.get("eligible_closed_bars_per_asset")) is not int
        or source["eligible_closed_bars_per_asset"] != 24
        or source.get("btc_context_available") is not True
        or any(source.get(name) is not False for name in _PROTECTED_FALSE)
        or type(source.get("network_requests")) is not int
        or source["network_requests"] != 0
        or type(source.get("database_mutation_statements")) is not int
        or source["database_mutation_statements"] != 0
        or any(type(source.get(name)) is not str
               or _DIGEST.fullmatch(source[name]) is None
               for name in (
                   "window_digest_sha256", "ranked_scope_sha256",
                   "ws_metadata_sha256",
               ))
    ):
        raise ValueError("ws_source_not_owner_replayed")
    close = source.get("latest_closed_end_ms")
    if (
        type(close) is not int
        or not _MIN_MS <= close < _MAX_MS
        or close % HOUR_MS != 0
        or type(now_ms) is not int
        or not _MIN_MS <= now_ms < _MAX_MS
        or not 180_000 <= now_ms - close < HOUR_MS - 60_000
    ):
        raise ValueError("ws_source_wrong_decision_clock")
    originals = source.get("research_rows")
    if type(originals) is not list or len(originals) != 50:
        raise ValueError("ws_source_symbols_missing")
    btc_rows = [row for row in originals
                if type(row) is dict and row.get("symbol") == "BTCUSDT"]
    if len(btc_rows) != 1:
        raise ValueError("BTC_context_missing_or_duplicate")
    btc_return = _parse_decimal(btc_rows[0].get("return_24bars_pct"))
    rows = _validated_descriptive_rows(originals, btc_return)
    counts = (
        ("descriptive_up_breakouts", "above_prior_23h_high"),
        ("descriptive_down_breakouts", "below_prior_23h_low"),
        ("descriptive_inside_bars", "inside_prior_23h_range"),
    )
    for key, breakout in counts:
        count = source.get(key)
        if (type(count) is not int
                or count != sum(row["breakout"] == breakout for row in rows)):
            raise ValueError("ws_source_breakout_counts_inconsistent")
    return rows


def build_ws_descriptive_watchlist(
    source: object, *, now_ms: int, include_private_symbols: bool = False,
) -> dict[str, Any]:
    """Pure closed-window projection. Private identities opt-in only.

    This does not claim that D323 passed: the 24-bar source replay is
    independently validated by J2's WS reader, but D323 also audits service
    isolation/owner epoch and is a distinct gate.
    """
    if type(include_private_symbols) is not bool:
        return _empty("invalid_privacy_option")
    try:
        rows = _validated_ws_source(source, now_ms=now_ms)
        up, down = _rank_descriptive_candidates(rows)
        output = _empty("ws_descriptive_watchlist_ready")
        output.update(
            latest_closed_end_ms=source["latest_closed_end_ms"],
            window_digest_sha256=source["window_digest_sha256"],
            audited_assets=50,
            eligible_closed_bars_per_asset=24,
            btc_context_available=True,
            observed_up_breakout_candidates=len(up),
            observed_down_breakout_candidates=len(down),
            unclassified_volume_assets=sum(
                row["volume_ratio"] is None for row in rows
            ),
            ws_journal_integrity_replayed=True,
        )
        if include_private_symbols:
            output["up_breakout_watchlist"] = [
                _display_descriptive_candidate(row) for row in up[:_MAX_ITEMS]
            ]
            output["down_breakout_watchlist"] = [
                _display_descriptive_candidate(row) for row in down[:_MAX_ITEMS]
            ]
        return output
    except (ValueError, TypeError, InvalidOperation, OverflowError,
            KeyError, AttributeError):
        return _empty("ws_research_integrity_abstain")


def observe_active_ws_n50_descriptive_watchlist(
    *, allow_private_readonly_research: bool = False,
    enable_descriptive_watchlist: bool = False,
    include_private_symbols: bool = False,
    confirm_private_symbol_output: bool = False,
    now_ms: int | None = None,
) -> dict[str, Any]:
    """Compose the existing owner-only D321/WS reader; no new file/DB access."""
    if (allow_private_readonly_research is not True
            or enable_descriptive_watchlist is not True):
        return _empty("owner_optin_required")
    if (type(include_private_symbols) is not bool
            or type(confirm_private_symbol_output) is not bool
            or (include_private_symbols and not confirm_private_symbol_output)):
        return _empty("private_symbols_optin_required")
    if (os.name != "posix" or os.getuid() != os.geteuid()
            or os.geteuid() == 0
            or now_ms is not None and type(now_ms) is not int):
        return _empty("owner_environment_abstain")
    now = time.time_ns() // 1_000_000 if now_ms is None else now_ms
    if type(now) is not int or not _MIN_MS <= now < _MAX_MS:
        return _empty("owner_environment_abstain")
    try:
        source = observe_active_private_ws_n50_24closed(
            allow_private_readonly_research=True,
            include_private_symbols=True,
            now_ms=now,
        )
        return build_ws_descriptive_watchlist(
            source, now_ms=now, include_private_symbols=include_private_symbols,
        )
    except (OSError, ValueError, TypeError, RuntimeError, OverflowError):
        return _empty("ws_owner_readonly_abstain")
