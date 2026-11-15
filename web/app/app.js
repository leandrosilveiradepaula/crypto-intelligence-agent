/* J5/MVP1: interactive PT-BR, local-only PAPER console.
   No fetch, XMLHttpRequest, WebSocket, beacon, credentials or order endpoints. */
(function () {
  "use strict";
  const E = globalThis.CIAEngine;
  const KEY = "cia-j5-paper-v1";
  const MAX_SNAPSHOT = 1048576;
  const HOUR = 3600000;
  const $ = id => document.getElementById(id);
  let state = E.emptyState();
  let feed = null;
  let feedOrigin = "none"; // local-auto, manual, or none
  let research = null;
  let researchOrigin = "none";
  let watchlist = null; // Volatile imported J2 shortlist; never persisted or uploaded.
  let storageAvailable = true;

  function el(tag, className, content) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (content !== undefined) node.textContent = String(content);
    return node;
  }
  function set(id, text) { $(id).textContent = String(text); }
  function amount(cents) { return "US$ " + E.format(cents, 2); }
  function decimal(input) { return String(input || "").trim().replace(",", "."); }
  function warn(message, error) {
    const box = $("notice");
    box.textContent = message;
    box.dataset.tone = error ? "error" : "info";
    box.hidden = false;
  }
  function check(test, message) { if (!test) throw new Error(message); }

  function load() {
    try {
      const stored = localStorage.getItem(KEY);
      if (stored !== null) {
        check(stored.length <= 200000, "Estado local excedeu limite");
        state = E.validateState(JSON.parse(stored));
      }
    } catch (_) {
      state = E.emptyState();
      storageAvailable = false;
      warn("Armazenamento local indisponível ou inconsistente. Esta sessão funcionará sem persistência.", true);
    }
  }
  function save() {
    try {
      E.validateState(state);
      localStorage.setItem(KEY, JSON.stringify(state));
      storageAvailable = true;
    } catch (_) {
      storageAvailable = false;
      warn("Não foi possível persistir cenários neste navegador. Exporte o JSON antes de fechar a página.", true);
    }
    set("storage-status", storageAvailable ?
      "Cenários fictícios guardados apenas neste navegador. Relatórios de mercado nunca são persistidos." :
      "Armazenamento indisponível. Os cenários ficam apenas nesta sessão.");
  }
  function option(label, value) {
    const element = el("option", null, label);
    element.value = value;
    return element;
  }
  function cell(label, value) {
    const node = el("div");
    node.append(el("span", null, label), el("strong", null, value));
    return node;
  }
  function formField(label, control) {
    const wrapper = el("label", "field");
    wrapper.append(document.createTextNode(label), control);
    return wrapper;
  }
  function control(tag, value) {
    const field = document.createElement(tag);
    if (tag === "input") {
      field.type = "text";
      field.inputMode = "decimal";
      field.value = value;
      field.autocomplete = "off";
    }
    return field;
  }
  function updateSummary() {
    const opened = state.positions.filter(p => p.status === "OPEN");
    let exposure = 0n, margin = 0n;
    for (const position of opened) {
      exposure += E.grossEntryExposureCents(position);
      margin += BigInt(position.marginCents);
    }
    set("metric-open", opened.length);
    set("metric-exposure", amount(exposure));
    set("metric-margin", amount(margin));
    set("metric-n50", feed ? feed.observed_50_of_50_hours + " / 24" : "— / 24");
    set("metric-n50-label", feed ? "Relatório importado; não é D323" : "Nenhum relatório importado");
    set("paper-gate", state.config.paused ?
      "Criação PAPER bloqueada localmente" : "Novos cenários permitidos");
  }
  function updateSettings() {
    set("form-leverage", state.config.leverage + "x");
    set("form-runner", E.format(BigInt(state.config.runnerBps), 2) + "%");
    $("leverage").value = state.config.leverage;
    $("default-margin").value = E.format(state.config.marginCents, 2).replace(",", ".");
    $("runner").value = E.format(BigInt(state.config.runnerBps), 2).replace(",", ".");
    $("pause").checked = state.config.paused;
    $("open-submit").disabled = state.config.paused || state.positions.length >= 100;
    if (!$("open-form").dataset.edited) {
      $("margin").value = E.format(state.config.marginCents, 2).replace(",", ".");
    }
  }
  function positionCard(position) {
    const card = el("article", "position-card" + (position.status === "CLOSED" ? " closed" : ""));
    const heading = el("div", "position-heading");
    heading.append(
      el("strong", null, position.symbol + " · " + position.side),
      el("span", null, position.status === "OPEN" ? "ABERTA · PAPER" : "ENCERRADA · PAPER")
    );
    card.append(heading);
    const meta = el("div", "position-meta");
    [
      position.id, "Margem " + amount(position.marginCents),
      "Alavancagem " + position.leverageAtOpen + "x",
      "Entrada hipotética US$ " + E.format(position.entryPriceUnits, 8),
      "Runner mínimo " + E.format(BigInt(position.runnerBpsAtOpen), 2) + "%"
    ].forEach(item => meta.append(el("span", null, item)));
    if (position.auto) meta.append(el("span", null,
      "Auto PAPER: " + position.auto.hits + "/2 alvos · passo " +
      position.auto.lastStep));
    card.append(meta);
    const cells = el("div", "position-balances");
    cells.append(
      cell("Quantidade inicial abstrata", E.format(position.initialUnits, 8)),
      cell("Quantidade restante", E.format(position.remainingUnits, 8)),
      cell("Exposição nominal da parcela", amount(E.grossEntryExposureCents(position))),
      cell("Saídas fictícias registradas", position.events.length)
    );
    card.append(cells);
    if (position.status === "OPEN") {
      // A user-provided hypothetical mark is never fetched or persisted.
      // Reuse the exact BigInt PAPER engine, after all partial exits.
      const mark = el("section", "mark-reference");
      mark.setAttribute("aria-label", "Variação bruta PAPER de " + position.id);
      const label = el("label", "field", "Mark hipotético (US$)");
      const entryUnits = BigInt(position.entryPriceUnits);
      const markInput = control("input",
        (entryUnits / E.SCALE).toString() + "." +
        (entryUnits % E.SCALE).toString().padStart(8, "0"));
      markInput.setAttribute("aria-label",
        "Preço mark hipotético de " + position.id);
      label.append(markInput);
      const output = el("div", "mark-output");
      output.setAttribute("role", "status");
      output.setAttribute("aria-live", "polite");
      const result = el("strong");
      const disclaimer = el("small", null,
        "Variação bruta de referência sobre o saldo restante. Não inclui taxas, " +
        "funding, slippage ou liquidação. Não é preço real nem PnL executável.");
      output.append(result, disclaimer);
      const calculate = () => {
        try {
          const gross = E.grossMarkPnlCents(position, decimal(markInput.value));
          result.textContent = "PnL bruto hipotético: " + amount(gross);
          output.dataset.valid = "true";
        } catch (_) {
          // Never show an outdated favorable result for malformed input.
          result.textContent = "Mark inválido: informe preço positivo válido.";
          output.dataset.valid = "false";
        }
      };
      markInput.addEventListener("input", calculate);
      calculate();
      mark.append(label, output);
      if (position.auto) {
        const a = position.auto;
        const rules = el("div", "auto-policy");
        const percentage = bp => E.format(BigInt(bp), 2) + "%";
        rules.append(el("p", "muted fine",
          "Regras desta posição: alvo 1 +" + percentage(a.target1Bps) +
          ", alvo 2 +" + percentage(a.target2Bps) +
          ", stop -" + percentage(a.stopBps) +
          ", saída " + percentage(a.partialBps) +
          " sobre o saldo restante. Alvos: " + a.hits + "/2; passos: " +
          a.lastStep + ". O runner não é realizado pelos alvos."));
        const trigger = el("button", "secondary auto-step-button",
          "Simular próximo fechamento PAPER");
        trigger.type = "button";
        trigger.setAttribute("aria-label",
          "Aplicar gatilhos PAPER de " + position.id);
        trigger.addEventListener("click", () => {
          try {
            const tick = E.applyAutoPaperStep(position,
              decimal(markInput.value), position.auto.lastStep + 1);
            save();
            render();
            const labels = {NO_TRIGGER:"sem gatilho",
              TARGET_1:"alvo 1: parcial fictícia", TARGET_2:"alvo 2: parcial fictícia",
              STOP:"stop fictício: saldo encerrado"};
            warn("Passo PAPER " + tick.step + ": " + labels[tick.action] +
              ". Nenhuma ordem ou execução de corretora.", false);
          } catch (err) { warn(err.message, true); }
        });
        rules.append(trigger);
        const batchLabel = el("label", "field auto-batch",
          "Reproduzir de 1 a 24 fechamentos fictícios (um preço por linha)");
        const batchInput = el("textarea", "auto-batch-input");
        batchInput.rows = 3;
        batchInput.maxLength = 512;
        batchInput.placeholder = "101.00\n102.00\n99.00";
        batchInput.setAttribute("aria-label",
          "Sequência de fechamentos hipotéticos de " + position.id);
        batchLabel.append(batchInput);
        const batchButton = el("button", "secondary auto-batch-button",
          "Reproduzir cenário PAPER");
        batchButton.type = "button";
        batchButton.addEventListener("click", () => {
          try {
            const raw = batchInput.value.trim();
            check(raw.length > 0 && raw.length <= 512,
              "Informe de 1 a 24 fechamentos fictícios");
            const marks = raw.split(/\r?\n/).map(decimal);
            const report = E.replayAutoPaperMarks(position, marks);
            save();
            render();
            warn("Cenário PAPER: " + report.processedSteps + " passos, " +
              report.targetEvents + " parciais, stop " +
              (report.stopTriggered ? "sim" : "não") + ", " +
              report.skippedAfterClose + " ignorados após encerramento. " +
              "Nenhuma ordem enviada.", false);
          } catch (err) { warn("Cenário recusado: " + err.message, true); }
        });
        rules.append(batchLabel, batchButton);
        mark.append(rules);
      }
      card.append(mark);
    }
    const details = el("details");
    details.append(el("summary", null, "Parciais, runner e histórico"));
    const ledger = el("ol", "ledger");
    if (position.events.length === 0) ledger.append(el("li", null, "Nenhuma parcial simulada."));
    position.events.forEach((event, index) => {
      const type = event.kind === "PARTIAL_PAPER" ?
        "Parcial (" + E.format(BigInt(event.percentBps), 2) + "% sobre " +
        (event.basis === "REMAINING_BALANCE" ? "saldo" : "inicial") + ")" :
        "Encerramento do saldo";
      const automated = event.autoAction ?
        "Auto PAPER " + event.autoAction + " · passo " + event.autoStep + " · " : "";
      ledger.append(el("li", null, (index + 1) + ". " + automated + type +
        " · " + E.format(event.units, 8) + " unidades abstratas"));
    });
    details.append(ledger);
    if (position.status === "OPEN") {
      const form = el("form", "partial-form");
      form.noValidate = true;
      const fields = el("div", "form-grid");
      const pInput = control("input", "50");
      pInput.setAttribute("aria-label", "Percentual da parcial PAPER");
      pInput.required = true;
      const select = control("select");
      select.append(
        option("Saldo restante", "REMAINING_BALANCE"),
        option("Posição inicial", "INITIAL_POSITION")
      );
      select.setAttribute("aria-label", "Base da parcial PAPER");
      fields.append(formField("Parcial (%)", pInput), formField("Base do cálculo", select));
      form.append(fields);
      const submit = el("button", "primary", "Registrar parcial fictícia");
      submit.type = "submit";
      form.append(submit);
      form.addEventListener("submit", event => {
        event.preventDefault();
        try {
          const units = E.partialExit(position, {
            basis: select.value, percent: decimal(pInput.value)
          });
          save();
          render();
          warn("Parcial PAPER registrada: " + E.format(units, 8) +
            " unidades abstratas. Nenhuma ordem enviada.", false);
        } catch (err) { warn(err.message, true); }
      });
      details.append(form);
      const close = el("button", "danger close-button", "Encerrar saldo PAPER");
      close.type = "button";
      close.addEventListener("click", () => {
        if (!window.confirm("Encerrar o saldo fictício de " + position.id +
            "? Esta ação não envia ordens.")) return;
        try {
          E.closeRunner(position);
          save();
          render();
          warn("Saldo PAPER encerrado e registrado no histórico local.", false);
        } catch (err) { warn(err.message, true); }
      });
      details.append(close);
    }
    card.append(details);
    return card;
  }
  function renderPositions() {
    const list = $("position-list");
    list.replaceChildren();
    const positions = state.positions.slice().reverse();
    positions.forEach(p => list.append(positionCard(p)));
    $("position-empty").hidden = positions.length > 0;
    set("position-count", positions.length + (positions.length === 1 ? " cenário" : " cenários"));
  }
  function utc(ms) {
    return new Date(ms).toLocaleString("pt-BR", {
      timeZone: "UTC", day: "2-digit", month: "2-digit",
      hour: "2-digit", minute: "2-digit", hour12: false
    }) + " UTC";
  }
  function validateFeed(snapshot) {
    check(snapshot && snapshot.schema_version === "j5-n50-ws-log-progress-v1" &&
      snapshot.quality === "sanitized_service_log_observation_only" &&
      snapshot.hours_in_window === 24 && Array.isArray(snapshot.slots) &&
      snapshot.slots.length === 24 && snapshot.source_authenticated === false &&
      snapshot.owner_d323_24h_audit_verified === false &&
      snapshot.orders_sent === false, "Relatório N50 sem contrato seguro");
    check(Number.isSafeInteger(snapshot.as_of_ms) &&
      snapshot.as_of_ms > 1600000000000 &&
      snapshot.as_of_ms <= Date.now() + 300000,
      "Relógio UTC do relatório N50 inválido");
    const states = {ok: 0, failed: 0, missing: 0, duplicate: 0};
    snapshot.slots.forEach((slot, i) => {
      check(slot && Object.hasOwn(states, slot.state) &&
        Number.isSafeInteger(slot.closed_end_ms) &&
        slot.closed_end_ms % HOUR === 0 &&
        slot.closed_end_ms <= snapshot.as_of_ms &&
        (i === 0 || slot.closed_end_ms === snapshot.slots[i - 1].closed_end_ms + HOUR),
        "Janela N50 truncada ou desalinhada");
      states[slot.state] += 1;
    });
    check(snapshot.observed_50_of_50_hours === states.ok &&
      snapshot.failed_hours === states.failed &&
      snapshot.missing_hours === states.missing &&
      snapshot.duplicate_hours === states.duplicate &&
      Number.isInteger(snapshot.consecutive_recent_observed_hours) &&
      snapshot.consecutive_recent_observed_hours >= 0 &&
      snapshot.consecutive_recent_observed_hours <= states.ok,
      "Contagens N50 incompatíveis com a linha do tempo");
    let streak = 0;
    for (let i = 23; i >= 0 && snapshot.slots[i].state === "ok"; --i) streak++;
    check(streak === snapshot.consecutive_recent_observed_hours,
      "Sequência N50 inconsistente");
    // v1 legacy imports have no scope metadata; do not invent a cohort.
    const scopeKeys = ["same_scope_recent_50_of_50_hours",
      "scope_evidence_available", "scope_changed_in_window"];
    if (scopeKeys.some(key => Object.hasOwn(snapshot, key))) {
      check(scopeKeys.every(key => Object.hasOwn(snapshot, key)) &&
        typeof snapshot.scope_evidence_available === "boolean" &&
        typeof snapshot.scope_changed_in_window === "boolean" &&
        Number.isInteger(snapshot.same_scope_recent_50_of_50_hours) &&
        snapshot.same_scope_recent_50_of_50_hours >= 0 &&
        snapshot.same_scope_recent_50_of_50_hours <= streak &&
        (snapshot.scope_evidence_available ?
          (snapshot.same_scope_recent_50_of_50_hours >= 1 &&
            snapshot.slots[23].state === "ok") :
          snapshot.same_scope_recent_50_of_50_hours === 0) &&
        (!snapshot.scope_changed_in_window || states.ok >= 2),
        "Progresso da coorte inconsistente");
    }
    return snapshot;
  }
  function validateResearch(snapshot) {
    check(snapshot && snapshot.schema_version === "j2-ws-n50-descriptive-24closed-v1" &&
      ["ws_n50_descriptive_24h_ready", "ws_n50_btc_context_missing"].includes(snapshot.status) &&
      snapshot.ws_journal_integrity_replayed === true &&
      snapshot.audited_assets === 50 &&
      snapshot.eligible_closed_bars_per_asset === 24 &&
      snapshot.formal_d323_24h_verified === false &&
      snapshot.marketwide_top50_verified === false &&
      snapshot.approved_for_signals === false &&
      snapshot.orders_sent === false &&
      /^[0-9a-f]{64}$/.test(snapshot.window_digest_sha256),
      "Pesquisa J2 sem contrato de leitura segura");
    const rows = snapshot.research_rows;
    check(Array.isArray(rows) && (rows.length === 0 || rows.length === 50),
      "Pesquisa deve trazer apenas agregado ou 50 linhas privadas");
    const counts = [snapshot.descriptive_up_breakouts,
      snapshot.descriptive_down_breakouts, snapshot.descriptive_inside_bars];
    check(counts.every(n => Number.isInteger(n) && n >= 0 && n <= 50) &&
      counts.reduce((a,b) => a + b, 0) === 50,
      "Contagens da pesquisa não fecham em 50");
    const symbols = new Set();
    rows.forEach(row => {
      check(row && /^[A-Z0-9]{1,28}USDT$/.test(row.symbol) &&
        !symbols.has(row.symbol) &&
        typeof row.return_24bars_pct === "string" &&
        /^-?(?:0|[1-9][0-9]{0,39})(?:\.[0-9]{1,90})?$/.test(row.return_24bars_pct) &&
        ["above_prior_23h_high","below_prior_23h_low","inside_prior_23h_range"].includes(row.last_closed_bar_breakout) &&
        row.approved_for_signals === false && row.orders_sent === false,
        "Linha descritiva inválida");
      symbols.add(row.symbol);
    });
    return snapshot;
  }

  function exactJ2Metric(raw) {
    // Decimal-string ordering without rounding any financial quantity to float.
    check(typeof raw === "string" &&
      /^-?(?:0|[1-9][0-9]{0,39})(?:\.[0-9]{1,90})?$/.test(raw),
      "Indicador privado J2 fora dos limites");
    const neg = raw.startsWith("-");
    const [integer, frac = ""] = (neg ? raw.slice(1) : raw).split(".");
    return (neg ? -1n : 1n) * BigInt(integer + frac.padEnd(90, "0"));
  }
  function compareJ2Keys(left, right) {
    for (let i = 0; i < 4; i++) {
      if (left[i] < right[i]) return -1;
      if (left[i] > right[i]) return 1;
    }
    return 0;
  }
  function validateWatchlist(snapshot) {
    // Private file ONLY: no credentials, URLs, raw OHLC or order authority.
    check(snapshot && snapshot.schema_version === "j2-n50-ws-descriptive-watchlist-v1" &&
      snapshot.status === "ws_descriptive_watchlist_ready" &&
      snapshot.quality === "private_ws_observations_not_trading_signals" &&
      snapshot.ws_journal_integrity_replayed === true &&
      snapshot.audited_assets === 50 &&
      snapshot.eligible_closed_bars_per_asset === 24 &&
      snapshot.btc_context_available === true &&
      /^[0-9a-f]{64}$/.test(snapshot.window_digest_sha256) &&
      Number.isSafeInteger(snapshot.latest_closed_end_ms) &&
      snapshot.latest_closed_end_ms > 1600000000000 &&
      snapshot.latest_closed_end_ms % HOUR === 0 &&
      snapshot.latest_closed_end_ms <= Date.now() + 300000 &&
      snapshot.execution_intents_created === 0 &&
      snapshot.network_requests === 0 &&
      snapshot.database_mutation_statements === 0 &&
      !Object.hasOwn(snapshot, "research_rows"),
      "Watchlist J2 sem origem ou relógio íntegros");
    const protectedFalse = [
      "formal_d323_24h_verified", "continuous_collector_verified",
      "rotation_36h_live_verified", "marketwide_top50_verified",
      "crypto_identity_independently_verified", "source_authenticated",
      "approved_for_signals", "approved_for_live_use",
      "financial_backtest_approved", "orders_sent", "systemd_modified"
    ];
    check(protectedFalse.every(key => snapshot[key] === false),
      "Watchlist J2 não autoriza sinais ou ordens");
    const up = snapshot.observed_up_breakout_candidates;
    const down = snapshot.observed_down_breakout_candidates;
    const volumeMissing = snapshot.unclassified_volume_assets;
    check([up,down,volumeMissing].every(n => Number.isSafeInteger(n) &&
      n >= 0 && n <= 50) && up + down <= 50,
      "Contagens da watchlist J2 inválidas");
    const scale = 10n ** 90n;
    const seen = new Set();
    const lists = [["up","above_prior_23h_high",up],
      ["down","below_prior_23h_low",down]];
    let hasPrivate = false;
    for (const [direction, breakout, count] of lists) {
      const items = snapshot[direction + "_breakout_watchlist"];
      check(Array.isArray(items) && (items.length === 0 ||
        items.length === Math.min(5, count)),
        "Watchlist J2 incompleta ou excedeu limite");
      hasPrivate = hasPrivate || items.length > 0;
      let previous = null;
      for (const item of items) {
        check(item && typeof item.symbol === "string" &&
          /^[A-Z0-9]{1,28}USDT$/.test(item.symbol) &&
          !seen.has(item.symbol) &&
          item.breakout === breakout &&
          item.approved_for_signals === false && item.orders_sent === false,
          "Símbolo ou direção de watchlist não autorizado");
        seen.add(item.symbol);
        const relative = exactJ2Metric(item.relative_vs_btc_pct_points);
        exactJ2Metric(item.return_24bars_pct);
        const atr = exactJ2Metric(item.mean_true_range_14_pct);
        const turnover = exactJ2Metric(item.quote_turnover_24bars_usdt);
        const ratio = exactJ2Metric(item.last_quote_turnover_vs_prior23_mean);
        check((direction === "up" ? relative > 0n : relative < 0n) &&
          turnover > 0n && atr >= 0n && ratio >= scale,
          "Critérios quantitativos da watchlist inconsistentes");
        const key = [direction === "up" ? -relative : relative,
          -ratio, -turnover, item.symbol];
        check(previous === null || compareJ2Keys(previous, key) <= 0,
          "Ranking da watchlist fora de ordem");
        previous = key;
      }
    }
    if (hasPrivate) {
      check(lists.every(([direction,,count]) =>
        snapshot[direction + "_breakout_watchlist"].length === Math.min(count,5)),
        "Símbolos privados parcialmente omitidos");
    }
    return snapshot;
  }

  function exactBackupKeys(obj, keys) {
    check(obj && typeof obj === "object" && !Array.isArray(obj) &&
      Object.keys(obj).length === keys.length &&
      keys.every(key => Object.hasOwn(obj, key)),
      "Backup PAPER com campos desconhecidos");
  }
  function validatePaperBackup(backup) {
    // The exported PAPER fixture has no permission to mutate market data,
    // execute orders, or carry arbitrary fields into persistent local state.
    exactBackupKeys(backup, ["schema_version", "simulation_only",
      "orders_sent", "exported_at", "state"]);
    check(backup.schema_version === "cia-j5-paper-local-export-v1" &&
      backup.simulation_only === true && backup.orders_sent === false,
      "Backup não é simulação PAPER autorizada");
    check(typeof backup.exported_at === "string" &&
      /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(backup.exported_at),
      "Horário do backup PAPER inválido");
    const stamp = Date.parse(backup.exported_at);
    check(Number.isFinite(stamp) && stamp > Date.parse("2020-01-01T00:00:00.000Z") &&
      stamp <= Date.now() + 300000 &&
      new Date(stamp).toISOString() === backup.exported_at,
      "Horário do backup PAPER inconsistente");
    const restored = E.validateState(backup.state);
    exactBackupKeys(restored, ["version", "nextId", "config", "positions"]);
    exactBackupKeys(restored.config, ["leverage", "marginCents", "runnerBps", "paused"]);
    check(restored.positions.every(position =>
      Number(position.id.slice(4)) < restored.nextId),
      "Backup PAPER com contador de IDs inconsistente");
    restored.positions.forEach(position => {
      const positionKeys = ["id", "symbol", "side", "openedAt",
        "entryPriceUnits", "marginCents", "leverageAtOpen", "runnerBpsAtOpen",
        "initialUnits", "remainingUnits", "events", "status"];
      if (Object.hasOwn(position, "auto")) {
        positionKeys.push("auto");
        exactBackupKeys(position.auto, ["version", "target1Bps",
          "target2Bps", "stopBps", "partialBps", "lastStep", "hits"]);
      }
      exactBackupKeys(position, positionKeys);
      position.events.forEach(event => {
        const keys = event.kind === "PARTIAL_PAPER" ?
          ["kind", "basis", "percentBps", "units", "at"] :
          ["kind", "units", "at"];
        if (Object.hasOwn(event, "autoStep") ||
            Object.hasOwn(event, "autoAction")) {
          keys.push("autoStep", "autoAction");
        }
        exactBackupKeys(event, keys);
      });
    });
    return restored;
  }

  function renderFeed() {
    $("feed-empty").hidden = !!feed;
    $("feed-loaded").hidden = !feed;
    if (!feed) {
      set("feed-status", "Não conectado");
      set("updated-time", "Dados não conectados");
      set("mode-pill", "PAPER · OFFLINE");
      return;
    }
    set("feed-status", feedOrigin === "local-auto" ?
      "Fonte local automática" : "Relatório importado");
    set("mode-pill", feedOrigin === "local-auto" ?
      "PAPER · FONTE LOCAL" : "PAPER · OFFLINE");
    set("updated-time", "N50: " + utc(feed.as_of_ms));
    set("n50-ok", feed.observed_50_of_50_hours + " / 24");
    set("n50-streak", feed.consecutive_recent_observed_hours);
    set("n50-failed", feed.failed_hours + feed.duplicate_hours);
    const hasScope = feed.scope_evidence_available === true;
    set("n50-scope", hasScope ?
      feed.same_scope_recent_50_of_50_hours + " / 24" : "—");
    set("n50-scope-note", feed.scope_changed_in_window === true ?
      "Mudança de coorte nos relatórios: não é falha da coleta nem reinício da homologação." :
      hasScope ? "Mesma coorte nos relatórios recentes; a auditoria SQLite D323 é separada." :
      "Os relatórios importados não identificam a coorte. Continuidade não demonstrada.");
    const timeline = $("timeline");
    timeline.replaceChildren();
    feed.slots.forEach(slot => {
      const li = el("li", slot.state);
      const label = {
        ok:"50/50 observado", failed:"Falha ou abstenção",
        missing:"Sem relatório", duplicate:"Duplicata"
      }[slot.state];
      li.title = utc(slot.closed_end_ms) + " · " + label;
      li.setAttribute("aria-label", li.title);
      timeline.append(li);
    });
  }
  function isLocalReadOnlyOrigin() {
    const loc = window.location;
    return loc.protocol === "http:" && loc.port === "8765" &&
      (loc.hostname === "127.0.0.1" || loc.hostname === "localhost");
  }

  async function refreshLocalFeed() {
    // file:// previews and ANY external host have no runtime transport.
    // A manually selected N50 snapshot stays in control for this session.
    if (!isLocalReadOnlyOrigin() || feedOrigin === "manual") return;
    try {
      const response = await window.fetch("/api/n50-progress", {
        method: "GET", credentials: "omit",
        cache: "no-store", redirect: "error"
      });
      check(response.ok && response.status === 200 &&
        (response.headers.get("content-type") || "").startsWith("application/json"),
        "Fonte de leitura local indisponível");
      const raw = await response.text();
      check(raw.length > 0 && raw.length < MAX_SNAPSHOT,
        "Relatório da fonte local fora do limite");
      const candidate = validateFeed(JSON.parse(raw));
      if (feedOrigin === "manual") return; // Import may complete during GET.
      feed = candidate;
      feedOrigin = "local-auto";
      render();
    } catch (_) {
      if (feedOrigin === "manual") return;
      // Never display a stale 50/50 as if the server still responded.
      feed = null;
      feedOrigin = "none";
      render();
      set("feed-status", "Fonte local indisponível");
    }
  }

  async function refreshLocalResearch() {
    // Reuse the exact private J2 50×24 readonly schema, never a trading signal.
    // No request occurs for file://, remote hosts or manual J2 imports.
    if (!isLocalReadOnlyOrigin() || researchOrigin === "manual") return;
    try {
      const response = await window.fetch("/api/j2-research", {
        method: "GET", credentials: "omit",
        cache: "no-store", redirect: "error"
      });
      check(response.ok && response.status === 200 &&
        (response.headers.get("content-type") || "").startsWith("application/json"),
        "Pesquisa J2 não disponível");
      const raw = await response.text();
      check(raw.length > 0 && raw.length < MAX_SNAPSHOT,
        "Pesquisa J2 local fora do limite");
      const candidate = validateResearch(JSON.parse(raw));
      check(candidate.research_rows.length === 0,
        "Servidor local J2 deve retornar apenas agregados");
      if (researchOrigin === "manual") return; // Import may complete during GET.
      research = candidate;
      researchOrigin = "local-auto";
      renderResearch();
      renderQuality();
    } catch (_) {
      if (researchOrigin === "manual") return;
      // Do not retain a once-valid breakout as a current observation.
      research = null;
      researchOrigin = "none";
      renderResearch();
      renderQuality();
      set("research-status", "J2 ainda indisponível");
    }
  }

  function renderResearch() {
    $("research-empty").hidden = !!research;
    $("research-loaded").hidden = !research;
    if (!research) {
      set("research-status", "J2 aguarda auditoria privada");
      return;
    }
    set("research-status", researchOrigin === "local-auto" ?
      "Descritivo · fonte local" : "Descritivo · importado");
    set("research-count", research.audited_assets);
    set("research-breakout", research.descriptive_up_breakouts);
    set("research-down", research.descriptive_down_breakouts);
    const list = $("research-rows");
    list.replaceChildren();
    if (research.research_rows.length === 0) {
      list.append(el("p", "muted fine",
        "Agregado importado. O operador não incluiu os símbolos privados neste relatório."));
    } else {
      const label = {above_prior_23h_high:"Acima da faixa",
        below_prior_23h_low:"Abaixo da faixa",
        inside_prior_23h_range:"Dentro da faixa"};
      research.research_rows.slice(0,5).forEach(row => {
        const node = el("div", "research-item");
        const left = el("div");
        left.append(el("strong", null, row.symbol),
          el("span", null, label[row.last_closed_bar_breakout]));
        const right = el("div", "score");
        right.append(el("strong", null, row.return_24bars_pct + "%"),
          el("span", null, "Variação 24h observada"));
        node.append(left, right);
        list.append(node);
      });
    }
  }
  function renderWatchlist() {
    $("watchlist-empty").hidden = !!watchlist;
    $("watchlist-loaded").hidden = !watchlist;
    if (!watchlist) {
      set("watchlist-status", "Sem watchlist importada");
      return;
    }
    const recent = watchlist.latest_closed_end_ms >= Date.now() - 2 * HOUR;
    set("watchlist-status", recent ? "Observação J2 importada" : "Histórico · não atual");
    set("watchlist-up-count", watchlist.observed_up_breakout_candidates);
    set("watchlist-down-count", watchlist.observed_down_breakout_candidates);
    set("watchlist-unclassified-count", watchlist.unclassified_volume_assets);
    set("watchlist-closed-end", utc(watchlist.latest_closed_end_ms));
    for (const [side, direction] of [["up","LONG"], ["down","SHORT"]]) {
      const list = $("watchlist-" + side + "-rows");
      list.replaceChildren();
      const rows = watchlist[side + "_breakout_watchlist"];
      if (!rows.length) {
        list.append(el("p", "muted fine",
          "Sem símbolos privados: não há candidatos exibíveis neste relatório."));
        continue;
      }
      rows.forEach((row, i) => {
        const card = el("div", "research-item");
        const left = el("div");
        left.append(el("strong", null, (i + 1) + ". " + row.symbol),
          el("span", null, direction + " · observação, não sinal"));
        const right = el("div", "score");
        right.append(el("strong", null, row.relative_vs_btc_pct_points + " pp"),
          el("span", null, "Força vs BTC · razão volume " +
            row.last_quote_turnover_vs_prior23_mean));
        card.append(left, right);
        list.append(card);
      });
    }
    set("watchlist-note", recent ?
      "Pesquisa fechada e somente leitura. Nenhuma posição foi aberta; J3 ainda avalia risco e resultados." :
      "Snapshot histórico: não interpretar como oportunidade atual. Nenhuma posição foi aberta.");
  }

  function renderQuality() {
    const recent = feed && feed.slots[23].closed_end_ms >= Date.now() - 2 * HOUR;
    const n50 = !feed ? "N50: fonte indisponível ou sem relatório." :
      !recent ? "N50: relatório obsoleto; atualização necessária." :
      "N50: " + feed.observed_50_of_50_hours + "/24 horas 50/50 observadas em logs" +
      (feed.scope_evidence_available === true ?
        "; mesma coorte observada: " + feed.same_scope_recent_50_of_50_hours + "/24" :
        "; coorte não comprovada nos logs") +
      (feedOrigin === "manual" ? " (importação manual)." : " (fonte local).");
    const j2 = watchlist ? "J2: watchlist observacional importada localmente; não é sinal." :
      !research ? "J2: aguardando janela privada íntegra de 50 × 24h." :
      researchOrigin === "manual" ? "J2: pesquisa descritiva importada manualmente; sem sinais." :
      !recent ? "J2: pesquisa agregada recebida, mas fonte N50 ausente ou obsoleta; prontidão não comprovada." :
      "J2: pesquisa agregada disponível; não equivale à homologação J1 nem a sinal.";
    set("quality-n50", n50);
    set("quality-j2", j2);
  }
  function render() {
    updateSummary();
    updateSettings();
    renderPositions();
    renderFeed();
    renderResearch();
    renderWatchlist();
    renderQuality();
  }
  function bind() {
    $("refresh-research-local").addEventListener("click", () => {
      if (researchOrigin === "manual") {
        warn("O JSON J2 importado tem prioridade nesta sessão. Recarregue a página para voltar à pesquisa local.", false);
      } else {
        void refreshLocalResearch();
      }
    });
    $("refresh-local").addEventListener("click", () => {
      if (feedOrigin === "manual") {
        warn("O JSON N50 importado manualmente tem prioridade nesta sessão. Recarregue a página para reativar a fonte local.", false);
      } else {
        void refreshLocalFeed();
      }
    });
    $("margin").addEventListener("input", () => { $("open-form").dataset.edited = "true"; });
    $("auto-enabled").addEventListener("change", () => {
      $("auto-config").hidden = !$("auto-enabled").checked;
    });
    $("open-form").addEventListener("submit", event => {
      event.preventDefault();
      try {
        const p = E.openPosition(state, {
          symbol: $("symbol").value, side: $("side").value,
          entry: decimal($("entry").value),
          margin: decimal($("margin").value),
          leverage: state.config.leverage,
          runner: E.format(BigInt(state.config.runnerBps), 2).replace(",", "."),
          auto: $("auto-enabled").checked ? {
            target1: decimal($("auto-target1").value),
            target2: decimal($("auto-target2").value),
            stop: decimal($("auto-stop").value),
            partial: decimal($("auto-partial").value)
          } : undefined
        });
        save();
        render();
        warn("Cenário " + p.id + " criado com " + p.leverageAtOpen +
          "x e margem PAPER. Nenhuma ordem real enviada.", false);
        $("posicoes").scrollIntoView({behavior:"smooth"});
      } catch (err) { warn(err.message, true); }
    });
    $("settings-form").addEventListener("submit", event => {
      event.preventDefault();
      try {
        const leverage = Number($("leverage").value);
        check(Number.isInteger(leverage) && leverage >= 1 && leverage <= 100,
          "Alavancagem deve estar entre 1 e 100x");
        const margin = E.fixed(decimal($("default-margin").value), 2, "Margem");
        check(margin >= 1n && margin <= 100000n,
          "Margem padrão permitida: US$ 0,01–1.000");
        const runner = E.percent(decimal($("runner").value), true);
        check(runner < 10000, "Runner precisa ser inferior a 100%");
        state.config.leverage = leverage;
        state.config.marginCents = margin.toString();
        state.config.runnerBps = runner;
        delete $("open-form").dataset.edited;
        save();
        render();
        warn("Configuração PAPER salva. Posições existentes mantiveram sua alavancagem original.", false);
      } catch (err) { warn(err.message, true); }
    });
    $("pause").addEventListener("change", () => {
      state.config.paused = $("pause").checked;
      save(); render();
      warn(state.config.paused ?
        "Trava local PAPER ativada. A coleta na VPS NÃO foi pausada." :
        "Trava local PAPER desativada. Não há execução real.", false);
    });
    $("import-file").addEventListener("change", async event => {
      const file = event.target.files && event.target.files[0];
      if (!file) return;
      try {
        check(file.size > 0 && file.size <= MAX_SNAPSHOT,
          "Arquivo JSON excede 1 MiB ou está vazio");
        const raw = await file.text();
        check(raw.length <= MAX_SNAPSHOT, "Relatório importado excede limite");
        const payload = JSON.parse(raw);
        if (payload.schema_version === "j5-n50-ws-log-progress-v1") {
          feed = validateFeed(payload);
          feedOrigin = "manual";
          warn("Relatório N50 carregado localmente. Substitui a atualização automática nesta sessão.", false);
        } else if (payload.schema_version === "j2-ws-n50-descriptive-24closed-v1") {
          research = validateResearch(payload);
          researchOrigin = "manual";
          warn("Pesquisa J2 importada; ela terá prioridade nesta sessão. Não é recomendação de entrada.", false);
        } else if (payload.schema_version === "j2-n50-ws-descriptive-watchlist-v1") {
          watchlist = validateWatchlist(payload);
          warn("Watchlist J2 importada somente nesta sessão; observações não são sinais nem ordens.", false);
        } else if (payload.schema_version === "cia-j5-paper-local-export-v1") {
          const restored = validatePaperBackup(payload);
          if (!window.confirm("Restaurar este backup PAPER? Todos os cenários locais atuais serão substituídos. A VPS e a coleta N50 não serão alteradas.")) {
            warn("Restauração cancelada. Os cenários PAPER atuais foram preservados.", false);
            return;
          }
          state = restored;
          delete $("open-form").dataset.edited;
          save();
          warn(storageAvailable ?
            "Backup PAPER restaurado neste navegador. Nenhuma ordem foi enviada." :
            "Backup PAPER aberto nesta sessão, mas não foi possível persistir no navegador. Exporte novamente antes de sair.",
            !storageAvailable);
        } else throw new Error("Schema JSON desconhecido. Importe relatórios sanitizados N50/J2 ou backup PAPER local.");
        render();
      } catch (err) {
        warn("Importação recusada: " + err.message, true);
      } finally {
        event.target.value = "";
      }
    });
    $("export-paper").addEventListener("click", () => {
      try {
        E.validateState(state);
        const content = JSON.stringify({
          schema_version:"cia-j5-paper-local-export-v1",
          simulation_only:true,orders_sent:false,exported_at:new Date().toISOString(),
          state
        }, null, 2);
        const blob = new Blob([content], {type:"application/json"});
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url; a.download = "crypto-intelligence-paper.json";
        document.body.append(a); a.click(); a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
        warn("Cenários PAPER exportados. Nenhuma informação de corretora foi incluída.", false);
      } catch (err) { warn(err.message, true); }
    });
    $("reset-paper").addEventListener("click", () => {
      if (!window.confirm("Apagar todos os cenários PAPER salvos neste navegador? Ação irreversível local.")) return;
      state = E.emptyState();
      delete $("open-form").dataset.edited;
      save(); render();
      warn("Cenários PAPER locais apagados. A VPS permanece intocada.", false);
    });
  }
  load();
  bind();
  render();
  if (isLocalReadOnlyOrigin()) {
    $("refresh-local").hidden = false;
    $("refresh-research-local").hidden = false;
    void refreshLocalFeed();
    void refreshLocalResearch();
    window.setInterval(() => { void refreshLocalFeed(); }, 60_000);
    window.setInterval(() => { void refreshLocalResearch(); }, 300_000);
  }
})();
