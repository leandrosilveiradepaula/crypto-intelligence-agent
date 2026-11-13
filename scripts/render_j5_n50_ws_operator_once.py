"""J5/D330: offline private N50 WS status HTML; no service/network mutation."""
from __future__ import annotations

import argparse
import json
import time

from crypto_intelligence_agent.j1_n50_ws_24h_witness import observe_n50_ws_24h
from crypto_intelligence_agent.j5_n50_ws_operator_mobile import (
    write_n50_ws_operator_html_once,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-private-readonly-audit", action="store_true")
    parser.add_argument("--enable-ws-24h-witness", action="store_true")
    parser.add_argument("--allow-private-report-write", action="store_true")
    args = parser.parse_args(argv)
    if not all((
        args.allow_private_readonly_audit,
        args.enable_ws_24h_witness,
        args.allow_private_report_write,
    )):
        print(json.dumps({
            "schema_version": "j5-n50-ws-operator-html-cli-v1",
            "status": "three_owner_optins_required",
            "orders_sent": False,
            "network_requests": 0,
            "systemd_modified": False,
        }, sort_keys=True, separators=(",", ":")))
        return 65
    now_ms = time.time_ns() // 1_000_000
    witness = observe_n50_ws_24h(
        allow_private_readonly_audit=True,
        enable_ws_24h_witness=True,
        now_ms=now_ms,
    )
    result = write_n50_ws_operator_html_once(
        witness, observed_at_ms=now_ms,
        allow_private_report_write=True,
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=True))
    return 0 if result["status"] in (
        "private_report_saved", "identical_private_report_exists",
    ) else 65


if __name__ == "__main__":
    raise SystemExit(main())
