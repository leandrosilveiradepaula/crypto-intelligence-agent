"""D518: independently dated 5-minute trade-price observations for exit replay.

Only an original D461 hourly path can authorize its own refinement. The
retrieved bars must reproduce the original hourly OHLC exactly. Never use
these bars to create entry signals, reconstruct membership or claim fills.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import tempfile
import time

from .bybit_linear_candle_research import stage_bybit_linear_kline
from .bybit_public_j1_transport import (
    BoundedBybitPublicClient, HOUR_MS, research_five_minute_url,
)
from .j2_rest_n50_history_d461 import RestN50History, _canonical, _unique
from .j4_automatic_entry_materializer_d448 import _read_owner_bytes
from .j4_private_paper_ws_operator_d425 import _private_directory
from .market_data import ClosedCandle, DataGapError, DataValidationError

SCHEMA = "d518-retrospective-five-minute-trade-bars-v1"
SOURCE = "public_rest_trade_bars_retrieved_after_decision"
QUALITY = "bybit_public_rest_historical_closed_unverified"
FIVE_MS = 300_000
MAX_HOURS = 36
MAX_SYMBOLS = 80
MAX_AGE_MS = 30*24*HOUR_MS
MAX_BYTES = 16_000_000
_NAME = re.compile(r"d518-retro-5m-([0-9]{13})-([0-9a-f]{16})[.]json\Z")
_SYMBOL = re.compile(r"[A-Z0-9]{1,28}USDT\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class IntrahourSeries:
    symbol: str
    anchor_digest: str
    anchor_end_ms: int
    anchor_captured_at_ms: int
    retrieved_at_ms: int
    candles: tuple[ClosedCandle, ...]


@dataclass(frozen=True)
class IntrahourSupplement:
    created_at_ms: int
    digest_sha256: str
    series: tuple[IntrahourSeries, ...]


def capture_plan(histories: tuple[RestN50History, ...]) -> dict:
    """At most one 36-hour page per symbol, without ranking by outcomes."""
    if (type(histories) is not tuple or len(histories)>72
            or any(type(h) is not RestN50History
                   or h.source_mode!="public_rest_observed_unverified"
                   for h in histories)):
        raise DataValidationError("D518 requires original archived memberships")
    if not histories:
        return {}
    by_end = {h.window_end_ms:h for h in histories}
    if len(by_end)!=len(histories):
        raise DataValidationError("D518 duplicate archived hour")
    last = max(by_end)
    plan = {}
    for end in sorted(by_end):
        if end <= last-MAX_HOURS*HOUR_MS:
            continue
        previous = by_end.get(end-HOUR_MS)
        if previous is None:
            continue
        previous_series = dict(previous.series)
        for symbol,bars in by_end[end].series:
            if symbol=="BTCUSDT" or symbol not in previous_series:
                continue
            if len(bars)<2 or bars[-2]!=previous_series[symbol][-1]:
                continue
            if symbol not in plan:
                plan[symbol]=(previous,end-HOUR_MS,end)
            else:
                anchor,start,_=plan[symbol]
                plan[symbol]=(anchor,start,end)
    if len(plan)>MAX_SYMBOLS:
        raise DataValidationError("D518 archive union exceeds bounded research sample")
    return plan


def _parse_series(symbol, record, created):
    keys={"anchor_digest","anchor_end_ms","anchor_captured_at_ms",
          "retrieved_at_ms","start_ms","end_ms","rows"}
    if (type(symbol) is not str or _SYMBOL.fullmatch(symbol) is None
            or type(record) is not dict or set(record)!=keys
            or type(record["anchor_digest"]) is not str
            or _DIGEST.fullmatch(record["anchor_digest"]) is None):
        raise DataValidationError("D518 invalid series identity")
    anchor,captured,received,start,end=(record[k] for k in (
        "anchor_end_ms","anchor_captured_at_ms","retrieved_at_ms","start_ms","end_ms"))
    if (any(type(v) is not int for v in (anchor,captured,received,start,end))
            or not 0<anchor==start<end<=received<=created
            or not anchor<=captured<anchor+HOUR_MS
            or not 0<=received-captured<=MAX_AGE_MS
            or start%HOUR_MS or end%HOUR_MS or end-start>MAX_HOURS*HOUR_MS):
        raise DataValidationError("D518 invalid retrospective capture clock")
    page=stage_bybit_linear_kline(
        {"retCode":0,"result":{"category":"linear","symbol":symbol,"list":record["rows"]}},
        symbol=symbol,quote_currency="USDT",contract_type="LinearPerpetual",
        contract_status="Trading",contract_observed_at_ms=captured,
        observed_at_ms=received,max_contract_age_ms=MAX_AGE_MS,
        interval="5m",start_open_ms=start,end_open_ms=end,
        max_candles=(end-start)//FIVE_MS,
    )
    bars=tuple(ClosedCandle(
        exchange="bybit_v5_public",market="linear_perpetual",symbol=symbol,interval="5m",
        open_time_ms=c.open_time_ms,close_time_ms=c.close_time_ms,
        open=c.open,high=c.high,low=c.low,close=c.close,
        base_volume=c.documented_base_volume,quote_volume=c.documented_quote_turnover,
        quality=QUALITY,
    ) for c in page.candles)
    return IntrahourSeries(symbol,record["anchor_digest"],anchor,captured,received,bars)


def decode_intrahour(raw: bytes, *, now_ms: int) -> IntrahourSupplement:
    if type(raw) is not bytes or not 2<=len(raw)<=MAX_BYTES:
        raise DataValidationError("D518 invalid supplement size")
    try:
        d=json.loads(raw.decode("ascii"),object_pairs_hook=_unique)
    except (ValueError,UnicodeError,TypeError) as exc:
        raise DataValidationError("D518 invalid supplement JSON") from exc
    if (type(d) is not dict or set(d)!={"schema","payload","sha256"}
            or d["schema"]!=SCHEMA or type(d["payload"]) is not dict
            or type(d["sha256"]) is not str
            or _DIGEST.fullmatch(d["sha256"]) is None
            or sha256(_canonical(d["payload"])).hexdigest()!=d["sha256"]):
        raise DataValidationError("D518 invalid supplement digest/schema")
    p=d["payload"]
    if (set(p)!={"source","created_at_ms","series"} or p["source"]!=SOURCE
            or type(p["created_at_ms"]) is not int
            or not 0<p["created_at_ms"]<=now_ms
            or type(p["series"]) is not dict or len(p["series"])>MAX_SYMBOLS):
        raise DataValidationError("D518 invalid supplement payload")
    return IntrahourSupplement(p["created_at_ms"],d["sha256"],tuple(
        _parse_series(s,p["series"][s],p["created_at_ms"]) for s in sorted(p["series"])))


def read_latest_intrahour(directory: Path, *, now_ms: int) -> IntrahourSupplement | None:
    home=_private_directory(directory)
    names=[p.name for p in home.iterdir()
           if (m:=_NAME.fullmatch(p.name)) is not None and int(m[1])<=now_ms]
    if not names:
        return None
    name=max(names)
    result=decode_intrahour(_read_owner_bytes(home,name,MAX_BYTES),now_ms=now_ms)
    if name!=f"d518-retro-5m-{result.created_at_ms}-{result.digest_sha256[:16]}.json":
        raise DataValidationError("D518 file identity mismatch")
    return result


def index_intrahour(histories, supplement, *, now_ms):
    if (type(supplement) is not IntrahourSupplement
            or not 0<supplement.created_at_ms<=now_ms):
        raise DataValidationError("D518 typed nonfuture supplement required")
    anchors={(h.digest_sha256,h.window_end_ms):h for h in histories}
    index={}
    rejected=0
    for series in supplement.series:
        h=anchors.get((series.anchor_digest,series.anchor_end_ms))
        if (h is None or h.captured_at_ms!=series.anchor_captured_at_ms
                or series.symbol not in h.symbols
                or h.source_mode!="public_rest_observed_unverified"
                or series.symbol in index
                or not h.captured_at_ms<=series.retrieved_at_ms<=supplement.created_at_ms):
            rejected+=1
            continue
        index[series.symbol]={c.open_time_ms:c for c in series.candles}
    return index,rejected


def refine_hourly_path(hourly, index):
    """Return 5m only when ALL 12 bars per original hour corroborate OHLC."""
    if not hourly:
        return None
    result=[]
    for h in hourly:
        series=index.get(h.symbol,{})
        bars=tuple(series.get(h.open_time_ms+i*FIVE_MS) for i in range(12))
        if any(c is None for c in bars):
            return None
        if (any(c.symbol!=h.symbol or c.interval!="5m" or c.quality!=QUALITY
                or c.open_time_ms!=h.open_time_ms+i*FIVE_MS
                or c.close_time_ms!=c.open_time_ms+FIVE_MS-1
                for i,c in enumerate(bars))
                or (bars[0].open,max(c.high for c in bars),min(c.low for c in bars),bars[-1].close)
                !=(h.open,h.high,h.low,h.close)):
            return None
        result.extend(bars)
    return tuple(result)


def capture_intrahour(*, directory:Path, histories:tuple[RestN50History,...],
                     allow_public_network:bool, confirm_personal_readonly_research:bool,
                     confirm_region_eligible:bool, confirm_public_data_rights:bool):
    """Bounded single owner job; no write to J1, policy, orders or positions."""
    if (not all(v is True for v in (allow_public_network,confirm_personal_readonly_research,
                                    confirm_region_eligible,confirm_public_data_rights))
            or os.name!="posix" or os.geteuid()==0 or os.geteuid()!=os.getuid()):
        raise DataValidationError("D518 owner and public research opt-ins required")
    home=_private_directory(directory)
    if any(p.startswith("j1-") for p in home.parts):
        raise DataValidationError("D518 no J1 writes")
    plan=capture_plan(histories)
    clock=lambda:time.time_ns()//1_000_000
    started=clock()
    client=BoundedBybitPublicClient(allow_five_minute_research=True)
    records={}
    for symbol,(anchor,start,end) in sorted(plan.items()):
        if clock()>=started+20*60_000:
            raise DataValidationError("D518 capture deadline")
        if not 0<=started-anchor.captured_at_ms<=MAX_AGE_MS or end+1000>started:
            continue
        _,p=client.get(research_five_minute_url(symbol,start,end))
        received=clock()
        if received<started or received>=started+20*60_000:
            raise DataValidationError("D518 capture deadline")
        if (type(p.get("result")) is not dict
                or p["result"].get("symbol")!=symbol or p["result"].get("category")!="linear"):
            raise DataValidationError("D518 provider response identity invalid")
        record={"anchor_digest":anchor.digest_sha256,"anchor_end_ms":anchor.window_end_ms,
                "anchor_captured_at_ms":anchor.captured_at_ms,"retrieved_at_ms":received,
                "start_ms":start,"end_ms":end,"rows":p["result"].get("list")}
        try:
            _parse_series(symbol,record,received)
        except DataGapError:
            continue
        records[symbol]=record
    created=clock()
    payload={"source":SOURCE,"created_at_ms":created,"series":records}
    digest=sha256(_canonical(payload)).hexdigest()
    raw=_canonical({"schema":SCHEMA,"payload":payload,"sha256":digest})
    supplement=decode_intrahour(raw,now_ms=created)
    name=f"d518-retro-5m-{created}-{digest[:16]}.json"
    fd,tmp=tempfile.mkstemp(prefix=".d518-stage-",dir=home)
    try:
        with os.fdopen(fd,"wb") as out:
            out.write(raw)
            out.flush()
            os.fsync(out.fileno())
        os.link(tmp,home/name,follow_symlinks=False)
        dfd=os.open(home,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    finally:
        os.unlink(tmp)
    return supplement,{"schema_version":SCHEMA,"status":"intrahour_supplement_saved",
                       "symbols_requested":len(plan),"symbols_retrieved":len(records),
                       "public_gets":client.requests_attempted,
                       "five_minute_bars":sum(len(s.candles) for s in supplement.series),
                       "retrieved_at_ms":created,"orders_sent":False,"j1_touched":False}
