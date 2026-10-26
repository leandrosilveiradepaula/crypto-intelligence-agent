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
    ]
    result = {
        "schema_version": "j1-readiness-v1",
        "assessment_kind": "reviewed_repository_checkpoint_not_live",
        "ready_for_live_top50": False,
        "ready_for_canonical_ohlcv": False,
        "ready_for_public_market_data_release": False,
        "gates": gates,
        # These are candidate venues for a future MANUAL action, not data-feed
        # approvals. Account ownership cannot prove API availability or rights.
        "manual_execution_candidates": [
            {
                "venue": "binance_usdm",
                "market": "linear_perpetual_usdt",
                "selection_status": "candidate_not_selected",
                "data_conformance": "offline_fixtures_only",
                "last_observed_access": "http_451_restricted",
                "quote_currency": "USDT",
                "account_access_verified": False,
                "live_signal_approved": False,
                "manual_plan_approved": False,
                "order_execution_enabled": False,
            },
            {
                "venue": "bybit_v5",
                "market": "linear_perpetual_usdt_usdc",
                "selection_status": "candidate_not_selected",
                "data_conformance": "documented_schema_offline_only",
                "last_observed_access": "first_instrument_get_restricted_no_candles",
                "quote_currency": "USDT_or_USDC_not_USD",
                "account_access_verified": False,
                "live_signal_approved": False,
                "manual_plan_approved": False,
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
