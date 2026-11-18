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
  global.CIAPaperWatch = Object.freeze({
    validateReport, installLocal, clearLocal, refreshLocal
  });
  if (typeof module === "object" && module && module.exports) {
    module.exports = global.CIAPaperWatch;
  }
  if (typeof document !== "undefined") {
    render();
    if (isLocal()) {
      void refreshLocal();
      global.setInterval(() => { void refreshLocal(); }, 30000);
    }
  }
})(typeof globalThis !== "undefined" ? globalThis : this);
