"""J2/D300: one owner-only observed N50 24-closed-bar research snapshot.

Without --include-private-symbols, stdout has count-only metrics. Passing the
flag prints descriptive per-symbol OHLCV-derived research, NOT order intents,
marketwide Top50 certification, a predictive signal or investment advice.
"""
from __future__ import annotations

import argparse
import json

from crypto_intelligence_agent.j2_n50_private_screen import (
    audit_private_n50_research,
)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--allow-private-readonly-audit", action="store_true")
    p.add_argument("--include-private-symbols", action="store_true")
    opts = vars(p.parse_args(argv))
    result = audit_private_n50_research(**opts)
    print(json.dumps(result, sort_keys=True, ensure_ascii=True,
                     separators=(",", ":")))
    return 0 if result["status"] in (
        "descriptive_research_ready", "btc_context_missing_research_only",
    ) else 65


if __name__ == "__main__":
    raise SystemExit(main())
