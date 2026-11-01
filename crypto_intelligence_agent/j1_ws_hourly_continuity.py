"""OPS10: fail-closed continuity gate for consecutive closed-hour WS audits.

No network, writes, orders, or private REST access. An ACK is not delivery.
This gate does not authenticate marketwide Top50 or a running service.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .bybit_closed_stream_cache import HOUR_MS, OfflineStreamAudit
from .market_data import DataValidationError


@dataclass(frozen=True)
class HourlyContinuityCheckpoint:
    decision_at_ms: int
    observed_at_ms: int
    expected_contracts: int
    complete_contracts: int
    missing_contracts: int
    journal_digest_sha256: str
    rank_digest_sha256: str | None

    def sanitized_report(self) -> dict:
        return {
            "decision_at_utc_ms": self.decision_at_ms,
            "observed_at_utc_ms": self.observed_at_ms,
            "expected_contracts": self.expected_contracts,
            "complete_contracts": self.complete_contracts,
            "missing_contracts": self.missing_contracts,
            "continuity_verified": self.missing_contracts == 0,
            "marketwide_top50_verified": False,
            "source_authenticated": False,
            "orders_sent": False,
        }


def checkpoint_from_audit(*, audit: OfflineStreamAudit, decision_at_ms: int,
                          observed_at_ms: int, expected_contracts: int
                          ) -> HourlyContinuityCheckpoint:
    """Require complete local 24h window; never infer delivery from subscribe ACK."""
    if (type(audit) is not OfflineStreamAudit
            or type(decision_at_ms) is not int or decision_at_ms <= 0
            or decision_at_ms % HOUR_MS
            or type(observed_at_ms) is not int
            or not decision_at_ms + 1000 <= observed_at_ms < decision_at_ms + HOUR_MS
            or type(expected_contracts) is not int
            or not 1 <= expected_contracts <= 52
            or type(audit.complete_24h_symbols) is not int
            or type(audit.missing_24h_symbols) is not int
            or audit.complete_24h_symbols < 0 or audit.missing_24h_symbols < 0
            or audit.complete_24h_symbols + audit.missing_24h_symbols != expected_contracts
            or type(audit.journal_digest_sha256) is not str
            or len(audit.journal_digest_sha256) != 64):
        raise DataValidationError("untrusted hourly continuity audit")
    return HourlyContinuityCheckpoint(
        decision_at_ms, observed_at_ms, expected_contracts,
        audit.complete_24h_symbols, audit.missing_24h_symbols,
        audit.journal_digest_sha256, audit.rank_digest_sha256,
    )


def compare_closed_hours(previous: HourlyContinuityCheckpoint,
                         current: HourlyContinuityCheckpoint) -> dict:
    """Fail closed across lease boundaries, clock jumps, and incomplete windows.

    This is a local continuity indicator, NOT proof of exchange-origin data.
    """
    if (type(previous) is not HourlyContinuityCheckpoint
            or type(current) is not HourlyContinuityCheckpoint):
        raise DataValidationError("two typed continuity checkpoints required")
    consecutive = current.decision_at_ms - previous.decision_at_ms == HOUR_MS
    valid = (consecutive
             and previous.observed_at_ms < current.observed_at_ms
             and previous.expected_contracts == current.expected_contracts
             and previous.missing_contracts == 0
             and current.missing_contracts == 0
             and previous.complete_contracts == previous.expected_contracts
             and current.complete_contracts == current.expected_contracts
             and previous.rank_digest_sha256 is not None
             and current.rank_digest_sha256 is not None)
    return {
        "status": "local_hourly_continuity_unverified_source" if valid
                  else "hourly_continuity_abstain",
        "consecutive_utc_hours": consecutive,
        "complete_local_windows": valid,
        "marketwide_top50_verified": False,
        "source_authenticated": False,
        "worker_running_verified": False,
        "orders_sent": False,
    }
