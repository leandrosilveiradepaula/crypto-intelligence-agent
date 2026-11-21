"""J5/MVP1: actual local PAPER math plus offline web contract.

The node tests use only built-in APIs; no JavaScript packages, broker, REST,
SQLite or live market data. Browser interaction is covered by Playwright QA.
"""
from __future__ import annotations

from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "web" / "app"

class _Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
    def handle_starttag(self, name, attrs):
        self.tags.append((name, dict(attrs)))

class AppLayoutContractTests(unittest.TestCase):
    def test_local_app_entrypoint_csp_and_accessible_navigation(self):
        html = (APP / "index.html").read_text(encoding="utf-8")
        parser = _Page()
        parser.feed(html)
        parser.close()
        tags = parser.tags
        self.assertTrue(any(t=="html" and a.get("lang")=="pt-BR" for t,a in tags))
        self.assertTrue(any(t=="meta" and a.get("name")=="viewport" for t,a in tags))
        csp = [a["content"] for t,a in tags
               if t=="meta" and a.get("http-equiv")=="Content-Security-Policy"]
        self.assertEqual(len(csp), 1)
        for rule in ("default-src 'none'", "connect-src 'self'",
                     "script-src 'self'", "form-action 'none'", "base-uri 'none'"):
            self.assertIn(rule, csp[0])
        scripts = [a.get("src") for t,a in tags if t=="script"]
        self.assertEqual(scripts, ["./engine.js", "./public-market.js", "./persisted-paper.js", "./integrated-paper-cycle.js", "./research-scorebook.js", "./paper-ws-health.js", "./paper-watch.js", "./resident-paper.js", "./last-public-paper-lease.js", "./prospective-research.js", "./app.js"])
        self.assertTrue(any(t=="link" and a.get("href")=="./style.css"
                            for t,a in tags))
        self.assertTrue(any(t=="a" and a.get("href")=="#conteudo"
                            for t,a in tags))
        for section in ("resumo", "mercado", "posicoes", "configuracoes"):
            self.assertTrue(any(t=="section" and a.get("id")==section
                                for t,a in tags))
        self.assertIn('data-live-orders="disabled"', html)
        self.assertIn('PAPER · OFFLINE', html)
        self.assertIn('Não conectado', html)
        self.assertIn("50x", html)
        self.assertIn('id="paper-ws-health-status"', html)
        self.assertIn('id="paper-ws-health-rows"', html)
        self.assertIn('id="quality-n50"', html)
        self.assertIn('id="quality-j2"', html)
        self.assertIn("Qualidade dos dados", html)
        self.assertIn('id="metric-stress"', html)
        self.assertIn('id="metric-stress-count"', html)
        self.assertIn("Não é VaR", html)
        self.assertIn('id="n50-scope"', html)
        self.assertIn('id="n50-scope-note"', html)
        self.assertIn("Horas da mesma coorte", html)
        for item in ("watchlist-title", "watchlist-status", "watchlist-up-count",
                     "watchlist-down-count", "watchlist-up-rows",
                     "watchlist-down-rows", "watchlist-note"):
            self.assertIn(f'id="{item}"', html)
        self.assertIn("Observações selecionadas J2", html)
        self.assertIn('id="prospective-status"', html)
        self.assertIn('id="prospective-horizons"', html)
        self.assertIn("sem candidatos", html.lower())
        self.assertIn("Importar relatórios ou restaurar PAPER", html)
        self.assertIn('id="auto-enabled"', html)
        self.assertIn('id="auto-target1"', html)
        self.assertIn('id="auto-stop"', html)
        self.assertIn("Simular próximo fechamento", (APP / "app.js").read_text(encoding="utf-8"))
        self.assertIn("substitui cenários locais somente após sua confirmação", html)
        self.assertIn("não é previsão, sinal ou ordem", html)
        self.assertNotIn("api.bybit.com", html)

    def test_browser_code_has_no_transport_or_dynamic_html_execution(self):
        for filename in ("engine.js", "public-market.js", "persisted-paper.js", "research-scorebook.js", "prospective-research.js", "app.js"):
            data=(APP / filename).read_text(encoding="utf-8")
            for dangerous in (
                "XMLHttpRequest(", "WebSocket(", "sendBeacon(",
                "eval(", "new Function(", ".innerHTML", "localStorage.clear()",
                "sessionStorage.clear()",
            ):
                self.assertNotIn(dangerous, data, f"{filename}: {dangerous}")
            self.assertNotIn("api.bybit.com", data)
        js = (APP / "app.js").read_text(encoding="utf-8")
        self.assertEqual(js.count('window.fetch("/api/n50-progress"'), 1)
        self.assertEqual(js.count('window.fetch("/api/j2-research"'), 1)
        self.assertIn('researchOrigin === "manual"', js)
        self.assertIn('window.setInterval(() => { void refreshLocalResearch(); }, 300_000);', js)
        self.assertIn('loc.protocol === "http:"', js)
        self.assertIn('loc.port === "8765"', js)
        self.assertIn('loc.hostname === "127.0.0.1"', js)
        self.assertIn('loc.hostname === "localhost"', js)
        self.assertIn('feedOrigin === "manual"', js)
        self.assertIn("function renderQuality()", js)
        self.assertIn('function validateWatchlist(snapshot)', js)
        self.assertIn('function renderWatchlist()', js)
        self.assertIn("mark-reference", js)
        self.assertIn("E.grossHypotheticalMarginImpactBps(", js)
        self.assertIn("Impacto bruto na margem original PAPER", js)
        self.assertIn("E.adversePaperShockLossCents(position, 100)", js)
        self.assertIn("E.adversePaperShockLossCents(position, 200)", js)
        self.assertIn('set("metric-stress", amount(adverse2))', js)
        self.assertIn("liquidação real desconhecida", js)
        self.assertIn("E.applyAutoPaperStep(position,", js)
        self.assertIn("E.replayAutoPaperMarks(position, marks)", js)
        self.assertIn("auto-batch-input", js)
        self.assertIn("Reproduzir cenário PAPER", js)
        self.assertIn('$("auto-enabled").checked', js)
        self.assertIn('keys.push("autoStep", "autoAction")', js)
        self.assertIn("E.grossMarkPnlCents(position, decimal(markInput.value))", js)
        self.assertIn("function validatePaperBackup(backup)", js)
        self.assertIn("E.validateProspectiveCapture(payload)", js)
        self.assertIn("E.validateProspectiveScore(payload, prospectiveCapture)", js)
        self.assertIn("function renderProspective()", js)
        self.assertIn("exactBackupKeys(restored.config", js)
        self.assertIn("E.validateState(backup.state)", js)
        self.assertIn('window.confirm("Restaurar este backup PAPER?', js)
        self.assertIn("Restauração cancelada", js)
        self.assertIn("state = restored;", js)
        self.assertIn('output.dataset.valid = "false"', js)
        self.assertIn('function exactJ2Metric(raw)', js)
        self.assertIn('compareJ2Keys(previous, key)', js)
        self.assertIn('"j2-n50-ws-descriptive-watchlist-v1"', js)
        self.assertIn('watchlist = validateWatchlist(payload)', js)
        self.assertIn("same_scope_recent_50_of_50_hours", js)
        self.assertIn("scope_evidence_available", js)
        self.assertIn("scope_changed_in_window", js)
        self.assertIn("Progresso da coorte inconsistente", js)
        self.assertIn("não é falha da coleta", js)
        self.assertIn("relatório obsoleto", js)
        self.assertIn("janela privada íntegra", js)
        self.assertIn("pesquisa agregada disponível", js)
        # Manual JSON has priority even if an earlier local GET resolves later.
        self.assertEqual(js.count('if (researchOrigin === "manual") return;'), 2)
        self.assertEqual(js.count('if (feedOrigin === "manual") return;'), 2)
        self.assertIn('if (researchOrigin === "manual") return; // Import may complete during GET.', js)
        self.assertIn('if (feedOrigin === "manual") return; // Import may complete during GET.', js)
        self.assertLess((APP / "app.js").stat().st_size, 50_000)
        self.assertLess((APP / "style.css").stat().st_size, 40_000)


    @unittest.skipUnless(shutil.which("node"), "Node.js read-only prospective report validators")
    def test_j2_j3_prospective_imports_are_causal_and_zero_safe(self):
        code = r"""
const assert = require("node:assert/strict");
const E = require("./web/app/engine.js");
const end = Date.UTC(2026, 10, 15, 3, 0);
const C = {
  schema_version:"j2-ws-owner-ledger-status-v1",
  status:"owner_local_decision_captured_not_independent_attestation",
  capture_records_created:1,candidates_captured:0,decision_closed_end_ms:end,
  owner_ws_sqlite_readonly_replayed:true,local_decision_record_consistency_verified:true,
  prospective_registration_independently_verified:false,marketwide_top50_verified:false,
  financial_backtest_approved:false,approved_for_signals:false,
  live_trading_authorized:false,orders_sent:false,network_requests:0,
  database_mutation_statements:0,systemd_modified:false
};
assert.equal(E.validateProspectiveCapture(C).candidates_captured, 0);
for (const bad of [
  {...C, private_symbol:"BTCUSDT"}, {...C, live_trading_authorized:true},
  {...C, candidates_captured:12}, {...C, capture_records_created:0},
  {...C, decision_closed_end_ms:end+1}, {...C, orders_sent:true}
]) assert.throws(()=>E.validateProspectiveCapture(bad));
const S = {
  schema_version:"j3-ws-watchlist-forward-reference-v1",
  status:"no_observations_selected", quality:"ex_post_closed_mark_cost_assumptions_not_fills",
  horizon_bars:1,selected_observations:0,matured_observations:0,
  aligned_observations:0,contrary_observations:0,unchanged_observations:0,
  gross_reference_bps_sum:null,net_reference_after_assumed_costs_bps_sum:null,
  same_side_btc_excess_reference_bps_sum:null,assumed_total_cost_quote_units:null,
  funding_events_hypothetical:0,
  prospective_registration_verified:false,intrabar_path_verified:false,
  venue_fees_verified:false,funding_schedule_verified:false,
  out_of_sample_results_validated:false,financial_backtest_approved:false,
  marketwide_top50_verified:false,approved_for_signals:false,
  live_trading_authorized:false,orders_sent:false,network_requests:0,
  database_accessed:true,database_mutation_statements:0,systemd_modified:false,
  owner_local_decision_file_verified:true,decision_closed_end_ms:end,
  future_closed_end_ms:end+3600000,owner_ws_sqlite_readonly_replayed:true,
  prospective_registration_independently_verified:false
};
assert.equal(E.validateProspectiveScore(S,C).status,"no_observations_selected");
for (const bad of [
  {...S, future_closed_end_ms:end+2*3600000},
  {...S, gross_reference_bps_sum:"12"},
  {...S, net_reference_after_assumed_costs_bps_sum:"1"},
  {...S, status:"ex_post_reference_marks_scored_not_a_backtest"},
  {...S, selected_observations:1},
  {...S, private_tick:"BTCUSDT"},
  {...S, prospective_registration_independently_verified:true},
  {...S, out_of_sample_results_validated:true},
]) assert.throws(()=>E.validateProspectiveScore(bad,C));
const one = {...C,candidates_captured:2};
const score = {...S,status:"ex_post_reference_marks_scored_not_a_backtest",
  selected_observations:2,matured_observations:2,
  aligned_observations:1,contrary_observations:1,
  gross_reference_bps_sum:"23.25",
  net_reference_after_assumed_costs_bps_sum:"-0.5",
  same_side_btc_excess_reference_bps_sum:"12.0",
  assumed_total_cost_quote_units:"0.20"};
assert.equal(E.validateProspectiveScore(score,one).net_reference_after_assumed_costs_bps_sum,"-0.5");
assert.throws(()=>E.validateProspectiveScore({...score,net_reference_after_assumed_costs_bps_sum:"NaN"},one));
assert.throws(()=>E.validateProspectiveScore({...score,matured_observations:1},one));
assert.throws(()=>E.validateProspectiveScore(score,{...one,decision_closed_end_ms:end-3600000}));
console.log("J2_J3_PROSPECTIVE_UI_CONTRACT_PASS");
"""
        result = subprocess.run(
            [shutil.which("node"), "-e", code],
            cwd=ROOT, text=True, capture_output=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("J2_J3_PROSPECTIVE_UI_CONTRACT_PASS", result.stdout)


    @unittest.skipUnless(shutil.which("node"), "Node.js PAPER adverse scenarios")
    def test_j4_j5_adverse_shocks_respect_partial_leverage_and_cents(self):
        js = r"""
const assert = require("node:assert/strict");
const E = require("./web/app/engine.js");
const s = E.emptyState();
const a = E.openPosition(s,{symbol:"BTCUSDT",side:"LONG",entry:"100",margin:"3",leverage:50,runner:"0"});
const b = E.openPosition(s,{symbol:"ETHUSDT",side:"SHORT",entry:"100",margin:"2",leverage:50,runner:"0"});
assert.equal(E.adversePaperShockLossCents(a,100),150n);
assert.equal(E.adversePaperShockLossCents(a,200),300n);
assert.equal(E.adversePaperShockLossCents(b,200),200n);
assert.equal(E.adversePaperShockLossCents(a,200)+E.adversePaperShockLossCents(b,200),500n);
E.partialExit(a,{basis:"REMAINING_BALANCE",percent:"50"});
assert.equal(E.adversePaperShockLossCents(a,200),150n);
s.config.leverage=1;
assert.equal(E.adversePaperShockLossCents(a,200),150n);
assert.equal(E.adversePaperShockLossCents(b,200),200n);
const tiny=E.openPosition(s,{symbol:"SOLUSDT",side:"SHORT",entry:"100",margin:"0.01",leverage:1,runner:"0"});
assert.equal(E.adversePaperShockLossCents(tiny,1),1n); // ceiling of subcent
for (const shock of [0,-1,10001,1.1,"200",NaN]) {
 assert.throws(()=>E.adversePaperShockLossCents(a,shock));
}
assert.throws(()=>E.adversePaperShockLossCents({...a,remainingUnits:"0"},200));
E.closeRunner(a);
assert.throws(()=>E.adversePaperShockLossCents(a,200));
assert.equal(E.validateState(s).positions.length,3);
assert.equal(E.emptyState().positions.length,0);
console.log("J4_J5_PAPER_ADVERSE_STRESS_PASS");
"""
        result = subprocess.run([shutil.which("node"), "-e", js],
                                cwd=ROOT, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("J4_J5_PAPER_ADVERSE_STRESS_PASS", result.stdout)

    @unittest.skipUnless(shutil.which("node"), "Node.js PAPER mark-to-margin risk projection")
    def test_j4_margin_impact_is_leverage_at_open_and_never_liquidation(self):
        js = r"""
const assert = require("node:assert/strict");
const E = require("./web/app/engine.js");
const state = E.emptyState();
const a = E.openPosition(state, {
  symbol:"BTCUSDT",side:"LONG",entry:"100",margin:"3",leverage:50,runner:"6"
});
assert.equal(E.grossHypotheticalMarginImpactBps(a,"100"),0n);
assert.equal(E.grossHypotheticalMarginImpactBps(a,"98"),-10000n);
assert.equal(E.grossHypotheticalMarginImpactBps(a,"97"),-15000n);
assert.equal(E.grossHypotheticalMarginImpactBps(a,"101"),5000n);
E.partialExit(a,{basis:"REMAINING_BALANCE",percent:"50"});
assert.equal(E.grossHypotheticalMarginImpactBps(a,"98"),-5000n);
assert.equal(E.grossHypotheticalMarginImpactBps(a,"96"),-10000n);
const b = E.openPosition(state,{
  symbol:"ETHUSDT",side:"SHORT",entry:"100",margin:"2",leverage:20,runner:"0"
});
assert.equal(E.grossHypotheticalMarginImpactBps(b,"102"),-4000n);
assert.equal(E.grossHypotheticalMarginImpactBps(b,"98"),4000n);
state.config.leverage = 1;
assert.equal(E.grossHypotheticalMarginImpactBps(a,"98"),-5000n);
assert.equal(E.grossHypotheticalMarginImpactBps(b,"102"),-4000n);
assert.throws(()=>E.grossHypotheticalMarginImpactBps(a,"NaN"));
assert.throws(()=>E.grossHypotheticalMarginImpactBps(a,"0"));
assert.throws(()=>E.grossHypotheticalMarginImpactBps(a,"-1"));
assert.throws(()=>E.grossHypotheticalMarginImpactBps({...a,leverageAtOpen:0},"99"));
E.closeRunner(a);
assert.throws(()=>E.grossHypotheticalMarginImpactBps(a,"99"));
assert.equal(E.validateState(state).positions.length,2);
console.log("J4_PAPER_MARGIN_IMPACT_PASS");
"""
        result = subprocess.run([shutil.which("node"), "-e", js],
                                cwd=ROOT, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("J4_PAPER_MARGIN_IMPACT_PASS", result.stdout)

    @unittest.skipUnless(shutil.which("node"), "optional Node.js offline PAPER arithmetic")
    def test_bigint_paper_partial_and_fixed_leverage_after_settings_change(self):
        script=r"""
const assert = require("node:assert/strict");
const E = require("./web/app/engine.js");
const s = E.emptyState();
const a = E.openPosition(s, {
  symbol:"BTCUSDT",side:"LONG", entry:"100",
  margin:"3", leverage:50, runner:"6",
}, "2026-11-13T18:00:00.000Z");
assert.equal(a.initialUnits,"150000000");
assert.equal(E.grossEntryExposureCents(a),15000n);
assert.equal(E.grossMarkPnlCents(a,"100"),0n);
assert.equal(E.grossMarkPnlCents(a,"101"),150n);
assert.equal(E.grossMarkPnlCents(a,"99"),-150n);
assert.throws(()=>E.grossMarkPnlCents(a,"NaN"),/Preço|Mark/);
for (const [p,quantity] of [["50",75000000n],["60",45000000n],["70",21000000n]]) {
  assert.equal(E.partialExit(a,{basis:"REMAINING_BALANCE",percent:p}),quantity);
  assert.deepEqual(E.validateState(JSON.parse(JSON.stringify(s))),s);
}
assert.equal(a.remainingUnits,"9000000");
assert.equal(a.leverageAtOpen,50);
assert.equal(E.format(a.remainingUnits,8),"0,09");
assert.equal(E.grossEntryExposureCents(a),900n);
assert.equal(E.grossMarkPnlCents(a,"101"),9n);
assert.throws(()=>E.partialExit(a,{basis:"REMAINING_BALANCE",percent:"1"}),/runner/);
s.config.leverage=20;
const b=E.openPosition(s,{
  symbol:"ETHUSDT",side:"SHORT",entry:"100",
  margin:"2",leverage:s.config.leverage,runner:"0"
},"2026-11-13T18:01:00.000Z");
assert.equal(a.leverageAtOpen,50);
assert.equal(b.leverageAtOpen,20);
assert.equal(E.grossMarkPnlCents(b,"99"),40n);
E.closeRunner(a);
assert.equal(a.remainingUnits,"0");
assert.equal(a.status,"CLOSED");
assert.equal(E.validateState(JSON.parse(JSON.stringify(s))).positions.length,2);
s.config.paused = true;
assert.throws(()=>E.openPosition(s,{
  symbol:"XRPUSDT",side:"LONG",entry:"1",
  margin:"1",leverage:50,runner:"0"
}),/Trava local/);
s.config.paused = false;
assert.throws(()=>E.openPosition(s,{
  symbol:"BTCUSDT",side:"LONG",entry:"0",
  margin:"3",leverage:50,runner:"6"
}),/Preço/);
const c=E.openPosition(s,{
  symbol:"SOLUSDT",side:"LONG",entry:"100",
  margin:"1",leverage:10,runner:"0"
});
E.partialExit(c,{basis:"INITIAL_POSITION",percent:"100"});
assert.equal(c.status,"CLOSED");
assert.equal(c.remainingUnits,"0");
assert.equal(E.validateState(JSON.parse(JSON.stringify(s))).positions.length,3);
const corrupted=JSON.parse(JSON.stringify(s));
corrupted.positions[0].remainingUnits="1";
assert.throws(()=>E.validateState(corrupted),/não conservado|inconsistente/);
console.log("J5_MVP1_BIGINT_PAPER_PASS");
"""
        result = subprocess.run(
            [shutil.which("node"), "-e", script],
            cwd=ROOT, text=True, capture_output=True, timeout=15,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("J5_MVP1_BIGINT_PAPER_PASS", result.stdout)


    @unittest.skipUnless(shutil.which("node"), "Node.js offline PAPER automatic exits")
    def test_j4_j5_auto_targets_stop_replay_and_legacy_backup(self):
        script=r"""
const assert = require("node:assert/strict");
const E = require("./web/app/engine.js");
const s = E.emptyState();
const cfg = {target1:"1",target2:"2",stop:"1",partial:"50"};
const input = {symbol:"BTCUSDT",side:"LONG",entry:"100",margin:"3",
               leverage:50,runner:"6",auto:cfg};
const a = E.openPosition(s, input, "2026-11-15T11:00:00.000Z");
assert.equal(a.auto.lastStep,0);
assert.equal(a.auto.hits,0);
assert.equal(a.leverageAtOpen,50);
assert.equal(E.applyAutoPaperStep(a,"100",1).action,"NO_TRIGGER");
assert.equal(a.events.length,0);
assert.equal(E.applyAutoPaperStep(a,"101",2).action,"TARGET_1");
assert.equal(a.remainingUnits,"75000000");
assert.equal(a.events[0].autoStep,2);
assert.equal(a.events[0].autoAction,"TARGET_1");
assert.throws(()=>E.applyAutoPaperStep(a,"102",2),/repetido|sequência/);
assert.equal(a.remainingUnits,"75000000");
assert.throws(()=>E.applyAutoPaperStep(a,"NaN",3),/Fechamento/);
assert.equal(a.auto.lastStep,2);
assert.equal(a.remainingUnits,"75000000");
assert.equal(E.applyAutoPaperStep(a,"102",3).action,"TARGET_2");
assert.equal(a.remainingUnits,"37500000");
assert.equal(a.events[1].autoAction,"TARGET_2");
assert.equal(E.applyAutoPaperStep(a,"103",4).action,"NO_TRIGGER");
assert.equal(a.remainingUnits,"37500000");
assert.equal(E.applyAutoPaperStep(a,"99",5).action,"STOP");
assert.equal(a.remainingUnits,"0");
assert.equal(a.status,"CLOSED");
assert.equal(a.events[2].autoAction,"STOP");
assert.equal(a.events[2].autoStep,5);
assert.throws(()=>E.applyAutoPaperStep(a,"99",6),/indisponíveis|encerrado/);
assert.deepEqual(E.validateState(JSON.parse(JSON.stringify(s))),s);

const b = E.openPosition(s, {...input, symbol:"ETHUSDT",
  side:"SHORT",runner:"6"}, "2026-11-15T11:01:00.000Z");
assert.equal(E.applyAutoPaperStep(b,"99",1).action,"TARGET_1");
assert.equal(E.applyAutoPaperStep(b,"98",2).action,"TARGET_2");
assert.equal(E.applyAutoPaperStep(b,"101",3).action,"STOP");
assert.equal(b.status,"CLOSED");
assert.equal(b.events[2].autoAction,"STOP");

const third = E.openPosition(s, {...input,symbol:"SOLUSDT",
  auto:undefined}, "2026-11-15T11:02:00.000Z");
assert.equal(third.auto,undefined);
E.partialExit(third,{basis:"REMAINING_BALANCE",percent:"50"});
assert.deepEqual(E.validateState(JSON.parse(JSON.stringify(s))),s);
const count = s.positions.length;
assert.throws(()=>E.openPosition(s,{...input,symbol:"BADUSDT",
  runner:"90"}, "2026-11-15T11:04:00.000Z"),/runner/);
assert.throws(()=>E.openPosition(s,{...input,symbol:"BADUSDT",
  auto:{...cfg,target1:"3"}}, "2026-11-15T11:04:00.000Z"),/ordenados/);
assert.equal(s.positions.length,count);
const corrupted=JSON.parse(JSON.stringify(s));
corrupted.positions[0].auto.hits=1;
assert.throws(()=>E.validateState(corrupted),/Progresso automático/);
const badReplay=JSON.parse(JSON.stringify(s));
badReplay.positions[2].events[0].percentBps=60;
assert.throws(()=>E.validateState(badReplay),/replay exato/);
const duplicate=JSON.parse(JSON.stringify(s));
duplicate.positions[0].events[1].autoStep=2;
assert.throws(()=>E.validateState(duplicate),/sequência/);
const forged=JSON.parse(JSON.stringify(s));
forged.positions[2].events[0].autoStep=1;
forged.positions[2].events[0].autoAction="TARGET_1";
assert.throws(()=>E.validateState(forged),/sequência/);
console.log("J4_J5_AUTO_EXIT_BIGINT_PAPER_PASS");
"""
        result = subprocess.run(
            [shutil.which("node"), "-e", script],
            cwd=ROOT, text=True, capture_output=True, timeout=15,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("J4_J5_AUTO_EXIT_BIGINT_PAPER_PASS", result.stdout)


    @unittest.skipUnless(shutil.which("node"), "Node.js bounded PAPER scenario replay")
    def test_j5_replay_auto_marks_is_all_or_nothing_and_no_exchange(self):
        script=r"""
const assert=require("node:assert/strict");
const E=require("./web/app/engine.js");
const s=E.emptyState();
const auto={target1:"1",target2:"2",stop:"1",partial:"50"};
const p=E.openPosition(s,{symbol:"BTCUSDT",side:"LONG",entry:"100",
  margin:"3",leverage:50,runner:"6",auto});
const before=JSON.stringify(p);
assert.throws(()=>E.replayAutoPaperMarks(p,["101","102","NaN"]),/Fechamento/);
assert.throws(()=>E.replayAutoPaperMarks(p,[]),/1 a 24/);
assert.throws(()=>E.replayAutoPaperMarks(p,Array(25).fill("100")),/1 a 24/);
assert.equal(JSON.stringify(p),before);
const out=E.replayAutoPaperMarks(p,["101","102","99","98"]);
assert.deepEqual(out,{processedSteps:3,skippedAfterClose:1,
  targetEvents:2,stopTriggered:true,ordersSent:false});
assert.equal(p.status,"CLOSED");
assert.equal(p.auto.lastStep,3);
assert.equal(p.remainingUnits,"0");
assert.equal(p.events.map(x=>x.autoAction).join(","),"TARGET_1,TARGET_2,STOP");
assert.deepEqual(E.validateState(JSON.parse(JSON.stringify(s))),s);
assert.throws(()=>E.replayAutoPaperMarks(p,["100"]),/posição PAPER aberta/);
const q=E.openPosition(s,{symbol:"ETHUSDT",side:"SHORT",entry:"100",
  margin:"2",leverage:20,runner:"6",auto});
const short=E.replayAutoPaperMarks(q,["99","98","101"]);
assert.equal(short.stopTriggered,true);
assert.equal(q.status,"CLOSED");

const conflict=E.openPosition(s,{symbol:"XRPUSDT",side:"LONG",entry:"100",
  margin:"3",leverage:50,runner:"30",
  auto:{target1:"1",target2:"2",stop:"1",partial:"25"}});
E.partialExit(conflict,{basis:"REMAINING_BALANCE",percent:"50"});
const conflictBefore=JSON.stringify(conflict);
assert.throws(()=>E.replayAutoPaperMarks(conflict,["101","102"]),/runner/);
assert.equal(JSON.stringify(conflict),conflictBefore);
const manual=E.openPosition(s,{symbol:"SOLUSDT",side:"LONG",entry:"100",
  margin:"1",leverage:10,runner:"6"});
assert.throws(()=>E.replayAutoPaperMarks(manual,["101"]),/gatilhos/);
assert.deepEqual(E.validateState(JSON.parse(JSON.stringify(s))),s);
console.log("J5_PAPER_BATCH_ATOMIC_PASS");
"""
        result=subprocess.run(
            [shutil.which("node"), "-e", script],cwd=ROOT,
            text=True,capture_output=True,timeout=15,check=False,
        )
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn("J5_PAPER_BATCH_ATOMIC_PASS",result.stdout)


if __name__ == "__main__":
    unittest.main()
