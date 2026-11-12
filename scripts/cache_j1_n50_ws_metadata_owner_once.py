"""Owner-only one-time D287 -> Bybit metadata -> private D316 WS cache.

This command does not install services, capture kline REST, start WS or send
orders. It may issue up to four public instruments-info GETs only after five
explicit flags and POSIX nonroot; 10006 never retries. It is never run on a
VPS by merely merging this source file.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from crypto_intelligence_agent.j1_n50_ws_metadata_bootstrap import (
    cache_current_n50_ws_metadata_once,
)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest-directory", type=Path, required=True)
    p.add_argument("--ws-directory", type=Path, required=True)
    p.add_argument("--allow-public-network", action="store_true")
    p.add_argument("--confirm-region-and-personal-research", action="store_true")
    p.add_argument("--enable-n50-ws-metadata-capture", action="store_true")
    p.add_argument("--allow-private-manifest-read", action="store_true")
    p.add_argument("--allow-private-ws-cache-write", action="store_true")
    a = p.parse_args(argv)
    out = cache_current_n50_ws_metadata_once(
        manifest_directory=a.manifest_directory,
        ws_directory=a.ws_directory,
        allow_public_network=a.allow_public_network,
        confirm_region_and_personal_research=a.confirm_region_and_personal_research,
        enable_n50_ws_metadata_capture=a.enable_n50_ws_metadata_capture,
        allow_private_manifest_read=a.allow_private_manifest_read,
        allow_private_ws_cache_write=a.allow_private_ws_cache_write,
    )
    print(json.dumps(out, sort_keys=True, separators=(",", ":"), ensure_ascii=True))
    if out["status"] == "ws_metadata_owner_n50_cached_for_ws_research":
        return 0
    if out["status"] == "ws_metadata_bootstrap_optin_required":
        return 77
    return 65


if __name__ == "__main__":
    raise SystemExit(main())
