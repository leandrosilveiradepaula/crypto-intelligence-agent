"""Read-only, bounded J6/PRE8 audit of EXPLICIT selected PAPER positions."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from crypto_intelligence_agent.paper_portfolio_incident_audit import (
    audit_selected_paper_portfolio_incidents,
)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Audita em lote posições PAPER selecionadas, sem corretora ou ordens.")
    parser.add_argument("--position-journal", required=True, type=Path)
    parser.add_argument("--position-id", required=True, action="append")
    parser.add_argument("--as-of-ms", required=True, type=int)
    parser.add_argument("--max-checkpoint-age-ms", required=True, type=int)
    parser.add_argument("--opening-order-journal", type=Path)
    args = parser.parse_args(argv)
    report = audit_selected_paper_portfolio_incidents(
        args.position_journal,
        tuple(args.position_id),
        as_of_ms=args.as_of_ms,
        max_checkpoint_age_ms=args.max_checkpoint_age_ms,
        opening_order_path=args.opening_order_journal,
    )
    print(json.dumps(report.sanitized_report(), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
