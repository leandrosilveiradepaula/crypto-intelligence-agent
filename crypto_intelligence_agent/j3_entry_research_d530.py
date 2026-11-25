"""D530 research-only causal pullback and Bollinger squeeze entry experiments.

Immutable explicit parameters; no live signal, profile or trading integration.
RSI is evaluated separately in D529, after the original candidate.
"""
from __future__ import annotations
from dataclasses import dataclass, replace
from decimal import Decimal, localcontext
import json
import re

from .j2_configurable_indicators_d513 import (
    BollingerBands, moving_average, bollinger_bands, parse_rsi,
    PivotSuperTrend, pivot_trend,
)
from .j3_combination_research_d520 import _unique, _decimal
from .market_data import DataValidationError
from .synthetic_feature_engine import _MATH_CONTEXT

SCHEMA="d530-entry-experiments-v1"
MAX_BYTES=32768


@dataclass(frozen=True)
class EntryExperiment:
    trigger: str
    fast: int
    slow: int
    exponential: bool
    pullback_bars: int
    trend_bars: int
    bb_period: int
    bb_deviations: Decimal
    compression_bars: int
    baseline_bars: int
    max_width_ratio: Decimal
    volume_period: int
    min_volume_ratio: Decimal
    cooldown_bars: int
    pivot_filter: PivotSuperTrend | None = None

    def __post_init__(self):
        if type(self.trigger) is not str or self.trigger not in ("pullback","bb_squeeze"):
            raise DataValidationError("D530 unknown trigger")
        if type(self.exponential) is not bool:
            raise DataValidationError("D530 explicit MA family")
        for k,lo,hi in (("fast",2,120),("slow",3,120),
                ("pullback_bars",1,24),("trend_bars",1,24),
                ("bb_period",2,120),("compression_bars",2,24),
                ("baseline_bars",4,120),("volume_period",2,120),
                ("cooldown_bars",0,120)):
            v=getattr(self,k)
            if type(v) is not int or not lo<=v<=hi:
                raise DataValidationError("D530 invalid integer parameter")
        if self.pivot_filter is not None and (type(self.pivot_filter) is not PivotSuperTrend
                or not self.pivot_filter.enabled):
            raise DataValidationError("D532 explicit enabled Pivot veto required")
        if self.fast>=self.slow:
            raise DataValidationError("D530 ordered MAs")
        for v,lo,hi in ((self.bb_deviations,Decimal(".1"),Decimal(10)),
                         (self.max_width_ratio,Decimal(".1"),Decimal(1)),
                         (self.min_volume_ratio,Decimal(".5"),Decimal(10))):
            if type(v) is not Decimal or not v.is_finite() or not lo<=v<=hi:
                raise DataValidationError("D530 invalid decimal parameter")

    @property
    def warmup(self):
        n=self.slow+self.trend_bars+self.pullback_bars+1
        if self.trigger=="bb_squeeze":
            n=max(self.slow+1,self.bb_period+self.compression_bars+self.baseline_bars)
        return max(24,self.volume_period+1,n)


def parse_experiments(raw):
    if type(raw) is not bytes or not 2<=len(raw)<=MAX_BYTES:
        raise DataValidationError("D530 bounded experiments file required")
    try:
        d=json.loads(raw.decode("utf-8"),object_pairs_hook=_unique)
    except (ValueError,UnicodeError,TypeError) as exc:
        raise DataValidationError("D530 malformed experiments") from exc
    if (type(d) is not dict or set(d)!={"schema","profiles"}
            or d["schema"]!=SCHEMA or type(d["profiles"]) is not list
            or not 1<=len(d["profiles"])<=24):
        raise DataValidationError("D530 explicit experimental matrix")
    result=[]
    names=set()
    fingerprints=set()
    for p in d["profiles"]:
        if (type(p) is not dict or set(p)!={"name","label","parameters",
                                               "relative_strength_bps","rsi_filter"}):
            raise DataValidationError("D530 explicit profile fields")
        name,label=p["name"],p["label"]
        if (type(name) is not str or not re.fullmatch(r"[a-z][a-z0-9_]{1,39}",name)
                or name in names or type(label) is not str or not 1<=len(label)<=100
                or any(ord(c)<32 for c in label)):
            raise DataValidationError("D530 profile identity")
        args=p["parameters"]
        required=set(EntryExperiment.__dataclass_fields__)-{"pivot_filter"}
        if type(args) is not dict or not required<=set(args)<=required|{"pivot_filter"}:
            raise DataValidationError("D530 explicit parameters")
        args=dict(args)
        pivot=args.get("pivot_filter")
        if pivot is not None:
            if type(pivot) is not dict or set(pivot)!={"pivot_period","atr_period","atr_factor"}:
                raise DataValidationError("D532 exact Pivot veto parameters")
            args["pivot_filter"]=PivotSuperTrend(True,pivot["pivot_period"],
                pivot["atr_period"],_decimal(pivot["atr_factor"]))
        for key in ("bb_deviations","max_width_ratio","min_volume_ratio"):
            args[key]=_decimal(args[key])
        cfg=EntryExperiment(**args)
        threshold=_decimal(p["relative_strength_bps"])
        if not 0<=threshold<=1000:
            raise DataValidationError("D530 FR threshold")
        gate=p["rsi_filter"]
        if gate is not None:
            if type(gate) is not dict or set(gate)!={"period","long_min","long_max"}:
                raise DataValidationError("D530 RSI pure veto")
            gate=parse_rsi({"enabled":True,**gate})
        fingerprint=(cfg,threshold,gate)
        if fingerprint in fingerprints:
            raise DataValidationError("D530 duplicate experiment")
        fingerprints.add(fingerprint)
        names.add(name)
        result.append((name,label,cfg,threshold,gate))
    return tuple(result)


def entry_events(candles, cfg):
    """Use only bars closed through the candidate. A correction arms a
    pullback once; one subsequent resumption consumes it. Squeeze uses
    exclusively prior bandwidth for compression and prior bands for breaks.
    Caller splits gaps and applies FR and optional RSI after candidate.
    """
    if type(cfg) is not EntryExperiment:
        raise DataValidationError("D530 typed experiment")
    # Pure veto of the already generated event, including its cooldown.
    # Rejected events never re-arm the underlying trigger or change its clock.
    if cfg.pivot_filter is not None:
        original=entry_events(candles,replace(cfg,pivot_filter=None))
        trend=pivot_trend(tuple(candles),cfg.pivot_filter)
        return {c.close_time_ms+1:original[c.close_time_ms+1]
                for i,c in enumerate(candles) if c.close_time_ms+1 in original
                and trend[i]==(1 if original[c.close_time_ms+1]=="LONG" else -1)}
    closes=tuple(c.close for c in candles)
    fast=moving_average(closes,cfg.fast,exponential=cfg.exponential)
    slow=moving_average(closes,cfg.slow,exponential=cfg.exponential)
    bands=(bollinger_bands(closes,BollingerBands(True,cfg.bb_period,
              cfg.bb_deviations,"breakout")) if cfg.trigger=="bb_squeeze" else ())
    result={}
    armed=None
    previous_trend=0
    streak=0
    last=None
    with localcontext(_MATH_CONTEXT):
        widths=tuple(None if b is None else (b[2]-b[0])/b[1] for b in bands)
        for i,c in enumerate(candles):
            if fast[i] is None or slow[i] is None:
                continue
            trend=1 if fast[i]>slow[i] and c.close>slow[i] else (
                -1 if fast[i]<slow[i] and c.close<slow[i] else 0)
            if trend!=previous_trend:
                streak=1
                armed=None
            else:
                streak+=1
            previous_trend=trend
            side=0
            if cfg.trigger=="pullback":
                if armed is not None and (trend!=armed[0] or i-armed[1]>cfg.pullback_bars):
                    armed=None
                if not trend:
                    continue
                if armed is not None and i>armed[1]:
                    prior=candles[i-1]
                    if ((trend==1 and c.close>fast[i] and c.close>prior.high)
                            or (trend==-1 and c.close<fast[i] and c.close<prior.low)):
                        side=trend
                        armed=None
                elif streak>=cfg.trend_bars and (
                        (trend==1 and c.close<=fast[i]) or
                        (trend==-1 and c.close>=fast[i])):
                    armed=(trend,i)
            else:
                n=cfg.compression_bars
                b=cfg.baseline_bars
                if i<n+b or not trend:
                    continue
                recent=widths[i-n:i]
                baseline=widths[i-n-b:i-n]
                if any(v is None for v in recent+baseline) or widths[i] is None:
                    continue
                base=sum(baseline,Decimal(0))/b
                if (base<=0 or sum(recent,Decimal(0))/n>base*cfg.max_width_ratio
                        or widths[i]<=widths[i-1]):
                    continue
                lower,_,upper=bands[i-1]
                side=1 if trend==1 and c.close>upper and closes[i-1]<=upper else (
                    -1 if trend==-1 and c.close<lower and closes[i-1]>=lower else 0)
            if not side or i+1<cfg.warmup or (last is not None and i-last<=cfg.cooldown_bars):
                continue
            prior_vol=sum((x.quote_volume for x in candles[i-cfg.volume_period:i]),Decimal(0))
            if prior_vol<=0 or c.quote_volume*cfg.volume_period<prior_vol*cfg.min_volume_ratio:
                continue
            result[c.close_time_ms+1]="LONG" if side==1 else "SHORT"
            last=i
    return result
