"""J1/OPS29: offline-only transitive evidence for multiple closed WS hours.

Consumes typed *already produced* journal audit checkpoints and finite WS
supervisor lease reports. It never creates a socket, reads a file, persists
data, starts a daemon, authenticates a source or authorizes ingestion.
"""
from __future__ import annotations

from dataclasses import dataclass

from .bybit_closed_stream_cache import HOUR_MS
from .bybit_ws_supervisor import WSRunReport
from .j1_ws_hourly_continuity import (
    HourlyContinuityCheckpoint, compare_closed_hours,
)

MAX_SOAK_HOURS = 72
MIN_SOAK_HOURS = 7


@dataclass(frozen=True)
class MultihourSoakAudit:
    """All values are aggregates; no symbols, raw timestamps or prices."""

    status: str
    consecutive_closed_hours: int = 0
    expected_contracts: int = 0
    observed_closed_events: int = 0
    acknowledged_leases: int = 0
    recovered_connections: int = 0
    preack_frames_discarded: int = 0

    def sanitized_report(self) -> dict:
        return {
            "status": self.status,
            "consecutive_closed_hours": self.consecutive_closed_hours,
            "expected_contracts": self.expected_contracts,
            "observed_closed_events": self.observed_closed_events,
            "acknowledged_leases": self.acknowledged_leases,
            "recovered_connections": self.recovered_connections,
            "preack_frames_discarded": self.preack_frames_discarded,
            "local_fixture_soak_consistent": (
                self.status == "local_multihour_soak_consistent_unverified"
            ),
            "continuous_collector_authorized": False,
            "worker_running_verified": False,
            "source_authenticated": False,
            "marketwide_top50_verified": False,
            "canonical_ohlcv_approved": False,
            "live_trading_authorized": False,
            "network_requests": 0,
            "orders_sent": False,
        }


def audit_ws_multihour_soak(
    *, checkpoints: tuple[HourlyContinuityCheckpoint, ...],
    leases: tuple[WSRunReport, ...],
    minimum_hours: int = MIN_SOAK_HOURS,
) -> MultihourSoakAudit:
    """Check a 1:1 succession of finished WS leases and 24h journal audits.

    Each lease refers to the immediately preceding UTC closed hour. The
    caller is responsible for obtaining the typed inputs from the existing
    offline supervisor and journal. A correct local simulation never proves
    real VPS uptime or attests marketwide coverage.

    All failures return zero counters: a partially successful prefix must
    never be mistaken for certified uninterrupted history.
    """
    bad = MultihourSoakAudit("local_multihour_soak_abstain")
    if (type(checkpoints) is not tuple or type(leases) is not tuple
            or type(minimum_hours) is not int
            or not MIN_SOAK_HOURS <= minimum_hours <= MAX_SOAK_HOURS
            or not minimum_hours <= len(checkpoints) <= MAX_SOAK_HOURS
            or len(leases) != len(checkpoints)):
        return bad

    expected = None
    recovered = preack = events = 0
    previous = None
    for cp, lease in zip(checkpoints, leases):
        if (type(cp) is not HourlyContinuityCheckpoint
                or type(lease) is not WSRunReport
                or type(cp.decision_at_ms) is not int
                or cp.decision_at_ms <= 0
                or cp.decision_at_ms % HOUR_MS != 0
                or type(cp.observed_at_ms) is not int
                or not cp.decision_at_ms + 1000 <= cp.observed_at_ms <
                        cp.decision_at_ms + HOUR_MS
                or type(cp.expected_contracts) is not int
                or not 1 <= cp.expected_contracts <= 52
                or type(cp.complete_contracts) is not int
                or type(cp.missing_contracts) is not int
                or cp.complete_contracts != cp.expected_contracts
                or cp.missing_contracts != 0
                or type(cp.rank_digest_sha256) is not str
                or len(cp.rank_digest_sha256) != 64
                or type(cp.journal_digest_sha256) is not str
                or len(cp.journal_digest_sha256) != 64
                or type(cp.private_scope_fingerprint) is not tuple):
            return bad
        if expected is None:
            expected = cp.expected_contracts
        if cp.expected_contracts != expected:
            return bad
        if previous is not None:
            continuity = compare_closed_hours(previous, cp)
            if (continuity["complete_local_windows"] is not True
                    or continuity["consecutive_utc_hours"] is not True):
                return bad
        previous = cp
        if (lease.status != "ws_budget_ended_research_only"
                or lease.failure_category is not None
                or type(lease.sessions_attempted) is not int
                or not 1 <= lease.sessions_attempted <= 4
                or type(lease.sessions_fully_acknowledged) is not int
                or not 1 <= lease.sessions_fully_acknowledged <= lease.sessions_attempted
                or type(lease.subscriptions_acknowledged) is not int
                or lease.subscriptions_acknowledged != lease.sessions_fully_acknowledged
                or type(lease.subscriptions_sent) is not int
                or lease.subscriptions_sent != lease.sessions_attempted
                or type(lease.reconnects) is not int
                or lease.reconnects != lease.sessions_attempted - 1
                or type(lease.closed_events_appended) is not int
                or type(lease.identical_replays) is not int
                or lease.closed_events_appended != expected
                or lease.identical_replays != 0
                or type(lease.open_updates) is not int or lease.open_updates < 0
                or type(lease.early_frames_buffered) is not int
                or lease.early_frames_buffered != 0
                or type(lease.preack_frames_discarded) is not int
                or lease.preack_frames_discarded < 0
                or type(lease.frames_seen) is not int
                or lease.frames_seen < expected
                or type(lease.heartbeat_pings) is not int
                or type(lease.heartbeat_pongs) is not int):
            return bad
        recovered += lease.reconnects
        preack += lease.preack_frames_discarded
        events += lease.closed_events_appended

    return MultihourSoakAudit(
        "local_multihour_soak_consistent_unverified",
        len(checkpoints), expected or 0, events,
        len(leases), recovered, preack,
    )
