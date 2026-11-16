/* J5/MVP1: deterministic decimal arithmetic for a LOCAL PAPER simulation.
   No exchange venue, transport, funding, venue fills or actual liquidation. */
(function (global) {
  "use strict";
  const SCALE = 100000000n;
  const BPS = 10000n;
  const MAX_POSITIONS = 100;
  const MAX_EVENTS = 100;
  const SYMBOL = /^[A-Z0-9]{1,28}USDT$/;
  const INTEGER = /^(0|[1-9][0-9]*)$/;
  const BASE_TIME = "2020-01-01T00:00:00.000Z";

  function requireValid(condition, message) {
    if (!condition) throw new Error(message);
  }
  function fixed(raw, digits, label) {
    requireValid(typeof raw === "string" &&
      /^(?:0|[1-9][0-9]{0,11})(?:\.[0-9]{1,8})?$/.test(raw),
      label + ": use número decimal positivo sem sinal");
    const parts = raw.split(".");
    requireValid((parts[1] || "").length <= digits,
      label + ": casas decimais acima do limite");
    return BigInt(parts[0]) * (10n ** BigInt(digits)) +
      BigInt((parts[1] || "").padEnd(digits, "0") || "0");
  }
  function format(value, digits) {
    let n = BigInt(value);
    const neg = n < 0n;
    if (neg) n = -n;
    const pow = 10n ** BigInt(digits);
    const whole = (n / pow).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ".");
    const fraction = (n % pow).toString().padStart(digits, "0").replace(/0+$/, "");
    return (neg ? "-" : "") + whole + (fraction ? "," + fraction : "");
  }
  function percent(raw, allowZero) {
    const result = fixed(raw, 2, "Percentual");
    requireValid(result <= BPS && (allowZero || result > 0n),
      "Percentual fora de 0–100%");
    return Number(result);
  }
  function settings() {
    return { leverage: 50, marginCents: "300", runnerBps: 600, paused: false };
  }
  function emptyState() {
    return { version: 1, nextId: 1, config: settings(), positions: [] };
  }
  function createAutoPolicy(raw, position) {
    if (raw === undefined) return undefined; // Legacy manually-managed position.
    requireValid(raw && typeof raw === "object" && !Array.isArray(raw) &&
      Object.keys(raw).length === 4 &&
      ["target1", "target2", "stop", "partial"].every(k =>
        Object.hasOwn(raw, k)), "Política automática PAPER inválida");
    const target1Bps = percent(raw.target1, false);
    const target2Bps = percent(raw.target2, false);
    const stopBps = percent(raw.stop, false);
    const partialBps = percent(raw.partial, false);
    requireValid(target1Bps < target2Bps && target2Bps < 10000 &&
      stopBps < 10000, "Alvos e stop PAPER exigem percentuais ordenados abaixo de 100%");
    // Two target exits must fit the runner floor at creation. Do not add a
    // position and discover later that its configured automatic exits fail.
    const dryRun = {...position, events: []};
    const pct = format(BigInt(partialBps), 2).replace(",", ".");
    partialExit(dryRun, {basis: "REMAINING_BALANCE", percent: pct});
    partialExit(dryRun, {basis: "REMAINING_BALANCE", percent: pct});
    return {version: 1, target1Bps, target2Bps, stopBps, partialBps,
      lastStep: 0, hits: 0};
  }

  function openPosition(state, input, now) {
    requireValid(state && state.version === 1 && Array.isArray(state.positions),
      "Estado PAPER inválido");
    requireValid(!state.config.paused, "Trava local PAPER ativa");
    requireValid(state.positions.length < MAX_POSITIONS,
      "Limite de cenários locais atingido");
    const symbol = String(input.symbol || "").trim().toUpperCase();
    requireValid(SYMBOL.test(symbol), "Informe um contrato USDT sintético");
    requireValid(input.side === "LONG" || input.side === "SHORT",
      "Direção PAPER inválida");
    const margin = fixed(input.margin, 2, "Margem PAPER");
    const price = fixed(input.entry, 8, "Preço hipotético");
    const leverage = Number(input.leverage);
    const floor = percent(input.runner, true);
    requireValid(margin >= 1n && margin <= 100000n,
      "Margem PAPER permitida: US$ 0,01–1.000");
    requireValid(price > 0n && price <= 10000000000000000n,
      "Preço hipotético fora da faixa");
    requireValid(Number.isInteger(leverage) && leverage >= 1 && leverage <= 100,
      "Alavancagem da simulação: 1–100x");
    requireValid(floor < 10000, "Runner de 100% impediria as parciais");
    const units = (margin * BigInt(leverage) * 100000000000000n) / price;
    requireValid(units > 0n && units <= 10n ** 30n,
      "Quantidade abstrata fora da precisão da simulação");
    const id = "SIM-" + String(state.nextId).padStart(4, "0");
    const at = typeof now === "string" && !Number.isNaN(Date.parse(now)) ? now : new Date().toISOString();
    const position = {
      id, symbol, side: input.side, openedAt: at,
      entryPriceUnits: price.toString(), marginCents: margin.toString(),
      leverageAtOpen: leverage, runnerBpsAtOpen: floor,
      initialUnits: units.toString(), remainingUnits: units.toString(),
      events: [], status: "OPEN"
    };
    const auto = createAutoPolicy(input.auto, position);
    if (auto !== undefined) position.auto = auto;
    state.positions.push(position);
    state.nextId += 1;
    return position;
  }
  function partialExit(position, input, now) {
    requireValid(position && position.status === "OPEN", "Cenário já encerrado");
    requireValid(Array.isArray(position.events) && position.events.length < MAX_EVENTS,
      "Limite de parciais locais atingido");
    const basis = input.basis;
    requireValid(basis === "INITIAL_POSITION" || basis === "REMAINING_BALANCE",
      "Base de percentual inválida");
    const p = percent(input.percent, false);
    const initial = BigInt(position.initialUnits);
    const before = BigInt(position.remainingUnits);
    const reserve = initial * BigInt(position.runnerBpsAtOpen) / BPS;
    const ref = basis === "INITIAL_POSITION" ? initial : before;
    const exit = ref * BigInt(p) / BPS;
    requireValid(exit > 0n && exit <= before, "Parcial inexistente ou acima do saldo");
    requireValid(before - exit >= reserve,
      "Parcial ultrapassa a reserva do runner. Ajuste o percentual.");
    position.remainingUnits = (before - exit).toString();
    if (before === exit) position.status = "CLOSED";
    position.events.push({
      kind: "PARTIAL_PAPER", basis, percentBps: p, units: exit.toString(),
      at: now || new Date().toISOString()
    });
    return exit;
  }
  function closeRunner(position, now) {
    requireValid(position && position.status === "OPEN", "Cenário já encerrado");
    requireValid(position.events.length < MAX_EVENTS, "Limite de eventos atingido");
    const left = BigInt(position.remainingUnits);
    requireValid(left > 0n, "Nenhuma quantidade a encerrar");
    position.remainingUnits = "0";
    position.status = "CLOSED";
    position.events.push({
      kind: "CLOSE_PAPER", units: left.toString(),
      at: now || new Date().toISOString()
    });
    return left;
  }
  function applyAutoPaperStep(position, rawMark, step, now) {
    requireValid(position && position.status === "OPEN" &&
      position.auto && position.auto.version === 1,
      "Gatilhos PAPER indisponíveis nesta posição");
    const policy = position.auto;
    requireValid(Number.isSafeInteger(step) && step > 0 && step <= 100000 &&
      step === policy.lastStep + 1,
      "Passo PAPER repetido ou fora de sequência");
    const mark = fixed(rawMark, 8, "Fechamento hipotético");
    requireValid(mark > 0n, "Fechamento hipotético deve ser positivo");
    const entry = BigInt(position.entryPriceUnits);
    const scaled = mark * BPS;
    const long = position.side === "LONG";
    const stopTouched = long ?
      scaled <= entry * (BPS - BigInt(policy.stopBps)) :
      scaled >= entry * (BPS + BigInt(policy.stopBps));
    let action = "NO_TRIGGER";
    let units = 0n;
    if (stopTouched) {
      units = closeRunner(position, now);
      action = "STOP";
    } else if (policy.hits < 2) {
      const target = policy.hits === 0 ? policy.target1Bps : policy.target2Bps;
      const reached = long ?
        scaled >= entry * (BPS + BigInt(target)) :
        scaled <= entry * (BPS - BigInt(target));
      if (reached) {
        const pct = format(BigInt(policy.partialBps), 2).replace(",", ".");
        units = partialExit(position, {basis: "REMAINING_BALANCE", percent: pct}, now);
        action = policy.hits === 0 ? "TARGET_1" : "TARGET_2";
        policy.hits += 1;
      }
    }
    if (action !== "NO_TRIGGER") {
      const event = position.events[position.events.length - 1];
      event.autoStep = step;
      event.autoAction = action;
    }
    policy.lastStep = step;
    return Object.freeze({step, action, units: units.toString(),
      remainingUnits: position.remainingUnits, ordersSent: false});
  }

  function replayAutoPaperMarks(position, marks) {
    requireValid(position && position.status === "OPEN" &&
      position.auto && position.auto.version === 1,
      "Replay automático exige posição PAPER aberta com gatilhos");
    requireValid(Array.isArray(marks) && marks.length >= 1 && marks.length <= 24,
      "Cenário PAPER exige de 1 a 24 fechamentos fictícios");
    // Prevalidate the COMPLETE fixture. A malformed later row must never
    // leave earlier exits half-committed in the original browser state.
    for (const mark of marks) {
      const value = fixed(mark, 8, "Fechamento hipotético do cenário");
      requireValid(value > 0n, "Cenário PAPER não aceita mark zero");
    }
    const draft = {...position,
      auto: {...position.auto},
      events: position.events.map(event => ({...event}))};
    let processed = 0, skippedAfterClose = 0, targets = 0, stopped = false;
    for (const mark of marks) {
      if (draft.status === "CLOSED") {
        skippedAfterClose += 1;
        continue;
      }
      const next = applyAutoPaperStep(draft, mark, draft.auto.lastStep + 1);
      processed += 1;
      if (next.action === "TARGET_1" || next.action === "TARGET_2") targets += 1;
      if (next.action === "STOP") stopped = true;
    }
    // All-or-nothing for this synchronous, fixture-only batch. No DB, orders,
    // network or intermediate localStorage writes exist in the engine.
    position.remainingUnits = draft.remainingUnits;
    position.status = draft.status;
    position.events = draft.events;
    position.auto = draft.auto;
    return Object.freeze({processedSteps: processed, skippedAfterClose,
      targetEvents: targets, stopTriggered: stopped, ordersSent: false});
  }

  function grossEntryExposureCents(position) {
    const initial = BigInt(position.initialUnits);
    const rest = BigInt(position.remainingUnits);
    return BigInt(position.marginCents) * BigInt(position.leverageAtOpen) * rest / initial;
  }
  function grossMarkPnlCents(position, mark) {
    const parsed = fixed(mark, 8, "Mark hipotético");
    requireValid(parsed > 0n, "Mark hipotético deve ser positivo");
    const difference = parsed - BigInt(position.entryPriceUnits);
    const direction = position.side === "LONG" ? 1n : -1n;
    return difference * BigInt(position.remainingUnits) * direction / 100000000000000n;
  }
  function grossHypotheticalMarginImpactBps(position, rawMark) {
    // Price move × leverageAtOpen, on the original simulated margin.
    // This is NOT liquidation, a fill, net return or risk-adjusted profit.
    requireValid(position && position.status === "OPEN" &&
      ["LONG", "SHORT"].includes(position.side) &&
      Number.isInteger(position.leverageAtOpen) &&
      position.leverageAtOpen >= 1 && position.leverageAtOpen <= 100,
      "Posição PAPER ou alavancagem inválida");
    const mark = fixed(rawMark, 8, "Mark hipotético");
    requireValid(mark > 0n, "Mark hipotético deve ser positivo");
    const entry = BigInt(position.entryPriceUnits);
    requireValid(entry > 0n, "Preço hipotético de entrada inválido");
    const side = position.side === "LONG" ? 1n : -1n;
    return (mark - entry) * side * BigInt(position.leverageAtOpen) * BPS / entry;
  }

  function validateState(raw) {
    requireValid(raw && typeof raw === "object" && !Array.isArray(raw) &&
      raw.version === 1 && Number.isSafeInteger(raw.nextId) &&
      raw.nextId >= 1 && raw.nextId < 1000000, "Versão local inválida");
    const c = raw.config;
    requireValid(c && Number.isInteger(c.leverage) && c.leverage >= 1 &&
      c.leverage <= 100 && INTEGER.test(c.marginCents) &&
      BigInt(c.marginCents) >= 1n && BigInt(c.marginCents) <= 100000n &&
      Number.isInteger(c.runnerBps) && c.runnerBps >= 0 &&
      c.runnerBps < 10000 && typeof c.paused === "boolean",
      "Configuração local inválida");
    requireValid(Array.isArray(raw.positions) && raw.positions.length <= MAX_POSITIONS,
      "Lista de posições locais inválida");
    const ids = new Set();
    for (const p of raw.positions) {
      requireValid(p && /^SIM-[0-9]{4,6}$/.test(p.id) && !ids.has(p.id) &&
        SYMBOL.test(p.symbol) && ["LONG", "SHORT"].includes(p.side) &&
        !Number.isNaN(Date.parse(p.openedAt)) &&
        ["OPEN", "CLOSED"].includes(p.status) &&
        Number.isInteger(p.leverageAtOpen) && p.leverageAtOpen >= 1 &&
        p.leverageAtOpen <= 100 && Number.isInteger(p.runnerBpsAtOpen) &&
        p.runnerBpsAtOpen >= 0 && p.runnerBpsAtOpen < 10000 &&
        [p.entryPriceUnits, p.marginCents, p.initialUnits, p.remainingUnits]
          .every(s => typeof s === "string" && INTEGER.test(s) && s.length <= 40),
        "Cenário local inválido");
      ids.add(p.id);
      const initial = BigInt(p.initialUnits);
      const remaining = BigInt(p.remainingUnits);
      requireValid(initial > 0n && remaining >= 0n && remaining <= initial &&
        BigInt(p.entryPriceUnits) > 0n && BigInt(p.marginCents) > 0n &&
        (p.status === "OPEN" ? remaining > 0n : remaining === 0n) &&
        Array.isArray(p.events) && p.events.length <= MAX_EVENTS,
        "Saldo PAPER não conservado");
      const hasAuto = Object.hasOwn(p, "auto");
      if (hasAuto) {
        const a = p.auto;
        requireValid(a && typeof a === "object" && !Array.isArray(a) &&
          Object.keys(a).length === 7 &&
          ["version", "target1Bps", "target2Bps", "stopBps",
           "partialBps", "lastStep", "hits"].every(k => Object.hasOwn(a, k)) &&
          a.version === 1 && Number.isSafeInteger(a.lastStep) &&
          a.lastStep >= 0 && a.lastStep <= 100000 &&
          Number.isSafeInteger(a.hits) && a.hits >= 0 && a.hits <= 2 &&
          [a.target1Bps, a.target2Bps, a.stopBps, a.partialBps].every(n =>
            Number.isInteger(n) && n > 0 && n <= 10000) &&
          a.target1Bps < a.target2Bps && a.target2Bps < 10000 &&
          a.stopBps < 10000 && a.hits <= a.lastStep,
          "Política automática PAPER adulterada");
      }
      let exited = 0n, replayRemaining = initial, autoHits = 0;
      let priorAutoStep = 0, stopped = false;
      const reserveFloor = initial * BigInt(p.runnerBpsAtOpen) / BPS;
      for (const event of p.events) {
        requireValid(event && ["PARTIAL_PAPER","CLOSE_PAPER"].includes(event.kind) &&
          typeof event.units === "string" && INTEGER.test(event.units) &&
          event.units.length <= 40 && BigInt(event.units) > 0n &&
          !Number.isNaN(Date.parse(event.at)), "Evento PAPER inválido");
        if (event.kind === "PARTIAL_PAPER") {
          requireValid(["INITIAL_POSITION","REMAINING_BALANCE"].includes(event.basis) &&
            Number.isInteger(event.percentBps) &&
            event.percentBps >= 1 && event.percentBps <= 10000,
            "Parcial PAPER sem base");
        }
        const eventUnits = BigInt(event.units);
        requireValid(replayRemaining > 0n && eventUnits <= replayRemaining,
          "Evento PAPER excede saldo cronológico");
        if (event.kind === "PARTIAL_PAPER") {
          const ref = event.basis === "INITIAL_POSITION" ? initial : replayRemaining;
          requireValid(ref * BigInt(event.percentBps) / BPS === eventUnits &&
            replayRemaining - eventUnits >= reserveFloor,
            "Quantidade parcial PAPER difere do replay exato");
        } else {
          requireValid(eventUnits === replayRemaining,
            "Encerramento PAPER não corresponde ao saldo anterior");
        }
        replayRemaining -= eventUnits;
        const autoTagged = Object.hasOwn(event, "autoStep") ||
          Object.hasOwn(event, "autoAction");
        if (autoTagged) {
          requireValid(hasAuto && Number.isSafeInteger(event.autoStep) &&
            event.autoStep > priorAutoStep &&
            event.autoStep <= p.auto.lastStep && !stopped,
            "Evento automático PAPER repetido ou fora de sequência");
          priorAutoStep = event.autoStep;
          if (event.autoAction === "STOP") {
            requireValid(event.kind === "CLOSE_PAPER",
              "STOP PAPER precisa encerrar o saldo");
            stopped = true;
          } else {
            autoHits += 1;
            requireValid(event.autoAction === "TARGET_" + autoHits &&
              event.kind === "PARTIAL_PAPER" &&
              event.basis === "REMAINING_BALANCE" &&
              event.percentBps === p.auto.partialBps && autoHits <= 2,
              "Parcial automática PAPER sem contrato");
          }
        }
        exited += BigInt(event.units);
      }
      requireValid(!hasAuto || (p.auto.hits === autoHits &&
        (!stopped || p.status === "CLOSED")),
        "Progresso automático PAPER inconsistente");
      requireValid(exited + remaining === initial && replayRemaining === remaining,
        "Ledger de quantidades PAPER inconsistente");
    }
    return raw;
  }

  // J3/J5 #661: private-owner *sanitized* research observations only.
  // Never persist or upload these reports; no on-exchange fills or signals.
  const UTC_HOUR = 3600000;
  const PROSPECTIVE_EPOCH_MIN = 1600000000000;
  const PROSPECTIVE_EPOCH_MAX = 4102444800000;
  const captureFields = [
    "schema_version", "status", "capture_records_created", "candidates_captured",
    "decision_closed_end_ms", "owner_ws_sqlite_readonly_replayed",
    "local_decision_record_consistency_verified",
    "prospective_registration_independently_verified", "marketwide_top50_verified",
    "financial_backtest_approved", "approved_for_signals", "live_trading_authorized",
    "orders_sent", "network_requests", "database_mutation_statements", "systemd_modified"
  ];
  const scoreFields = [
    "schema_version", "status", "quality", "horizon_bars", "selected_observations",
    "matured_observations", "aligned_observations", "contrary_observations",
    "unchanged_observations", "gross_reference_bps_sum",
    "net_reference_after_assumed_costs_bps_sum",
    "same_side_btc_excess_reference_bps_sum",
    "assumed_total_cost_quote_units", "funding_events_hypothetical",
    "prospective_registration_verified", "intrabar_path_verified",
    "venue_fees_verified", "funding_schedule_verified",
    "out_of_sample_results_validated", "financial_backtest_approved",
    "marketwide_top50_verified", "approved_for_signals", "live_trading_authorized",
    "orders_sent", "network_requests", "database_accessed",
    "database_mutation_statements", "systemd_modified",
    "owner_local_decision_file_verified", "decision_closed_end_ms",
    "future_closed_end_ms", "owner_ws_sqlite_readonly_replayed",
    "prospective_registration_independently_verified"
  ];
  function exactKeys(raw, fields) {
    requireValid(raw && typeof raw === "object" && !Array.isArray(raw) &&
      Object.keys(raw).length === fields.length &&
      fields.every(field => Object.hasOwn(raw, field)),
      "Relatório prospectivo contém campos desconhecidos ou incompletos");
  }
  function hourlyUtc(value) {
    return Number.isSafeInteger(value) &&
      value >= PROSPECTIVE_EPOCH_MIN && value < PROSPECTIVE_EPOCH_MAX &&
      value % UTC_HOUR === 0 && value <= Date.now() + 300000;
  }
  function boundedCount(value, max) {
    return Number.isSafeInteger(value) && value >= 0 && value <= max;
  }
  function validateProspectiveCapture(raw) {
    exactKeys(raw, captureFields);
    requireValid(raw.schema_version === "j2-ws-owner-ledger-status-v1" &&
      raw.status === "owner_local_decision_captured_not_independent_attestation" &&
      raw.capture_records_created === 1 &&
      boundedCount(raw.candidates_captured, 10) &&
      hourlyUtc(raw.decision_closed_end_ms) &&
      raw.owner_ws_sqlite_readonly_replayed === true &&
      raw.local_decision_record_consistency_verified === true &&
      ["prospective_registration_independently_verified", "marketwide_top50_verified",
       "financial_backtest_approved", "approved_for_signals", "live_trading_authorized",
       "orders_sent", "systemd_modified"].every(x => raw[x] === false) &&
      raw.network_requests === 0 && raw.database_mutation_statements === 0,
      "Captura prospectiva inválida ou sem prova local");
    return raw;
  }
  function validateProspectiveScore(raw, capture) {
    const decision = validateProspectiveCapture(capture);
    exactKeys(raw, scoreFields);
    const scored = raw.status === "ex_post_reference_marks_scored_not_a_backtest";
    const noCandidates = raw.status === "no_observations_selected";
    const decimal = v => typeof v === "string" &&
      /^-?(?:0|[1-9][0-9]{0,299})(?:[.][0-9]{1,300})?$/.test(v);
    requireValid(raw.schema_version === "j3-ws-watchlist-forward-reference-v1" &&
      (scored || noCandidates) &&
      raw.quality === "ex_post_closed_mark_cost_assumptions_not_fills" &&
      [1, 4, 8].includes(raw.horizon_bars) &&
      raw.selected_observations === decision.candidates_captured &&
      boundedCount(raw.matured_observations, 10) &&
      raw.decision_closed_end_ms === decision.decision_closed_end_ms &&
      hourlyUtc(raw.future_closed_end_ms) &&
      raw.future_closed_end_ms === raw.decision_closed_end_ms +
        raw.horizon_bars * UTC_HOUR &&
      raw.owner_local_decision_file_verified === true &&
      raw.owner_ws_sqlite_readonly_replayed === true &&
      raw.database_accessed === true &&
      ["prospective_registration_verified", "intrabar_path_verified",
       "venue_fees_verified", "funding_schedule_verified",
       "out_of_sample_results_validated", "financial_backtest_approved",
       "marketwide_top50_verified", "approved_for_signals",
       "live_trading_authorized", "orders_sent", "systemd_modified",
       "prospective_registration_independently_verified"].every(x => raw[x] === false) &&
      raw.network_requests === 0 && raw.database_mutation_statements === 0 &&
      boundedCount(raw.funding_events_hypothetical, 100),
      "Resultado J3 inconsistente com a captura ou com flags de segurança");
    if (noCandidates) {
      requireValid(raw.selected_observations === 0 &&
        raw.matured_observations === 0 && raw.aligned_observations === 0 &&
        raw.contrary_observations === 0 && raw.unchanged_observations === 0 &&
        ["gross_reference_bps_sum", "net_reference_after_assumed_costs_bps_sum",
         "same_side_btc_excess_reference_bps_sum",
         "assumed_total_cost_quote_units"].every(key => raw[key] === null) &&
        raw.funding_events_hypothetical === 0,
        "Ausência de oportunidades não pode gerar PnL");
    } else {
      requireValid(raw.selected_observations > 0 &&
        raw.matured_observations === raw.selected_observations &&
        ["aligned_observations", "contrary_observations",
         "unchanged_observations"].every(k => boundedCount(raw[k], 10)) &&
        raw.aligned_observations + raw.contrary_observations +
          raw.unchanged_observations === raw.matured_observations &&
        ["gross_reference_bps_sum", "net_reference_after_assumed_costs_bps_sum",
         "same_side_btc_excess_reference_bps_sum",
         "assumed_total_cost_quote_units"].every(k => decimal(raw[k])),
        "Métricas J3 ausentes ou inconsistentes");
    }
    return raw;
  }

  const publicApi = Object.freeze({
    SCALE, BPS, format, fixed, percent, settings, emptyState,
    openPosition, partialExit, closeRunner, grossEntryExposureCents,
    grossMarkPnlCents, grossHypotheticalMarginImpactBps,
    applyAutoPaperStep, replayAutoPaperMarks, validateState,
    validateProspectiveCapture, validateProspectiveScore
  });
  global.CIAEngine = publicApi;
  if (typeof module === "object" && module && module.exports) module.exports = publicApi;
})(typeof globalThis !== "undefined" ? globalThis : this);
