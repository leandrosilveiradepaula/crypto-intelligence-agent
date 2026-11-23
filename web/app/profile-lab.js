/* D487: user-controlled PAPER parameters, with owner-only localhost saving.
   No direct venue access, websocket, orders or browser-side trading engine. */
(function () {
"use strict";
const $ = id => document.getElementById(id);
const RESEARCH_INT = ["ema_period","atr_period","extrema_period",
  "quote_volume_period","compression_bars","baseline_bars","cooldown_bars"];
const RESEARCH_DEC = ["max_atr_ratio","min_quote_volume_ratio"];
let snapshot = null, edited = false;
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
function fill(model) {
  RESEARCH_INT.forEach(k => $("r-"+k).value = model.research[k]);
  RESEARCH_DEC.forEach(k => $("r-"+k).value = model.research[k]);
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
    status("Perfil PAPER carregado. Você pode alterar os valores e salvar. Nenhuma posição será modificada.");
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
    status("Perfil salvo na VPS. Será lido pelo motor na PRÓXIMA sessão PAPER; as posições atuais permanecem iguais.");
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
      " encerrada(s) · "+d.intents.length+
      " intenção(ões) PAPER. Ordens reais: NÃO.";
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
  } catch(e) {
    $("paper-session-details").textContent =
      "Diário da sessão ainda indisponível. Não presumir posições ou fills.";
    $("paper-position-rows").textContent="Estado não disponível.";
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

async function preview() {
  if (!snapshot) return;
  if (edited) {
    status("Salve as alterações antes de pesquisar com o novo perfil.",true);
    return;
  }
  $("preview").disabled = true;
  $("preview-details").textContent = "Lendo o histórico REAL já armazenado na VPS…";
  $("preview-rows").replaceChildren();
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
      for (const item of result.candidates) {
        const card=document.createElement("div");
        card.className="row";
        const name=document.createElement("strong");
        name.textContent=item.symbol+" · "+item.side;
        const relative=document.createElement("span");
        relative.className="mono";
        relative.textContent="BTC relativo: "+item.btc_relative_percent+" p.p.";
        card.append(name,relative);
        $("preview-rows").append(card);
      }
      if (!result.candidates.length) {
        $("preview-rows").textContent="Nenhum candidato para este histórico e configuração.";
      }
    }
  } catch(error) {
    $("preview-details").textContent="Pesquisa indisponível: "+error.message;
  } finally {
    $("preview").disabled = false;
  }
}
document.addEventListener("DOMContentLoaded",()=>{
  $("save").addEventListener("click",save);
  $("preview").addEventListener("click",preview);
  document.querySelectorAll("input").forEach(node=>{
    node.addEventListener("input",()=>{edited=true;});
    node.addEventListener("change",()=>{edited=true;});
  });
  load();
  loadPaperSession();
  setInterval(loadPaperSession,15000);
});
})();