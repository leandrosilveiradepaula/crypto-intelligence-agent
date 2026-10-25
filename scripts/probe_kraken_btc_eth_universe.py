"""J1/WU35: one-shot, PRIVATE, current BTC/ETH Kraken research universe.

Reuse existing Kraken GET-only client, signed dated asset registry, pure
selector and SQLiteMarketDataStore. Never claim Top50 or public-data rights.
No raw instruments, quote volumes, prices or DB files leave this process.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from time import time
from typing import Any, Callable

from crypto_intelligence_agent.crypto_asset_registry import (
    CryptoRegistryHistory, load_registry_json,
)
from crypto_intelligence_agent.kraken_public_readonly import (
    KrakenPublicReadOnlyResearch, SOURCE as KRAKEN_SOURCE,
)
from crypto_intelligence_agent.market_data import (
    DataTimeoutError, DataValidationError, ExchangeAccessError, HttpResponseError,
)
from crypto_intelligence_agent.storage import SQLiteMarketDataStore

REGISTRY_PATH = (Path(__file__).resolve().parent.parent /
                 "registries" / "crypto-btc-eth-20261025-v1.json")
MAX_CAPTURE_AGE_MS = 30_000
MAX_REGISTRY_AGE_MS = 7 * 86_400_000


class UniverseProbeError(ValueError):
    pass


def inspect_once(
    *, allow_public_network: bool, allow_private_kraken_universe: bool,
    client: Any | None = None, clock_ms: Callable[[], int] | None = None,
    registry_data: bytes | None = None,
) -> dict[str, Any]:
    if allow_public_network is not True or allow_private_kraken_universe is not True:
        raise UniverseProbeError("double_opt_in_required")
    clock = clock_ms or (lambda: int(time() * 1000))
    now = clock()
    if type(now) is not int or not 0 < now < 253_402_300_799_999:
        raise UniverseProbeError("invalid_utc_clock")
    registry = load_registry_json(
        REGISTRY_PATH.read_bytes() if registry_data is None else registry_data)
    if registry.observed_at_ms > now:
        raise UniverseProbeError("reviewed_registry_not_yet_observed")
    history = CryptoRegistryHistory((registry,))
    report: dict[str, Any] = {
        "schema_version": "j1-kraken-btc-eth-private-universe-v1",
        "provider": "kraken_futures",
        "observed_at_utc": datetime.fromtimestamp(now / 1000, timezone.utc)
            .isoformat(timespec="seconds"),
        "requests_attempted_exact": None, "max_gets": 2,
        "credentials_used": False, "orders_sent": False,
        "raw_responses_persisted": False,
        "market_data_published": False,
        "retained_market_data_after_run": False,
        "registry_sha256": registry.sha256_digest,
        "registry_bases_count": len(registry.assets),
        "ranking_quote_currency": "USD",
        "historical_top50_approved": False,
        "canonical_ohlcv_approved": False,
        "volume_unit_verified": False,
        "commercial_or_public_rights_verified": False,
        "ready_for_trading": False,
    }
    reader = client or KrakenPublicReadOnlyResearch(allow_public_network=True)
    try:
        observed = reader.current_market_snapshot()
        if (observed.source != KRAKEN_SOURCE
                or type(observed.captured_start_ms) is not int
                or type(observed.captured_end_ms) is not int
                or observed.captured_start_ms < now
                or observed.captured_end_ms < observed.captured_start_ms
                or observed.captured_end_ms - now > MAX_CAPTURE_AGE_MS):
            raise UniverseProbeError("invalid_live_capture_timing_or_source")
        decision_time = clock()
        if (type(decision_time) is not int
                or decision_time < observed.captured_end_ms
                or decision_time - observed.captured_end_ms > MAX_CAPTURE_AGE_MS):
            raise UniverseProbeError("invalid_decision_clock")
        snapshot = history.select_at(
            instruments=observed.instruments, tickers=observed.tickers,
            market_observed_at_ms=observed.observed_at_ms,
            decision_at_ms=decision_time,
            max_market_age_ms=MAX_CAPTURE_AGE_MS,
            max_registry_age_ms=MAX_REGISTRY_AGE_MS,
            max_symbols=min(50, len(registry.assets)),
        )
        with TemporaryDirectory() as directory:
            store = SQLiteMarketDataStore(
                Path(directory) / "private_current_universe.sqlite")
            store.save_universe_snapshot(snapshot)
            store.save_universe_snapshot(snapshot)  # idempotent on repeated identical input
            recorded = store.universe_snapshot(
                observed_at_ms=snapshot.observed_at_ms,
                selection_rule_version=snapshot.selection_rule_version,
                source=snapshot.source,
            )
            if recorded != snapshot:
                raise UniverseProbeError("ephemeral_snapshot_roundtrip_mismatch")
            if len(recorded.eligible) > len(registry.assets):
                raise UniverseProbeError("universe_exceeds_registry_size")
            report["eligible_contracts_count"] = len(recorded.eligible)
            report["excluded_contracts_count"] = len(recorded.excluded)
            report["ephemeral_sqlite_roundtrip"] = True
        report["requests_attempted_exact"] = 2
        report["status"] = (
            "private_current_universe_validated" if snapshot.eligible
            else "no_eligible_crypto_contracts_in_current_sample"
        )
    except ExchangeAccessError:
        report["status"] = "access_restricted_no_retry"
    except DataTimeoutError:
        report["status"] = "network_timeout_no_retry"
    except HttpResponseError:
        report["status"] = "market_metadata_http_failure"
    except DataValidationError:
        report["status"] = "market_metadata_or_registry_validation_rejected"
    except UniverseProbeError as error:
        report["status"] = str(error)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-public-network", action="store_true")
    parser.add_argument("--allow-private-kraken-universe", action="store_true")
    args = parser.parse_args()
    try:
        result = inspect_once(
            allow_public_network=args.allow_public_network,
            allow_private_kraken_universe=args.allow_private_kraken_universe)
    except UniverseProbeError as error:
        result = {"status": str(error), "max_gets": 2,
                  "requests_attempted_exact": None, "orders_sent": False}
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["status"] == "private_current_universe_validated" else 1


if __name__ == "__main__":
    raise SystemExit(main())
