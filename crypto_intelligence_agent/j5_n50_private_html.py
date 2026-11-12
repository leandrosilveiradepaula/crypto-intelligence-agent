"""J5/D301: no-script PT-BR mobile report for J2's owner-verified N50 data.

This intentionally does NOT serve HTML, expose an HTTP endpoint, control
orders, connect to an exchange, or read a user's account. The HTML source is
rendered in-memory from an exact, fail-closed J2/D300 report and written only
by a separately gated owner-only CLI to a private file.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Context, Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext
from hashlib import sha256
from html import escape
import os
from pathlib import Path
import re
import stat
from typing import Any

from .j1_auto_research_epoch import HOUR_MS
from .j2_n50_descriptive_watchlist import build_descriptive_watchlist

TEMPLATE = Path(__file__).resolve().parent.parent / "web" / "n50-private-research-template.html"
EXPECTED_ENVELOPE = frozenset((
    "schema_version", "status", "quality", "epoch_id",
    "scope_digest_sha256", "latest_published_end_ms", "as_of_ms",
    "eligible_closed_bars_per_asset", "audited_assets",
    "btc_context_available", "btc_return_24bar_pct",
    "descriptive_up_breakouts", "descriptive_down_breakouts",
    "descriptive_inside_bars", "research_rows", "window_digest_sha256",
    "owner_journal_integrity_verified", "marketwide_top50_verified",
    "crypto_identity_independently_verified", "source_authenticated",
    "approved_for_signals", "approved_for_live_use", "orders_sent",
    "network_requests", "database_mutation_statements", "systemd_modified",
))
EXPECTED_ROW = frozenset((
    "descriptive_rank", "symbol", "return_24bars_pct",
    "relative_vs_btc_pct_points", "mean_true_range_14_pct",
    "quote_turnover_24bars_usdt",
    "last_quote_turnover_vs_prior23_mean",
    "last_closed_bar_breakout", "approved_for_signals", "orders_sent",
))
SHA_RE = re.compile(r"[a-f0-9]{64}\Z")
SYMBOL_RE = re.compile(r"[A-Z0-9]{1,28}USDT\Z")
EPOCH_RE = re.compile(r"epoch-[0-9]{13}\Z")
ENUM = frozenset((
    "above_prior_23h_high", "below_prior_23h_low",
    "inside_prior_23h_range",
))
LABELS = {
    "above_prior_23h_high": "Acima da máxima anterior",
    "below_prior_23h_low": "Abaixo da mínima anterior",
    "inside_prior_23h_range": "Dentro da faixa anterior",
}
ROOT = Path("/home/cia-probe/agent/j1-n50-managed-d296-private")


class InvalidPrivateResearchView(ValueError):
    pass


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise InvalidPrivateResearchView(reason)


def _number(value: Any, *, can_be_negative: bool, allow_none: bool = False) -> Decimal | None:
    if value is None and allow_none:
        return None
    _require(type(value) is str and 1 <= len(value) <= 120,
             "bounded_decimal_string_required")
    try:
        v = Decimal(value)
    except (InvalidOperation, ValueError):
        raise InvalidPrivateResearchView("invalid_decimal") from None
    _require(v.is_finite() and len(v.as_tuple().digits) <= 60
             and v.as_tuple().exponent >= -24 and v.adjusted() <= 35
             and (can_be_negative or v >= 0), "decimal_rejected")
    return v


def _format(v: Decimal | None, places: int = 2) -> str:
    if v is None:
        return "—"
    with localcontext(Context(prec=80)):
        value = v.quantize(Decimal("1").scaleb(-places), rounding=ROUND_HALF_EVEN)
    return escape(format(value, "f"), quote=True)


def _utc(value: int) -> str:
    return datetime.fromtimestamp(value // 1000, tz=timezone.utc).strftime(
        "%d/%m/%Y %H:%M UTC"
    )


def validate_n50_private_report(report: Any) -> list[dict]:
    """Reject untrusted/lax data even if the caller claims it was audited."""
    _require(type(report) is dict and set(report) == EXPECTED_ENVELOPE,
             "unexpected_j2_report_envelope")
    _require(report["schema_version"] == "j2-private-n50-24closed-research-v1"
             and report["quality"] == "provisional_private_research_only",
             "unsupported_research_origin")
    btc = report["btc_context_available"]
    _require(type(btc) is bool
             and report["status"] == (
                 "descriptive_research_ready" if btc
                 else "btc_context_missing_research_only"),
             "unsupported_report_state")
    for key in (
        "marketwide_top50_verified", "crypto_identity_independently_verified",
        "source_authenticated", "approved_for_signals",
        "approved_for_live_use", "orders_sent", "systemd_modified",
    ):
        _require(report[key] is False, "unapproved_live_or_signal_flag")
    _require(report["owner_journal_integrity_verified"] is True
             and type(report["network_requests"]) is int
             and report["network_requests"] == 0
             and type(report["database_mutation_statements"]) is int
             and report["database_mutation_statements"] == 0
             and report["eligible_closed_bars_per_asset"] == 24
             and report["audited_assets"] == 50
             and type(report["audited_assets"]) is int,
             "missing_j1_integrity_gate")
    for key in ("epoch_id", "scope_digest_sha256", "window_digest_sha256"):
        pattern = EPOCH_RE if key == "epoch_id" else SHA_RE
        _require(type(report[key]) is str
                 and pattern.fullmatch(report[key]) is not None,
                 "untrusted_epoch_or_digest")
    end = report["latest_published_end_ms"]
    viewed = report["as_of_ms"]
    _require(type(end) is int and type(viewed) is int and end % HOUR_MS == 0
             and 1_600_000_000_000 < end <= viewed <= end+2*HOUR_MS,
             "invalid_snapshot_clock")
    counts = tuple(report[k] for k in (
        "descriptive_up_breakouts", "descriptive_down_breakouts",
        "descriptive_inside_bars",
    ))
    _require(all(type(n) is int and 0 <= n <= 50 for n in counts)
             and sum(counts) == 50, "invalid_breakout_counts")
    btc_return = _number(report["btc_return_24bar_pct"],
                         can_be_negative=True, allow_none=True)
    _require((btc_return is not None) == btc, "btc_context_inconsistent")

    rows = report["research_rows"]
    _require(type(rows) is list and len(rows) == 50, "fifty_private_rows_required")
    seen: set[str] = set()
    result: list[dict] = []
    previous_return = None
    breakout_counts = {label: 0 for label in ENUM}
    for index, item in enumerate(rows, 1):
        _require(type(item) is dict and set(item) == EXPECTED_ROW,
                 "unexpected_private_asset_fields")
        symbol = item["symbol"]
        _require(type(item["descriptive_rank"]) is int
                 and item["descriptive_rank"] == index
                 and type(symbol) is str
                 and SYMBOL_RE.fullmatch(symbol) is not None
                 and symbol not in seen
                 and item["approved_for_signals"] is False
                 and item["orders_sent"] is False,
                 "invalid_or_duplicated_ranked_asset")
        seen.add(symbol)
        change = _number(item["return_24bars_pct"], can_be_negative=True)
        _require(change is not None and change > -100,
                 "invalid_past_return")
        relative = _number(item["relative_vs_btc_pct_points"],
                           can_be_negative=True, allow_none=True)
        _require((relative is not None) == btc, "btc_relative_inconsistent")
        atr = _number(item["mean_true_range_14_pct"], can_be_negative=False)
        turnover = _number(item["quote_turnover_24bars_usdt"],
                           can_be_negative=False)
        ratio = _number(item["last_quote_turnover_vs_prior23_mean"],
                        can_be_negative=False, allow_none=True)
        direction = item["last_closed_bar_breakout"]
        _require(type(direction) is str and direction in ENUM,
                 "unknown_breakout_description")
        breakout_counts[direction] += 1
        if previous_return is not None:
            _require(previous_return >= change,
                     "research_history_not_sorted")
        previous_return = change
        result.append({
            "rank": index, "symbol": symbol,
            "change": change, "relative": relative,
            "atr": atr, "turnover": turnover, "ratio": ratio,
            "direction": direction,
        })
    _require(breakout_counts["above_prior_23h_high"] == counts[0]
             and breakout_counts["below_prior_23h_low"] == counts[1]
             and breakout_counts["inside_prior_23h_range"] == counts[2],
             "aggregate_and_rows_diverge")
    _require(("BTCUSDT" in seen) == btc,
             "btc_presence_mismatch")
    return result


def render_n50_private_html(report: dict) -> str:
    checked = validate_n50_private_report(report)
    html = TEMPLATE.read_text(encoding="utf-8")
    now = report["as_of_ms"]
    end = report["latest_published_end_ms"]
    cards = []
    lines = []
    for i, item in enumerate(checked):
        direction = LABELS[item["direction"]]
        css = ("positive" if item["change"] > 0
               else "negative" if item["change"] < 0 else "muted")
        changed = _format(item["change"])
        name = escape(item["symbol"], quote=True)
        relative = _format(item["relative"])
        atr = _format(item["atr"])
        turnover = _format(item["turnover"], 2)
        lines.append(
            '<tr><td>'+str(item["rank"])+'</td><td>'+name+'</td>'
            '<td class="'+css+'">'+changed+'%</td>'
            '<td>'+relative+'</td><td>'+atr+'%</td>'
            '<td>'+turnover+'</td><td>'+escape(direction)+'</td></tr>'
        )
        if i < 4:
            cards.append(
                '<article class="asset" aria-label="Contrato '+name+'">'
                '<h3>'+name+'</h3>'
                '<strong class="'+css+'">'+changed+'%</strong>'
                '<p>Variação observada em 24 barras</p>'
                '<p>Vs. BTC: '+relative+' p.p.</p>'
                '<p>'+escape(direction)+'</p></article>'
            )
    # D310: never recompute observations with a second set of heuristics.
    # Delegate the entire selection, direction and ranking to reviewed D308.
    # D300 may legitimately lack BTC; report an explicit abstention instead.
    if report["btc_context_available"]:
        watch = build_descriptive_watchlist(
            report, include_private_symbols=True,
        )
        _require(watch["status"] == "descriptive_watchlist_ready"
                 and watch["owner_journal_integrity_verified"] is True
                 and watch["window_digest_sha256"] ==
                 report["window_digest_sha256"]
                 and watch["latest_published_end_ms"] ==
                 report["latest_published_end_ms"]
                 and watch["audited_assets"] == 50
                 and watch["orders_sent"] is False
                 and watch["approved_for_live_use"] is False
                 and watch["approved_for_signals"] is False,
                 "unverified_j2_d308_watchlist")
        def _items(items: list[dict[str, Any]]) -> str:
            if not items:
                return '<li class="muted">Nenhum rompimento sob estes critérios.</li>'
            rendered: list[str] = []
            for row in items:
                symbol = escape(row["symbol"], quote=True)
                relative = _format(_number(
                    row["relative_vs_btc_pct_points"],
                    can_be_negative=True,
                ))
                intensity = _format(_number(
                    row["last_quote_turnover_vs_prior23_mean"],
                    can_be_negative=False,
                ))
                rendered.append(
                    '<li><strong>'+symbol+'</strong>'
                    '<span class="fine">Vs. BTC: '+relative+
                    ' p.p. · intensidade de turnover: '+intensity+
                    '×</span></li>'
                )
            return "".join(rendered)
        watch_status = "Observação de 24 fechamentos auditados, não validada fora da amostra."
        watch_up_count = str(watch["observed_up_breakout_candidates"])
        watch_down_count = str(watch["observed_down_breakout_candidates"])
        watch_up_rows = _items(watch["up_breakout_watchlist"])
        watch_down_rows = _items(watch["down_breakout_watchlist"])
    else:
        # No BTC denominator means NO invented relative-strength ranking.
        watch_status = "Indisponível: esta coorte não contém referência BTC."
        watch_up_count = "0"
        watch_down_count = "0"
        watch_up_rows = '<li class="muted">Sem contexto BTC auditado.</li>'
        watch_down_rows = '<li class="muted">Sem contexto BTC auditado.</li>'
    replacements = {
        "__CLOSED_UTC__": escape(_utc(end)),
        "__OBSERVED_UTC__": escape(_utc(now)),
        "__ASSET_COUNT__": "50",
        "__UP_COUNT__": str(report["descriptive_up_breakouts"]),
        "__DOWN_COUNT__": str(report["descriptive_down_breakouts"]),
        "__INSIDE_COUNT__": str(report["descriptive_inside_bars"]),
        "__BTC_CONTEXT__": ("disponível no mesmo fechamento" if
                             report["btc_context_available"] else
                             "não disponível na coorte"),
        "__STATUS_TEXT__": ("24 barras auditadas, somente pesquisa" if
                            report["status"]=="descriptive_research_ready" else
                            "sem referência BTC, apenas descrição"),
        "__DIGEST_PREFIX__": report["window_digest_sha256"][:16],
        "__TOP_CARDS__": "".join(cards),
        "__ROWS__": "".join(lines),
        "__WATCHLIST_STATUS__": escape(watch_status),
        "__WATCHLIST_UP_COUNT__": watch_up_count,
        "__WATCHLIST_DOWN_COUNT__": watch_down_count,
        "__WATCHLIST_UP_ROWS__": watch_up_rows,
        "__WATCHLIST_DOWN_ROWS__": watch_down_rows,
    }
    for mark, value in replacements.items():
        _require(html.count(mark) == 1, "template_contract_drift")
        html = html.replace(mark, value)
    _require("__N50_" not in html
             and "<script" not in html.lower()
             and "https://" not in html.lower()
             and "http://" not in html.lower(),
             "unsafe_html_surface")
    return html


def write_n50_private_html_once(
    report: dict,
    *, root_directory: Path = ROOT,
    allow_private_report_write: bool = False,
    owner_ok: bool | None = None,
) -> dict[str, Any]:
    """Save one immutable 0600 local artifact per validated epoch+checkpoint."""
    out = {
        "schema_version": "j5-n50-private-html-save-v1",
        "status": "optin_required",
        "file_name": None, "digest_sha256": None,
        "private_report_saved": False,
        "network_requests": 0, "orders_sent": False,
        "systemd_modified": False, "research_journal_modified": False,
    }
    if allow_private_report_write is not True:
        return out
    out["status"] = "blocked"
    permitted = ((os.name == "posix" and os.getuid() == os.geteuid()
                  and os.geteuid() != 0) if owner_ok is None else owner_ok)
    if (permitted is not True or not isinstance(root_directory, Path)
            or not root_directory.is_absolute() or root_directory.is_symlink()):
        return out
    try:
        from scripts.audit_bybit_marketwide_closed24h import _strict_owner
        if root_directory.resolve(strict=True) != root_directory:
            return out
        _strict_owner(root_directory, directory=True)
        html = render_n50_private_html(report)
        body = html.encode("utf-8")
        if not 2_000 <= len(body) <= 400_000:
            return out
        parent = root_directory / "reports"
        if not parent.exists() and not parent.is_symlink():
            parent.mkdir(mode=0o700)
        _strict_owner(parent, directory=True)
        if parent.is_symlink():
            return out
        sha = sha256(body).hexdigest()
        name = ("n50-" + str(report["latest_published_end_ms"])
                + "-" + report["window_digest_sha256"][:12] + ".html")
        dest = parent / name
        if dest.exists() or dest.is_symlink():
            _strict_owner(dest, directory=False)
            if dest.is_symlink() or dest.read_bytes() != body:
                return out
            out.update(status="identical_private_report_exists",
                       file_name=name,digest_sha256=sha)
            return out
        fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                     getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            with os.fdopen(fd, "wb", closefd=False) as file:
                file.write(body)
                file.flush()
                os.fsync(fd)
        finally:
            os.close(fd)
        st = dest.lstat()
        if (not stat.S_ISREG(st.st_mode) or st.st_uid != os.geteuid()
                or stat.S_IMODE(st.st_mode) != 0o600
                or st.st_nlink != 1):
            raise ValueError("private_report_permissions")
        dir_fd = os.open(parent, os.O_RDONLY |
                         getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
        out.update(status="private_report_saved", file_name=name,
                   digest_sha256=sha, private_report_saved=True)
        return out
    except (OSError, ValueError, TypeError, OverflowError, UnicodeError):
        return out
