/* J5/D403: public REST ticker sample viewer. No network, orders or trading. */
(function (global) {
  "use strict";
  const FIELDS = Object.freeze([
    "schema_version", "status", "source", "server_at_ms",
    "captured_at_ms", "observed_symbol_count", "quotes",
    "network_gets_in_this_capture", "crypto_only_membership_verified",
    "continuous_websocket_verified",
    "imported_report_authenticated_by_browser", "paper_positions_linked",
    "orders_sent", "approved_for_signals", "approved_for_live_use"
  ]);
  const QUOTE_FIELDS = Object.freeze([
    "symbol", "last_price", "mark_price", "bid_price", "ask_price",
    "bid_size", "ask_size", "turnover_24h"
  ]);
  const DECIMAL = /^(?:0|[1-9][0-9]{0,29})(?:\.[0-9]{1,24})?$/;
  const SCALE = 10n ** 24n;
  let current = null;
  let origin = "none"; // manual, local-auto, none; never persisted

  function insist(ok) {
    if (!ok) throw new Error("Amostra Bybit inválida ou incompleta");
  }
  function exact(value, fields) {
    insist(value !== null && typeof value === "object" &&
      !Array.isArray(value) && Object.keys(value).length === fields.length &&
      fields.every(key => Object.hasOwn(value, key)));
  }
  function unit(text, positive) {
    insist(typeof text === "string" && DECIMAL.test(text));
    const parts = text.split(".");
    const scaled = BigInt(parts[0]) * SCALE +
      BigInt(((parts[1] || "") + "0".repeat(24)).slice(0, 24));
    insist(positive ? scaled > 0n : scaled >= 0n);
    return scaled;
  }
  function validateReport(raw) {
    exact(raw, FIELDS);
    insist(raw.schema_version === "bybit-public-rest-price-pulse-d403-v1" &&
      raw.status === "rest_snapshot_display_only" &&
      raw.source === "bybit_v5_public_linear_tickers" &&
      Number.isSafeInteger(raw.server_at_ms) &&
      Number.isSafeInteger(raw.captured_at_ms) &&
      raw.server_at_ms >= 1600000000000 &&
      raw.captured_at_ms >= raw.server_at_ms - 5000 &&
      raw.captured_at_ms - raw.server_at_ms <= 45000 &&
      raw.captured_at_ms < 4102444800000 &&
      Number.isSafeInteger(raw.observed_symbol_count) &&
      raw.observed_symbol_count >= 1 && raw.observed_symbol_count <= 50 &&
      Array.isArray(raw.quotes) &&
      raw.quotes.length === raw.observed_symbol_count &&
      raw.network_gets_in_this_capture === 1 &&
      ["crypto_only_membership_verified", "continuous_websocket_verified",
       "imported_report_authenticated_by_browser", "paper_positions_linked",
       "orders_sent", "approved_for_signals", "approved_for_live_use"]
        .every(key => raw[key] === false));
    let previous = "";
    for (const q of raw.quotes) {
      exact(q, QUOTE_FIELDS);
      insist(typeof q.symbol === "string" &&
        /^[A-Z0-9]{1,28}USDT$/.test(q.symbol) && q.symbol > previous);
      previous = q.symbol;
      unit(q.last_price, true);
      unit(q.mark_price, true);
      const bid = unit(q.bid_price, true);
      const ask = unit(q.ask_price, true);
      insist(bid <= ask);
      unit(q.bid_size, true);
      unit(q.ask_size, true);
      unit(q.turnover_24h, false);
    }
    return raw;
  }
  function item(tag, content) {
    const node = document.createElement(tag);
    node.textContent = String(content);
    return node;
  }
  function render() {
    if (typeof document === "undefined") return;
    const empty = document.getElementById("public-market-empty");
    const loaded = document.getElementById("public-market-loaded");
    const status = document.getElementById("public-market-status");
    const summary = document.getElementById("public-market-summary");
    const rows = document.getElementById("public-market-rows");
    if (!empty || !loaded || !status || !summary || !rows) return;
    empty.hidden = current !== null;
    loaded.hidden = current === null;
    if (!current) {
      status.textContent = "Sem amostra REST";
      status.dataset.tone = "blocked";
      return;
    }
    const age = Date.now() - current.captured_at_ms;
    const recent = age >= -5000 && age <= 30000;
    status.textContent = recent ? "Amostra REST recente" : "Amostra REST vencida";
    status.dataset.tone = recent ? "conditional" : "blocked";
    summary.textContent = current.observed_symbol_count +
      " contratos selecionados · UTC " +
      new Date(current.server_at_ms).toISOString().replace("T", " ").slice(0, 19) +
      " · " + (recent ? "instantâneo, não streaming" :
        "preços antigos; atualize a amostra");
    rows.replaceChildren();
    for (const quote of current.quotes) {
      const card = item("div", "");
      card.className = "market-pulse-row";
      card.setAttribute("role", "group");
      card.setAttribute("aria-label", quote.symbol + " · leitura pública REST");
      card.append(
        item("strong", quote.symbol),
        item("span", "Último: " + quote.last_price),
        item("span", "Mark: " + quote.mark_price),
        item("span", "Compra: " + quote.bid_price),
        item("span", "Venda: " + quote.ask_price)
      );
      rows.append(card);
    }
  }
  function install(raw) {
    const accepted = validateReport(raw);
    current = accepted;
    origin = "manual"; // Explicit operator import wins during this tab.
    render();
  }
  function hasManualPriority() { return origin === "manual"; }
  function installLocal(raw) {
    const accepted = validateReport(raw);
    if (hasManualPriority()) return;
    current = accepted;
    origin = "local-auto";
    render();
  }
  function clearLocal() {
    if (hasManualPriority()) return;
    current = null;
    origin = "none";
    render();
    const status = typeof document !== "undefined" &&
      document.getElementById("public-market-status");
    if (status) {
      status.textContent = "Fonte REST indisponível";
      status.dataset.tone = "blocked";
    }
  }
  async function refreshLocal() {
    const loc = global.location;
    if (!loc || loc.protocol !== "http:" || loc.port !== "8765" ||
        !["127.0.0.1", "localhost"].includes(loc.hostname) ||
        hasManualPriority()) return;
    try {
      const response = await global.fetch("/api/bybit-public-price", {
        method: "GET", credentials: "omit",
        cache: "no-store", redirect: "error"
      });
      if (!response.ok || response.status !== 200 ||
          !(response.headers.get("content-type") || "").startsWith("application/json")) {
        throw new Error("Fonte pública local indisponível");
      }
      const raw = await response.text();
      if (raw.length === 0 || raw.length >= 1048576) {
        throw new Error("Amostra REST fora do limite");
      }
      if (hasManualPriority()) return;
      installLocal(JSON.parse(raw));
    } catch (_) {
      // A failed refresh cannot leave an old automatic quote looking fresh.
      clearLocal();
    }
  }
  const api = Object.freeze({
    validateReport, install, installLocal, clearLocal, hasManualPriority,
    refreshLocal
  });
  global.CIAPublicMarket = api;
  if (typeof module === "object" && module && module.exports) {
    module.exports = api;
  }
  if (typeof document !== "undefined") {
    render();
    global.setInterval(render, 5000);
  }
})(typeof globalThis !== "undefined" ? globalThis : this);
