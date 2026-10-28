"""J1/HIST #241: privacy-preserving audit of EXISTING monthly Vision ZIPs.

No downloading, persistence, broker API, authentication, trading or permission
grant. The caller's hashes and filename are NOT independent provenance.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.vision_checksum_sidecar import parse_untrusted_local_vision_checksum
from crypto_intelligence_agent.offline_vision_month import inspect_offline_vision_month
from crypto_intelligence_agent.offline_vision_series import assemble_offline_vision_months
from crypto_intelligence_agent.vision_research_oos import diagnose_vision_monthly_direction
from dataclasses import asdict
from scripts.audit_private_bybit_json import _read_private_file

_SCHEMA = "vision-local-series-v1"
_NAME = re.compile(r"[A-Z0-9]{2,20}USDT-1h-20[0-9]{2}-(0[1-9]|1[0-2])\.zip\Z")
_HASH = re.compile(r"[a-f0-9]{64}\Z")
_MAX_ZIP_BYTES = 8_000_000
_MAX_TOTAL_ZIP_BYTES = 192_000_000


class VisionLocalAuditError(ValueError):
    """Do not include filenames, paths or market values in exception messages."""


def audit_private_vision_archives(
    *, manifest_path: str,
    allow_personal_nonproduction_research: bool = False,
    audit_directional_oos: bool = False,
    require_local_checksum_sidecars: bool = False,
) -> dict[str, object]:
    """Parse and assemble a private, caller-supplied contiguous archive series.

    Reading never creates a file. Check all manifest identities before reading
    archive bytes; fail closed on changed files or resource exhaustion.
    """
    if allow_personal_nonproduction_research is not True:
        raise VisionLocalAuditError("explicit_personal_nonproduction_opt_in_required")
    if type(require_local_checksum_sidecars) is not bool:
        raise VisionLocalAuditError("invalid_local_checksum_mode")
    if type(audit_directional_oos) is not bool:
        raise VisionLocalAuditError("invalid_directional_research_mode")
    if os.name != "posix":
        raise VisionLocalAuditError("private_posix_environment_required")
    try:
        manifest_raw = _read_private_file(manifest_path, max_bytes=16_384)
        manifest = json.loads(manifest_raw)
        if (type(manifest) is not dict or set(manifest) != {
                "schema_version", "as_of_ms", "archives"}
                or manifest["schema_version"] != _SCHEMA
                or type(manifest["as_of_ms"]) is not int
                or type(manifest["archives"]) is not list
                or not 2 <= len(manifest["archives"]) <= 24):
            raise VisionLocalAuditError("invalid_bounded_manifest")
        names = []
        expected_hashes = []
        for item in manifest["archives"]:
            if (type(item) is not dict or set(item) != {"name", "sha256"}
                    or type(item["name"]) is not str
                    or _NAME.fullmatch(item["name"]) is None
                    or type(item["sha256"]) is not str
                    or _HASH.fullmatch(item["sha256"]) is None):
                raise VisionLocalAuditError("invalid_archive_identity")
            names.append(item["name"])
            expected_hashes.append(item["sha256"])
        if len(set(names)) != len(names):
            raise VisionLocalAuditError("duplicate_archive_identity")
        directory = Path(manifest_path).expanduser().parent
        if not directory.is_absolute() or directory.is_symlink():
            raise VisionLocalAuditError("unsafe_private_archive_directory")
        if any((directory / name).is_symlink() for name in names):
            raise VisionLocalAuditError("unsafe_archive_symlink")
        # Optional separate, strictly bounded local .CHECKSUM texts must agree
        # with the manifest. Both remain locally supplied and UNAUTHENTICATED.
        # Preflight sidecars before loading any large ZIPs.
        if require_local_checksum_sidecars:
            for name, digest in zip(names, expected_hashes):
                local_text = _read_private_file(
                    str(directory / (name + ".CHECKSUM")), max_bytes=256,
                )
                claim = parse_untrusted_local_vision_checksum(
                    local_text, archive_name=name,
                )
                if claim != digest:
                    raise VisionLocalAuditError("local_checksum_manifest_mismatch")
        # Check a total input budget using fstat-backed private reads; a claimed
        # SHA is checked against bytes and cannot bypass ZIP/CSV verification.
        total = 0
        months = []
        for name, digest in zip(names, expected_hashes):
            blob = _read_private_file(str(directory / name), max_bytes=_MAX_ZIP_BYTES)
            total += len(blob)
            if total > _MAX_TOTAL_ZIP_BYTES or sha256(blob).hexdigest() != digest:
                raise VisionLocalAuditError("archive_size_or_digest_rejected")
            months.append(inspect_offline_vision_month(
                blob, archive_name=name, expected_sha256=digest,
                as_of_ms=manifest["as_of_ms"],
            ))
        series = assemble_offline_vision_months(
            tuple(months), as_of_ms=manifest["as_of_ms"],
        )
        directional = (diagnose_vision_monthly_direction(tuple(months), as_of_ms=manifest["as_of_ms"])
                       if audit_directional_oos else None)
        report = {
            "schema_version": _SCHEMA,
            "status": "private_unverified_monthly_series_inspected",
            "archive_count": len(series.month_names),
            "closed_candle_count": len(series.candles),
            "first_open_ms": series.first_open_ms,
            "end_open_exclusive_ms": series.end_open_exclusive_ms,
            "local_archive_identity_manifest_sha256": series.series_manifest_sha256,
            "source_authenticated": False,
            "dataset_rights_authorized": False,
            "canonical_ohlcv_approved": False,
            "historical_top50_approved": False,
            "financial_backtest_approved": False,
            "ready_for_trading": False,
            "live_trading_authorized": False,
            "orders_sent": False,
            "network_requests": 0,
            "data_stored": False,
        }
        if require_local_checksum_sidecars:
            report["untrusted_local_checksum_sidecars_matched"] = len(names)
            report["checksum_proves_provider_origin"] = False
        if directional is not None:
            report["directional_oos"] = {
                "quality": directional.quality,
                "folds": [asdict(f) for f in directional.folds],
                "source_authenticated": False,
                "dataset_rights_authorized": False,
                "financial_backtest_approved": False,
                "out_of_sample_financial_returns_validated": False,
                "ready_for_trading": False,
                "orders_sent": False,
            }
        return report
    except Exception:
        # Never print a third-party library exception containing private data
        # or paths; callers and the CLI receive a stable sanitized error.
        raise VisionLocalAuditError("private_vision_series_audit_rejected") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--allow-personal-nonproduction-research", action="store_true")
    parser.add_argument("--audit-directional-oos", action="store_true")
    parser.add_argument("--require-local-checksum-sidecars", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = audit_private_vision_archives(
            manifest_path=args.manifest,
            allow_personal_nonproduction_research=args.allow_personal_nonproduction_research,
            audit_directional_oos=args.audit_directional_oos,
            require_local_checksum_sidecars=args.require_local_checksum_sidecars,
        )
    except Exception:
        report = {
            "schema_version": _SCHEMA,
            "status": "private_vision_series_audit_rejected",
            "network_requests": 0, "data_stored": False,
            "dataset_rights_authorized": False,
            "canonical_ohlcv_approved": False,
            "financial_backtest_approved": False,
            "live_trading_authorized": False, "orders_sent": False,
        }
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return int(report["status"] != "private_unverified_monthly_series_inspected")


if __name__ == "__main__":
    raise SystemExit(main())
