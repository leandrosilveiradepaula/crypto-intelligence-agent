"""J5/MVP1: real Chromium checks of the offline product, not a static mock.

Uses local file:// from this repo and synthetic inputs only. Network access
is denied. No exchange credentials, private journals or real account data.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys
import time

ENTRY = Path(__file__).resolve().parents[1] / "web" / "app" / "index.html"
WIDTHS = ((320, 720), (390, 844), (768, 1024), (1280, 900))


def run(*, out_dir: Path | None = None) -> dict[str, object]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright local ausente; usar CI mobile PAPER.") from exc
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
    records = []
    problems = []
    with sync_playwright() as playwright:
        path = next((x for name in ("chromium", "chromium-browser", "google-chrome")
                     if (x := shutil.which(name))), None)
        args = ["--disable-background-networking", "--disable-sync",
                "--no-first-run", "--no-default-browser-check",
                "--disable-extensions"]
        browser = (playwright.chromium.launch(executable_path=path, headless=True,
                                              args=args) if path else
                   playwright.chromium.launch(channel="chrome", headless=True,
                                              args=args))
        try:
            for width, height in WIDTHS:
                context = browser.new_context(
                    viewport={"width": width, "height": height},
                    color_scheme="dark", reduced_motion="reduce",
                    accept_downloads=True,
                )
                page = context.new_page()
                errors = []
                outbound = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                def deny_remote(route):
                    url = route.request.url
                    if url.startswith(("http://", "https://", "ws://", "wss://")):
                        outbound.append(url)
                        route.abort()
                    else:
                        route.continue_()
                page.route("**/*", deny_remote)
                page.goto(ENTRY.as_uri(), wait_until="load", timeout=15000)
                page.wait_for_function("() => Boolean(window.CIAEngine)", timeout=5000)
                initial = page.locator("#metric-open").inner_text()
                if initial != "0":
                    errors.append("new browser must begin with no PAPER positions")
                if page.locator("#feed-status").inner_text() != "Não conectado":
                    errors.append("empty live market must not be invented")
                geometry = page.evaluate("""() => ({
                    width: innerWidth,
                    overflow: Math.max(document.documentElement.scrollWidth,
                                      document.body.scrollWidth) - innerWidth,
                    source: document.body.dataset.mode,
                    forms: document.querySelectorAll('form').length
                })""")
                if geometry["overflow"] > 1:
                    errors.append("document overflows mobile viewport")
                if geometry["source"] != "offline_paper" or geometry["forms"] < 2:
                    errors.append("wrong app shell or missing PAPER forms")
                if width == 390:
                    page.locator("#open-submit").click()
                    if page.locator("#metric-open").inner_text() != "1":
                        errors.append("creating PAPER scenario did not open position")
                    for p in ("50", "60", "70"):
                        page.locator(".position-card details summary").first.click()
                        page.locator(".partial-form input").first.fill(p)
                        page.locator(".partial-form button").first.click()
                    balance = page.locator(".position-card .position-balances div").first
                    remaining = page.locator(".position-card .position-balances div").nth(1).locator("strong").inner_text()
                    if remaining != "0,09":
                        errors.append("50/60/70 partials must leave 6% of 1.5 units")
                    page.locator("#leverage").fill("20")
                    page.locator("#settings-form button").click()
                    page.locator("#margin").fill("2")
                    page.locator("#open-submit").click()
                    if page.locator("#metric-open").inner_text() != "2":
                        errors.append("new scenario must reflect new leverage")
                    captions = page.locator(".position-meta").all_inner_texts()
                    if not any("50x" in s for s in captions) or not any("20x" in s for s in captions):
                        errors.append("changing global leverage modified prior position")
                    page.locator("#pause").check()
                    if not page.locator("#open-submit").is_disabled():
                        errors.append("local PAPER pause failed to block new scenario")
                    page.reload(wait_until="load")
                    if page.locator("#metric-open").inner_text() != "2":
                        errors.append("local PAPER positions did not survive reload")
                    if not page.locator("#open-submit").is_disabled():
                        errors.append("local PAPER pause did not survive reload")
                    page.locator("#pause").uncheck()
                    now = int(time.time() * 1000)
                    last = (now // 3600000) * 3600000
                    slots = [{"closed_end_ms": last - (23-i)*3600000,
                              "state": "ok" if i >= 22 else "missing"}
                             for i in range(24)]
                    feed = {
                        "schema_version":"j5-n50-ws-log-progress-v1",
                        "quality":"sanitized_service_log_observation_only",
                        "hours_in_window":24,"slots":slots,"as_of_ms":now,
                        "observed_50_of_50_hours":2,
                        "consecutive_recent_observed_hours":2,
                        "failed_hours":0,"missing_hours":22,"duplicate_hours":0,
                        "source_authenticated":False,
                        "owner_d323_24h_audit_verified":False,
                        "orders_sent":False,
                    }
                    page.locator("#import-file").set_input_files({
                        "name":"n50-sanitized.json","mimeType":"application/json",
                        "buffer":json.dumps(feed).encode(),
                    })
                    page.locator("#n50-ok").wait_for(state="visible", timeout=5000)
                    if page.locator("#n50-ok").inner_text() != "2 / 24":
                        errors.append("count-only N50 import not rendered")
                    research = {
                        "schema_version":"j2-ws-n50-descriptive-24closed-v1",
                        "status":"ws_n50_descriptive_24h_ready",
                        "ws_journal_integrity_replayed":True,
                        "audited_assets":50,"eligible_closed_bars_per_asset":24,
                        "descriptive_up_breakouts":12,
                        "descriptive_down_breakouts":5,
                        "descriptive_inside_bars":33,
                        "formal_d323_24h_verified":False,
                        "marketwide_top50_verified":False,
                        "approved_for_signals":False,"orders_sent":False,
                        "window_digest_sha256":"a"*64,"research_rows":[],
                    }
                    page.locator("#import-file").set_input_files({
                        "name":"j2-count-only.json","mimeType":"application/json",
                        "buffer":json.dumps(research).encode(),
                    })
                    page.locator("#research-count").wait_for(state="visible", timeout=5000)
                    if page.locator("#research-count").inner_text() != "50":
                        errors.append("research count-only import not rendered")
                    malicious = dict(research, status="<img src=x onerror=alert(1)>")
                    page.locator("#import-file").set_input_files({
                        "name":"invalid.json","mimeType":"application/json",
                        "buffer":json.dumps(malicious).encode(),
                    })
                    page.wait_for_function(
                        "() => document.querySelector('#notice').textContent.includes('Importação recusada')",
                        timeout=5000,
                    )
                    if "Importação recusada" not in page.locator("#notice").inner_text():
                        errors.append("untrusted market file not rejected")
                    if page.locator("img").count() or page.locator("script").count() != 2:
                        errors.append("HTML injection on invalid market data")
                if outbound:
                    errors.append("unexpected outbound network activity")
                if out_dir is not None:
                    page.screenshot(path=str(out_dir / f"app-{width}px.png"),
                                    full_page=True)
                records.append({"width":width,"height":height,"layout":geometry,
                                "outbound_requests":len(outbound),"errors":errors})
                problems.extend(f"{width}px: {s}" for s in errors)
                context.close()
            # Exercise actual GET refresh without importing JSON manually. The
            # local server is synthetic and loopback-only, never an exchange.
            from http.server import HTTPServer
            from threading import Thread
            from unittest.mock import patch
            from scripts import serve_j5_local_readonly as local
            now = int(time.time() * 1000)
            latest = (now // 3600000) * 3600000
            slots = [
                {"closed_end_ms": latest - (23 - i) * 3600000,
                 "state": "ok" if i >= 22 else "missing"}
                for i in range(24)
            ]
            fixture = {
                "schema_version": "j5-n50-ws-log-progress-v1",
                "quality": "sanitized_service_log_observation_only",
                "as_of_ms": now, "hours_in_window": 24,
                "slots": slots, "observed_50_of_50_hours": 2,
                "consecutive_recent_observed_hours": 2,
                "failed_hours": 0, "missing_hours": 22,
                "duplicate_hours": 0, "source_authenticated": False,
                "owner_d323_24h_audit_verified": False,
                "orders_sent": False,
            }
            external = []
            local_errors = []
            with patch.object(local, "read_n50_progress", return_value=fixture) as source:
                server = HTTPServer((local.HOST, local.PORT), local.LoopbackPanelHandler)
                worker = Thread(target=server.serve_forever, daemon=True)
                worker.start()
                try:
                    context = browser.new_context(
                        viewport={"width": 390, "height": 844},
                        color_scheme="dark", reduced_motion="reduce",
                    )
                    page = context.new_page()
                    page.on("pageerror", lambda error: local_errors.append(str(error)))
                    def route_local_only(route):
                        url = route.request.url
                        if url.startswith("http://127.0.0.1:8765/"):
                            route.continue_()
                        else:
                            external.append(url)
                            route.abort()
                    page.route("**/*", route_local_only)
                    page.goto("http://127.0.0.1:8765/", wait_until="load")
                    page.wait_for_function(
                        "() => document.querySelector('#n50-ok').textContent === '2 / 24'",
                        timeout=5000,
                    )
                    if source.call_count < 1:
                        local_errors.append("loopback GET did not read sanitized N50")
                    if page.locator("#feed-status").inner_text() != "Fonte local automática":
                        local_errors.append("auto-loaded report not labeled as local source")
                    if page.locator("#refresh-local").is_hidden():
                        local_errors.append("read-only local refresh button is missing")
                    if page.locator("#metric-open").inner_text() != "0":
                        local_errors.append("auto-load created an invalid PAPER position")
                    with patch.object(
                        local, "read_n50_progress",
                        side_effect=local.SourceNotReady("sensitive info hidden")
                    ):
                        page.locator("#refresh-local").click()
                        page.wait_for_function(
                            "() => document.querySelector('#feed-status').textContent === 'Fonte local indisponível'",
                            timeout=5000,
                        )
                        if page.locator("#metric-n50").inner_text() != "— / 24":
                            local_errors.append("stale N50 remained visible after backend error")
                    if external:
                        local_errors.append("browser attempted non-loopback network access")
                    if out_dir is not None:
                        page.screenshot(
                            path=str(out_dir / "app-loopback-390px.png"),
                            full_page=True,
                        )
                    context.close()
                finally:
                    server.shutdown()
                    server.server_close()
                    worker.join(timeout=3)
            problems.extend("loopback: " + x for x in local_errors)
            records.append({
                "width": 390, "mode": "loopback_auto_status",
                "outbound_requests": len(external), "errors": local_errors,
            })
        finally:
            browser.close()
    result = {
        "schema_version":"j5-mobile-paper-app-browser-qa-v1",
        "status":"PASS" if not problems else "FAIL",
        "quality":"local_synthetic_paper_only",
        "screen_count":len(records),"screens":records,
        "orders_sent":False,"network_requests":0,
        "problems":problems,
    }
    if out_dir is not None:
        (out_dir / "app-browser-qa.json").write_text(
            json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out-dir",type=Path)
    args=p.parse_args(argv)
    result=run(out_dir=args.out_dir)
    print(json.dumps(result,ensure_ascii=False,sort_keys=True))
    return 0 if result["status"]=="PASS" else 1


if __name__=="__main__":
    sys.exit(main())
