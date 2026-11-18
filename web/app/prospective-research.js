/* D436 public-Bybit research is read-only and never a trading signal. */
(function (global) {
  "use strict";
  const STATUSES = new Set(["observed_long_hypothesis_not_authorized",
    "observed_short_hypothesis_not_authorized", "observed_no_hypothesis",
    "observed_data_insufficient", "observed_feed_unavailable",
    "observed_session_ended"]);
  const REQUIRED = new Set(["schema_version", "status", "evaluated_at_ms",
    "latest_closed_end_ms", "journal_digest_sha256", "closed_events_appended",
    "identical_replays", "failure_category", "source", "network_attempted",
    "last_frame_received_ms", "session_ended", "session_ended_at_ms", "data_quality",
    "approved_for_signals", "orders_sent", "risk_gate_called",
    "auto2_called", "auto4_called", "live_trading_authorized"]);
  let lastRequest = 0;
  const positive = n => Number.isSafeInteger(n) && n > 0;
  function valid(v) {
    if (!v || typeof v !== "object" || Array.isArray(v) ||
        Object.keys(v).length !== REQUIRED.size ||
        !Object.keys(v).every(key => REQUIRED.has(key)) ||
        v.schema_version !== "j2-prospective-bybit-research-d436-v2" ||
        !STATUSES.has(v.status) ||
        !["offline_protocol_replay", "public_ws_observed_unverified"].includes(v.source) ||
        v.network_attempted !== (v.source === "public_ws_observed_unverified") ||
        v.data_quality !== "bybit_public_ws_confirmed_unverified" ||
        ["approved_for_signals", "orders_sent", "risk_gate_called",
         "auto2_called", "auto4_called", "live_trading_authorized"].some(key => v[key] !== false) ||
        !positive(v.evaluated_at_ms) ||
        (v.latest_closed_end_ms !== null && (!positive(v.latest_closed_end_ms) ||
         v.latest_closed_end_ms >= v.evaluated_at_ms)) ||
        (v.journal_digest_sha256 !== null && (typeof v.journal_digest_sha256 !== "string" ||
         !/^[a-f0-9]{64}$/.test(v.journal_digest_sha256))) ||
        (v.latest_closed_end_ms !== null && v.journal_digest_sha256 === null) ||
        ![null, "gap_or_stale", "invalid_frame_or_scope",
          "session_finished", "session_abstained"].includes(v.failure_category) ||
        !Number.isSafeInteger(v.closed_events_appended) || v.closed_events_appended < 0 ||
        v.closed_events_appended > 4096 ||
        !Number.isSafeInteger(v.identical_replays) || v.identical_replays < 0 ||
        v.identical_replays > 4096 ||
        typeof v.session_ended !== "boolean" ||
        v.session_ended !== (v.status === "observed_session_ended") ||
        (v.last_frame_received_ms !== null && !positive(v.last_frame_received_ms)) ||
        (v.session_ended_at_ms !== null && !positive(v.session_ended_at_ms)) ||
        (v.session_ended && v.session_ended_at_ms === null) ||
        (!v.session_ended && (v.session_ended_at_ms !== null ||
                              v.last_frame_received_ms === null))) return false;
    if (v.session_ended && v.last_frame_received_ms !== null &&
        v.last_frame_received_ms > v.session_ended_at_ms) return false;
    if (!v.session_ended && ["observed_long_hypothesis_not_authorized",
       "observed_short_hypothesis_not_authorized", "observed_no_hypothesis"].includes(v.status) &&
        v.latest_closed_end_ms === null) return false;
    return true;
  }
  function render(v) {
    const label = global.document.getElementById("live-research-status");
    const detail = global.document.getElementById("live-research-detail");
    if (!label || !detail) return;
    if (!valid(v)) {
      label.textContent = "Indisponível";
      detail.textContent = "Dados ausentes, vencidos ou recusados. Sem supervisão ativa.";
    } else if (v.session_ended) {
      label.textContent = "Sessão encerrada";
      detail.textContent = "Sessão finita concluída. Nenhuma hipótese permanece atual; sem monitoramento contínuo.";
    } else {
      const names = {
        observed_long_hypothesis_not_authorized: "Hipótese LONG · NÃO autorizada",
        observed_short_hypothesis_not_authorized: "Hipótese SHORT · NÃO autorizada",
        observed_no_hypothesis: "Sem hipótese",
        observed_data_insufficient: "Abstenção · dados insuficientes",
        observed_feed_unavailable: "Feed indisponível"
      };
      label.textContent = names[v.status];
      detail.textContent = v.source === "offline_protocol_replay"
        ? "Replay offline; não há conexão pública. Pesquisa, nunca sinal ou ordem."
        : "Amostra pública não autenticada em sessão finita. Pesquisa, nunca sinal ou ordem.";
    }
  }
  function isLocal() {
    const loc = global.location;
    return loc && loc.protocol === "http:" &&
      (loc.hostname === "127.0.0.1" || loc.hostname === "localhost") &&
      loc.port === "8765";
  }
  async function refreshLocal() {
    if (!isLocal()) return;
    const request = ++lastRequest;
    try {
      const response = await global.fetch("/api/j2-prospective-research", {
        method: "GET", credentials: "omit", cache: "no-store", redirect: "error"
      });
      if (!response.ok || response.status !== 200 ||
          !(response.headers.get("content-type") || "").startsWith("application/json"))
        throw new Error("unavailable");
      const raw = await response.text();
      if (raw.length < 2 || raw.length > 4096) throw new Error("unavailable");
      const report = JSON.parse(raw);
      if (request === lastRequest) render(report);
    } catch (_) {
      if (request === lastRequest) render(null);
    }
  }
  global.CIAProspectiveResearch = Object.freeze({render, refreshLocal, valid});
})(globalThis);
