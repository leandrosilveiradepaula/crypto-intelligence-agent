"""D528: private, resumable long-history research, not a historical marketwide Top50.

Freeze a current provisional D451 cohort; store only genuinely returned closed
REST bars, never manufacture D461 decision snapshots or WS confirmations.
Each 30-day shard uses the existing transactional store/backfill/checkpoint.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext, Context
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3

from .backfill import HistoricalBackfill, _validate_exact_page
from .bybit_linear_candle_research import stage_bybit_linear_kline
from .bybit_public_j1_transport import BoundedBybitPublicClient, research_history_kline_url, HOUR_MS
from .j2_dynamic_public_n50_d451 import DynamicPublicN50
from .j4_private_paper_ws_operator_d425 import _owner_file, _private_directory
from .j4_automatic_entry_materializer_d448 import _read_owner_bytes, _atomic_private_write
from .market_data import ClosedCandle, DataGapError, DataValidationError, interval_duration_ms
from .storage import SQLiteMarketDataStore, _candle_from_row

SCHEMA = "d528-private-long-history-plan-v1"
EXCHANGE = "bybit_v5_public"
MARKET = "linear_perpetual"
QUALITY = "bybit_public_rest_historical_closed_unverified"
SOURCE = "public_rest_retrospective_d528"
DAY = 24 * HOUR_MS
SHARD = 30 * DAY
MAX_DAYS = 730
MAX_PLAN_AGE_MS = 30 * DAY
MAX_BATCH_MS = 30 * 60_000
MAX_BATCH_GETS = 400
PAGE = 1000
MIN_FREE_BYTES = 1024**3
PLAN_FILE = "d528-plan.json"
_SYMBOL = re.compile(r"[A-Z0-9]{1,28}USDT\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")


def canonical(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=True,
                      separators=(",", ":"), allow_nan=False).encode("ascii")


@dataclass(frozen=True)
class HistoryPlan:
    cutoff_ms: int
    observed_at_ms: int
    cohort_sha256: str
    members: tuple[tuple[str, int], ...]
    source_mode: str

    def payload(self):
        return {"cutoff_ms": self.cutoff_ms, "observed_at_ms": self.observed_at_ms,
                "cohort_sha256": self.cohort_sha256,
                "members": [list(m) for m in self.members], "source_mode": self.source_mode}

    @property
    def digest(self):
        return sha256(canonical(self.payload())).hexdigest()

    def encode(self):
        return canonical({"schema": SCHEMA, "payload": self.payload(), "sha256": self.digest})


def decode_plan(raw: bytes) -> HistoryPlan:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise DataValidationError("D528 duplicate plan key")
            result[key] = value
        return result
    if type(raw) is not bytes or not 1 <= len(raw) <= 32768:
        raise DataValidationError("D528 plan size")
    try:
        obj = json.loads(raw, object_pairs_hook=unique)
        if type(obj) is not dict or set(obj) != {"schema", "payload", "sha256"} or obj["schema"] != SCHEMA:
            raise DataValidationError("D528 plan envelope")
        p = obj["payload"]
        if type(p) is not dict or set(p) != {"cutoff_ms","observed_at_ms","cohort_sha256","members","source_mode"}:
            raise DataValidationError("D528 plan shape")
        if (type(p["cutoff_ms"]) is not int or type(p["observed_at_ms"]) is not int
                or p["cutoff_ms"] % DAY or not MAX_DAYS*DAY < p["cutoff_ms"] < p["observed_at_ms"]
                or p["observed_at_ms"]-p["cutoff_ms"] > 2*DAY
                or type(p["cohort_sha256"]) is not str or _SHA.fullmatch(p["cohort_sha256"]) is None
                or p["source_mode"] not in ("public_rest_observed_unverified","injected_offline_protocol_replay")
                or type(p["members"]) is not list or not 1 <= len(p["members"]) <= 50
                or (p["source_mode"] == "public_rest_observed_unverified" and len(p["members"]) != 50)):
            raise DataValidationError("D528 invalid cohort or cutoff")
        for m in p["members"]:
            if (type(m) is not list or len(m) != 2 or type(m[0]) is not str
                    or _SYMBOL.fullmatch(m[0]) is None or type(m[1]) is not int
                    or not 0 < m[1] <= p["observed_at_ms"]):
                raise DataValidationError("D528 invalid member or launch")
        names = [m[0] for m in p["members"]]
        if names != sorted(set(names)) or "BTCUSDT" not in names:
            raise DataValidationError("D528 unique sorted cohort and BTC required")
        plan = HistoryPlan(p["cutoff_ms"], p["observed_at_ms"], p["cohort_sha256"],
                           tuple(tuple(m) for m in p["members"]), p["source_mode"])
        if obj["sha256"] != plan.digest or raw != plan.encode():
            raise DataValidationError("D528 plan digest/canonical mismatch")
        return plan
    except (ValueError, TypeError, KeyError, UnicodeError) as exc:
        raise DataValidationError("D528 malformed plan") from exc


def freeze_cohort(snapshot: DynamicPublicN50) -> HistoryPlan:
    if type(snapshot) is not DynamicPublicN50:
        raise DataValidationError("D528 typed D451 cohort required")
    observed = snapshot.ticker_received_at_ms
    cutoff = ((observed - 2000)//DAY)*DAY
    return decode_plan(HistoryPlan(cutoff, observed, snapshot.fingerprint_sha256,
        tuple(sorted((m.symbol, m.launch_time_ms) for m in snapshot.ranked)),
        snapshot.source_mode).encode())


def load_plan(home: Path) -> HistoryPlan:
    return decode_plan(_read_owner_bytes(_private_directory(home), PLAN_FILE, 32768))


def save_plan(home: Path, plan: HistoryPlan):
    # The CLI holds the exclusive history lock. Never replace a cohort.
    home = _private_directory(home)
    if (home/PLAN_FILE).exists() or (home/PLAN_FILE).is_symlink():
        raise DataValidationError("D528 cohort already frozen")
    _atomic_private_write(home, PLAN_FILE, plan.encode())


def windows(plan, days, interval):
    """Fixed boundaries anchored at cutoff. Extend backwards, never redownload.
    The final partial 30-day shard is collected in full (up to 730 days total).
    """
    if type(days) is not int or not 1 <= days <= MAX_DAYS or interval not in ("1h","5m"):
        raise DataValidationError("D528 invalid days or interval")
    duration = interval_duration_ms(interval)
    for i in range((days+29)//30):
        end = plan.cutoff_ms - i*SHARD
        start = max(end-SHARD, plan.cutoff_ms-MAX_DAYS*DAY)
        for symbol, launch in plan.members:
            first = max(start, ((launch+duration-1)//duration)*duration)
            if first < end:
                yield start, end, symbol, first


def shard_path(home, plan, start, interval):
    return home / ("d528-"+plan.digest[:16]+"-"+str(start)+"-"+interval+".sqlite")


class BatchLimit(Exception):
    pass


class ProviderGap(DataGapError):
    pass


class HistorySource:
    def __init__(self, plan, client, wall_ms, started, max_gets, home):
        self.plan, self.client, self.wall_ms = plan, client, wall_ms
        self.started, self.max_gets, self.home = started, max_gets, home
        self.initial_requests = client.requests_attempted

    @property
    def gets(self):
        return self.client.requests_attempted - self.initial_requests

    def closed_candles(self, symbol, interval, *, observed_at_ms,
                       start_time_ms=None, end_time_ms=None, limit=PAGE):
        if (self.gets >= self.max_gets or self.wall_ms() >= self.started+MAX_BATCH_MS):
            raise BatchLimit
        if shutil.disk_usage(self.home).free < MIN_FREE_BYTES:
            raise BatchLimit
        if (type(start_time_ms) is not int or type(end_time_ms) is not int
                or symbol not in dict(self.plan.members)
                or end_time_ms >= self.plan.cutoff_ms):
            raise DataValidationError("D528 invalid historical page")
        end = end_time_ms+1
        duration = interval_duration_ms(interval)
        if not 1 <= (end-start_time_ms)//duration <= min(PAGE,limit):
            raise DataValidationError("D528 page exceeds budget")
        _, payload = self.client.get(research_history_kline_url(symbol, interval, start_time_ms, end))
        received = self.wall_ms()
        if not self.started <= received < self.started+MAX_BATCH_MS+60_000:
            raise DataValidationError("D528 invalid retrieval clock")
        try:
            page = stage_bybit_linear_kline(payload, symbol=symbol, quote_currency="USDT",
                contract_type="LinearPerpetual", contract_status="Trading",
                contract_observed_at_ms=self.plan.observed_at_ms, observed_at_ms=received,
                max_contract_age_ms=MAX_PLAN_AGE_MS, interval=interval,
                start_open_ms=start_time_ms, end_open_ms=end)
        except DataGapError as exc:
            # Not a local checkpoint failure; no synthetic candles and no retry
            # in this batch. Other independent members/shards can progress.
            raise ProviderGap("D528 provider page incomplete") from exc
        return tuple(ClosedCandle(EXCHANGE, MARKET, symbol, interval,
                    c.open_time_ms,c.close_time_ms,c.open,c.high,c.low,c.close,
                    c.documented_base_volume,c.documented_quote_turnover,QUALITY)
                    for c in page.candles)


def _store(path):
    # Dedicated owner directory, never a PAPER or J1 database. Existing shards
    # must be private regular files; a new shard is created exclusively 0600.
    if path.exists() or path.is_symlink():
        if os.name == "posix":
            os.close(_owner_file(path.parent,path.name))
        elif path.is_symlink() or not path.is_file():
            raise DataValidationError("D528 unsafe shard")
    else:
        fd = os.open(path, os.O_CREAT|os.O_EXCL|os.O_WRONLY, 0o600)
        os.close(fd)
    if (path.with_name(path.name+"-journal").is_symlink()
            or path.with_name(path.name+"-wal").is_symlink()
            or path.with_name(path.name+"-shm").is_symlink()):
        raise DataValidationError("D528 unsafe SQLite sidecar")
    return SQLiteMarketDataStore(path)


def collect_batch(*, home, plan, days, interval, client, wall_ms, max_gets=MAX_BATCH_GETS):
    """One bounded batch. A successful partial report is NOT full coverage."""
    plan = decode_plan(plan.encode())
    started = wall_ms()
    if (type(max_gets) is not int or not 1 <= max_gets <= MAX_BATCH_GETS
            or not plan.observed_at_ms <= started < plan.observed_at_ms+MAX_PLAN_AGE_MS
            or type(client) is not BoundedBybitPublicClient or not client.allow_long_history_research
            or (client.transport is None and plan.source_mode != "public_rest_observed_unverified")):
        raise DataValidationError("D528 invalid batch budget/source/plan age")
    source = HistorySource(plan, client, wall_ms, started, max_gets, home)
    duration = interval_duration_ms(interval)
    jobs = tuple(windows(plan, days, interval))
    stats = {s:{"expected":0,"saved":0,"complete_shards":0,"gap_shards":0}
             for s,_ in plan.members}
    for _, end, symbol, first in jobs:
        stats[symbol]["expected"] += (end-first)//duration
    store = None
    last = None
    limited = False
    for start,end,symbol,first in jobs:
        path = shard_path(home, plan, start, interval)
        if path != last:
            store = None
            last = path
            if not path.exists() and not path.is_symlink() and (limited or source.gets >= max_gets):
                limited = True
            else:
                if not path.exists() and shutil.disk_usage(home).free < MIN_FREE_BYTES:
                    limited = True
                else:
                    store = _store(path)
        if store is None:
            continue
        row = stats[symbol]
        try:
            HistoricalBackfill(source, store, page_size=PAGE, contract_version=plan.digest).run(
                exchange=EXCHANGE, market=MARKET, symbol=symbol, interval=interval,
                start_open_ms=first,end_open_ms=end,observed_at_ms=started,source_name=SOURCE)
        except BatchLimit:
            limited = True
        except ProviderGap:
            row["gap_shards"] += 1
        q = store.quality_report(exchange=EXCHANGE,market=MARKET,symbol=symbol,interval=interval,
                                 start_open_ms=first,end_open_ms=end)
        row["saved"] += q.persisted_candles
        row["complete_shards"] += int(q.complete)
    expected = sum(x["expected"] for x in stats.values())
    saved = sum(x["saved"] for x in stats.values())
    complete = sum(x["complete_shards"] for x in stats.values())
    return {"schema_version":"d528-long-history-coverage-v1",
            "status":"coverage_complete" if complete==len(jobs) and expected>0 else "coverage_partial",
            "plan_sha256":plan.digest, "requested_days":days,
            "planned_days":min(MAX_DAYS,((days+29)//30)*30),
            "cutoff_ms":plan.cutoff_ms,"interval":interval,"cohort_size":len(plan.members),
            "expected_candles_after_launch":expected,"saved_candles":saved,
            "missing_candles":expected-saved,"complete_member_shards":complete,
            "expected_member_shards":len(jobs),"public_gets":source.gets,
            "batch_limit_reached":limited, "by_symbol":stats,
            "cohort_origin":"current_D451_provisional_survivors",
            "historical_marketwide_top50_verified":False,
            "retrospective_not_contemporaneous":True,"orders_sent":False,
            "profile_modified":False,"j1_touched":False}


def read_window(home, plan, symbol, interval, start, end):
    """Read exactly one contiguous window across shards; never create a DB."""
    if (interval not in ("1h","5m") or symbol not in dict(plan.members)
            or type(start) is not int or type(end) is not int
            or not plan.cutoff_ms-MAX_DAYS*DAY <= start < end <= plan.cutoff_ms):
        raise DataValidationError("D528 read range outside frozen plan")
    duration = interval_duration_ms(interval)
    if start % duration or end % duration:
        raise DataValidationError("D528 read grid")
    result = []
    cursor = start
    while cursor < end:
        index = (plan.cutoff_ms-1-cursor)//SHARD
        shard_end = plan.cutoff_ms-index*SHARD
        shard_start = max(shard_end-SHARD,plan.cutoff_ms-MAX_DAYS*DAY)
        path = shard_path(home,plan,shard_start,interval)
        if not path.is_file() or path.is_symlink():
            raise DataGapError("D528 history shard missing")
        if os.name == "posix":
            os.close(_owner_file(home,path.name))
        until = min(end,shard_end)
        with sqlite3.connect(path.resolve().as_uri()+"?mode=ro",uri=True) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute("SELECT * FROM candles WHERE exchange=? AND market=? AND symbol=? AND interval=? AND open_time_ms>=? AND open_time_ms<? ORDER BY open_time_ms",
                (EXCHANGE,MARKET,symbol,interval,cursor,until)).fetchall()
        bars = tuple(_candle_from_row(row) for row in rows)
        _validate_exact_page(bars,EXCHANGE,MARKET,symbol,interval,cursor,until,duration)
        if any(c.quality != QUALITY for c in bars):
            raise DataValidationError("D528 historical provenance mismatch")
        result.extend(bars)
        cursor = until
    return tuple(result)


def rank_closed_cohort(plan, decision_ms, series, top_n=50):
    """Causal turnover ranking INSIDE the frozen survivor cohort, not past N50.
    Require all launch-eligible members' full prior 24h; do not rank partial data.
    Future bars in the supplied mapping do not influence the result.
    """
    if (type(decision_ms) is not int or decision_ms%HOUR_MS
            or not plan.cutoff_ms-MAX_DAYS*DAY+DAY <= decision_ms <= plan.cutoff_ms
            or type(top_n) is not int or not 1 <= top_n <= 50):
        raise DataValidationError("D528 rank decision outside plan")
    ranked = []
    start = decision_ms-DAY
    with localcontext(Context(prec=100)):
        for symbol,launch in plan.members:
            if launch > start:
                continue
            bars = tuple(b for b in series.get(symbol,()) if start<=b.open_time_ms<decision_ms)
            _validate_exact_page(bars,EXCHANGE,MARKET,symbol,"1h",start,decision_ms,HOUR_MS)
            if any(b.quality != QUALITY or b.quote_volume < 0 for b in bars):
                raise DataValidationError("D528 rank invalid bar provenance/turnover")
            ranked.append((symbol,sum((b.quote_volume for b in bars),Decimal(0))))
    return tuple(sorted(ranked,key=lambda x:(-x[1],x[0]))[:top_n])
