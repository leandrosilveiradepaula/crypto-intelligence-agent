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
    card.append(meta);
    const cells = el("div", "position-balances");
    cells.append(
      cell("Quantidade inicial abstrata", E.format(position.initialUnits, 8)),
      cell("Quantidade restante", E.format(position.remainingUnits, 8)),
      cell("Exposição nominal da parcela", amount(E.grossEntryExposureCents(position))),
      cell("Saídas fictícias registradas", position.events.length)
    );
    card.append(cells);
    const details = el("details");
    details.append(el("summary", null, "Parciais, runner e histórico"));
    const ledger = el("ol", "ledger");
    if (position.events.length === 0) ledger.append(el("li", null, "Nenhuma parcial simulada."));
    position.events.forEach((event, index) => {
      const type = event.kind === "PARTIAL_PAPER" ?
        "Parcial (" + E.format(BigInt(event.percentBps), 2) + "% sobre " +
        (event.basis === "REMAINING_BALANCE" ? "saldo" : "inicial") + ")" :
        "Encerramento do saldo";
      ledger.append(el("li", null, (index + 1) + ". " + type +
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
      feed = candidate;
      feedOrigin = "local-auto";
      render();
    } catch (_) {
      // Never display a stale 50/50 as if the server still responded.
      feed = null;
      feedOrigin = "none";
      render();
      set("feed-status", "Fonte local indisponível");
    }
  }

  function renderResearch() {
    $("research-empty").hidden = !!research;
    $("research-loaded").hidden = !research;
    if (!research) {
      set("research-status", "Aguardando 24h");
      return;
    }
    set("research-status", "Descritivo · local");
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
  function render() {
    updateSummary();
    updateSettings();
    renderPositions();
    renderFeed();
    renderResearch();
  }
  function bind() {
    $("refresh-local").addEventListener("click", () => {
      if (feedOrigin === "manual") {
        warn("O JSON N50 importado manualmente tem prioridade nesta sessão. Recarregue a página para reativar a fonte local.", false);
      } else {
        void refreshLocalFeed();
      }
    });
    $("margin").addEventListener("input", () => { $("open-form").dataset.edited = "true"; });
    $("open-form").addEventListener("submit", event => {
      event.preventDefault();
      try {
        const p = E.openPosition(state, {
          symbol: $("symbol").value, side: $("side").value,
          entry: decimal($("entry").value),
          margin: decimal($("margin").value),
          leverage: state.config.leverage,
          runner: E.format(BigInt(state.config.runnerBps), 2).replace(",", ".")
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
          warn("Pesquisa descritiva J2 carregada. Isso não é recomendação de entrada.", false);
        } else throw new Error("Schema JSON desconhecido. Importe somente relatórios sanitizados N50/J2.");
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
    void refreshLocalFeed();
    window.setInterval(() => { void refreshLocalFeed(); }, 60_000);
  }
})();
