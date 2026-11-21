/* D407: read-only visualizer of EXISTING AUTO4 PAPER position snapshots.
   Independent of the browser's local lab. No network, order or persistence. */
(function (global) {
  "use strict";
  const ROOT = Object.freeze([
    "schema_version", "mode", "quality", "source_provenance",
    "selection", "no_cross_instrument_quantity_aggregation", "orders_sent",
    "live_trading_authorized", "approved_for_live_use",
    "financial_pnl_available", "positions"
  ]);
  const FIELDS = Object.freeze([
    "position_id", "venue_candidate", "symbol_fixture", "side",
    "checkpoint_utc", "initial_confirmed_units", "filled_exit_units",
    "reserved_unfilled_units", "confirmed_remaining_units",
    "unreserved_units", "runner_floor_units", "runner_filled_units",
    "runner_reserved_unfilled_units", "runner_unallocated_units",
    "runner_readiness", "trailing_stop_active", "native_stop_verified",
    "recovered_runner", "margin_intent_requested",
    "opening_order_cross_checked", "pending_or_unknown_orders",
    "unknown_order_count"
  ]);
  const CONDITIONAL = Object.freeze([
    "schema_version", "status", "priced_entry_units",
    "realized_exit_units", "gross_realized_reference_quote",
    "entry_fee_allocated_quote", "exit_fee_quote",
    "entry_slippage_allocated_quote", "exit_slippage_quote",
    "conditional_realized_before_funding_quote",
    "outstanding_entry_cost_quote", "leverage_at_open",
    "priced_fill_events", "funding_calendar_verified",
    "funding_settlement_unknown", "true_realized_net_pnl_available",
    "source_is_hypothetical_post_latency_bbo",
    "venue_fill_verified", "venue_fee_schedule_verified",
    "liquidation_verified", "orders_sent", "approved_for_live_use"
  ]);
  const LEGACY_PNL = Object.freeze([
    "status", "true_realized_net_pnl_available"
  ]);
  const SIGNED_DEC = /^-?(?:0|[1-9][0-9]{0,35})(?:\.[0-9]{1,30})?$/;
  const MARGIN = Object.freeze([
    "leverage_at_intent", "requested_margin_quote", "quote_currency",
    "quality", "opening_order_cross_checked",
    "actual_position_margin_verified", "venue_leverage_verified", "orders_sent"
  ]);
  const RECOVERED = Object.freeze([
    "state", "observed_tick_count", "digest_sha256",
    "hypothetical_only", "native_stop_verified", "trailing_stop_active"
  ]);
  const RUNNERS = Object.freeze({
    "NO_RESIDUAL_RUNNER_CONFIGURED": "Sem parcela residual",
    "PENDING_EXIT_RECONCILIATION": "Saída pendente: reconciliar",
    "WAITING_FOR_PARTIAL_FILLS": "Aguardando parciais confirmadas",
    "RUNNER_CONFIRMED_NOT_PROTECTED": "Runner PAPER sem stop nativo",
    "RUNNER_EXIT_PENDING_RECONCILIATION": "Runner pendente: reconciliar",
    "RUNNER_EXIT_PARTIALLY_FILLED": "Runner parcialmente preenchido",
    "RUNNER_CLOSED_PAPER_ONLY": "Runner encerrado no diário PAPER",
    "RUNNER_EXIT_CANCELLED_REMAINDER": "Saída cancelada: saldo liberado"
  });
  const DEC = /^(?:0|[1-9][0-9]{0,35})(?:\.[0-9]{1,30})?$/;
  const UNIT_SCALE = 10n ** 30n;
  let current = null;
  let source = "none"; // manual import or explicitly opt-in local owner snapshot
  let refreshing = false;

  function valid(ok) {
    if (!ok) throw new Error("Relatório de posições PAPER inválido ou incompatível");
  }
  function exact(obj, fields) {
    valid(obj !== null && typeof obj === "object" && !Array.isArray(obj)
      && Object.keys(obj).length === fields.length
      && fields.every(k => Object.hasOwn(obj, k)));
  }
  function units(raw, positive) {
    valid(typeof raw === "string" && DEC.test(raw));
    const parts = raw.split(".");
    const scaled = BigInt(parts[0]) * UNIT_SCALE +
      BigInt(((parts[1] || "") + "0".repeat(30)).slice(0, 30));
    valid(positive ? scaled > 0n : scaled >= 0n);
    return scaled;
  }
  function signedScaled(raw) {
    valid(typeof raw === "string" && SIGNED_DEC.test(raw));
    return raw.startsWith("-") ? -units(raw.slice(1), false) : units(raw, false);
  }
  function validateConditionalPnl(pnl, position, exited) {
    if (pnl.status === "legacy_paper_position_without_priced_strategy") {
      exact(pnl, LEGACY_PNL);
      valid(pnl.true_realized_net_pnl_available === false);
      return;
    }
    exact(pnl, CONDITIONAL);
    valid(pnl.schema_version === "d454-paper-conditional-priced-fills-v1"
      && ["legacy_unpriced_fill_no_pnl",
          "conditional_paper_reference_before_unverified_funding"].includes(pnl.status)
      && pnl.funding_calendar_verified === false
      && pnl.funding_settlement_unknown === true
      && pnl.true_realized_net_pnl_available === false
      && pnl.source_is_hypothetical_post_latency_bbo === true
      && pnl.venue_fill_verified === false
      && pnl.venue_fee_schedule_verified === false
      && pnl.liquidation_verified === false
      && pnl.orders_sent === false && pnl.approved_for_live_use === false
      && Number.isSafeInteger(pnl.leverage_at_open)
      && pnl.leverage_at_open >= 1 && pnl.leverage_at_open <= 200
      && Number.isSafeInteger(pnl.priced_fill_events)
      && pnl.priced_fill_events >= 0 && pnl.priced_fill_events <= 1024);
    valid(units(pnl.realized_exit_units, false) === exited);
    if (position.margin_intent_requested !== null) {
      valid(pnl.leverage_at_open === position.margin_intent_requested.leverage_at_intent);
    }
    const numbers = [
      "priced_entry_units", "gross_realized_reference_quote",
      "entry_fee_allocated_quote", "exit_fee_quote",
      "entry_slippage_allocated_quote", "exit_slippage_quote",
      "conditional_realized_before_funding_quote", "outstanding_entry_cost_quote"
    ];
    if (pnl.status === "legacy_unpriced_fill_no_pnl") {
      valid(pnl.priced_fill_events === 0
        && numbers.every(field => pnl[field] === null));
      return;
    }
    valid(pnl.priced_fill_events >= 1
      && units(pnl.priced_entry_units, true) === units(position.initial_confirmed_units, true));
    for (const field of numbers) {
      valid(typeof pnl[field] === "string" && SIGNED_DEC.test(pnl[field]));
    }
    const costs = [
      "entry_fee_allocated_quote", "exit_fee_quote",
      "entry_slippage_allocated_quote", "exit_slippage_quote"
    ].reduce((sum, field) => sum + units(pnl[field], false), 0n);
    units(pnl.outstanding_entry_cost_quote, false);
    valid(signedScaled(pnl.conditional_realized_before_funding_quote) ===
      signedScaled(pnl.gross_realized_reference_quote) - costs);
    if (exited === 0n) {
      valid(costs === 0n && signedScaled(pnl.gross_realized_reference_quote) === 0n);
    }
  }
  function validateReport(raw) {
    exact(raw, ROOT);
    valid(raw.schema_version === "paper_positions_snapshot_v1" &&
      raw.mode === "offline_paper" &&
      raw.quality === "synthetic_journal_replay_only" &&
      raw.source_provenance === "local_sqlite_digest_not_exchange_authenticated" &&
      raw.selection === "explicit_ids_same_sqlite_read_transaction" &&
      raw.no_cross_instrument_quantity_aggregation === true &&
      raw.orders_sent === false && raw.live_trading_authorized === false &&
      raw.approved_for_live_use === false && raw.financial_pnl_available === false &&
      Array.isArray(raw.positions) && raw.positions.length >= 1 &&
      raw.positions.length <= 128);
    const ids = new Set();
    for (const p of raw.positions) {
      valid(p && typeof p === "object" && !Array.isArray(p));
      const present = Object.hasOwn(p, "conditional_paper_pnl");
      exact(p, present ? [...FIELDS, "conditional_paper_pnl"] : FIELDS);
      valid(typeof p.position_id === "string" &&
        /^fixture_[A-Za-z0-9_-]{1,120}$/.test(p.position_id) &&
        !ids.has(p.position_id));
      ids.add(p.position_id);
      valid(["bybit_v5", "binance_usdm"].includes(p.venue_candidate) &&
        /^[A-Z0-9]{1,28}USDT$/.test(p.symbol_fixture) &&
        ["LONG", "SHORT"].includes(p.side) &&
        typeof p.checkpoint_utc === "string" &&
        /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(p.checkpoint_utc) &&
        Number.isFinite(Date.parse(p.checkpoint_utc)) &&
        Object.hasOwn(RUNNERS, p.runner_readiness) &&
        p.trailing_stop_active === false && p.native_stop_verified === false &&
        typeof p.opening_order_cross_checked === "boolean" &&
        Number.isSafeInteger(p.pending_or_unknown_orders) &&
        Number.isSafeInteger(p.unknown_order_count) &&
        p.pending_or_unknown_orders >= 0 &&
        p.unknown_order_count >= 0 &&
        p.unknown_order_count <= p.pending_or_unknown_orders &&
        p.pending_or_unknown_orders <= 1000);
      const initial = units(p.initial_confirmed_units, true);
      const exited = units(p.filled_exit_units, false);
      const reserved = units(p.reserved_unfilled_units, false);
      const remaining = units(p.confirmed_remaining_units, false);
      const unreserved = units(p.unreserved_units, false);
      const floor = units(p.runner_floor_units, false);
      const runnerFilled = units(p.runner_filled_units, false);
      const runnerReserved = units(p.runner_reserved_unfilled_units, false);
      const runnerFree = units(p.runner_unallocated_units, false);
      valid(exited + remaining === initial &&
        reserved + unreserved === remaining &&
        floor <= initial && runnerFilled <= exited &&
        runnerReserved <= reserved && runnerFree <= remaining);
      if (present) {
        valid(p.conditional_paper_pnl !== null &&
          typeof p.conditional_paper_pnl === "object" &&
          !Array.isArray(p.conditional_paper_pnl));
        validateConditionalPnl(p.conditional_paper_pnl, p, exited);
      }
      if (p.margin_intent_requested !== null) {
        const m = p.margin_intent_requested;
        exact(m, MARGIN);
        valid(Number.isSafeInteger(m.leverage_at_intent) &&
          m.leverage_at_intent >= 1 && m.leverage_at_intent <= 200 &&
          /^[A-Z]{2,12}$/.test(m.quote_currency) &&
          m.quality === "synthetic_requested_margin_at_intent_only" &&
          m.opening_order_cross_checked === p.opening_order_cross_checked &&
          m.actual_position_margin_verified === false &&
          m.venue_leverage_verified === false && m.orders_sent === false);
        units(m.requested_margin_quote, true);
      }
      if (p.recovered_runner !== null) {
        const x = p.recovered_runner;
        exact(x, RECOVERED);
        valid(["NOT_ACTIVATED", "TRACKING", "TRIGGERED_HYPOTHETICAL_ONLY"]
          .includes(x.state) &&
          Number.isSafeInteger(x.observed_tick_count) &&
          x.observed_tick_count >= 0 &&
          x.observed_tick_count <= 1000000 &&
          typeof x.digest_sha256 === "string" &&
          /^[a-f0-9]{64}$/.test(x.digest_sha256) &&
          x.hypothetical_only === true && x.native_stop_verified === false &&
          x.trailing_stop_active === false);
      }
    }
    return raw;
  }
  function span(tag, value, className) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    el.textContent = String(value);
    return el;
  }
  function render() {
    if (typeof document === "undefined") return;
    const empty = document.getElementById("persisted-paper-empty");
    const loaded = document.getElementById("persisted-paper-loaded");
    const status = document.getElementById("persisted-paper-status");
    const list = document.getElementById("persisted-paper-rows");
    const summary = document.getElementById("persisted-paper-summary");
    if (!empty || !loaded || !status || !list || !summary) return;
    empty.hidden = Boolean(current);
    loaded.hidden = !current;
    list.replaceChildren();
    if (!current) { status.textContent = "Sem diário PAPER"; return; }
    const blocked = current.positions.filter(p =>
      p.pending_or_unknown_orders > 0 ||
      p.runner_readiness.includes("PENDING_EXIT")).length;
    status.textContent = blocked ? "Reconciliação pendente" :
      source === "owner-local" ? "Diário PAPER local" : "Diário PAPER importado";
    summary.textContent = current.positions.length + " posições selecionadas" +
      (blocked ? " · " + blocked + " com pendências" : " · sem pendências registradas") +
      (source === "owner-local" ?
        " · leitura local recente do SQLite; sem stop nativo" :
        " · dados estáticos importados, sem monitor ao vivo");
    for (const p of current.positions) {
      const card = span("article", "", "market-pulse-row");
      card.append(span("strong", p.symbol_fixture + " · " + p.side),
        span("span", "Posição PAPER: " + p.position_id),
        span("span", "Abertura fictícia: " + p.initial_confirmed_units +
          " · parciais preenchidas: " + p.filled_exit_units),
        span("span", "Restante: " + p.confirmed_remaining_units +
          " · reservado: " + p.reserved_unfilled_units +
          " · disponível: " + p.unreserved_units),
        span("span", "Runner: " + RUNNERS[p.runner_readiness]),
        span("span", "Ordens incertas: " + p.unknown_order_count +
          " · pendentes: " + p.pending_or_unknown_orders),
        span("span", p.opening_order_cross_checked ?
          "Abertura cruzada com diário AUTO2" : "Abertura não cruzada com AUTO2"),
        span("span", "Checkpoint UTC: " + p.checkpoint_utc));
      if (p.margin_intent_requested) {
        const m = p.margin_intent_requested;
        card.append(span("span", "Margem solicitada PAPER: " +
          m.requested_margin_quote + " " + m.quote_currency +
          " · alavancagem solicitada: " + m.leverage_at_intent + "x"));
      } else {
        card.append(span("span", "Margem/alavancagem não registradas no diário"));
      }
      if (p.recovered_runner) {
        card.append(span("span", "Monitor recuperado PAPER: " +
          p.recovered_runner.state + " · " +
          p.recovered_runner.observed_tick_count + " marcas hipotéticas"));
      }
      if (Object.hasOwn(p, "conditional_paper_pnl")) {
        const pnl = p.conditional_paper_pnl;
        if (pnl.status === "conditional_paper_reference_before_unverified_funding") {
          card.append(
            span("strong", "Resultado PAPER parcial estimado: " +
              pnl.conditional_realized_before_funding_quote + " USDT"),
            span("span", "Bruto: " + pnl.gross_realized_reference_quote +
              " · taxas e slippage já estimados"),
            span("span", "Funding e liquidação não verificados · NÃO é lucro real")
          );
        } else {
          card.append(span("span",
            "Resultado financeiro indisponível: dados antigos sem preço executado"));
        }
      }
      if (p.pending_or_unknown_orders || p.unknown_order_count) {
        card.append(span("strong", "Bloqueado para novas reduções até reconciliação"));
      }
      list.append(card);
    }
  }
  function install(payload) {
    const accepted = validateReport(payload);
    current = accepted; // Manual volatile snapshot; never persisted.
    source = "manual";
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
      const response = await global.fetch("/api/owner-paper-positions", {
        method: "GET", credentials: "omit", cache: "no-store", redirect: "error"
      });
      if (response.status !== 200 || !response.ok ||
          !(response.headers.get("content-type") || "").startsWith("application/json")) {
        throw new Error("owner PAPER source not available");
      }
      const raw = await response.text();
      if (raw.length < 2 || raw.length > 96000) throw new Error("PAPER view oversized");
      const accepted = validateReport(JSON.parse(raw));
      current = accepted;
      source = "owner-local";
      render();
    } catch (_) {
      // Never leave an old owner snapshot on screen as a current one.
      // A manually imported report is independent, so preserve it.
      if (source === "owner-local") {
        current = null;
        source = "none";
        render();
      }
    } finally {
      refreshing = false;
    }
  }
  global.CIAPersistedPaper = Object.freeze({ validateReport, install, refreshLocal });
  if (typeof module === "object" && module && module.exports) {
    module.exports = global.CIAPersistedPaper;
  }
  if (typeof document !== "undefined") {
    render();
    if (isLocal()) {
      void refreshLocal();
      global.setInterval(() => { void refreshLocal(); }, 15000);
    }
  }
})(typeof globalThis !== "undefined" ? globalThis : this);
