"""D432: produce an owner-only Console projection from the offline vertical proof.

Never opens a socket or writes a market/AUTO journal. The report itself is
created by the existing J2-to-AUTO2-to-AUTO4-to-runner demo; D392 is run alongside it
to prove the Bybit-shaped intrahour stop-first fixture before publication.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import tempfile

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.paper_intrahour_proof_d392 import demonstrate_paper_intrahour_cycle
from scripts.demo_full_offline_paper_lifecycle import run_full_offline_paper_lifecycle

_NAME = "latest-integrated-paper-cycle.json"


def publish(directory: Path) -> dict:
    if (os.name != "posix" or os.geteuid() == 0 or not directory.is_absolute()
            or directory.is_symlink()):
        raise DataValidationError("D432 requires a nonroot absolute owner directory")
    info = directory.stat()
    if (not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700
            or info.st_uid != os.geteuid()):
        raise DataValidationError("D432 owner directory must be 0700")
    report = run_full_offline_paper_lifecycle()
    intrahour = demonstrate_paper_intrahour_cycle(side="LONG")
    if (intrahour["status"] != "fixture_cycle_closed" or report["orders_sent"]
            or report["network_requests"] != 0):
        raise DataValidationError("D432 only publishes verified offline PAPER fixtures")
    raw = json.dumps(report, sort_keys=True, separators=(",", ":")).encode("utf-8")
    fd, temporary = tempfile.mkstemp(prefix=".cycle-", dir=directory)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as out:
            out.write(raw); out.flush(); os.fsync(out.fileno())
        os.replace(temporary, directory / _NAME)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)
    return {"status": "offline_integrated_cycle_published", "orders_sent": False,
            "network_requests": 0, "bybit_intrahour_fixture_verified": True}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(publish(args.directory), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
