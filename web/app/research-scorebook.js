/* D408/J5: display only already-scored prospective research references.
   No account, recommendation, orders, market fetch, PnL or persistence. */
(function (global) {
  "use strict";
  const ROOT = Object.freeze([
    "schema_version", "status", "source", "report_records_accepted",
    "distinct_decision_hours_in_supplied_files", "horizons",
    "all_decision_windows_present_verified",
    "cost_assumptions_consistent_across_decisions_verified",
    "prospective_registration_independently_verified",
    "out_of_sample_results_validated", "strategy_profitable_verified",
    "financial_backtest_approved", "marketwide_top50_verified",
    "approved_for_signals", "approved_for_live_use", "orders_sent",
    "network_requests", "database_accessed", "database_mutation_statements"
  ]);
  const ROW = Object.freeze([
    "horizon_hours", "records", "scored_decisions", "empty_decisions",
    "matured_research_observations", "directionally_favorable",
    "directionally_contrary", "unchanged",
    "net_reference_bps_sum_under_individual_assumptions",
    "net_reference_bps_mean_per_observation"
  ]);
  const FINITE = /^-?(?:0|[1-9][0-9]{0,20})(?:\.[0-9]{1,30})?$/;
  let current = null;
  function requireValid(ok) {
    if (!ok) throw new Error("Resumo prospectivo J3 inválido ou não autorizado");
  }
  function exact(raw, keys) {
    requireValid(raw !== null && typeof raw === "object" && !Array.isArray(raw) &&
      Object.keys(raw).length === keys.length &&
      keys.every(k => Object.hasOwn(raw, k)));
  }
  function bounded(n, max) {
    return Number.isSafeInteger(n) && n >= 0 && n <= max;
  }
  function validateReport(raw) {
    exact(raw, ROOT);
    requireValid(raw.schema_version === "j3-ws-prospective-evidence-summary-d408-v1" &&
      raw.status === "descriptive_forward_research_not_strategy_validation" &&
      raw.source === "imported_owner_report_contract_only_not_independently_attested" &&
      bounded(raw.report_records_accepted, 256) &&
      raw.report_records_accepted > 0 &&
      bounded(raw.distinct_decision_hours_in_supplied_files, 256) &&
      raw.distinct_decision_hours_in_supplied_files > 0 &&
      raw.distinct_decision_hours_in_supplied_files <= raw.report_records_accepted &&
      Array.isArray(raw.horizons) && raw.horizons.length === 3 &&
      ["all_decision_windows_present_verified",
       "cost_assumptions_consistent_across_decisions_verified",
       "prospective_registration_independently_verified",
       "out_of_sample_results_validated", "strategy_profitable_verified",
       "financial_backtest_approved", "marketwide_top50_verified",
       "approved_for_signals", "approved_for_live_use", "orders_sent",
       "database_accessed"].every(k => raw[k] === false) &&
      raw.network_requests === 0 &&
      raw.database_mutation_statements === 0);
    let totalRecords = 0;
    for (let i = 0; i < raw.horizons.length; i++) {
      const row = raw.horizons[i];
      exact(row, ROW);
      requireValid(row.horizon_hours === [1, 4, 8][i] &&
        bounded(row.records, 256) &&
        bounded(row.scored_decisions, 256) &&
        bounded(row.empty_decisions, 256) &&
        row.records === row.scored_decisions + row.empty_decisions &&
        bounded(row.matured_research_observations, 2560) &&
        bounded(row.directionally_favorable, 2560) &&
        bounded(row.directionally_contrary, 2560) &&
        bounded(row.unchanged, 2560) &&
        row.directionally_favorable + row.directionally_contrary +
          row.unchanged === row.matured_research_observations &&
        (row.scored_decisions > 0) ===
          (row.matured_research_observations > 0));
      const values = [
        row.net_reference_bps_sum_under_individual_assumptions,
        row.net_reference_bps_mean_per_observation
      ];
      requireValid(values.every(v =>
        row.matured_research_observations === 0 ?
          v === null : typeof v === "string" && FINITE.test(v)));
      totalRecords += row.records;
    }
    requireValid(totalRecords === raw.report_records_accepted);
    return raw;
  }
  function span(tag, text, classname) {
    const node = document.createElement(tag);
    node.textContent = String(text);
    if (classname) node.className = classname;
    return node;
  }
  function render() {
    if (typeof document === "undefined") return;
    const empty = document.getElementById("research-scorebook-empty");
    const loaded = document.getElementById("research-scorebook-loaded");
    const status = document.getElementById("research-scorebook-status");
    const rows = document.getElementById("research-scorebook-rows");
    const summary = document.getElementById("research-scorebook-summary");
    if (!empty || !loaded || !status || !rows || !summary) return;
    empty.hidden = Boolean(current);
    loaded.hidden = !current;
    rows.replaceChildren();
    if (!current) {
      status.textContent = "Sem histórico consolidado";
      return;
    }
    status.textContent = "Pesquisa prospectiva · não validada";
    summary.textContent = current.distinct_decision_hours_in_supplied_files +
      " horários fornecidos · " + current.report_records_accepted +
      " avaliações de referência; não comprova todas as horas";
    for (const row of current.horizons) {
      const card = span("article", "", "market-pulse-row");
      card.append(span("strong", "Horizonte " + row.horizon_hours + "h"),
        span("span", "Decisões com observações: " + row.scored_decisions +
          " · sem candidatos: " + row.empty_decisions),
        span("span", "Observações maduras: " + row.matured_research_observations),
        span("span", "Favoráveis: " + row.directionally_favorable +
          " · contrárias: " + row.directionally_contrary +
          " · neutras: " + row.unchanged),
        span("span", row.net_reference_bps_mean_per_observation === null ?
          "Sem referência líquida para este horizonte" :
          "Média referencial: " +
          row.net_reference_bps_mean_per_observation +
          " bps/observação, após custos hipotéticos não comparáveis"));
      rows.append(card);
    }
  }
  function install(raw) {
    const validated = validateReport(raw);
    current = validated;
    render();
  }
  global.CIAResearchEvidence = Object.freeze({validateReport, install});
  if (typeof module === "object" && module && module.exports) {
    module.exports = global.CIAResearchEvidence;
  }
  if (typeof document !== "undefined") render();
})(typeof globalThis !== "undefined" ? globalThis : this);
