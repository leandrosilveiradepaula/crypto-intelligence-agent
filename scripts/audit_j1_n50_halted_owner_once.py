"""D304: inspect only the active private halted N50 journal, never retry it.

Run as cia-probe. No CLI-provided DB path, no SQL writes, no systemd
modification, no public GET, and no trade/order action.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from crypto_intelligence_agent.j1_n50_managed_cycle import _pointer_read
from crypto_intelligence_agent.j1_n50_halted_forensic import audit_halted_n50_epoch

ROOT = Path("/home/cia-probe/agent/j1-n50-managed-d296-private")


def main(argv: list[str] | None = None) -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--allow-private-readonly-audit",action="store_true")
    opts=p.parse_args(argv)
    result={"schema_version":"j1-n50-halted-owner-forensic-v1",
            "status":"optin_required" if not opts.allow_private_readonly_audit else "blocked",
            "orders_sent":False,"resume_authorized":False,
            "systemd_modified":False,"network_requests":0}
    if opts.allow_private_readonly_audit:
        try:
            pointer=_pointer_read(ROOT)
            if pointer is not None:
                epoch=ROOT/"epochs"/pointer["epoch_id"]
                result=audit_halted_n50_epoch(
                    scope_directory=epoch/"scope",
                    journal_directory=epoch/"journal",
                    allow_private_readonly_audit=True)
        except (OSError,ValueError,TypeError):
            pass
    print(json.dumps(result,sort_keys=True,separators=(",",":"),ensure_ascii=True))
    return 0 if result["status"]=="halted_owner_review_verified" else 65


if __name__=="__main__":
    raise SystemExit(main())
