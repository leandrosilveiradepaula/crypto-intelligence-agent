"""D436 finite prospective Bybit closed-candle research operator.

This is deliberately a *composition* of the established public kline parser,
isolated confirmed-candle journal and D434/D435 boundary.  It has no order,
RiskGate, AUTO2/AUTO4, credential or owner-J1 dependency.  A caller supplies
the receive clock with each WebSocket frame; therefore replay is deterministic
and a restart is safe to repeat.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable
import json
import os
import re
import stat
import tempfile
import time

from .bybit_closed_stream_cache import HOUR_MS, OfflineReviewedStreamScope, SQLiteOfflineClosedStreamJournal
from .bybit_ws_offline_pipeline import ingest_offline_ws_batch
from .bybit_public_ws_once import _bounded_json, StreamSession
from .bybit_ws_supervisor import WSRunBudget, supervise_ws_research
from .j2_bybit_closed_research_bridge import read_bybit_closed_research_series
from .j2_observed_bybit_research import evaluate_observed_bybit_research
from .market_data import DataGapError, DataValidationError
from .synthetic_entry_hypotheses import CompressionBreakoutConfig


@dataclass(frozen=True)
class ProspectiveResearchUpdate:
    """Sanitizable result for one confirmed-close evaluation attempt."""

    status: str
    evaluated_at_ms: int
    latest_closed_end_ms: int | None
    journal_digest_sha256: str | None
    appended: int
    identical_replays: int
    failure_category: str | None = None
    data_mode: str = "offline_protocol_replay"
    last_frame_received_ms: int | None = None
    session_ended: bool = False
    session_ended_at_ms: int | None = None

    def sanitized_report(self) -> dict:
        return {
            "schema_version": "j2-prospective-bybit-research-d436-v2",
            "status": self.status,
            "evaluated_at_ms": self.evaluated_at_ms,
            "latest_closed_end_ms": self.latest_closed_end_ms,
            "journal_digest_sha256": self.journal_digest_sha256,
            "closed_events_appended": self.appended,
            "identical_replays": self.identical_replays,
            "failure_category": self.failure_category,
            "source": self.data_mode,
            "network_attempted": self.data_mode == "public_ws_observed_unverified",
            "last_frame_received_ms": self.last_frame_received_ms,
            "session_ended": self.session_ended,
            "session_ended_at_ms": self.session_ended_at_ms,
            "data_quality": "bybit_public_ws_confirmed_unverified",
            "approved_for_signals": False,
            "orders_sent": False,
            "risk_gate_called": False,
            "auto2_called": False,
            "auto4_called": False,
            "live_trading_authorized": False,
        }


def consume_confirmed_close_batch(
    *, frames: Iterable[tuple[str | bytes, int]], journal_path: str | Path,
    scope: OfflineReviewedStreamScope, symbol: str, decision_at_ms: int,
    as_of_ms: int, config: CompressionBreakoutConfig,
) -> ProspectiveResearchUpdate:
    """Persist a bounded batch and evaluate its latest causal close.

    The established journal rejects conflicting replays and records gaps.  An
    incomplete/stale/contradictory journal produces an explicit abstention;
    it never falls back to REST or invents an intervening candle.
    """
    if (type(symbol) is not str or type(decision_at_ms) is not int
            or type(as_of_ms) is not int or decision_at_ms % HOUR_MS
            or not decision_at_ms + 1 <= as_of_ms < decision_at_ms + HOUR_MS):
        raise DataValidationError("D436 decision clock or symbol invalid")
    journal = SQLiteOfflineClosedStreamJournal(Path(journal_path))
    try:
        batch = ingest_offline_ws_batch(frames=frames, scope=scope, journal=journal)
        series = read_bybit_closed_research_series(
            journal_path, scope=scope, symbol=symbol,
            decision_at_ms=decision_at_ms, as_of_ms=as_of_ms,
        )
        evaluation = evaluate_observed_bybit_research(
            series, config=config, decision_at_ms=decision_at_ms,
        )
        latest = series.candles[-1].close_time_ms
        status = ("observed_long_hypothesis_not_authorized"
                  if evaluation.hypotheses and evaluation.hypotheses[0].side.value == "LONG"
                  else "observed_short_hypothesis_not_authorized"
                  if evaluation.hypotheses else "observed_no_hypothesis")
        return ProspectiveResearchUpdate(status, decision_at_ms, latest,
                                         series.journal_digest_sha256,
                                         batch.appended, batch.identical_replays)
    except DataGapError:
        return ProspectiveResearchUpdate("observed_data_insufficient", decision_at_ms,
                                         None, None, 0, 0, "gap_or_stale")
    except DataValidationError:
        return ProspectiveResearchUpdate("observed_feed_unavailable", decision_at_ms,
                                         None, None, 0, 0, "invalid_frame_or_scope")


def evaluate_persisted_confirmed_close(*, journal_path: str | Path,
    scope: OfflineReviewedStreamScope, symbol: str, open_ms: int,
    received_ms: int, config: CompressionBreakoutConfig,
    data_mode: str = "offline_protocol_replay") -> ProspectiveResearchUpdate:
    """Causal post-append callback: no parser, reingest or synthetic clock."""
    if (type(open_ms) is not int or open_ms <= 0 or open_ms % HOUR_MS
            or type(received_ms) is not int or received_ms < open_ms + HOUR_MS
            or data_mode not in ("offline_protocol_replay", "public_ws_observed_unverified")):
        raise DataValidationError("D436 callback close clock invalid")
    decision = open_ms + HOUR_MS
    # The WS journal accepts a genuinely confirmed close immediately at the
    # boundary; the research audit intentionally enforces a 1000-ms safety
    # window. Never terminate the active WS feed for this benign timing gap.
    if received_ms < decision + 1000:
        return ProspectiveResearchUpdate(
            "observed_data_insufficient", decision, None, None, 1, 0,
            "close_safety_not_elapsed", data_mode, received_ms,
        )
    try:
        series = read_bybit_closed_research_series(journal_path, scope=scope, symbol=symbol,
            decision_at_ms=decision, as_of_ms=received_ms)
        result = evaluate_observed_bybit_research(series, config=config, decision_at_ms=decision)
        status = ("observed_long_hypothesis_not_authorized" if result.hypotheses and result.hypotheses[0].side.value == "LONG"
                  else "observed_short_hypothesis_not_authorized" if result.hypotheses else "observed_no_hypothesis")
        return ProspectiveResearchUpdate(status, decision, series.candles[-1].close_time_ms,
            series.journal_digest_sha256, 1, 0, None, data_mode, received_ms)
    except (DataGapError, DataValidationError):
        return ProspectiveResearchUpdate("observed_data_insufficient", decision, None, None,
            1, 0, "gap_or_stale", data_mode, received_ms)


_PROJECTION = "latest-j2-prospective-research.json"
_PROJECTION_SCHEMA = "j2-prospective-bybit-research-d436-v2"
_STATUSES = frozenset((
    "observed_long_hypothesis_not_authorized",
    "observed_short_hypothesis_not_authorized",
    "observed_no_hypothesis", "observed_data_insufficient",
    "observed_feed_unavailable", "observed_session_ended",
))
_FAILURES = frozenset((
    None, "gap_or_stale", "invalid_frame_or_scope",
    "session_finished", "session_abstained", "close_safety_not_elapsed",
))
_SOURCES = frozenset(("offline_protocol_replay", "public_ws_observed_unverified"))
_PROJECTION_TTL_MS = 120_000


def _projection_fields() -> frozenset[str]:
    return frozenset((
        "schema_version", "status", "evaluated_at_ms", "latest_closed_end_ms",
        "journal_digest_sha256", "closed_events_appended", "identical_replays",
        "failure_category", "source", "network_attempted", "last_frame_received_ms",
        "session_ended", "session_ended_at_ms", "data_quality",
        "approved_for_signals", "orders_sent", "risk_gate_called",
        "auto2_called", "auto4_called", "live_trading_authorized",
    ))


def _validate_projection(value: object, *, now_ms: int) -> dict:
    """One strict contract for publisher and loopback reader; never leak raw data."""
    if type(value) is not dict or set(value) != _projection_fields():
        raise DataValidationError("D436 projection keys invalid")
    if (value["schema_version"] != _PROJECTION_SCHEMA
            or type(value["status"]) is not str
            or value["status"] not in _STATUSES
            or type(value["source"]) is not str
            or value["source"] not in _SOURCES
            or value["data_quality"] != "bybit_public_ws_confirmed_unverified"
            or type(value["failure_category"]) not in (str, type(None))
            or value["failure_category"] not in _FAILURES
            or type(value["network_attempted"]) is not bool
            or value["network_attempted"] is not (
                value["source"] == "public_ws_observed_unverified"
            )
            or any(value[k] is not False for k in (
                "approved_for_signals", "orders_sent", "risk_gate_called",
                "auto2_called", "auto4_called", "live_trading_authorized",
            ))):
        raise DataValidationError("D436 projection forbidden claims")
    for key in ("closed_events_appended", "identical_replays"):
        if type(value[key]) is not int or not 0 <= value[key] <= 4096:
            raise DataValidationError("D436 projection counter invalid")
    for key in ("evaluated_at_ms",):
        if type(value[key]) is not int or value[key] <= 0:
            raise DataValidationError("D436 decision clock invalid")
    for key in ("latest_closed_end_ms", "last_frame_received_ms",
                "session_ended_at_ms"):
        if value[key] is not None and (
                type(value[key]) is not int or value[key] <= 0):
            raise DataValidationError("D436 projection clock invalid")
    digest = value["journal_digest_sha256"]
    if digest is not None and (
            type(digest) is not str or re.fullmatch(r"[a-f0-9]{64}", digest) is None):
        raise DataValidationError("D436 journal digest invalid")
    ended = value["session_ended"]
    if type(ended) is not bool or (value["status"] == "observed_session_ended") != ended:
        raise DataValidationError("D436 session state invalid")
    if ended:
        if value["session_ended_at_ms"] is None:
            raise DataValidationError("D436 terminal clock absent")
        reference = value["session_ended_at_ms"]
        if (value["last_frame_received_ms"] is not None and
                value["last_frame_received_ms"] > reference):
            raise DataValidationError("D436 terminal precedes market receipt")
    else:
        if (value["session_ended_at_ms"] is not None
                or value["last_frame_received_ms"] is None):
            raise DataValidationError("D436 active observation absent")
        reference = value["last_frame_received_ms"]
    if (type(now_ms) is not int or
            not 0 <= now_ms - reference <= _PROJECTION_TTL_MS):
        raise DataValidationError("D436 projection expired or future")
    if value["latest_closed_end_ms"] is not None and (
            value["latest_closed_end_ms"] >= value["evaluated_at_ms"]
            or value["journal_digest_sha256"] is None):
        raise DataValidationError("D436 observed close/digest mismatch")
    if (not ended and value["status"] in (
            "observed_long_hypothesis_not_authorized",
            "observed_short_hypothesis_not_authorized", "observed_no_hypothesis")
            and (value["latest_closed_end_ms"] is None
                 or value["journal_digest_sha256"] is None
                 or value["evaluated_at_ms"] % HOUR_MS)):
        raise DataValidationError("D436 observation lacks causal provenance")
    return value


def publish_projection(directory: Path, update: ProspectiveResearchUpdate) -> None:
    """Atomic, owner-only local publication; never a network or trade effect."""
    if (type(update) is not ProspectiveResearchUpdate
            or os.name != "posix" or os.geteuid() == 0 or
            directory.is_symlink() or not directory.is_dir()):
        raise DataValidationError("D436 owner projection directory required")
    info = directory.stat()
    if (info.st_uid != os.geteuid() or
            stat.S_IMODE(info.st_mode) != 0o700):
        raise DataValidationError("D436 unsafe projection directory")
    data = update.sanitized_report()
    ref_ms = (update.session_ended_at_ms if update.session_ended
              else update.last_frame_received_ms)
    _validate_projection(data, now_ms=ref_ms)
    blob = json.dumps(data, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")
    if not 1 <= len(blob) <= 4096:
        raise DataValidationError("D436 projection size")
    fd, temporary = tempfile.mkstemp(prefix=".j2-d436-", dir=directory)
    try:
        with os.fdopen(fd, "wb") as out:
            os.fchmod(out.fileno(), 0o600)
            out.write(blob)
            out.flush()
            os.fsync(out.fileno())
        target = directory / _PROJECTION
        if target.is_symlink():
            raise DataValidationError("D436 destination symlink refused")
        os.replace(temporary, target)
        temporary = ""
        dfd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    finally:
        if temporary:
            os.unlink(temporary)


def read_projection(directory: Path, *, now_ms: int) -> dict:
    if (os.name != "posix" or os.geteuid() == 0 or
            directory.is_symlink() or not directory.is_dir()
            or type(now_ms) is not int):
        raise DataValidationError("D436 projection unavailable")
    d = directory.stat()
    if (d.st_uid != os.geteuid() or
            stat.S_IMODE(d.st_mode) != 0o700):
        raise DataValidationError("D436 projection unsafe")
    fd = os.open(directory / _PROJECTION,
                 os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1
                or not 1 <= info.st_size <= 4096):
            raise DataValidationError("D436 projection unsafe")
        raw = os.read(fd, 4097)
        after = os.fstat(fd)
    finally:
        os.close(fd)
    if (len(raw) != info.st_size or after.st_ino != info.st_ino
            or after.st_mtime_ns != info.st_mtime_ns
            or after.st_size != info.st_size):
        raise DataValidationError("D436 projection changed")
    def unique(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise DataValidationError("D436 duplicate projection field")
            result[key] = item
        return result
    value = json.loads(
        raw.decode("ascii"), object_pairs_hook=unique,
        parse_constant=lambda _: (_ for _ in ()).throw(
            DataValidationError("D436 numeric invalid")),
    )
    return _validate_projection(value, now_ms=now_ms)


def supervise_prospective_research(
    *, session_factory, journal_path: str | Path,
    scope: OfflineReviewedStreamScope, symbol: str,
    config: CompressionBreakoutConfig, budget: WSRunBudget,
    projection_directory: Path | None = None,
    data_mode: str = "offline_protocol_replay",
    public_session_opted_in: bool = False, **clock_args,
):
    """Read-only, finite, opt-in supervision. Never imply a daemon or order."""
    if (data_mode not in _SOURCES
            or type(public_session_opted_in) is not bool
            or (data_mode == "public_ws_observed_unverified"
                and not public_session_opted_in)):
        raise DataValidationError("D436 explicit public research opt-in required")
    journal = SQLiteOfflineClosedStreamJournal(Path(journal_path))
    latest: list[ProspectiveResearchUpdate] = []

    def after(raw, received_ms):
        payload = _bounded_json(raw)
        rows = payload.get("data") if type(payload) is dict else None
        # The supervised parser has already accepted and committed this close;
        # this callback never accepts pre-ACK, open or duplicate rows.
        if (type(rows) is not list or len(rows) != 1
                or type(rows[0]) is not dict
                or rows[0].get("confirm") is not True):
            return
        row = rows[0]
        if (payload.get("topic") != "kline.60." + symbol
                or type(row.get("start")) is not int):
            return
        update = evaluate_persisted_confirmed_close(
            journal_path=journal_path, scope=scope, symbol=symbol,
            open_ms=row["start"], received_ms=received_ms,
            config=config, data_mode=data_mode,
        )
        latest[:] = [update]
        if projection_directory is not None:
            publish_projection(projection_directory, update)

    report = supervise_ws_research(
        session_factory=session_factory, scope=scope, journal=journal,
        budget=budget, on_confirmed_frame=after, **clock_args,
    )
    # End the finite session explicitly, whether it completed or abstained.
    # Never leave a past hypothesis displayed as current supervision.
    wall_ms = clock_args.get("wall_ms")
    end_ms = wall_ms() if wall_ms is not None else time.time_ns() // 1_000_000
    if type(end_ms) is not int or end_ms <= 0:
        raise DataValidationError("D436 terminal clock invalid")
    last = latest[0] if latest else None
    terminal = ProspectiveResearchUpdate(
        status="observed_session_ended",
        evaluated_at_ms=last.evaluated_at_ms if last else end_ms,
        latest_closed_end_ms=last.latest_closed_end_ms if last else None,
        journal_digest_sha256=last.journal_digest_sha256 if last else None,
        appended=0, identical_replays=0,
        failure_category=("session_finished" if
                          report.status == "ws_budget_ended_research_only"
                          else "session_abstained"),
        data_mode=data_mode,
        last_frame_received_ms=last.last_frame_received_ms if last else None,
        session_ended=True, session_ended_at_ms=end_ms,
    )
    if projection_directory is not None:
        publish_projection(projection_directory, terminal)
    return report, (last if last is not None else None)


def run_authorized_public_kline_session(
    *, journal_path: str | Path, scope: OfflineReviewedStreamScope, symbol: str,
    config: CompressionBreakoutConfig, budget: WSRunBudget,
    allow_public_network: bool = False, allow_public_websocket: bool = False,
    confirm_personal_readonly_research: bool = False,
    confirm_region_eligible: bool = False, projection_directory: Path | None = None,
    session_factory=None, owner_check=None, **clock_args,
):
    """Open one bounded Bybit public session only after four explicit gates.

    An injected transport is always labelled offline protocol replay.  Only the
    lazy approved Bybit transport can label a session public-observed; neither
    outcome authenticates the source or authorizes a signal/order.
    """
    flags = (allow_public_network, allow_public_websocket,
             confirm_personal_readonly_research, confirm_region_eligible)
    if any(type(x) is not bool for x in flags):
        raise DataValidationError("D436 public opt-in flags invalid")
    if not all(flags):
        return {"status": "explicit_public_research_optin_required",
                "network_attempted": False, "orders_sent": False}, None
    real_transport = session_factory is None
    if real_transport and (owner_check is not None or clock_args):
        # Clock and ownership test hooks must never label a live socket.
        return {"status": "public_test_hooks_forbidden", "network_attempted": False,
                "orders_sent": False}, None
    if owner_check is None:
        owner_check = lambda: os.name == "posix" and os.geteuid() != 0
    if not callable(owner_check) or not owner_check():
        return {"status": "unprivileged_owner_required", "network_attempted": False,
                "orders_sent": False}, None
    if real_transport:
        if os.name != "posix" or os.geteuid() == 0:
            return {"status": "unprivileged_owner_required", "network_attempted": False,
                    "orders_sent": False}, None
        from .bybit_public_ws_once import ENDPOINT, _real_session_factory
        if ENDPOINT != "wss://stream.bybit.com/v5/public/linear":
            raise DataValidationError("D436 Bybit endpoint changed")
        session_factory = _real_session_factory
    report, update = supervise_prospective_research(
        session_factory=session_factory, journal_path=journal_path, scope=scope,
        symbol=symbol, config=config, budget=budget,
        projection_directory=projection_directory,
        data_mode=("public_ws_observed_unverified" if real_transport
                   else "offline_protocol_replay"),
        public_session_opted_in=real_transport, **clock_args,
    )
    return report, update
