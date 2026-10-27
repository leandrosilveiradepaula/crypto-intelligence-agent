"""Deterministic OFFLINE J1 readiness snapshot; evidence is NOT self-certifying.

This report describes the *verified repository checkpoint*, not a live probe or
a configurable permission mechanism. New evidence requires review and a code
change backed by tests, rather than arbitrary untrusted fixture flags.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

# Keep the original "python scripts/j1_readiness_report.py" invocation usable.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from crypto_intelligence_agent.readiness_evidence import (  # noqa: E402
    MAX_EVIDENCE_BYTES, audit_evidence_json,
)


def readiness_snapshot(*, evidence_json: str | bytes | None = None,
                       decision_at_ms: int | None = None) -> dict[str, Any]:
    """Return an offline checkpoint; optional claims never change its live gates."""
    gates = [
        {
            "capability": "crypto_only_identity",
            "status": "blocked",
            "evidence_kind": "repository_review",
            "source": "docs/CRYPTO_REGISTRY.md",
            "issue": 32,
            "reason": "No approved real, time-versioned, rights-checked crypto-only registry",
        },
        {
            "capability": "kraken_candle_volume_units",
            "status": "blocked",
            "evidence_kind": "observed_unverified",
            "source": "docs/OPERATIONAL_STATE.md",
            "issue": 36,
            "reason": "Kraken raw trade volume has no attested base/quote unit",
        },
        {
            "capability": "provider_external_rights",
            "status": "blocked",
            "evidence_kind": "repository_review",
            "source": "docs/PROVIDER_RIGHTS.md",
            "issue": 48,
            "reason": "No authenticated redistribution/commercial authorization",
        },
        {
            "capability": "binance_network_access",
            "status": "blocked",
            "evidence_kind": "observed_http_451",
            "source": "docs/OPERATIONAL_STATE.md",
            "issue": 19,
            "reason": "Region-restricted HTTP451 cannot be bypassed",
        },
        {
            "capability": "historical_coverage",
            "status": "unknown",
            "evidence_kind": "not_demonstrated",
            "source": "docs/VALIDATION_PLAN.md",
            "issue": 2,
            "reason": "No validated live point-in-time Top50 history",
        },
        {
            "capability": "closed_candle_parser",
            "status": "verified",
            "evidence_kind": "offline_tests_only",
            "source": "docs/VALIDATION_PLAN.md",
            "issue": 34,
            "reason": "Offline closed-candle staging only; not canonical OHLCV",
        },
        {
            "capability": "hyperliquid_native_candle_schema",
            "status": "verified",
            "evidence_kind": "documented_schema_offline_only",
            "source": "docs/DATA_CONTRACT.md",
            "issue": 69,
            "reason": "Official info candle schema and metadata are parsed with fixtures; units, rights, identity, real coverage remain unverified",
        },
        {
            "capability": "okx_quote_currency",
            "status": "verified",
            "evidence_kind": "documented_schema_offline_only",
            "source": "docs/DATA_CONTRACT.md",
            "issue": 60,
            "reason": "Contracts, base and quote volumes documented for linear SWAP; not live verified or licensed",
        },
        {
            "capability": "bybit_quote_currency",
            "status": "verified",
            "evidence_kind": "documented_schema_offline_only",
            "source": "docs/DATA_CONTRACT.md",
            "issue": 50,
            "reason": "Documented quote USDT/USDC; neither USD conversion nor live proof",
        },
        {
            # A single approved public-market schema/candle sample from the
            # owner's VPS, not a continuing data feed or live license.
            "capability": "bybit_public_btcusdt_three_closed_1h_candles",
            "status": "verified",
            "evidence_kind": "owner_supplied_sanitized_ssh_output",
            "source": "docs/J1_SOURCE_GATES.md",
            "issue": 213,
            "reason": (
                "Only 3 closed 1h BTCUSDT Bybit V5 candles validated in a "
                "single owner-run VPS probe on 2026-10-27; no storage, "
                "historical coverage, public-data rights or trading approval"
            ),
        },
        {
            "capability": "bybit_ticker_24h_units",
            "status": "blocked",
            "evidence_kind": "ticker_api_units_unattested",
            "source": "docs/J1_SOURCE_GATES.md",
            "issue": 196,
            "reason": (
                "Bybit V5 ticker turnover24h and volume24h units lack explicit "
                "endpoint-scoped attestation. Kline units and UI labels are "
                "not proof of REST ticker semantics."
            ),
        },
    ]
    result = {
        "schema_version": "j1-readiness-v3",
        "assessment_kind": "reviewed_repository_checkpoint_not_live",
        "ready_for_live_top50": False,
        "ready_for_canonical_ohlcv": False,
        "ready_for_public_market_data_release": False,
        "ready_for_live_order_execution": False,
        "target_execution_mode": "automated_entries_and_exits",
        "current_execution_mode": "offline_paper_not_deployed",
        "live_trading_authorized": False,
        "gates": gates,
        # These are candidate venues for FUTURE automated trading, not live
        # authorizations. Account ownership cannot prove API availability or rights.
        "automated_execution_candidates": [
            {
                "venue": "binance_usdm",
                "market": "linear_perpetual_usdt",
                "selection_status": "candidate_not_selected",
                "data_conformance": "offline_fixtures_only",
                "last_observed_access": "http_451_restricted",
                # A separate, later PRIVATE signed GET from the owner's VPS was
                # rejected with a sanitized status. Its HTTP code/cause is unknown.
                # The public HTTP451 feed observation above remains independent.
                "private_api_auth_observation": {
                    "status": "access_or_region_restricted",
                    "observed_date_utc": "2026-10-27",
                    "evidence_kind": "owner_supplied_sanitized_ssh_output",
                    "evidence_issue": 205,
                    "read_only_scope_attested_by_endpoint": False,
                    "current_access_rechecked": False,
                },
                "quote_currency": "USDT",
                "account_access_verified": False,
                "live_signal_approved": False,
                "automated_execution_approved": False,
                "exchange_order_adapter_live_approved": False,
                "order_execution_enabled": False,
            },
            {
                "venue": "bybit_v5",
                "market": "linear_perpetual_usdt_usdc",
                "selection_status": "candidate_not_selected",
                "data_conformance": "one_owner_vps_btcusdt_3_closed_1h_validation",
                "last_observed_access": "owner_vps_btcusdt_3_closed_1h_observed",
                "previous_github_actions_public_probe": {
                    "status": "bybit_access_or_region_restricted_no_retry",
                    "observed_closed_candles": 0,
                    "evidence_issue": 138,
                    "environment": "github_actions_runner_not_owner_vps",
                },
                "public_market_research_observation": {
                    "status": "private_real_bybit_base_btc_quote_usdt_observed",
                    "observed_at_utc": "2026-10-27T13:07:29+00:00",
                    "evidence_kind": "owner_supplied_sanitized_ssh_output",
                    "evidence_issue": 213,
                    "symbol": "BTCUSDT",
                    "interval": "1h",
                    "requests_attempted": 2,
                    "validated_closed_candles": 3,
                    "documented_base_unit": "BTC",
                    "documented_turnover_quote_unit": "USDT_not_USD",
                    "instrument_response_sha256": (
                        "cf3fbdc4bfe2f12c191cf122ca81f2e938c11111f7d6dbb9a075e16a7cf51651"
                    ),
                    "kline_response_sha256": (
                        "6e1727c293014f5aee5c596e90688ea6e6e091f21a9fbee0947862f75d7876d0"
                    ),
                    "registry_sha256": (
                        "a95179a342289833f3b14f0c2442163acdcb32f1ca0c9569fa01adeaa3534746"
                    ),
                    "current_access_rechecked": False,
                    "raw_market_data_stored": False,
                    "provider_signed_provenance_verified": False,
                    "historical_top50_approved": False,
                    "canonical_ohlcv_approved": False,
                    "public_or_commercial_rights_authorized": False,
                    "ready_for_trading": False,
                    "orders_sent": False,
                    "credentials_used": False,
                },
                # This field concerns a PRIVATE GET with the owner's HMAC
                # read-only key. It is NOT a successful PUBLIC market-data GET
                # and does not authorize market data, trading or distribution.
                "private_api_auth_observation": {
                    "status": "authenticated_read_only_key_confirmed",
                    "observed_date_utc": "2026-10-27",
                    "evidence_kind": "owner_supplied_sanitized_ssh_output",
                    "evidence_issue": 205,
                    "read_only_scope_attested_by_endpoint": True,
                    "current_access_rechecked": False,
                },
                "quote_currency": "USDT_or_USDC_not_USD",
                "ticker_turnover_unit_verified": False,
                "ticker_volume_unit_verified": False,
                "ticker_units_evidence_scope": "v5_rest_ticker_field_not_attested",
                # Historical successful owner-run account-auth probe, as of the
                # date above. NOT an assertion that the key remains valid now.
                "account_access_verified": True,
                "live_signal_approved": False,
                "automated_execution_approved": False,
                "exchange_order_adapter_live_approved": False,
                "order_execution_enabled": False,
            },
        ],
    }

    if evidence_json is not None:
        if decision_at_ms is None:
            raise ValueError("decision_at_ms is required for an evidence audit")
        result["provenance_review"] = audit_evidence_json(
            evidence_json, decision_at_ms=decision_at_ms,
        )
    elif decision_at_ms is not None:
        raise ValueError("decision_at_ms requires evidence_json")
    return result


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Deterministic offline J1 readiness report")
    parser.add_argument("--evidence-json", type=Path,
                        help="Optional small local JSON of untrusted provenance claims")
    parser.add_argument("--decision-at-ms", type=int,
                        help="UTC-ms decision time required with --evidence-json")
    args = parser.parse_args([] if argv is None else argv)
    if (args.evidence_json is None) != (args.decision_at_ms is None):
        parser.error("--evidence-json and --decision-at-ms must be supplied together")
    evidence = None
    if args.evidence_json is not None:
        with args.evidence_json.open("rb") as infile:
            evidence = infile.read(MAX_EVIDENCE_BYTES + 1)
    report = readiness_snapshot(evidence_json=evidence, decision_at_ms=args.decision_at_ms)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main(sys.argv[1:])
