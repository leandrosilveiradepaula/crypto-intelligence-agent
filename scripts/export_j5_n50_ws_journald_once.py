"""J5/APP-DATA1: offline journalctl JSON -> count-only N50 app snapshot.

Reads bounded NDJSON from *stdin only*. Does not invoke journalctl, read a
private directory, call an API, touch systemd, create files or send orders.
Requires explicit --allow-sanitized-journald-stdin. The caller determines
whether the journalctl export is authorized; no source authentication here.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from typing import Any

from crypto_intelligence_agent.j5_n50_ws_hour_progress import (
    project_n50_ws_log_progress,
)
from crypto_intelligence_agent.market_data import DataValidationError

_MAX_INPUT_BYTES = 1_048_576
_MAX_LINES = 4096
_MAX_MESSAGE_BYTES = 8192
_UNIT = "cia-j1-n50-ws.service"
_SCHEMA = "j1-n50-ws-cached-owner-window-v1"
_US_PATTERN = re.compile(r"[0-9]{15,17}\Z")
_MIN_MS = 1_600_000_000_000
_MAX_MS = 4_102_444_800_000


def _pairs_unique(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in items:
        if key in result:
            raise DataValidationError("duplicate JSON property in journal export")
        result[key] = value
    return result


def _nonfinite(_: str) -> None:
    raise DataValidationError("nonfinite JSON field in journal export")


def _load(raw: str) -> Any:
    return json.loads(raw, object_pairs_hook=_pairs_unique,
                      parse_constant=_nonfinite)


def export_n50_journald_progress(raw: bytes, *, now_ms: int) -> dict[str, Any]:
    """Only log-derived observation; D323/marketwide approval is impossible.

    Reject a damaged report instead of ignoring it and promoting a sparse
    timeline. Service startup/preflight and systemd plain-text messages are
    ignored, but ANY malformed JSON object from that service fails closed.
    """
    if (type(raw) is not bytes or not 0 < len(raw) <= _MAX_INPUT_BYTES
            or type(now_ms) is not int
            or not _MIN_MS <= now_ms < _MAX_MS):
        raise DataValidationError("bounded journalctl JSON bytes and UTC time required")
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeError:
        raise DataValidationError("journalctl JSON must be UTF-8") from None
    if not 1 <= len(lines) <= _MAX_LINES:
        raise DataValidationError("journalctl JSON line limit exceeded")
    events = []
    for line in lines:
        if not 0 < len(line.encode("utf-8")) <= _MAX_MESSAGE_BYTES * 2:
            raise DataValidationError("oversize journalctl JSON line")
        data = _load(line)
        if type(data) is not dict:
            raise DataValidationError("journalctl entry must be JSON object")
        if data.get("_SYSTEMD_UNIT") != _UNIT:
            continue
        message = data.get("MESSAGE")
        if type(message) is not str:
            raise DataValidationError("service journal entry has no string MESSAGE")
        stripped = message.strip()
        if not stripped.startswith("{"):
            continue  # known systemd progress line, not a runner report
        if len(stripped.encode("utf-8")) > _MAX_MESSAGE_BYTES:
            raise DataValidationError("oversize N50 service MESSAGE")
        report = _load(stripped)
        if type(report) is not dict:
            raise DataValidationError("invalid JSON service report object")
        if report.get("schema_version") != _SCHEMA:
            continue  # different structured status such as owner preflight
        timestamp = data.get("__REALTIME_TIMESTAMP")
        if (type(timestamp) is not str
                or _US_PATTERN.fullmatch(timestamp) is None):
            raise DataValidationError("runner report lacks valid journald timestamp")
        at_ms = int(timestamp) // 1000
        if not _MIN_MS <= at_ms <= now_ms:
            raise DataValidationError("future or out-of-range runner report")
        events.append({"finished_at_ms": at_ms, "report": report})
        if len(events) > _MAX_LINES:
            raise DataValidationError("too many N50 closed-hour reports")
    if not events:
        raise DataValidationError("no N50 owner-hour report in journal export")
    # Existing J5 projection is the *only* authority for 24h slot arithmetic.
    # No raw MESSAGE, symbol, price, digest, file path or timestamp credential
    # is copied into the result.
    return project_n50_ws_log_progress(events, now_ms=now_ms)


def _abstain() -> int:
    print(json.dumps({
        "schema_version": "j5-n50-ws-journald-export-cli-v1",
        "status": "input_invalid_or_unavailable_abstain",
        "owner_d323_24h_audit_verified": False,
        "continuous_collector_verified": False,
        "live_trading_authorized": False,
        "orders_sent": False,
        "network_requests": 0,
        "database_accessed": False,
        "systemd_modified": False,
    }, sort_keys=True, separators=(",", ":")))
    return 65


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-sanitized-journald-stdin", action="store_true")
    args = parser.parse_args(argv)
    if args.allow_sanitized_journald_stdin is not True:
        return _abstain()
    try:
        raw = sys.stdin.buffer.read(_MAX_INPUT_BYTES + 1)
        result = export_n50_journald_progress(
            raw, now_ms=time.time_ns() // 1_000_000,
        )
    except (DataValidationError, OSError, ValueError, TypeError,
            OverflowError, UnicodeError):
        return _abstain()
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
