"""D287: seal a current D286 Top50 research epoch; run original M1 journal.

No default IO, no automatic service. Legacy N2 timer remains intact.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import time
from typing import Any

from crypto_intelligence_agent.bybit_public_j1_transport import BoundedBybitPublicClient
from crypto_intelligence_agent.j1_auto_research_epoch import (
    FILE_NAME, build_ranked_research_scope, validate_ranked_research_scope,
)
from crypto_intelligence_agent.j1_rest_incremental_owner import run_hourly_once
from scripts.audit_bybit_marketwide_closed24h import CensusAbstain, _strict_owner
from scripts.run_j1_auto_closed24h_rank_once import research_current_closed24h_once

MAX_MANIFEST_BYTES = 20_000
MAX_REPORT_BYTES = 40_000


def _decode_private_file(path: Path, *, max_bytes: int) -> dict:
    if (not isinstance(path, Path) or not path.is_absolute()
            or path.is_symlink() or path.name in ("", ".", "..")):
        raise ValueError("private_research_file_path_invalid")
    _strict_owner(path.parent, directory=True)
    _strict_owner(path, directory=False)
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        s = os.fstat(fd)
        if (not stat.S_ISREG(s.st_mode) or s.st_uid != os.geteuid()
                or stat.S_IMODE(s.st_mode) != 0o600
                or s.st_nlink != 1 or not 0 < s.st_size <= max_bytes):
            raise ValueError("private_research_file_bound_invalid")
        with os.fdopen(fd, "rb", closefd=False) as source:
            raw = source.read(max_bytes + 1)
        if not 0 < len(raw) <= max_bytes:
            raise ValueError("private_research_file_bound_invalid")
    finally:
        os.close(fd)

    def pairs(p):
        result = {}
        for k, v in p:
            if k in result:
                raise ValueError("duplicate_json_key")
            result[k] = v
        return result

    result = json.loads(
        raw.decode("ascii"), object_pairs_hook=pairs,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")),
    )
    if type(result) is not dict:
        raise ValueError("private_research_json_shape_invalid")
    return result



def _write_scope_file_once(scope_directory: Path, manifest: dict) -> None:
    """One immutable owner-only report -> epoch file, never overwrite."""
    _strict_owner(scope_directory, directory=True)
    target = scope_directory / FILE_NAME
    if target.exists() or target.is_symlink():
        raise ValueError("research_scope_epoch_already_exists")
    raw = json.dumps(manifest, ensure_ascii=True, sort_keys=True,
                     separators=(",", ":")).encode("ascii") + b"\n"
    if len(raw) > MAX_MANIFEST_BYTES:
        raise ValueError("research_scope_manifest_too_large")
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                 | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "wb", closefd=False) as dest:
            dest.write(raw)
            dest.flush()
            os.fsync(fd)
    except (OSError, ValueError):
        target.unlink(missing_ok=True)
        raise
    finally:
        os.close(fd)


def seal_current_ranked_scope_once(
    *, report_path: Path, scope_directory: Path, now_ms: int,
    allow_private_manifest_write: bool = False,
    owner_ok: bool | None = None,
) -> dict[str, Any]:
    result = {
        "schema_version": "j1-seal-current-rank-research-only-v1",
        "status": "optin_required", "manifest_written": False,
        "database_modified": False, "network_requests": 0,
        "marketwide_top50_verified": False, "orders_sent": False,
    }
    owner = ((os.name == "posix" and os.getuid() == os.geteuid()
              and os.geteuid() != 0) if owner_ok is None else owner_ok)
    if allow_private_manifest_write is not True or owner is not True:
        return result
    result["status"] = "abstain"
    try:
        if (not isinstance(report_path, Path)
                or not isinstance(scope_directory, Path)
                or not scope_directory.is_absolute()
                or report_path.parent == scope_directory
                or report_path in scope_directory.parents
                or scope_directory in report_path.parents):
            raise ValueError("unsafe_manifest_destination")
        _strict_owner(scope_directory, directory=True)
        report = _decode_private_file(report_path, max_bytes=MAX_REPORT_BYTES)
        manifest = build_ranked_research_scope(report, now_ms=now_ms)
        _write_scope_file_once(scope_directory, manifest)
        result.update({
            "status": "sealed_current_auto_rank_research_scope_only",
            "manifest_written": True,
            "scope_digest_sha256": manifest["scope_digest_sha256"],
            "research_members": 50,
            "selection_closed_hour_end_ms": manifest["closed_hour_end_ms"],
            "scope_must_rotate_after_48h": True,
        })
    except (CensusAbstain, OSError, ValueError, TypeError, UnicodeError,
            OverflowError, json.JSONDecodeError):
        result["failure_category"] = "private_scope_validation_or_write_rejected"
    return result



def capture_and_seal_current_rank_once(
    *, scope_directory: Path,
    allow_public_network: bool = False,
    confirm_region_and_personal_research: bool = False,
    allow_private_manifest_write: bool = False,
    owner_ok: bool | None = None,
    clock_ms=None,
    client: BoundedBybitPublicClient | None = None,
) -> dict[str, Any]:
    """Full-current D286 GET rank -> private N50 epoch in a SINGLE owner run.

    Never emits symbols or raw turnover and never writes a SQLite database.
    """
    out = {
        "schema_version": "j1-capture-seal-current-rank-research-only-v1",
        "status": "optin_required",
        "manifest_written": False, "database_modified": False,
        "network_accessed": False, "requests_attempted": 0,
        "marketwide_top50_verified": False, "orders_sent": False,
        "live_trading_authorized": False,
    }
    owner = ((os.name == "posix" and os.getuid() == os.geteuid()
              and os.geteuid() != 0) if owner_ok is None else owner_ok)
    if (owner is not True or allow_public_network is not True
            or confirm_region_and_personal_research is not True
            or allow_private_manifest_write is not True):
        return out
    out["status"] = "abstain"
    try:
        if (not isinstance(scope_directory, Path)
                or not scope_directory.is_absolute()):
            raise ValueError("invalid_manifest_directory")
        _strict_owner(scope_directory, directory=True)
        if ((scope_directory / FILE_NAME).exists()
                or (scope_directory / FILE_NAME).is_symlink()):
            raise ValueError("research_scope_epoch_already_exists")
        clock = clock_ms or (lambda: time.time_ns() // 1_000_000)
        active_client = client if client is not None else BoundedBybitPublicClient()
        proof = research_current_closed24h_once(
            client=active_client, clock_ms=clock,
            allow_public_network=True,
            confirm_region_and_personal_research=True,
            include_public_symbols=True, owner_ok=owner,
        )
        out["requests_attempted"] = proof.get("requests_attempted", 0)
        out["network_accessed"] = proof.get("network_accessed", False)
        if proof.get("status") != (
            "current_closed24h_provisional_perpetual_rank_research_only"
        ):
            out["failure_category"] = "full_current_capture_abstained"
            return out
        scope = build_ranked_research_scope(proof, now_ms=clock())
        _write_scope_file_once(scope_directory, scope)
        out.update({
            "status": "sealed_current_auto_rank_research_scope_only",
            "manifest_written": True,
            "research_members": 50,
            "selection_closed_hour_end_ms": scope["closed_hour_end_ms"],
            "scope_digest_sha256": scope["scope_digest_sha256"],
            "rank_digest_sha256": scope["closed24h_rank_digest_sha256"],
            "scope_must_rotate_after_48h": True,
        })
    except (CensusAbstain, OSError, ValueError, TypeError, UnicodeError,
            OverflowError):
        out["failure_category"] = "current_capture_or_private_manifest_rejected"
    return out


def load_private_ranked_scope(directory: Path, *, now_ms: int) -> dict:
    if not isinstance(directory, Path) or not directory.is_absolute():
        raise ValueError("current_research_scope_path_invalid")
    scope = _decode_private_file(
        directory / FILE_NAME, max_bytes=MAX_MANIFEST_BYTES,
    )
    validate_ranked_research_scope(scope, now_ms=now_ms, max_assets=50)
    return scope


def run_current_ranked_epoch_once(
    *, manifest_directory: Path, output_directory: Path,
    allow_public_network: bool = False,
    allow_private_storage: bool = False,
    confirm_region_and_personal_research: bool = False,
    allow_private_manifest_read: bool = False,
    owner_ok: bool | None = None, clock_ms=None,
    client: BoundedBybitPublicClient | None = None,
) -> dict[str, Any]:
    if (allow_private_manifest_read is not True
            or allow_public_network is not True
            or allow_private_storage is not True
            or confirm_region_and_personal_research is not True):
        return {
            "schema_version": "j1-auto-ranked-research-epoch-run-v1",
            "status": "owner_optin_required", "orders_sent": False,
            "database_modified": False, "network_requests": 0,
            "marketwide_top50_verified": False,
        }
    clock = clock_ms or (lambda: time.time_ns() // 1_000_000)

    def reader(directory: Path, *, include_private_symbols: bool):
        if include_private_symbols is not True:
            raise ValueError("private_research_manifest_optin_required")
        return load_private_ranked_scope(directory, now_ms=clock())

    return run_hourly_once(
        frozen_directory=manifest_directory, output_directory=output_directory,
        max_assets=50, allow_public_network=True, allow_private_storage=True,
        confirm_region_and_personal_research=True, owner_ok=owner_ok,
        clock_ms=clock, client=client, frontier_reader=reader,
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="action", required=True)
    seal = sub.add_parser("seal")
    seal.add_argument("--rank-report-file", required=True, type=Path)
    seal.add_argument("--manifest-directory", required=True, type=Path)
    seal.add_argument("--allow-private-manifest-write", action="store_true")
    capture = sub.add_parser("capture-seal")
    capture.add_argument("--manifest-directory", required=True, type=Path)
    capture.add_argument("--allow-public-network", action="store_true")
    capture.add_argument("--confirm-region-and-personal-research", action="store_true")
    capture.add_argument("--allow-private-manifest-write", action="store_true")
    run = sub.add_parser("run")
    run.add_argument("--manifest-directory", required=True, type=Path)
    run.add_argument("--output-directory", required=True, type=Path)
    run.add_argument("--allow-public-network", action="store_true")
    run.add_argument("--allow-private-storage", action="store_true")
    run.add_argument("--confirm-region-and-personal-research", action="store_true")
    run.add_argument("--allow-private-manifest-read", action="store_true")
    args = p.parse_args(argv)
    if args.action == "seal":
        report = seal_current_ranked_scope_once(
            report_path=args.rank_report_file,
            scope_directory=args.manifest_directory,
            now_ms=time.time_ns() // 1_000_000,
            allow_private_manifest_write=args.allow_private_manifest_write,
        )
        ok = report["status"] == "sealed_current_auto_rank_research_scope_only"
    elif args.action == "capture-seal":
        report = capture_and_seal_current_rank_once(
            scope_directory=args.manifest_directory,
            allow_public_network=args.allow_public_network,
            confirm_region_and_personal_research=args.confirm_region_and_personal_research,
            allow_private_manifest_write=args.allow_private_manifest_write,
        )
        ok = report["status"] == "sealed_current_auto_rank_research_scope_only"
    else:
        report = run_current_ranked_epoch_once(
            manifest_directory=args.manifest_directory,
            output_directory=args.output_directory,
            allow_public_network=args.allow_public_network,
            allow_private_storage=args.allow_private_storage,
            confirm_region_and_personal_research=args.confirm_region_and_personal_research,
            allow_private_manifest_read=args.allow_private_manifest_read,
        )
        ok = report["status"] == "research_sample_closed_hour_persisted"
    print(json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=True))
    return 0 if ok else 65


if __name__ == "__main__":
    raise SystemExit(main())
