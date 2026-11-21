"""D457: preflight real J2/J4 PAPER resident without files/network mutations.

Run this AS the unprivileged owner on the target host. A successful result
does not authorize service installation, place orders, or claim venue stops.
Use the same interpreter/working directory intended for the eventual unit.
"""
from __future__ import annotations

import argparse
from importlib.util import find_spec
import json
import os
from pathlib import Path
import stat
import sys

from crypto_intelligence_agent.market_data import DataValidationError


def preflight(*, j2_directory: Path, paper_directory: Path,
              policy_file: Path) -> dict:
    checks: dict[str, bool] = {}
    checks["unprivileged_posix_owner"] = (
        os.name == "posix" and hasattr(os, "geteuid") and os.geteuid() != 0
    )
    checks["directories_separate"] = (
        isinstance(j2_directory, Path) and isinstance(paper_directory, Path)
        and j2_directory.is_absolute() and paper_directory.is_absolute()
        and j2_directory != paper_directory
        and all(not piece.startswith("j1-")
                for piece in j2_directory.parts + paper_directory.parts)
    )
    checks["python_websockets_sync_client"] = False
    if find_spec("websockets") is not None:
        try:
            from websockets.sync.client import connect
            checks["python_websockets_sync_client"] = callable(connect)
        except (ImportError, ModuleNotFoundError, AttributeError):
            pass
    for label, path in (("j2", j2_directory), ("paper", paper_directory)):
        ok = False
        if checks["unprivileged_posix_owner"] and isinstance(path, Path):
            try:
                info = path.lstat()
                ok = (stat.S_ISDIR(info.st_mode)
                      and stat.S_IMODE(info.st_mode) == 0o700
                      and info.st_uid == os.geteuid()
                      and not path.is_symlink()
                      and os.access(path, os.R_OK | os.W_OK | os.X_OK))
            except OSError:
                pass
        checks[label + "_private_owner_directory"] = ok
    checks["policy_owner_only_and_valid"] = False
    if (checks["unprivileged_posix_owner"] and
        checks["paper_private_owner_directory"] and
        isinstance(policy_file, Path)):
        try:
            from scripts.run_j2_j4_public_paper_resident_d453 import (
                read_owner_paper_policy,
            )
            parsed = read_owner_paper_policy(policy_file)
            checks["policy_owner_only_and_valid"] = parsed.margin_quote > 0
        except (OSError, ValueError, TypeError, RuntimeError, ImportError,
                DataValidationError):
            pass
    result={
        "schema_version":"d457-paper-resident-owner-preflight-v1",
        "status":"ready_for_finite_owner_paper_trial" if all(checks.values())
                 else "blocked_fail_closed",
        "checks":checks,
        "network_attempted":False,
        "filesystem_changed":False,
        "real_orders_sent":False,
        "production_install_authorized":False,
        "continuous_protection_verified":False,
        "venue_stop_verified":False,
    }
    return result


def main(argv: list[str]|None=None) -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--j2-directory",type=Path,required=True)
    p.add_argument("--paper-directory",type=Path,required=True)
    p.add_argument("--policy-file",type=Path,required=True)
    a=p.parse_args(argv)
    result=preflight(j2_directory=a.j2_directory,
                     paper_directory=a.paper_directory,
                     policy_file=a.policy_file)
    print(json.dumps(result,separators=(",",":"),sort_keys=True))
    return 0 if result["status"]=="ready_for_finite_owner_paper_trial" else 2


if __name__=="__main__":
    raise SystemExit(main())
