"""J1/PIT1: owner-only read-only coverage audit of EXISTING Vision manifest dirs.

No market download, files written, public OHLC, asset names or trading.
A matching set of local samples never proves the historical eligible Top50.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat

from scripts.audit_private_bybit_json import _read_private_file
from scripts.audit_offline_vision_series import audit_private_vision_archives

_MAX_SYMBOLS = 50
_NAME = re.compile(r"[A-Z0-9]{2,20}USDT-1h-20[0-9]{2}-(?:0[1-9]|1[0-2])\.zip\Z")


class VisionCoverageAuditError(ValueError):
    """Never include private paths, symbols or exchange payloads in errors."""


def _unique_json(pairs):
    data = {}
    for key, value in pairs:
        if key in data:
            raise VisionCoverageAuditError("duplicate_manifest_json_key")
        data[key] = value
    return data


def audit_private_vision_multiasset_coverage(
    *, manifest_paths: tuple[str, ...],
    allow_personal_nonproduction_research: bool = False,
) -> dict[str, object]:
    """Audit 1..50 sibling private archives; only publish aggregate metadata."""
    if allow_personal_nonproduction_research is not True:
        raise VisionCoverageAuditError("personal_nonproduction_opt_in_required")
    if (os.name != "posix" or type(manifest_paths) is not tuple
            or not 1 <= len(manifest_paths) <= _MAX_SYMBOLS
            or any(type(value) is not str for value in manifest_paths)):
        raise VisionCoverageAuditError("bounded_private_posix_inputs_required")
    try:
        paths = tuple(Path(value) for value in manifest_paths)
        if (len(set(paths)) != len(paths)
                or any(not p.is_absolute() or p.name != "manifest.json"
                       or p.is_symlink() or p.parent.is_symlink()
                       or p.resolve(strict=True) != p for p in paths)):
            raise VisionCoverageAuditError("unsafe_or_duplicate_private_manifest")
        roots = {p.parent.parent for p in paths}
        if len(roots) != 1:
            raise VisionCoverageAuditError("unrelated_private_roots")
        root = next(iter(roots))
        root_stat = root.stat()
        if (root.is_symlink() or root.resolve(strict=True) != root
                or not stat.S_ISDIR(root_stat.st_mode)
                or root_stat.st_uid != os.getuid() or root_stat.st_mode & 0o077):
            raise VisionCoverageAuditError("unsafe_private_root")
        coverage = []
        symbols = set()
        signature = None
        for path in paths:
            # Calls the existing fully bounded ZIP+SHA+calendar+sidecar auditor.
            report = audit_private_vision_archives(
                manifest_path=str(path), allow_personal_nonproduction_research=True,
                require_local_checksum_sidecars=True,
            )
            if (report["status"] != "private_unverified_monthly_series_inspected"
                    or report.get("untrusted_local_checksum_sidecars_matched")
                    != report["archive_count"]):
                raise VisionCoverageAuditError("private_series_not_validated")
            raw = _read_private_file(str(path), max_bytes=16_384)
            manifest = json.loads(raw, object_pairs_hook=_unique_json)
            if (type(manifest) is not dict or set(manifest) != {
                    "schema_version", "as_of_ms", "archives"}
                    or type(manifest["archives"]) is not list
                    or not manifest["archives"]):
                raise VisionCoverageAuditError("invalid_research_manifest")
            names = [row["name"] for row in manifest["archives"]]
            if any(type(name) is not str or _NAME.fullmatch(name) is None for name in names):
                raise VisionCoverageAuditError("invalid_research_symbol")
            symbol = names[0].split("-1h-")[0]
            if (any(not name.startswith(symbol + "-1h-") for name in names)
                    or symbol in symbols):
                raise VisionCoverageAuditError("duplicate_or_mixed_asset")
            symbols.add(symbol)
            current = (
                report["first_open_ms"], report["end_open_exclusive_ms"],
                report["closed_candle_count"], report["archive_count"],
            )
            if signature is None:
                signature = current
            elif signature != current:
                raise VisionCoverageAuditError("unmatched_historical_calendar")
            coverage.append((symbol, report["local_archive_identity_manifest_sha256"]))
        # A deterministic digest of local claims, not an exchange signature.
        data = "\n".join(f"{s}:{d}" for s, d in sorted(coverage)).encode("ascii")
        return {
            "schema_version": "vision-private-coverage-v1",
            "status": "private_research_coverage_audited",
            "observed_symbol_count": len(symbols),
            "archive_count": len(coverage) * signature[3],
            "aligned_closed_1h_hours": signature[2],
            "total_research_candle_rows": len(symbols) * signature[2],
            "first_open_ms": signature[0],
            "end_open_exclusive_ms": signature[1],
            "observed_sample_identity_sha256": sha256(data).hexdigest(),
            "has_two_or_more_local_assets": len(symbols) >= 2,
            "research_only": True,
            "historical_top50_verified": False,
            "historical_listing_eligibility_verified": False,
            "usd_comparable_volume_verified": False,
            "source_authenticated": False,
            "dataset_rights_authorized_for_live": False,
            "canonical_ohlcv_approved": False,
            "financial_backtest_approved": False,
            "ready_for_trading": False,
            "live_trading_authorized": False,
            "orders_sent": False,
            "network_requests": 0,
            "data_stored": False,
        }
    except Exception:
        raise VisionCoverageAuditError("private_vision_multiasset_audit_rejected") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", action="append", required=True)
    parser.add_argument("--allow-personal-nonproduction-research", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = audit_private_vision_multiasset_coverage(
            manifest_paths=tuple(args.manifest),
            allow_personal_nonproduction_research=args.allow_personal_nonproduction_research,
        )
    except Exception:
        result = {
            "schema_version": "vision-private-coverage-v1",
            "status": "private_vision_multiasset_audit_rejected",
            "network_requests": 0, "data_stored": False,
            "historical_top50_verified": False,
            "live_trading_authorized": False, "orders_sent": False,
        }
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return int(result["status"] != "private_research_coverage_audited")


if __name__ == "__main__":
    raise SystemExit(main())
