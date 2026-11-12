"""J3/D302: one prospective-boundary, EX-POST mark study for real N50 data.

The preceding 24h ranking is frozen at checkpoint t. A distinct, genuinely
published t+1h outcome is read ONLY AFTER its close. There is no fitted model,
executable price, margin, funding settlement, liquidation, or order path.
The numbers are a descriptive, cost-assumption sensitivity; NEVER PnL.
"""
from __future__ import annotations

from contextlib import closing
from decimal import Context, Decimal, InvalidOperation, localcontext
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
import time
from typing import Any

from .j1_auto_research_epoch import HOUR_MS
from .j1_n50_managed_cycle import _pointer_read
from .j1_rest_incremental_owner import _DB_NAME
from .j1_rest_resume_readiness import (
    MAX_DB_BYTES, audit_existing_rest_resume,
)
from .j2_n50_private_screen import (
    ROOT, BARS, _metrics, _read_decimal,
)
from .market_data import DataValidationError
from .synthetic_cost_scenarios import (
    BPS_DENOMINATOR, _amount, _rate,
)
from scripts.audit_bybit_marketwide_closed24h import _strict_owner, _digest
from scripts.run_j1_current_ranked_epoch_once import load_private_ranked_scope

_CTX = Context(prec=512)
_LIMIT = 50 * (BARS + 1)


def _result(status: str) -> dict[str, Any]:
    return {
        "schema_version": "j3-n50-expost-onehour-mark-v1",
        "status": status,
        "quality": "provisional_private_expost_observation_only",
        "epoch_id": None,
        "scope_digest_sha256": None,
        "prior_closed_end_ms": None,
        "prior_published_observed_at_ms": None,
        "outcome_closed_end_ms": None,
        "outcome_published_observed_at_ms": None,
        "audited_contracts": 0,
        "observed_candles_per_contract": 0,
        "top_prior_return_sample_count": 0,
        "bottom_prior_return_sample_count": 0,
        "hypothetical_notional_per_asset_quote": None,
        "hypothetical_total_cost_per_asset_quote": None,
        "top_tail_long_expost_net_mark_sum_quote": None,
        "bottom_tail_short_expost_net_mark_sum_quote": None,
        "all50_long_expost_net_mark_sum_quote": None,
        "number_of_profitable_fills_verified": 0,
        "private_mark_observations": [],
        "snapshot_digest_sha256": None,
        "journal_integrity_verified": False,
        "real_market_data_identity_verified": False,
        "fill_prices_verified": False,
        "fees_and_funding_venue_verified": False,
        "intrabar_liquidation_validated": False,
        "out_of_sample_results_validated": False,
        "financial_backtest_approved": False,
        "approved_for_signals": False,
        "live_trading_authorized": False,
        "orders_sent": False,
        "network_requests": 0,
        "database_mutation_statements": 0,
        "systemd_modified": False,
    }


def evaluate_n50_expost_marks(
    *, root_directory: Path = ROOT,
    allow_private_readonly_audit: bool = False,
    include_private_symbols: bool = False,
    owner_ok: bool | None = None,
    now_ms: int | None = None,
    hypothetical_notional_quote: Decimal = Decimal("100"),
    entry_fee_bps: Decimal = Decimal("6"),
    exit_fee_bps: Decimal = Decimal("6"),
    entry_slippage_bps: Decimal = Decimal("3"),
    exit_slippage_bps: Decimal = Decimal("3"),
    tail_count: int = 5,
) -> dict[str, Any]:
    """Compare fixed previous-hour rank tails with the NEXT known mark close.

    This is NOT a prospective entry or OOS validation. All comparisons use a
    non-executable signal-close reference and identical hypothetical costs.
    """
    out = _result("optin_required")
    if allow_private_readonly_audit is not True:
        return out
    out["status"] = "blocked"
    permitted = ((os.name == "posix" and os.getuid() == os.geteuid()
                  and os.geteuid() != 0) if owner_ok is None else owner_ok)
    if (permitted is not True
            or not isinstance(root_directory, Path)
            or not root_directory.is_absolute()
            or root_directory.is_symlink()
            or type(include_private_symbols) is not bool
            or (now_ms is not None and type(now_ms) is not int)
            or type(tail_count) is not int or not 1 <= tail_count <= 25):
        return out
    try:
        _amount(hypothetical_notional_quote, "hypothetical notional")
        for value, name in (
            (entry_fee_bps, "entry fee"), (exit_fee_bps, "exit fee"),
            (entry_slippage_bps, "entry slippage"),
            (exit_slippage_bps, "exit slippage"),
        ):
            _rate(value, name, signed=False)
    except (DataValidationError, ValueError, TypeError):
        return out
    now = time.time_ns() // 1_000_000 if now_ms is None else now_ms
    if not 1_600_000_000_000 <= now < 4_102_444_800_000:
        return out
    try:
        if root_directory.resolve(strict=True) != root_directory:
            return out
        for path in (root_directory, root_directory / "epochs",
                     root_directory / "lease"):
            _strict_owner(path, directory=True)
            if path.is_symlink():
                return out
        pointer = _pointer_read(root_directory)
        if pointer is None:
            return _result("no_published_epoch")
        epoch_id = pointer["epoch_id"]
        epoch = root_directory / "epochs" / epoch_id
        scope_dir = epoch / "scope"
        journal = epoch / "journal"
        for path in (epoch, scope_dir, journal):
            _strict_owner(path, directory=True)
            if path.is_symlink():
                return out
        scope = load_private_ranked_scope(scope_dir, now_ms=now)
        symbols = scope["ranked_research_symbols_only"]
        digest = scope["scope_digest_sha256"]
        if (len(symbols) != 50 or len(set(symbols)) != 50
                or pointer["scope_digest_sha256"] != digest
                or pointer["catalog_post_observed_at_ms"] !=
                   scope["catalog_post_observed_at_ms"]
                or epoch_id != f"epoch-{scope['closed_hour_end_ms']:013d}"):
            return out
        db_path = journal / _DB_NAME
        if not db_path.exists() and not db_path.is_symlink():
            return _result("two_checkpoints_required")
        if db_path.is_symlink():
            return out
        audit = audit_existing_rest_resume(
            output_directory=journal, now_ms=now,
            allow_private_readonly_audit=True, expected_members=50,
            owner_ok=permitted,
        )
        if (audit.get("journal_integrity_verified") is not True
                or audit.get("journal_scope_digest_sha256") != digest
                or audit.get("reviewed_research_contracts") != 50
                or audit.get("historical_unpublished_hours") != 0
                or audit.get("historical_checkpoint_gaps_present") is not False
                or audit.get("research_closed_24h_ranked_contracts") != 50
                or audit.get("partial_unpublished_hour") is not False
                or audit.get("orders_sent") is not False
                or audit.get("live_trading_authorized") is not False
                or audit.get("status") != "no_gap"):
            return _result("unverified_journal_or_missing_pit")
        if (type(audit.get("published_hours")) is not int
                or audit["published_hours"] < 2):
            return _result("two_checkpoints_required")
        end = audit["last_published_end_ms"]
        if type(end) is not int or end % HOUR_MS or end > now or now-end > 2*HOUR_MS:
            return _result("stale_outcome_pit")
        _strict_owner(db_path, directory=False)
        if db_path.stat().st_size > MAX_DB_BYTES:
            return out
        with closing(sqlite3.connect(
            db_path.as_uri() + "?mode=ro", uri=True, timeout=2
        )) as db:
            db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN")
            checkpoints = db.execute(
                "SELECT end_ms,observed_at_ms,scope_digest,observed_contracts "
                "FROM published_hour ORDER BY end_ms DESC LIMIT 2"
            ).fetchall()
            if len(checkpoints) != 2:
                return out
            latest, previous = checkpoints
            signal_end, first_seen, first_digest, first_count = previous
            final_end, final_seen, final_digest, final_count = latest
            if (type(signal_end) is not int
                    or signal_end + HOUR_MS != final_end
                    or final_end != end
                    or first_digest != digest or final_digest != digest
                    or first_count != 50 or final_count != 50
                    or type(first_seen) is not int or type(final_seen) is not int
                    or not signal_end + 60_000 <= first_seen <= signal_end + 900_000
                    or not final_end + 60_000 <= final_seen <= final_end + 900_000
                    or not first_seen < final_seen <= now):
                return out
            start = signal_end - BARS * HOUR_MS
            candle_rows = db.execute(
                "SELECT symbol,open_ms,open,high,low,close,base_volume,"
                "quote_turnover,received_at_ms,digest_sha256 "
                "FROM candles WHERE open_ms>=? AND open_ms<? "
                "ORDER BY symbol,open_ms LIMIT ?",
                (start, final_end, _LIMIT+1),
            ).fetchall()
            if len(candle_rows) != _LIMIT:
                return _result("incomplete_25hour_window")
            by_symbol = {symbol: [] for symbol in symbols}
            hashes: list[tuple[str,int,str]] = []
            for row in candle_rows:
                symbol, opened, *rest = row
                if (symbol not in by_symbol
                        or type(opened) is not int
                        or opened != start+len(by_symbol[symbol])*HOUR_MS):
                    return out
                raw = rest[:6]
                observed_at, digest_line = rest[6:]
                if (type(observed_at) is not int or
                        observed_at < opened + HOUR_MS or
                        observed_at > (first_seen if opened < signal_end
                                       else final_seen) or
                        type(digest_line) is not str or
                        digest_line != _digest([symbol,(str(opened),*raw)])):
                    return out
                nums = tuple(_read_decimal(
                    v, positive=i < 4,
                ) for i, v in enumerate(raw))
                op,hi,lo,cl,base,quote = nums
                if hi < max(op,cl,lo) or lo > min(op,cl,hi):
                    return out
                by_symbol[symbol].append((opened, nums))
                hashes.append((symbol,opened,digest_line))
        if any(len(bars) != BARS+1 for bars in by_symbol.values()):
            return out
        with localcontext(_CTX):
            fixed_cost = (
                hypothetical_notional_quote * (
                    entry_fee_bps + exit_fee_bps +
                    entry_slippage_bps + exit_slippage_bps
                ) / BPS_DENOMINATOR
            )
            ranking = []
            for symbol in symbols:
                bars = by_symbol[symbol]
                past = _metrics(symbol, bars[:BARS])
                signal_close = bars[BARS-1][1][3]
                outcome_close = bars[BARS][1][3]
                outcome_change = outcome_close/signal_close - Decimal(1)
                ranking.append((
                    symbol, past["return_24bars_pct"], outcome_change,
                ))
            # Sorting uses ONLY prefix 24h values, never the t+1h label.
            ranking.sort(key=lambda item:(-item[1],item[0]))
            top = ranking[:tail_count]
            bottom = ranking[-tail_count:]
            top_net = sum((
                hypothetical_notional_quote*item[2]-fixed_cost
                for item in top
            ), Decimal(0))
            bottom_net = sum((
                -hypothetical_notional_quote*item[2]-fixed_cost
                for item in bottom
            ), Decimal(0))
            all_long_net = sum((
                hypothetical_notional_quote*item[2]-fixed_cost
                for item in ranking
            ), Decimal(0))
        out.update(
            status="expost_reference_only",
            epoch_id=epoch_id,
            scope_digest_sha256=digest,
            prior_closed_end_ms=signal_end,
            prior_published_observed_at_ms=first_seen,
            outcome_closed_end_ms=final_end,
            outcome_published_observed_at_ms=final_seen,
            audited_contracts=50, observed_candles_per_contract=BARS+1,
            top_prior_return_sample_count=tail_count,
            bottom_prior_return_sample_count=tail_count,
            hypothetical_notional_per_asset_quote=format(
                hypothetical_notional_quote,"f"),
            hypothetical_total_cost_per_asset_quote=format(fixed_cost,"f"),
            top_tail_long_expost_net_mark_sum_quote=format(top_net,"f"),
            bottom_tail_short_expost_net_mark_sum_quote=format(bottom_net,"f"),
            all50_long_expost_net_mark_sum_quote=format(all_long_net,"f"),
            snapshot_digest_sha256=sha256(json.dumps(
                hashes,ensure_ascii=True,separators=(",",":")
            ).encode("ascii")).hexdigest(),
            journal_integrity_verified=True,
        )
        if include_private_symbols:
            out["private_mark_observations"] = [
                {
                    "prior_return_rank":i+1,
                    "symbol":sym,
                    "prior_24bar_return_pct":format(past,"f"),
                    "next_closed_hour_mark_change_pct":format(
                        change*Decimal(100),"f"),
                    "hypothetical_reference_not_an_order":True,
                }
                for i,(sym,past,change) in enumerate(ranking)
            ]
        return out
    except (OSError, ValueError, TypeError, OverflowError, InvalidOperation,
            sqlite3.Error, UnicodeError):
        return _result("blocked")
