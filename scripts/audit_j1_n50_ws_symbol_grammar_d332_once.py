"""D332: owner-only count whether legacy WS parser rejects active sealed N50 symbols.

No network, trading, database writes or private identities in stdout.
"""
from __future__ import annotations

import argparse
import json

from crypto_intelligence_agent.j1_n50_ws_symbol_grammar_d332 import (
    observe_n50_ws_symbol_grammar_owner,
)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--allow-private-pointer-read", action="store_true")
    p.add_argument("--allow-private-manifest-read", action="store_true")
    p.add_argument("--allow-private-ws-scope-read", action="store_true")
    p.add_argument("--allow-owner-symbol-grammar-audit", action="store_true")
    args = p.parse_args(argv)
    report = observe_n50_ws_symbol_grammar_owner(
        allow_private_pointer_read=args.allow_private_pointer_read,
        allow_private_manifest_read=args.allow_private_manifest_read,
        allow_private_ws_scope_read=args.allow_private_ws_scope_read,
        allow_owner_symbol_grammar_audit=args.allow_owner_symbol_grammar_audit,
    )
    print(json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=True))
    return 0 if report["status"] == "single_letter_legacy_mismatch_in_scope" else 65


if __name__ == "__main__":
    raise SystemExit(main())
