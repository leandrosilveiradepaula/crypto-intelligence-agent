"""Opt-in LOCAL Kraken BTC research collector, no auto scheduling.

Do not run on a shared or public website. Store only in an existing private
directory outside the public repository. No market data is printed.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import sqlite3

from crypto_intelligence_agent.private_kraken_research import (
    LocalResearchError, capture_private_research,
)
from crypto_intelligence_agent.market_data import (
    DataGapError, DataTimeoutError, DataValidationError,
    DuplicateCandleError, ExchangeAccessError, HttpResponseError,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True,
                        help="absolute path outside repo, in owner-only directory (0700)")
    parser.add_argument("--allow-public-network", action="store_true")
    parser.add_argument("--allow-private-persistence", action="store_true")
    args = parser.parse_args(argv)
    try:
        summary = capture_private_research(
            db_path=args.database, allow_public_network=args.allow_public_network,
            allow_private_persistence=args.allow_private_persistence,
        )
        result = {"status": "private_local_capture_complete", **asdict(summary)}
    except LocalResearchError as error:
        result = {"status": error.args[0]}
    except ExchangeAccessError:
        result = {"status": "public_exchange_access_restricted_no_retry"}
    except DataTimeoutError:
        result = {"status": "public_exchange_network_failure_no_retry"}
    except HttpResponseError:
        result = {"status": "public_exchange_http_failure_no_retry"}
    except (DataGapError, DataValidationError, DuplicateCandleError):
        result = {"status": "data_or_local_replay_validation_failed"}
    except (OSError, sqlite3.DatabaseError):
        result = {"status": "private_local_sqlite_failure"}
    result.update({
        "canonical_ohlcv_approved": False,
        "historical_top50_approved": False,
        "commercial_or_public_rights_verified": False,
        "orders_sent": False,
    })
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["status"] == "private_local_capture_complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
