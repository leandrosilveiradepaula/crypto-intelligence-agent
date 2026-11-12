"""J2/D308: deterministic, DESCRIPTIVE N50 breakout/strength watchlist.

Uses only the audited owner-only D300 24 closed bars. This is not a
prediction, validated strategy, execution intent, risk approval or Top50
marketwide certification. The private source is never queried over network.
"""
from __future__ import annotations

from decimal import Context, Decimal, InvalidOperation, localcontext
import os
from pathlib import Path
import re
from typing import Any

from .j1_auto_research_epoch import HOUR_MS
from .j2_n50_private_screen import ROOT, audit_private_n50_research

_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_SYMBOL = re.compile(r"[A-Z0-9]{1,28}USDT\Z")
_DECIMAL = re.compile(r"-?(?:0|[1-9][0-9]{0,39})(?:\.[0-9]{1,90})?\Z")
_BREAKOUTS = frozenset({
    "above_prior_23h_high", "below_prior_23h_low", "inside_prior_23h_range",
})
_CONTEXT = Context(prec=50)
_MAX_ITEMS = 5


def _empty(status: str) -> dict[str, Any]:
    return {
        "schema_version": "j2-n50-descriptive-watchlist-v1",
        "status": status,
        "quality": "research_observation_not_a_trading_signal",
        "epoch_id": None,
        "window_digest_sha256": None,
        "latest_published_end_ms": None,
        "audited_assets": 0,
        "observed_up_breakout_candidates": 0,
        "observed_down_breakout_candidates": 0,
        "unclassified_volume_assets": 0,
        "up_breakout_watchlist": [],
        "down_breakout_watchlist": [],
        "rules": {
            "up": "closed_above_previous_23h_high AND outperform_BTC_24bars AND last_quote_turnover_at_least_prior23_mean",
            "down": "closed_below_previous_23h_low AND underperform_BTC_24bars AND last_quote_turnover_at_least_prior23_mean",
            "rank": "relative_BTC_strength_then_volume_intensity_then_24h_turnover",
            "history": "24_currently_closed_1h_bars_only",
            "atr": "descriptive_context_not_a_liquidation_or_risk_gate",
        },
        "owner_journal_integrity_verified": False,
        "marketwide_top50_verified": False,
        "crypto_identity_independently_verified": False,
        "source_authenticated": False,
        "approved_for_signals": False,
        "approved_for_live_use": False,
        "execution_intents_created": 0,
        "orders_sent": False,
        "network_requests": 0,
        "database_mutation_statements": 0,
        "systemd_modified": False,
    }


def _parse_decimal(raw: object, *, nonnegative: bool = False) -> Decimal:
    """Never convert financial values through float or accept NaN/infinity."""
    if type(raw) is not str or _DECIMAL.fullmatch(raw) is None:
        raise ValueError("invalid_research_metric")
    try:
        number = Decimal(raw)
    except (InvalidOperation, ValueError):
        raise ValueError("invalid_research_metric") from None
    if not number.is_finite() or (nonnegative and number < 0):
        raise ValueError("invalid_research_metric")
    return number


def _validated(snapshot: object) -> tuple[list[dict[str, Any]], Decimal]:
    if type(snapshot) is not dict:
        raise ValueError("research_snapshot_type")
    if (
        snapshot.get("schema_version") != "j2-private-n50-24closed-research-v1"
        or snapshot.get("status") != "descriptive_research_ready"
        or snapshot.get("owner_journal_integrity_verified") is not True
        or snapshot.get("audited_assets") != 50
        or type(snapshot.get("audited_assets")) is not int
        or snapshot.get("eligible_closed_bars_per_asset") != 24
        or type(snapshot.get("eligible_closed_bars_per_asset")) is not int
        or snapshot.get("btc_context_available") is not True
        or snapshot.get("marketwide_top50_verified") is not False
        or snapshot.get("crypto_identity_independently_verified") is not False
        or snapshot.get("source_authenticated") is not False
        or snapshot.get("approved_for_signals") is not False
        or snapshot.get("approved_for_live_use") is not False
        or snapshot.get("orders_sent") is not False
        or snapshot.get("network_requests") != 0
        or snapshot.get("database_mutation_statements") != 0
        or snapshot.get("systemd_modified") is not False
        or type(snapshot.get("epoch_id")) is not str
        or re.fullmatch(r"epoch-[0-9]{13}", snapshot["epoch_id"]) is None
        or type(snapshot.get("window_digest_sha256")) is not str
        or _DIGEST.fullmatch(snapshot["window_digest_sha256"]) is None
        or type(snapshot.get("scope_digest_sha256")) is not str
        or _DIGEST.fullmatch(snapshot["scope_digest_sha256"]) is None
    ):
        raise ValueError("unverified_research_snapshot")
    end = snapshot.get("latest_published_end_ms")
    as_of = snapshot.get("as_of_ms")
    if (
        type(end) is not int or end % HOUR_MS != 0
        or type(as_of) is not int
        or not end <= as_of <= end + 2 * HOUR_MS
    ):
        raise ValueError("invalid_closed_hour")
    source = snapshot.get("research_rows")
    if type(source) is not list or len(source) != 50:
        raise ValueError("incomplete_research_universe")
    btc_return = _parse_decimal(snapshot.get("btc_return_24bar_pct"))
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for rank, original in enumerate(source, 1):
        if type(original) is not dict:
            raise ValueError("invalid_research_row")
        symbol = original.get("symbol")
        if (
            type(symbol) is not str
            or _SYMBOL.fullmatch(symbol) is None
            or symbol in seen
            or type(original.get("descriptive_rank")) is not int
            or original["descriptive_rank"] != rank
            or original.get("last_closed_bar_breakout") not in _BREAKOUTS
            or original.get("approved_for_signals") is not False
            or original.get("orders_sent") is not False
        ):
            raise ValueError("invalid_research_row")
        seen.add(symbol)
        ret = _parse_decimal(original.get("return_24bars_pct"))
        relative = _parse_decimal(original.get("relative_vs_btc_pct_points"))
        turnover = _parse_decimal(
            original.get("quote_turnover_24bars_usdt"), nonnegative=True
        )
        atr = _parse_decimal(
            original.get("mean_true_range_14_pct"), nonnegative=True
        )
        ratio_raw = original.get("last_quote_turnover_vs_prior23_mean")
        ratio = (
            None if ratio_raw is None else
            _parse_decimal(ratio_raw, nonnegative=True)
        )
        with localcontext(_CONTEXT):
            if ret - btc_return != relative:
                raise ValueError("inconsistent_btc_relative_return")
        if rows and (
            ret > rows[-1]["return"]
            or (ret == rows[-1]["return"] and symbol < rows[-1]["symbol"])
        ):
            raise ValueError("noncausal_research_order")
        rows.append({
            "symbol": symbol, "return": ret, "relative": relative,
            "turnover": turnover, "atr": atr, "volume_ratio": ratio,
            "breakout": original["last_closed_bar_breakout"],
        })
    if "BTCUSDT" not in seen or next(
        row["return"] for row in rows if row["symbol"] == "BTCUSDT"
    ) != btc_return:
        raise ValueError("missing_or_inconsistent_btc")
    return rows, btc_return


def build_descriptive_watchlist(
    snapshot: object, *, include_private_symbols: bool = False,
) -> dict[str, Any]:
    """Pure fail-closed projection of *audited* D300 research; no market actions.

    A volume ratio >=1, a confirmed 23h closed breakout and relative
    BTC strength define observations, not recommended positions. Ties are
    deterministic, ATR is context only, and the top five are not optimized.
    """
    out = _empty("source_not_ready")
    if type(include_private_symbols) is not bool:
        return _empty("invalid_privacy_option")
    try:
        rows, _ = _validated(snapshot)
        up = [row for row in rows if
              row["breakout"] == "above_prior_23h_high"
              and row["relative"] > 0
              and row["turnover"] > 0
              and row["volume_ratio"] is not None
              and row["volume_ratio"] >= 1]
        down = [row for row in rows if
                row["breakout"] == "below_prior_23h_low"
                and row["relative"] < 0
                and row["turnover"] > 0
                and row["volume_ratio"] is not None
                and row["volume_ratio"] >= 1]
        up.sort(key=lambda r: (
            -r["relative"], -r["volume_ratio"], -r["turnover"], r["symbol"],
        ))
        down.sort(key=lambda r: (
            r["relative"], -r["volume_ratio"], -r["turnover"], r["symbol"],
        ))
        out.update(
            status="descriptive_watchlist_ready",
            epoch_id=snapshot["epoch_id"],
            window_digest_sha256=snapshot["window_digest_sha256"],
            latest_published_end_ms=snapshot["latest_published_end_ms"],
            audited_assets=50,
            observed_up_breakout_candidates=len(up),
            observed_down_breakout_candidates=len(down),
            unclassified_volume_assets=sum(
                r["volume_ratio"] is None for r in rows
            ),
            owner_journal_integrity_verified=True,
        )
        if include_private_symbols:
            def display(row: dict[str, Any]) -> dict[str, Any]:
                return {
                    "symbol": row["symbol"],
                    "relative_vs_btc_pct_points": format(row["relative"], "f"),
                    "return_24bars_pct": format(row["return"], "f"),
                    "quote_turnover_24bars_usdt": format(row["turnover"], "f"),
                    "last_quote_turnover_vs_prior23_mean": format(
                        row["volume_ratio"], "f"
                    ),
                    "mean_true_range_14_pct": format(row["atr"], "f"),
                    "breakout": row["breakout"],
                    "approved_for_signals": False,
                    "orders_sent": False,
                }
            out["up_breakout_watchlist"] = [
                display(row) for row in up[:_MAX_ITEMS]
            ]
            out["down_breakout_watchlist"] = [
                display(row) for row in down[:_MAX_ITEMS]
            ]
        return out
    except (ValueError, TypeError, InvalidOperation, OverflowError):
        return _empty("research_integrity_abstain")


def observe_private_n50_watchlist(
    *, root_directory: Path = ROOT,
    allow_private_readonly_audit: bool = False,
    enable_descriptive_watchlist: bool = False,
    include_private_symbols: bool = False,
    confirm_private_symbol_output: bool = False,
    owner_ok: bool | None = None,
    now_ms: int | None = None,
) -> dict[str, Any]:
    """Read-only owner entrypoint; private symbols require separate opt-in."""
    if (
        allow_private_readonly_audit is not True
        or enable_descriptive_watchlist is not True
    ):
        return _empty("owner_optin_required")
    if (
        type(include_private_symbols) is not bool
        or type(confirm_private_symbol_output) is not bool
        or (include_private_symbols and not confirm_private_symbol_output)
    ):
        return _empty("private_symbol_output_not_approved")
    owner = (
        os.name == "posix" and os.getuid() == os.geteuid()
        and os.geteuid() != 0
        if owner_ok is None else owner_ok
    )
    if (
        owner is not True or type(owner_ok) not in (bool, type(None))
        or type(root_directory) is not Path
        or type(now_ms) not in (int, type(None))
    ):
        return _empty("owner_environment_abstain")
    # D300 performs private owner/DAC, causal scope, every digest, timestamp,
    # replay and 50x24 source audit BEFORE a row becomes research material.
    source = audit_private_n50_research(
        root_directory=root_directory,
        allow_private_readonly_audit=True,
        include_private_symbols=True,
        owner_ok=owner,
        now_ms=now_ms,
    )
    return build_descriptive_watchlist(
        source, include_private_symbols=include_private_symbols
    )
