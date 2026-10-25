"""Explicitly versioned, date-gated local research-only crypto identity manifests.

This module reads only checked-in identity URLs/review metadata. It fetches NO
market data or publisher API; an integrity hash does not certify licenses,
assets' future status, or perpetual listing availability.
"""
from __future__ import annotations

from pathlib import Path

from .crypto_asset_registry import (
    CryptoRegistryHistory, CryptoRegistrySnapshot, load_registry_json,
)
from .market_data import DataValidationError

_ROOT = Path(__file__).resolve().parent.parent / "registries"
REGISTRY_VARIANTS = frozenset({"btc-eth", "expanded-10"})
_FILES = {
    "btc-eth": _ROOT / "crypto-btc-eth-20261025-v1.json",
    "expanded-10": _ROOT / "crypto-bases-10-20261025-v2.json",
}


def load_reviewed_registry(
    variant: str, *, as_of_ms: int,
) -> CryptoRegistrySnapshot:
    """Read the exact requested registry revision, never silently backdate.

    A caller asking for v2 before its observation must receive an error, not
    an earlier registry implicitly relabeled as v2. Old v1 remains available
    as an explicit replay input after v2 was created.
    """
    if type(variant) is not str or variant not in REGISTRY_VARIANTS:
        raise DataValidationError("unsupported research-only registry revision")
    if type(as_of_ms) is not int or as_of_ms <= 0:
        raise DataValidationError("registry lookup needs positive UTC-ms observation")
    previous = load_registry_json(_FILES["btc-eth"].read_bytes())
    revisions = CryptoRegistryHistory((previous,))
    if variant == "expanded-10":
        newer = load_registry_json(_FILES["expanded-10"].read_bytes())
        revisions.append(newer)
        desired = newer
    else:
        desired = previous
    selected = revisions.as_of(as_of_ms, max_age_ms=7 * 86_400_000)
    if selected.sha256_digest != desired.sha256_digest:
        raise DataValidationError("requested crypto registry revision was not yet known")
    return selected
