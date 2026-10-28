"""Owner-only Binance Vision research archives; no production/live use.

Network and retention are off without explicit opt-ins. Files are written only
under a new private POSIX directory outside the checkout. No market bytes in logs.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
from urllib.error import HTTPError, URLError
from urllib.request import Request, ProxyHandler, HTTPRedirectHandler, build_opener

from crypto_intelligence_agent.market_data import DataValidationError
from crypto_intelligence_agent.vision_checksum_sidecar import parse_untrusted_local_vision_checksum
from crypto_intelligence_agent.offline_vision_month import inspect_offline_vision_month
from crypto_intelligence_agent.offline_vision_series import assemble_offline_vision_months

BASE = "https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1h/"
NAME = re.compile(r"BTCUSDT-1h-(20[0-9]{2})-(0[1-9]|1[0-2])\.zip\Z")
ZIP_LIMIT = 8_000_000
CHECKSUM_LIMIT = 256


class VisionCaptureError(ValueError):
    """Sanitized failure (never print remote bodies or filesystem paths)."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _open(request, *, timeout):
    return build_opener(ProxyHandler({}), _NoRedirect()).open(request, timeout=timeout)


def _fetch(url: str, *, limit: int, opener) -> bytes:
    if not url.startswith(BASE) or url.count("/") != BASE.count("/"):
        raise VisionCaptureError("unapproved_archive_endpoint")
    try:
        with opener(Request(url, method="GET"), timeout=10) as response:
            if response.getcode() != 200 or response.geturl() != url:
                raise VisionCaptureError("redirect_or_status_rejected")
            raw = response.read(limit + 1)
        if not 1 <= len(raw) <= limit:
            raise VisionCaptureError("archive_download_size_rejected")
        return raw
    except HTTPError as error:
        if error.code in (401, 403, 418, 429, 451):
            raise VisionCaptureError("access_restricted_no_retry") from None
        raise VisionCaptureError("http_error_no_retry") from None
    except (URLError, TimeoutError, OSError):
        raise VisionCaptureError("network_error_no_retry") from None


def _new_private_directory(path: str) -> Path:
    if os.name != "posix" or type(path) is not str:
        raise VisionCaptureError("owner_only_posix_required")
    target = Path(path)
    if not target.is_absolute() or target.exists() or target.is_symlink():
        raise VisionCaptureError("new_absolute_private_directory_required")
    if any(part in (".", "..") for part in target.parts):
        raise VisionCaptureError("unsafe_target_path")
    parent = target.parent
    if parent.is_symlink() or not parent.is_dir():
        raise VisionCaptureError("unsafe_target_parent")
    st = parent.stat()
    if (not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid()
            or st.st_mode & 0o077):
        raise VisionCaptureError("owner_only_parent_0700_required")
    # A public code checkout, or any of its ancestors, must not receive data.
    checkout = Path(__file__).resolve().parent.parent
    if target == checkout or checkout in target.parents:
        raise VisionCaptureError("checkout_storage_forbidden")
    return target


def capture_private_vision_months(
    *, names: tuple[str, str], output_dir: str,
    as_of_ms: int, allow_public_network: bool = False,
    allow_personal_nonproduction_license: bool = False,
    allow_private_archive_retention: bool = False,
    confirm_territory_and_access: bool = False,
    opened=None,
) -> dict[str, object]:
    """One-shot two-month capture. User, not this software, accepts dataset terms."""
    if not all(v is True for v in (
            allow_public_network, allow_personal_nonproduction_license,
            allow_private_archive_retention, confirm_territory_and_access)):
        raise VisionCaptureError("four_explicit_owner_opt_ins_required")
    if (type(names) is not tuple or len(names) != 2
            or any(type(n) is not str or NAME.fullmatch(n) is None for n in names)
            or type(as_of_ms) is not int or as_of_ms <= 0):
        raise VisionCaptureError("two_explicit_completed_months_required")
    first = datetime(int(names[0][11:15]), int(names[0][16:18]), 1, tzinfo=timezone.utc)
    second = datetime(int(names[1][11:15]), int(names[1][16:18]), 1, tzinfo=timezone.utc)
    if (second.year * 12 + second.month) != (first.year * 12 + first.month + 1):
        raise VisionCaptureError("contiguous_months_required")
    directory = _new_private_directory(output_dir)
    opener = opened or _open
    artifacts: list[tuple[str, bytes, bytes, str]] = []
    months = []
    for name in names:
        # Fixed host, known filename and exactly two files per month.
        checksum = _fetch(BASE + name + ".CHECKSUM", limit=CHECKSUM_LIMIT, opener=opener)
        expected = parse_untrusted_local_vision_checksum(checksum, archive_name=name)
        blob = _fetch(BASE + name, limit=ZIP_LIMIT, opener=opener)
        if sha256(blob).hexdigest() != expected:
            raise VisionCaptureError("official_checksum_digest_mismatch")
        month = inspect_offline_vision_month(
            blob, archive_name=name, expected_sha256=expected,
            as_of_ms=as_of_ms,
        )
        months.append(month)
        artifacts.append((name, blob, checksum, expected))
    series = assemble_offline_vision_months(tuple(months), as_of_ms=as_of_ms)
    manifest = json.dumps({
        "schema_version": "vision-local-series-v1",
        "as_of_ms": as_of_ms,
        "archives": [{"name": name, "sha256": digest}
                     for name, _, _, digest in artifacts],
    }, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    # Only now, after all downloads and checks, create the target. No overwrite.
    try:
        directory.mkdir(mode=0o700)
        if directory.stat().st_mode & 0o077:
            raise VisionCaptureError("private_directory_mode_rejected")
        for name, raw, checksum, _ in artifacts:
            for filename, data in ((name, raw), (name + ".CHECKSUM", checksum)):
                fd = os.open(directory / filename, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "wb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
        fd = os.open(directory / "manifest.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(manifest)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        # Target was new; do not delete any external/preexisting inputs.
        if directory.exists():
            for child in directory.iterdir():
                if child.is_file() and not child.is_symlink():
                    child.unlink()
            directory.rmdir()
        raise VisionCaptureError("private_archive_commit_rejected") from None
    return {
        "status": "private_nonproduction_research_archives_stored",
        "archive_count": 2,
        "closed_candle_count": len(series.candles),
        "series_manifest_sha256": series.series_manifest_sha256,
        "network_requests": 4, "data_stored_locally": True,
        "source_signature_verified": False, "territorial_eligibility_verified_by_software": False,
        "dataset_rights_authorized_for_live": False,
        "canonical_ohlcv_approved": False, "historical_top50_approved": False,
        "financial_backtest_approved": False, "ready_for_trading": False,
        "live_trading_authorized": False, "orders_sent": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first-month", required=True, help="BTCUSDT-1h-YYYY-MM.zip")
    parser.add_argument("--second-month", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--as-of-ms", required=True, type=int)
    for flag in ("allow-public-network", "allow-personal-nonproduction-license",
                 "allow-private-archive-retention", "confirm-territory-and-access"):
        parser.add_argument("--" + flag, action="store_true")
    args = parser.parse_args(argv)
    try:
        result = capture_private_vision_months(
            names=(args.first_month, args.second_month),
            output_dir=args.output_dir, as_of_ms=args.as_of_ms,
            allow_public_network=args.allow_public_network,
            allow_personal_nonproduction_license=args.allow_personal_nonproduction_license,
            allow_private_archive_retention=args.allow_private_archive_retention,
            confirm_territory_and_access=args.confirm_territory_and_access,
        )
    except Exception:
        result = {"status": "private_vision_capture_rejected",
                  "network_requests": "not_attested_on_failure",
                  "data_stored_locally": "not_attested_on_failure",
                  "live_trading_authorized": False, "orders_sent": False}
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return int(result["status"] != "private_nonproduction_research_archives_stored")


if __name__ == "__main__":
    raise SystemExit(main())
