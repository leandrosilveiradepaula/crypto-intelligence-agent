"""D461: complete REST 24h N50 historical research bootstrap, separate from WS.

One immutable, SHA-256-checksummed owner-only snapshot of 50 complete REST
windows. Public REST historical candles are NEVER rewritten as WS confirm=true
or appended to the WS-only D451 journal. One bounded GET per symbol; no
private account endpoints, trading, unbounded retries, or funding claims.

All 50 rows must validate before ANY snapshot is committed. A frozen
snapshot can be reread/audited without another HTTP request after restart.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext, Context
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import time
import tempfile

from .bybit_linear_candle_research import stage_bybit_linear_kline
from .bybit_public_j1_transport import (
    BoundedBybitPublicClient, kline_url, HOUR_MS,
)
from .j2_dynamic_public_n50_d451 import DynamicPublicN50
from .j4_private_paper_ws_operator_d425 import _private_directory
from .j4_automatic_entry_materializer_d448 import (
    _read_owner_bytes,
)
from .market_data import ClosedCandle, DataGapError, DataValidationError

_SCHEMA = "d461-public-rest-n50-24h-history-v1"
_SOURCE = "public_rest_historical_closed_unverified"
_QUALITY = "bybit_public_rest_historical_closed_unverified"
_WINDOW = 24
_MAX_BYTES = 500_000
_DIGEST = re.compile(r"[a-f0-9]{64}\Z")


def _canonical(value: dict) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


@dataclass(frozen=True)
class RestN50History:
    scope_sha256: str
    window_end_ms: int
    captured_at_ms: int
    digest_sha256: str
    source_mode: str
    series: tuple[tuple[str, tuple[ClosedCandle, ...]], ...]
    snapshot_file: Path | None = None

    @property
    def symbols(self) -> tuple[str, ...]:
        return tuple(symbol for symbol, _ in self.series)

    def sanitized_report(self) -> dict:
        return {
            "schema_version": _SCHEMA,
            "status": "historical_rest_n50_24h_research_ready",
            "eligible_members": len(self.series),
            "validated_closed_candles": sum(len(bars) for _, bars in self.series),
            "window_end_ms": self.window_end_ms,
            "captured_at_ms": self.captured_at_ms,
            "sha256": self.digest_sha256,
            "source_mode": self.source_mode,
            "provenance": _SOURCE,
            "websocket_confirmed_candles": 0,
            "real_time_market_data_verified": False,
            "source_authenticated": False,
            "marketwide_crypto_identity_verified": False,
            "approved_for_live_trading": False,
            "orders_sent": False,
            "j1_touched": False,
        }


def _name(fingerprint: str, until: int) -> str:
    if (type(fingerprint) is not str or _DIGEST.fullmatch(fingerprint) is None
            or type(until) is not int or until <= 0
            or until % HOUR_MS):
        raise DataValidationError("D461 exact cohort fingerprint and hour required")
    return "rest-history-d461-" + fingerprint[:18] + "-" + str(until) + ".json"


def _decode(envelope: dict, *, snapshot: DynamicPublicN50 | None,
            end_ms: int, path: Path | None) -> RestN50History:
    if (type(envelope) is not dict or set(envelope) != {"schema", "payload", "sha256"}
            or envelope["schema"] != _SCHEMA
            or type(envelope["sha256"]) is not str
            or _DIGEST.fullmatch(envelope["sha256"]) is None
            or type(envelope["payload"]) is not dict
            or sha256(_canonical(envelope["payload"])).hexdigest() != envelope["sha256"]):
        raise DataGapError("D461 invalid or tampered immutable REST history")
    p = envelope["payload"]
    if (set(p) != {"cohort_sha256", "window_end_ms", "captured_at_ms",
                    "member_symbols", "source_mode", "rows"}
            or type(p["cohort_sha256"]) is not str
            or _DIGEST.fullmatch(p["cohort_sha256"]) is None
            or p["window_end_ms"] != end_ms
            or type(p["captured_at_ms"]) is not int
            or not end_ms <= p["captured_at_ms"] < end_ms + HOUR_MS
            or p["source_mode"] not in (
                "public_rest_observed_unverified",
                "injected_offline_protocol_replay",
            )
            or type(p["member_symbols"]) is not list
            or len(p["member_symbols"]) != 50
            or any(type(x) is not str for x in p["member_symbols"])
            or len(set(p["member_symbols"])) != 50
            or p["member_symbols"] != sorted(p["member_symbols"])
            or type(p["rows"]) is not dict
            or set(p["rows"]) != set(p["member_symbols"])
            or len(p["rows"]) != 50
            or (snapshot is not None and (
                p["cohort_sha256"] != snapshot.fingerprint_sha256
                or p["source_mode"] != snapshot.source_mode
                or p["member_symbols"] != sorted(snapshot.symbols)
                or snapshot.scope.observed_at_ms > p["captured_at_ms"]
            ))):
        raise DataGapError("D461 REST history scope/window changed")
    series = []
    for symbol in p["member_symbols"]:
        raw = p["rows"][symbol]
        if (type(raw) is not list or len(raw) != _WINDOW
                or any(type(row) is not list or len(row) != 7
                       or any(type(item) is not str for item in row) for row in raw)):
            raise DataGapError("D461 incomplete or untyped historical page")
        page = stage_bybit_linear_kline(
            {"retCode": 0, "result": {
                "category": "linear", "symbol": symbol, "list": raw,
            }},
            symbol=symbol, quote_currency="USDT",
            contract_type="LinearPerpetual", contract_status="Trading",
            # A frozen historical read must NOT be re-dated to a fresh
            # current ticker catalog: do not rely on live N50 membership for
            # replays. Historical-only quality never authorizes AUTO2.
            contract_observed_at_ms=(
                snapshot.scope.observed_at_ms if snapshot is not None
                else p["captured_at_ms"]
            ),
            observed_at_ms=p["captured_at_ms"],
            max_contract_age_ms=86_400_000,
            interval="1h", start_open_ms=end_ms-_WINDOW*HOUR_MS,
            end_open_ms=end_ms, max_candles=_WINDOW,
        )
        bars = tuple(ClosedCandle(
            exchange="bybit_v5_public", market="linear_perpetual", symbol=symbol,
            interval="1h", open_time_ms=bar.open_time_ms,
            close_time_ms=bar.close_time_ms,
            open=bar.open, high=bar.high, low=bar.low, close=bar.close,
            base_volume=bar.documented_base_volume,
            quote_volume=bar.documented_quote_turnover,
            quality=_QUALITY,
        ) for bar in page.candles)
        series.append((symbol, bars))
    return RestN50History(
        p["cohort_sha256"], end_ms, p["captured_at_ms"],
        envelope["sha256"], p["source_mode"], tuple(series), path,
    )


def capture_rest_n50_24h(
    *, snapshot: DynamicPublicN50, private_j2_directory: Path,
    allow_public_network: bool = False,
    confirm_personal_readonly_research: bool = False,
    confirm_region_eligible: bool = False,
    confirm_public_data_rights: bool = False,
    client: BoundedBybitPublicClient | None = None,
    wall_ms=None,
) -> RestN50History:
    """Capture 50 complete rows in one UTC window with atomic all-or-none write.

    The existing J1 bounded GET helper is used ONLY as transport; none of
    J1's state/DB/timers are accessed. Injected offline captures are marked.
    """
    flags = (allow_public_network, confirm_personal_readonly_research,
             confirm_region_eligible, confirm_public_data_rights)
    if any(type(v) is not bool for v in flags) or not all(flags):
        raise DataValidationError("D461 four explicit public research opt-ins required")
    if (type(snapshot) is not DynamicPublicN50
            or len(snapshot.symbols) != 50
            or not isinstance(private_j2_directory, Path)
            or any(s.startswith("j1-") for s in private_j2_directory.parts)):
        raise DataValidationError("D461 requires exact N50 and distinct J2 owner scope")
    home = _private_directory(private_j2_directory)
    if snapshot.source_mode not in (
        "public_rest_observed_unverified", "injected_offline_protocol_replay",
    ):
        raise DataValidationError("D461 unsupported market provenance")
    injected = client is not None
    if injected:
        if (type(client) is not BoundedBybitPublicClient
                or client.transport is None or not callable(wall_ms)
                or snapshot.source_mode != "injected_offline_protocol_replay"):
            raise DataValidationError("D461 injected REST must be separately labeled offline")
    else:
        if (wall_ms is not None or snapshot.source_mode != "public_rest_observed_unverified"
                or os.name != "posix" or not hasattr(os,"geteuid")
                or os.geteuid() == 0):
            raise DataValidationError("D461 public REST requires nonroot real owner")
        wall_ms = lambda: time.time_ns() // 1_000_000
        client = BoundedBybitPublicClient()
    started = wall_ms()
    if type(started) is not int or started < snapshot.ticker_received_ms:
        raise DataValidationError("D461 REST history cannot predate N50 snapshot")
    end_ms = started // HOUR_MS * HOUR_MS
    if end_ms <= 0 or started - snapshot.ticker_received_ms > 300_000:
        raise DataValidationError("D461 fresh public N50 membership required")
    filename = _name(snapshot.fingerprint_sha256, end_ms)
    path = home / filename
    if path.exists() or path.is_symlink():
        # A later N50 ticker refresh must NOT re-date the first historical
        # REST capture. Reuse frozen owner bytes when the exact membership,
        # source mode and UTC hour still match, without new network GETs.
        frozen = reopen_frozen_rest_n50_for_research(
            private_j2_directory=home, filename=filename,
        )
        if (frozen.scope_sha256 != snapshot.fingerprint_sha256
                or frozen.source_mode != snapshot.source_mode
                or frozen.window_end_ms != end_ms):
            raise DataGapError("D461 frozen cohort cannot be relabelled")
        return frozen
    rows = {}
    for symbol in sorted(snapshot.symbols):
        _, payload = client.get(kline_url(symbol, end_ms-_WINDOW*HOUR_MS, end_ms))
        received = wall_ms()
        if (type(received) is not int or received < started
                or received >= end_ms + HOUR_MS):
            raise DataGapError("D461 UTC window changed during REST capture")
        validated = stage_bybit_linear_kline(
            payload, symbol=symbol, quote_currency="USDT",
            contract_type="LinearPerpetual", contract_status="Trading",
            contract_observed_at_ms=snapshot.scope.observed_at_ms,
            observed_at_ms=received, max_contract_age_ms=86_400_000,
            interval="1h", start_open_ms=end_ms-_WINDOW*HOUR_MS,
            end_open_ms=end_ms, max_candles=_WINDOW,
        )
        rows[symbol] = [[
            str(c.open_time_ms), format(c.open, "f"),
            format(c.high, "f"), format(c.low, "f"),
            format(c.close, "f"), format(c.documented_base_volume, "f"),
            format(c.documented_quote_turnover, "f"),
        ] for c in reversed(validated.candles)]
    last = wall_ms()
    if type(last) is not int or last >= end_ms + HOUR_MS:
        raise DataGapError("D461 cohort REST capture crossed UTC window")
    p = {"cohort_sha256": snapshot.fingerprint_sha256,
         "window_end_ms": end_ms, "captured_at_ms": last,
         "member_symbols": sorted(snapshot.symbols),
         "source_mode": snapshot.source_mode, "rows": rows}
    envelope = {"schema": _SCHEMA, "payload": p,
                "sha256": sha256(_canonical(p)).hexdigest()}
    raw = _canonical(envelope)
    if len(raw) > _MAX_BYTES:
        raise DataValidationError("D461 historical snapshot size exceeded")
    # Validate exactly what the immutable reader will later trust, before
    # any disk writes; never turn REST history into a WS-confirmed event.
    parsed = _decode(envelope, snapshot=snapshot, end_ms=end_ms, path=path)
    # D448's atomic writer is intentionally limited to tiny AUTO2
    # sidecars. Never raise its size cap or reuse it for 50x24 historical
    # data. Stage 0600 bytes and use an exclusive hardlink for a once-only
    # atomic publication; never replace an earlier captured observation.
    fd, staged_name = tempfile.mkstemp(prefix=".d461-staged-", dir=home)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(raw)
            out.flush()
            os.fsync(out.fileno())
        os.link(staged_name, path, follow_symlinks=False)
        dirfd = os.open(home, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(dirfd)
        finally:
            os.close(dirfd)
    finally:
        os.unlink(staged_name)
    return parsed


def read_rest_n50_24h(*, snapshot: DynamicPublicN50,
                      private_j2_directory: Path, window_end_ms: int) -> RestN50History:
    if type(snapshot) is not DynamicPublicN50 or not isinstance(private_j2_directory, Path):
        raise DataValidationError("D461 typed replay requires the exact frozen cohort")
    home = _private_directory(private_j2_directory)
    filename = _name(snapshot.fingerprint_sha256, window_end_ms)
    raw = _read_owner_bytes(home, filename, _MAX_BYTES)
    try:
        doc = json.loads(raw.decode("ascii"), object_pairs_hook=_unique)
    except (ValueError, UnicodeError, TypeError):
        raise DataGapError("D461 corrupt owner historical REST bytes") from None
    return _decode(doc, snapshot=snapshot, end_ms=window_end_ms,
                   path=home/filename)


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DataGapError("D461 repeated JSON historical field")
        result[key] = value
    return result


def research_rest_n50_24h(
    *, history: RestN50History,
    config,
) -> dict:
    """Use existing D435 indicators for real, REST-sourced RESEARCH ONLY.

    This cannot initialize AUTO2, issue a trading signal, create a WS
    confirmed receipt, or evade D447's default WS-only quality gate.
    """
    from .j2_bybit_closed_research_bridge import BybitClosedResearchSeries
    from .j2_observed_bybit_research import evaluate_observed_bybit_research
    from .synthetic_entry_hypotheses import CompressionBreakoutConfig
    if (type(history) is not RestN50History
            or type(config) is not CompressionBreakoutConfig
            or len(history.series) != 50
            or len(set(history.symbols)) != 50):
        raise DataValidationError("D461 typed immutable REST-only research required")
    outcome = []
    total = Decimal(0)
    for symbol, bars in history.series:
        if (len(bars) != 24 or bars[-1].close_time_ms + 1 != history.window_end_ms
                or any(c.quality != _QUALITY or c.symbol != symbol for c in bars)):
            raise DataGapError("D461 historical REST research coherence invalid")
        series = BybitClosedResearchSeries(
            bars, history.digest_sha256, history.scope_sha256,
            "research_only_public_closed_series",
        )
        observed = evaluate_observed_bybit_research(
            series, config=config, decision_at_ms=history.window_end_ms,
            close_safety_ms=1, allow_rest_historical_research=True,
        )
        with localcontext(Context(prec=72)):
            pct = (bars[-1].close / bars[0].open - 1) * 100
            turnover = sum((x.quote_volume for x in bars), Decimal(0))
            total += turnover
        outcome.append({
            "symbol": symbol,
            "closed_bars": 24,
            "last_closed_at_ms": bars[-1].close_time_ms,
            "historical_24h_return_percent": format(pct, "f"),
            "historical_quote_turnover_usdt": format(turnover, "f"),
            "hypothesis_count": len(observed.hypotheses),
            "historical_hypothesis_side": (
                observed.hypotheses[0].side.value
                if observed.hypotheses else None
            ),
            "provenance": _SOURCE,
            "approved_for_signals": False,
            "orders_sent": False,
        })
    return {
        "schema_version": "d461-rest-24h-j2-research-v1",
        "status": "historical_n50_indicators_researched_no_order",
        "window_end_ms": history.window_end_ms,
        "closed_candles_analyzed": len(outcome) * 24,
        "members_analyzed": len(outcome),
        "potential_hypothesis_count": sum(x["hypothesis_count"] for x in outcome),
        "total_quote_turnover_usdt": format(total, "f"),
        "rows": outcome,
        "source_mode": history.source_mode,
        "provenance": _SOURCE,
        "websocket_confirmed_candles": 0,
        "approved_for_signals": False,
        "orders_sent": False,
        "source_authenticated": False,
        "venue_trading_approved": False,
    }


def reopen_frozen_rest_n50_for_research(
    *, private_j2_directory: Path, filename: str,
) -> RestN50History:
    """Offline research replay after changing N50 membership or REST clocks.

    The immutable original snapshot remains the source of its own exact
    cohort, end hour, checksum, 50x24 rows and historical-only quality.
    Never supplies an instrument contract or a WS-confirmed receipt.
    """
    if (not isinstance(private_j2_directory, Path)
            or type(filename) is not str
            or re.fullmatch(r"rest-history-d461-[0-9a-f]{18}-[0-9]{13}[.]json",
                            filename) is None):
        raise DataValidationError("D461 exact frozen owner REST filename required")
    home = _private_directory(private_j2_directory)
    raw = _read_owner_bytes(home, filename, _MAX_BYTES)
    try:
        envelope = json.loads(raw.decode("ascii"), object_pairs_hook=_unique)
    except (ValueError, UnicodeError, TypeError):
        raise DataGapError("D461 frozen historical REST JSON corrupt") from None
    p = envelope.get("payload") if type(envelope) is dict else None
    if (type(p) is not dict
            or type(p.get("cohort_sha256")) is not str
            or type(p.get("window_end_ms")) is not int
            or _name(p["cohort_sha256"], p["window_end_ms"]) != filename):
        raise DataGapError("D461 frozen REST archive identity mismatch")
    return _decode(
        envelope, snapshot=None, end_ms=p["window_end_ms"],
        path=home / filename,
    )
