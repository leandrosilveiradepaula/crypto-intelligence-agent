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
      let exited = 0n;
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
        exited += BigInt(event.units);
      }
      requireValid(exited + remaining === initial,
        "Ledger de quantidades PAPER inconsistente");
    }
    return raw;
  }
  const publicApi = Object.freeze({
    SCALE, BPS, format, fixed, percent, settings, emptyState,
    openPosition, partialExit, closeRunner, grossEntryExposureCents,
    grossMarkPnlCents, validateState
  });
  global.CIAEngine = publicApi;
  if (typeof module === "object" && module && module.exports) module.exports = publicApi;
})(typeof globalThis !== "undefined" ? globalThis : this);
