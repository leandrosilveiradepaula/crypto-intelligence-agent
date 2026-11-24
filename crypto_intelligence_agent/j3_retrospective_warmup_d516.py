"""Optional, separately dated REST warmup for retrospective D512 research.

Never re-date a D461 archive or infer old membership from today's ranking.
One bounded supplement per explicit owner request. Only its older candles
can supplement the original decision archive; subsequent observations and
the universe come from the original D512 archives. No WS or PAPER writes.
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
from .bybit_public_j1_transport import BoundedBybitPublicClient, HOUR_MS
from .j2_rest_n50_history_d461 import (
    RestN50History, fetch_closed_rest_rows, _canonical, _unique,
)
from .j4_automatic_entry_materializer_d448 import _read_owner_bytes
from .j4_private_paper_ws_operator_d425 import _private_directory
from .market_data import ClosedCandle, DataGapError, DataValidationError

SCHEMA = "d516-retrospective-rest-warmup-v1"
SOURCE = "public_rest_retrieved_after_decision"
QUALITY = "bybit_public_rest_historical_closed_unverified"
MAX_SYMBOLS = 80
MAX_HOURS = 122
MAX_BYTES = 4_000_000
MAX_AGE_MS = 30 * 24 * HOUR_MS
_NAME = re.compile(r"d516-retro-warmup-([0-9]{13})-([0-9a-f]{16})[.]json\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_SYMBOL = re.compile(r"[A-Z0-9]{1,28}USDT\Z")


@dataclass(frozen=True)
class WarmupSeries:
    symbol: str
    anchor_digest: str
    anchor_end_ms: int
    anchor_captured_at_ms: int
    retrieved_at_ms: int
    candles: tuple[ClosedCandle, ...]


@dataclass(frozen=True)
class WarmupSupplement:
    created_at_ms: int
    history_hours: int
    digest_sha256: str
    series: tuple[WarmupSeries, ...]


def _anchors(histories, hours):
    """Earliest original member observation among the last 24 paired hours."""
    if (type(histories) is not tuple or len(histories) > 72
            or type(hours) is not int or not 24 <= hours <= MAX_HOURS
            or any(type(h) is not RestN50History
                   or h.source_mode != "public_rest_observed_unverified"
                   for h in histories)):
        raise DataValidationError("D516 observed frozen archives required")
    by_end = {h.window_end_ms: h for h in histories}
    if len(by_end) != len(histories):
        raise DataValidationError("D516 duplicate archive hour")
    ends = sorted(e for e in by_end if e + HOUR_MS in by_end)[-24:]
    first = {}
    for end in ends:
        h = by_end[end]
        for symbol, bars in h.series:
            if symbol != "BTCUSDT" and symbol not in first:
                first[symbol] = (h, bars)
    need = {s: (h, bars) for s, (h, bars) in first.items()
            if len(bars) < hours}
    if len(need) > MAX_SYMBOLS:
        raise DataValidationError("D516 cohort exceeds bounded warmup request")
    return need


def _series(symbol, record, hours, created):
    keys = {"anchor_digest", "anchor_end_ms", "anchor_captured_at_ms",
            "retrieved_at_ms", "rows"}
    if (type(symbol) is not str or _SYMBOL.fullmatch(symbol) is None
            or type(record) is not dict or set(record) != keys
            or type(record["anchor_digest"]) is not str
            or _DIGEST.fullmatch(record["anchor_digest"]) is None):
        raise DataValidationError("D516 invalid historical warmup series")
    end = record["anchor_end_ms"]
    captured = record["anchor_captured_at_ms"]
    retrieved = record["retrieved_at_ms"]
    if (any(type(v) is not int for v in (end, captured, retrieved))
            or end <= hours * HOUR_MS or end % HOUR_MS
            or not end <= captured < end + HOUR_MS
            or not captured <= retrieved <= created
            or retrieved - captured > MAX_AGE_MS):
        raise DataValidationError("D516 invalid historical retrieval clock")
    page = stage_bybit_linear_kline(
        {"retCode": 0, "result": {"category": "linear", "symbol": symbol,
                                 "list": record["rows"]}},
        symbol=symbol, quote_currency="USDT",
        contract_type="LinearPerpetual", contract_status="Trading",
        contract_observed_at_ms=captured, observed_at_ms=retrieved,
        max_contract_age_ms=MAX_AGE_MS, interval="1h",
        start_open_ms=end-hours*HOUR_MS, end_open_ms=end, max_candles=hours,
    )
    candles = tuple(ClosedCandle(
        exchange="bybit_v5_public", market="linear_perpetual", symbol=symbol,
        interval="1h", open_time_ms=c.open_time_ms, close_time_ms=c.close_time_ms,
        open=c.open, high=c.high, low=c.low, close=c.close,
        base_volume=c.documented_base_volume, quote_volume=c.documented_quote_turnover,
        quality=QUALITY,
    ) for c in page.candles)
    return WarmupSeries(symbol, record["anchor_digest"], end, captured, retrieved, candles)


def decode_supplement(raw: bytes, *, now_ms: int) -> WarmupSupplement:
    if type(raw) is not bytes or not 2 <= len(raw) <= MAX_BYTES:
        raise DataValidationError("D516 invalid supplement size")
    try:
        doc = json.loads(raw.decode("ascii"), object_pairs_hook=_unique)
    except (ValueError, UnicodeError, TypeError) as exc:
        raise DataValidationError("D516 invalid supplement JSON") from exc
    if (type(doc) is not dict or set(doc) != {"schema", "payload", "sha256"}
            or doc["schema"] != SCHEMA or type(doc["payload"]) is not dict
            or type(doc["sha256"]) is not str
            or _DIGEST.fullmatch(doc["sha256"]) is None
            or sha256(_canonical(doc["payload"])).hexdigest() != doc["sha256"]):
        raise DataValidationError("D516 supplement digest/schema mismatch")
    p = doc["payload"]
    if (set(p) != {"source", "created_at_ms", "history_hours", "series"}
            or p["source"] != SOURCE
            or type(p["created_at_ms"]) is not int
            or not 0 < p["created_at_ms"] <= now_ms
            or type(p["history_hours"]) is not int
            or not 24 <= p["history_hours"] <= MAX_HOURS
            or type(p["series"]) is not dict
            or len(p["series"]) > MAX_SYMBOLS):
        raise DataValidationError("D516 invalid supplement payload")
    return WarmupSupplement(p["created_at_ms"], p["history_hours"], doc["sha256"],
                            tuple(_series(s, p["series"][s], p["history_hours"],
                                          p["created_at_ms"]) for s in sorted(p["series"])))


def seed_by_anchor(histories: tuple[RestN50History, ...],
                   supplement: WarmupSupplement, *, now_ms: int) -> tuple[dict, int]:
    """Only corroborated older rows, inserted AT their archive's decision hour.

    The complete original overlap must match economically. A disappeared
    anchor or revised row excludes that symbol's supplement; no archive is
    changed, no later candle is used to make an earlier decision.
    """
    if (type(supplement) is not WarmupSupplement
            or not 0 < supplement.created_at_ms <= now_ms):
        raise DataValidationError("D516 typed nonfuture supplement required")
    # Fixture callers can construct synthetic digests; real archives bind
    # membership and end time in the digest. Key by both to avoid ambiguity.
    index = {(h.digest_sha256, h.window_end_ms): h for h in histories}
    seeds = {}
    rejected = 0
    seen = set()
    for series in supplement.series:
        h = index.get((series.anchor_digest, series.anchor_end_ms))
        original = dict(h.series).get(series.symbol) if h is not None else None
        cs = series.candles
        if (series.symbol in seen or h is None or original is None
                or h.captured_at_ms != series.anchor_captured_at_ms
                or h.source_mode != "public_rest_observed_unverified"
                or len(cs) != supplement.history_hours
                or len(original) >= len(cs)
                or tuple(cs[-len(original):]) != original
                or not h.captured_at_ms <= series.retrieved_at_ms <= supplement.created_at_ms):
            rejected += 1
            continue
        seen.add(series.symbol)
        seeds.setdefault(h.window_end_ms, []).extend(cs[:-len(original)])
    return seeds, rejected


def read_latest_supplement(directory: Path, *, now_ms: int) -> WarmupSupplement | None:
    home = _private_directory(directory)
    files = []
    for p in home.iterdir():
        m = _NAME.fullmatch(p.name)
        if m is not None and int(m[1]) <= now_ms:
            files.append((int(m[1]), p.name))
    if not files:
        return None
    _, name = max(files)
    s = decode_supplement(_read_owner_bytes(home, name, MAX_BYTES), now_ms=now_ms)
    if name != f"d516-retro-warmup-{s.created_at_ms}-{s.digest_sha256[:16]}.json":
        raise DataValidationError("D516 supplement file identity mismatch")
    return s


def capture_retrospective_warmup(
    *, directory: Path, histories: tuple[RestN50History, ...], history_hours: int,
    allow_public_network: bool, confirm_personal_readonly_research: bool,
    confirm_region_eligible: bool, confirm_public_data_rights: bool,
) -> tuple[WarmupSupplement, dict]:
    """Explicit one-shot, at most 160 public GETs, no retry or live data write."""
    if (not all(v is True for v in (allow_public_network,
                                    confirm_personal_readonly_research,
                                    confirm_region_eligible, confirm_public_data_rights))
            or os.name != "posix" or not hasattr(os, "geteuid")
            or os.geteuid() == 0 or os.geteuid() != os.getuid()):
        raise DataValidationError("D516 explicit public research opt-ins and owner required")
    home = _private_directory(directory)
    if any(p.startswith("j1-") for p in home.parts):
        raise DataValidationError("D516 must not write in J1")
    plan = _anchors(histories, history_hours)
    clock = lambda: time.time_ns() // 1_000_000
    started = clock()
    client = BoundedBybitPublicClient()
    rows = {}
    omitted = 0
    for symbol, (anchor, original) in sorted(plan.items()):
        if clock() >= started+30*60_000:
            raise DataValidationError("D516 bounded capture deadline reached")
        if not 0 <= started-anchor.captured_at_ms <= MAX_AGE_MS:
            omitted += 1
            continue
        try:
            raw = fetch_closed_rest_rows(
                client=client, symbol=symbol,
                start_ms=anchor.window_end_ms-history_hours*HOUR_MS,
                end_ms=anchor.window_end_ms, contract_observed_at_ms=anchor.captured_at_ms,
                wall_ms=clock, max_contract_age_ms=MAX_AGE_MS,
                not_before_ms=started, not_after_ms=started+30*60_000,
            )
            retrieved = clock()
            record = {"anchor_digest": anchor.digest_sha256,
                      "anchor_end_ms": anchor.window_end_ms,
                      "anchor_captured_at_ms": anchor.captured_at_ms,
                      "retrieved_at_ms": retrieved, "rows": raw}
            parsed = _series(symbol, record, history_hours, retrieved)
            if tuple(parsed.candles[-len(original):]) != original:
                omitted += 1
                continue
            rows[symbol] = record
        except DataGapError:
            # New listings or incomplete pages: no guessed prices.
            # Transport rate limits/access failures propagate without retry.
            omitted += 1
    created = clock()
    payload = {"source": SOURCE, "created_at_ms": created,
               "history_hours": history_hours, "series": rows}
    digest = sha256(_canonical(payload)).hexdigest()
    raw = _canonical({"schema": SCHEMA, "payload": payload, "sha256": digest})
    supplement = decode_supplement(raw, now_ms=created)
    name = f"d516-retro-warmup-{created}-{digest[:16]}.json"
    fd, tmp = tempfile.mkstemp(prefix=".d516-stage-", dir=home)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(raw)
            out.flush()
            os.fsync(out.fileno())
        os.link(tmp, home/name, follow_symlinks=False)
        dfd = os.open(home, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    finally:
        os.unlink(tmp)
    return supplement, {
        "schema_version": SCHEMA, "status": "retrospective_warmup_saved",
        "requested_history_hours": history_hours, "symbols_requested": len(plan),
        "symbols_corroborated": len(rows), "symbols_omitted": omitted,
        "public_gets": client.requests_attempted, "retrieved_at_ms": created,
        "retrospective_not_contemporaneous": True, "orders_sent": False,
        "j1_touched": False, "out_of_sample_results_validated": False,
    }
