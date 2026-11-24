"""Owner one-shot: recover older public bars and compare the same D461 cohorts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

from crypto_intelligence_agent.j3_retrospective_warmup_d516 import (
    capture_retrospective_warmup, read_latest_supplement,
)
from crypto_intelligence_agent.j3_archived_strategy_comparison_d512 import read_comparison_archives
from crypto_intelligence_agent.market_data import DataGapError, DataValidationError
from crypto_intelligence_agent.bybit_public_j1_transport import J1BybitCaptureError
from scripts.serve_paper_profile_lab_d487 import _strategy_comparison
from scripts.run_j2_j4_public_paper_resident_d453 import read_owner_paper_policy


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--historical-directory", type=Path, required=True)
    p.add_argument("--policy-file", type=Path, required=True)
    p.add_argument("--history-hours", type=int, required=True)
    p.add_argument("--ema-periods", type=int, nargs=3, required=True)
    p.add_argument("--reuse", action="store_true", help="Only read the existing supplement")
    for flag in ("allow-public-network", "confirm-personal-readonly-research",
                 "confirm-region-eligible", "confirm-public-data-rights"):
        p.add_argument("--"+flag, action="store_true")
    a = p.parse_args(argv)
    try:
        if (not 24 <= a.history_hours <= 122
                or not 2 <= a.ema_periods[0] < a.ema_periods[1] < a.ema_periods[2] <= 120
                or a.history_hours < a.ema_periods[2]+2):
            raise DataValidationError("D516 invalid comparison periods")
        read_owner_paper_policy(a.policy_file)
        now = time.time_ns()//1_000_000
        archives = read_comparison_archives(a.historical_directory, now_ms=now)
        if not a.reuse:
            _, info = capture_retrospective_warmup(
                directory=a.historical_directory, histories=archives,
                history_hours=a.history_hours,
                allow_public_network=a.allow_public_network,
                confirm_personal_readonly_research=a.confirm_personal_readonly_research,
                confirm_region_eligible=a.confirm_region_eligible,
                confirm_public_data_rights=a.confirm_public_data_rights,
            )
        else:
            s = read_latest_supplement(a.historical_directory, now_ms=now)
            if s is None or s.history_hours < a.history_hours:
                raise DataValidationError("D516 sufficient saved supplement unavailable")
            info = {"status": "saved_retrospective_warmup_reused", "public_gets": 0}
        report = _strategy_comparison(
            paper_file=a.policy_file, history_directory=a.historical_directory,
            ema_periods=tuple(a.ema_periods), now_ms=time.time_ns()//1_000_000,
            retrospective=True,
        )
        report.pop("windows", None)
        print(json.dumps({"capture": info, "comparison": report,
                          "orders_sent": False}, sort_keys=True, separators=(",", ":")))
        return 0
    except (DataValidationError, DataGapError, J1BybitCaptureError,
            OSError, TypeError, ValueError, ArithmeticError):
        print(json.dumps({"status": "retrospective_research_unavailable",
                          "orders_sent": False}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
