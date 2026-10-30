"""J1/J2 research-only replay across aligned, previously validated Vision months.

No marketwide eligibility, provider attestation, orders or network.
"""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
import json

from .market_data import DataValidationError
from .offline_vision_month import OfflineVisionMonth
from .offline_vision_series import assemble_offline_vision_months

HOUR_MS=3_600_000
MAX_ASSETS=50
MAX_DECISIONS=720


@dataclass(frozen=True)
class OfflineVisionReplay:
    asset_count: int
    decisions_count: int
    ranked_observations: int
    first_decision_ms: int
    last_decision_ms: int
    ranking_digest_sha256: str

    def sanitized_report(self) -> dict:
        return {
            "schema_version":"vision-private-dynamic-replay-v1",
            "status":"offline_research_sample_replayed",
            "asset_count":self.asset_count,
            "decisions_count":self.decisions_count,
            "ranked_observations":self.ranked_observations,
            "first_decision_ms":self.first_decision_ms,
            "last_decision_ms":self.last_decision_ms,
            "ranking_digest_sha256":self.ranking_digest_sha256,
            "sample_only":True,
            "marketwide_top50_verified":False,
            "historical_listing_eligibility_verified":False,
            "dataset_rights_authorized_for_live":False,
            "canonical_ohlcv_approved":False,
            "financial_backtest_approved":False,
            "live_trading_authorized":False,
            "orders_sent":False,
            "network_requests":0,
            "data_stored":False,
        }


def replay_offline_vision_dynamic_ranking(
    month_groups: tuple[tuple[OfflineVisionMonth, ...], ...], *,
    as_of_ms: int, first_decision_ms: int, last_decision_ms: int,
    step_hours: int=24, max_candidates: int=50,
) -> OfflineVisionReplay:
    if (type(month_groups) is not tuple or not 2 <= len(month_groups) <= MAX_ASSETS
            or any(type(group) is not tuple for group in month_groups)
            or type(as_of_ms) is not int
            or type(first_decision_ms) is not int or type(last_decision_ms) is not int
            or type(step_hours) is not int or not 1 <= step_hours <= 720
            or type(max_candidates) is not int or not 1 <= max_candidates <= 50
            or first_decision_ms % HOUR_MS or last_decision_ms % HOUR_MS
            or last_decision_ms < first_decision_ms):
        raise DataValidationError("bounded aligned research replay inputs required")
    series=tuple(assemble_offline_vision_months(group,as_of_ms=as_of_ms)
                 for group in month_groups)
    symbols=[item.symbol for item in series]
    if len(set(symbols)) != len(symbols):
        raise DataValidationError("duplicate offline research asset")
    signature=(series[0].first_open_ms,series[0].end_open_exclusive_ms,len(series[0].candles))
    if any((item.first_open_ms,item.end_open_exclusive_ms,len(item.candles))!=signature
           or item.interval!="1h" or not item.symbol.endswith("USDT") for item in series):
        raise DataValidationError("unaligned offline sample or mixed quote")
    first_open=signature[0]
    if (first_decision_ms < first_open+24*HOUR_MS
            or last_decision_ms > signature[1]
            or last_decision_ms+1000 > as_of_ms):
        raise DataValidationError("replay uses unavailable or future candle")
    n=(last_decision_ms-first_decision_ms)//(step_hours*HOUR_MS)+1
    if (last_decision_ms-first_decision_ms)%(step_hours*HOUR_MS) or n>MAX_DECISIONS:
        raise DataValidationError("replay schedule incomplete or over budget")
    # Incremental prefix sums prevent repeating 24-window parsing at every date.
    prefix=[]
    for item in series:
        running=[Decimal(0)]
        for candle in item.candles:
            running.append(running[-1]+candle.documented_quote_volume)
        prefix.append(running)
    digest=sha256()
    for k in range(n):
        at=first_decision_ms+k*step_hours*HOUR_MS
        idx=(at-first_open)//HOUR_MS
        ranked=sorted(
            ((item.symbol, prefix[j][idx]-prefix[j][idx-24])
             for j,item in enumerate(series)), key=lambda x:(-x[1],x[0]))
        digest.update(json.dumps(
            [at,[[s,format(v,"f")] for s,v in ranked[:max_candidates]]],
            separators=(",",":"),ensure_ascii=True).encode("ascii"))
        digest.update(b"\n")
    return OfflineVisionReplay(
        asset_count=len(series),decisions_count=n,
        ranked_observations=n*min(max_candidates,len(series)),
        first_decision_ms=first_decision_ms,last_decision_ms=last_decision_ms,
        ranking_digest_sha256=digest.hexdigest(),
    )
