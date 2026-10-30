"""Print one sanitised, read-only J6/PRE6 PAPER incident report."""
from __future__ import annotations
import argparse
from decimal import Decimal
import json
from pathlib import Path

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.paper_runner_incident_audit import audit_paper_runner_incident
from crypto_intelligence_agent.paper_runner_trailing import PaperRunnerTrailPolicy


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Audita uma posição PAPER explícita, sem escrita ou rede.")
    p.add_argument("--position-journal", type=Path, required=True)
    p.add_argument("--position-id", required=True)
    p.add_argument("--runner-journal", type=Path)
    p.add_argument("--activation-bps")
    p.add_argument("--trail-distance-bps")
    p.add_argument("--max-tick-gap-ms", type=int)
    p.add_argument("--max-last-tick-age-ms", type=int)
    p.add_argument("--as-of-ms", type=int)
    a = p.parse_args(argv)
    values = (a.runner_journal, a.activation_bps, a.trail_distance_bps, a.max_tick_gap_ms, a.max_last_tick_age_ms, a.as_of_ms)
    if any(x is not None for x in values) and not all(x is not None for x in values):
        p.error("RUNNER2 requer diário, política e cutoff completos")
    policy = None
    if a.runner_journal is not None:
        try:
            policy = PaperRunnerTrailPolicy(Decimal(a.activation_bps), Decimal(a.trail_distance_bps), a.max_tick_gap_ms, a.max_last_tick_age_ms)
        except (ValueError, ArithmeticError) as exc:
            raise DataValidationError("política RUNNER2 inválida") from exc
    report = audit_paper_runner_incident(a.position_journal, a.position_id, runner_journal_path=a.runner_journal, policy=policy, as_of_ms=a.as_of_ms)
    print(json.dumps(report.sanitized_report(), ensure_ascii=False, sort_keys=True))

if __name__ == "__main__":
    main()
