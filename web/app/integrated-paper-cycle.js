/* D431: strict read-only renderer for one deterministic J6 fixture (not live monitoring). */
(function (global) {
  "use strict";
  const STAGES = [
    "j2_risk_open_intent_reserved_without_fill",
    "explicit_fixture_open_fill_crosschecked_on_restart",
    "three_explicit_fixture_partial_fills",
    "runner2_hypothetical_trigger",
    "runner_reduce_only_pending_recovered_without_fill",
    "explicit_fixture_runner_fill_and_pre8_audit"
  ];
  const FIELDS = [
    "schema_version", "mode", "stages", "interruption_checks",
    "stop_outage_research", "strategy_open_intent_count",
    "synthetic_open_fill_injected_explicitly", "synthetic_partial_fills_injected_explicitly",
    "synthetic_runner_fill_injected_explicitly", "opening_units", "partial_exit_units",
    "runner_exit_units", "confirmed_remaining_units", "restart_duplicate_orders",
    "crosschecked_auto2_auto4_opening", "portfolio_positions_observed",
    "market_data_real", "orders_sent", "native_stop_verified",
    "live_trading_authorized", "approved_for_live_use", "financial_pnl_available",
    "network_requests", "persistent_files_retained"
  ].sort();
  function valid(ok) { if (!ok) throw new Error("Ciclo PAPER integrado inválido"); }
  function install(raw) {
    const box = document.getElementById("integrated-cycle");
    if (box) { box.hidden = true; box.replaceChildren(); }
    valid(raw && typeof raw === "object" && !Array.isArray(raw) &&
      Object.keys(raw).sort().join("|") === FIELDS.join("|") &&
      raw.schema_version === "j6_full_offline_paper_lifecycle_v1" &&
      raw.mode === "offline_paper" && Array.isArray(raw.stages) &&
      raw.stages.length === STAGES.length && raw.stages.every((v, i) => v === STAGES[i]) &&
      raw.orders_sent === false && raw.live_trading_authorized === false &&
      raw.approved_for_live_use === false && raw.market_data_real === false &&
      raw.financial_pnl_available === false && raw.native_stop_verified === false &&
      raw.network_requests === 0 && raw.persistent_files_retained === false &&
      raw.restart_duplicate_orders === 0 && raw.strategy_open_intent_count === 1 &&
      raw.portfolio_positions_observed === 1 &&
      raw.crosschecked_auto2_auto4_opening === true &&
      raw.synthetic_open_fill_injected_explicitly === true &&
      raw.synthetic_partial_fills_injected_explicitly === 3 &&
      raw.synthetic_runner_fill_injected_explicitly === true &&
      raw.opening_units === "2" && raw.partial_exit_units === "1.88" &&
      raw.runner_exit_units === "0.12" && raw.confirmed_remaining_units === "0" &&
      Array.isArray(raw.interruption_checks) && raw.interruption_checks.length > 0 &&
      raw.interruption_checks.some(x => x && x.health_new_open_allowed_paper_only === false) &&
      raw.stop_outage_research && raw.stop_outage_research.hypothetical_only === true &&
      raw.stop_outage_research.worse_than_assumed_stop === true);
    if (!box) return;
    const title = document.createElement("strong");
    title.textContent = "Ciclo integrado reproduzido — somente simulação";
    const detail = document.createElement("p");
    detail.textContent = "Abertura: " + raw.opening_units + " unidades fictícias · parciais: " +
      raw.partial_exit_units + " · runner encerrado: " + raw.runner_exit_units +
      " · reinício sem duplicação: sim. PnL financeiro: indisponível/não validado.";
    const failure = document.createElement("p");
    failure.textContent = "Falha simulada: novas aberturas são bloqueadas quando a proteção PAPER não pode ser verificada; nenhuma posição é presumida protegida.";
    box.append(title, detail, failure);
    box.hidden = false;
  }
  function localPanel() {
    const loc = global.location;
    return Boolean(loc && loc.protocol === "http:" && loc.port === "8765" &&
      (loc.hostname === "127.0.0.1" || loc.hostname === "localhost"));
  }
  async function refreshLocal() {
    if (!localPanel()) return;
    try {
      const response = await global.fetch("/api/integrated-paper-cycle", {
        method: "GET", credentials: "omit", cache: "no-store", redirect: "error"
      });
      if (!response.ok || !(response.headers.get("content-type") || "").startsWith("application/json")) throw new Error();
      const raw = await response.text();
      if (raw.length < 2 || raw.length > 32768) throw new Error();
      install(JSON.parse(raw));
    } catch (_) { /* Absence is not current PAPER supervision. */ }
  }
  global.CIAIntegratedPaperCycle = Object.freeze({ install, refreshLocal });
  if (typeof document !== "undefined" && localPanel()) {
    void refreshLocal();
    global.setInterval(() => { void refreshLocal(); }, 30000);
  }
})(typeof globalThis !== "undefined" ? globalThis : this);
