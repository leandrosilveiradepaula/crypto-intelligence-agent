"""J5/PRE8 #268: Chrome QA for three OFFLINE PAPER recovery states.

Uses static fixture status objects only, no external data or accounts. Browser
blocks all network requests; no pages, inputs, extensions or trading actions.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys

from crypto_intelligence_agent.paper_operator_status import PaperOperatorStatus
from crypto_intelligence_agent.paper_recovery_status import (
    PaperRecoveryState, PaperRecoveryStatus,
)
from scripts.audit_paper_dashboard_browser import VIEWPORTS
from scripts.inspect_paper_recovery import render_recovery_html


def _fixture_statuses() -> tuple[PaperRecoveryStatus, ...]:
    operator = PaperOperatorStatus(
        new_paper_open_paused=False,
        pause_sequence=0,
        pause_changed_at_ms=0,
        durable_cursor_present=True,
        cursor_sequence=1,
        accepted_candle_count=5,
        last_closed_candle_at_ms=1_700_000_000_000,
        reserved_open_intent_count=0,
        pending_or_unresolved_open_count=0,
        unknown_open_requires_reconciliation=False,
    )
    return (
        PaperRecoveryStatus(
            PaperRecoveryState.UNVERIFIED, "paper_journal_unverified", None,
        ),
        PaperRecoveryStatus(
            PaperRecoveryState.BLOCKED, "paper_operator_paused", operator,
        ),
        PaperRecoveryStatus(
            PaperRecoveryState.PAPER_FLAT_HYPOTHETICAL_ONLY,
            "paper_flat_not_live_verified", operator,
        ),
    )


def run_audit(*, out_dir: Path | None = None) -> dict[str, object]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright offline necessario para QA de navegador.") from exc
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    failures = []
    with sync_playwright() as engine:
        browser_path = next(
            (candidate for name in ("google-chrome", "chromium", "chromium-browser")
             if (candidate := shutil.which(name))), None,
        )
        launch_args = [
            "--disable-background-networking", "--disable-sync",
            "--no-first-run", "--disable-extensions",
        ]
        if browser_path:
            browser = engine.chromium.launch(
                executable_path=browser_path, headless=True, args=launch_args,
            )
        else:
            browser = engine.chromium.launch(
                channel="chrome", headless=True, args=launch_args,
            )
        try:
            for status in _fixture_statuses():
                for width, height in VIEWPORTS:
                    context = browser.new_context(
                        viewport={"width": width, "height": height},
                        device_scale_factor=1,
                        reduced_motion="reduce",
                    )
                    page = context.new_page()
                    external = []

                    def deny_request(route):
                        external.append(route.request.url)
                        route.abort()

                    page.route("**/*", deny_request)
                    page.set_content(render_recovery_html(status), wait_until="load")
                    observed = page.evaluate("""() => {
                      const doc = document.documentElement;
                      const summary = document.querySelector('.summary');
                      const skip = document.querySelector('.skip');
                      const main = document.getElementById('conteudo');
                      const warning = document.querySelector('.warning');
                      const grid = document.querySelector('.grid');
                      const cards = [...document.querySelectorAll('.tile, header, footer, .summary, .warning')];
                      return {
                        width: innerWidth,
                        scroll_width: Math.max(doc.scrollWidth, document.body.scrollWidth),
                        state: summary && summary.getAttribute('data-state'),
                        skip: Boolean(skip && skip.getAttribute('href') === '#conteudo'
                                      && main && main.tabIndex === -1),
                        first_tabbable: document.querySelector('a[href]') === skip,
                        banner_visible: Boolean(warning && warning.getBoundingClientRect().height > 0
                                        && warning.textContent.includes('EXCLUSIVAMENTE PAPER')),
                        forbidden_controls: document.querySelectorAll(
                          'script, form, button, input, iframe, img, link, select, textarea'
                        ).length,
                        outbound_links: [...document.querySelectorAll('a[href]')]
                          .filter(a => a.getAttribute('href') !== '#conteudo').length,
                        clipped: cards.some(el => {
                          const box = el.getBoundingClientRect();
                          return box.left < -1 || box.right > innerWidth + 1
                              || el.scrollWidth > el.clientWidth + 1;
                        }),
                        grid_columns: getComputedStyle(grid).gridTemplateColumns
                          .trim().split(/\s+/).length
                      };
                    }""")
                    errors = []
                    if observed["width"] != width or observed["scroll_width"] > width + 1:
                        errors.append("viewport overflow")
                    if observed["state"] != status.state.value:
                        errors.append("wrong recovery state")
                    if not observed["skip"] or not observed["first_tabbable"]:
                        errors.append("missing accessible skip link")
                    if not observed["banner_visible"]:
                        errors.append("risk warning not visible")
                    if observed["forbidden_controls"] or observed["outbound_links"] or external:
                        errors.append("interactive or external content")
                    if observed["clipped"]:
                        errors.append("clipped mobile text")
                    if width <= 420 and observed["grid_columns"] != 1:
                        errors.append("narrow viewport must have single-column cards")
                    page.keyboard.press("Tab")
                    focused = page.evaluate(
                        "document.activeElement.classList.contains('skip')"
                    )
                    if not focused:
                        errors.append("keyboard did not focus skip link")
                    else:
                        page.keyboard.press("Enter")
                        if page.evaluate("location.hash") != "#conteudo":
                            errors.append("keyboard skip did not navigate")
                    record = {
                        "state": status.state.value, "width": width,
                        "errors": errors, "external_requests": len(external),
                    }
                    results.append(record)
                    failures.extend(
                        f"{status.state.value}@{width}: {problem}"
                        for problem in errors
                    )
                    context.close()
        finally:
            browser.close()
    report = {
        "schema_version": "paper_recovery_browser_qa_v1",
        "mode": "offline_paper",
        "orders_sent": False,
        "live_trading_authorized": False,
        "cases": results,
        "passed": not failures,
        "failures": failures,
    }
    if out_dir is not None:
        (out_dir / "paper-recovery-report.json").write_text(
            json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
    return report


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="QA Chrome de recuperação PAPER offline")
    parser.add_argument("--out-dir", type=Path)
    args = parser.parse_args(argv)
    report = run_audit(out_dir=args.out_dir)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    if not report["passed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
