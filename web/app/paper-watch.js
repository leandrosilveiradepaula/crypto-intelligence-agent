/* D427: local-only terminal PAPER lease status; NOT a live stop or account. */
(function (global) {
  "use strict";
  const SCHEMA = "j5-paper-finite-lease-watch-d427-v1";
  const MAX_AGE_MS = 180000;
  const FIELDS = Object.freeze([
    "schema_version", "status", "sampled_at_ms", "source",
    "configured_position_routes", "quote_events_forwarded",
    "quote_events_deferred", "hypothetical_reservations_observed",
    "reconciliation_events_observed", "subscription_acks",
    "owner_cohort_unchanged", "market_lease_completed",
    "finite_lease_ended", "full_position_coverage_verified",
    "continuous_supervision_verified", "native_stop_verified",
    "real_fills_verified", "live_trading_authorized",
    "orders_sent", "approved_for_signals"
  ]);
  const FALSE_FLAGS = [
    "full_position_coverage_verified", "continuous_supervision_verified",
    "native_stop_verified", "real_fills_verified", "live_trading_authorized",
    "orders_sent", "approved_for_signals"
  ];
  const COUNTS = [
    "configured_position_routes", "quote_events_forwarded",
    "quote_events_deferred", "hypothetical_reservations_observed",
    "reconciliation_events_observed", "subscription_acks"
  ];
  let current = null;
  let refreshing = false;
  function valid(condition) {
    if (!condition) throw new Error("Relatório PAPER local inválido");
  }
  function validateReport(r, now = Date.now()) {
    valid(r && typeof r === "object" && !Array.isArray(r));
    valid(Object.keys(r).length === FIELDS.length &&
      FIELDS.every(key => Object.prototype.hasOwnProperty.call(r, key)));
    valid(r.schema_version === SCHEMA && r.source === "real_public_websocket");
    valid(r.status === "finite_paper_lease_ended" ||
      r.status === "finite_paper_lease_failed_closed");
    valid(Number.isSafeInteger(r.sampled_at_ms) &&
      r.sampled_at_ms >= 1600000000000 && r.sampled_at_ms <= 4102444800000 &&
      Number.isSafeInteger(now) && now - r.sampled_at_ms >= -5000 &&
      now - r.sampled_at_ms <= MAX_AGE_MS);
    valid(r.finite_lease_ended === true &&
      typeof r.market_lease_completed === "boolean" &&
      typeof r.owner_cohort_unchanged === "boolean" &&
      FALSE_FLAGS.every(key => r[key] === false));
    valid(COUNTS.every((key, i) => Number.isSafeInteger(r[key]) &&
      r[key] >= 0 && r[key] <= (i === 0 ? 50 : i === 5 ? 2 : 100000)));
    valid(r.hypothetical_reservations_observed +
      r.reconciliation_events_observed <= r.quote_events_forwarded);
    valid(r.quote_events_forwarded === 0 || r.subscription_acks > 0);
    valid(!r.market_lease_completed || r.subscription_acks > 0);
    if (r.status === "finite_paper_lease_failed_closed") {
      valid(COUNTS.every(key => r[key] === 0) &&
        r.market_lease_completed === false &&
        r.owner_cohort_unchanged === false);
    }
    return Object.freeze({...r});
  }
  function node(tag, content) {
    const element = document.createElement(tag);
    element.textContent = String(content);
    return element;
  }
  function render() {
    if (typeof document === "undefined") return;
    const status = document.getElementById("paper-watch-status");
    const empty = document.getElementById("paper-watch-empty");
    const loaded = document.getElementById("paper-watch-loaded");
    const rows = document.getElementById("paper-watch-rows");
    const caption = document.getElementById("paper-watch-summary");
    if (!status || !empty || !loaded || !rows || !caption) return;
    rows.replaceChildren();
    if (!current || Date.now() - current.sampled_at_ms > MAX_AGE_MS) {
      current = null;
      status.textContent = "Sem supervisão PAPER ativa";
      empty.hidden = false;
      loaded.hidden = true;
      caption.textContent = "";
      return;
    }
    const failed = current.status === "finite_paper_lease_failed_closed";
    status.textContent = failed ?
      "Última tentativa interrompida" : "Última sessão encerrada";
    empty.hidden = true;
    loaded.hidden = false;
    const at = new Date(current.sampled_at_ms).toISOString().slice(0, 16).replace("T", " ");
    caption.textContent = "Registro de " + at +
      " UTC. Sessão finita encerrada; não existe proteção contínua ou stop nativo.";
    for (const [label, value] of [
      ["Rotas PAPER configuradas na sessão", current.configured_position_routes],
      ["Cotações encaminhadas ao motor", current.quote_events_forwarded],
      ["Eventos adiados pela validação", current.quote_events_deferred],
      ["Reservas hipotéticas criadas na sessão", current.hypothetical_reservations_observed],
      ["Eventos que exigiram reconciliação", current.reconciliation_events_observed],
      ["Assinaturas públicas confirmadas", current.subscription_acks]
    ]) {
      const cell = document.createElement("div");
      cell.className = "market-pulse-row";
      cell.append(node("span", label), node("strong", value));
      rows.append(cell);
    }
    const needs = current.reconciliation_events_observed > 0 ||
      current.hypothetical_reservations_observed > 0;
    const warning = document.getElementById("paper-watch-warning");
    if (warning) warning.textContent = failed ?
      "Falha na última observação: conferir diário PAPER e conexão. Não presumir fechamento." :
      needs ?
      "Conferir reservas e reconciliação no diário AUTO4. Eventos não são ordens únicas nem FILLs." :
      "Nenhuma nova intenção observada nesta sessão; ainda podem existir reservas anteriores.";
  }
  function installLocal(raw) {
    current = validateReport(raw);
    render();
  }
  function clearLocal() {
    current = null;
    render();
  }
  function isLocal() {
    const loc = global.location;
    return Boolean(loc && loc.protocol === "http:" && loc.port === "8765" &&
      (loc.hostname === "127.0.0.1" || loc.hostname === "localhost"));
  }
  async function refreshLocal() {
    if (!isLocal() || refreshing) return;
    refreshing = true;
    try {
      const response = await global.fetch("/api/paper-watch", {
        method: "GET", credentials: "omit", cache: "no-store",
        redirect: "error"
      });
      if (!response.ok || response.status !== 200 ||
          !(response.headers.get("content-type") || "").startsWith("application/json")) {
        throw new Error("Supervisor PAPER indisponível");
      }
      const raw = await response.text();
      if (raw.length < 2 || raw.length > 4096) throw new Error("Tamanho inválido");
      installLocal(JSON.parse(raw));
    } catch (_) {
      // Never preserve a last-known-good state as current supervision.
      clearLocal();
    } finally {
      refreshing = false;
    }
  }

  /* D444: progress of an owner-only worker, never evidence of an exchange stop. */
  const WORKER_KEYS = Object.freeze([
    "schema_version", "phase", "updated_at_ms", "last_good_lease_at_ms",
    "lease_attempts", "healthy_lease_count", "consecutive_lease_failures",
    "accepted_quote_events_total", "last_lease_outcome", "source_mode",
    "lease_active", "native_stop_active", "exchange_source_authenticated",
    "uninterrupted_coverage_verified", "paper_positions_automatically_filled",
    "j1_state_accessed", "orders_sent", "approved_for_live_use"
  ]);
  const WORKER_PHASES = new Set([
    "starting", "lease_started", "between_leases", "stopped_by_operator",
    "failed_closed", "stopped_after_repeated_degradation",
    "completed_finite_cycles"
  ]);
  function validateWorker(raw, now = Date.now()) {
    valid(raw && typeof raw === "object" && !Array.isArray(raw));
    valid(Object.keys(raw).length === WORKER_KEYS.length &&
      WORKER_KEYS.every(k => Object.prototype.hasOwnProperty.call(raw, k)));
    valid(raw.schema_version === "j4-btc-continuous-paper-worker-d444-v1");
    valid(WORKER_PHASES.has(raw.phase));
    valid(raw.source_mode === "public_ws_observed_unverified" ||
      raw.source_mode === "injected_offline_protocol_replay");
    valid(Number.isSafeInteger(raw.updated_at_ms) &&
      Number.isSafeInteger(now) && raw.updated_at_ms <= now &&
      now - raw.updated_at_ms <= (
        ["stopped_by_operator", "failed_closed",
         "stopped_after_repeated_degradation",
         "completed_finite_cycles"].includes(raw.phase) ? 86400000 : 120000));
    valid(raw.last_good_lease_at_ms === null ||
      (Number.isSafeInteger(raw.last_good_lease_at_ms) &&
       raw.last_good_lease_at_ms <= raw.updated_at_ms));
    valid(["lease_attempts", "healthy_lease_count", "consecutive_lease_failures",
           "accepted_quote_events_total"].every(
      k => Number.isSafeInteger(raw[k]) && raw[k] >= 0 && raw[k] <= 100000000
    ));
    valid(raw.healthy_lease_count <= raw.lease_attempts);
    valid(typeof raw.lease_active === "boolean" &&
      raw.lease_active === (raw.phase === "lease_started"));
    valid(["native_stop_active", "exchange_source_authenticated",
           "uninterrupted_coverage_verified",
           "paper_positions_automatically_filled", "j1_state_accessed",
           "orders_sent", "approved_for_live_use"].every(k => raw[k] === false));
    return Object.freeze({...raw});
  }
  function renderWorker(raw) {
    const status = document.getElementById("paper-worker-status");
    const summary = document.getElementById("paper-worker-summary");
    const rows = document.getElementById("paper-worker-rows");
    if (!status || !summary || !rows) return;
    rows.replaceChildren();
    if (!raw) {
      status.textContent = "Indisponível";
      summary.textContent = "Nenhum estado recente do processo PAPER. Não presumir acompanhamento ativo.";
      return;
    }
    const labels = {
      starting: "Processo inicializando",
      lease_started: "Tentativa de sessão em andamento",
      between_leases: "Entre sessões / reconexão",
      stopped_by_operator: "Processo encerrado",
      failed_closed: "Processo interrompido",
      stopped_after_repeated_degradation: "Interrompido por falhas",
      completed_finite_cycles: "Ciclos de teste concluídos"
    };
    status.textContent = labels[raw.phase] || "Indisponível";
    summary.textContent = "Último estado: " +
      new Date(raw.updated_at_ms).toISOString().slice(0, 16).replace("T", " ") +
      " UTC. Uma sessão pode terminar sem proteção contínua de stop.";
    for (const [label, count] of [
      ["Ciclos iniciados", raw.lease_attempts],
      ["Sessões com cotação fresca ao encerrar", raw.healthy_lease_count],
      ["Falhas consecutivas", raw.consecutive_lease_failures],
      ["Cotações encaminhadas nos ciclos", raw.accepted_quote_events_total]
    ]) {
      const cell = document.createElement("div");
      cell.className = "market-pulse-row";
      cell.append(node("span", label), node("strong", count));
      rows.append(cell);
    }
  }
  async function refreshWorkerLocal() {
    if (!isLocal()) return;
    try {
      const response = await global.fetch("/api/paper-worker", {
        method: "GET", credentials: "omit", cache: "no-store", redirect: "error"
      });
      if (response.status !== 200 || !response.ok ||
          !(response.headers.get("content-type") || "").startsWith("application/json")) {
        throw new Error("Worker status unavailable");
      }
      const body = await response.text();
      if (body.length < 2 || body.length > 4096) throw new Error("Worker status invalid");
      renderWorker(validateWorker(JSON.parse(body)));
    } catch (_) {
      renderWorker(null);
    }
  }
  global.CIAPaperWatch = Object.freeze({
    validateReport, installLocal, clearLocal, refreshLocal,
    validateWorker, refreshWorkerLocal
  });
  if (typeof module === "object" && module && module.exports) {
    module.exports = global.CIAPaperWatch;
  }
  if (typeof document !== "undefined") {
    render();
    if (isLocal()) {
      void refreshLocal();
      void refreshWorkerLocal();
      global.setInterval(() => { void refreshLocal(); }, 30000);
      global.setInterval(() => { void refreshWorkerLocal(); }, 10000);
    }
  }
})(typeof globalThis !== "undefined" ? globalThis : this);
