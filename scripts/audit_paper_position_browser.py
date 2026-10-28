"""J5/PRE4: Chrome QA of a persisted PAPER fixture read in SQLite mode=ro.

No external URL, JSON, keys, market data or real order. Reuse the same local
Playwright environment and widths as PRE3; screenshots are synthetic evidence.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile

from crypto_intelligence_agent.paper_margin_preflight import (
    PaperLinearContractFixture, assess_paper_margin_open,
)
from crypto_intelligence_agent.paper_risk_gate import PaperRiskLimits, PaperRiskObservation
from crypto_intelligence_agent.paper_order_store import SQLitePaperOrderJournal
from crypto_intelligence_agent.paper_position_inspection import inspect_paper_position
from crypto_intelligence_agent.paper_position_reservations import SQLitePaperPositionJournal
from crypto_intelligence_agent.synthetic_order_lifecycle import (
    PaperOrderEffect, PaperOrderEvent, PaperOrderEventKind,
    PaperOrderIntent, PaperOrderSide, PaperVenue,
)
from crypto_intelligence_agent.synthetic_partial_exits import (
    ExitBasis, SyntheticExitPlan, SyntheticExitTranche,
)
from crypto_intelligence_agent.synthetic_position_state import (
    SyntheticLeverageSettings, SyntheticSide,
)
from decimal import Decimal
from scripts.audit_paper_dashboard_browser import VIEWPORTS
from scripts.inspect_paper_position import TEMPLATE, render_paper_position


D = Decimal
T = 1792985000000


def _fixture_margin_decision(opening: PaperOrderIntent):
    """An offline quote/lot/50x hypothesis; never real venue metadata."""
    assumption = PaperLinearContractFixture(
        venue=opening.venue, symbol=opening.symbol,
        quote_currency="USDT", observed_at_ms=T,
        fixture_version="fixture_browser_margin_v1",
        max_leverage_assumed=75, price_tick_quote=D("0.01"),
        quantity_step_base=D(1), min_quantity_base=D(1),
        min_notional_quote=D(100), max_notional_quote=D(1000),
    )
    limits = PaperRiskLimits(
        max_order_notional_quote=D(1000), max_symbol_exposure_quote=D(2000),
        max_portfolio_exposure_quote=D(3000),
        max_realized_loss_today_quote=D(50),
        max_pending_open_orders=2, max_market_age_ms=1000,
    )
    mark = PaperRiskObservation(
        venue=opening.venue, symbol=opening.symbol,
        quote_currency="USDT", observed_at_ms=T,
        mark_price_quote=D("2.5"), symbol_exposure_quote=D(0),
        portfolio_exposure_quote=D(0), realized_loss_today_quote=D(0),
        pending_open_orders=0, unresolved_open_exists=False,
        kill_switch_active=False,
    )
    evaluation = assess_paper_margin_open(
        opening, SyntheticLeverageSettings(), D(5),
        assumption, limits, mark,
        decision_at_ms=T, max_contract_age_ms=1000,
    )
    if not evaluation.allowed_for_paper_research_only:
        raise AssertionError("synthetic browser margin scenario must be feasible")
    return limits, mark, evaluation


def _synthetic_fixture_html() -> str:
    """Persist, reopen RO, and render one intentionally unresolved PAPER exit."""
    with tempfile.TemporaryDirectory(prefix="paper_readonly_browser_") as base:
        base_path = Path(base)
        position_path = base_path / "position.sqlite"
        order_path = base_path / "opening.sqlite"
        opening = PaperOrderIntent(
            intent_id="fixture_browser_open", fixture_signal_id="fixture_browser_signal",
            venue=PaperVenue.BYBIT_V5, symbol="BTCUSDT",
            position_side=SyntheticSide.LONG, side=PaperOrderSide.BUY,
            effect=PaperOrderEffect.OPEN, requested_units=D(100),
            created_at_ms=T,
        )
        f = PaperOrderEvent(
            "fixture_browser_open_fill", PaperOrderEventKind.FILL, T + 1, D(100),
        )
        position_store = SQLitePaperPositionJournal(position_path)
        order_store = SQLitePaperOrderJournal(order_path)
        risk_limits, observation, evaluation = _fixture_margin_decision(opening)
        health, reservation = order_store.reserve_open_if_paper_risk_with_health(
            opening, risk_limits, observation, decision_at_ms=T,
            position_journal_path=position_path, margin_assessment=evaluation,
        )
        if not health.new_open_allowed or reservation.entry is None:
            raise AssertionError("synthetic browser OPEN must only reserve PENDING")
        order_store.append_events(opening.intent_id, (f,), as_of_ms=T + 1)
        position_store.create_position(
            position_id="fixture_browser_position", opening_intent=opening,
            opening_events=(f,),
            exit_plan=SyntheticExitPlan(
                initial_units=D(100),
                tranches=tuple(
                    SyntheticExitTranche(ExitBasis.REMAINING_BALANCE, D(x))
                    for x in ("50", "60", "70")
                ),
                residual_floor_percent=D(6),
            ),
            plan_version="browser-fixture-v1", synthetic_lot_step_units=D(1),
            as_of_ms=T + 1, opening_order_path=order_path,
        )
        exit_intent = PaperOrderIntent(
            intent_id="fixture_browser_exit", fixture_signal_id="fixture_browser_exit_signal",
            venue=PaperVenue.BYBIT_V5, symbol="BTCUSDT",
            position_side=SyntheticSide.LONG, side=PaperOrderSide.SELL,
            effect=PaperOrderEffect.REDUCE_ONLY, requested_units=D(50),
            max_reducible_units=D(100), created_at_ms=T + 2,
        )
        position_store.reserve_exit(
            "fixture_browser_position", 1, exit_intent, as_of_ms=T + 2,
        )
        position_store.append_exit_events(
            "fixture_browser_position", exit_intent.intent_id,
            (
                PaperOrderEvent(
                    "fixture_browser_partial", PaperOrderEventKind.FILL, T + 3, D(20),
                ),
                PaperOrderEvent(
                    "fixture_browser_unknown", PaperOrderEventKind.UNKNOWN, T + 4,
                ),
            ), as_of_ms=T + 4,
        )
        inspected = inspect_paper_position(
            position_path, "fixture_browser_position", opening_order_path=order_path,
        )
        return render_paper_position(inspected, TEMPLATE.read_text("utf-8"))


_JS = r"""() => {
    const w = innerWidth;
    const docWidth = Math.max(document.documentElement.scrollWidth, document.body.scrollWidth);
    const relevant = ['.brand', '.warning', '.stat', '.card', '.facts', '.stats', '.table-wrap'];
    const overflow = [];
    for (const selector of relevant) {
      for (const el of document.querySelectorAll(selector)) {
        const r = el.getBoundingClientRect();
        if (r.left < -1 || r.right > w + 1) overflow.push(selector);
      }
    }
    const table = document.querySelector('.table-wrap');
    const skip = document.querySelector('.skip-link');
    const warning = document.querySelector('.warning');
    const metrics = {};
    for (const el of document.querySelectorAll('[data-metric]'))
       metrics[el.getAttribute('data-metric')] = el.textContent.trim();
    const first = [...document.querySelectorAll('a[href],[tabindex]')]
       .find(el => el.tabIndex >= 0);
    return {
       width: w, docWidth, overflow,
       metrics, status_unknown: document.querySelectorAll('.status-unknown').length,
       margin_leverage: document.querySelector('[data-field="margin-leverage"]')?.textContent.trim(),
       margin_requested: document.querySelector('[data-field="margin-requested"]')?.textContent.trim(),
       margin_warning: document.body.textContent.includes('Não comprova margem efetiva'),
       warning_visible: Boolean(warning && warning.getBoundingClientRect().height > 0
         && warning.textContent.includes('SIMULADO')),
       has_accessible_table: Boolean(table && table.tabIndex === 0
         && table.getAttribute('role') === 'region'
         && table.getAttribute('aria-label')
         && table.getAttribute('aria-describedby') === 'table-scroll-instructions'),
       table_scrollable_by_width: Boolean(table && table.scrollWidth > table.clientWidth + 1),
       skip_first: Boolean(skip && first === skip
         && skip.getAttribute('href') === '#conteudo-principal'),
    };
}"""


def run_audit(out_dir: Path | None = None) -> dict[str, object]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("playwright ausente: instalar somente em venv local") from exc
    html = _synthetic_fixture_html()
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
    findings: list[dict[str, object]] = []
    failures: list[str] = []
    with sync_playwright() as playwright:
        chrome = next((
            candidate for exe in ("google-chrome", "chromium", "chromium-browser")
            if (candidate := shutil.which(exe))
        ), None)
        kwargs = {"executable_path": chrome} if chrome else {"channel": "chrome"}
        browser = playwright.chromium.launch(
            headless=True, args=["--disable-background-networking", "--disable-sync",
                                 "--disable-extensions", "--no-first-run"], **kwargs,
        )
        try:
            for width, height in VIEWPORTS:
                ctx = browser.new_context(
                    viewport={"width": width, "height": height},
                    color_scheme="dark", reduced_motion="reduce",
                )
                page = ctx.new_page()
                requests: list[str] = []

                def deny(route):
                    requests.append(route.request.url)
                    route.abort()

                page.route("**/*", deny)
                page.set_content(html, wait_until="load")
                actual = page.evaluate(_JS)
                errors = []
                if actual["docWidth"] > width + 1 or actual["overflow"]:
                    errors.append("document/element horizontal overflow")
                if actual["metrics"] != {
                    "initial": "100", "filled": "20", "reserved": "30",
                    "available": "50", "remaining": "80", "floor": "6",
                }:
                    errors.append("rendered balances mismatch verified PAPER events")
                if actual["status_unknown"] != 1:
                    errors.append("UNKNOWN PAPER exit missing from table")
                if (actual["margin_leverage"] != "50x (PAPER)"
                        or actual["margin_requested"] != "5 USDT"
                        or not actual["margin_warning"]):
                    errors.append("PAPER margin/leverage label or warning missing")
                if not actual["warning_visible"] or not actual["has_accessible_table"]:
                    errors.append("SIMULADO banner or keyboard table missing")
                if not actual["skip_first"]:
                    errors.append("first keyboard item must be the skip link")
                if requests:
                    errors.append("remote request attempted")
                page.keyboard.press("Tab")
                focused = page.evaluate(
                    "document.activeElement.classList.contains('skip-link')"
                )
                if not focused:
                    errors.append("Tab did not focus skip link")
                else:
                    page.keyboard.press("Enter")
                    if page.evaluate("location.hash") != "#conteudo-principal":
                        errors.append("Enter did not navigate to main")
                table = page.locator(".table-wrap")
                table.focus()
                left = table.evaluate("(el) => el.scrollLeft")
                page.keyboard.press("ArrowRight")
                page.wait_for_timeout(200)
                moved = table.evaluate("(el) => el.scrollLeft") - left
                if actual["table_scrollable_by_width"] and moved <= 0:
                    errors.append("keyboard did not scroll narrow table")
                actual.update({
                    "keyboard_table_delta": moved, "external_requests": len(requests),
                    "errors": errors,
                })
                if out_dir is not None:
                    table.evaluate("(el) => { el.scrollLeft = 0; }")
                    page.evaluate("window.scrollTo(0,0)")
                    page.screenshot(
                        path=str(out_dir / f"paper-position-{width}px.png"),
                        full_page=True,
                    )
                findings.append(actual)
                failures.extend(f"{width}px: {failure}" for failure in errors)
                ctx.close()
        finally:
            browser.close()
    report: dict[str, object] = {
        "schema_version": "paper_position_browser_qa_v1",
        "mode": "offline_paper", "source": "local_persisted_synthetic_fixture_only",
        "orders_sent": False, "live_trading_authorized": False,
        "passed": not failures, "viewports": findings, "failures": failures,
    }
    if out_dir is not None:
        (out_dir / "paper-position-browser-report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return report


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="QA Chrome de HTML vindo de SQLite PAPER local; sem dados reais."
    )
    parser.add_argument("--out-dir", type=Path)
    args = parser.parse_args(argv)
    result = run_audit(args.out_dir)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    if not result["passed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
