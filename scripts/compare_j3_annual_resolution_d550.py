"""Read-only owner comparison of the saved hourly and fine annual reports."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from crypto_intelligence_agent.j3_resolution_comparison_d550 import (
    MAX_REPORT_BYTES, compare_annual_reports,
)
from crypto_intelligence_agent.j4_private_paper_ws_operator_d425 import (
    _owner_file, _private_directory,
)
from crypto_intelligence_agent.market_data import MarketDataError


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def read_private_report(path):
    if not path.is_absolute() or path.suffix != ".json":
        raise ValueError("absolute private JSON report required")
    home = _private_directory(path.parent)
    with os.fdopen(_owner_file(home, path.name), "rb") as stream:
        before = os.fstat(stream.fileno())
        if not 2 <= before.st_size <= MAX_REPORT_BYTES:
            raise ValueError("report size")
        raw = stream.read(MAX_REPORT_BYTES + 1)
        if (len(raw) != before.st_size or
                _identity(before) != _identity(os.fstat(stream.fileno()))):
            raise ValueError("report changed while reading")
    return raw


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hourly-report", type=Path, required=True)
    parser.add_argument("--fine-report", type=Path, required=True)
    parser.add_argument("--confirm-private-readonly-research", action="store_true")
    parser.add_argument("--compact", action="store_true",
                        help="emit only aggregate coverage and sign transitions")
    args = parser.parse_args(argv)
    try:
        if (not args.confirm_private_readonly_research or os.name != "posix"
                or os.getuid() != os.geteuid() or os.geteuid() == 0):
            raise ValueError("explicit owner-only research required")
        hourly = read_private_report(args.hourly_report)
        fine = read_private_report(args.fine_report)
        result = compare_annual_reports(hourly, fine)
        if args.compact:
            result.pop("rows")
        print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
        return 0
    except (MarketDataError, OSError, ValueError, TypeError, ArithmeticError,
            AttributeError, RecursionError) as exc:
        print(json.dumps({"status": "d550_comparison_unavailable",
                          "error_type": type(exc).__name__, "public_gets": 0,
                          "orders_sent": False, "winner_selected": False}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
