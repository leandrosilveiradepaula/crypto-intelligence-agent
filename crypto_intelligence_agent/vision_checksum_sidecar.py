"""J1 #259: parse a local, untrusted Binance Vision sha256sum sidecar.

This has NO network access, provider authentication or licensing authority.
It only checks that a private sidecar names exactly the expected archive.
The caller must independently compare the returned digest with the ZIP bytes
and its manifest hash; neither comparison proves Binance provenance.
"""
from __future__ import annotations

import re

from .market_data import DataValidationError

_ARCHIVE = re.compile(
    r"[A-Z0-9]{2,20}USDT-1h-20[0-9]{2}-(?:0[1-9]|1[0-2])\.zip\Z"
)
_SIDECAR = re.compile(
    rb"([0-9a-f]{64}) (?: |\*)([A-Z0-9]{2,20}USDT-1h-20[0-9]{2}-(?:0[1-9]|1[0-2])\.zip)\Z"
)
_MAX_SIDECAR_BYTES = 256


def parse_untrusted_local_vision_checksum(
    raw: bytes, *, archive_name: str,
) -> str:
    """Accept one strict sha256sum line, optionally terminated by CRLF/LF.

    The .CHECKSUM text is an untrusted local claim until its origin is
    independently established. No path components, escape mode, BOM, hash
    uppercase, blank lines or multiple checksum entries are permitted.
    """
    if (type(raw) is not bytes or not 1 <= len(raw) <= _MAX_SIDECAR_BYTES
            or type(archive_name) is not str
            or _ARCHIVE.fullmatch(archive_name) is None):
        raise DataValidationError("invalid untrusted local checksum identity")
    line = raw[:-1] if raw.endswith(b"\n") else raw
    if line.endswith(b"\r"):
        line = line[:-1]
    match = _SIDECAR.fullmatch(line)
    if (match is None or
            match.group(2) != archive_name.encode("ascii")):
        raise DataValidationError("local checksum format or ZIP name mismatch")
    return match.group(1).decode("ascii")
