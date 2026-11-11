"""Audit the *installed* finite REST timer against the recurring M1 template.

Read-only, nonroot, opt-in. No systemctl, systemd-run, installation, writes,
network, trades, secrets or service activation. This is not a deployment tool.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

from crypto_intelligence_agent.j1_rest_recurring_plan import (
    inspect_finite_to_recurring_rest_timer,
)
from crypto_intelligence_agent.j1_rest_resume_readiness import (
    audit_existing_rest_resume,
)
from scripts.render_j1_rest_hourly_timer import render

_TIMER = Path("/etc/systemd/system/cia-j1-rest-hourly.timer")
_SERVICE = Path("/etc/systemd/system/cia-j1-rest-hourly.service")


def audit_installed_timer(*, owner: str, repo: str, python: str,
                          frozen: str, output: str, max_assets: int,
                          now_ms: int, allow_private_readonly_audit: bool,
                          installed_timer_path: Path = _TIMER,
                          installed_service_path: Path = _SERVICE,
                          readiness_reader=audit_existing_rest_resume) -> dict:
    """Only reads known unit files and privately replays the M1 journal."""
    report = {
        "schema_version": "j1-rest-recurring-timer-preflight-v1",
        "status": "optin_required",
        "activation_authorized": False,
        "timer_activated": False,
        "service_started": False,
        "network_requests": 0,
        "database_modified": False,
        "orders_sent": False,
        "marketwide_top50_verified": False,
    }
    if allow_private_readonly_audit is not True:
        return report
    if (type(now_ms) is not int or not isinstance(installed_timer_path, Path)
            or not isinstance(installed_service_path, Path)
            or installed_timer_path != _TIMER
            or installed_service_path != _SERVICE):
        return {**report, "status": "invalid_configuration"}
    try:
        desired_service, desired_timer = render(
            owner=owner, repo=repo, python=python,
            frozen=frozen, output=output, max_assets=max_assets,
        )
        current_timer = installed_timer_path.read_text(encoding="ascii")
        current_service = installed_service_path.read_text(encoding="ascii")
        readiness = readiness_reader(
            output_directory=Path(output), now_ms=now_ms,
            allow_private_readonly_audit=True,
        )
        return inspect_finite_to_recurring_rest_timer(
            installed_timer=current_timer,
            installed_service=current_service,
            rendered_timer=desired_timer,
            rendered_service=desired_service,
            readiness=readiness, now_ms=now_ms,
        )
    except (ValueError, TypeError, OSError, UnicodeError):
        return {**report, "status": "abstain",
                "failure_category": "installed_unit_or_private_read_invalid"}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--owner", required=True)
    p.add_argument("--repo", required=True)
    p.add_argument("--python", required=True)
    p.add_argument("--frozen", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--max-assets", type=int, default=2)
    p.add_argument("--allow-private-readonly-audit", action="store_true")
    args = p.parse_args(argv)
    data = audit_installed_timer(
        owner=args.owner, repo=args.repo, python=args.python,
        frozen=args.frozen, output=args.output, max_assets=args.max_assets,
        now_ms=time.time_ns() // 1_000_000,
        allow_private_readonly_audit=args.allow_private_readonly_audit,
    )
    print(json.dumps(data, sort_keys=True, separators=(",", ":")))
    return 0 if data["status"] == (
        "recurring_unit_verified_pending_operational_gate"
    ) else 2


if __name__ == "__main__":
    raise SystemExit(main())
