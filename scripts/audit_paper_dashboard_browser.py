"""J5/PRE3: optional real-browser QA of an OFFLINE synthetic PAPER dashboard.

Run on a machine with free Playwright Python and installed Chromium/Chrome:
    python3 -m scripts.audit_paper_dashboard_browser --out-dir /tmp/paper-ui-qa

The script uses page.set_content(), blocks ALL network requests, and does not
accept external HTML, JSON, URLs, accounts or market feeds. This is NOT a
financial validation, production release or complete WCAG certification.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys

from scripts.render_paper_dashboard import (
    TEMPLATE, make_paper_snapshot, render_paper_dashboard,
)

VIEWPORTS = ((280, 640), (320, 700), (375, 812), (390, 844),
             (768, 1024), (1280, 900))

# Run inside the browser against the actual HTML and CSS from the repository,
# not a mocked layout. The table is intentionally horizontally scrollable at
# small widths but the DOCUMENT itself must never overflow horizontally.
_LAYOUT_JS = r"""() => {
  const w = window.innerWidth;
  const doc = document.documentElement;
  const wanted = [
    '.site-header', '.header-content', '.brand', '.brand span:last-child',
    '.header-label', 'main', '.warning', '.stats', '.stat', '.flow',
    '.flow-step', '.venues', '.card', '.venue-header', '.tag',
    '.venue-metric', '.pending', '.pending > div', '.table-wrap', 'footer'
  ];
  const outside = [];
  const clipped = [];
  for (const selector of wanted) {
    for (const element of document.querySelectorAll(selector)) {
      const r = element.getBoundingClientRect();
      if (r.left < -1 || r.right > w + 1) {
        outside.push({selector, left: Math.round(r.left), right: Math.round(r.right)});
      }
      if (['.brand', '.brand span:last-child', '.card', '.venue-header', '.tag',
           '.stat', '.venue-metric'].includes(selector)
          && element.scrollWidth > element.clientWidth + 1) {
        clipped.push({selector, visible: element.clientWidth,
                      content: element.scrollWidth});
      }
    }
  }
  const skip = document.querySelector('.skip-link');
  const main = document.getElementById('conteudo-principal');
  const table = document.querySelector('.table-wrap');
  const warning = document.querySelector('.warning');
  const firstTabbable = [...document.querySelectorAll('a[href], [tabindex], button, input')]
      .find(el => el.tabIndex >= 0);
  const tableScroll = table ? table.scrollWidth - table.clientWidth : 0;
  function rgb(text) {
    const m = text.match(/rgba?\(([^)]+)\)/);
    return m ? m[1].split(',').slice(0,3).map(Number) : null;
  }
  function lum(channels) {
    if (!channels) return null;
    const parts = channels.map(v => {
      const c = v / 255;
      return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * parts[0] + 0.7152 * parts[1] + 0.0722 * parts[2];
  }
  function contrast(textSelector, backgroundSelector) {
    const fgEl = document.querySelector(textSelector);
    const bgEl = document.querySelector(backgroundSelector);
    if (!fgEl || !bgEl) return 0;
    const a = lum(rgb(getComputedStyle(fgEl).color));
    const b = lum(rgb(getComputedStyle(bgEl).backgroundColor));
    if (a === null || b === null) return 0;
    return Number(((Math.max(a,b) + 0.05)/(Math.min(a,b) + 0.05)).toFixed(2));
  }
  return {
    viewport_width: w,
    document_scroll_width: Math.max(doc.scrollWidth, document.body.scrollWidth),
    outside, clipped,
    banner_visible: Boolean(warning && warning.getBoundingClientRect().height > 0
        && warning.textContent.includes('SIMULADO')),
    skip_link: Boolean(skip && main && skip.getAttribute('href') === '#conteudo-principal'
        && main.tabIndex === -1 && firstTabbable === skip),
    scroll_region: Boolean(table && table.tabIndex === 0
        && table.getAttribute('role') === 'region'
        && table.getAttribute('aria-label')
        && table.getAttribute('aria-describedby') === 'table-scroll-instructions'),
    table_extra_scroll_width: tableScroll,
    contrast: {
      muted_stat: contrast('.stat dt', '.stat'),
      warning: contrast('.warning p', '.warning'),
      flow_description: contrast('.flow-step p', '.flow-step'),
      venue_label: contrast('.venue-header p', '.card')
    }
  };
}"""


def run_audit(*, out_dir: Path | None = None) -> dict[str, object]:
    """Render known PAPER fixtures; fail on geometry, keyboard and network drift."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright nao instalado: usar venv local com playwright (sem API paga)."
        ) from exc

    html = render_paper_dashboard(
        make_paper_snapshot(), TEMPLATE.read_text(encoding="utf-8"),
    )
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, object]] = []
    failures: list[str] = []
    with sync_playwright() as playwright:
        browser_path = next((
            candidate for command in ("chromium", "chromium-browser", "google-chrome")
            if (candidate := shutil.which(command))
        ), None)
        browser_args = [
            "--disable-background-networking", "--disable-sync",
            "--no-first-run", "--no-default-browser-check",
            "--disable-extensions",
        ]
        if browser_path:
            browser = playwright.chromium.launch(
                executable_path=browser_path, headless=True, args=browser_args,
            )
        else:
            # GitHub ubuntu-latest has Google Chrome available by default.
            browser = playwright.chromium.launch(
                channel="chrome", headless=True, args=browser_args,
            )
        try:
            for width, height in VIEWPORTS:
                context = browser.new_context(
                    viewport={"width": width, "height": height},
                    device_scale_factor=1,
                    color_scheme="dark",
                    reduced_motion="reduce",
                )
                page = context.new_page()
                external_requests: list[str] = []

                def deny_request(route):
                    external_requests.append(route.request.url)
                    route.abort()

                page.route("**/*", deny_request)
                page.set_content(html, wait_until="load", timeout=15000)
                observed: dict[str, object] = page.evaluate(_LAYOUT_JS)
                errors: list[str] = []
                if observed["viewport_width"] != width:
                    errors.append("browser viewport did not match requested width")
                if observed["document_scroll_width"] > width + 1:
                    errors.append("document horizontal overflow")
                if observed["outside"]:
                    errors.append("elements extend outside viewport")
                if observed["clipped"]:
                    errors.append("card/header text is clipped")
                if not observed["banner_visible"]:
                    errors.append("SIMULADO warning missing from visible layout")
                if not observed["skip_link"]:
                    errors.append("first tabbable element is not skip-to-content")
                if not observed["scroll_region"]:
                    errors.append("table lacks accessible keyboard scrolling")
                if any(float(ratio) < 4.5 for ratio in observed["contrast"].values()):
                    errors.append("one or more sampled normal-text contrast ratios below 4.5")
                if external_requests:
                    errors.append("unexpected HTTP/remote resource request")
                # Exercise actual keyboard, not only static tabindex.
                page.keyboard.press("Tab")
                focus = page.evaluate(
                    "document.activeElement.classList.contains('skip-link')"
                )
                if not focus:
                    errors.append("keyboard Tab did not focus skip link")
                else:
                    skip_rect = page.locator(".skip-link").bounding_box()
                    if not skip_rect or skip_rect["y"] < -1:
                        errors.append("skip link is not visible when focused")
                    page.keyboard.press("Enter")
                    if page.evaluate("location.hash") != "#conteudo-principal":
                        errors.append("keyboard Enter did not navigate to main landmark")
                table = page.locator(".table-wrap")
                table.focus()
                before = table.evaluate("(el) => el.scrollLeft")
                page.keyboard.press("ArrowRight")
                page.wait_for_timeout(200)
                after = table.evaluate("(el) => el.scrollLeft")
                if observed["table_extra_scroll_width"] > 1 and after <= before:
                    errors.append("keyboard ArrowRight did not scroll narrow table")
                observed["keyboard_skip_passed"] = focus
                observed["keyboard_table_scroll_delta"] = after - before
                observed["external_request_count"] = len(external_requests)
                observed["errors"] = errors
                if out_dir is not None:
                    # Full-page PNG of original content (no injection/fixtures from web).
                    page.evaluate("window.scrollTo(0, 0)")
                    table.evaluate("(el) => { el.scrollLeft = 0; }")
                    page.screenshot(
                        path=str(out_dir / f"paper-mobile-{width}px.png"),
                        full_page=True,
                    )
                results.append(observed)
                failures.extend(f"{width}px: {error}" for error in errors)
                context.close()
        finally:
            browser.close()
    report: dict[str, object] = {
        "schema_version": "paper_browser_qa_v1",
        "mode": "offline_paper",
        "quality": "synthetic_fixture_only",
        "orders_sent": False,
        "live_trading_authorized": False,
        "chrome_viewports": results,
        "passed": not failures,
        "failures": failures,
    }
    if out_dir is not None:
        (out_dir / "paper-browser-report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return report


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="QA local em navegador da pagina PAPER, sem trading ou rede."
    )
    parser.add_argument("--out-dir", type=Path,
                        help="Diretorio local para screenshots PNG e relatorio JSON")
    args = parser.parse_args(argv)
    report = run_audit(out_dir=args.out_dir)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    if not report["passed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
