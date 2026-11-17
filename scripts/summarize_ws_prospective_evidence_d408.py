"""Summarize multiple already-scored J2/J3 prospective references, offline only.

Example after authorized previous captures:
  python -m scripts.summarize_ws_prospective_evidence_d408 \
    --score /research/score-hour-a.json --score /research/score-hour-b.json \
    --output /new/path/summary.json

Each --score must be an explicit single JSON score. No directory discovery,
owner SQLite, new research decision, internet, account or orders.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import sys

from crypto_intelligence_agent.j3_ws_prospective_evidence_summary_d408 import (
    summarize_ws_prospective_references,
)
from crypto_intelligence_agent.market_data import DataValidationError

MAX_SCORE_BYTES = 8192


def _no_duplicates(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise DataValidationError("D408 duplicate score JSON key")
        result[key] = value
    return result


def _read(path: Path) -> dict:
    if not isinstance(path, Path) or not path.is_absolute() or path.is_symlink():
        raise DataValidationError("D408 expected absolute non-symlink score file")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as reader:
        metadata = os.fstat(reader.fileno())
        if not stat.S_ISREG(metadata.st_mode) or not 1 <= metadata.st_size <= MAX_SCORE_BYTES:
            raise DataValidationError("D408 score file invalid or oversized")
        raw = reader.read(MAX_SCORE_BYTES + 1)
    if not 1 <= len(raw) <= MAX_SCORE_BYTES:
        raise DataValidationError("D408 score bytes invalid")
    return json.loads(
        raw.decode("ascii"), object_pairs_hook=_no_duplicates,
        parse_constant=lambda _: (_ for _ in ()).throw(
            DataValidationError("D408 nonfinite JSON value")
        ),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--score", action="append", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if not 1 <= len(args.score) <= 256 or len(set(args.score)) != len(args.score):
            raise DataValidationError("D408 1..256 unique explicit score paths required")
        reports = tuple(_read(path) for path in args.score)
        summary = summarize_ws_prospective_references(reports)
        wire = json.dumps(summary, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False) + "\n"
        if args.output is None:
            sys.stdout.write(wire)
        else:
            path = args.output
            if not path.is_absolute() or path.is_symlink():
                raise DataValidationError("D408 output must be new absolute regular file")
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                         | getattr(os, "O_NOFOLLOW", 0), 0o600)
            with os.fdopen(fd, "w", encoding="ascii") as out:
                out.write(wire)
        return 0
    except (DataValidationError, OSError, ValueError, TypeError,
            OverflowError, UnicodeError):
        # A caller should not receive private filenames, symbols or score bytes.
        print("D408: referencias J3 ausentes ou inconsistentes.", file=sys.stderr)
        return 65


if __name__ == "__main__":
    raise SystemExit(main())
