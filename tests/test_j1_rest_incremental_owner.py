"""M1: idempotent closed REST-hour research without live orders or global Top50."""
from __future__ import annotations

from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.bybit_public_j1_transport import (
    BoundedBybitPublicClient,
)
from crypto_intelligence_agent.j1_rest_incremental_owner import (
    HOUR_MS, _DB_NAME, _frontier, run_hourly_once,
)

T = 1794218520000  # 2026-11-09T... after one closed UTC hour, within +15m
BASE = T // HOUR_MS * HOUR_MS
SYMS = tuple(["BTCUSDT","ETHUSDT"] + [f"TST{i}USDT" for i in range(48)])
D = "a"*64


def fake_frontier(*_args, **_kw):
    return {
        "status": "retrospective_negative_overlay_research_only",
        "research_frontier_count": 50,
        "research_frontier_not_eligible_top50": True,
        "marketwide_top50_verified": False,
        "orders_sent": False,
        "network_accessed": False,
        "database_modified": False,
        "current_eligible_contracts_verified": 0,
        "frozen_capture_window_end_ms": 1793970000000,
        "current_metadata_observed_at_ms": 1794103607305,
        "research_frontier_digest_sha256": D,
        "private_snapshot_sha256": D,
        "frozen_raw_top50_digest_sha256": D,
        "private_research_symbols_only": [
            {"position":i+1, "symbol":s,
             "category_unverified":"archived_crypto_reference_only"}
            for i,s in enumerate(SYMS)
        ],
    }


def body(url, _limit):
    from urllib.parse import parse_qs, urlsplit
    q = parse_qs(urlsplit(url).query)
    sym = q["symbol"][0]
    start = int(q["start"][0])
    hours = int(q["limit"][0])
    records = [
        [str(start + i*HOUR_MS), "1", "2", "1", "2", "20", "40"]
        for i in reversed(range(hours))
    ]
    return json.dumps({"retCode":0,"result":{
        "category":"linear","symbol":sym,"list":records
    }}).encode("ascii")


@unittest.skipUnless(os.name == "posix", "owner private journal POSIX only")
class M1OwnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.frozen = base / "frozen"
        self.frozen.mkdir(mode=0o700)
        self.out = base / "fresh"
        self.out.mkdir(mode=0o700)
        self.frozen.chmod(0o700)
        self.out.chmod(0o700)

    def run_once(self, *, delta=0, client=None, count=2, scope=fake_frontier):
        t = BASE+120_000+delta
        fetch = client if client is not None else BoundedBybitPublicClient(transport=body)
        return run_hourly_once(
            frozen_directory=self.frozen, output_directory=self.out,
            max_assets=count, owner_ok=True,
            allow_public_network=True, allow_private_storage=True,
            confirm_region_and_personal_research=True,
            clock_ms=lambda:t, client=fetch, frontier_reader=scope,
        )

    def assert_safe(self, data):
        for key in ("marketwide_top50_verified",
                    "crypto_identity_independently_verified",
                    "source_authenticated", "continuous_collector_verified",
                    "signal_authorized","live_trading_authorized",
                    "orders_sent","frozen_history_modified"):
            self.assertFalse(data[key])
        self.assertNotIn("BTCUSDT", json.dumps(data))
        self.assertNotIn(str(self.out), json.dumps(data))

    def test_first_24h_then_one_hour_then_idempotent(self):
        a = self.run_once()
        self.assertEqual(a["status"], "research_sample_closed_hour_persisted", a)
        self.assertEqual((a["new_closed_candles"],a["requests_attempted"]), (48,2))
        b = self.run_once(delta=HOUR_MS)
        self.assertEqual((b["new_closed_candles"],b["requests_attempted"]), (2,2))
        c = self.run_once(delta=HOUR_MS)
        self.assertEqual((c["new_closed_candles"],c["requests_attempted"]), (0,0))
        with closing(sqlite3.connect(self.out/_DB_NAME)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM candles").fetchone()[0],50)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM published_hour").fetchone()[0],2)
        for out in (a,b,c):
            self.assert_safe(out)

    def test_partial_failure_recovery_without_fake_hour_publication(self):
        hits = []
        def fail_second(url, limit):
            hits.append(url)
            if len(hits) == 2:
                from crypto_intelligence_agent.bybit_public_j1_transport import J1BybitCaptureError
                raise J1BybitCaptureError("network_error_no_retry")
            return body(url,limit)
        first = self.run_once(client=BoundedBybitPublicClient(transport=fail_second))
        self.assertEqual(first["status"], "research_provider_fail_stop")
        self.assertEqual(first["new_closed_candles"],24)
        with closing(sqlite3.connect(self.out/_DB_NAME)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM published_hour").fetchone()[0],0)
        later=self.run_once()
        self.assertEqual(later["new_closed_candles"],24,later)
        self.assertEqual(later["requests_attempted"],1)
        self.assertEqual(later["contracts_at_decision"],2)
        self.assert_safe(later)

    def test_slow_provider_crosses_safe_window_without_candle_commit(self):
        clock = {"ms": BASE + 120_000}
        calls = []

        def slow(url, limit):
            calls.append(url)
            clock["ms"] = BASE + 901_000
            return body(url, limit)

        first = run_hourly_once(
            frozen_directory=self.frozen, output_directory=self.out,
            max_assets=2, owner_ok=True,
            allow_public_network=True, allow_private_storage=True,
            confirm_region_and_personal_research=True,
            clock_ms=lambda: clock["ms"],
            client=BoundedBybitPublicClient(transport=slow),
            frontier_reader=fake_frontier,
        )
        self.assertEqual(first["status"], "research_integrity_or_environment_abstain")
        self.assertEqual(first["failure_category"],
                         "utc_close_window_elapsed_before_commit")
        self.assertEqual(len(calls), 1)
        self.assertEqual(first["new_closed_candles"], 0)
        with closing(sqlite3.connect(self.out/_DB_NAME)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM candles").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM published_hour").fetchone()[0], 0)
        self.assert_safe(first)

    def test_expiry_after_first_member_never_publishes_partial_hour(self):
        clock = {"ms": BASE + 120_000}
        calls = []

        def gradually_slow(url, limit):
            calls.append(url)
            if len(calls) == 2:
                clock["ms"] = BASE + 901_000
            return body(url, limit)

        out = run_hourly_once(
            frozen_directory=self.frozen, output_directory=self.out,
            max_assets=2, owner_ok=True,
            allow_public_network=True, allow_private_storage=True,
            confirm_region_and_personal_research=True,
            clock_ms=lambda: clock["ms"],
            client=BoundedBybitPublicClient(transport=gradually_slow),
            frontier_reader=fake_frontier,
        )
        self.assertEqual(out["status"], "research_integrity_or_environment_abstain")
        self.assertEqual(len(calls), 2)
        self.assertEqual(out["new_closed_candles"], 24)
        with closing(sqlite3.connect(self.out/_DB_NAME)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM candles").fetchone()[0], 24)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM published_hour").fetchone()[0], 0)
        self.assert_safe(out)

    def test_quota_denial_latches_stop_before_next_get(self):
        from crypto_intelligence_agent.bybit_public_j1_transport import J1BybitCaptureError
        def quota(url, limit):
            raise J1BybitCaptureError("provider_rate_limit_no_retry")
        denied=self.run_once(client=BoundedBybitPublicClient(transport=quota))
        self.assertEqual(denied["status"],"research_provider_fail_stop")
        self.assertEqual(denied["requests_attempted"],1)
        blocked=self.run_once()
        self.assertEqual(blocked["status"],"halted_owner_review_required")
        self.assertEqual(blocked["requests_attempted"],0)
        self.assert_safe(blocked)

    def test_corrupted_old_candle_is_not_silently_accepted(self):
        self.run_once()
        with closing(sqlite3.connect(self.out/_DB_NAME)) as db,db:
            db.execute("UPDATE candles SET close='9' WHERE symbol='BTCUSDT'")
        broken = self.run_once(delta=HOUR_MS)
        self.assertEqual(broken["status"], "research_integrity_or_environment_abstain",broken)
        self.assertEqual(broken["requests_attempted"],0)
        self.assert_safe(broken)

    def test_change_scope_cannot_continue_or_backdate(self):
        self.run_once()
        def altered(*args,**kwargs):
            data = fake_frontier()
            data["research_frontier_digest_sha256"] = "b"*64
            return data
        bad=self.run_once(delta=HOUR_MS,scope=altered)
        self.assertEqual(bad["status"],"research_integrity_or_environment_abstain")
        self.assertEqual(bad["requests_attempted"],0)

    def test_missing_middle_hour_abstains_without_retroactive_pit(self):
        self.run_once()
        with closing(sqlite3.connect(self.out/_DB_NAME)) as db,db:
            db.execute("DELETE FROM candles WHERE symbol='BTCUSDT' AND open_ms=?",
                       (BASE-3*HOUR_MS,))
        out=self.run_once(delta=HOUR_MS)
        self.assertEqual(out["status"],"research_integrity_or_environment_abstain")
        self.assertEqual(out["requests_attempted"],0)
        self.assert_safe(out)

    def test_no_optin_does_no_io(self):
        with patch("subprocess.run",side_effect=AssertionError("no process")):
            out=run_hourly_once(frozen_directory=self.frozen,
                output_directory=self.out, frontier_reader=lambda *a,**kw:self.fail("I/O"),
                client=BoundedBybitPublicClient(transport=lambda *a:self.fail("GET")),
                clock_ms=lambda:self.fail("clock"))
        self.assertEqual(out["status"],"owner_optin_required")
        self.assertFalse((self.out/_DB_NAME).exists())


class M1PortableTests(unittest.TestCase):
    def test_d264_frozen_frontier_requires_no_approval(self):
        values = fake_frontier()
        syms,digest = _frontier(values,now=1794218520000,max_assets=2)
        self.assertEqual(syms,("BTCUSDT","ETHUSDT"))
        self.assertEqual(len(digest),64)
        for change in (
            {"research_frontier_not_eligible_top50":False},
            {"marketwide_top50_verified":True},
            {"private_snapshot_sha256":"not-a-hash"},
            {"current_eligible_contracts_verified":1},
        ):
            altered=fake_frontier()
            altered.update(change)
            with self.assertRaises(ValueError):
                _frontier(altered,now=1794218520000,max_assets=2)


if __name__ == "__main__":
    unittest.main()
