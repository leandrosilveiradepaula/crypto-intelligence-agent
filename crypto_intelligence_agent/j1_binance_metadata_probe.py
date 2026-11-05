"""OPS35: one bounded read-only Binance public exchangeInfo metadata census.

Default is offline. Every transport dependency is injected; actual public GET
is installed only by explicit non-root owner opt-in via the script. Never infer
marketwide rank, verified USD-M identity, license or confirmed candle from
exchangeInfo metadata or a returned SHA. No DB, credentials, background task.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re
from typing import Callable, Any

from .crypto_asset_registry import CryptoRegistrySnapshot, CryptoRegistryHistory
from .j1_binance_top50_pit import (
    BinanceCatalogCapture, _catalog, _eligible_shape, content_sha256,
    MAX_CLOCK_SKEW_MS, MAX_REGISTRY_AGE_MS,
)
from .market_data import DataValidationError

URL = "https://fapi.binance.com/fapi/v1/exchangeInfo"
MAX_BODY_BYTES = 2_000_000
MAX_GETS = 2


@dataclass(frozen=True)
class MetadataProbeReport:
    status: str
    requested: int = 0
    received: int = 0
    catalog_rows: int = 0
    reviewed_crypto_perpetuals: int = 0
    plausible_unreviewed: int = 0
    excluded_non_perp_or_non_usdt: int = 0
    catalog_digest_sha256: str | None = None
    identity_registry_applied: bool = False

    def sanitized_report(self) -> dict:
        return {
            "status": self.status, "requests_attempted": self.requested,
            "responses_validated": self.received,
            "catalog_rows": self.catalog_rows,
            "reviewed_crypto_perpetuals": self.reviewed_crypto_perpetuals,
            "plausible_unreviewed": self.plausible_unreviewed,
            "excluded_non_perp_or_non_usdt": self.excluded_non_perp_or_non_usdt,
            "catalog_membership_sha256": self.catalog_digest_sha256,
            "identity_registry_applied": self.identity_registry_applied,
            "catalog_completeness_authenticated": False,
            "usdm_contract_verified": False,
            "crypto_identity_independently_authenticated": False,
            "marketwide_top50_verified": False,
            "canonical_ohlcv_approved": False,
            "continuous_collector_authorized": False,
            "network_source_authenticated": False,
            "storage_writes": 0, "orders_sent": False,
        }


def _parse_json(data: bytes) -> dict:
    if (type(data) is not bytes or not 1 <= len(data) <= MAX_BODY_BYTES):
        raise DataValidationError("metadata_size_abstain")
    def no_duplicates(pairs):
        result = {}
        for k,v in pairs:
            if k in result:
                raise DataValidationError("metadata_duplicate_keys_abstain")
            result[k] = v
        return result
    try:
        value = json.loads(data, object_pairs_hook=no_duplicates,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except DataValidationError:
        # Preserve the explicit, sanitised duplicate-key failure instead of
        # collapsing it into an unrelated JSON syntax failure.
        raise
    except (ValueError, UnicodeDecodeError, RecursionError):
        raise DataValidationError("metadata_json_abstain") from None
    if type(value) is not dict:
        raise DataValidationError("metadata_schema_abstain")
    return value


def _error_class(exc: Exception) -> str:
    text = str(exc)
    if text in ("metadata_size_abstain", "metadata_duplicate_keys_abstain",
                "metadata_json_abstain", "metadata_schema_abstain"):
        return text
    if text.startswith("binance_http_"):
        return "metadata_http_abstain"
    return "metadata_transport_or_validation_abstain"


def capture_binance_metadata_once(*, registry: CryptoRegistrySnapshot | None = None,
    catalog_only_unverified: bool = False,
    allow_public_network: bool = False,
    confirm_region_and_personal_research: bool = False,
    owner_check: Callable[[], bool] = lambda: False,
    fetch: Callable[[str, int], bytes] | None = None,
    utc_ms: Callable[[], int] | None = None,
) -> MetadataProbeReport:
    """At most 2 GETs with no retry; hold no payload after returning.

    Default requires a fresh PIT identity registry before any GET. The extra
    opt-in catalog-only mode deliberately SKIPS identity classification: it
    accepts *no registry*, discloses no market symbols and can never authorize
    marketwide, OHLCV, USD-M identity, persistence or trading. This permits a
    bounded public metadata census when the reviewed registry is stale,
    WITHOUT backdating or weakening its freshness check for identity mode.

    The real fetch implementation must enforce the same byte cap, no redirect,
    origin pin, 8s timeout and access restriction policy independently.
    """
    if allow_public_network is not True or confirm_region_and_personal_research is not True:
        return MetadataProbeReport("metadata_owner_optin_required")
    if owner_check() is not True:
        return MetadataProbeReport("metadata_nonroot_required")
    if fetch is None or utc_ms is None or not callable(fetch) or not callable(utc_ms):
        return MetadataProbeReport("metadata_transport_not_configured")
    completed = []
    attempted = 0
    try:
        if type(catalog_only_unverified) is not bool:
            raise DataValidationError("metadata_mode_invalid")
        history = None
        if catalog_only_unverified:
            # No synthetic or stale registry can be slipped into this mode.
            if registry is not None:
                raise DataValidationError("metadata_registry_not_allowed_in_catalog_only")
            reviewed = frozenset()
        else:
            if type(registry) is not CryptoRegistrySnapshot:
                raise DataValidationError("metadata_registry_invalid")
            history = CryptoRegistryHistory((registry,))
        first_request = utc_ms()
        if type(first_request) is not int or first_request <= 0:
            raise DataValidationError("metadata_clock_abstain")
        if history is not None:
            # Reject stale/future identity before any HTTP attempt, not after.
            reviewed = history.as_of(first_request,
                max_age_ms=MAX_REGISTRY_AGE_MS).verified_crypto_bases
        for idx in range(MAX_GETS):
            requested = first_request if idx == 0 else utc_ms()
            if type(requested) is not int or requested <= 0:
                raise DataValidationError("metadata_clock_abstain")
            if completed and requested <= completed[-1][0].received_at_ms:
                raise DataValidationError("metadata_clock_abstain")
            if history is not None:
                # A registry expiring DURING a capture cannot be accepted.
                # In particular, never make a second GET after expiry.
                history.as_of(requested, max_age_ms=MAX_REGISTRY_AGE_MS)
            attempted += 1
            raw = fetch(URL, MAX_BODY_BYTES)
            received = utc_ms()
            if (type(received) is not int or received < requested
                    or received - requested > MAX_CLOCK_SKEW_MS):
                raise DataValidationError("metadata_clock_abstain")
            if history is not None:
                history.as_of(received, max_age_ms=MAX_REGISTRY_AGE_MS)
            payload = _parse_json(raw)
            capture = BinanceCatalogCapture(payload, requested, received,
                                             content_sha256(payload),
                                             caller_declares_full_response=True)
            rows, digest = _catalog(capture)
            completed.append((capture, rows, digest))
        pre, post = completed
        if pre[2] != post[2] or pre[1] != post[1] or pre[0].received_at_ms >= post[0].requested_at_ms:
            raise DataValidationError("metadata_catalog_changed_abstain")
        plausible = [row for row in pre[1].values() if _eligible_shape(row)]
        reviewed_count = sum(row["baseAsset"] in reviewed for row in plausible)
        return MetadataProbeReport(
            ("metadata_catalog_only_unverified" if catalog_only_unverified
             else "metadata_catalog_pair_research_unverified"), attempted,
            len(completed), len(pre[1]), reviewed_count,
            len(plausible)-reviewed_count, len(pre[1])-len(plausible), pre[2],
            identity_registry_applied=(not catalog_only_unverified),
        )
    except (DataValidationError, ValueError, TypeError, KeyError, RuntimeError,
            OSError, TimeoutError, OverflowError, AttributeError) as exc:
        return MetadataProbeReport(_error_class(exc), attempted, len(completed))
