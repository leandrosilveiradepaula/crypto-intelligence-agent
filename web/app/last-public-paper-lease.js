/* D470: LAST owner PAPER lease != current market data, stops or live trading. */
(function(global){
  "use strict";
  const API="/api/last-public-paper-lease";
  const KEYS=Object.freeze([
    "schema_version","status","primary_returned","sampled_at_ms",
    "last_lease_observed_at_ms","last_lease_recent",
    "historical_rest_candles_reported","confirmed_ws_closes_reported",
    "paper_close_callbacks_reported","public_ticker_callbacks_reported",
    "kline_lease_status","ticker_lease_status","kline_failure_category",
    "ticker_failure_category","paper_research_cohort_complete",
    "paper_relative_btc_hypotheses","paper_pending_open_count",
    "paper_cohort_researched_count","is_historical_lease_report",
    "same_hour_ws_cohort_integrity_independently_verified",
    "current_ticker_coverage_verified","current_kline_coverage_verified",
    "native_stop_verified","real_fills_verified","orders_sent",
    "approved_for_live_use"
  ]);
  const STATES=Object.freeze({
    not_reported:"Sessão não concluída",
    finite_public_paper_research_degraded:"Última sessão degradada",
    finite_public_paper_research_closed:"Última sessão finalizada"
  });
  const KLINE=Object.freeze({
    not_reported:"sem resultado",ws_budget_ended_research_only:"encerrado pelo prazo",
    ws_budget_ended_abstain:"abstenção",ws_fail_closed_abstain:"falha de validação",
    ws_frame_budget_exhausted_abstain:"limite de frames",
    ws_reconnect_budget_exhausted_abstain:"reconexão esgotada"
  });
  const TICKER=Object.freeze({
    not_reported:"causa não registrada",lease_completed:"encerrado pelo prazo",
    lease_degraded:"degradado",lease_abstained:"abstenção",
    ticker_fail_closed_abstain:"falha de validação",
    ticker_reconnect_budget_exhausted_abstain:"reconexão esgotada"
  });
  let refreshing=false;
  const count=(n)=>n===null?"indisponível":String(n);
  function accept(v){
    const valid=v&&typeof v==="object"&&!Array.isArray(v)
      && Object.keys(v).length===KEYS.length
      && KEYS.every(k=>Object.hasOwn(v,k))
      && v.schema_version==="j5-last-public-paper-lease-d470-v1"
      && Object.hasOwn(STATES,v.status)
      && Object.hasOwn(KLINE,v.kline_lease_status)
      && Object.hasOwn(TICKER,v.ticker_lease_status)
      && typeof v.primary_returned==="boolean"
      && typeof v.last_lease_recent==="boolean"
      && Number.isSafeInteger(v.sampled_at_ms)
      && Number.isSafeInteger(v.last_lease_observed_at_ms)
      && v.sampled_at_ms>=v.last_lease_observed_at_ms-5000
      && v.sampled_at_ms-v.last_lease_observed_at_ms<=604800000
      && ["historical_rest_candles_reported","confirmed_ws_closes_reported",
          "paper_close_callbacks_reported","public_ticker_callbacks_reported",
          "paper_relative_btc_hypotheses","paper_pending_open_count",
          "paper_cohort_researched_count"].every(k=>v[k]===null||
            (Number.isSafeInteger(v[k])&&v[k]>=0&&v[k]<=5000000))
      && (v.paper_research_cohort_complete===null
        ||typeof v.paper_research_cohort_complete==="boolean")
      && [v.kline_failure_category,v.ticker_failure_category].every(s=>
        typeof s==="string"&&s.length>=1&&s.length<=64&&/^[a-z0-9_]+$/.test(s))
      && ["is_historical_lease_report"].every(k=>v[k]===true)
      && ["same_hour_ws_cohort_integrity_independently_verified",
          "current_ticker_coverage_verified","current_kline_coverage_verified",
          "native_stop_verified","real_fills_verified","orders_sent",
          "approved_for_live_use"].every(k=>v[k]===false)
      && (v.status!=="finite_public_paper_research_closed"||
        (v.kline_lease_status==="ws_budget_ended_research_only"
        &&v.ticker_lease_status==="lease_completed"))
      && (v.paper_close_callbacks_reported===null
        ||v.confirmed_ws_closes_reported===null
        ||v.paper_close_callbacks_reported<=v.confirmed_ws_closes_reported);
    if(!valid)throw new Error("Última sessão PAPER inválida");
    return v;
  }
  function set(id,text){
    if(typeof document==="undefined")return;
    const item=document.getElementById(id);
    if(item)item.textContent=text;
  }
  function view(v){
    if(!v){
      set("last-public-paper-status","Sem diagnóstico de sessão");
      set("last-public-paper-summary",
          "Nenhuma sessão pública concluída foi carregada deste proprietário.");
      set("last-public-paper-market","Velas e histórico: indisponíveis.");
      set("last-public-paper-ticker","Ticker: indisponível.");
      set("last-public-paper-research","Pesquisa/aberturas: indisponíveis.");
      return;
    }
    set("last-public-paper-status",STATES[v.status]);
    set("last-public-paper-summary",
      "Relatório da última sessão · "+(v.last_lease_recent?"recente":"histórico/antigo")+
      " · "+new Date(v.last_lease_observed_at_ms).toLocaleString("pt-BR")+
      ". Não representa conexão atual, stop nativo ou ordem real.");
    set("last-public-paper-market",
      "REST histórico: "+count(v.historical_rest_candles_reported)+
      " velas · fechamentos WS registrados: "+count(v.confirmed_ws_closes_reported)+
      " · callbacks PAPER: "+count(v.paper_close_callbacks_reported)+
      ". Contagem autorrelatada; não substitui conferência do SQLite.");
    set("last-public-paper-ticker",
      "Ticker da última sessão: "+TICKER[v.ticker_lease_status]+
      " · "+count(v.public_ticker_callbacks_reported)+
      " cotações · velas: "+KLINE[v.kline_lease_status]+
      ". Motivo do ticker: "+(
        v.ticker_failure_category==="none_or_unknown"?
        "não preservado":"categoria técnica "+v.ticker_failure_category
      )+".");
    set("last-public-paper-research",
      "Coorte pesquisada: "+(
        v.paper_research_cohort_complete===null?"indisponível":
        v.paper_research_cohort_complete?"relatada completa":"relatada incompleta"
      )+" · hipóteses relativas ao BTC: "+count(v.paper_relative_btc_hypotheses)+
      " · aberturas PAPER pendentes: "+count(v.paper_pending_open_count)+
      ". Histórico não autoriza entradas.");
  }
  function isLocal(){
    const l=global.location;
    return Boolean(l&&l.protocol==="http:"&&l.port==="8765"
      &&(l.hostname==="localhost"||l.hostname==="127.0.0.1"));
  }
  async function refreshLocal(){
    if(!isLocal()||refreshing)return;
    refreshing=true;
    try{
      const response=await global.fetch(API,{
        method:"GET",credentials:"omit",cache:"no-store",redirect:"error"
      });
      if(response.status!==200||!response.ok
        ||!(response.headers.get("content-type")||"").startsWith("application/json"))
        throw new Error("No owner-only lease");
      const raw=await response.text();
      if(raw.length<2||raw.length>4096)throw new Error("Lease too large");
      view(accept(JSON.parse(raw)));
    }catch(_){view(null);}
    finally{refreshing=false;}
  }
  global.CIALastPublicPaperLease=Object.freeze({accept,view,refreshLocal});
  if(typeof module==="object"&&module&&module.exports)
    module.exports=global.CIALastPublicPaperLease;
  if(typeof document!=="undefined"){
    view(null);
    if(isLocal()){
      void refreshLocal();
      global.setInterval(()=>{void refreshLocal();},30000);
    }
  }
})(typeof globalThis!=="undefined"?globalThis:this);
