"""D290: owner-only N50 policy inspection, offline and read-only.

Reads one existing private scope and one M1 SQLite journal. Returns a safe
planning decision; NEVER issues GET, starts systemd, writes a DB, or trades.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import time

from crypto_intelligence_agent.j1_n50_supervision import plan_n50_supervision
from crypto_intelligence_agent.j1_rest_resume_readiness import audit_existing_rest_resume
from scripts.run_j1_current_ranked_epoch_once import load_private_ranked_scope


def inspect_n50_epoch_once(
    *, manifest_directory: Path, output_directory: Path, now_ms: int,
    allow_private_manifest_read: bool = False,
    allow_private_readonly_audit: bool = False,
    owner_ok: bool | None = None,
) -> dict:
    empty = plan_n50_supervision(
        now_ms=now_ms, sealed_scope=None, audit=None).sanitized_report()
    if (allow_private_manifest_read is not True
            or allow_private_readonly_audit is not True):
        return {**empty, "reason": "explicit_private_read_optin_required"}
    owner = ((os.name == "posix" and os.getuid() == os.geteuid()
              and os.geteuid() != 0) if owner_ok is None else owner_ok)
    if owner is not True:
        return {**empty, "reason": "nonroot_owner_required"}
    if (not isinstance(manifest_directory, Path)
            or not isinstance(output_directory, Path)
            or not manifest_directory.is_absolute()
            or not output_directory.is_absolute()
            or manifest_directory == output_directory
            or manifest_directory in output_directory.parents
            or output_directory in manifest_directory.parents):
        return {**empty, "reason": "private_path_invalid"}
    try:
        manifest = load_private_ranked_scope(manifest_directory, now_ms=now_ms)
        audit = audit_existing_rest_resume(
            output_directory=output_directory, now_ms=now_ms,
            allow_private_readonly_audit=True, expected_members=50,
            owner_ok=owner,
        )
        return plan_n50_supervision(
            now_ms=now_ms, sealed_scope=manifest, audit=audit
        ).sanitized_report()
    except (OSError, ValueError, TypeError, UnicodeError, OverflowError):
        return {**empty, "reason": "private_read_or_integrity_rejected"}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest-directory", required=True, type=Path)
    p.add_argument("--output-directory", required=True, type=Path)
    p.add_argument("--allow-private-manifest-read", action="store_true")
    p.add_argument("--allow-private-readonly-audit", action="store_true")
    args = p.parse_args(argv)
    report = inspect_n50_epoch_once(
        manifest_directory=args.manifest_directory,
        output_directory=args.output_directory,
        now_ms=time.time_ns() // 1_000_000,
        allow_private_manifest_read=args.allow_private_manifest_read,
        allow_private_readonly_audit=args.allow_private_readonly_audit,
    )
    print(json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=True))
    return 0 if report["status"] in ("no_op", "deferred", "needs_external_gate") else 2


if __name__ == "__main__":
    raise SystemExit(main())
