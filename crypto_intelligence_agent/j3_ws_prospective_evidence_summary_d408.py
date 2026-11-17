"""D408: scorebook of past J2/J3 CLOSED-price research references, not trades.

Consumes only the already-projected, owner-replayed J3 results. Does not
select new candidates, infer fills, access owner files, trade or rank assets.
Incomplete/duplicate/forged observations fail closed. This scorebook is NOT
independently timestamped or a representative out-of-sample sample.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, localcontext
from typing import Any

from .bybit_closed_stream_cache import HOUR_MS
from .market_data import DataValidationError
from scripts.run_j3_ws_owner_forward_tick_once import _projection

_MAX = 256
_MAX_TIME = 4_102_444_800_000
_MIN_TIME = 1_600_000_000_000
_HORIZONS = (1, 4, 8)
_STATUS = "reference_marks_scored_hypothetical_only"


def _bps(text: object) -> Decimal:
    if type(text) is not str or not 1 <= len(text) <= 600:
        raise DataValidationError("D408 invalid numeric research reference")
    try:
        value = Decimal(text)
    except (InvalidOperation, ValueError):
        raise DataValidationError("D408 invalid numeric research reference") from None
    # Bounded research-only magnitude. This is not a market assumption.
    if not value.is_finite() or abs(value) > Decimal("1e9"):
        raise DataValidationError("D408 nonfinite or unbounded reference value")
    return value


def summarize_ws_prospective_references(
    reports: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    """Summarize distinct (frozen decision hour, forward horizon) pairs.

    All passed records must have been validated against the original
    owner's read-only scoring contract by the same D667 projection.
    Missing historical decisions are NOT supplied here; the denominator is
    only the records a caller explicitly gives. No profit signal is emitted.
    """
    if (type(reports) is not tuple
            or not 1 <= len(reports) <= _MAX
            or any(type(r) is not dict for r in reports)):
        raise DataValidationError("D408 expected 1..256 owner score JSON records")

    by_horizon = {
        h: {
            "horizon_hours": h,
            "records": 0, "scored_decisions": 0, "empty_decisions": 0,
            "matured_research_observations": 0,
            "directionally_favorable": 0,
            "directionally_contrary": 0,
            "unchanged": 0,
            "net_reference_bps_sum_under_individual_assumptions": None,
            "net_reference_bps_mean_per_observation": None,
        }
        for h in _HORIZONS
    }
    seen: set[tuple[int, int]] = set()
    hours: set[int] = set()
    net_sum = {h: Decimal(0) for h in _HORIZONS}
    for item in reports:
        horizon = item.get("horizon_bars")
        end = item.get("decision_closed_end_ms")
        future_end = item.get("future_closed_end_ms")
        if (type(horizon) is not int or horizon not in _HORIZONS
                or type(end) is not int or not _MIN_TIME <= end < _MAX_TIME
                or end % HOUR_MS != 0
                or type(future_end) is not int
                or future_end != end + horizon * HOUR_MS
                or future_end >= _MAX_TIME
                or (end, horizon) in seen):
            raise DataValidationError("D408 duplicate or invalid research decision time")
        projection = _projection(item, horizon=horizon, future_end=future_end)
        if projection["status"] not in (
            _STATUS, "no_observations_selected"
        ):
            raise DataValidationError("D408 unverified, missing or stale score")
        seen.add((end, horizon))
        hours.add(end)
        row = by_horizon[horizon]
        row["records"] += 1
        if projection["status"] == "no_observations_selected":
            row["empty_decisions"] += 1
            continue
        n = projection["matured_observations"]
        aligned = item["aligned_observations"]
        contrary = item["contrary_observations"]
        unchanged = item["unchanged_observations"]
        if n <= 0 or aligned + contrary + unchanged != n:
            raise DataValidationError("D408 forward counts inconsistent")
        value = _bps(projection["net_reference_after_assumed_costs_bps_sum"])
        row["scored_decisions"] += 1
        row["matured_research_observations"] += n
        row["directionally_favorable"] += aligned
        row["directionally_contrary"] += contrary
        row["unchanged"] += unchanged
        net_sum[horizon] += value

    with localcontext() as ctx:
        ctx.prec = 75
        for horizon in _HORIZONS:
            row = by_horizon[horizon]
            n = row["matured_research_observations"]
            if n:
                row["net_reference_bps_sum_under_individual_assumptions"] = format(
                    net_sum[horizon], "f",
                )
                row["net_reference_bps_mean_per_observation"] = format(
                    net_sum[horizon] / Decimal(n), ".4f",
                )
    return {
        "schema_version": "j3-ws-prospective-evidence-summary-d408-v1",
        "status": "descriptive_forward_research_not_strategy_validation",
        "source": "imported_owner_report_contract_only_not_independently_attested",
        "report_records_accepted": len(reports),
        "distinct_decision_hours_in_supplied_files": len(hours),
        "horizons": [by_horizon[h] for h in _HORIZONS],
        "all_decision_windows_present_verified": False,
        "cost_assumptions_consistent_across_decisions_verified": False,
        "prospective_registration_independently_verified": False,
        "out_of_sample_results_validated": False,
        "strategy_profitable_verified": False,
        "financial_backtest_approved": False,
        "marketwide_top50_verified": False,
        "approved_for_signals": False,
        "approved_for_live_use": False,
        "orders_sent": False,
        "network_requests": 0,
        "database_accessed": False,
        "database_mutation_statements": 0,
    }
