"""J1/WU23: bounded, sanitized verification of Vike's *public sample manifest*.

A manifest is the provider's own assertion of license and schema. Even if it
passes these checks, the Parquet rows have NOT been inspected, the upstream
rights have NOT been independently authenticated and NO market data is ready
for trading or redistribution. No key, wallets, trades or raw values are logged.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
from hashlib import sha256
import json
import re
from typing import Any
from urllib.request import HTTPRedirectHandler, Request, build_opener


MANIFEST_URL = "https://data.vike.io/archive/hl-samples/manifest.json"
MAX_MANIFEST_BYTES = 65_536
MAX_AGE_MS = 7 * 86_400_000
_REQUIRED_FILL_FIELDS = {
    "fill_ts": "DateTime64(3, 'UTC')",
    "wallet": "String", "asset": "String", "side": "String",
    "size_token": "Float64", "price": "Float64", "size_usd": "Float64",
    "trade_id": "UInt64", "dex_name": "String",
}
_REQUIRED_POSITION_FIELDS = {
    "snapshot_ts": "DateTime('UTC')", "wallet": "String",
    "asset": "String", "size_token": "Float64", "size_usd": "Float64",
    "dex_name": "String",
}


class ManifestValidationError(ValueError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _object_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ManifestValidationError("duplicate key in public manifest")
        result[key] = value
    return result


def _nonfinite(value: str) -> None:
    raise ManifestValidationError("nonfinite value in public manifest")


def _utc_instant(raw: Any) -> datetime:
    if type(raw) is not str or re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", raw
    ) is None:
        raise ManifestValidationError("manifest timestamp must be ISO UTC seconds")
    try:
        return datetime.strptime(raw, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ManifestValidationError("invalid manifest UTC timestamp") from exc


def _utc_day(raw: Any, label: str) -> date:
    if type(raw) is not str or re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw) is None:
        raise ManifestValidationError(label + " must be ISO date")
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ManifestValidationError(label + " invalid calendar date") from exc


def _schema_fields(dataset: Any, required: dict[str, str]) -> dict[str, str]:
    if type(dataset) is not dict or type(dataset.get("schema")) is not list:
        raise ManifestValidationError("missing manifest dataset schema")
    fields: dict[str, str] = {}
    for row in dataset["schema"]:
        if type(row) is not dict:
            raise ManifestValidationError("invalid schema row")
        name, kind = row.get("name"), row.get("type")
        if type(name) is not str or type(kind) is not str or len(name) > 80 or len(kind) > 100:
            raise ManifestValidationError("malformed dataset schema field")
        if name in fields:
            raise ManifestValidationError("duplicate manifest schema column")
        fields[name] = kind
    if any(fields.get(field) != kind for field, kind in required.items()):
        raise ManifestValidationError("dataset column unit/type mismatch")
    return fields


def validate_manifest(raw: str | bytes, *, observed_at_ms: int) -> dict[str, Any]:
    """Validate publication claims, not the actual dataset or its legal license."""
    if type(observed_at_ms) is not int or observed_at_ms <= 0:
        raise ManifestValidationError("observed_at_ms must be positive integer UTC-ms")
    if type(raw) is str:
        try:
            content = raw.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ManifestValidationError("invalid manifest UTF-8") from exc
    elif type(raw) is bytes:
        content = raw
    else:
        raise ManifestValidationError("manifest must be UTF-8 JSON bytes")
    if not 1 <= len(content) <= MAX_MANIFEST_BYTES:
        raise ManifestValidationError("manifest empty or exceeds maximum bytes")
    try:
        d = json.loads(content, object_pairs_hook=_object_no_duplicates,
                       parse_constant=_nonfinite)
    except (ValueError, UnicodeDecodeError, RecursionError) as exc:
        raise ManifestValidationError("invalid public manifest JSON") from exc
    if type(d) is not dict or d.get("venue") != "hyperliquid":
        raise ManifestValidationError("manifest venue is not Hyperliquid")
    generated = _utc_instant(d.get("generated_at"))
    generated_ms = int(generated.timestamp() * 1000)
    if generated_ms > observed_at_ms or observed_at_ms - generated_ms > MAX_AGE_MS:
        raise ManifestValidationError("manifest is future-dated or stale")
    license_claim = d.get("license")
    if (type(license_claim) is not dict
            or license_claim.get("name") != "CC BY 4.0"
            or license_claim.get("url") != "https://creativecommons.org/licenses/by/4.0/"
            or type(license_claim.get("attribution")) is not str
            or not 10 <= len(license_claim["attribution"]) <= 240):
        raise ManifestValidationError("missing or unsupported license claim")
    sample = d.get("sample")
    if (type(sample) is not dict or sample.get("asset") != "BTC"
            or sample.get("files") != ["fills-sample.parquet", "positions-sample.parquet"]):
        raise ManifestValidationError("manifest sample not the fixed BTC keyless samples")
    sampled = _utc_day(sample.get("date"), "sample.date")
    datasets = d.get("datasets")
    if type(datasets) is not dict:
        raise ManifestValidationError("missing datasets")
    for key, needed in (
        ("fills", _REQUIRED_FILL_FIELDS),
        ("positions", _REQUIRED_POSITION_FIELDS),
    ):
        entry = datasets.get(key)
        fields = _schema_fields(entry, needed)
        if entry.get("sample_file") != key + "-sample.parquet":
            raise ManifestValidationError("sample file and dataset are inconsistent")
        if type(entry.get("sample_covers")) is not str or not entry["sample_covers"]:
            raise ManifestValidationError("missing sample coverage description")
        published = entry.get("published")
        if type(published) is not dict:
            raise ManifestValidationError("missing historical coverage declaration")
        earliest = _utc_day(published.get("from"), "published.from")
        latest = _utc_day(published.get("to"), "published.to")
        if (not earliest <= sampled <= latest
                or latest > generated.date()
                or type(published.get("days")) is not int
                or published["days"] <= 0
                or len(fields) > 100):
            raise ManifestValidationError("inconsistent publication/snapshot dates")
    return {
        "assessment": "publisher_manifest_metadata_only",
        "manifest_url": MANIFEST_URL,
        "manifest_sha256": sha256(content).hexdigest(),
        "generated_at_utc": d["generated_at"],
        "sample_utc_date": sample["date"],
        "sample_asset": "BTC",
        "datasets": ["fills", "positions"],
        "data_license_claimed": "CC BY 4.0",
        "fills_numeric_type": "Float64",
        "fills_are_double_sided": True,
        "sample_rows_inspected": False,
        "upstream_rights_independently_verified": False,
        "canonical_candle_units_verified": False,
        "crypto_only_universe_verified": False,
        "authorized_for_public_release": False,
        "ready_for_live_top50": False,
    }


def probe_public_manifest(
    *, allow_public_network: bool, allow_manifest_research: bool,
    observed_at_ms: int | None = None, opener: Any = None,
) -> dict[str, Any]:
    if allow_public_network is not True or allow_manifest_research is not True:
        raise ManifestValidationError("explicit double opt-in required before keyless GET")
    client = build_opener(NoRedirect()) if opener is None else opener
    req = Request(MANIFEST_URL, method="GET", headers={"Accept": "application/json"})
    try:
        with client.open(req, timeout=8) as response:
            if response.status != 200 or response.geturl() != MANIFEST_URL:
                raise ManifestValidationError("unexpected HTTP status or redirect")
            content_type = response.headers.get("Content-Type", "").split(";")[0].lower()
            if content_type not in ("application/json", "text/json"):
                raise ManifestValidationError("manifest MIME is not JSON")
            raw = response.read(MAX_MANIFEST_BYTES + 1)
    except ManifestValidationError:
        raise
    except Exception as exc:
        # Never log response body, headers, IP, cookies, account or traceback URL.
        raise ManifestValidationError("public manifest GET failed") from exc
    instant = observed_at_ms
    if instant is None:
        instant = int(datetime.now(timezone.utc).timestamp() * 1000)
    return validate_manifest(raw, observed_at_ms=instant)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Owner-only public Vike manifest research")
    parser.add_argument("--allow-public-network", action="store_true")
    parser.add_argument("--allow-vike-manifest-research", action="store_true")
    args = parser.parse_args(argv)
    result = probe_public_manifest(
        allow_public_network=args.allow_public_network,
        allow_manifest_research=args.allow_vike_manifest_research,
    )
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    main()
