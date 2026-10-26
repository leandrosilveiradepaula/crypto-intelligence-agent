"""J5/PRE2: build an offline, read-only HTML view from trusted PAPER fixtures.

No HTTP, accounts, credentials, imported JSON, exchange data or order actions.
The only CLI data source is the in-process synthetic J4/AUTO5 replay. A
standalone HTML page is generated without scripts or remote dependencies.
"""
from __future__ import annotations

import argparse
import json
from decimal import Decimal
from html import escape
from html.parser import HTMLParser
from pathlib import Path
import re
import sys
from typing import Any

from crypto_intelligence_agent.synthetic_order_lifecycle import PaperVenue
from crypto_intelligence_agent.synthetic_partial_exits import (
    ExitBasis, SyntheticExitPlan, SyntheticExitTranche,
    plan_synthetic_partial_exits,
)
from scripts.demo_automated_paper_cycle import simulate_automatic_paper_cycle


TEMPLATE = Path(__file__).resolve().parent.parent / "web" / "paper-demo.html"
VENUES = (PaperVenue.BINANCE_USDM, PaperVenue.BYBIT_V5)
RULE_PERCENTAGES = (Decimal("50"), Decimal("60"), Decimal("70"))
_INTEGER_DECIMAL = re.compile(r"(?:0|[1-9][0-9]{0,11})(?:\.[0-9]{1,8})?\Z")
_ROOT_FIELDS = frozenset({
    "schema_version", "demo", "mode", "live_trading_authorized", "orders_sent", "results",
})
_RESULT_FIELDS = frozenset({
    "mode", "quality", "signal_source", "market_data_source",
    "venue_candidate", "venue_selected_for_live", "symbol_fixture",
    "hypothetical_mark_price_quote", "quote_currency_fixture",
    "paper_risk_result", "entry_status", "initial_confirmed_units",
    "exit_steps", "filled_exit_units", "residual_units",
    "residual_percent_of_initial",
    "unknown_resolved_by_explicit_fixture_fill",
    "recovery_consistent_after_restart", "approved_for_live_use",
    "live_trading_authorized", "orders_sent", "real_financial_pnl_available",
    "database_retention",
})
_STEP_FIELDS = frozenset({"step", "basis", "filled_units", "status"})


class InvalidPaperSnapshot(ValueError):
    """A snapshot cannot be safely displayed as this fictitious PAPER view."""


def _require(condition: bool, explanation: str) -> None:
    if not condition:
        raise InvalidPaperSnapshot(explanation)


def _number(value: Any, label: str) -> Decimal:
    _require(type(value) is str and _INTEGER_DECIMAL.fullmatch(value) is not None,
             f"{label}: bounded, nonnegative decimal string required")
    number = Decimal(value)
    _require(number.is_finite(), f"{label}: non-finite quantity")
    return number


def _fmt(value: Decimal) -> str:
    # Never introduce exchange lot/tick rounding; this is display only.
    return format(value.normalize(), "f")


def make_paper_snapshot() -> dict[str, object]:
    """Re-run ONLY the J4/AUTO5 trusted synthetic scenarios, never load JSON."""
    return {
        "schema_version": "paper_dashboard_snapshot_v1",
        "demo": "two_independent_synthetic_candidate_venues",
        "mode": "offline_paper",
        "live_trading_authorized": False,
        "orders_sent": False,
        "results": [simulate_automatic_paper_cycle(v) for v in VENUES],
    }


def validate_paper_snapshot(snapshot: object) -> tuple[dict[str, object], ...]:
    """Strict, versioned presentation contract; reject all live/extra fields."""
    _require(type(snapshot) is dict and set(snapshot) == _ROOT_FIELDS,
             "unexpected PAPER snapshot envelope")
    assert isinstance(snapshot, dict)
    _require(snapshot["schema_version"] == "paper_dashboard_snapshot_v1"
             and type(snapshot["schema_version"]) is str,
             "unsupported PAPER snapshot schema version")
    _require(snapshot["demo"] == "two_independent_synthetic_candidate_venues"
             and type(snapshot["demo"]) is str, "unrecognized fixture origin")
    _require(snapshot["mode"] == "offline_paper"
             and type(snapshot["mode"]) is str, "non-PAPER snapshot denied")
    for key in ("live_trading_authorized", "orders_sent"):
        _require(type(snapshot[key]) is bool and snapshot[key] is False,
                 f"{key}: real execution cannot be enabled")
    results = snapshot["results"]
    _require(type(results) is list and len(results) == 2,
             "two independent candidate fixtures required")
    validated = []
    common = None
    for venue, value in zip(VENUES, results):
        _require(type(value) is dict and set(value) == _RESULT_FIELDS,
                 "unexpected or missing per-venue fields")
        assert isinstance(value, dict)
        _require(
            type(value["venue_candidate"]) is str
            and value["venue_candidate"] == venue.value
            and type(value["symbol_fixture"]) is str
            and value["symbol_fixture"] == "BTCUSDT"
            and type(value["quote_currency_fixture"]) is str
            and value["quote_currency_fixture"] == "USDT",
            "unexpected venue, symbol or quote; static view cannot attest a contract",
        )
        expected_labels = {
            "mode": "offline_paper",
            "quality": "synthetic_fixture_only",
            "signal_source": "predefined_test_fixture_not_a_validated_strategy",
            "market_data_source": "invented_unit_test_values_not_exchange_data",
            "paper_risk_result": "open_allowed_paper_only",
            "entry_status": "FILLED",
            "database_retention": "temporary_files_discarded",
        }
        for key, expected in expected_labels.items():
            _require(type(value[key]) is str and value[key] == expected,
                     f"{venue.value}: invalid {key}")
        for key, expected in {
            "venue_selected_for_live": False,
            "unknown_resolved_by_explicit_fixture_fill": True,
            "recovery_consistent_after_restart": True,
            "approved_for_live_use": False,
            "live_trading_authorized": False,
            "orders_sent": False,
            "real_financial_pnl_available": False,
        }.items():
            _require(type(value[key]) is bool and value[key] is expected,
                     f"{venue.value}: unsafe {key}")
        _require(_number(value["hypothetical_mark_price_quote"], "fixture mark") > 0,
                 "hypothetical mark must be positive")
        initial = _number(value["initial_confirmed_units"], "initial units")
        filled = _number(value["filled_exit_units"], "filled exit units")
        residual = _number(value["residual_units"], "residual units")
        residual_pct = _number(value["residual_percent_of_initial"],
                               "residual percent")
        _require(initial > 0 and residual > 0 and filled + residual == initial,
                 "paper position conservation failed")

        # Reuse the J4/PRE1 planner. The HTML describes exactly these three
        # REMAINING_BALANCE rules; changes require an explicit new UI contract.
        plan = SyntheticExitPlan(
            initial_units=initial,
            tranches=tuple(SyntheticExitTranche(ExitBasis.REMAINING_BALANCE, p)
                           for p in RULE_PERCENTAGES),
            residual_floor_percent=residual_pct,
        )
        schedule = plan_synthetic_partial_exits(plan)
        rows = value["exit_steps"]
        _require(type(rows) is list and len(rows) == len(schedule.allocations),
                 "unexpected number of PAPER tranches")
        running = initial
        quantities = []
        for index, (row, expected) in enumerate(zip(rows, schedule.allocations), 1):
            _require(type(row) is dict and set(row) == _STEP_FIELDS,
                     "unexpected paper tranche payload")
            assert isinstance(row, dict)
            _require(type(row["step"]) is int and row["step"] == index
                     and type(row["basis"]) is str
                     and row["basis"] == "REMAINING_BALANCE"
                     and type(row["status"]) is str and row["status"] == "FILLED",
                     "paper tranche identity, basis or fill status differs")
            actual = _number(row["filled_units"], f"tranche {index} quantity")
            _require(actual == expected.exit_units,
                     f"tranche {index} does not match J4/PRE1 planner")
            running -= actual
            quantities.append(_fmt(actual))
        _require(running == residual and residual_pct * initial == 100 * residual,
                 "runner residual differs from declared percentage")
        _require(filled == sum((_number(x["filled_units"], "tranche")
                               for x in rows), Decimal(0)),
                 "fill totals disagree with individual tranches")
        fingerprint = (_fmt(initial), _fmt(filled), _fmt(residual),
                       _fmt(residual_pct), tuple(quantities))
        if common is None:
            common = fingerprint
        else:
            _require(fingerprint == common,
                     "candidate results differ; shared summary would mislead")
        validated.append(value)
    return tuple(validated)


def _tag_text(document: str, marker: str, value: str,
              *, attr: str = "data-snapshot-key") -> str:
    # Markers belong to the checked-in template. Values are validated numbers
    # and html-escaped. This does not parse or interpolate arbitrary HTML.
    key = re.escape(marker)
    tag = re.compile(
        r'(?P<open><(?P<tag>dd|small|span|strong|td)\b'
        r'(?=[^>]*\b' + re.escape(attr) + r'="' + key + r'")[^>]*>)'
        r'(?P<old>[^<]*)'
        r'(?P<end></(?P=tag)>)'
    )
    updated, count = tag.subn(
        lambda match: match.group("open") + escape(value, quote=True)
        + match.group("end"), document,
    )
    _require(count == 1, f"required unique UI marker missing: {marker}")
    return updated


def _tranche_attribute(document: str, step: int, value: str) -> str:
    tag = re.compile(
        r'(?P<start><tr\b(?=[^>]*\bdata-step="' + str(step) +
        r'")[^>]*\bdata-qty=")(?P<old>[^"]*)(?P<end>")'
    )
    updated, count = tag.subn(
        lambda match: match.group("start") + escape(value, quote=True)
        + match.group("end"), document,
    )
    _require(count == 1, f"required unique PAPER row missing: {step}")
    return updated


class _OfflineHTMLPolicy(HTMLParser):
    """Allow one local skip link; deny all external assets and actionable HTML."""

    _BLOCKED_TAGS = frozenset({
        "script", "form", "iframe", "button", "input", "object", "embed",
        "link", "img", "base", "video", "audio", "source", "picture",
        "svg", "math", "textarea", "select",
    })
    _BLOCKED_ATTRIBUTES = frozenset({
        "src", "srcset", "action", "formaction", "data", "poster",
        "xlink:href", "ping",
    })

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.errors: list[str] = []
        self.skip_link_count = 0
        self.main_target_count = 0
        self.scroll_region_count = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._BLOCKED_TAGS:
            self.errors.append(f"forbidden dynamic/asset tag {tag}")
        lookup = dict(attrs)
        for name, value in attrs:
            if name.startswith("on") or name in self._BLOCKED_ATTRIBUTES:
                self.errors.append(f"forbidden HTML attribute {name}")
            if name == "href":
                if tag == "a" and value == "#conteudo-principal":
                    self.skip_link_count += 1
                else:
                    self.errors.append("external or unknown link forbidden")
        if tag == "main" and lookup.get("id") == "conteudo-principal":
            if lookup.get("tabindex") == "-1":
                self.main_target_count += 1
            else:
                self.errors.append("skip target must support focus")
        if tag == "div" and "table-wrap" in (lookup.get("class") or "").split():
            if (lookup.get("role") == "region"
                    and lookup.get("tabindex") == "0"
                    and lookup.get("aria-describedby") == "table-scroll-instructions"
                    and lookup.get("aria-label")):
                self.scroll_region_count += 1
            else:
                self.errors.append("scrollable table must have keyboard focus/name")


def _audit_offline_template(template: str) -> None:
    """Strict safety policy for the built-in template, not an HTML sanitizer."""
    _require(not re.search(r"https?://|@import\b|url\s*\(", template,
                           flags=re.IGNORECASE),
             "outbound URL or remote stylesheet in PAPER template")
    parser = _OfflineHTMLPolicy()
    parser.feed(template)
    parser.close()
    _require(not parser.errors and parser.skip_link_count == 1
             and parser.main_target_count == 1 and parser.scroll_region_count == 1,
             "unsafe or incomplete offline keyboard template: "
             + ", ".join(parser.errors[:3]))


def render_paper_dashboard(snapshot: object, template: str) -> str:
    """Pure rendering of confirmed synthetic results to offline HTML only."""
    validated = validate_paper_snapshot(snapshot)
    _require(type(template) is str and template.lstrip().lower().startswith(
        "<!doctype html>"), "standalone HTML template required")
    _require("default-src 'none'" in template
             and "connect-src 'none'" in template
             and 'data-mode="offline_paper"' in template
             and "SIMULADO" in template, "insecure PAPER template")
    _require(re.search(r"<\s*(?:script|form|iframe|button|input|object|embed|link)\b",
                       template, flags=re.IGNORECASE) is None,
             "dynamic or actionable tags forbidden in PAPER view")
    _audit_offline_template(template)
    first = validated[0]
    initial = _number(first["initial_confirmed_units"], "initial")
    exit_total = _number(first["filled_exit_units"], "exit total")
    residual = _number(first["residual_units"], "residual")
    residual_pct = _number(first["residual_percent_of_initial"], "runner percent")
    rows = first["exit_steps"]
    updated = template
    by_metric = {
        "initial_units": _fmt(initial),
        "filled_exit_units": _fmt(exit_total),
        "residual_units": _fmt(residual),
    }
    for key, value in by_metric.items():
        updated = _tag_text(updated, key, value, attr="data-metric")
    steps = [_number(row["filled_units"], "tranche") for row in rows]
    joined = " + ".join(_fmt(v) for v in steps) + " unidades"
    updated = _tag_text(updated, "summary-exits", joined)
    updated = _tag_text(updated, "summary-runner-percent",
                        _fmt(residual_pct) + "% da posição inicial")
    updated = _tag_text(updated, "overview-opening", _fmt(initial))
    updated = _tag_text(updated, "flow-opening", _fmt(initial))
    updated = _tag_text(updated, "runner-note",
                        _fmt(residual) + " unidades (" + _fmt(residual_pct) + "%)")
    running = initial
    for index, amount in enumerate(steps, 1):
        running -= amount
        updated = _tag_text(updated, f"exit-{index}-fill", _fmt(amount))
        updated = _tag_text(updated, f"exit-{index}-balance", _fmt(running))
        updated = _tranche_attribute(updated, index, _fmt(amount))
    for scenario in validated:
        venue = scenario["venue_candidate"]
        vals = {
            f"{venue}-initial": _fmt(initial) + " unidades",
            f"{venue}-exits": " / ".join(_fmt(x) for x in steps),
            f"{venue}-runner": _fmt(residual) + " unidades",
        }
        for key, val in vals.items():
            updated = _tag_text(updated, key, val)
    return updated


def main(argv: list[str] | None = None) -> None:
    cli = argparse.ArgumentParser(
        description="Exporta HTML local de replay inteiramente fictício; sem trading."
    )
    cli.add_argument("--format", choices=("html", "json"), default="html",
                     help="HTML local (padrão) ou snapshot JSON estritamente fictício.")
    cli.add_argument("--output", type=Path,
                     help="Novo arquivo HTML/JSON; nunca sobrescreve destino existente.")
    args = cli.parse_args(argv)
    snapshot = make_paper_snapshot()
    validate_paper_snapshot(snapshot)
    payload = (render_paper_dashboard(snapshot, TEMPLATE.read_text(encoding="utf-8"))
               if args.format == "html" else
               json.dumps(snapshot, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    if args.output is None:
        sys.stdout.write(payload)
    else:
        # Exclusive creation prevents accidental overwrite of user's files.
        with args.output.open("x", encoding="utf-8") as output:
            output.write(payload)


if __name__ == "__main__":
    main()
