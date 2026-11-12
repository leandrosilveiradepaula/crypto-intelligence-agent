"""D312: read-only owner proof for CURRENT N50 10006 HALT, no retries.

Strictly uses the actual active pointer; never trusts a named historical epoch
instead. Emits only fixed schema, counts, UTC and SHA; no prices or symbols.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from crypto_intelligence_agent.j1_n50_managed_cycle import _pointer_read
from crypto_intelligence_agent.j1_n50_halted_forensic import audit_halted_n50_epoch
from scripts.audit_bybit_marketwide_closed24h import _strict_owner

ROOT = Path("/home/cia-probe/agent/j1-n50-managed-d296-private")
EXPECTED_HALTED_EPOCH = "epoch-1794492000000"


def candidate(*, expected_epoch_id: str = EXPECTED_HALTED_EPOCH,
              allow_private_readonly_audit: bool = False) -> dict[str, Any]:
    out: dict[str, Any] = {
        "schema_version": "j1-n50-recovery-candidate-v1",
        "status": "optin_required" if not allow_private_readonly_audit else "blocked",
        "active_epoch_id": None,
        "halted_reason": None,
        "last_published_end_ms": None,
        "published_hours": 0,
        "partial_contracts_at_next_hour": 0,
        "stored_candles": 0,
        "scope_digest_sha256": None,
        "owner_integrity_verified": False,
        "resume_authorized": False,
        "network_requests": 0,
        "database_mutation_statements": 0,
        "systemd_modified": False,
        "marketwide_top50_verified": False,
        "live_trading_authorized": False,
        "orders_sent": False,
    }
    if not allow_private_readonly_audit:
        return out
    if type(expected_epoch_id) is not str or expected_epoch_id != EXPECTED_HALTED_EPOCH:
        return out
    try:
        _strict_owner(ROOT, directory=True)
        _strict_owner(ROOT / "epochs", directory=True)
        active = _pointer_read(ROOT)
        if active is None or active["epoch_id"] != expected_epoch_id:
            return out
        epoch = ROOT / "epochs" / expected_epoch_id
        _strict_owner(epoch, directory=True)
        verified = audit_halted_n50_epoch(
            scope_directory=epoch / "scope", journal_directory=epoch / "journal",
            allow_private_readonly_audit=True,
        )
        last = verified.get("last_published_end_ms")
        published = verified.get("published_hours")
        partial = verified.get("partial_contracts_at_next_hour")
        stored = verified.get("stored_candles")
        digest = verified.get("scope_digest_sha256")
        if (verified.get("status") != "halted_owner_review_verified"
                or verified.get("halted_reason") != "provider_denied_owner_review"
                or verified.get("saved_rows_integrity_verified") is not True
                or verified.get("resume_authorized") is not False
                or verified.get("historical_missing_publication_hours") != 0
                or verified.get("orders_sent") is not False
                or verified.get("network_requests") != 0
                or verified.get("database_mutation_statements") != 0
                or verified.get("systemd_modified") is not False
                or type(last) is not int or last % 3_600_000
                or type(published) is not int or not 1 <= published <= 72
                or type(partial) is not int or not 1 <= partial < 50
                or type(stored) is not int or stored != 50 * (24 + published - 1) + partial
                or type(digest) is not str or len(digest) != 64
                or digest != active["scope_digest_sha256"]):
            return out
        out.update(
            status="current_halted_epoch_candidate_verified",
            active_epoch_id=expected_epoch_id,
            halted_reason="provider_denied_owner_review",
            last_published_end_ms=last,
            published_hours=published,
            partial_contracts_at_next_hour=partial,
            stored_candles=stored,
            scope_digest_sha256=digest,
            owner_integrity_verified=True,
        )
        return out
    except (KeyError, ValueError, OSError, TypeError, OverflowError):
        return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--allow-private-readonly-audit", action="store_true")
    p.add_argument("--expected-epoch-id", default=EXPECTED_HALTED_EPOCH)
    data = candidate(**vars(p.parse_args(argv)))
    print(json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True))
    return 0 if data["status"] == "current_halted_epoch_candidate_verified" else 65


if __name__ == "__main__":
    raise SystemExit(main())
