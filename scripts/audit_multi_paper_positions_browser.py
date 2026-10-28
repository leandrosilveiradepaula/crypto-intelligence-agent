"""J5/PRE5 Chrome QA: two persisted synthetic positions, no network or trades."""
from __future__ import annotations

import argparse
from decimal import Decimal
import json
from pathlib import Path
import shutil
import sys
import tempfile

from crypto_intelligence_agent.paper_order_store import SQLitePaperOrderJournal
from crypto_intelligence_agent.paper_position_reservations import SQLitePaperPositionJournal
from scripts.audit_paper_position_browser import _fixture_margin_decision
from crypto_intelligence_agent.paper_position_inspection import inspect_paper_positions
from crypto_intelligence_agent.synthetic_order_lifecycle import (
    PaperOrderEffect, PaperOrderEvent, PaperOrderEventKind,
    PaperOrderIntent, PaperOrderSide, PaperVenue,
)
from crypto_intelligence_agent.synthetic_partial_exits import (
    ExitBasis, SyntheticExitPlan, SyntheticExitTranche,
)
from crypto_intelligence_agent.synthetic_position_state import SyntheticSide
from scripts.audit_paper_dashboard_browser import VIEWPORTS
from scripts.inspect_paper_positions import TEMPLATE, render_paper_positions


D = Decimal
T = 1792985000000


def _local_fixture_selected():
    with tempfile.TemporaryDirectory(prefix="paper_multi_browser_") as temp:
        path = Path(temp) / "positions.sqlite"
        order_path = Path(temp) / "opening-orders.sqlite"
        writer = SQLitePaperPositionJournal(path)
        order_writer = SQLitePaperOrderJournal(order_path)
        for suffix, venue, symbol in (
            ("A", PaperVenue.BINANCE_USDM, "BTCUSDT"),
            ("B", PaperVenue.BYBIT_V5, "ETHUSDT"),
        ):
            opening = PaperOrderIntent(
                intent_id=f"fixture_browse_open_{suffix}",
                fixture_signal_id=f"fixture_browse_signal_{suffix}",
                venue=venue, symbol=symbol,
                position_side=SyntheticSide.LONG, side=PaperOrderSide.BUY,
                effect=PaperOrderEffect.OPEN, requested_units=D(100), created_at_ms=T,
            )
            opening_fill = PaperOrderEvent(
                f"fixture_browse_fill_{suffix}",
                PaperOrderEventKind.FILL, T + 1, D(100),
            )
            if suffix == "A":
                risk_limits, observation, assessment = _fixture_margin_decision(opening)
                health, reservation = order_writer.reserve_open_if_paper_risk_with_health(
                    opening, risk_limits, observation, decision_at_ms=T,
                    position_journal_path=path, margin_assessment=assessment,
                )
                if not health.new_open_allowed or reservation.entry is None:
                    raise AssertionError("synthetic multi PAPER reservation rejected")
                order_writer.append_events(
                    opening.intent_id, (opening_fill,), as_of_ms=T + 1,
                )
            writer.create_position(
                position_id=f"fixture_browse_position_{suffix}",
                opening_intent=opening,
                opening_events=(opening_fill,),
                exit_plan=SyntheticExitPlan(
                    initial_units=D(100),
                    tranches=tuple(SyntheticExitTranche(ExitBasis.REMAINING_BALANCE, D(n))
                                   for n in ("50", "60", "70")),
                    residual_floor_percent=D(6),
                ),
                plan_version="browser-multi-v1",
                synthetic_lot_step_units=D(1), as_of_ms=T + 1,
                opening_order_path=order_path if suffix == "A" else None,
            )
        exit_intent = PaperOrderIntent(
            intent_id="fixture_browse_exit_B",
            fixture_signal_id="fixture_browse_exit_signal_B",
            venue=PaperVenue.BYBIT_V5, symbol="ETHUSDT",
            position_side=SyntheticSide.LONG, side=PaperOrderSide.SELL,
            effect=PaperOrderEffect.REDUCE_ONLY, requested_units=D(10),
            max_reducible_units=D(100), created_at_ms=T + 2,
        )
        writer.reserve_exit(
            "fixture_browse_position_B", 1, exit_intent, as_of_ms=T + 2,
        )
        writer.append_exit_events(
            "fixture_browse_position_B", exit_intent.intent_id,
            (PaperOrderEvent(
                "fixture_browse_timeout", PaperOrderEventKind.UNKNOWN, T + 3,
            ),),
            as_of_ms=T + 3,
        )
        selected = inspect_paper_positions(
            path, ("fixture_browse_position_A", "fixture_browse_position_B"),
        )
        return selected


def _local_fixture_html() -> str:
    return render_paper_positions(
        _local_fixture_selected(), TEMPLATE.read_text("utf-8"),
    )


_JS = r"""() => {
  const width = innerWidth;
  const docWidth = Math.max(document.documentElement.scrollWidth, document.body.scrollWidth);
  const cards = [...document.querySelectorAll('.position-card')];
  const table = document.querySelector('.table-wrap');
  const main = document.querySelector('main');
  const first = [...document.querySelectorAll('a[href],[tabindex]')]
      .find(el => el.tabIndex >= 0);
  const skip = document.querySelector('.skip-link');
  const warning = document.querySelector('.warning');
  const selectors = ['main', '.warning', '.position-card', '.balances', '.balances div', '.table-wrap'];
  const outside = [];
  for (const selector of selectors) for (const el of document.querySelectorAll(selector)) {
    const r = el.getBoundingClientRect();
    if (r.left < -1 || r.right > width + 1) outside.push(selector);
  }
  return {
    width, docWidth, outside,
    card_count: cards.length,
    ids: cards.map(c => c.getAttribute('data-position')),
    unknown_on_second: cards.length === 2 && cards[1].textContent.includes('UNKNOWN: 1'),
    unknown_on_first: cards.length === 2 && cards[0].textContent.includes('UNKNOWN: 1'),
    first_has_margin: cards.length === 2
      && cards[0].textContent.includes('Alavancagem solicitada (PAPER): 50x')
      && cards[0].textContent.includes('Margem solicitada (PAPER): 5 USDT'),
    second_margin_missing: cards.length === 2
      && cards[1].textContent.includes('não registradas'),
    explicit_no_aggregation: document.body.textContent.includes('Não existe total consolidado'),
    banner: Boolean(warning && warning.getBoundingClientRect().height > 0
                     && warning.textContent.includes('SIMULADO')),
    table_accessible: Boolean(table && table.tabIndex === 0
                     && table.getAttribute('role') === 'region'
                     && table.getAttribute('aria-describedby') === 'table-scroll-instructions'),
    table_scrollable: Boolean(table && table.scrollWidth > table.clientWidth + 1),
    skip_first: Boolean(first === skip && main && main.id === 'conteudo-principal'
                         && skip.getAttribute('href') === '#conteudo-principal'),
  };
}"""


def run_audit(out_dir: Path | None = None) -> dict[str, object]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("playwright local requerido para QA visual") from exc
    html = _local_fixture_html()
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    failures = []
    with sync_playwright() as playwright:
        chrome = next((
            p for exe in ("google-chrome", "chromium", "chromium-browser")
            if (p := shutil.which(exe))
        ), None)
        kwargs = {"executable_path": chrome} if chrome else {"channel": "chrome"}
        browser = playwright.chromium.launch(
            headless=True,
            args=["--disable-background-networking", "--disable-sync",
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
                sample = page.evaluate(_JS)
                errors = []
                if sample["docWidth"] > width + 1 or sample["outside"]:
                    errors.append("global or visible card overflow")
                if sample["card_count"] != 2 or sample["ids"] != [
                    "fixture_browse_position_A", "fixture_browse_position_B",
                ]:
                    errors.append("explicit positions absent or reordered")
                if sample["unknown_on_first"] or not sample["unknown_on_second"]:
                    errors.append("UNKNOWN state misattributed between positions")
                if not sample["first_has_margin"] or not sample["second_margin_missing"]:
                    errors.append("PAPER margin not isolated to matching position/legacy")
                if not sample["explicit_no_aggregation"] or not sample["banner"]:
                    errors.append("fake portfolio aggregate or missing SIMULADO warning")
                if not sample["table_accessible"] or not sample["skip_first"]:
                    errors.append("keyboard table/skip-link missing")
                if requests:
                    errors.append("unexpected external network request")
                page.keyboard.press("Tab")
                if not page.evaluate(
                    "document.activeElement.classList.contains('skip-link')"
                ):
                    errors.append("Tab failed to focus internal skip link")
                else:
                    page.keyboard.press("Enter")
                    if page.evaluate("location.hash") != "#conteudo-principal":
                        errors.append("Enter did not navigate to main")
                table = page.locator(".table-wrap")
                table.focus()
                before = table.evaluate("(el) => el.scrollLeft")
                page.keyboard.press("ArrowRight")
                page.wait_for_timeout(180)
                delta = table.evaluate("(el) => el.scrollLeft") - before
                if sample["table_scrollable"] and delta <= 0:
                    errors.append("keyboard did not scroll table")
                sample["keyboard_scroll_delta"] = delta
                sample["external_requests"] = len(requests)
                sample["errors"] = errors
                if out_dir is not None:
                    table.evaluate("(el) => { el.scrollLeft = 0; }")
                    page.evaluate("window.scrollTo(0,0)")
                    page.screenshot(
                        path=str(out_dir / f"paper-multi-{width}px.png"),
                        full_page=True,
                    )
                rows.append(sample)
                failures.extend(f"{width}px: {error}" for error in errors)
                ctx.close()
        finally:
            browser.close()
    result: dict[str, object] = {
        "schema_version": "paper_multi_browser_qa_v1",
        "mode": "offline_paper", "source": "selected_synthetic_sqlite_positions",
        "orders_sent": False, "live_trading_authorized": False,
        "passed": not failures, "failures": failures, "viewports": rows,
    }
    if out_dir is not None:
        (out_dir / "paper-multi-browser-report.json").write_text(
            json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
    return result


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="QA Chrome offline de posicoes PAPER selecionadas por ID."
    )
    parser.add_argument("--out-dir", type=Path)
    args = parser.parse_args(argv)
    result = run_audit(args.out_dir)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    if not result["passed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
