/* D412: local-only display for FINITE J2/J4 market/PAPER health reports.
   This never requests a live feed or interprets a file as authenticated trades. */
(function (global) {
  "use strict";
  const ROOT = [
    "schema_version", "status", "failure_category", "sessions_attempted",
    "subscriptions_sent", "subscriptions_acknowledged", "reconnects",
    "frames_seen", "ticker_frames_accepted", "preack_frames_discarded",
    "preack_frames_bootstrapped_after_ack",
    "heartbeat_pings", "heartbeat_pongs", "last_fresh_quote_count",
    "latency_0_to_100ms", "latency_101_to_1000ms",
    "latency_1001_to_5000ms", "latency_over_5000ms",
    "no_unbounded_queue", "source_authenticated",
    "marketwide_top50_verified", "order_submission_enabled", "orders_sent",
    "approved_for_live_use", "public_data_only", "no_service_installed",
    "paper_monitoring", "paper_coverage_gate", "requested_ranked_contracts",
    "requested_position_contracts", "requested_distinct_contracts",
    "unique_ranked_contracts_observed", "unique_position_contracts_observed",
    "unique_distinct_contracts_observed", "fresh_distinct_contracts_at_end",
    "finite_coverage_observed_once", "finite_coverage_fresh_at_end",
    "coverage_applies_to_final_session_only", "scope_independently_verified",
    "continuous_24x7_verified", "existing_paper_position_quote_processed",
    "unrelated_n50_silence_blocks_protective_paper_exits",
    "universe_health_sufficient_for_new_entries", "underlying_ws_status",
    "data_mode", "real_market_frames_verified",
    "position_contracts_derived_from_existing_auto4_router",
    "positions_outside_n50_subscribed", "owner_scope_read",
    "owner_scope_unchanged_after_lease", "j1_source_was_written",
    "paper_journal_mutation_possible", "paper_fills_from_tickers",
    "native_stop_verified", "risk_safety_verified", "approved_for_signals"
  ];
  const PAPER = [
    "schema_version", "status", "configured_positions", "events_seen",
    "exact_duplicates_skipped", "other_symbols_ignored", "decision_counts",
    "runner_decision_counts", "feed_authenticated",
    "marketwide_top50_verified", "native_stop_verified",
    "order_submission_enabled", "orders_sent", "approved_for_live_use"
  ];
  const GATE = [
    "mode", "quote_frames_deferred", "quote_frames_delivered_to_paper",
    "unrelated_market_frames_ignored_for_paper",
    "full_universe_required_for_existing_exits", "orders_sent",
    "approved_for_live_use"
  ];
  const COUNTS = [
    "sessions_attempted", "subscriptions_sent", "subscriptions_acknowledged",
    "reconnects", "frames_seen", "ticker_frames_accepted",
    "preack_frames_discarded", "heartbeat_pings", "heartbeat_pongs",
    "last_fresh_quote_count", "latency_0_to_100ms", "latency_101_to_1000ms",
    "latency_1001_to_5000ms", "latency_over_5000ms",
    "requested_ranked_contracts", "requested_position_contracts",
    "requested_distinct_contracts", "unique_ranked_contracts_observed",
    "unique_position_contracts_observed", "unique_distinct_contracts_observed",
    "fresh_distinct_contracts_at_end",
    "position_contracts_derived_from_existing_auto4_router",
    "positions_outside_n50_subscribed"
  ];
  let current = null;
  function valid(check) {
    if (!check) throw new Error("Diagnóstico WS/PAPER inválido ou sem origem verificável");
  }
  function exact(obj, fields) {
    valid(obj !== null && typeof obj === "object" && !Array.isArray(obj) &&
      Object.keys(obj).length === fields.length &&
      fields.every(k => Object.hasOwn(obj, k)));
  }
  function count(n, max = 5000000) {
    valid(Number.isSafeInteger(n) && n >= 0 && n <= max);
  }
  function allFalse(obj, keys) {
    for (const key of keys) valid(obj[key] === false);
  }
  function validateCounts(obj) {
    valid(obj !== null && typeof obj === "object" && !Array.isArray(obj));
    valid(Object.keys(obj).length <= 60);
    for (const [key, n] of Object.entries(obj)) {
      valid(/^[a-z][a-z0-9_]{1,100}$/.test(key));
      count(n);
    }
  }
  function validateReport(report) {
    exact(report, ROOT);
    valid(report.schema_version === "j2-j4-current-n50-paper-lease-d410-v1" &&
      ["finite_paper_lease_completed_with_fresh_scope",
       "finite_paper_lease_degraded_or_incomplete"].includes(report.status) &&
      ["lease_completed", "lease_abstained",
       "public_market_frames_not_verified"].includes(report.underlying_ws_status) &&
      ["real_public_websocket", "injected_offline_fixture"].includes(report.data_mode) &&
      (report.failure_category === null ||
       (typeof report.failure_category === "string" &&
        /^[a-z_]{1,80}$/.test(report.failure_category))));
    allFalse(report, [
      "source_authenticated", "marketwide_top50_verified",
      "order_submission_enabled", "orders_sent", "approved_for_live_use",
      "scope_independently_verified", "continuous_24x7_verified",
      "unrelated_n50_silence_blocks_protective_paper_exits",
      "universe_health_sufficient_for_new_entries",
      "j1_source_was_written", "paper_fills_from_tickers",
      "native_stop_verified", "risk_safety_verified", "approved_for_signals"
    ]);
    valid(report.no_unbounded_queue === true &&
      report.public_data_only === true && report.no_service_installed === true &&
      report.coverage_applies_to_final_session_only === true &&
      report.owner_scope_read === true &&
      report.paper_journal_mutation_possible === true);
    for (const key of [
      "finite_coverage_observed_once", "finite_coverage_fresh_at_end",
      "existing_paper_position_quote_processed", "owner_scope_unchanged_after_lease",
      "real_market_frames_verified"
    ]) valid(typeof report[key] === "boolean");
    for (const key of COUNTS) count(report[key]);
    valid(report.requested_ranked_contracts === 50 &&
      report.requested_distinct_contracts >= 50 &&
      report.requested_distinct_contracts <= 100 &&
      report.requested_position_contracts ===
        report.positions_outside_n50_subscribed &&
      report.position_contracts_derived_from_existing_auto4_router >= 1 &&
      report.position_contracts_derived_from_existing_auto4_router <= 100 &&
      report.positions_outside_n50_subscribed <=
        report.position_contracts_derived_from_existing_auto4_router &&
      report.requested_distinct_contracts ===
        50 + report.positions_outside_n50_subscribed &&
      report.unique_ranked_contracts_observed <= 50 &&
      report.unique_position_contracts_observed <=
        report.requested_position_contracts &&
      report.unique_distinct_contracts_observed <=
        report.requested_distinct_contracts &&
      report.fresh_distinct_contracts_at_end <=
        report.unique_distinct_contracts_observed &&
      report.ticker_frames_accepted <= report.frames_seen &&
      report.subscriptions_acknowledged <= report.subscriptions_sent &&
      report.sessions_attempted >= report.subscriptions_acknowledged &&
      report.reconnects <= report.sessions_attempted);
    if (report.finite_coverage_observed_once) {
      valid(report.unique_distinct_contracts_observed ===
        report.requested_distinct_contracts);
    }
    if (report.finite_coverage_fresh_at_end) {
      valid(report.finite_coverage_observed_once &&
        report.fresh_distinct_contracts_at_end ===
          report.requested_distinct_contracts);
    }
    if (report.status === "finite_paper_lease_completed_with_fresh_scope") {
      valid(report.finite_coverage_fresh_at_end &&
        report.owner_scope_unchanged_after_lease &&
        report.underlying_ws_status === "lease_completed");
    }
    if (report.real_market_frames_verified) {
      valid(report.data_mode === "real_public_websocket" &&
        report.subscriptions_acknowledged > 0 &&
        report.ticker_frames_accepted > 0);
    }
    if (report.data_mode === "injected_offline_fixture") {
      valid(report.real_market_frames_verified === false);
    }
    exact(report.paper_monitoring, PAPER);
    const paper = report.paper_monitoring;
    valid(paper.schema_version === "paper-intrahour-quote-router-d391-v1" &&
      paper.status === "offline_paper_only");
    allFalse(paper, ["feed_authenticated", "marketwide_top50_verified",
      "native_stop_verified", "order_submission_enabled", "orders_sent",
      "approved_for_live_use"]);
    for (const key of ["configured_positions", "events_seen",
                      "exact_duplicates_skipped", "other_symbols_ignored"]) {
      count(paper[key]);
    }
    valid(paper.configured_positions ===
      report.position_contracts_derived_from_existing_auto4_router);
    validateCounts(paper.decision_counts);
    validateCounts(paper.runner_decision_counts);
    exact(report.paper_coverage_gate, GATE);
    const gate = report.paper_coverage_gate;
    valid(gate.mode === "fresh_held_position_quote_independent_of_n50");
    allFalse(gate, [
      "full_universe_required_for_existing_exits", "orders_sent",
      "approved_for_live_use"
    ]);
    count(gate.quote_frames_deferred);
    count(gate.quote_frames_delivered_to_paper);
    count(gate.unrelated_market_frames_ignored_for_paper);
    valid(gate.quote_frames_delivered_to_paper <= paper.events_seen &&
      gate.quote_frames_deferred + gate.quote_frames_delivered_to_paper +
        gate.unrelated_market_frames_ignored_for_paper <=
        report.ticker_frames_accepted &&
      report.existing_paper_position_quote_processed ===
        (gate.quote_frames_delivered_to_paper > 0));
    return report;
  }
  function span(tag, message, className) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    el.textContent = String(message);
    return el;
  }
  function render() {
    if (typeof document === "undefined") return;
    const empty = document.getElementById("paper-ws-health-empty");
    const shown = document.getElementById("paper-ws-health-loaded");
    const tag = document.getElementById("paper-ws-health-status");
    const rows = document.getElementById("paper-ws-health-rows");
    if (!empty || !shown || !tag || !rows) return;
    empty.hidden = Boolean(current);
    shown.hidden = !current;
    rows.replaceChildren();
    if (!current) {
      tag.textContent = "Sem relatório WebSocket";
      return;
    }
    const r = current;
    const isFixture = r.data_mode === "injected_offline_fixture";
    const degraded = !r.finite_coverage_fresh_at_end ||
      !r.owner_scope_unchanged_after_lease ||
      r.underlying_ws_status !== "lease_completed";
    tag.textContent = degraded ? "Amostra degradada" : "Amostra finita encerrada";
    const add = (label, value) => rows.append(span(
      "p", label + ": " + value, "muted fine"
    ));
    add("Origem do arquivo", isFixture ?
      "Dados sintéticos de testes offline" :
      "Declara sessão pública Bybit; não autenticado externamente");
    add("Saúde do universo", degraded ?
      "Degradada ou incompleta — não liberar entradas" :
      "Cobertura finita; não é sinal nem feed 24h");
    add("Cobertura observada", r.unique_distinct_contracts_observed +
      " de " + r.requested_distinct_contracts + " contratos");
    add("Preços recentes no encerramento", r.fresh_distinct_contracts_at_end +
      " de " + r.requested_distinct_contracts);
    add("Posições PAPER selecionadas", r.position_contracts_derived_from_existing_auto4_router);
    add("Posições fora do Top 50", r.positions_outside_n50_subscribed);
    add("Cotações da posição avaliadas", r.paper_coverage_gate.quote_frames_delivered_to_paper);
    add("Cotações próprias sem validade", r.paper_coverage_gate.quote_frames_deferred);
    add("Tiques de outros ativos sem encaminhamento ao PAPER",
      r.paper_coverage_gate.unrelated_market_frames_ignored_for_paper);
    add("Reservas PAPER por tipo", Object.entries(r.paper_monitoring.decision_counts)
      .filter(([key]) => key === "paper_stop_reserved" || key === "paper_target_reserved")
      .reduce((acc, [, n]) => acc + n, 0));
    add("Reconexões", r.reconnects);
    add("Estado da época J1", r.owner_scope_unchanged_after_lease ?
      "Mesma época nas duas leituras" : "Mudança ou indisponibilidade");
    add("Segurança", "Somente PAPER, sem FILL inferido, stop nativo ou ordem real");
    rows.append(span("strong",
      "Importação pontual. O navegador não está conectado ao WebSocket e não acompanha a VPS."));
  }
  function install(data) {
    current = validateReport(data);
    render();
  }
  global.CIAPaperWSHealth = Object.freeze({ validateReport, install });
  if (typeof module === "object" && module && module.exports) {
    module.exports = global.CIAPaperWSHealth;
  }
  if (typeof document !== "undefined") render();
})(typeof globalThis !== "undefined" ? globalThis : this);
