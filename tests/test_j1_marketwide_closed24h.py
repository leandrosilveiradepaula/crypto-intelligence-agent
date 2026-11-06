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
