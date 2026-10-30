"""Cost-sensitive monthly OOS *research proxy*, NOT execution or backtest approval."""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal, localcontext, Context
from hashlib import sha256
import json
from .market_data import DataValidationError
from .offline_vision_series import assemble_offline_vision_months

H=3600000
CTX=Context(prec=100)
MAX_ASSETS=50

@dataclass(frozen=True)
class OOSCostFold:
    test_month_number:int
    selected_rule:str
    training_net_bps:Decimal
    observations:int
    net_bps:Decimal
    benchmark_long_net_bps:Decimal
    worst_drawdown_bps:Decimal

@dataclass(frozen=True)
class CostedOOSResearch:
    asset_count:int
    cost_bps_per_side:Decimal
    folds:tuple[OOSCostFold,...]
    digest_sha256:str

    def sanitized_report(self)->dict:
        return {"status":"offline_hypothetical_costed_oos_only",
            "asset_count":self.asset_count,"fold_count":len(self.folds),
            "selected_rules":[f.selected_rule for f in self.folds],
            "scored_observations":sum(f.observations for f in self.folds),
            "net_bps":str(sum((f.net_bps for f in self.folds),Decimal(0))),
            "benchmark_net_bps":str(sum((f.benchmark_long_net_bps for f in self.folds),Decimal(0))),
            "worst_drawdown_proxy_bps":str(min((f.worst_drawdown_bps for f in self.folds),default=Decimal(0))),
            "research_digest_sha256":self.digest_sha256,
            "marketwide_top50_verified":False,"source_authenticated":False,
            "financial_backtest_approved":False,"live_trading_authorized":False,
            "orders_sent":False,"network_requests":0,"data_stored":False}

def costed_vision_monthly_oos(month_groups:tuple[tuple,...],*,as_of_ms:int,
                            cost_bps_per_side:Decimal)->CostedOOSResearch:
    if (type(month_groups) is not tuple or not 2<=len(month_groups)<=MAX_ASSETS
        or type(cost_bps_per_side) is not Decimal or not cost_bps_per_side.is_finite()
        or cost_bps_per_side<0 or cost_bps_per_side>Decimal(1000)
        or cost_bps_per_side.as_tuple().exponent< -6):
        raise DataValidationError("bounded hypothetical OOS inputs required")
    series=tuple(assemble_offline_vision_months(g,as_of_ms=as_of_ms) for g in month_groups)
    if len(set(s.symbol for s in series))!=len(series):
        raise DataValidationError("duplicate historical sample symbol")
    if any(s.interval!="1h" or s.first_open_ms!=series[0].first_open_ms
        or s.end_open_exclusive_ms!=series[0].end_open_exclusive_ms
        or s.month_names[0][-11:]!=series[0].month_names[0][-11:]
        or len(s.candles)!=len(series[0].candles)
        or len(s.month_names)!=len(series[0].month_names)
        for s in series):
        raise DataValidationError("unaligned monthly OOS sample")
    if len(series[0].month_names)<2:
        raise DataValidationError("OOS requires two closed months")
    indices=[0]
    for i in range(1,len(series[0].candles)):
        if series[0].candles[i].open_time_ms//(24*H) == series[0].candles[i-1].open_time_ms//(24*H):
            continue
        # Month boundaries are derived from validated month segments below instead.
    cursor=0
    for g in month_groups[0]:
        cursor+=len(g.candles)
        indices.append(cursor)
    with localcontext(CTX):
        # Each hypothetical trade is one fully closed test bar after an
        # already known 24h ranking. Selection cannot use current-bar volume.
        def scores(lo,hi):
            out=[]
            for i in range(max(24,lo),hi):
                ranked=sorted(((s.symbol,sum((c.documented_quote_volume for c in s.candles[i-24:i]),Decimal(0)),j)
                               for j,s in enumerate(series)),key=lambda x:(-x[1],x[0]))
                j=ranked[0][2]
                c=series[j].candles[i]
                prev=series[j].candles[i-1]
                if c.open<=0 or prev.close<=0:
                    raise DataValidationError("invalid OOS price")
                direction=1 if prev.close>series[j].candles[i-2].close else (-1 if prev.close<series[j].candles[i-2].close else 0)
                base=(c.close-c.open)*Decimal(10000)/c.open
                turnover=cost_bps_per_side*2
                out.append((direction,base,turnover))
            return out
        # Distinct calendar-month folds, no reuse of current month for fitting.
        folds=[]
        history=[]
        for k in range(len(indices)-1):
            current=scores(indices[k],indices[k+1])
            if k:
                cont=sum(((b*d-t) for d,b,t in history if d),Decimal(0))
                rev=sum(((-b*d-t) for d,b,t in history if d),Decimal(0))
                rule="continuation" if cont>rev and cont>0 else ("reversal" if rev>cont and rev>0 else "abstain")
                fit=max(cont,rev,Decimal(0))
                net=bench=equity=peak=worst=Decimal(0)
                count=0
                for d,b,t in current:
                    bench+=b-t
                    if d and rule!="abstain":
                        value=b*d*(1 if rule=="continuation" else -1)-t
                        count+=1
                        net+=value
                        equity+=value
                        peak=max(peak,equity)
                        worst=min(worst,equity-peak)
                folds.append(OOSCostFold(k+1,rule,fit,count,net,bench,worst))
            history.extend(current)
        digest=sha256(json.dumps([
            [f.test_month_number,f.selected_rule,str(f.training_net_bps),
             f.observations,str(f.net_bps),str(f.benchmark_long_net_bps),str(f.worst_drawdown_bps)]
            for f in folds],separators=(",",":")).encode()).hexdigest()
    return CostedOOSResearch(len(series),cost_bps_per_side,tuple(folds),digest)
