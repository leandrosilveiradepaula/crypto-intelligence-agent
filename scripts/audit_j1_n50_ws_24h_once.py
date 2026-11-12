"""D323: opt-in owner-only audit; no network, timer, REST or orders."""
from __future__ import annotations

import argparse
import json

from crypto_intelligence_agent.j1_n50_ws_24h_witness import observe_n50_ws_24h


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-private-readonly-audit", action="store_true")
    parser.add_argument("--enable-ws-24h-witness", action="store_true")
    args = parser.parse_args(argv)
    report = observe_n50_ws_24h(
        allow_private_readonly_audit=args.allow_private_readonly_audit,
        enable_ws_24h_witness=args.enable_ws_24h_witness,
    )
    print(json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=True))
    return 0 if report["status"] == "ws_24h_local_evidence_verified" else 65


if __name__ == "__main__":
    raise SystemExit(main())
