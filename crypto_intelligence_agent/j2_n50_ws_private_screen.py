"""J2/WS-READ1: descriptive N50 from the existing audited WS SQLite journal.

No REST fallback, new storage, venue transport, fills, order intent or
marketwide/crypto-only certification. This composes D313's local journal
replay with J2/D300's existing closed-24h descriptive metrics.
"""
from __future__ import annotations

from contextlib import closing
from decimal import Decimal, localcontext
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
import stat
from typing import Any
from urllib.parse import quote

from .bybit_closed_stream_cache import (
    HOUR_MS, OfflineReviewedStreamScope,
    SQLiteOfflineClosedStreamJournal, _validated_payload,
)
from .j1_auto_research_epoch import validate_ranked_research_scope
from .j2_n50_private_screen import (
    BARS, MATH, _metrics, _read_decimal, _text,
)
from .market_data import DataGapError, DataValidationError

_COUNT = 50
_ROWS = _COUNT * BARS
_MIN_MS = 1_600_000_000_000
_MAX_MS = 4_102_444_800_000
_EARLIEST_AFTER_CLOSE_MS = 180_000
_LATEST_AFTER_CLOSE_MS = HOUR_MS - 60_000


def _blank(status: str) -> dict[str, Any]:
    return {
        "schema_version": "j2-ws-n50-descriptive-24closed-v1",
        "status": status,
        "quality": "private_ws_24h_descriptive_research_only",
        "latest_closed_end_ms": None,
        "audited_assets": 0,
        "eligible_closed_bars_per_asset": 0,
        "btc_context_available": False,
        "descriptive_up_breakouts": 0,
        "descriptive_down_breakouts": 0,
        "descriptive_inside_bars": 0,
        "research_rows": [],
        "ws_journal_integrity_replayed": False,
        "window_digest_sha256": None,
        "ranked_scope_sha256": None,
        "ws_metadata_sha256": None,
        "formal_d323_24h_verified": False,
        "continuous_collector_verified": False,
        "rotation_36h_live_verified": False,
        "marketwide_top50_verified": False,
        "crypto_identity_independently_verified": False,
        "source_authenticated": False,
        "approved_for_signals": False,
        "approved_for_live_use": False,
        "financial_backtest_approved": False,
        "orders_sent": False,
        "network_requests": 0,
        "database_mutation_statements": 0,
        "systemd_modified": False,
    }


def _private_journal_file(journal: SQLiteOfflineClosedStreamJournal) -> Path:
    """Require the isolated owner WS journal, never the halted REST one."""
    path = journal.path
    if (type(path) is not Path or not path.is_absolute()
            or path.name != "ws-confirmed.sqlite"
            or path.is_symlink()
            or path.resolve(strict=True) != path):
        raise DataValidationError("unsafe WS journal pathname")
    parent = path.parent
    root_stat = parent.lstat()
    file_stat = path.lstat()
    if (not stat.S_ISDIR(root_stat.st_mode)
            or root_stat.st_uid != os.geteuid()
            or stat.S_IMODE(root_stat.st_mode) != 0o700
            or not stat.S_ISREG(file_stat.st_mode)
            or file_stat.st_uid != os.geteuid()
            or file_stat.st_nlink != 1
            or stat.S_IMODE(file_stat.st_mode) != 0o600):
        raise DataValidationError("owner-only WS journal DAC rejected")
    return path


def _audited_window(
    *, journal: SQLiteOfflineClosedStreamJournal,
    ws_scope: OfflineReviewedStreamScope,
    members: tuple[str, ...],
    decision_at_ms: int,
    observed_at_ms: int,
):
    """Verify 50x24 and the last close using J1's complete SQLite replay."""
    audit = journal.audit(
        scope=ws_scope, decision_at_ms=decision_at_ms,
        as_of_ms=observed_at_ms, hour_evidence_symbols=members,
    )
    if (audit.status != "offline_reviewed_24h_complete_not_top50"
            or audit.complete_24h_symbols != _COUNT
            or audit.missing_24h_symbols != 0
            or audit.hour_evidence_expected != _COUNT
            or audit.hour_evidence_confirmed != _COUNT
            or not isinstance(audit.rank_digest_sha256, str)
            or len(audit.rank_digest_sha256) != 64
            or not isinstance(audit.hour_evidence_sha256, str)
            or len(audit.hour_evidence_sha256) != 64
            or audit.observed_symbols != _COUNT):
        raise DataGapError("24h WS journal not yet independently complete")
    return audit


def research_private_ws_n50_24closed(
    *, ranked_scope: dict,
    ws_scope: OfflineReviewedStreamScope,
    journal: SQLiteOfflineClosedStreamJournal,
    decision_at_ms: int,
    observed_at_ms: int,
    allow_private_readonly_research: bool = False,
    include_private_symbols: bool = False,
    owner_ok: bool | None = None,
) -> dict[str, Any]:
    """One 24h descriptive snapshot. Never a signal, live rank or approved PIT.

    Works with already owner-reviewed in-memory scope and one immutable
    private WS journal. It does not read an active pointer or open any WS.
    A privileged owner caller remains responsible for selecting the CURRENT
    D321 pointer before passing the scope and journal to this function.
    """
    out = _blank("owner_optin_required")
    if allow_private_readonly_research is not True:
        return out
    out["status"] = "ws_24h_readonly_integrity_abstain"
    allowed_owner = (
        os.name == "posix" and os.getuid() == os.geteuid()
        and os.geteuid() != 0
        if owner_ok is None else owner_ok
    )
    if (allowed_owner is not True
            or type(owner_ok) not in (bool, type(None))
            or type(include_private_symbols) is not bool
            or type(ranked_scope) is not dict
            or type(ws_scope) is not OfflineReviewedStreamScope
            or type(journal) is not SQLiteOfflineClosedStreamJournal
            or type(decision_at_ms) is not int
            or type(observed_at_ms) is not int
            or not _MIN_MS <= decision_at_ms < _MAX_MS
            or decision_at_ms % HOUR_MS
            or not _EARLIEST_AFTER_CLOSE_MS <= observed_at_ms - decision_at_ms
                   < _LATEST_AFTER_CLOSE_MS):
        return out
    try:
        symbols, binding = validate_ranked_research_scope(
            ranked_scope, now_ms=observed_at_ms, max_assets=_COUNT,
        )
        members = tuple(sorted(symbols))
        if (len(ws_scope.contracts) != _COUNT
                or {x.symbol for x in ws_scope.contracts} != set(members)
                or ws_scope.observed_at_ms >= decision_at_ms - (BARS - 1)*HOUR_MS):
            return out
        path = _private_journal_file(journal)
        first = _audited_window(
            journal=journal, ws_scope=ws_scope, members=members,
            decision_at_ms=decision_at_ms, observed_at_ms=observed_at_ms,
        )
        start = decision_at_ms - BARS * HOUR_MS
        by_member: dict[str, list[tuple[int, tuple[Decimal, ...]]]] = {
            sym: [] for sym in symbols
        }
        fingerprints: list[tuple[str, int, str]] = []
        uri = "file:" + quote(path.as_posix(), safe="/") + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True, timeout=2)) as db:
            db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN")
            rows = db.execute(
                "SELECT symbol,open_ms,received_ms,registry_sha256,payload,digest "
                "FROM confirmed WHERE open_ms>=? AND open_ms<? "
                "ORDER BY symbol,open_ms LIMIT ?",
                (start, decision_at_ms, _ROWS + 1),
            ).fetchall()
            if len(rows) != _ROWS:
                raise DataGapError("24h research bars absent")
            for symbol, opened, received, registry, payload, digest in rows:
                if (symbol not in by_member
                        or type(opened) is not int
                        or opened != start+len(by_member[symbol])*HOUR_MS
                        or type(received) is not int
                        or received > observed_at_ms
                        or registry != ws_scope.registry_sha256):
                    raise DataGapError("WS row membership, timeline or registry changed")
                data = _validated_payload(payload, digest)
                if (data["symbol"] != symbol
                        or data["open_ms"] != opened
                        or data["received_ms"] != received
                        or data["registry_sha256"] != registry
                        or data["scope_observed_ms"] != ws_scope.observed_at_ms
                        or not any(x.symbol == symbol
                                   and x.launch_time_ms == data["launch_ms"]
                                   for x in ws_scope.contracts)):
                    raise DataGapError("WS source metadata differs from reviewed scope")
                values = tuple(
                    _read_decimal(data[name], positive=i < 4)
                    for i, name in enumerate((
                        "open", "high", "low", "close",
                        "volume_base", "turnover_usdt",
                    ))
                )
                by_member[symbol].append((opened, values))
                fingerprints.append((symbol, opened, digest))
        # J1 audit on both sides ensures our read-only SQL snapshot was not
        # collected across an unseen append, gap marker or journal replacement.
        second = _audited_window(
            journal=journal, ws_scope=ws_scope, members=members,
            decision_at_ms=decision_at_ms, observed_at_ms=observed_at_ms,
        )
        if (first.journal_digest_sha256 != second.journal_digest_sha256
                or first.rank_digest_sha256 != second.rank_digest_sha256
                or first.hour_evidence_sha256 != second.hour_evidence_sha256
                or first.persisted_rows != second.persisted_rows
                or any(len(v) != BARS for v in by_member.values())):
            raise DataGapError("WS journal changed between audit snapshots")
        research = [_metrics(symbol, by_member[symbol]) for symbol in symbols]
        btc = next((x for x in research if x["symbol"] == "BTCUSDT"), None)
        with localcontext(MATH):
            for item in research:
                item["relative_vs_btc_pct_points"] = (
                    item["return_24bars_pct"]-btc["return_24bars_pct"]
                    if btc is not None else None
                )
        research.sort(key=lambda r: (-r["return_24bars_pct"], r["symbol"]))
        out.update(
            status=("ws_n50_descriptive_24h_ready" if btc is not None
                    else "ws_n50_btc_context_missing"),
            latest_closed_end_ms=decision_at_ms,
            audited_assets=_COUNT,
            eligible_closed_bars_per_asset=BARS,
            btc_context_available=btc is not None,
            descriptive_up_breakouts=sum(x["last_closed_bar_breakout"]
                                         == "above_prior_23h_high" for x in research),
            descriptive_down_breakouts=sum(x["last_closed_bar_breakout"]
                                           == "below_prior_23h_low" for x in research),
            descriptive_inside_bars=sum(x["last_closed_bar_breakout"]
                                        == "inside_prior_23h_range" for x in research),
            ws_journal_integrity_replayed=True,
            window_digest_sha256=sha256(json.dumps(
                fingerprints, ensure_ascii=True,
                sort_keys=True, separators=(",", ":"),
            ).encode("ascii")).hexdigest(),
            ranked_scope_sha256=binding,
            ws_metadata_sha256=ws_scope.registry_sha256,
        )
        if include_private_symbols:
            out["research_rows"] = [{
                "descriptive_rank": i,
                "symbol": row["symbol"],
                "return_24bars_pct": _text(row["return_24bars_pct"]),
                "relative_vs_btc_pct_points": _text(row["relative_vs_btc_pct_points"]),
                "mean_true_range_14_pct": _text(row["mean_true_range_14_pct"]),
                "quote_turnover_24bars_usdt": _text(row["quote_turnover_24bars_usdt"]),
                "last_quote_turnover_vs_prior23_mean": _text(
                    row["last_quote_turnover_vs_prior23_mean"]),
                "last_closed_bar_breakout": row["last_closed_bar_breakout"],
                "approved_for_signals": False,
                "orders_sent": False,
            } for i, row in enumerate(research, 1)]
        return out
    except (OSError, ValueError, TypeError, OverflowError, UnicodeError,
            sqlite3.Error, DataValidationError, DataGapError):
        return _blank("ws_24h_readonly_integrity_abstain")
