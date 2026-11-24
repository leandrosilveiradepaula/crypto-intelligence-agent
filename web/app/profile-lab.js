/* D487: user-controlled PAPER parameters, with owner-only localhost saving.
   No direct venue access, websocket, orders or browser-side trading engine. */
(function () {
"use strict";
const $ = id => document.getElementById(id);
const RESEARCH_INT = ["ema_period","atr_period","extrema_period",
  "quote_volume_period","compression_bars","baseline_bars","cooldown_bars"];
const RESEARCH_DEC = ["max_atr_ratio","min_quote_volume_ratio"];
let snapshot = null, edited = false;
let historyCount = null, historyOffset = 50, loadedHistory = [];
let previewFunnel = null, previewFilter = "historical_candidate";
const status = (msg, error=false) => {
  $("status").textContent = msg;
  $("status").dataset.error = error ? "true" : "false";
};
const trim = value => String(value).trim().replace(",", ".");
function numeric(id, maximum=100000) {
  const v = trim($(id).value);
  if (!/^(?:0|[1-9]\d*)(?:\.\d{1,8})?$/.test(v) ||
      !Number.isFinite(Number(v)) || Number(v) > maximum) {
    throw new Error("Informe um número válido em " + id);
  }
  return v;
}
function integer(id, maximum, min=0) {
  const v = numeric(id, maximum);
  if (!/^\d+$/.test(v) || Number(v)<min) {
    throw new Error("Período inválido em " + id);
  }
  return Number(v);
}
function formatted(v) {
  const x = Number(v);
  if (!Number.isFinite(x)) throw new Error("Número inválido");
  return x.toFixed(8).replace(/0+$/,"").replace(/\.$/,"");
}
function priceBpsFromMarginRoi(roi, leverage) {
  return formatted(Number(roi) * 100 / leverage);
}
function marginRoiFromPriceBps(bps, leverage) {
  return formatted(Number(bps) * leverage / 100);
}
function customDefaults(cross) {
  return {ema:cross.map(period=>({enabled:true,period})),
    sma:cross.map(period=>({enabled:false,period})),
    pivot_supertrend:{enabled:false,pivot_period:2,atr_period:10,atr_factor:"3"},
    bollinger:{enabled:false,period:20,deviations:"2",mode:"breakout"},
    rsi:{enabled:false,period:14,long_min:50,long_max:70}};
}
function refreshCustom() {
  $("custom-indicators").hidden = $("r-entry_mode").value!=="indicator_combo";
  const active = [];
  for (const family of ["ema","sma"]) {
    for (let i=0;i<3;i++) {
      const on=$("ci-"+family+"-"+i+"-enabled").checked;
      const field=$("ci-"+family+"-"+i+"-period");
      field.disabled=!on;
      if (on) active.push(family.toUpperCase()+" "+field.value);
    }
  }
  const p=$("ci-pivot-enabled").checked;
  for (const id of ["ci-pivot-period","ci-pivot-atr","ci-pivot-factor"]) $(id).disabled=!p;
  if (p) active.push("Pivot SuperTrend");
  const bb=$("ci-bb-enabled").checked;
  for (const id of ["ci-bb-period","ci-bb-deviations","ci-bb-mode"]) $(id).disabled=!bb;
  if (bb) active.push("Bollinger "+$("ci-bb-period").value+"/"+$("ci-bb-deviations").value);
  const rsi=$("ci-rsi-enabled").checked;
  for (const id of ["ci-rsi-period","ci-rsi-min","ci-rsi-max"]) $(id).disabled=!rsi;
  if (rsi) active.push("RSI "+$("ci-rsi-period").value);
  $("custom-summary").textContent=active.length ?
    "Ativos: "+active.join(" + ")+". Mudanças valem após salvar e iniciar nova sessão PAPER." :
    "Todos desligados: não haverá novas entradas por este modo. Posições existentes continuam acompanhadas.";
}
function fillCustom(profile) {
  for (const family of ["ema","sma"]) {
    profile[family].forEach((row,i)=>{
      $("ci-"+family+"-"+i+"-enabled").checked=row.enabled===true;
      $("ci-"+family+"-"+i+"-period").value=row.period;
    });
  }
  const p=profile.pivot_supertrend;
  $("ci-pivot-enabled").checked=p.enabled===true;
  $("ci-pivot-period").value=p.pivot_period;
  $("ci-pivot-atr").value=p.atr_period;
  $("ci-pivot-factor").value=p.atr_factor;
  const bb=profile.bollinger || {enabled:false,period:20,deviations:"2",mode:"breakout"};
  $("ci-bb-enabled").checked=bb.enabled===true;
  $("ci-bb-period").value=bb.period;
  $("ci-bb-deviations").value=bb.deviations;
  $("ci-bb-mode").value=bb.mode;
  const rsi=profile.rsi || {enabled:false,period:14,long_min:50,long_max:70};
  $("ci-rsi-enabled").checked=rsi.enabled===true;
  $("ci-rsi-period").value=rsi.period;
  $("ci-rsi-min").value=rsi.long_min;
  $("ci-rsi-max").value=rsi.long_max;
  refreshCustom();
}
function collectCustom() {
  const result={};
  for (const family of ["ema","sma"]) {
    const rows=[0,1,2].map(i=>({
      enabled:$("ci-"+family+"-"+i+"-enabled").checked,
      period:integer("ci-"+family+"-"+i+"-period",120,2),
    }));
    const active=rows.filter(r=>r.enabled).map(r=>r.period);
    if (active.some((v,i)=>i>0 && active[i-1]>=v)) {
      throw new Error("Os períodos "+family.toUpperCase()+" ativos devem ser crescentes.");
    }
    result[family]=rows;
  }
  const factor=numeric("ci-pivot-factor",100);
  if (Number(factor)<0.1 || (factor.split(".")[1]||"").length>6) {
    throw new Error("Fator ATR deve estar entre 0,1 e 100, com até 6 casas decimais.");
  }
  result.pivot_supertrend={
    enabled:$("ci-pivot-enabled").checked,
    pivot_period:integer("ci-pivot-period",50,1),
    atr_period:integer("ci-pivot-atr",120,1),
    atr_factor:factor,
  };
  const dev=numeric("ci-bb-deviations",10);
  const mode=$("ci-bb-mode").value;
  if (Number(dev)<0.1 || (dev.split(".")[1]||"").length>6 || !["breakout","reentry"].includes(mode)) {
    throw new Error("Bollinger: multiplicador entre 0,1 e 10, até 6 casas decimais, e regra válida.");
  }
  result.bollinger={enabled:$("ci-bb-enabled").checked,period:integer("ci-bb-period",120,2),deviations:dev,mode};
  const lower=integer("ci-rsi-min",99,50), upper=integer("ci-rsi-max",100,51);
  if (lower>=upper) throw new Error("RSI: limite inferior deve ser menor que o superior.");
  result.rsi={enabled:$("ci-rsi-enabled").checked,period:integer("ci-rsi-period",120,2),long_min:lower,long_max:upper};
  return result;
}
function fill(model) {
  RESEARCH_INT.forEach(k => $("r-"+k).value = model.research[k]);
  RESEARCH_DEC.forEach(k => $("r-"+k).value = model.research[k]);
  $("r-entry_mode").value = model.research.entry_mode || "breakout";
  const cross = model.research.ema_cross_periods || [10,30,60];
  ["fast","mid","trend"].forEach((k,i) => $("r-ma_"+k).value = cross[i]);
  fillCustom(model.research.indicators || customDefaults(cross));
  $("r-experimental_paper_relaxation").checked =
    model.research.experimental_paper_relaxation === true;
  $("p-margin_quote").value = model.paper.margin_quote;
  $("p-leverage").value = model.paper.leverage;
  $("p-stop_roi").value = marginRoiFromPriceBps(
    model.paper.stop_distance_bps, model.paper.leverage);
  $("p-target1_roi").value = marginRoiFromPriceBps(
    model.paper.target_distances_bps[0], model.paper.leverage);
  $("p-target2_roi").value = marginRoiFromPriceBps(
    model.paper.target_distances_bps[1], model.paper.leverage);
  $("p-partial1").value = model.paper.tranches[0].percent;
  $("p-partial2").value = model.paper.tranches[1].percent;
  $("p-runner_floor_percent").value = model.paper.runner_floor_percent;
  edited = false;
}
function collect() {
  const research = {};
  RESEARCH_INT.forEach(k => {
    research[k] = integer("r-"+k,500, k==="cooldown_bars" ? 0 : 2);
  });
  RESEARCH_DEC.forEach(k => research[k] = numeric("r-"+k,100));
  research.experimental_paper_relaxation =
    $("r-experimental_paper_relaxation").checked;
  research.entry_mode = $("r-entry_mode").value;
  if (!["breakout","ema_cross","indicator_combo"].includes(research.entry_mode)) {
    throw new Error("Selecione uma regra de entrada válida.");
  }
  research.ema_cross_periods = ["fast","mid","trend"].map(
    k => integer("r-ma_"+k,120,2));
  const [fast,mid,trend] = research.ema_cross_periods;
  if (!(fast < mid && mid < trend)) {
    throw new Error("As EMAs devem ter períodos crescentes.");
  }
  if (research.entry_mode==="indicator_combo") {
    research.indicators=collectCustom();
  }
  const leverage=integer("p-leverage",100,1);
  const t1=numeric("p-target1_roi",5000);
  const t2=numeric("p-target2_roi",5000);
  const stop=numeric("p-stop_roi",100);
  const p1=numeric("p-partial1",100);
  const p2=numeric("p-partial2",100);
  const runner=numeric("p-runner_floor_percent",100);
  if (!(Number(t1)>0 && Number(t2)>Number(t1) && Number(stop)>0)) {
    throw new Error("Os alvos devem ser positivos e crescentes.");
  }
  if (!(Number(p1)>0 && Number(p2)>0 && Number(p1)+Number(p2)+Number(runner)<=100)) {
    throw new Error("As duas parciais + runner não podem ultrapassar 100%.");
  }
  if (!research.experimental_paper_relaxation &&
      (Number(research.max_atr_ratio)>1 ||
       Number(research.min_quote_volume_ratio)<1)) {
    throw new Error("Ative o perfil experimental para usar ATR >1 ou volume <1.");
  }
  if (research.experimental_paper_relaxation &&
      (Number(research.max_atr_ratio)>2 ||
       Number(research.min_quote_volume_ratio)<.5)) {
    throw new Error("Perfil experimental admite ATR até 2 e volume desde 0,5.");
  }
  const paper = {
    leverage, margin_quote:numeric("p-margin_quote",10000),
    stop_distance_bps:priceBpsFromMarginRoi(stop,leverage),
    target_distances_bps:[
      priceBpsFromMarginRoi(t1,leverage),
      priceBpsFromMarginRoi(t2,leverage),
    ],
    tranches:[
      {basis:"INITIAL_POSITION",percent:p1},
      {basis:"INITIAL_POSITION",percent:p2},
    ],
    runner_floor_percent:runner,
  };
  return {research,paper};
}
async function getJson(url, options) {
  const response = await fetch(url, {
    credentials:"same-origin", cache:"no-store", ...options,
  });
  const value = await response.json();
  if (!response.ok) {
    throw new Error(value.status || "O servidor local recusou a solicitação.");
  }
  return value;
}
async function load() {
  try {
    snapshot = await getJson("/api/profile");
    fill(snapshot);
    $("save").disabled = false;
    $("preview").disabled = false;
    $("compare-history").disabled = false;
    status("Perfil PAPER carregado. Você pode alterar os valores e salvar. Nenhuma posição será modificada.");
    await preview();
  } catch (error) {
    status("Perfil indisponível. Abra pelo servidor privado da VPS e verifique as permissões: "+error.message,true);
  }
}
async function save() {
  if (!snapshot) return;
  $("save").disabled = true;
  try {
    const edits = collect();
    const result = await getJson("/api/profile",{
      method:"POST",
      headers:{"Content-Type":"application/json","X-CIA-Paper-Profile":"1"},
      body: JSON.stringify({revision:snapshot.revision,edits}),
    });
    snapshot = result;
    fill(snapshot);
    edited = false;
    status("Perfil salvo na VPS. Será lido pelo motor na PRÓXIMA sessão PAPER; as posições atuais permanecem iguais.");
    await preview();
  } catch(error) {
    status("Não foi possível salvar: "+error.message+
      ". Confirme os parâmetros ou recarregue o perfil.",true);
  } finally {
    $("save").disabled = false;
  }
}
async function loadPaperSession() {
  try {
    const d=await getJson("/api/paper-session");
    $("paper-session-details").textContent =
      d.open_position_count+" em aberto · "+d.closed_position_count+
      " encerrada(s) · "+(d.intent_count ?? d.intents.length)+
      " intenção(ões) PAPER (mais recentes: "+d.intents.length+
      "). Ordens reais: NÃO.";
    showPaperScorecard(d.paper_scorecard);
    const container=$("paper-session-rows");
    container.replaceChildren();
    for (const intent of d.intents) {
      const row=document.createElement("div");
      row.className="row";
      const a=document.createElement("strong");
      a.textContent=intent.symbol+" · "+intent.side;
      const b=document.createElement("span");
      b.className="muted";
      b.textContent=intent.status+" · preenchido "+intent.filled_units+
        " / "+intent.requested_units+" (PAPER)";
      row.append(a,b);
      container.append(row);
    }
    showPositions("paper-position-rows",d.positions || [],"Nenhuma posição automática preenchida.");
    if (historyCount !== d.position_count) {
      historyCount = d.position_count;
      historyOffset = 50;
      loadedHistory = [];
      $("history-rows").replaceChildren();
    }
    $("history-next").disabled = !(d.position_count > historyOffset);
  } catch(e) {
    $("paper-session-details").textContent =
      "Diário da sessão ainda indisponível. Não presumir posições ou fills.";
    $("paper-position-rows").textContent="Estado não disponível.";
    $("paper-scorecard-metrics").replaceChildren();
    $("paper-scorecard-note").textContent="Desempenho indisponível: diário PAPER não confirmado.";
  }
  try {
    const op=await getJson("/api/paper-operator");
    $("paper-operator-status").textContent =
      "Operador local: "+op.status+" · sessões: "+op.cycle_attempts+
      ". Status recente, mas cobertura de stop e execução na corretora NÃO são garantidas.";
  } catch(e) {
    $("paper-operator-status").textContent =
      "Operador sem confirmação recente. Não presumir stops ativos.";
  }
  try {
    const d=await getJson("/api/paper-demo");
    showPositions("paper-demo-rows",d.positions,
      "Nenhuma posição demonstrativa registrada.");
  } catch(e) {
    $("paper-demo-rows").textContent="Diário demonstrativo indisponível.";
  }
}

async function loadMoreHistory() {
  const button = $("history-next");
  button.disabled = true;
  try {
    const page = await getJson("/api/paper-history?offset="+historyOffset+"&limit=25");
    if (page.schema_version !== "d502-owner-paper-history-page-v1" ||
        page.orders_sent !== false || !Array.isArray(page.positions)) {
      throw new Error("Página de histórico não validada.");
    }
    historyOffset += page.positions.length;
    // Open/partial positions are already pinned at the top of the live
    // list, including positions older than the latest 50. Historical
    // pagination displays CLOSED operations only, without duplicating them.
    loadedHistory = loadedHistory.concat(
      page.positions.filter(p => p.status === "CLOSED")
    );
    showPositions("history-rows",loadedHistory,"Sem operações encerradas mais antigas.");
    button.disabled = !page.more_available;
  } catch(error) {
    $("history-rows").textContent="Histórico indisponível: "+error.message;
    button.disabled = false;
  }
}

function showPaperScorecard(d) {
  const root=$("paper-scorecard-metrics");
  const note=$("paper-scorecard-note");
  root.replaceChildren();
  if (!d || d.schema_version!=="d511-observed-paper-closed-scorecard-v1" ||
      d.orders_sent!==false || d.real_account_pnl_available!==false ||
      d.exchange_execution_verified!==false || d.funding_settlement_verified!==false) {
    note.textContent="Resumo de desempenho indisponível ou não validado.";
    return;
  }
  const value=v=>v===null || v===undefined ? "Sem dados" : String(v);
  decisionMetric(root,"Encerradas precificadas",d.sample_closed_priced+
    " / "+d.total_closed_positions_in_journal);
  decisionMetric(root,"Vitórias / derrotas",d.sample_winning_closed+
    " / "+d.sample_losing_closed);
  decisionMetric(root,"Resultado condicional (USDT)",value(
    d.conditional_closed_net_before_funding_quote));
  decisionMetric(root,"Recuo entre fechamentos (USDT)",value(
    d.max_drawdown_closed_trade_sequence_quote));
  const incomplete = !d.window_covers_every_closed_position ||
    !d.priced_covers_every_closed_position;
  note.textContent="Amostra: "+d.sample_closed_positions+
    " encerradas visíveis; "+d.sample_closed_unpriced+
    " sem preço verificável. Taxa de acerto da amostra: "+
    value(d.priced_closed_win_rate_percent)+"%. "+
    (incomplete?"Histórico incompleto ou sem preços; métricas PARCIAIS. ":"")+
    "Valores hipotéticos antes de funding; sem execução na corretora, "+
    "sem drawdown intrabar e sem validação fora da amostra.";
}

function showPositions(id,positions,emptyText) {
  const root=$(id);
  root.replaceChildren();
  if (!positions || !positions.length) {
    root.textContent=emptyText;
    return;
  }
  const statusLabel={OPEN:"Aberta",PARTIAL:"Saída parcial",CLOSED:"Encerrada"};
  const closureLabel={STOP:"Stop PAPER",TARGETS:"Alvos PAPER",OTHER:"Outras saídas PAPER"};
  for (const p of positions) {
    const card=document.createElement("div");
    card.className="position-card";
    const symbol=document.createElement("strong");
    symbol.textContent=p.symbol+" · "+p.side+" · "+
      (statusLabel[p.status] || "PAPER");
    const detail=document.createElement("div");
    detail.className="muted";
    detail.textContent="Saldo: "+p.remaining_units+
      " / "+p.initial_units+" · encerrado: "+p.filled_exit_units;
    const levels=document.createElement("div");
    levels.className="muted";
    const marginTerms=(p.requested_margin_quote===null ||
      p.leverage_at_intent===null) ?
      " · Margem/alavancagem não informadas nesta demonstração" :
      " · Margem: "+p.requested_margin_quote+" USDT · "+
      p.leverage_at_intent+"x";
    levels.textContent="Stop (mark): "+p.stop_mark_price+
      " · Alvos: "+(p.target_prices || []).join(" / ")+marginTerms;
    const summary=document.createElement("div");
    summary.className="muted";
    if (p.closure_reason && p.closure_reason!=="NONE") {
      summary.textContent="Motivo do fechamento: "+
        (closureLabel[p.closure_reason] || "saída PAPER");
    }
    const pnl=document.createElement("div");
    pnl.className="muted";
    if (p.conditional_result_before_funding_quote!==null &&
        p.conditional_result_before_funding_quote!==undefined) {
      pnl.textContent="Resultado PAPER estimado antes de funding: "+
        p.conditional_result_before_funding_quote+" USDT"+
        " (preços e custos hipotéticos; não é resultado na corretora)";
    } else {
      pnl.textContent="Resultado financeiro não disponível para esta demonstração.";
    }
    card.append(symbol,detail,levels,summary,pnl);
    root.append(card);
  }
}

function decisionMetric(root, title, value) {
  const box = document.createElement("div");
  box.className = "decision-metric";
  const strong = document.createElement("strong");
  strong.textContent = String(value);
  const caption = document.createElement("span");
  caption.textContent = title;
  box.append(strong, caption);
  root.append(box);
}

async function loadDecisionFunnel() {
  const details = $("decision-current");
  const steps = $("decision-steps");
  const reasons = $("decision-reasons");
  try {
    const d = await getJson("/api/paper-decision-funnel");
    if (d.schema_version !== "d509-paper-decision-funnel-v1" ||
        d.orders_sent !== false || d.exchange_orders_verified !== false ||
        d.source !== "previous_completed_public_lease_only") {
      throw new Error("Diagnóstico PAPER não validado.");
    }
    const messages = {
      last_lease_stale:"Último ciclo antigo; não representa o estado atual da conexão.",
      last_lease_abstained:"Ciclo anterior não completou a observação pública.",
      confirmed_n50_cohort_not_proven:"Não foi comprovada a coorte completa de velas WS.",
      confirmed_cohort_not_yet_researched:"Velas observadas, mas pesquisa causal ainda não concluída.",
      no_eligible_hypothesis_after_btc_filters:"Nenhuma hipótese elegível depois da estratégia e BTC.",
      paper_position_recorded_in_lease:"O último ciclo registrou uma posição PAPER.",
      paper_open_pending_in_lease:"O último ciclo registrou uma intenção de abertura PAPER.",
      candidates_without_paper_fill:"Houve candidatos, mas não há preenchimento PAPER comprovado neste resumo."
    };
    details.textContent = (messages[d.status] || "Resumo da última sessão PAPER.")+
      " Último ciclo: "+new Date(d.last_lease_at_ms).toLocaleString("pt-BR")+
      ". Fonte: diário de pesquisa WS público; sem proteção nativa nem ordem real.";
    steps.replaceChildren();
    const c = d.counters || {}, e = d.paper_event_counts || {};
    const number = v => Number.isInteger(v) && v >= 0 ? v : "—";
    decisionMetric(steps, "Velas fechadas por WS", number(c.accepted_confirmed_close_callbacks));
    decisionMetric(steps, "Pesquisas de coorte", number(c.paper_cohort_researched_count));
    decisionMetric(steps, "Candidatos relativos ao BTC", number(c.paper_relative_btc_hypotheses));
    decisionMetric(steps, "Posições PAPER criadas", number(e.paper_position_created));
    const names = {
      configured_margin_does_not_fit_contract_lot:"Margem insuficiente para lote",
      public_contract_refresh_pending:"Aguardando contrato público atualizado",
      paper_entry_replay_or_validation_blocked:"Entrada bloqueada pela validação",
      paper_open_expired_cancelled:"Intenção PAPER expirada",
      paper_open_pending_armed:"Intenções PAPER armadas",
      kline_confirmed_events_appended:"Velas WS persistidas"
    };
    const obstacles = Object.entries(names).map(([key,label]) => {
      const count = key in e ? e[key] : c[key];
      return Number.isInteger(count) && count > 0 ? label+": "+count : null;
    }).filter(Boolean);
    reasons.textContent = obstacles.length ? obstacles.join(" · ") :
      "Nenhuma causa individual de bloqueio registrada neste resumo. Nem todo candidato histórico gera uma entrada.";
  } catch (error) {
    details.textContent = "Ainda não há diagnóstico válido de um ciclo WS concluído. O operador pode estar executando a primeira sessão; não presumir falha nem entrada.";
    steps.replaceChildren();
    reasons.textContent = "";
  }
}

function showHistoricalDecisions() {
  const root = $("preview-rows");
  root.replaceChildren();
  document.querySelectorAll("[data-decision-filter]").forEach(node => {
    node.setAttribute("aria-pressed",
      node.dataset.decisionFilter === previewFilter ? "true" : "false");
  });
  if (!previewFunnel) return;
  const labels = {
    historical_candidate:"Candidato histórico · alinhado ao BTC",
    btc_relative_not_aligned:"Hipótese técnica · não alinhada ao BTC",
    no_technical_hypothesis:"Sem hipótese técnica nesta vela",
    btc_reference:"BTC · referência para comparação"
  };
  const selected = previewFunnel.decisions.filter(x =>
    previewFilter === "all" || x.decision === previewFilter);
  if (!selected.length) {
    root.textContent = "Nenhum ativo nesta categoria.";
    return;
  }
  for (const item of selected) {
    const card = document.createElement("div");
    card.className = "row";
    const name = document.createElement("strong");
    name.textContent = item.symbol+
      (item.historical_side ? " · "+item.historical_side : "");
    const detail = document.createElement("span");
    detail.className = "muted";
    detail.textContent = (labels[item.decision] || "Sem classificação")+
      " · BTC relativo: "+item.btc_relative_percent+" p.p.";
    card.append(name,detail);
    root.append(card);
  }
}

async function preview() {
  if (!snapshot) return;
  if (edited) {
    status("Salve as alterações antes de pesquisar com o novo perfil.",true);
    return;
  }
  $("preview").disabled = true;
  $("preview-details").textContent = "Lendo o histórico REAL já armazenado na VPS…";
  $("preview-rows").replaceChildren();
  $("preview-funnel").replaceChildren();
  previewFunnel = null;
  try {
    const result = await getJson("/api/research-preview");
    if (result.status==="more_closed_candles_required") {
      $("preview-details").textContent =
        "A configuração exige pelo menos "+result.needed_candles+
        " candles completos. Este histórico tem "+result.available_candles+
        ". Nenhum sinal foi fabricado.";
    } else if (result.status==="historical_data_not_available") {
      $("preview-details").textContent =
        "Ainda não há histórico armazenado para esta pesquisa.";
    } else {
      $("preview-details").textContent =
        "Histórico público Bybit: "+result.symbols+" ativos × "+
        result.closed_bars_per_symbol+" velas de 1 hora. "+
        result.raw_hypotheses+" hipóteses técnicas, "+
        result.candidate_count+" também alinhadas ao BTC. "+
        "Pesquisa histórica; NÃO são entradas PAPER nem sinais WS.";
      const funnel = result.decision_funnel;
      if (funnel && funnel.schema_version === "d509-rest-research-funnel-v1" &&
          funnel.member_count === result.symbols &&
          Array.isArray(funnel.decisions) &&
          funnel.decisions.length === result.symbols) {
        previewFunnel = funnel;
        const counts = funnel.reason_counts;
        const root = $("preview-funnel");
        decisionMetric(root, "Sem hipótese técnica", counts.no_technical_hypothesis);
        decisionMetric(root, "Excluídos pelo BTC", counts.btc_relative_not_aligned);
        decisionMetric(root, "Candidatos históricos", counts.historical_candidate);
        decisionMetric(root, "Ativos analisados", funnel.member_count);
        showHistoricalDecisions();
      } else {
        $("preview-rows").textContent =
          "Sem detalhamento individual para este arquivo histórico.";
      }
    }
  } catch(error) {
    $("preview-details").textContent="Pesquisa indisponível: "+error.message;
  } finally {
    $("preview").disabled = false;
  }
}
async function compareHistoricalStrategies() {
  const button=$("compare-history"), summary=$("compare-status"), root=$("compare-results");
  if (!snapshot) return;
  root.replaceChildren();
  button.disabled=true;
  try {
    const periods=["fast","mid","trend"].map(k=>integer("r-ma_"+k,120,2));
    if (!(periods[0]<periods[1] && periods[1]<periods[2])) {
      throw new Error("Os períodos das EMAs devem ser crescentes.");
    }
    summary.textContent="Lendo os arquivos locais e comparando as mesmas decisões horárias…";
    const retro=$("compare-retro").checked;
    const horizon=integer("compare-horizon",12,1);
    const resolution=$("compare-resolution").value;
    if (!["1h","5m"].includes(resolution)) throw new Error("Resolução inválida.");
    const d=await getJson("/api/strategy-comparison?fast="+periods[0]+
      "&mid="+periods[1]+"&trend="+periods[2]+(retro?"&retro=1":"")+"&horizon="+horizon+"&resolution="+resolution);
    if (d.status==="retrospective_warmup_not_available") {
      summary.textContent="Histórico complementar ainda não disponível. Use o histórico original ou solicite a coleta complementar.";
      return;
    }
    if (d.status==="intrahour_supplement_not_available") {
      summary.textContent="Histórico de 5 minutos ainda não coletado. Escolha 1 hora ou solicite a coleta complementar.";
      return;
    }
    if (retro!==d.retrospective_warmup_requested) {
      throw new Error("A origem do histórico não corresponde à seleção.");
    }
    if (d.schema_version!=="d512-archived-rest-strategy-comparison-v1" ||
        d.orders_sent!==false || d.financial_backtest_approved!==false ||
        d.out_of_sample_results_validated!==false || d.exchange_fills_verified!==false ||
        d.intrabar_path_verified!==false || d.funding_settlement_verified!==false) {
      throw new Error("Resposta histórica não validada.");
    }
    const replay=d.exit_replay;
    if (!replay || replay.schema_version!=="d517-observed-ohlc-exit-scenarios-v1" ||
        replay.horizon_hours!==horizon || replay.interval!==resolution || replay.orders_sent!==false ||
        replay.financial_backtest_approved!==false || replay.intrabar_path_verified!==false ||
        replay.funding_settlement_verified!==false || replay.liquidation_verified!==false) {
      throw new Error("Cenários de saídas indisponíveis ou inválidos.");
    }
    summary.textContent=d.archive_count+" arquivos horários · "+d.paired_decision_hours+
      " decisões com observação da hora seguinte · "+d.common_eligible_symbol_hours+
      " ativos-hora elegíveis em todas as estratégias comparadas. Aquecimento: "+
      d.maximum_contiguous_hours_observed+" / "+d.required_warmup_hours+
      " velas; "+d.excluded_warmup_or_conflict_symbol_hours+" ativos-hora excluídos por dados insuficientes ou conflitantes. "+
      "Notional de referência: "+d.reference_notional_quote+" USDT; custo assumido por ciclo: "+
      d.assumed_roundtrip_cost_quote+" USDT. Sem funding confirmado."+
      (retro?" Aquecimento RETROSPECTIVO (recuperado depois): "+
        d.retrospective_warmup_symbol_hours+" ativos-hora usaram velas extras; "+
        d.retrospective_warmup_rejected_series+" séries rejeitadas. Não é prova prospectiva.":"");
    if (!d.common_eligible_symbol_hours) {
      root.textContent="Ainda não existem dados compatíveis suficientes para uma comparação. Nenhum resultado foi inventado.";
      return;
    }
    const labels={breakout:"Rompimento com filtros",ema_cross:"Cruzamento EMA "+d.ema_periods.join("/"),
      indicator_combo:"Combinação de indicadores salva",reference_long:"Referência LONG dos ativos elegíveis"};
    const modes=["breakout","ema_cross",...(d.results.indicator_combo?["indicator_combo"]:[]),"reference_long"];
    for (const k of modes) {
      const r=d.results[k], card=document.createElement("article");
      card.className="position-card";
      const title=document.createElement("strong");
      title.textContent=labels[k];
      const metrics=document.createElement("div");
      metrics.className="decision-steps";
      const show=v=>v===null?"Sem dados":Number(v).toLocaleString("pt-BR",{maximumFractionDigits:6});
      decisionMetric(metrics,"Hipóteses",r.candidates);
      decisionMetric(metrics,"Observações futuras disponíveis",r.scored_marks);
      decisionMetric(metrics,"Positivas / negativas após custos",r.positive_marks+" / "+r.negative_marks);
      decisionMetric(metrics,"Marca média antes de funding (bps)",show(r.average_mark_before_funding_bps));
      const note=document.createElement("p");
      note.className="muted";
      note.textContent="Soma condicional de marcas: "+show(r.conditional_mark_before_funding_quote)+
        " USDT (não é carteira). Sem observação futura: "+r.missing_future_marks+
        ". Toques stop: "+r.stop_range_touches+"; alvos: "+r.target_range_touches.join(" / ")+
        "; stop e alvo na mesma vela: "+r.stop_and_target_same_bar+
        ". Não inferir execução nem sequência das parciais.";
      card.append(title,metrics,note);
      const exits=replay.results[k];
      const exitTitle=document.createElement("strong");
      exitTitle.textContent="Cenários de stop e parciais · "+horizon+"h · "+resolution;
      const coverage=document.createElement("p");
      coverage.className="muted";
      coverage.textContent=exits.complete_path_count+" trajetórias completas / "+
        exits.candidate_count+" hipóteses; "+exits.missing_path_count+" sem cobertura completa. "+
        exits.ordering_sensitive_count+" resultados dependem da ordem dos extremos.";
      const cards=document.createElement("div");
      cards.className="decision-steps";
      for(const [key,label] of [["adverse_first","Extremo adverso primeiro"],["favorable_first","Extremo favorável primeiro"]]){
        const e=exits[key], section=document.createElement("div");
        section.className="position-card";
        const h=document.createElement("strong");
        h.textContent=label;
        const metrics=document.createElement("div");
        metrics.className="decision-steps";
        decisionMetric(metrics,"Soma condicional pré-funding (USDT)",show(e.conditional_before_funding_quote));
        decisionMetric(metrics,"Média por hipótese completa (bps)",show(e.average_before_funding_bps));
        decisionMetric(metrics,"Positivas / negativas",e.positive_count+" / "+e.negative_count);
        decisionMetric(metrics,"Com parcial / com stop",e.with_targets_count+" / "+e.stop_count);
        decisionMetric(metrics,"Com residual no fim",e.residual_at_horizon_count);
        decisionMetric(metrics,"Perda ≥ margem solicitada",e.loss_at_least_margin_count);
        section.append(h,metrics);
        cards.append(section);
      }
      const caution=document.createElement("p");
      caution.className="muted";
      caution.textContent="Margem de referência "+replay.requested_margin_quote+" USDT · "+
        replay.leverage_at_intent+"x. Resultados de hipóteses independentes; não são saldo, "+
        "limites garantidos de resultado, trajetória intrabar observada ou liquidação.";
      card.append(exitTitle,coverage,cards,caution);
      if (resolution==="5m") {
        const matched=replay.matched_hourly_reference?.[k];
        if (!matched || matched.complete_path_count!==exits.complete_path_count) {
          throw new Error("Comparação horária sem amostra equivalente.");
        }
        const reference=document.createElement("p");
        reference.className="muted";
        reference.textContent="Mesma amostra em 1h: "+matched.ordering_sensitive_count+
          " hipóteses sensíveis à ordem dos extremos, contra "+exits.ordering_sensitive_count+
          " em 5m. Soma pré-funding (adverso / favorável): "+
          show(matched.adverse_first.conditional_before_funding_quote)+" / "+
          show(matched.favorable_first.conditional_before_funding_quote)+" USDT.";
        card.append(reference);
      }
      root.append(card);
    }
  } catch(e) {
    summary.textContent="Comparação indisponível: "+e.message;
  } finally {
    button.disabled=false;
  }
}
let matrixPoll=null, matrixJobId=null;
function showMatrix(job) {
  const summary=$("matrix-status"),root=$("matrix-results"),button=$("matrix-start");
  if (job.schema_version!=="d522-owner-local-research-job-v1" ||
      job.orders_sent!==false || job.profile_modified!==false) {
    throw new Error("Resposta da pesquisa inválida.");
  }
  button.disabled=job.status==="running";
  if (job.status==="running") {
    summary.textContent="Pesquisa em execução: "+job.strategy_count+" estratégias / "+(job.scenario_count||job.strategy_count)+" cenários. O monitor continua disponível.";
    if (matrixJobId!==job.job_id) root.replaceChildren();
    matrixJobId=job.job_id;
    if (matrixPoll===null) matrixPoll=setInterval(refreshMatrix,3000);
    return;
  }
  if (matrixPoll!==null) {clearInterval(matrixPoll);matrixPoll=null;}
  if (job.status==="idle") {
    root.replaceChildren();
    summary.textContent="Nenhuma bateria executada neste processo.";
    return;
  }
  if (job.status==="failed") {
    root.replaceChildren();
    summary.textContent="Pesquisa indisponível. "+(job.error==="research_timeout"?
      "Tempo limite atingido.":"Confira os suplementos e o perfil salvo.");
    return;
  }
  const d=job.report;
  if (job.status!=="completed" || !d || d.schema_version!=="d520-exploratory-combination-research-v1" ||
      d.orders_sent!==false || d.profile_modified!==false || d.winner_selected!==false ||
      d.out_of_sample_results_validated!==false || d.financial_backtest_approved!==false ||
      d.funding_settlement_verified!==false || d.liquidation_verified!==false ||
      !Array.isArray(d.rows) || d.rows.length!==job.strategy_count) {
    throw new Error("Relatório exploratório inválido.");
  }
  matrixJobId=job.job_id;
  const show=v=>v===null?"Sem dados":Number(v).toLocaleString("pt-BR",{maximumFractionDigits:6});
  const grid=Array.isArray(d.stop_grid)?d.stop_grid:[];
  const stopSummary=grid.length?"stops "+grid.map(v=>show(v.stop_bps)).join(" / ")+" bps · detalhes do primeiro stop":
    "stop "+show(d.common_exit_policy.stop_distance_bps)+" bps · perda bruta no stop "+show(d.stop_gross_loss_margin_pct)+"% da margem";
  summary.textContent=d.rows.length+" estratégias / "+(d.scenario_count||d.rows.length)+" cenários · "+d.common_covered_symbol_hours+
    " oportunidades com trajetória comum · "+d.horizon_hours+"h / 5min · "+stopSummary+" (liquidação não avaliada) · corte "+
    new Date(d.as_of_ms).toLocaleString("pt-BR")+
    ". Margem "+show(d.requested_margin_quote)+" USDT · "+d.leverage_at_intent+"x · nominal "+show(d.reference_notional_quote)+" USDT"+
    (d.reference_bankroll_quote==null?"":" · banca de referência "+show(d.reference_bankroll_quote)+" USDT (sem simulação de carteira)")+
    ". Perfil lido na revisão "+job.profile_revision.slice(0,12)+
    (d.status==="no_complete_common_paths"?". Sem cobertura suficiente.":"");
  root.replaceChildren();
  if(!grid.length&&d.stop_risk){
    const risk=document.createElement("p");risk.className="muted";
    risk.textContent="Perda bruta posição integral: "+show(d.stop_risk.gross_stop_loss_quote)+" USDT"+
      (d.stop_risk.gross_stop_loss_pct_of_reference_bankroll==null?"":" · "+show(d.stop_risk.gross_stop_loss_pct_of_reference_bankroll)+"% da banca")+
      (d.stop_risk.gross_stop_reaches_initial_margin?" · Contrafactual: alcança/excede margem inicial.":"")+" · Liquidação não modelada.";
    root.append(risk);
  }
  for(const r of d.rows) {
    const card=document.createElement("article"),title=document.createElement("strong");
    card.className="position-card";
    title.textContent=r.label;
    const metrics=document.createElement("div");
    metrics.className="decision-steps";
    decisionMetric(metrics,"Sinais / completos",r.candidates+" / "+r.complete);
    if(r.rsi_veto){
      decisionMetric(metrics,"Sinais originais / vetados pelo RSI",r.rsi_veto.checked+" / "+r.rsi_veto.rejected);
      decisionMetric(metrics,"Trajetórias originais / vetadas pelo RSI",r.rsi_veto.covered_checked+" / "+r.rsi_veto.covered_rejected);
    }
    decisionMetric(metrics,"LONG / SHORT",r.long+" / "+r.short);
    decisionMetric(metrics,"Cobertura",r.coverage_pct===null?"Sem sinais":show(r.coverage_pct)+"%");
    decisionMetric(metrics,"Positivos / negativos",r.positive+" / "+r.negative);
    decisionMetric(metrics,"Soma adversa / favorável (USDT)",show(r.net_adverse)+" / "+show(r.net_favorable));
    decisionMetric(metrics,"Média adversa após custos (bps)",show(r.mean_adverse_bps));
    decisionMetric(metrics,"Custos estimados (USDT)",show(r.cost_adverse));
    decisionMetric(metrics,"Com alvo / stop",r.with_targets+" / "+r.stop_count);
    decisionMetric(metrics,"Stop antes de TP1 / na primeira hora",r.stop_before_tp1+" / "+r.stop_before_tp1_first_hour);
    decisionMetric(metrics,"Stop antes de TP1, alvo tocado depois",r.stop_before_tp1_then_later_tp1);
    decisionMetric(metrics,"Positivas com stop",r.positive_with_stop);
    decisionMetric(metrics,"Excursão adversa / favorável média, caminho inteiro (bps)",show(r.mean_full_path_mae_bps)+" / "+show(r.mean_full_path_mfe_bps));
    const note=document.createElement("p");
    note.className="muted";
    note.textContent=(r.descriptive_sample_screen_met?"Amostra atende filtro descritivo.":"Amostra abaixo do filtro descritivo.")+
      " Não é aprovação estatística. Casos sensíveis à ordem: "+r.ambiguous_count+
      ". Perdas pelo menos iguais à margem: "+r.loss_at_least_margin+".";
    card.append(title,metrics,note);
    if(grid.length){
      const heading=document.createElement("h3");heading.textContent="Comparação de stops (mesmos sinais e trajetórias)";card.append(heading);
      for(const variant of grid){
        const v=variant.rows.find(x=>x.name===r.name);
        if(!v||v.candidates!==r.candidates||v.complete!==r.complete) throw new Error("Cobertura inconsistente entre stops.");
        const line=document.createElement("div");line.className="decision-steps";
        decisionMetric(line,"Stop / perda bruta teórica da margem",show(variant.stop_bps)+" bps / "+show(variant.gross_loss_margin_pct)+"%");
        if(variant.gross_stop_loss_quote!=null){
          decisionMetric(line,"Perda bruta posição integral (USDT)",show(variant.gross_stop_loss_quote));
          if(variant.gross_stop_loss_pct_of_reference_bankroll!=null) decisionMetric(line,"Perda bruta / banca de referência",show(variant.gross_stop_loss_pct_of_reference_bankroll)+"%");
          if(variant.gross_stop_reaches_initial_margin) decisionMetric(line,"Risco","Contrafactual: stop alcança/excede margem inicial; liquidação não modelada.");
        }
        decisionMetric(line,"Resultado adverso / favorável (USDT)",show(v.net_adverse)+" / "+show(v.net_favorable));
        decisionMetric(line,"Stops antes de TP1 / recuperações posteriores",v.stop_before_tp1+" / "+v.stop_before_tp1_then_later_tp1);
        decisionMetric(line,"Positivas / negativas / perda ≥ margem",v.positive+" / "+v.negative+" / "+v.loss_at_least_margin);
        card.append(line);
      }
    }
    for (const x of r.entry_examples || []) {
      const item=document.createElement("p");
      item.className="muted";
      item.textContent=x.symbol+" · "+x.side+" · "+new Date(x.decision_end_ms).toLocaleString("pt-BR")+
        " · FR "+show(x.relative_strength_bps)+" bps · abertura seguinte "+x.next_open_reference_ex_post;
      card.append(item);
    }
    root.append(card);
  }
}
async function refreshMatrix(){
  try {showMatrix(await getJson("/api/combination-research"));}
  catch(e){
    $("matrix-status").textContent="Pesquisa indisponível: "+e.message;
    $("matrix-start").disabled=false;
    if(matrixPoll!==null){clearInterval(matrixPoll);matrixPoll=null;}
  }
}
async function startMatrix(){
  $("matrix-start").disabled=true;
  try{
    const horizon=integer("matrix-horizon",12,1);
    const request={horizon_hours:horizon,preset:$("matrix-preset").value};
    for(const [id,key] of [["matrix-bankroll","research_bankroll_quote"],["matrix-margin","research_margin_quote"]]){
      const value=$(id).value.trim();if(value) request[key]=value;
    }
    if($("matrix-leverage").value.trim()) request.research_leverage=integer("matrix-leverage",200,1);
    if ($("matrix-grid-enabled").checked){
      const words=$("matrix-grid").value.trim().split(/\s+/);
      const stops=words.map(Number);
      if(words.length<2||words.length>8||words.some((w,i)=>!/^\d{1,4}$/.test(w)||stops[i]<1||stops[i]>1000||(i>0&&stops[i]<=stops[i-1])))
        throw new Error("Informe 2 a 8 stops inteiros de 1 a 1000 bps em ordem crescente.");
      request.stop_grid_bps=stops;
    } else if ($("matrix-stop").value.trim()) request.stop_bps=integer("matrix-stop",1000,1);
    const response=await fetch("/api/combination-research",{
      method:"POST",headers:{"Content-Type":"application/json","X-CIA-Paper-Profile":"1"},
      body:JSON.stringify(request)
    });
    if(response.status===409){await refreshMatrix();return;}
    if(response.status!==202)throw new Error("Solicitação não aceita.");
    showMatrix(await response.json());
  }catch(e){
    $("matrix-status").textContent="Pesquisa indisponível: "+e.message;
    $("matrix-start").disabled=false;
  }
}
document.addEventListener("DOMContentLoaded",()=>{
  $("save").addEventListener("click",save);
  $("preview").addEventListener("click",preview);
  $("compare-history").addEventListener("click",compareHistoricalStrategies);
  const updateGrid=()=>{const on=$("matrix-grid-enabled").checked;$("matrix-grid").disabled=!on;$("matrix-stop").disabled=on;};
  $("matrix-grid-enabled").addEventListener("change",updateGrid);updateGrid();
  $("matrix-start").addEventListener("click",startMatrix);
  $("matrix-refresh").addEventListener("click",refreshMatrix);
  refreshMatrix();
  $("history-next").addEventListener("click",loadMoreHistory);
  $("decision-refresh").addEventListener("click",loadDecisionFunnel);
  document.querySelectorAll("[data-decision-filter]").forEach(node => {
    node.addEventListener("click", () => {
      previewFilter = node.dataset.decisionFilter;
      showHistoricalDecisions();
    });
  });
  $("r-entry_mode").addEventListener("change",refreshCustom);
  $("custom-indicators").addEventListener("input",refreshCustom);
  $("custom-indicators").addEventListener("change",refreshCustom);
  document.querySelectorAll("input,select").forEach(node=>{
    node.addEventListener("input",()=>{edited=true;});
    node.addEventListener("change",()=>{edited=true;});
  });
  load();
  loadPaperSession();
  loadDecisionFunnel();
  setInterval(loadPaperSession,15000);
  setInterval(loadDecisionFunnel,60000);
  setInterval(() => { if (!edited && snapshot) preview(); }, 300000);
});
})();