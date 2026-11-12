"""D317: OFF-by-default owner CLI for one public N50 WS close, no REST.

This command is code-only until separately installed and approved on a VPS.
It opens a public linear WebSocket only with EVERY explicit owner opt-in.
The D316 private cache must already exist; no REST rank/metadata/kline GET
or brokerage account and no systemd mutations or order path are supported.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from crypto_intelligence_agent.j1_n50_ws_cached_runner import (
    _report, run_cached_n50_ws_owner_window,
)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest-directory", type=Path, required=True)
    p.add_argument("--ws-directory", type=Path, required=True)
    p.add_argument("--allow-private-manifest-read", action="store_true")
    p.add_argument("--allow-private-ws-scope-read", action="store_true")
    p.add_argument("--allow-private-ws-writer", action="store_true")
    p.add_argument("--allow-public-websocket", action="store_true")
    p.add_argument("--confirm-region-and-personal-research", action="store_true")
    p.add_argument("--allow-create-ws-journal", action="store_true")
    args = p.parse_args(argv)
    out = _report("ws_owner_window_optin_required")
    # Never load a socket driver unless the exact public-network and private
    # storage/read gates are ALL present. This CLI does not support secrets.
    if not all((
        args.allow_private_manifest_read,
        args.allow_private_ws_scope_read,
        args.allow_private_ws_writer,
        args.allow_public_websocket,
        args.confirm_region_and_personal_research,
    )):
        print(json.dumps(out, sort_keys=True, separators=(",", ":")))
        return 77
    if os.name != "posix" or os.getuid() != os.geteuid() or os.geteuid() == 0:
        out["status"] = "ws_owner_window_preflight_abstain"
        print(json.dumps(out, sort_keys=True, separators=(",", ":")))
        return 77
    try:
        from crypto_intelligence_agent.bybit_public_ws_once import _real_session_factory
        out = run_cached_n50_ws_owner_window(
            manifest_directory=args.manifest_directory,
            ws_directory=args.ws_directory,
            session_factory=_real_session_factory,
            allow_private_manifest_read=True,
            allow_private_ws_scope_read=True,
            allow_private_ws_writer=True,
            allow_injected_public_ws=True,
            allow_create_ws_journal=args.allow_create_ws_journal,
        )
    except (OSError, RuntimeError, ValueError, TypeError, ImportError,
            OverflowError):
        out["status"] = "ws_owner_window_integrity_abstain"
    # Output contains only fixed categories, bounded counts, UTC and SHA.
    print(json.dumps(out, sort_keys=True, separators=(",", ":"), ensure_ascii=True))
    return 0 if out["status"] == "ws_owner_hour_50_observed_local_only" else 65


if __name__ == "__main__":
    raise SystemExit(main())
