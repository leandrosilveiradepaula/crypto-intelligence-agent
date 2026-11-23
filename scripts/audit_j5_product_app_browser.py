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
                if width == 320:
                    # J4/J5 automatic PAPER exit triggers run only for explicit
                    # hypothetical mark closes; never on J2 market imports.
                    page.locator("#auto-enabled").check()
                    if page.locator("#auto-config").is_hidden():
                        errors.append("automatic PAPER controls were not shown")
                    page.locator("#open-submit").click()
                    if (page.locator("#metric-open").inner_text() != "1"
                            or page.locator(".auto-step-button").count() != 1):
                        errors.append("automatic PAPER scenario was not created")
                    mark = page.locator(".position-card .mark-reference input").first
                    mark.fill("101")
                    page.locator(".auto-step-button").first.click()
                    if ("Auto PAPER: 1/2 alvos" not in
                            page.locator(".position-meta").first.inner_text()
                            or "0,75" not in
                            page.locator(".position-balances").first.inner_text()):
                        errors.append("first PAPER target did not reduce remaining units")
                    page.reload(wait_until="load")
                    if "Auto PAPER: 1/2 alvos" not in page.locator(".position-meta").first.inner_text():
                        errors.append("automatic PAPER target was not persisted")
                    mark = page.locator(".position-card .mark-reference input").first
                    mark.fill("NaN")
                    page.locator(".auto-step-button").first.click()
                    if ("Fechamento hipotético" not in page.locator("#notice").inner_text()
                            or "Auto PAPER: 1/2 alvos" not in
                            page.locator(".position-meta").first.inner_text()):
                        errors.append("invalid hypothetical mark advanced automatic PAPER state")
                    mark.fill("102")
                    page.locator(".auto-step-button").first.click()
                    if ("Auto PAPER: 2/2 alvos" not in
                            page.locator(".position-meta").first.inner_text()
                            or "0,375" not in
                            page.locator(".position-balances").first.inner_text()):
                        errors.append("second PAPER target did not leave residual runner")
                    mark = page.locator(".position-card .mark-reference input").first
                    mark.fill("99")
                    page.locator(".auto-step-button").first.click()
                    # Ledger is nested in a closed <details>, so expand before
                    # asserting the event text: hidden innerText may be empty.
                    page.locator(".position-card details summary").first.click()
                    if (page.locator("#metric-open").inner_text() != "0"
                            or page.locator(".auto-step-button").count()
                            or "Auto PAPER STOP" not in page.locator(".ledger").inner_text()):
                        errors.append("hypothetical stop did not close PAPER residual")
                    page.reload(wait_until="load")
                    page.locator(".position-card details summary").first.click()
                    if (page.locator("#metric-open").inner_text() != "0"
                            or "Auto PAPER STOP" not in page.locator(".ledger").inner_text()):
                        errors.append("automatic PAPER stop was not persisted after reload")
                    if page.evaluate(
                        "() => document.documentElement.scrollWidth > window.innerWidth + 1"
                    ):
                        errors.append("automatic PAPER panel overflows 320px viewport")
                if width == 768:
                    # One click replays a finite hypothetical mark path. The
                    # path must never be treated as observed market data.
                    page.locator("#auto-enabled").check()
                    page.locator("#open-submit").click()
                    batch = page.locator(".auto-batch-input").first
                    batch.fill("101\n102\n99\n98")
                    page.locator(".auto-batch-button").first.click()
                    page.wait_for_function(
                        "() => document.querySelector('#metric-open').textContent === '0'",
                        timeout=5000,
                    )
                    page.locator(".position-card details summary").first.click()
                    if ("Auto PAPER STOP" not in page.locator(".ledger").inner_text()
                            or "1 ignorados" not in page.locator("#notice").inner_text()
                            or page.locator(".auto-batch-button").count()):
                        errors.append("automatic PAPER batch did not stop and skip future fixture rows")
                    page.reload(wait_until="load")
                    page.locator(".position-card details summary").first.click()
                    if (page.locator("#metric-open").inner_text() != "0"
                            or "Auto PAPER TARGET_2" not in
                            page.locator(".ledger").inner_text()):
                        errors.append("automatic PAPER batch did not survive reload")
                    if page.evaluate(
                        "() => document.documentElement.scrollWidth > innerWidth + 1"
                    ):
                        errors.append("PAPER batch panel overflows tablet viewport")
                if width == 390:
                    page.locator("#open-submit").click()
                    if page.locator("#metric-open").inner_text() != "1":
                        errors.append("creating PAPER scenario did not open position")
                    # Mark input is hypothetical, exact BigInt and cannot change
                    # any position event or persist a market-price claim.
                    mark_input = page.locator(".position-card .mark-reference input").first
                    mark_result = page.locator(".position-card .mark-output").first
                    if ("US$ 0" not in mark_result.inner_text()
                            or mark_result.get_attribute("data-valid") != "true"):
                        errors.append("mark must start at entry reference with zero gross PnL")
                    mark_input.fill("101")
                    if ("US$ 1,5" not in mark_result.inner_text()
                            or mark_result.get_attribute("data-valid") != "true"):
                        errors.append("LONG +1% should yield US$1.50 gross for 50x paper")
                    mark_input.fill("NaN")
                    if ("Mark inválido" not in mark_result.inner_text()
                            or "US$ 1,5" in mark_result.inner_text()
                            or mark_result.get_attribute("data-valid") != "false"):
                        errors.append("invalid mark left stale favorable PnL on screen")
                    mark_input.fill("99")
                    if ("US$ -1,5" not in mark_result.inner_text()
                            or mark_result.get_attribute("data-valid") != "true"):
                        errors.append("LONG -1% should yield negative gross reference")
                    if page.locator("#metric-open").inner_text() != "1":
                        errors.append("mark edit must not open or close PAPER positions")
                    for p in ("50", "60", "70"):
                        page.locator(".position-card details summary").first.click()
                        page.locator(".partial-form input").first.fill(p)
                        page.locator(".partial-form button").first.click()
                    balance = page.locator(".position-card .position-balances div").first
                    remaining = page.locator(".position-card .position-balances div").nth(1).locator("strong").inner_text()
                    if remaining != "0,09":
                        errors.append("50/60/70 partials must leave 6% of 1.5 units")
                    partial_mark = page.locator(".position-card .mark-reference input").first
                    partial_result = page.locator(".position-card .mark-output").first
                    partial_mark.fill("101")
                    if ("US$ 0,09" not in partial_result.inner_text()
                            or partial_result.get_attribute("data-valid") != "true"):
                        errors.append("mark PnL must use remaining units after partial exits")
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
                    # Real browser roundtrip: the exported JSON must be
                    # restorable, with explicit destructive confirmation.
                    with page.expect_download(timeout=5000) as exported:
                        page.locator("#export-paper").click()
                    backup_bytes = Path(exported.value.path()).read_bytes()
                    backup = json.loads(backup_bytes)
                    if (backup["schema_version"] != "cia-j5-paper-local-export-v1"
                            or backup["simulation_only"] is not True
                            or backup["orders_sent"] is not False
                            or len(backup["state"]["positions"]) != 2):
                        errors.append("PAPER export schema was not suitable for restore")
                    page.once("dialog", lambda dialog: dialog.accept())
                    page.locator("#reset-paper").click()
                    if page.locator("#metric-open").inner_text() != "0":
                        errors.append("PAPER local reset did not clear scenarios")
                    page.once("dialog", lambda dialog: dialog.dismiss())
                    page.locator("#import-file").set_input_files({
                        "name":"paper-restore.json", "mimeType":"application/json",
                        "buffer":backup_bytes,
                    })
                    page.wait_for_function(
                        "() => document.querySelector('#notice').textContent.includes('Restauração cancelada')",
                        timeout=5000,
                    )
                    if page.locator("#metric-open").inner_text() != "0":
                        errors.append("cancelled PAPER restore still modified state")
                    page.once("dialog", lambda dialog: dialog.accept())
                    page.locator("#import-file").set_input_files({
                        "name":"paper-restore.json", "mimeType":"application/json",
                        "buffer":backup_bytes,
                    })
                    page.wait_for_function(
                        "() => document.querySelector('#metric-open').textContent === '2'",
                        timeout=5000,
                    )
                    if len(page.locator(".position-card").all_inner_texts()) != 2:
                        errors.append("PAPER restore lost simulated positions")
                    bad_order = dict(backup, orders_sent=True)
                    page.locator("#import-file").set_input_files({
                        "name":"paper-order-forgery.json", "mimeType":"application/json",
                        "buffer":json.dumps(bad_order).encode(),
                    })
                    page.wait_for_function(
                        "() => document.querySelector('#notice').textContent.includes('Importação recusada')",
                        timeout=5000,
                    )
                    if page.locator("#metric-open").inner_text() != "2":
                        errors.append("PAPER order-forgery backup replaced state")
                    poisoned = json.loads(backup_bytes)
                    poisoned["state"]["positions"][0]["unexpected_credentials"] = "reject"
                    page.locator("#import-file").set_input_files({
                        "name":"paper-extra-fields.json", "mimeType":"application/json",
                        "buffer":json.dumps(poisoned).encode(),
                    })
                    page.wait_for_function(
                        "() => document.querySelector('#notice').textContent.includes('campos desconhecidos')",
                        timeout=5000,
                    )
                    if page.locator("#metric-open").inner_text() != "2":
                        errors.append("PAPER extra-field backup replaced state")
                    recycled = json.loads(backup_bytes)
                    recycled["state"]["nextId"] = 1
                    page.locator("#import-file").set_input_files({
                        "name":"paper-reused-id.json", "mimeType":"application/json",
                        "buffer":json.dumps(recycled).encode(),
                    })
                    page.wait_for_function(
                        "() => document.querySelector('#notice').textContent.includes('contador de IDs inconsistente')",
                        timeout=5000,
                    )
                    if page.locator("#metric-open").inner_text() != "2":
                        errors.append("reused PAPER ID backup replaced valid state")
                    page.reload(wait_until="load")
                    if page.locator("#metric-open").inner_text() != "2":
                        errors.append("restored PAPER scenarios did not survive reload")
                    if not all("US$ 0" in value for value in
                               page.locator(".position-card .mark-output").all_inner_texts()):
                        errors.append("manual hypothetical marks must not persist in PAPER backup")
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
                    ws_shortlist = {
                        "schema_version":"j2-n50-ws-descriptive-watchlist-v1",
                        "status":"ws_descriptive_watchlist_ready",
                        "quality":"private_ws_observations_not_trading_signals",
                        "ws_journal_integrity_replayed":True,
                        "audited_assets":50,"eligible_closed_bars_per_asset":24,
                        "btc_context_available":True,
                        "latest_closed_end_ms":last,
                        "window_digest_sha256":"a"*64,
                        "observed_up_breakout_candidates":1,
                        "observed_down_breakout_candidates":1,
                        "unclassified_volume_assets":0,
                        "up_breakout_watchlist":[{
                            "symbol":"AAAUSDT", "breakout":"above_prior_23h_high",
                            "relative_vs_btc_pct_points":"1.2",
                            "return_24bars_pct":"4.4",
                            "mean_true_range_14_pct":"1.3",
                            "quote_turnover_24bars_usdt":"100000",
                            "last_quote_turnover_vs_prior23_mean":"1.6",
                            "approved_for_signals":False,"orders_sent":False,
                        }],
                        "down_breakout_watchlist":[{
                            "symbol":"BBBUSDT",
                            "breakout":"below_prior_23h_low",
                            "relative_vs_btc_pct_points":"-2.4",
                            "return_24bars_pct":"-4.4",
                            "mean_true_range_14_pct":"1.1",
                            "quote_turnover_24bars_usdt":"90000",
                            "last_quote_turnover_vs_prior23_mean":"1.2",
                            "approved_for_signals":False,"orders_sent":False,
                        }],
                        "formal_d323_24h_verified":False,
                        "continuous_collector_verified":False,
                        "rotation_36h_live_verified":False,
                        "marketwide_top50_verified":False,
                        "crypto_identity_independently_verified":False,
                        "source_authenticated":False,
                        "approved_for_signals":False,"approved_for_live_use":False,
                        "financial_backtest_approved":False,
                        "orders_sent":False,"systemd_modified":False,
                        "execution_intents_created":0,"network_requests":0,
                        "database_mutation_statements":0,
                    }
                    page.locator("#import-file").set_input_files({
                        "name":"j2-private-watchlist.json",
                        "mimeType":"application/json",
                        "buffer":json.dumps(ws_shortlist).encode(),
                    })
                    page.locator("#watchlist-up-count").wait_for(
                        state="visible", timeout=5000)
                    if (page.locator("#watchlist-up-count").inner_text() != "1"
                            or page.locator("#watchlist-down-count").inner_text() != "1"
                            or page.locator("#watchlist-up-rows .research-item").count() != 1
                            or page.locator("#watchlist-down-rows .research-item").count() != 1
                            or "AAAUSDT" not in page.locator("#watchlist-up-rows").inner_text()
                            or "BBB" not in page.locator("#watchlist-down-rows").inner_text()):
                        errors.append("private WS shortlist not shown in mobile cards")
                    if page.locator("#metric-open").inner_text() != "2":
                        errors.append("watchlist import wrongly created a PAPER position")
                    fits = page.evaluate(
                        "() => document.documentElement.scrollWidth <= window.innerWidth + 1"
                    )
                    if not fits:
                        errors.append("private shortlist overflows mobile viewport")
                    if out_dir is not None:
                        page.screenshot(path=str(out_dir / f"app-{width}px-watchlist.png"),
                                        full_page=True)
                    count_only_shortlist = dict(
                        ws_shortlist, up_breakout_watchlist=[],
                        down_breakout_watchlist=[],
                    )
                    page.locator("#import-file").set_input_files({
                        "name":"j2-count-only-watchlist.json",
                        "mimeType":"application/json",
                        "buffer":json.dumps(count_only_shortlist).encode(),
                    })
                    if (page.locator("#watchlist-up-rows .research-item").count()
                            or page.locator("#watchlist-down-rows .research-item").count()
                            or "AAAUSDT" in page.locator("#watchlist-up-rows").inner_text()):
                        errors.append("count-only watchlist leaked names")
                    forged = dict(
                        ws_shortlist, up_breakout_watchlist=[
                            dict(ws_shortlist["up_breakout_watchlist"][0],
                                 symbol="<img src=x onerror=alert(1)>")
                        ],
                    )
                    page.locator("#import-file").set_input_files({
                        "name":"j2-invalid-watchlist.json",
                        "mimeType":"application/json",
                        "buffer":json.dumps(forged).encode(),
                    })
                    page.wait_for_function(
                        "() => document.querySelector('#notice').textContent.includes('Importação recusada')",
                        timeout=5000,
                    )
                    if (page.locator("#watchlist-up-rows .research-item").count()
                            or page.locator("img").count()):
                        errors.append("invalid private shortlist was rendered")
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
                    # Exact script allowlist catches injected HTML while
                    # accepting reviewed local PAPER read-only renderers.
                    allowed_scripts = (
                        "./engine.js", "./public-market.js", "./persisted-paper.js",
                        "./integrated-paper-cycle.js",
                        "./research-scorebook.js", "./paper-ws-health.js",
                        "./paper-watch.js", "./resident-paper.js",
                        "./last-public-paper-lease.js",
                        "./prospective-research.js", "./app.js",
                    )
                    actual_scripts = page.locator("script[src]").evaluate_all(
                        "(nodes) => nodes.map(n => n.getAttribute('src')).sort()"
                    )
                    if (page.locator("img").count()
                            or page.locator("script").count() != len(allowed_scripts)
                            or actual_scripts != sorted(allowed_scripts)):
                        errors.append("HTML injection on invalid market data")

                    # D399: exercise the REAL import and renderer in Chrome,
                    # including risk veto, forged PnL, and volatile lifetime.
                    risk = {
                        "schema_version":"paper-partial-derisk-risk-d398-v1",
                        "status":"conditional_closed_after_observed_partial_derisk_proxy",
                        "leverage_at_open_intent":50,
                        "mark_ticks_checked":4,"confirmed_paper_fills_applied":2,
                        "full_notional_proxy_vetoed":True,"has_discrete_terminal":False,
                        "conditional_net_after_partial_risk_quote":"3.394",
                        "partial_derisking_applies_after_explicit_fill_only":True,
                        "liquidation_checked_before_same_tick_fill":True,
                        "no_unobserved_intrabar_ticks_assumed":True,
                        "margin_added_from_fills":False,
                        "funding_calendar_complete":False,
                        "risk_tiers_authenticated_by_venue":False,
                        "venue_leverage_verified":False,
                        "venue_liquidation_verified":False,
                        "liquidation_formula_verified":False,
                        "net_pnl_verified":False,
                        "orders_sent":False,"order_submission_enabled":False,
                        "approved_for_live_use":False,
                    }
                    page.locator("#import-file").set_input_files({
                        "name":"d399-synthetic-risk.json",
                        "mimeType":"application/json",
                        "buffer":json.dumps(risk).encode(),
                    })
                    page.locator("#risk-audit-loaded").wait_for(
                        state="visible", timeout=5000)
                    if (page.locator("#risk-audit-status").inner_text() !=
                            "Referência condicional"
                            or "3.394" not in page.locator("#risk-value").inner_text()
                            or "NÃO é PnL" not in page.locator("#risk-value").inner_text()
                            or page.locator("#risk-leverage").inner_text() != "50x"
                            or page.locator("#risk-fills").inner_text() != "2"
                            or page.locator("#metric-open").inner_text() != "2"):
                        errors.append("conditional D398 risk report not rendered safely")
                    if page.evaluate(
                        "() => document.documentElement.scrollWidth > window.innerWidth + 1"
                    ):
                        errors.append("D399 risk panel overflows 320px viewport")
                    if out_dir is not None:
                        page.screenshot(
                            path=str(out_dir / "app-320px-d399-risk.png"),
                            full_page=True,
                        )
                    forged_risk = dict(risk, net_pnl_verified=True)
                    page.locator("#import-file").set_input_files({
                        "name":"d399-false-profit.json",
                        "mimeType":"application/json",
                        "buffer":json.dumps(forged_risk).encode(),
                    })
                    page.wait_for_function(
                        "() => document.querySelector('#notice').textContent.includes('Importação recusada')",
                        timeout=5000,
                    )
                    if ("3.394" not in page.locator("#risk-value").inner_text()
                            or page.locator("#metric-open").inner_text() != "2"):
                        errors.append("forged J3 profit replaced safe report or local state")
                    veto = dict(
                        risk, status="abstain_partial_risk_liquidation_proxy",
                        mark_ticks_checked=2, confirmed_paper_fills_applied=0,
                        has_discrete_terminal=True,
                        conditional_net_after_partial_risk_quote=None,
                    )
                    page.locator("#import-file").set_input_files({
                        "name":"d399-liquidation-veto.json",
                        "mimeType":"application/json",
                        "buffer":json.dumps(veto).encode(),
                    })
                    page.wait_for_function(
                        "() => document.querySelector('#risk-decision').textContent.includes('Possível liquidação')",
                        timeout=5000,
                    )
                    if ("Possível liquidação" not in page.locator("#risk-decision").inner_text()
                            or "não disponível" not in page.locator("#risk-value").inner_text()
                            or "3.394" in page.locator("#risk-value").inner_text()):
                        errors.append("liquidation veto still displayed a financial number")
                    page.reload(wait_until="load")
                    if (not page.locator("#risk-audit-loaded").is_hidden()
                            or not page.locator("#risk-audit-empty").is_visible()
                            or page.locator("#metric-open").inner_text() != "2"):
                        errors.append("transient J3 risk report leaked into local PAPER storage")

                    # D407: persisted AUTO4 view is distinct from browser PAPER lab.
                    # Quotes, orders, account data and exchange network stay absent.
                    durable = {
                        "schema_version":"paper_positions_snapshot_v1",
                        "mode":"offline_paper",
                        "quality":"synthetic_journal_replay_only",
                        "source_provenance":"local_sqlite_digest_not_exchange_authenticated",
                        "selection":"explicit_ids_same_sqlite_read_transaction",
                        "no_cross_instrument_quantity_aggregation":True,
                        "orders_sent":False,
                        "live_trading_authorized":False,
                        "approved_for_live_use":False,
                        "financial_pnl_available":False,
                        "positions":[{
                            "position_id":"fixture_d407_unsafe_reconcile",
                            "venue_candidate":"bybit_v5",
                            "symbol_fixture":"ETHUSDT",
                            "side":"LONG",
                            "checkpoint_utc":"2026-11-16T13:00:00.002Z",
                            "initial_confirmed_units":"100",
                            "filled_exit_units":"30",
                            "reserved_unfilled_units":"20",
                            "confirmed_remaining_units":"70",
                            "unreserved_units":"50",
                            "runner_floor_units":"6",
                            "runner_filled_units":"0",
                            "runner_reserved_unfilled_units":"0",
                            "runner_unallocated_units":"6",
                            "runner_readiness":"PENDING_EXIT_RECONCILIATION",
                            "trailing_stop_active":False,
                            "native_stop_verified":False,
                            "recovered_runner":None,
                            "margin_intent_requested":None,
                            "opening_order_cross_checked":False,
                            "pending_or_unknown_orders":1,
                            "unknown_order_count":1
                        }]
                    }
                    page.locator("#import-file").set_input_files({
                        "name":"d407-durable-fixture.json",
                        "mimeType":"application/json",
                        "buffer":json.dumps(durable).encode(),
                    })
                    page.locator("#persisted-paper-loaded").wait_for(
                        state="visible", timeout=5000)
                    panel_text = page.locator("#persisted-paper-rows").inner_text()
                    if (page.locator("#persisted-paper-status").inner_text() !=
                            "Reconciliação pendente"
                            or "parciais preenchidas: 30" not in panel_text
                            or "Restante: 70" not in panel_text
                            or "Saída pendente: reconciliar" not in panel_text
                            or page.locator("#metric-open").inner_text() != "2"):
                        errors.append("D407 durable PAPER balances/reconciliation not displayed")
                    tampered = dict(durable, orders_sent=True)
                    page.locator("#import-file").set_input_files({
                        "name":"d407-forged-live.json",
                        "mimeType":"application/json",
                        "buffer":json.dumps(tampered).encode(),
                    })
                    page.wait_for_function(
                        "() => document.querySelector('#notice').textContent.includes('Importação recusada')",
                        timeout=5000)
                    if ("Restante: 70" not in page.locator(
                            "#persisted-paper-rows").inner_text()
                            or page.locator("#metric-open").inner_text() != "2"):
                        errors.append("D407 forged live report replaced safe PAPER or local lab")
                    page.reload(wait_until="load")
                    if (not page.locator("#persisted-paper-loaded").is_hidden()
                            or not page.locator("#persisted-paper-empty").is_visible()
                            or page.locator("#metric-open").inner_text() != "2"):
                        errors.append("D407 imported durable state persisted across reload")

                    # D408: scored opportunity history is only reference evidence,
                    # not a permission to send orders or create PAPER positions.
                    def horizon(h, records, scored, empty, matured,
                                good=0, bad=0, neutral=0, total=None, average=None):
                        return {
                            "horizon_hours":h, "records":records,
                            "scored_decisions":scored, "empty_decisions":empty,
                            "matured_research_observations":matured,
                            "directionally_favorable":good,
                            "directionally_contrary":bad, "unchanged":neutral,
                            "net_reference_bps_sum_under_individual_assumptions":total,
                            "net_reference_bps_mean_per_observation":average,
                        }
                    scorebook = {
                        "schema_version":"j3-ws-prospective-evidence-summary-d408-v1",
                        "status":"descriptive_forward_research_not_strategy_validation",
                        "source":"imported_owner_report_contract_only_not_independently_attested",
                        "report_records_accepted":2,
                        "distinct_decision_hours_in_supplied_files":1,
                        "horizons":[
                            horizon(1,1,1,0,2,good=1,bad=1,total="5.0",average="2.5000"),
                            horizon(4,1,0,1,0),
                            horizon(8,0,0,0,0),
                        ],
                        "all_decision_windows_present_verified":False,
                        "cost_assumptions_consistent_across_decisions_verified":False,
                        "prospective_registration_independently_verified":False,
                        "out_of_sample_results_validated":False,
                        "strategy_profitable_verified":False,
                        "financial_backtest_approved":False,
                        "marketwide_top50_verified":False,
                        "approved_for_signals":False,
                        "approved_for_live_use":False,
                        "orders_sent":False,
                        "network_requests":0,
                        "database_accessed":False,
                        "database_mutation_statements":0,
                    }
                    page.locator("#import-file").set_input_files({
                        "name":"d408-research-summary.json", "mimeType":"application/json",
                        "buffer":json.dumps(scorebook).encode(),
                    })
                    page.locator("#research-scorebook-loaded").wait_for(
                        state="visible", timeout=5000)
                    if (page.locator("#research-scorebook-status").inner_text()
                            != "Pesquisa prospectiva · não validada"
                            or "Horizonte 1h" not in page.locator(
                                "#research-scorebook-rows").inner_text()
                            or "sem candidatos: 1" not in page.locator(
                                "#research-scorebook-rows").inner_text()
                            or page.locator("#metric-open").inner_text() != "2"):
                        errors.append("D408 forward research evidence not shown independently")
                    forged_scorebook = dict(scorebook, approved_for_signals=True)
                    page.locator("#import-file").set_input_files({
                        "name":"d408-forged-signal.json", "mimeType":"application/json",
                        "buffer":json.dumps(forged_scorebook).encode(),
                    })
                    page.wait_for_function(
                        "() => document.querySelector('#notice').textContent.includes('Importação recusada')",
                        timeout=5000)
                    if "Horizonte 1h" not in page.locator(
                            "#research-scorebook-rows").inner_text():
                        errors.append("forged signal replaced valid J3 research")
                    page.reload(wait_until="load")
                    if (not page.locator("#research-scorebook-loaded").is_hidden()
                            or not page.locator("#research-scorebook-empty").is_visible()
                            or page.locator("#metric-open").inner_text() != "2"):
                        errors.append("D408 research imported history persisted after reload")

                    # D403: real import path for public REST price samples.
                    # All Chrome test fixtures are synthetic; never fetch Bybit.
                    observed = int(time.time() * 1000)
                    pulse = {
                        "schema_version": "bybit-public-rest-price-pulse-d403-v1",
                        "status": "rest_snapshot_display_only",
                        "source": "bybit_v5_public_linear_tickers",
                        "server_at_ms": observed - 50,
                        "captured_at_ms": observed,
                        "observed_symbol_count": 1,
                        "quotes": [{
                            "symbol": "BTCUSDT", "last_price": "100.01",
                            "mark_price": "100", "bid_price": "99.99",
                            "ask_price": "100.02", "bid_size": "2",
                            "ask_size": "3", "turnover_24h": "1023.5",
                        }],
                        "network_gets_in_this_capture": 1,
                        "crypto_only_membership_verified": False,
                        "continuous_websocket_verified": False,
                        "imported_report_authenticated_by_browser": False,
                        "paper_positions_linked": False,
                        "orders_sent": False,
                        "approved_for_signals": False,
                        "approved_for_live_use": False,
                    }
                    page.locator("#import-file").set_input_files({
                        "name":"d403-rest-synthetic.json",
                        "mimeType":"application/json",
                        "buffer":json.dumps(pulse).encode(),
                    })
                    page.locator("#public-market-loaded").wait_for(
                        state="visible", timeout=5000)
                    if (page.locator("#public-market-status").inner_text() !=
                            "Amostra REST recente"
                            or "Mark: 100" not in page.locator(
                                "#public-market-rows").inner_text()
                            or "BTCUSDT" not in page.locator(
                                "#public-market-rows").inner_text()
                            or page.locator("#metric-open").inner_text() != "2"):
                        errors.append("D403 REST price import did not render safely")
                    forged = dict(pulse, orders_sent=True)
                    page.locator("#import-file").set_input_files({
                        "name":"d403-forged-account.json",
                        "mimeType":"application/json",
                        "buffer":json.dumps(forged).encode(),
                    })
                    page.wait_for_function(
                        "() => document.querySelector('#notice').textContent.includes('Importação recusada')",
                        timeout=5000)
                    if "Mark: 100" not in page.locator(
                            "#public-market-rows").inner_text():
                        errors.append("forged D403 quote replaced accepted report")
                    stale = dict(
                        pulse, server_at_ms=observed-120050,
                        captured_at_ms=observed-120000,
                    )
                    page.locator("#import-file").set_input_files({
                        "name":"d403-stale.json",
                        "mimeType":"application/json",
                        "buffer":json.dumps(stale).encode(),
                    })
                    page.wait_for_function(
                        "() => document.querySelector('#public-market-status').textContent.includes('vencida')",
                        timeout=5000)
                    if ("preços antigos" not in page.locator(
                            "#public-market-summary").inner_text()
                            or page.locator("#metric-open").inner_text() != "2"):
                        errors.append("old REST sample displayed as current or modified PAPER")
                    page.reload(wait_until="load")
                    if (not page.locator("#public-market-loaded").is_hidden()
                            or not page.locator("#public-market-empty").is_visible()
                            or page.locator("#metric-open").inner_text() != "2"):
                        errors.append("public REST quotes persisted after browser reload")
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
            j2_fixture = {
                "schema_version": "j2-ws-n50-descriptive-24closed-v1",
                "status": "ws_n50_descriptive_24h_ready",
                "ws_journal_integrity_replayed": True,
                "audited_assets": 50, "eligible_closed_bars_per_asset": 24,
                "descriptive_up_breakouts": 12,
                "descriptive_down_breakouts": 5,
                "descriptive_inside_bars": 33,
                "formal_d323_24h_verified": False,
                "marketwide_top50_verified": False,
                "approved_for_signals": False,
                "orders_sent": False,
                "window_digest_sha256": "a" * 64,
                "research_rows": [],
            }
            external = []
            local_errors = []
            public_fixture = {
                "schema_version": "bybit-public-rest-price-pulse-d403-v1",
                "status": "rest_snapshot_display_only",
                "source": "bybit_v5_public_linear_tickers",
                "server_at_ms": now - 50,
                "captured_at_ms": now,
                "observed_symbol_count": 1,
                "network_gets_in_this_capture": 1,
                "quotes": [{
                    "symbol": "BTCUSDT", "last_price": "50000",
                    "mark_price": "50001", "bid_price": "49999",
                    "ask_price": "50002", "bid_size": "2",
                    "ask_size": "3", "turnover_24h": "123456",
                }],
                "crypto_only_membership_verified": False,
                "continuous_websocket_verified": False,
                "imported_report_authenticated_by_browser": False,
                "paper_positions_linked": False,
                "orders_sent": False, "approved_for_signals": False,
                "approved_for_live_use": False,
            }
            local.LoopbackPanelHandler.market_symbols = ("BTCUSDT",)
            local.LoopbackPanelHandler.market_last_attempt_ms = 0
            local.LoopbackPanelHandler.market_cached = None
            with patch.object(local, "read_n50_progress", return_value=fixture) as source, patch.object(
                local, "read_j2_descriptive", return_value=j2_fixture
            ) as j2_source, patch.object(
                local, "read_public_market_prices", return_value=public_fixture
            ) as public_source:
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
                    page.wait_for_function("() => Boolean(window.CIAPublicMarket)", timeout=5000)
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
                    page.wait_for_function(
                        "() => document.querySelector('#research-count').textContent === '50'",
                        timeout=5000,
                    )
                    # D404: same-origin automatic REAL public REST schema,
                    # with a fully injected fixture: zero internet in Chrome.
                    page.wait_for_function(
                        "() => document.querySelector('#public-market-status').textContent === 'Amostra REST recente'",
                        timeout=5000,
                    )
                    if ("Mark: 50001" not in page.locator("#public-market-rows").inner_text()
                            or public_source.call_count != 1
                            or page.locator("#refresh-public-market-local").is_hidden()):
                        local_errors.append("public REST auto pulse not surfaced in loopback")
                    with patch.object(
                        local, "read_public_market_prices",
                        side_effect=local.SourceNotReady("never leak private paths"),
                    ) as missing:
                        # Force a fresh server attempt after synthetic outage.
                        local.LoopbackPanelHandler.market_last_attempt_ms = 0
                        local.LoopbackPanelHandler.market_cached = None
                        page.locator("#refresh-public-market-local").click()
                        page.wait_for_function(
                            "() => document.querySelector('#public-market-status').textContent === 'Fonte REST indisponível'",
                            timeout=5000,
                        )
                        if (not page.locator("#public-market-loaded").is_hidden()
                                or not page.locator("#public-market-empty").is_visible()
                                or page.locator("#metric-open").inner_text() != "0"
                                or missing.call_count != 1):
                            local_errors.append("failed local market refresh left stale quote")
                    # Manual import takes priority and never gets clobbered by
                    # later background or button refresh while this tab lives.
                    page.locator("#import-file").set_input_files({
                        "name":"manually-reviewed-pulse.json",
                        "mimeType":"application/json",
                        "buffer":json.dumps(public_fixture).encode(),
                    })
                    page.wait_for_function(
                        "() => document.querySelector('#public-market-rows').textContent.includes('Mark: 50001')",
                        timeout=5000,
                    )
                    with patch.object(
                        local, "read_public_market_prices",
                        side_effect=AssertionError("manual priority must not fetch"),
                    ) as forbidden:
                        page.locator("#refresh-public-market-local").click()
                        if (forbidden.call_count > 0 or
                                page.locator("#public-market-loaded").is_hidden()):
                            local_errors.append("manual REST import lost its priority")
                    if j2_source.call_count < 1:
                        local_errors.append("loopback J2 GET did not read research summary")
                    if page.locator("#research-status").inner_text() != "Descritivo · fonte local":
                        local_errors.append("J2 count-only auto-report not labeled as local")
                    if page.locator("#research-rows .research-item").count():
                        local_errors.append("loopback J2 leaked private symbol rows")
                    with patch.object(
                        local, "read_j2_descriptive",
                        side_effect=local.SourceNotReady("private journal not ready"),
                    ):
                        page.locator("#refresh-research-local").click()
                        page.wait_for_function(
                            "() => document.querySelector('#research-status').textContent === 'J2 ainda indisponível'",
                            timeout=5000,
                        )
                        if not page.locator("#research-loaded").is_hidden():
                            local_errors.append("old J2 breakout still visible after source failure")
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
                    local.LoopbackPanelHandler.market_symbols = ()
                    local.LoopbackPanelHandler.market_last_attempt_ms = 0
                    local.LoopbackPanelHandler.market_cached = None
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
