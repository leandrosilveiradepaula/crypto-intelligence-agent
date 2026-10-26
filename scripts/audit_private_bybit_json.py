"""Audit two privately saved Bybit V5 API-shaped JSON responses, OFFLINE ONLY.

Never pass account exports, API keys or private JSON to a public GitHub repo.
This tool does not fetch or authenticate market data; any response is an
UNVERIFIED local sample, regardless of whether its format passes validation.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from crypto_intelligence_agent.bybit_local_json_audit import (  # noqa: E402
    LocalBybitCaptureManifest, MAX_LOCAL_BODY, audit_local_bybit_json,
)
from crypto_intelligence_agent.market_data import MarketDataError  # noqa: E402


class PrivateLocalInputError(ValueError):
    """Sanitized error without raw file bytes, prices, path or provider data."""


def _read_private_file(value: str, *, max_bytes: int) -> bytes:
    if os.name != "posix":
        raise PrivateLocalInputError("private POSIX file permissions cannot be verified")
    if type(value) is not str or not value or type(max_bytes) is not int:
        raise PrivateLocalInputError("absolute private input file required")
    path = Path(value).expanduser()
    if not path.is_absolute() or path.is_symlink() or path.parent.is_symlink():
        raise PrivateLocalInputError("unsafe private file path")
    try:
        resolved = path.resolve(strict=True)
        if resolved == ROOT or ROOT in resolved.parents:
            raise PrivateLocalInputError("public checkout is not a private input directory")
        if path.parent.stat().st_mode & 0o077:
            raise PrivateLocalInputError("input directory must be owner-only (0700)")
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(path, flags)
        try:
            st = os.fstat(fd)
            if (not stat.S_ISREG(st.st_mode) or st.st_nlink != 1
                    or st.st_mode & 0o077 or not 1 <= st.st_size <= max_bytes):
                raise PrivateLocalInputError("private JSON must be regular 0600 file of bounded size")
            with os.fdopen(fd, "rb", closefd=False) as reader:
                raw = reader.read(max_bytes + 1)
            if not 1 <= len(raw) <= max_bytes:
                raise PrivateLocalInputError("private JSON is empty or exceeds size budget")
            if os.fstat(fd).st_size != len(raw):
                raise PrivateLocalInputError("private file changed during read")
            return raw
        finally:
            os.close(fd)
    except (OSError, RuntimeError, ValueError) as error:
        if type(error) is PrivateLocalInputError:
            raise
        raise PrivateLocalInputError("unavailable or unsafe private local input") from None


def inspect_private_inputs(
    *, manifest_path: str, instrument_path: str, kline_path: str,
    allow_private_offline_input: bool = False,
) -> dict:
    if allow_private_offline_input is not True:
        raise PrivateLocalInputError("explicit private offline input consent required")
    manifest_bytes = _read_private_file(manifest_path, max_bytes=4_096)
    manifest = LocalBybitCaptureManifest.from_json_bytes(manifest_bytes)
    if len({Path(manifest_path).resolve(), Path(instrument_path).resolve(),
            Path(kline_path).resolve()}) != 3:
        raise PrivateLocalInputError("three distinct local files are required")
    instrument = _read_private_file(instrument_path, max_bytes=MAX_LOCAL_BODY)
    klines = _read_private_file(kline_path, max_bytes=MAX_LOCAL_BODY)
    return audit_local_bybit_json(
        instrument_raw=instrument, kline_raw=klines, manifest=manifest,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--instrument", required=True)
    parser.add_argument("--kline", required=True)
    parser.add_argument("--allow-private-offline-input", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = inspect_private_inputs(
            manifest_path=args.manifest,
            instrument_path=args.instrument, kline_path=args.kline,
            allow_private_offline_input=args.allow_private_offline_input,
        )
    except (MarketDataError, PrivateLocalInputError, ValueError):
        # No original exception, filename, market data or supplied payload
        # reaches stdout, stderr, CI or the public repository.
        report = {
            "schema_version": "j1-bybit-private-local-audit-v1",
            "status": "offline_input_rejected",
            "actual_provider_origin_authenticated": False,
            "canonical_ohlcv_approved": False,
            "historical_top50_approved": False,
            "public_or_commercial_rights_authorized": False,
            "live_trading_authorized": False,
            "orders_sent": False,
            "network_requests": 0,
            "data_stored": False,
        }
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if report["status"] == "offline_schema_conformance_passed_origin_unverified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
