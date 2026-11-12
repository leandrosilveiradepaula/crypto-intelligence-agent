"""J5/D301: export one owner-only, offline N50 research page after real J1 audit.

All three opt-ins are required. No HTTP server, credentials, trading commands,
market GETs, or shared/public file target. The report lives in private
owner-only storage; no symbols or OHLCV are printed to stdout.
"""
from __future__ import annotations

import argparse
import json

from crypto_intelligence_agent.j2_n50_private_screen import (
    audit_private_n50_research,
)
from crypto_intelligence_agent.j5_n50_private_html import (
    write_n50_private_html_once,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-private-readonly-audit", action="store_true")
    parser.add_argument("--allow-private-report-write", action="store_true")
    parser.add_argument("--include-private-symbols", action="store_true")
    args = parser.parse_args(argv)
    if (args.allow_private_readonly_audit is not True
            or args.allow_private_report_write is not True
            or args.include_private_symbols is not True):
        result = {
            "schema_version": "j5-n50-private-html-cli-v1",
            "status": "three_owner_optins_required",
            "orders_sent": False,
            "network_requests": 0,
            "systemd_modified": False,
        }
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 65
    report = audit_private_n50_research(
        allow_private_readonly_audit=True,
        include_private_symbols=True,
    )
    if report["status"] not in (
        "descriptive_research_ready", "btc_context_missing_research_only",
    ):
        result = {
            "schema_version": "j5-n50-private-html-cli-v1",
            "status": "audit_unavailable_or_unverified",
            "orders_sent": False,
            "network_requests": 0,
            "systemd_modified": False,
        }
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 65
    output = write_n50_private_html_once(
        report, allow_private_report_write=True,
    )
    print(json.dumps(output, sort_keys=True, separators=(",", ":")))
    return 0 if output["status"] in (
        "private_report_saved", "identical_private_report_exists",
    ) else 65


if __name__ == "__main__":
    raise SystemExit(main())
