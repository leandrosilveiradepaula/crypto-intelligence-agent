/* D456: owner-only D453 PAPER operator status; never venue protection. */
(function(global){
  "use strict";
  const API="/api/resident-paper-status";
  const STATES=Object.freeze({
    starting:"Inicializando observador PAPER",
    observing_public_lease:"Sessão pública em andamento (não comprovada)",
    held_only_fallback:"Contingência: acompanhando posições existentes",
    lease_ended_not_protected:"Sessão encerrada; sem proteção nativa",
    degraded_no_held_coverage:"Sem acompanhamento PAPER: falha",
    bounded_run_completed:"Execução de teste encerrada",
    stopped:"Operador encerrado"
  });
  const KEYS=Object.freeze([
    "schema_version","status","sampled_at_ms","last_reported_at_ms",
    "cycle_attempts","primary_leases_completed","held_only_fallbacks",
    "source_mode","lease_now_guaranteed_active",
    "uninterrupted_market_coverage_verified","native_stop_verified",
    "venue_position_verified","real_orders_sent","approved_for_live_use"
  ]);
  let previous=null,refreshing=false;
  function valid(ok){if(!ok)throw new Error("Status residente PAPER inválido");}
  function accept(value){
    valid(value&&typeof value==="object"&&!Array.isArray(value)
      && Object.keys(value).length===KEYS.length
      && KEYS.every(k=>Object.hasOwn(value,k))
      && value.schema_version==="j5-resident-paper-readonly-d456-v1"
      && Object.hasOwn(STATES,value.status)
      && ["offline_injected_test","public_research_unverified"].includes(value.source_mode)
      && ["lease_now_guaranteed_active","uninterrupted_market_coverage_verified",
          "native_stop_verified","venue_position_verified",
          "real_orders_sent","approved_for_live_use"].every(k=>value[k]===false)
      && ["sampled_at_ms","last_reported_at_ms"].every(k=>
        Number.isSafeInteger(value[k])&&value[k]>=1600000000000
        && value[k]<=4102444800000)
      && value.sampled_at_ms>=value.last_reported_at_ms-5000
      && value.sampled_at_ms-value.last_reported_at_ms<=375000
      && ["cycle_attempts","primary_leases_completed","held_only_fallbacks"].every(k=>
        Number.isSafeInteger(value[k])&&value[k]>=0&&value[k]<=1000000)
      && value.primary_leases_completed+value.held_only_fallbacks<=value.cycle_attempts);
    return value;
  }
  function view(value){
    if(typeof document==="undefined")return;
    const status=document.getElementById("resident-paper-status");
    const summary=document.getElementById("resident-paper-summary");
    if(!status||!summary)return;
    if(!value){
      status.textContent="Sem estado residente recente";
      summary.textContent="Operador PAPER ausente, encerrado ou sem estado válido; nenhuma saída é protegida na corretora.";
      return;
    }
    status.textContent=STATES[value.status];
    summary.textContent="Ciclos "+value.cycle_attempts+
      " · sessões completas "+value.primary_leases_completed+
      " · contingências "+value.held_only_fallbacks+
      " · status local não garante feed, stop nativo ou posição real.";
  }
  function isLocal(){
    const l=global.location;
    return Boolean(l&&l.protocol==="http:"&&l.port==="8765"
      && (l.hostname==="localhost"||l.hostname==="127.0.0.1"));
  }
  async function refreshLocal(){
    if(!isLocal()||refreshing)return;
    refreshing=true;
    try{
      const response=await global.fetch(API,{
        method:"GET",credentials:"omit",cache:"no-store",redirect:"error"
      });
      if(!response.ok||response.status!==200
        ||!(response.headers.get("content-type")||"").startsWith("application/json")){
        throw new Error("resident PAPER source absent");
      }
      const body=await response.text();
      if(body.length<2||body.length>4096)throw new Error("oversized resident PAPER");
      previous=accept(JSON.parse(body));
      view(previous);
    }catch(_){
      previous=null;
      view(null);
    }finally{refreshing=false;}
  }
  global.CIAResidentPaper=Object.freeze({accept,refreshLocal});
  if(typeof module==="object"&&module&&module.exports){
    module.exports=global.CIAResidentPaper;
  }
  if(typeof document!=="undefined"){
    view(null);
    if(isLocal()){
      void refreshLocal();
      global.setInterval(()=>{void refreshLocal();},15000);
    }
  }
})(typeof globalThis!=="undefined"?globalThis:this);
