/* Read-only D431 rendering for the deterministic J6 PAPER lifecycle demo. */
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
  function valid(ok) { if (!ok) throw new Error("Ciclo PAPER integrado inválido"); }
  function install(raw) {
    valid(raw && raw.schema_version === "j6_full_offline_paper_lifecycle_v1" &&
      raw.mode === "offline_paper" && Array.isArray(raw.stages) &&
      raw.stages.length === STAGES.length && raw.stages.every((v, i) => v === STAGES[i]) &&
      raw.orders_sent === false && raw.live_trading_authorized === false &&
      raw.approved_for_live_use === false && raw.market_data_real === false &&
      raw.financial_pnl_available === false && raw.restart_duplicate_orders === 0 &&
      raw.synthetic_open_fill_injected_explicitly === true &&
      raw.synthetic_partial_fills_injected_explicitly === 3 &&
      raw.synthetic_runner_fill_injected_explicitly === true);
    const box = document.getElementById("integrated-cycle");
    if (!box) return;
    box.hidden = false;
    box.replaceChildren();
    const title = document.createElement("strong");
    title.textContent = "Ciclo integrado reproduzido — somente simulação";
    const detail = document.createElement("p");
    detail.textContent = "Abertura: " + raw.opening_units + " unidades fictícias · parciais: " +
      raw.partial_exit_units + " · runner encerrado: " + raw.runner_exit_units +
      " · reinício sem duplicação: sim. PnL financeiro: indisponível/não validado.";
    const failure = document.createElement("p");
    failure.textContent = "Falha simulada: novas aberturas são bloqueadas quando a proteção PAPER não pode ser verificada; nenhuma posição é presumida protegida.";
    box.append(title, detail, failure);
  }
  global.CIAIntegratedPaperCycle = Object.freeze({ install });
})(typeof globalThis !== "undefined" ? globalThis : this);
