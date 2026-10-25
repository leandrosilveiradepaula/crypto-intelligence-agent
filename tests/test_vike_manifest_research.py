"""Vike manifest structural tests. No network, API key or real wallet payloads."""
import copy
from datetime import datetime, timezone
import json
import unittest
from unittest.mock import Mock

from scripts.probe_vike_public_manifest import (
    MANIFEST_URL, MAX_MANIFEST_BYTES, ManifestValidationError,
    probe_public_manifest, validate_manifest,
)


NOW = int(datetime(2026, 10, 25, 16, tzinfo=timezone.utc).timestamp() * 1000)


def fixture():
    def dataset(path, names, first):
        return {
            "sample_file": path,
            "sample_covers": "synthetic BTC data for one short interval",
            "published": {"from": first, "to": "2026-10-21", "days": 150},
            "schema": [{"name": name, "type": kind} for name, kind in names],
        }
    return {
        "venue": "hyperliquid",
        "generated_at": "2026-10-22T12:56:48Z",
        "license": {
            "name": "CC BY 4.0",
            "url": "https://creativecommons.org/licenses/by/4.0/",
            "attribution": "Hyperliquid sample (c) Vike CC BY 4.0",
        },
        "sample": {
            "asset": "BTC", "date": "2026-10-21",
            "files": ["fills-sample.parquet", "positions-sample.parquet"],
        },
        "datasets": {
            "fills": dataset("fills-sample.parquet", [
                ("fill_ts", "DateTime64(3, 'UTC')"), ("wallet", "String"),
                ("asset", "String"), ("side", "String"),
                ("size_token", "Float64"), ("price", "Float64"),
                ("size_usd", "Float64"), ("trade_id", "UInt64"),
                ("dex_name", "String")], "2026-05-01"),
            "positions": dataset("positions-sample.parquet", [
                ("snapshot_ts", "DateTime('UTC')"), ("wallet", "String"),
                ("asset", "String"), ("size_token", "Float64"),
                ("size_usd", "Float64"), ("dex_name", "String")], "2026-05-08"),
        },
    }


def parse(obj=None, *, observed=NOW):
    return validate_manifest(
        json.dumps(fixture() if obj is None else obj), observed_at_ms=observed
    )


class FakeReply:
    status = 200
    headers = {"Content-Type": "application/json"}

    def __init__(self, raw, *, url=MANIFEST_URL):
        self.raw = raw
        self.url = url

    def geturl(self):
        return self.url

    def read(self, maxlen):
        return self.raw[:maxlen]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class VikeManifestTests(unittest.TestCase):
    def test_valid_metadata_is_not_a_license_or_dataset_validation(self):
        result = parse()
        self.assertEqual(result["assessment"], "publisher_manifest_metadata_only")
        self.assertEqual(result["data_license_claimed"], "CC BY 4.0")
        self.assertEqual(result["sample_utc_date"], "2026-10-21")
        self.assertEqual(result["sample_asset"], "BTC")
        self.assertEqual(result["datasets"], ["fills", "positions"])
        self.assertEqual(len(result["manifest_sha256"]), 64)
        for gate in ("sample_rows_inspected", "upstream_rights_independently_verified",
                     "canonical_candle_units_verified", "crypto_only_universe_verified",
                     "authorized_for_public_release", "ready_for_live_top50"):
            self.assertFalse(result[gate])

    def test_replay_deterministic_and_sha_sensitive(self):
        self.assertEqual(parse(), parse(copy.deepcopy(fixture())))
        changed = fixture()
        changed["sample"]["date"] = "2026-10-20"
        self.assertNotEqual(parse(changed)["manifest_sha256"], parse()["manifest_sha256"])

    def test_malformed_duplicate_nan_and_empty(self):
        for body in (b"", b"{}", b"[]", b'{"venue":"hyperliquid","venue":"fake"}',
                     b'{"venue":NaN}', b"\xff", b"x" * (MAX_MANIFEST_BYTES + 1)):
            with self.subTest(body=body[:20]), self.assertRaises(ManifestValidationError):
                validate_manifest(body, observed_at_ms=NOW)

    def test_reject_license_claim_changes_and_absence(self):
        for replacement in ("CC0", "MIT", "", False):
            doc = fixture()
            doc["license"]["name"] = replacement
            with self.subTest(replacement=replacement), self.assertRaises(ManifestValidationError):
                parse(doc)
        doc = fixture()
        doc["license"]["url"] = "https://fake-license.example"
        with self.assertRaises(ManifestValidationError):
            parse(doc)

    def test_wrong_venue_sample_market_or_archive_paths(self):
        changes = [
            ("venue", "polymarket"),
            ("sample", {"asset": "ETH", "date": "2026-10-21", "files": ["x"]}),
            ("datasets", {}),
        ]
        for key, val in changes:
            doc = fixture()
            doc[key] = val
            with self.subTest(key=key), self.assertRaises(ManifestValidationError):
                parse(doc)

    def test_future_and_expired_manifest(self):
        with self.assertRaises(ManifestValidationError):
            parse(observed=int(datetime(2026, 10, 21, tzinfo=timezone.utc).timestamp()*1000))
        with self.assertRaises(ManifestValidationError):
            parse(observed=int(datetime(2026, 11, 10, tzinfo=timezone.utc).timestamp()*1000))
        for invalid in (True, 0, -1, 1.5, "now"):
            with self.subTest(value=invalid), self.assertRaises(ManifestValidationError):
                parse(observed=invalid)

    def test_invalid_calendar_dates_and_timeline(self):
        mutations = [
            ("generated_at", "2026-13-99T12:56:48Z"),
            ("generated_at", "2026-10-22"),
            ("sample", {"date": "2026-10-99", "asset": "BTC",
                        "files": ["fills-sample.parquet", "positions-sample.parquet"]}),
            ("sample", {"date": "2026-11-01", "asset": "BTC",
                        "files": ["fills-sample.parquet", "positions-sample.parquet"]}),
        ]
        for key, value in mutations:
            doc = fixture()
            doc[key] = value
            with self.subTest(key=key), self.assertRaises(ManifestValidationError):
                parse(doc)

    def test_numeric_units_cannot_be_misrepresented(self):
        for dataset, field, kind in (
            ("fills", "size_usd", "Decimal"),
            ("fills", "price", "String"),
            ("fills", "trade_id", "String"),
            ("positions", "snapshot_ts", "DateTime"),
            ("positions", "size_token", "Float32"),
        ):
            d = fixture()
            for row in d["datasets"][dataset]["schema"]:
                if row["name"] == field:
                    row["type"] = kind
            with self.subTest(dataset=dataset, field=field), self.assertRaises(ManifestValidationError):
                parse(d)

    def test_duplicate_columns_and_missing_wallet_field(self):
        d = fixture()
        d["datasets"]["fills"]["schema"].append(
            {"name": "price", "type": "Float64"}
        )
        with self.assertRaises(ManifestValidationError):
            parse(d)
        d = fixture()
        d["datasets"]["positions"]["schema"] = [
            row for row in d["datasets"]["positions"]["schema"]
            if row["name"] != "wallet"
        ]
        with self.assertRaises(ManifestValidationError):
            parse(d)

    def test_inconsistent_publication_ranges_and_files(self):
        for field, value in (("from", "2026-10-25"), ("to", "2026-11-01"),
                             ("days", 0), ("days", True)):
            d = fixture()
            d["datasets"]["fills"]["published"][field] = value
            with self.subTest(field=field), self.assertRaises(ManifestValidationError):
                parse(d)
        d = fixture()
        d["datasets"]["fills"]["sample_file"] = "other.parquet"
        with self.assertRaises(ManifestValidationError):
            parse(d)

    def test_get_not_permitted_by_default(self):
        for network, explicit in ((False, False), (False, True), (True, False)):
            with self.subTest(network=network, explicit=explicit):
                with self.assertRaises(ManifestValidationError):
                    probe_public_manifest(
                        allow_public_network=network, allow_manifest_research=explicit,
                        observed_at_ms=NOW, opener=Mock(),
                    )

    def test_one_get_only_to_fixed_endpoint_without_credentials(self):
        raw = json.dumps(fixture()).encode()
        fake = Mock()
        fake.open.return_value = FakeReply(raw)
        result = probe_public_manifest(
            allow_public_network=True, allow_manifest_research=True,
            observed_at_ms=NOW, opener=fake,
        )
        self.assertEqual(result["assessment"], "publisher_manifest_metadata_only")
        self.assertEqual(fake.open.call_count, 1)
        req, = fake.open.call_args.args
        self.assertEqual(req.full_url, MANIFEST_URL)
        self.assertEqual(req.get_method(), "GET")
        self.assertNotIn("Authorization", req.headers)
        self.assertNotIn("x-api-key", {x.lower() for x in req.headers})

    def test_redirect_wrong_mime_or_bad_http_fails_closed(self):
        raw = json.dumps(fixture()).encode()
        for mutation in ("redirect", "mime", "status", "network"):
            fake = Mock()
            reply = FakeReply(raw)
            if mutation == "redirect":
                reply.url = "https://different.example.com"
            elif mutation == "mime":
                reply.headers = {"Content-Type": "text/html"}
            elif mutation == "status":
                reply.status = 403
            else:
                fake.open.side_effect = OSError("PRIVATE_IP_TOKEN")
            if mutation != "network":
                fake.open.return_value = reply
            with self.subTest(mutation=mutation), self.assertRaises(ManifestValidationError) as err:
                probe_public_manifest(
                    allow_public_network=True, allow_manifest_research=True,
                    observed_at_ms=NOW, opener=fake,
                )
            self.assertNotIn("PRIVATE_IP_TOKEN", str(err.exception))


if __name__ == "__main__":
    unittest.main()
