"""Causal J2 research math for D434 public confirmed candles, never a signal gate."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext

from .j2_bybit_closed_research_bridge import BybitClosedResearchSeries
from .synthetic_entry_hypotheses import CompressionBreakoutConfig, _prior_atr_means
from .synthetic_feature_engine import CausalFeatureRow, _MATH_CONTEXT, _numeric
from .synthetic_position_state import SyntheticSide
from .market_data import DataGapError, DataValidationError

_QUALITY = "bybit_public_ws_confirmed_unverified"


@dataclass(frozen=True)
class ObservedBybitHypothesis:
    side: SyntheticSide
    closed_at_ms: int
    close: Decimal
    journal_digest_sha256: str
    @property
    def approved_for_signals(self) -> bool: return False
    @property
    def orders_sent(self) -> bool: return False


@dataclass(frozen=True)
class ObservedBybitResearch:
    status: str
    evaluated_candle_count: int
    hypotheses: tuple[ObservedBybitHypothesis, ...]
    journal_digest_sha256: str
    @property
    def approved_for_signals(self) -> bool: return False
    @property
    def orders_sent(self) -> bool: return False


def evaluate_observed_bybit_research(series: BybitClosedResearchSeries, *, config: CompressionBreakoutConfig,
                                     decision_at_ms: int, close_safety_ms: int = 1) -> ObservedBybitResearch:
    if type(series) is not BybitClosedResearchSeries or type(config) is not CompressionBreakoutConfig:
        raise DataValidationError("typed observed series and J2 configuration required")
    cs = series.candles
    if (not cs or any(c.quality != _QUALITY for c in cs) or decision_at_ms != cs[-1].close_time_ms + close_safety_ms):
        raise DataGapError("observed public series is not causally available")
    rows=[]
    with localcontext(_MATH_CONTEXT):
        ema=atr=None; ranges=[]; alpha=Decimal(2)/Decimal(config.features.ema_period+1)
        for i,c in enumerate(cs):
            for key in ("open","high","low","close"): _numeric(getattr(c,key),key,strictly_positive=True)
            for key in ("base_volume","quote_volume"): _numeric(getattr(c,key),key,strictly_positive=False)
            previous=cs[i-1].close if i else None
            tr=c.high-c.low if previous is None else max(c.high-c.low,abs(c.high-previous),abs(c.low-previous)); ranges.append(tr)
            if i==config.features.ema_period-1: ema=sum((x.close for x in cs[:i+1]),Decimal(0))/Decimal(i+1)
            elif i>=config.features.ema_period: ema=ema+alpha*(c.close-ema)
            if i==config.features.atr_period-1: atr=sum(ranges,Decimal(0))/Decimal(len(ranges))
            elif i>=config.features.atr_period: atr=(atr*Decimal(config.features.atr_period-1)+tr)/Decimal(config.features.atr_period)
            xp=config.features.extrema_period; vp=config.features.quote_volume_period
            prior=cs[i-xp:i] if i>=xp else (); high=max((x.high for x in prior),default=None); low=min((x.low for x in prior),default=None)
            ratio=None
            if i>=vp:
                total=sum((x.quote_volume for x in cs[i-vp:i]),Decimal(0)); ratio=c.quote_volume/(total/Decimal(vp)) if total>0 else None
            rows.append(CausalFeatureRow(c.open_time_ms,c.close_time_ms,c.close,None,tr if False else None,tr,atr,high,low,ratio))
        hypotheses=[]
        shadow=type("Series",(),{"rows":tuple(rows)})()
        for i,row in enumerate(rows):
            prior=_prior_atr_means(shadow,i,config)
            if not prior or row.ema_close is None or row.preceding_high is None or row.preceding_low is None or row.quote_volume_to_prior_mean is None: continue
            recent,baseline=prior
            if recent/baseline>config.max_atr_ratio or row.quote_volume_to_prior_mean<config.min_quote_volume_ratio: continue
            side= SyntheticSide.LONG if row.close>row.preceding_high and row.close>row.ema_close else SyntheticSide.SHORT if row.close<row.preceding_low and row.close<row.ema_close else None
            if side: hypotheses.append(ObservedBybitHypothesis(side,row.close_time_ms,row.close,series.journal_digest_sha256))
    return ObservedBybitResearch("observed_hypothesis_not_authorized" if hypotheses else "observed_no_hypothesis",len(rows),tuple(hypotheses),series.journal_digest_sha256)
