"""J3 OOS stress audit: frozen monthly rule, conditional OHLC branches only."""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal, localcontext, Context
from hashlib import sha256
import json
from .market_data import DataValidationError
from .offline_vision_series import assemble_offline_vision_months
from .vision_costed_oos import costed_vision_monthly_oos
from .vision_intrabar_stress import VisionStressAssumptions, stress_vision_candle

_CTX=Context(prec=512)

@dataclass(frozen=True)
class VisionStressOOS:
    stressed_count: int
    ambiguous_count: int
    liquidation_possible_count: int
    worst_net_quote: Decimal
    best_net_quote: Decimal
    digest_sha256: str
    benchmark_worst_net_quote: Decimal = Decimal(0)
    benchmark_best_net_quote: Decimal = Decimal(0)
    worst_drawdown_proxy_quote: Decimal = Decimal(0)
    best_drawdown_proxy_quote: Decimal = Decimal(0)
    benchmark_worst_drawdown_proxy_quote: Decimal = Decimal(0)
    benchmark_best_drawdown_proxy_quote: Decimal = Decimal(0)
    fold_reports: tuple[tuple[int,int,int,int], ...] = ()

    def sanitized_report(self)->dict:
        return {
            "status":"offline_oos_conditional_intrabar_stress_only",
            "stressed_count":self.stressed_count,
            "ambiguous_count":self.ambiguous_count,
            "liquidation_possible_count":self.liquidation_possible_count,
            "worst_net_quote":str(self.worst_net_quote),
            "best_net_quote":str(self.best_net_quote),
            "digest_sha256":self.digest_sha256,
            "benchmark_worst_net_quote":str(self.benchmark_worst_net_quote),
            "benchmark_best_net_quote":str(self.benchmark_best_net_quote),
            "worst_drawdown_proxy_quote":str(self.worst_drawdown_proxy_quote),
            "best_drawdown_proxy_quote":str(self.best_drawdown_proxy_quote),
            "benchmark_worst_drawdown_proxy_quote":str(self.benchmark_worst_drawdown_proxy_quote),
            "benchmark_best_drawdown_proxy_quote":str(self.benchmark_best_drawdown_proxy_quote),
            "fold_coverage":[{"test_month_number":k,"bars_scored":bars,
                "strategy_exposures":exposures,"ambiguous_exposures":amb}
                for k,bars,exposures,amb in self.fold_reports],
            "financial_backtest_approved":False,
            "marketwide_top50_verified":False,
            "source_authenticated":False,
            "live_trading_authorized":False,
            "orders_sent":False,"network_requests":0,"data_stored":False,
        }


def audit_costed_vision_intrabar_oos(month_groups:tuple[tuple,...],*,as_of_ms:int,
    cost_bps_per_side:Decimal, assumptions:VisionStressAssumptions)->VisionStressOOS:
    if type(assumptions) is not VisionStressAssumptions:
        raise DataValidationError("explicit synthetic stress assumptions required")
    baseline=costed_vision_monthly_oos(
        month_groups,as_of_ms=as_of_ms,cost_bps_per_side=cost_bps_per_side)
    series=tuple(assemble_offline_vision_months(g,as_of_ms=as_of_ms)
                 for g in month_groups)
    bounds=[0]
    for month in month_groups[0]:
        bounds.append(bounds[-1]+len(month.candles))
    # Honor each fold's rule selected from PRIOR months. No refitting or
    # artificial extraction of winners from the test period.
    with localcontext(_CTX):
        worst=best=Decimal(0)
        n=ambiguous=liquidations=0
        bench_worst=bench_best=Decimal(0)
        eq=[Decimal(0) for _ in range(4)]
        peak=[Decimal(0) for _ in range(4)]
        dd=[Decimal(0) for _ in range(4)]
        fold_reports=[]
        digest=sha256()
        def track(j,change):
            eq[j]+=change
            peak[j]=max(peak[j],eq[j])
            dd[j]=min(dd[j],eq[j]-peak[j])
        for k,fold in enumerate(baseline.folds,1):
            exposure_before=n
            ambiguous_before=ambiguous
            bars=0
            for i in range(bounds[k],bounds[k+1]):
                ranked=sorted(
                    ((s.symbol,sum((c.documented_quote_volume
                                    for c in s.candles[i-24:i]),Decimal(0)),j)
                     for j,s in enumerate(series)),
                    key=lambda row:(-row[1],row[0]))
                j=ranked[0][2]
                prices=series[j].candles
                bars+=1
                # Same ranked candle and synthetic terms for the fixed LONG
                # benchmark, including when the selected rule abstains.
                reference=stress_vision_candle(prices[i],long=True,assumptions=assumptions)
                bench_worst+=reference.worst_net_quote
                bench_best+=reference.best_net_quote
                track(2,reference.worst_net_quote)
                track(3,reference.best_net_quote)
                movement=prices[i-1].close-prices[i-2].close
                if movement==0 or fold.selected_rule=="abstain":
                    continue
                trend=movement>0
                long=trend if fold.selected_rule=="continuation" else not trend
                row=stress_vision_candle(prices[i],long=long,assumptions=assumptions)
                n+=1
                ambiguous+=int(row.intrabar_ambiguous)
                liquidations+=int(row.touched_liquidation_proxy)
                worst+=row.worst_net_quote
                best+=row.best_net_quote
                track(0,row.worst_net_quote)
                track(1,row.best_net_quote)
                digest.update(json.dumps([
                    k,i,int(long),str(row.worst_net_quote),str(row.best_net_quote),
                    int(row.intrabar_ambiguous),int(row.touched_liquidation_proxy)],
                    separators=(",",":")).encode("ascii")+b"\\n")
            fold_reports.append((k,bars,n-exposure_before,ambiguous-ambiguous_before))
        digest.update(json.dumps([str(bench_worst),str(bench_best),
            [str(x) for x in dd],fold_reports],separators=(",",":")).encode("ascii"))
        return VisionStressOOS(n,ambiguous,liquidations,worst,best,digest.hexdigest(),
            bench_worst,bench_best,dd[0],dd[1],dd[2],dd[3],tuple(fold_reports))
