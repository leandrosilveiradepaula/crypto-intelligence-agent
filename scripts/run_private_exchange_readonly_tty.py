"""AUTH1 private TTY launcher: HMAC credentials exist only in process memory.

Requires a real interactive terminal, user confirmation and dedicated READ-ONLY
exchange keys. No local .env, shell history, CLI secrets or persistent files.
This is NOT a trading executor or authorization to submit orders.
"""
from __future__ import annotations

import argparse
import getpass
import json
import sys
import warnings

from scripts.probe_private_exchange_readonly import _safe_result, diagnose

_ENV_NAMES = {
    "binance": ("BINANCE_READONLY_API_KEY", "BINANCE_READONLY_API_SECRET"),
    "bybit": ("BYBIT_READONLY_API_KEY", "BYBIT_READONLY_API_SECRET"),
}
_SUCCESS_STATUSES = frozenset((
    "authenticated_read_only_key_confirmed",
    "authenticated_permissions_not_attested",
))


def _report(venue: str, status: str) -> None:
    print(json.dumps(_safe_result(venue, status), sort_keys=True))


class _SanitizedParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        # argparse normally echoes unrecognized CLI values. Never print an
        # accidentally pasted API secret in errors or usage.
        self.exit(2, "invalid arguments; use --help for options\\n")


def main(argv: list[str] | None = None) -> int:
    parser = _SanitizedParser(
        description="AUTH1 private, single-GET read-only API connectivity probe (TTY only)",
    )
    parser.add_argument("--venue", required=True, choices=tuple(_ENV_NAMES))
    parser.add_argument("--allow-private-read", action="store_true")
    parser.add_argument("--confirm-read-only-key", action="store_true")
    args = parser.parse_args(argv)

    # No flags -> no secret prompt, no external request.
    if not args.allow_private_read or not args.confirm_read_only_key:
        _report(args.venue, "offline_network_disabled")
        return 1

    # Block non-interactive automation/pipes, captured terminals and unsafe
    # fallback to echoing input in getpass.
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        _report(args.venue, "interactive_tty_required")
        return 2

    key = ""
    secret = ""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            key = getpass.getpass("API key SOMENTE LEITURA (oculta): ")
            secret = getpass.getpass("API secret SOMENTE LEITURA (oculta): ")
    except (getpass.GetPassWarning, EOFError, KeyboardInterrupt, OSError, ValueError):
        _report(args.venue, "interactive_entry_cancelled")
        return 2

    if not key or not secret:
        _report(args.venue, "missing_private_credentials")
        return 2

    # Pass an explicit in-memory mapping to the existing, fixed-endpoint signed
    # GET. Never export credentials via env, argv, stdout, disk or logs.
    env_names = _ENV_NAMES[args.venue]
    ephemeral_credentials = {env_names[0]: key, env_names[1]: secret}
    key = secret = ""
    try:
        result = diagnose(
            args.venue,
            allow_private_read=True,
            confirm_read_only_key=True,
            env=ephemeral_credentials,
        )
        # No provider payload or exception is printed, only an allowlisted
        # safe status envelope returned by the AUTH1 diagnostic.
        print(json.dumps(result, sort_keys=True))
        return 0 if result["status"] in _SUCCESS_STATUSES else 1
    except Exception:
        _report(args.venue, "unexpected_diagnostic_failure")
        return 2
    finally:
        ephemeral_credentials.clear()


if __name__ == "__main__":
    sys.exit(main())
