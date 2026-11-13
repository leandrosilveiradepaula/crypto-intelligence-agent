"""J5/PROGRESS1: offline stdin -> count-only JSON or static PT-BR HTML.

No journald, network, database, path, systemd or trading access. The operator
must supply a pre-sanitized envelope from an independent read-only source.
"""
from __future__ import annotations

import argparse
import json
import sys

from crypto_intelligence_agent.j5_n50_ws_hour_progress import (
    project_n50_ws_log_progress, render_n50_ws_log_progress_html,
)
from crypto_intelligence_agent.market_data import DataValidationError

_MAX_INPUT = 1_048_576


def _unique_pairs(items):
    obj = {}
    for key, value in items:
        if key in obj:
            raise ValueError("duplicate JSON key")
        obj[key] = value
    return obj


def _nonfinite(value):
    raise ValueError("nonfinite JSON numeric token")


def _error(status: str) -> int:
    print(json.dumps({
        "schema_version": "j5-n50-ws-log-progress-cli-v1",
        "status": status,
        "data_stored": False,
        "database_accessed": False,
        "network_requests": 0,
        "systemd_modified": False,
        "orders_sent": False,
    }, sort_keys=True, separators=(",", ":")))
    return 65


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-sanitized-stdin-read", action="store_true")
    parser.add_argument("--format", choices=("json", "html"), default="json")
    args = parser.parse_args(argv)
    if args.allow_sanitized_stdin_read is not True:
        return _error("optin_required")
    try:
        raw = sys.stdin.buffer.read(_MAX_INPUT + 1)
        if not 1 <= len(raw) <= _MAX_INPUT:
            return _error("input_invalid_abstain")
        doc = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_unique_pairs,
            parse_constant=_nonfinite,
        )
        if (type(doc) is not dict
                or set(doc) != {"schema_version", "now_ms", "events"}
                or doc["schema_version"] != "j5-n50-ws-count-only-input-v1"):
            return _error("input_invalid_abstain")
        if args.format == "html":
            rendered = render_n50_ws_log_progress_html(
                doc["events"], now_ms=doc["now_ms"],
            )
            sys.stdout.write(rendered)
        else:
            report = project_n50_ws_log_progress(
                doc["events"], now_ms=doc["now_ms"],
            )
            print(json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=True))
        return 0
    except (DataValidationError, ValueError, TypeError, UnicodeError,
            OverflowError, OSError):
        return _error("input_invalid_abstain")


if __name__ == "__main__":
    raise SystemExit(main())
