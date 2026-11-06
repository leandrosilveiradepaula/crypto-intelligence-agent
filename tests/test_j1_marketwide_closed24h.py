"""J1/TOP50: offline fixture-only tests; no HTTP, real credentials or orders."""
from __future__ import annotations

from contextlib import closing
from pathlib import Path
import json
import os
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from urllib.parse import urlsplit, parse_qs

from scripts.audit_bybit_marketwide_closed24h import (
    HOUR_MS, CensusAbstain, _catalog, _closed_candles, _dec, run_census,
)

NOW = 1793971800000
END = NOW // HOUR_MS * HOUR_MS
SYMS = tuple(f"COIN{x:03d}USDT" for x in range(60))


def catalog(symbols=SYMS):
    return {"retCode": 0, "time": NOW-1000, "result": {
        "category": "linear", "nextPageCursor": "", "list": [
            {"symbol": s, "baseCoin": s[:-4], "contractType": "LinearPerpetual",
             "status": "Trading", "quoteCoin": "USDT", "settleCoin": "USDT"} for s in symbols
        ]}}


def bars(symbol, end=END):
    return {"retCode": 0, "result": {"category": "linear", "symbol": symbol,
        "list": [[str(end-(i+1)*HOUR_MS), "100.1", "102", "99", "100.2",
                  "2.0", str(100+i)] for i in range(24)]}}


class FakeClient:
    def __init__(self, *, fail_on=0, drift=False, members=SYMS):
        self.requests_attempted = 0
        self.fail_on = fail_on
        self.drift = drift
        self.members = members

    def get(self, url):
        self.requests_attempted += 1
        if self.requests_attempted == self.fail_on:
            raise CensusAbstain("provider_denied")
        parsed = urlsplit(url)
        if parsed.path.endswith("instruments-info"):
            payload = (catalog(self.members[:-1]+("CHANGEDUSDT",))
                       if self.drift else catalog(self.members))
        else:
            params = parse_qs(parsed.query)
            payload = bars(params["symbol"][0], end=END)
        return json.dumps(payload).encode("ascii"), payload


class MarketwideClosed24hTests(unittest.TestCase):
    def setUp(self):
        if os.name != "posix":
            self.skipTest("POSIX private SQLite and flock only")
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / "owner-research"

    def run_batch(self, client=None, size=10, **kw):
        params = dict(directory=self.directory, now_ms=lambda: NOW,
            client=client or FakeClient(), max_contracts=size,
            allow_public_network=True, allow_private_storage=True,
            confirm_region_and_personal_research=True, owner_ok=True)
        params.update(kw)
        return run_census(**params)

    def test_one_batch_and_resume_does_not_redownload_previous_members(self):
        a = self.run_batch(size=10)
        self.assertEqual(a["status"], "basic_market_24h_batch_partial_unverified")
        self.assertEqual(a["completed_contracts"], 10)
        self.assertEqual(a["validated_closed_1h_rows"], 240)
        self.assertEqual(a["requests_attempted"], 11)
        self.assertFalse(a["marketwide_top50_verified"])
        b = self.run_batch(size=60)
        self.assertEqual(b["status"], "basic_market_24h_closed_rank_complete_unverified")
        self.assertEqual(b["requests_attempted"], 51)
        self.assertEqual(b["completed_contracts"], 60)
        self.assertEqual(b["validated_closed_1h_rows"], 1440)
        self.assertTrue(b["full_basic_contract_24h_ranking_complete"])
        self.assertEqual(b["top50_basic_count"], 50)
        self.assertEqual(len(b["top50_basic_digest_sha256"]), 64)
        c = self.run_batch()
        self.assertEqual(c["requests_attempted"], 1)
        self.assertEqual(c["top50_basic_digest_sha256"], b["top50_basic_digest_sha256"])
        self.assertNotIn("COIN001", json.dumps(b))

    def test_partial_failure_preserves_previous_completed_contracts(self):
        first = self.run_batch(client=FakeClient(fail_on=5), size=20)
        self.assertEqual(first["status"], "abstain")
        self.assertEqual(first["requests_attempted"], 5)
        self.assertEqual(first["completed_contracts"], 3)
        with closing(sqlite3.connect(self.directory / "j1-marketwide-closed24h.sqlite")) as conn:
            count = conn.execute("SELECT count(*) FROM candles").fetchone()[0]
        self.assertEqual(count, 72)
        second = self.run_batch(size=10)
        self.assertEqual(second["completed_contracts"], 13)
        self.assertEqual(second["requests_attempted"], 11)

    def test_822_basic_contracts_complete_by_seven_bounded_batches(self):
        symbols = tuple(f"COIN{x:04d}USDT" for x in range(822))
        last = None
        total_gets = 0
        for batch in range(7):
            last = self.run_batch(client=FakeClient(members=symbols), size=120)
            total_gets += last["requests_attempted"]
            self.assertLessEqual(last["requests_attempted"], 121)
            self.assertFalse(last["marketwide_top50_verified"])
        self.assertEqual(last["status"], "basic_market_24h_closed_rank_complete_unverified")
        self.assertEqual(last["completed_contracts"], 822)
        self.assertEqual(last["validated_closed_1h_rows"], 822*24)
        self.assertEqual(last["top50_basic_count"], 50)
        self.assertEqual(total_gets, 829)

    def test_scope_drift_vetoes_before_kline_requests(self):
        self.run_batch(size=2)
        drifted = self.run_batch(client=FakeClient(drift=True), size=10)
        self.assertEqual(drifted["status"], "abstain")
        self.assertEqual(drifted["failure_stage"], "sqlite_integrity")
        self.assertEqual(drifted["requests_attempted"], 1)

    def test_bad_stored_bar_rejected_without_new_kline(self):
        self.run_batch(size=1)
        db = self.directory / "j1-marketwide-closed24h.sqlite"
        with closing(sqlite3.connect(db)) as conn, conn:
            conn.execute("UPDATE candles SET quote_turnover='NaN' WHERE symbol=?", (SYMS[0],))
        a = self.run_batch(size=8)
        self.assertEqual(a["status"], "abstain")
        self.assertEqual(a["failure_stage"], "replay")
        self.assertEqual(a["requests_attempted"], 1)

    def test_sqlite_blob_does_not_pass_decimal_text_replay(self):
        self.run_batch(size=1)
        db = self.directory / "j1-marketwide-closed24h.sqlite"
        with closing(sqlite3.connect(db)) as conn, conn:
            conn.execute(
                "UPDATE candles SET quote_turnover=? WHERE symbol=?",
                (sqlite3.Binary(b"100"), SYMS[0]),
            )
        a = self.run_batch(size=5)
        self.assertEqual(a["status"], "abstain")
        self.assertEqual(a["failure_stage"], "replay")
        self.assertEqual(a["requests_attempted"], 1)

    def test_short_live_candle_history_is_explicitly_incomplete_not_ranked(self):
        class ShortHistory(FakeClient):
            def get(self, url):
                raw, payload = super().get(url)
                if urlsplit(url).path.endswith("/kline"):
                    payload["result"]["list"] = payload["result"]["list"][:10]
                return raw, payload

        report = self.run_batch(client=ShortHistory(), size=5)
        self.assertEqual(report["status"], "basic_market_24h_survey_partial_unverified")
        self.assertEqual(report["completed_contracts"], 0)
        self.assertEqual(report["incomplete_24h_contracts"], 5)
        self.assertEqual(report["incomplete_24h_rows"], 50)
        self.assertEqual(report["inspected_contracts"], 5)
        self.assertEqual(report["remaining_contracts"], 55)
        self.assertEqual(report["requests_attempted"], 6)
        self.assertEqual(report["top50_basic_count"], 0)
        self.assertFalse(report["full_basic_contract_24h_ranking_complete"])
        self.assertFalse(report["marketwide_top50_verified"])
        self.assertNotIn("COIN000", json.dumps(report))

    def test_allowlisted_diagnostic_for_transport_and_unknown_errors(self):
        from crypto_intelligence_agent.bybit_public_j1_transport import J1BybitCaptureError

        class TransportDenied(FakeClient):
            def get(self, url):
                if self.requests_attempted == 1:
                    self.requests_attempted += 1
                    raise J1BybitCaptureError("network_error_no_retry")
                return super().get(url)

        bad = self.run_batch(client=TransportDenied(), size=5)
        self.assertEqual(bad["failure_category"], "transport_or_http")
        self.assertEqual(bad["failure_code"], "network_error_no_retry")
        self.assertEqual(bad["completed_contracts"], 0)
        self.assertEqual(bad["requests_attempted"], 2)

        class UnexpectedTransport(FakeClient):
            def get(self, url):
                if self.requests_attempted == 1:
                    self.requests_attempted += 1
                    raise J1BybitCaptureError("PRIVATE_SYMBOL_OR_URL_SECRET")
                return super().get(url)

        unknown = self.run_batch(client=UnexpectedTransport(), size=5)
        self.assertEqual(unknown["failure_code"], "unclassified_transport")
        self.assertNotIn("PRIVATE_SYMBOL", json.dumps(unknown))
        self.assertEqual(unknown["requests_attempted"], 2)

    def test_diagnostic_integrity_is_distinct_from_insufficient_history(self):
        class BadOHLC(FakeClient):
            def get(self, url):
                raw, payload = super().get(url)
                if urlsplit(url).path.endswith("/kline"):
                    payload["result"]["list"][0][2] = "50"
                return raw, payload

        result = self.run_batch(client=BadOHLC(), size=3)
        self.assertEqual(result["failure_category"], "candle_integrity_or_time")
        self.assertEqual(result["failure_code"], "kline_ohlcv_integrity_abstain")
        self.assertEqual(result["requests_attempted"], 2)

    def test_scientific_decimal_is_exact_finite_and_bounded(self):
        from decimal import Decimal
        self.assertEqual(_dec("1.2E-8"), Decimal("1.2E-8"))
        self.assertEqual(_dec("0e-8"), Decimal("0E-8"))
        self.assertEqual(_dec("3e+2"), Decimal("300"))
        self.assertEqual(_dec("1e-48"), Decimal("1E-48"))
        self.assertEqual(_dec("1e+48"), Decimal("1E+48"))
        for invalid in (
            "NaN", "Infinity", "1e9999", "1e49", "1e-49", "1e-999",
            "-1e-8", "+1", "1e1e2", "1 E-2", "1e", "1e+", "1e--1",
            "1e0001", "01e-1", "0x1", "", "1" * 97, 1e-8,
        ):
            with self.subTest(invalid=invalid), self.assertRaises(CensusAbstain):
                _dec(invalid)

    def test_scientific_ohlcv_can_resume_and_preserve_exact_text(self):
        class Scientific(FakeClient):
            def get(self, url):
                raw, payload = super().get(url)
                if urlsplit(url).path.endswith("/kline"):
                    payload["result"]["list"][0][1] = "1.2E-8"
                    payload["result"]["list"][0][2] = "1.3E-8"
                    payload["result"]["list"][0][3] = "1.1E-8"
                    payload["result"]["list"][0][4] = "1.2E-8"
                    payload["result"]["list"][0][5] = "1.23e-5"
                    payload["result"]["list"][0][6] = "0E-8"
                return raw, payload

        first = self.run_batch(client=Scientific(), size=1)
        self.assertEqual(first["status"], "basic_market_24h_batch_partial_unverified")
        self.assertEqual(first["completed_contracts"], 1)
        self.assertEqual(first["requests_attempted"], 2)
        with closing(sqlite3.connect(
            self.directory / "j1-marketwide-closed24h.sqlite")) as conn:
            values = conn.execute(
                "SELECT open, base_volume, quote_turnover FROM candles "
                "WHERE symbol=? ORDER BY open_ms DESC LIMIT 1", (SYMS[0],)
            ).fetchone()
        self.assertEqual(values, ("1.2E-8", "1.23e-5", "0E-8"))
        repeated = self.run_batch(size=1)
        self.assertEqual(repeated["status"], "basic_market_24h_batch_partial_unverified")
        self.assertEqual(repeated["completed_contracts"], 2)
        self.assertEqual(repeated["requests_attempted"], 2)

    def test_decimal_field_identified_without_echoing_raw_values(self):
        class BadVolume(FakeClient):
            def get(self, url):
                raw, payload = super().get(url)
                if urlsplit(url).path.endswith("/kline"):
                    payload["result"]["list"][0][6] = "SECRET_BAD_VOLUME"
                return raw, payload

        result = self.run_batch(client=BadVolume(), size=1)
        self.assertEqual(result["status"], "abstain")
        self.assertEqual(result["failure_code"], "invalid_candle_decimal")
        self.assertEqual(result["invalid_decimal_field"], "quote_turnover")
        self.assertEqual(result["failure_category"], "candle_integrity_or_time")
        self.assertEqual(result["requests_attempted"], 2)
        self.assertNotIn("SECRET_BAD_VOLUME", json.dumps(result))
        self.assertNotIn("COIN000", json.dumps(result))
        self.assertEqual(result["completed_contracts"], 0)

    def test_incomplete_24h_is_persisted_not_ranked_and_not_refetched(self):
        class ShortOne(FakeClient):
            def get(self, url):
                raw, payload = super().get(url)
                if (urlsplit(url).path.endswith("/kline")
                        and parse_qs(urlsplit(url).query)["symbol"][0] == SYMS[2]):
                    payload["result"]["list"] = payload["result"]["list"][:10]
                return raw, payload

        a = self.run_batch(client=ShortOne(), size=6)
        self.assertEqual(a["status"], "basic_market_24h_survey_partial_unverified")
        self.assertEqual(a["completed_contracts"], 5)
        self.assertEqual(a["incomplete_24h_contracts"], 1)
        self.assertEqual(a["incomplete_24h_rows"], 10)
        self.assertEqual(a["inspected_contracts"], 6)
        self.assertEqual(a["remaining_contracts"], 54)
        self.assertFalse(a["full_basic_contract_24h_ranking_complete"])
        self.assertFalse(a["marketwide_top50_verified"])
        self.assertEqual(a["requests_attempted"], 7)

        b = self.run_batch(client=ShortOne(), size=60)
        self.assertEqual(b["completed_contracts"], 59)
        self.assertEqual(b["incomplete_24h_contracts"], 1)
        self.assertEqual(b["inspected_contracts"], 60)
        self.assertEqual(b["remaining_contracts"], 0)
        self.assertEqual(b["requests_attempted"], 55)
        self.assertEqual(b["status"], "basic_market_24h_survey_complete_with_incomplete_unverified")
        self.assertFalse(b["full_basic_contract_24h_ranking_complete"])
        self.assertEqual(b["top50_basic_count"], 0)
        self.assertEqual(b["top50_complete_subset_count"], 50)
        self.assertEqual(len(b["top50_complete_subset_digest_sha256"]), 64)

        c = self.run_batch(client=ShortOne(), size=60)
        self.assertEqual(c["requests_attempted"], 1)
        self.assertEqual(c["incomplete_24h_contracts"], 1)
        self.assertEqual(c["status"], b["status"])

    def test_short_history_integrity_gap_is_fail_closed(self):
        class ShortGap(FakeClient):
            def get(self, url):
                raw, payload = super().get(url)
                if urlsplit(url).path.endswith("/kline"):
                    rows = payload["result"]["list"][:10]
                    rows[8][0] = str(END - 14*HOUR_MS)
                    payload["result"]["list"] = rows
                return raw, payload

        result = self.run_batch(client=ShortGap(), size=5)
        self.assertEqual(result["status"], "abstain")
        self.assertEqual(result["failure_code"], "kline_missing_open_or_future_hour")
        self.assertEqual(result["incomplete_24h_contracts"], 0)
        self.assertEqual(result["completed_contracts"], 0)
        self.assertEqual(result["requests_attempted"], 2)

    def test_incomplete_saved_json_corruption_rejected_before_kline_get(self):
        class ShortOne(FakeClient):
            def get(self, url):
                raw, payload = super().get(url)
                if urlsplit(url).path.endswith("/kline"):
                    payload["result"]["list"] = payload["result"]["list"][:8]
                return raw, payload

        a = self.run_batch(client=ShortOne(), size=1)
        self.assertEqual(a["incomplete_24h_contracts"], 1)
        db_path = self.directory / "j1-marketwide-closed24h.sqlite"
        with closing(sqlite3.connect(db_path)) as db, db:
            db.execute("UPDATE incomplete SET candles_json='[]' WHERE symbol=?", (SYMS[0],))
        b = self.run_batch(size=1)
        self.assertEqual(b["status"], "abstain")
        self.assertEqual(b["failure_stage"], "replay")
        self.assertEqual(b["failure_code"], "short_history_replay_invalid")
        self.assertEqual(b["requests_attempted"], 1)

    def test_incomplete_observation_launch_hint_drift_rejected(self):
        class HintShort(FakeClient):
            def __init__(self, hint):
                super().__init__()
                self.hint = hint

            def get(self, url):
                raw, payload = super().get(url)
                if urlsplit(url).path.endswith("instruments-info"):
                    payload["result"]["list"][0]["launchTime"] = str(self.hint)
                else:
                    payload["result"]["list"] = payload["result"]["list"][:8]
                return raw, payload

        first = self.run_batch(client=HintShort(END - 12*HOUR_MS), size=1)
        self.assertEqual(first["incomplete_24h_contracts"], 1)
        later = self.run_batch(client=HintShort(END - 13*HOUR_MS), size=1)
        self.assertEqual(later["status"], "abstain")
        self.assertEqual(later["failure_stage"], "replay")
        self.assertEqual(later["failure_code"], "short_history_catalog_hint_changed")
        self.assertEqual(later["requests_attempted"], 1)

    def test_zero_candle_observation_is_explicitly_not_zero_turnover(self):
        class EmptyHistory(FakeClient):
            def get(self, url):
                raw, payload = super().get(url)
                if urlsplit(url).path.endswith("/kline"):
                    payload["result"]["list"] = []
                return raw, payload

        a = self.run_batch(client=EmptyHistory(), size=1)
        self.assertEqual(a["completed_contracts"], 0)
        self.assertEqual(a["incomplete_24h_contracts"], 1)
        self.assertEqual(a["incomplete_24h_rows"], 0)
        self.assertEqual(a["top50_basic_count"], 0)
        self.assertFalse(a["marketwide_top50_verified"])
        self.assertEqual(a["requests_attempted"], 2)

    def test_no_gate_no_network_no_files(self):
        denied = self.run_batch(allow_public_network=False)
        self.assertEqual(denied["status"], "owner_gate_required")
        self.assertEqual(denied["requests_attempted"], 0)
        self.assertFalse(self.directory.exists())

    def test_catalog_and_closed_bar_adversarial(self):
        base = catalog()
        bad = json.loads(json.dumps(base))
        bad["result"]["nextPageCursor"] = "next"
        with self.assertRaises(CensusAbstain):
            _catalog(bad, NOW)
        bad = json.loads(json.dumps(base))
        bad["result"]["list"].append(dict(bad["result"]["list"][0]))
        with self.assertRaises(CensusAbstain):
            _catalog(bad, NOW)
        valid = _closed_candles(bars(SYMS[0]), SYMS[0], END)
        self.assertEqual(len(valid), 24)
        for which, replacement in [(2, "50"), (3, "105"), (6, "-1"), (1, "NaN")]:
            with self.subTest(which=which):
                broken = bars(SYMS[0])
                broken["result"]["list"][0][which] = replacement
                with self.assertRaises(CensusAbstain):
                    _closed_candles(broken, SYMS[0], END)
        broken = bars(SYMS[0])
        broken["result"]["list"][0][0] = str(END)
        with self.assertRaises(CensusAbstain):
            _closed_candles(broken, SYMS[0], END)
        for n in ("NaN", "Infinity", "1e9999", "-1", "01", "+1", 1.1):
            with self.subTest(decimal=n), self.assertRaises(CensusAbstain):
                _dec(n)

    def test_expired_window_no_silent_shift(self):
        self.run_batch(size=1)
        out = self.run_batch(now_ms=lambda: NOW+49*HOUR_MS)
        self.assertEqual(out["status"], "abstain")
        self.assertEqual(out["requests_attempted"], 1)

    def test_symlink_path_abstain(self):
        external = Path(self.temp.name) / "another"
        external.mkdir(mode=0o700)
        self.directory.symlink_to(external, target_is_directory=True)
        output = self.run_batch()
        self.assertEqual(output["status"], "abstain")
        self.assertEqual(output["requests_attempted"], 0)


if __name__ == "__main__":
    unittest.main()
