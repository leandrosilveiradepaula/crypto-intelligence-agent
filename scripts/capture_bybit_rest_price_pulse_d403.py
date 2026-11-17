"""Capture one bounded Bybit public REST price sample, not a live feed.

Example:
  python -m scripts.capture_bybit_rest_price_pulse_d403 \
    --symbols BTCUSDT,ETHUSDT --output /tmp/cia-bybit-prices.json

Never uses an API key, user account, order endpoint, J1 owner SQLite,
background service, scheduled poll, or retry.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from crypto_intelligence_agent.bybit_public_rest_price_pulse_d403 import (
    capture_public_rest_price_pulse,
)
from crypto_intelligence_agent.bybit_public_j1_transport import J1BybitCaptureError
from crypto_intelligence_agent.market_data import DataGapError, DataValidationError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", required=True,
                        help="Independent reviewed USDT symbol CSV (1..50)")
    parser.add_argument("--output", type=Path, help="New private JSON file")
    args = parser.parse_args(argv)
    try:
        names = tuple(args.symbols.split(","))
        report = capture_public_rest_price_pulse(symbols=names)
        wire = json.dumps(report, ensure_ascii=True, sort_keys=True,
                          separators=(",", ":")) + "\n"
        if args.output is None:
            sys.stdout.write(wire)
        else:
            path = args.output
            if not path.is_absolute() or path.is_symlink():
                raise DataValidationError("D403 output must be absolute and regular")
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as out:
                out.write(wire)
    except (J1BybitCaptureError, DataValidationError, DataGapError,
            OSError, ValueError):
        # Do not echo provider response, URL, symbols or private paths.
        sys.stderr.write("D403: amostra indisponivel; nenhum arquivo confiavel.\n")
        return 65
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
