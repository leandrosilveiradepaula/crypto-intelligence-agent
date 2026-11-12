"""J2/D300: descriptive 24-closed-bar research on audited private N50.

This is NOT the synthetic J2 signal engine, an order generator, a strategy,
a marketwide crypto identity certificate, or an evaluation of profit. The
only input is an owner-only D294 epoch whose D290/D292 SQLite replay passes.
No network, writes, credentials or exchange endpoints exist here.
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

from crypto_intelligence_agent.j1_auto_research_epoch import HOUR_MS
from crypto_intelligence_agent.j1_n50_managed_cycle import (
    ACTIVE_FILE, _pointer_read,
)
from crypto_intelligence_agent.j1_rest_incremental_owner import _DB_NAME
from crypto_intelligence_agent.j1_rest_resume_readiness import (
    MAX_DB_BYTES, audit_existing_rest_resume,
)
from scripts.audit_bybit_marketwide_closed24h import (
    CensusAbstain, _digest, _strict_owner,
)
from scripts.run_j1_current_ranked_epoch_once import load_private_ranked_scope

ROOT = Path("/home/cia-probe/agent/j1-n50-managed-d296-private")
MATH = Context(prec=50)
BARS = 24
ATR_BARS = 14
MAX_VALUE_DIGITS = 40
MAX_EXPONENT = 35
MIN_EXPONENT = -24


class PrivateResearchAbstain(ValueError):
    """An immutable audit/provenance/UTC gate prevented research."""


def _result(status: str) -> dict[str, Any]:
    return {
        "schema_version": "j2-private-n50-24closed-research-v1",
        "status": status,
        "quality": "provisional_private_research_only",
        "epoch_id": None,
        "scope_digest_sha256": None,
        "latest_published_end_ms": None,
        "as_of_ms": None,
        "eligible_closed_bars_per_asset": 0,
        "audited_assets": 0,
        "btc_context_available": False,
        "btc_return_24bar_pct": None,
        "descriptive_up_breakouts": 0,
        "descriptive_down_breakouts": 0,
        "descriptive_inside_bars": 0,
        "research_rows": [],
        "window_digest_sha256": None,
        "owner_journal_integrity_verified": False,
        "marketwide_top50_verified": False,
        "crypto_identity_independently_verified": False,
        "source_authenticated": False,
        "approved_for_signals": False,
        "approved_for_live_use": False,
        "orders_sent": False,
        "network_requests": 0,
        "database_mutation_statements": 0,
        "systemd_modified": False,
    }


def _read_decimal(raw: Any, *, positive: bool) -> Decimal:
    if type(raw) is not str or not 1 <= len(raw) <= 90:
        raise PrivateResearchAbstain("invalid_decimal_field")
    try:
        value = Decimal(raw)
    except (InvalidOperation, ValueError):
        raise PrivateResearchAbstain("invalid_decimal_field") from None
    t = value.as_tuple()
    if (not value.is_finite() or len(t.digits) > MAX_VALUE_DIGITS
            or t.exponent < MIN_EXPONENT or value.adjusted() > MAX_EXPONENT
            or value < 0 or (positive and value == 0)):
        raise PrivateResearchAbstain("decimal_out_of_bounds")
    return value


def _metrics(symbol: str, bars: list[tuple[int, tuple[Decimal, ...]]]) -> dict:
    """Pure descriptive arithmetic using ONLY these 24 consecutive closed bars.

    The first OHLC open is the return denominator; mean true range for the
    final 14 bars uses each prior close, not future market data.
    """
    if len(bars) != BARS:
        raise PrivateResearchAbstain("insufficient_closed_bars")
    with localcontext(MATH):
        first_open = bars[0][1][0]
        last_close = bars[-1][1][3]
        change = (last_close / first_open - 1) * 100
        true_ranges: list[Decimal] = []
        for i, (_, (opened, high, low, closed, base, quote)) in enumerate(bars):
            previous_close = bars[i - 1][1][3] if i else None
            tr = (high - low if previous_close is None else max(
                high - low, abs(high - previous_close), abs(low - previous_close)
            ))
            true_ranges.append(tr)
        mean_true_range = sum(true_ranges[-ATR_BARS:], Decimal(0)) / ATR_BARS
        atr_pct = mean_true_range / last_close * 100
        prior_quote = sum((row[1][5] for row in bars[:-1]), Decimal(0))
        volume_ratio = (bars[-1][1][5] * Decimal(23) / prior_quote
                        if prior_quote > 0 else None)
        turnover = prior_quote + bars[-1][1][5]
        prior_high = max(row[1][1] for row in bars[:-1])
        prior_low = min(row[1][2] for row in bars[:-1])
        breakout = ("above_prior_23h_high" if last_close > prior_high
                    else "below_prior_23h_low" if last_close < prior_low
                    else "inside_prior_23h_range")
    return {
        "symbol": symbol,
        "return_24bars_pct": change,
        "mean_true_range_14_pct": atr_pct,
        "last_quote_turnover_vs_prior23_mean": volume_ratio,
        "quote_turnover_24bars_usdt": turnover,
        "last_closed_bar_breakout": breakout,
    }


def _text(value: Decimal | None) -> str | None:
    return format(value, "f") if value is not None else None


def audit_private_n50_research(
    *, root_directory: Path = ROOT,
    allow_private_readonly_audit: bool = False,
    include_private_symbols: bool = False,
    owner_ok: bool | None = None,
    now_ms: int | None = None,
) -> dict[str, Any]:
    """One fully replayed owner snapshot; descriptive stats never emit orders."""
    out = _result("owner_optin_required")
    if allow_private_readonly_audit is not True:
        return out
    out["status"] = "blocked"
    owner = ((os.name == "posix" and os.getuid() == os.geteuid()
              and os.geteuid() != 0)
             if owner_ok is None else owner_ok)
    if (owner is not True
            or type(include_private_symbols) is not bool
            or not isinstance(root_directory, Path)
            or not root_directory.is_absolute()
            or root_directory.is_symlink()
            or (now_ms is not None and type(now_ms) is not int)):
        return out
    now = time.time_ns() // 1_000_000 if now_ms is None else now_ms
    if not 1_600_000_000_000 <= now < 4_102_444_800_000:
        return out
    try:
        if root_directory.resolve(strict=True) != root_directory:
            return out
        for directory in (root_directory, root_directory / "epochs",
                          root_directory / "lease"):
            _strict_owner(directory, directory=True)
            if directory.is_symlink():
                return out
        pointer = _pointer_read(root_directory)
        if pointer is None:
            return _result("awaiting_first_epoch")
        epoch_id = pointer["epoch_id"]
        epoch = root_directory / "epochs" / epoch_id
        scope_dir = epoch / "scope"
        journal_dir = epoch / "journal"
        for directory in (epoch, scope_dir, journal_dir):
            _strict_owner(directory, directory=True)
            if directory.is_symlink():
                return out
        scope = load_private_ranked_scope(scope_dir, now_ms=now)
        symbols = scope["ranked_research_symbols_only"]
        digest = scope["scope_digest_sha256"]
        if (len(symbols) != 50
                or len(set(symbols)) != 50
                or pointer["scope_digest_sha256"] != digest
                or pointer["catalog_post_observed_at_ms"]
                   != scope["catalog_post_observed_at_ms"]
                or epoch_id != f"epoch-{scope['closed_hour_end_ms']:013d}"):
            return out
        audit = audit_existing_rest_resume(
            output_directory=journal_dir, now_ms=now,
            allow_private_readonly_audit=True, expected_members=50,
            owner_ok=owner,
        )
        if (audit.get("journal_integrity_verified") is not True
                or audit.get("journal_scope_digest_sha256") != digest
                or audit.get("reviewed_research_contracts") != 50
                or audit.get("research_closed_24h_ranked_contracts") != 50
                or audit.get("historical_unpublished_hours") != 0
                or audit.get("historical_checkpoint_gaps_present") is not False
                or audit.get("partial_unpublished_hour") is not False
                or audit.get("orders_sent") is not False
                or audit.get("source_authenticated") is not False
                or audit.get("status") != "no_gap"
                or type(audit.get("published_hours")) is not int
                or audit["published_hours"] < 1):
            return _result("no_current_integral_checkpoint")
        end = audit["last_published_end_ms"]
        if (type(end) is not int or end % HOUR_MS
                or end > now or now - end > 2 * HOUR_MS):
            return _result("stale_or_invalid_closed_hour")
        db_path = journal_dir / _DB_NAME
        _strict_owner(db_path, directory=False)
        if db_path.is_symlink() or db_path.stat().st_size > MAX_DB_BYTES:
            return out
        lower = end - BARS * HOUR_MS
        with closing(sqlite3.connect(
            db_path.as_uri() + "?mode=ro", uri=True, timeout=2,
        )) as db:
            db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN")
            observed = db.execute(
                "SELECT end_ms,scope_digest,observed_contracts FROM published_hour "
                "ORDER BY end_ms DESC LIMIT 1"
            ).fetchone()
            if observed != (end, digest, 50):
                return out
            rows = db.execute(
                "SELECT symbol,open_ms,open,high,low,close,base_volume,"
                "quote_turnover,received_at_ms,digest_sha256 "
                "FROM candles WHERE open_ms>=? AND open_ms<? "
                "ORDER BY symbol,open_ms LIMIT ?",
                (lower, end, len(symbols)*BARS + 1),
            ).fetchall()
            if len(rows) != len(symbols)*BARS:
                return _result("closed_window_missing_or_incomplete")
            by_symbol: dict[str, list[tuple[int, tuple[Decimal, ...]]]] = {
                symbol: [] for symbol in symbols
            }
            observed_hashes: list[tuple[str, int, str]] = []
            for row in rows:
                symbol, opened, *rest = row
                if (symbol not in by_symbol
                        or type(opened) is not int
                        or opened != lower + len(by_symbol[symbol])*HOUR_MS):
                    return out
                raw = rest[:6]
                received, recorded_digest = rest[6:]
                if (type(received) is not int or received < opened+HOUR_MS
                        or received > now or type(recorded_digest) is not str
                        or recorded_digest != _digest(
                            [symbol, (str(opened), *raw)]
                        )):
                    return out
                values = tuple(_read_decimal(
                    v, positive=i < 4,
                ) for i,v in enumerate(raw))
                opened_price, high, low, closed, base, quote = values
                if high < max(opened_price, low, closed) or low > min(
                    opened_price, high, closed
                ):
                    return out
                by_symbol[symbol].append((opened, values))
                observed_hashes.append((symbol, opened, recorded_digest))
        if any(len(v) != BARS for v in by_symbol.values()):
            return out
        research = [_metrics(symbol, by_symbol[symbol]) for symbol in symbols]
        benchmark = next((x for x in research if x["symbol"] == "BTCUSDT"), None)
        btc_change = benchmark["return_24bars_pct"] if benchmark else None
        with localcontext(MATH):
            for x in research:
                x["relative_vs_btc_pct_points"] = (
                    x["return_24bars_pct"] - btc_change
                    if btc_change is not None else None
                )
        research.sort(key=lambda item: (-item["return_24bars_pct"], item["symbol"]))
        out.update(
            status=("descriptive_research_ready" if benchmark
                    else "btc_context_missing_research_only"),
            epoch_id=epoch_id, scope_digest_sha256=digest,
            latest_published_end_ms=end, as_of_ms=now,
            eligible_closed_bars_per_asset=BARS,
            audited_assets=len(research),
            btc_context_available=benchmark is not None,
            btc_return_24bar_pct=_text(btc_change),
            descriptive_up_breakouts=sum(
                x["last_closed_bar_breakout"]=="above_prior_23h_high"
                for x in research
            ),
            descriptive_down_breakouts=sum(
                x["last_closed_bar_breakout"]=="below_prior_23h_low"
                for x in research
            ),
            descriptive_inside_bars=sum(
                x["last_closed_bar_breakout"]=="inside_prior_23h_range"
                for x in research
            ),
            window_digest_sha256=sha256(json.dumps(
                observed_hashes, ensure_ascii=True,
                separators=(",", ":"),
            ).encode("ascii")).hexdigest(),
            owner_journal_integrity_verified=True,
        )
        if include_private_symbols:
            out["research_rows"] = [
                {
                    "descriptive_rank": i,
                    "symbol": x["symbol"],
                    "return_24bars_pct": _text(x["return_24bars_pct"]),
                    "relative_vs_btc_pct_points":
                        _text(x["relative_vs_btc_pct_points"]),
                    "mean_true_range_14_pct": _text(
                        x["mean_true_range_14_pct"]
                    ),
                    "quote_turnover_24bars_usdt": _text(
                        x["quote_turnover_24bars_usdt"]
                    ),
                    "last_quote_turnover_vs_prior23_mean": _text(
                        x["last_quote_turnover_vs_prior23_mean"]
                    ),
                    "last_closed_bar_breakout": x["last_closed_bar_breakout"],
                    "approved_for_signals": False,
                    "orders_sent": False,
                } for i,x in enumerate(research, 1)
            ]
        return out
    except (OSError, ValueError, TypeError, OverflowError, InvalidOperation,
            sqlite3.Error, CensusAbstain, UnicodeError):
        return _result("blocked")
