"""Deterministic OFFLINE J1 readiness snapshot; evidence is NOT self-certifying.

This report describes the *verified repository checkpoint*, not a live probe or
a configurable permission mechanism. New evidence requires review and a code
change backed by tests, rather than arbitrary untrusted fixture flags.
"""
from __future__ import annotations

import json
from typing import Any


def readiness_snapshot() -> dict[str, Any]:
    """Return the conservative, versioned J1 research-readiness assessment."""
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
            "capability": "bybit_quote_currency",
            "status": "verified",
            "evidence_kind": "documented_schema_offline_only",
            "source": "docs/DATA_CONTRACT.md",
            "issue": 50,
            "reason": "Documented quote USDT/USDC; neither USD conversion nor live proof",
        },
    ]
    return {
        "schema_version": "j1-readiness-v1",
        "assessment_kind": "reviewed_repository_checkpoint_not_live",
        "ready_for_live_top50": False,
        "ready_for_canonical_ohlcv": False,
        "ready_for_public_market_data_release": False,
        "gates": gates,
    }


def main() -> None:
    print(json.dumps(readiness_snapshot(), ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
