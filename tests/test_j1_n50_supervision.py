"""No-network adversarial tests for D290 current-N50 supervision policy."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from unittest.mock import patch
import unittest

from crypto_intelligence_agent.j1_auto_research_epoch import (
    _binding, SCHEMA, STATUS, HOUR_MS,
)
from crypto_intelligence_agent.j1_n50_supervision import plan_n50_supervision

T = 1_800_000_000_000 // HOUR_MS * HOUR_MS
SYMS = [f"TST{i:02d}USDT" for i in range(50)]
DIGEST = "a" * 64


def scope():
    data = {
        "schema_version": SCHEMA,
        "status": STATUS,
        "closed_hour_end_ms": T,
        "catalog_pre_observed_at_ms": T + 65_000,
        "catalog_post_observed_at_ms": T + 120_000,
        "pool_candidate_count": 370,
        "candidate_pool_digest_sha256": "b" * 64,
        "closed24h_rank_digest_sha256": "c" * 64,
        "ranked_research_symbols_only": SYMS[:],
        "scope_digest_sha256": "",
        "provisional_research_only": True,
        "marketwide_top50_verified": False,
        "independent_crypto_identity_verified": False,
        "live_trading_authorized": False,
        "orders_sent": False,
    }
    data["scope_digest_sha256"] = _binding(data)
    return data


def audit(*, last=T, published=1, now=T+HOUR_MS+120_000):
    # One 24h bootstrap checkpoint then one new bar per published hour.
    target = now // HOUR_MS * HOUR_MS
    remaining = (target-last)//HOUR_MS
    return {
        "schema_version": "j1_rest_resume_readiness_v1",
        "status": "no_gap",
        "journal_integrity_verified": True,
        "activation_authorized": False,
        "continuous_collector_verified": False,
        "marketwide_top50_verified": False,
        "source_authenticated": False,
        "signal_authorized": False,
        "live_trading_authorized": False,
        "orders_sent": False,
        "network_requests": 0,
        "database_mutation_statements": 0,
        "reviewed_research_contracts": 50,
        "research_closed_24h_ranked_contracts": 50,
        "rank_is_sample_only_not_marketwide": True,
        "historical_checkpoint_gaps_present": False,
        "historical_unpublished_hours": 0,
        "journal_scope_digest_sha256": scope()["scope_digest_sha256"],
        "last_published_end_ms": last,
        "published_hours": published,
        "stored_candles": 50 * (24 + published-1),
        "catchup_hours": remaining,
        "catchup_within_worker_limit": True,
        "unobserved_closed_hours": max(0, remaining-1),
        "next_eligible_end_ms": target,
    }


class N50SupervisionPolicyTests(unittest.TestCase):
    def test_current_hour_requests_gate_only_and_no_ops(self):
        now = T + HOUR_MS + 120_000
        d = plan_n50_supervision(now_ms=now,sealed_scope=scope(),audit=audit(now=now))
        self.assertEqual(d.action, "run_existing_epoch_once")
        self.assertEqual(d.status, "needs_external_gate")
        report=d.sanitized_report()
        self.assertEqual(report["stored_candles"],1200)
        self.assertFalse(report["operational_activation_authorized"])
        self.assertFalse(report["continuous_collector_verified"])
        self.assertFalse(report["orders_sent"])
        self.assertEqual(report["network_requests"],0)
        self.assertNotIn("USDT",str(report))
        self.assertEqual(report["scope_digest_sha256"],scope()["scope_digest_sha256"])

    def test_same_hour_idempotent_and_outside_window_deferred(self):
        now = T + HOUR_MS + 120_000
        same = audit(last=T+HOUR_MS,published=2,now=now)
        self.assertEqual(plan_n50_supervision(
            now_ms=now,sealed_scope=scope(),audit=same).status,"no_op")
        later = T + HOUR_MS + 20*60_000
        self.assertEqual(plan_n50_supervision(
            now_ms=later,sealed_scope=scope(),audit=audit(now=later)).status,
            "deferred")

    def test_bootstrap_requires_separate_empty_owner_journal(self):
        now=T+120_000
        d=plan_n50_supervision(now_ms=now,sealed_scope=scope(),audit=None)
        self.assertEqual(d.action,"bootstrap_new_empty_epoch")
        self.assertEqual(d.status,"needs_external_gate")

    def test_rotation_requires_serialized_refresh_and_new_journal(self):
        now=T+37*HOUR_MS+120_000
        last=T+36*HOUR_MS
        d=plan_n50_supervision(
            now_ms=now,sealed_scope=scope(),
            audit=audit(last=last,published=37,now=now))
        self.assertEqual(d.action,"serialize_rotation_to_new_epoch")
        self.assertEqual(d.status,"needs_external_gate")
        self.assertFalse(d.sanitized_report()["new_manifest_written"])
        self.assertFalse(d.sanitized_report()["new_journal_written"])

    def test_scope_expires_and_cannot_bootstrap_stale_epoch(self):
        self.assertEqual(plan_n50_supervision(
            now_ms=T+49*HOUR_MS+120_000,sealed_scope=scope(),audit=None
        ).status,"blocked")

    def test_catchup_gap_and_prior_pit_gap_fail_closed(self):
        now=T+4*HOUR_MS+120_000
        old=audit(now=now)
        d=plan_n50_supervision(now_ms=now,sealed_scope=scope(),audit=old)
        self.assertEqual(d.status,"blocked")
        last=T+HOUR_MS
        bad=audit(last=last,published=2,now=now)
        self.assertEqual(plan_n50_supervision(
            now_ms=now,sealed_scope=scope(),audit=bad).status,"blocked")
        good=audit(now=T+HOUR_MS+120_000)
        good["historical_checkpoint_gaps_present"]=True
        self.assertEqual(plan_n50_supervision(
            now_ms=T+HOUR_MS+120_000,sealed_scope=scope(),audit=good).status,
            "blocked")

    def test_tampering_and_untrusted_readiness_denied(self):
        now=T+HOUR_MS+120_000
        for key,value in [
            ("journal_scope_digest_sha256","f"*64),
            ("journal_integrity_verified",False),
            ("source_authenticated",True),
            ("activation_authorized",True),
            ("research_closed_24h_ranked_contracts",49),
            ("stored_candles",1201),
            ("published_hours",True),
            ("historical_unpublished_hours",21),
            ("catchup_hours",2),
            ("next_eligible_end_ms",T),
            ("network_requests",1),
        ]:
            with self.subTest(key=key):
                a=audit(now=now)
                a[key]=value
                self.assertEqual(plan_n50_supervision(
                    now_ms=now,sealed_scope=scope(),audit=a).status,"blocked")
        tampered=scope()
        tampered["ranked_research_symbols_only"][0]="FAKEUSDT"
        self.assertEqual(plan_n50_supervision(
            now_ms=now,sealed_scope=tampered,audit=audit(now=now)).status,
            "blocked")

    def test_no_network_or_db_or_systemd_and_portable(self):
        now=T+HOUR_MS+120_000
        with patch("urllib.request.urlopen",side_effect=AssertionError("net")), \
                patch("sqlite3.connect",side_effect=AssertionError("sqlite")), \
                patch("subprocess.run",side_effect=AssertionError("systemd")):
            first=plan_n50_supervision(
                now_ms=now,sealed_scope=scope(),audit=audit(now=now))
            again=plan_n50_supervision(
                now_ms=now,sealed_scope=scope(),audit=audit(now=now))
        self.assertEqual(first,again)
        self.assertEqual(plan_n50_supervision(
            now_ms=True,sealed_scope=scope(),audit=None).status,"blocked")
        self.assertEqual(plan_n50_supervision(
            now_ms=now,sealed_scope=scope(),audit="missing").status,"blocked")


if __name__=="__main__":
    unittest.main()
