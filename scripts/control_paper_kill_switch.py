"""Owner-only local PAPER pause/resume/status; never connects to exchanges.

Example:
  python3 -m scripts.control_paper_kill_switch --journal /private/orders.sqlite \
    --action pause --expected-sequence 0

Resume always requires --confirm-paper-resume and a fresh expected sequence.
The control gates new PAPER OPEN only; it does not cancel orders or
protect live positions. An existing owner-only POSIX file is mandatory.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import time

from crypto_intelligence_agent.paper_order_store import SQLitePaperOrderJournal
from crypto_intelligence_agent.paper_position_inspection import _checked_path


def _owner_only_existing_journal(value: str) -> Path:
    if os.name != "posix":
        raise ValueError("operator_control_requires_posix_private_files")
    source = _checked_path(value)
    if source.parent.is_symlink() or (
        stat.S_IMODE(source.stat().st_mode) != 0o600
        or stat.S_IMODE(source.parent.stat().st_mode) != 0o700
        or source.stat().st_nlink != 1
    ):
        raise ValueError("private_journal_requires_single_owner_0600_file_and_0700_dir")
    return source


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--journal", required=True)
    parser.add_argument("--action", choices=("status", "pause", "resume"), required=True)
    parser.add_argument("--expected-sequence", type=int)
    parser.add_argument("--confirm-paper-resume", action="store_true")
    args = parser.parse_args(argv)
    try:
        if (args.action == "status" and (
            args.expected_sequence is not None or args.confirm_paper_resume
        )) or (args.action != "status" and args.expected_sequence is None):
            raise ValueError("mutation_requires_explicit_current_sequence")
        path = _owner_only_existing_journal(args.journal)
        journal = SQLitePaperOrderJournal(path)
        if args.action == "status":
            state = journal.read_local_kill_switch()
        else:
            state = journal.set_local_kill_switch(
                pause=args.action == "pause",
                expected_sequence=args.expected_sequence,
                changed_at_ms=int(time.time() * 1000),
                acknowledge_resume=args.confirm_paper_resume,
            )
        report = {
            "schema_version": "paper_local_operator_switch_status_v1",
            "status": "open_reservations_paused" if state.active
                      else "open_reservations_not_paused",
            "sequence": state.sequence,
            "changed_at_ms": state.changed_at_ms,
            "paper_only": True,
            "order_submission_enabled": False,
            "live_trading_authorized": False,
            "orders_sent": False,
        }
        code = 0
    except Exception:
        report = {
            "schema_version": "paper_local_operator_switch_status_v1",
            "status": "operator_switch_refused",
            "order_submission_enabled": False,
            "live_trading_authorized": False,
            "orders_sent": False,
        }
        code = 1
    print(json.dumps(report, ensure_ascii=True, separators=(",", ":"), sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(run())
