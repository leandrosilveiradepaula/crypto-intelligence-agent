"""J1 #217: owner-only Bybit local JSON to isolated research SQLite, OFFLINE.

No GET/POST, credentials, canonical feed, permissions, trading or deployment.
Input origin and rights remain UNVERIFIED even after successful staging.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from crypto_intelligence_agent.bybit_local_json_audit import (  # noqa: E402
    LocalBybitCaptureManifest, MAX_LOCAL_BODY, audit_local_bybit_json,
)
from crypto_intelligence_agent.bybit_research_storage import SQLiteBybitResearchStore  # noqa: E402
from crypto_intelligence_agent.private_kraken_research import (  # noqa: E402
    _private_db_path, _create_private_file,
)
from scripts.audit_private_bybit_json import _read_private_file  # noqa: E402


class PrivateBybitStagingError(ValueError):
    """Never include private input paths or payload in the error message."""


def stage_owner_supplied_bybit_files(
    *, manifest_path: str, instrument_path: str, kline_path: str,
    database_path: str,
    allow_private_offline_input: bool = False,
    allow_private_research_staging: bool = False,
    attest_source_and_retention_rights_reviewed: bool = False,
) -> dict[str, object]:
    """Stage existing owner-supplied files, only after three explicit opt-ins.

    The attestation is a user's claim, NOT a legally verified provider grant.
    Use real data only after an independent rights/territory review.
    """
    if (allow_private_offline_input is not True
            or allow_private_research_staging is not True
            or attest_source_and_retention_rights_reviewed is not True):
        raise PrivateBybitStagingError("three_explicit_local_opt_ins_required")
    if os.name != "posix":
        raise PrivateBybitStagingError("owner_only_posix_required")
    target = _private_db_path(database_path)
    if target.exists() and target.stat().st_nlink != 1:
        raise PrivateBybitStagingError("hardlinked_database_rejected")
    try:
        paths = tuple(Path(p).resolve(strict=False)
                      for p in (manifest_path, instrument_path, kline_path))
    except (TypeError, ValueError, OSError):
        raise PrivateBybitStagingError("invalid_local_file_path") from None
    if len(set(paths + (target.resolve(strict=False),))) != 4:
        raise PrivateBybitStagingError("distinct_local_inputs_and_db_required")
    manifest = LocalBybitCaptureManifest.from_json_bytes(
        _read_private_file(manifest_path, max_bytes=4096)
    )
    instrument_raw = _read_private_file(instrument_path, max_bytes=MAX_LOCAL_BODY)
    kline_raw = _read_private_file(kline_path, max_bytes=MAX_LOCAL_BODY)
    audit = audit_local_bybit_json(
        instrument_raw=instrument_raw, kline_raw=kline_raw, manifest=manifest,
    )
    if audit["status"] != "offline_schema_conformance_passed_origin_unverified":
        raise PrivateBybitStagingError("unverified_bybit_schema_rejected")

    # The existing research store revalidates BOTH raw documents, and
    # commits a whole page atomically. There is no HTTP code in this CLI.
    created = _create_private_file(target)
    try:
        store = SQLiteBybitResearchStore(target)
        saved = store.commit_raw_pair(
            instrument_raw=instrument_raw, kline_raw=kline_raw,
            manifest=manifest, capture_environment="private_local_unverified",
        )
        replay = store.replay_page(
            symbol=manifest.symbol, interval=manifest.interval,
            start_open_ms=manifest.start_open_ms,
            end_open_ms=manifest.end_open_ms,
        )
        quality = store.quality_report(
            symbol=manifest.symbol, interval=manifest.interval,
            start_open_ms=manifest.start_open_ms,
            end_open_ms=manifest.end_open_ms,
        )
        if (saved != replay or not quality.complete_for_offline_staging_only
                or saved.rights_authorized or saved.canonical_ohlcv_approved
                or saved.live_trading_authorized):
            raise PrivateBybitStagingError("research_replay_rejected")
    except Exception:
        # Never erase an existing database. A newly created file is removed
        # on failed staging; input raw files are left untouched.
        if created:
            try:
                target.unlink()
            except OSError:
                pass
        raise
    return {
        "schema_version": "j1-bybit-private-research-import-v1",
        "status": "private_local_research_page_staged_unverified",
        "staged_closed_candles": len(saved.candles),
        "expected_closed_candles": quality.expected_candles,
        "replay_and_quality_complete_offline_only": True,
        "network_requests": 0, "data_stored_locally": True,
        "provider_authenticated": False, "rights_authorized": False,
        "canonical_ohlcv_approved": False, "historical_top50_approved": False,
        "financial_backtest_approved": False, "ready_for_trading": False,
        "live_trading_authorized": False, "orders_sent": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("manifest", "instrument", "kline", "database"):
        parser.add_argument("--" + name, required=True)
    for name in (
        "allow-private-offline-input",
        "allow-private-research-staging",
        "attest-source-and-retention-rights-reviewed",
    ):
        parser.add_argument("--" + name, action="store_true")
    args = parser.parse_args(argv)
    try:
        report = stage_owner_supplied_bybit_files(
            manifest_path=args.manifest, instrument_path=args.instrument,
            kline_path=args.kline, database_path=args.database,
            allow_private_offline_input=args.allow_private_offline_input,
            allow_private_research_staging=args.allow_private_research_staging,
            attest_source_and_retention_rights_reviewed=(
                args.attest_source_and_retention_rights_reviewed
            ),
        )
    except Exception:
        report = {
            "schema_version": "j1-bybit-private-research-import-v1",
            "status": "private_research_import_rejected",
            "network_requests": 0,
            "data_stored_locally": "not_attested_on_failure",
            "rights_authorized": False, "canonical_ohlcv_approved": False,
            "historical_top50_approved": False,
            "financial_backtest_approved": False,
            "live_trading_authorized": False, "orders_sent": False,
        }
    print(json.dumps(report, separators=(",", ":"), sort_keys=True))
    return 0 if report["status"] == "private_local_research_page_staged_unverified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
