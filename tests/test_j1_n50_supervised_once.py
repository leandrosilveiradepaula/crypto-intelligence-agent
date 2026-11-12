"""D291: one-shot supervised N50 uses ONLY D287/M1 with explicit opt-in."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch
import unittest

from crypto_intelligence_agent.j1_auto_research_epoch import (
    _binding, SCHEMA, STATUS, HOUR_MS,
)
from crypto_intelligence_agent.j1_rest_incremental_owner import _DB_NAME
from crypto_intelligence_agent.j1_n50_supervised_once import run_supervised_n50_once

T = 1_800_000_000_000 // HOUR_MS * HOUR_MS
ROOT = Path.cwd().resolve() / "simulated-n50-owner-only"
SCOPE = ROOT / "scope"
OUTPUT = ROOT / "journal"


def manifest():
    d = {
        "schema_version":SCHEMA, "status":STATUS,
        "closed_hour_end_ms":T,
        "catalog_pre_observed_at_ms":T+65_000,
        "catalog_post_observed_at_ms":T+120_000,
        "pool_candidate_count":370,
        "candidate_pool_digest_sha256":"b"*64,
        "closed24h_rank_digest_sha256":"c"*64,
        "ranked_research_symbols_only":[f"TST{i:02d}USDT" for i in range(50)],
        "scope_digest_sha256":"",
        "provisional_research_only":True,
        "marketwide_top50_verified":False,
        "independent_crypto_identity_verified":False,
        "live_trading_authorized":False,
        "orders_sent":False,
    }
    d["scope_digest_sha256"]=_binding(d)
    return d


def readiness():
    return {
        "schema_version":"j1_rest_resume_readiness_v1",
        "status":"no_gap", "journal_integrity_verified":True,
        "activation_authorized":False, "continuous_collector_verified":False,
        "marketwide_top50_verified":False, "source_authenticated":False,
        "signal_authorized":False, "live_trading_authorized":False,
        "orders_sent":False, "network_requests":0,
        "database_mutation_statements":0,
        "reviewed_research_contracts":50,
        "research_closed_24h_ranked_contracts":50,
        "rank_is_sample_only_not_marketwide":True,
        "historical_checkpoint_gaps_present":False,
        "historical_unpublished_hours":0,
        "journal_scope_digest_sha256":manifest()["scope_digest_sha256"],
        "last_published_end_ms":T, "published_hours":1,
        "stored_candles":1200, "catchup_hours":1,
        "catchup_within_worker_limit":True,
        "unobserved_closed_hours":0,
        "next_eligible_end_ms":T+HOUR_MS,
    }


def worker():
    return {
        "status":"research_sample_closed_hour_persisted",
        "selected_research_contracts":50,
        "new_closed_candles":50, "requests_attempted":50,
        "orders_sent":False, "marketwide_top50_verified":False,
        "live_trading_authorized":False, "frozen_history_modified":False,
    }


class SupervisedN50OnceTests(unittest.TestCase):
    def invoke(self, **change):
        args = dict(
            manifest_directory=SCOPE, output_directory=OUTPUT,
            owner_ok=True, clock_ms=lambda:T+HOUR_MS+120_000,
            allow_private_manifest_read=True,
            allow_private_readonly_audit=True,
            allow_public_network=True, allow_private_storage=True,
            confirm_region_and_personal_research=True,
            enable_n50_research_once=True,
        )
        args.update(change)
        return run_supervised_n50_once(**args)

    def test_optins_must_precede_any_private_or_network_calls(self):
        with patch("crypto_intelligence_agent.j1_n50_supervised_once.load_private_ranked_scope",
                   side_effect=AssertionError("read")), \
                patch("crypto_intelligence_agent.j1_n50_supervised_once.run_current_ranked_epoch_once",
                      side_effect=AssertionError("GET")):
            for option in (
                "allow_private_manifest_read", "allow_private_readonly_audit",
                "allow_public_network", "allow_private_storage",
                "confirm_region_and_personal_research", "enable_n50_research_once",
            ):
                with self.subTest(option=option):
                    r=self.invoke(**{option:False})
                    self.assertEqual(r["status"],"optin_required")
                    self.assertEqual(r["requests_attempted"],0)
            self.assertEqual(self.invoke(owner_ok=False)["status"],"blocked")

    def test_one_owner_epoch_persists_incremental_through_existing_writer(self):
        with patch("crypto_intelligence_agent.j1_n50_supervised_once._strict_owner"), \
                patch("crypto_intelligence_agent.j1_n50_supervised_once.load_private_ranked_scope",
                      return_value=manifest()), \
                patch("pathlib.Path.is_file",return_value=True), \
                patch("crypto_intelligence_agent.j1_n50_supervised_once.audit_existing_rest_resume",
                      return_value=readiness()) as aud, \
                patch("crypto_intelligence_agent.j1_n50_supervised_once.run_current_ranked_epoch_once",
                      return_value=worker()) as run:
            r=self.invoke()
        self.assertEqual(r["status"],"research_hour_persisted")
        self.assertEqual(r["decision_action"],"run_existing_epoch_once")
        self.assertEqual((r["selected_research_contracts"],r["new_closed_candles"],r["requests_attempted"]),(50,50,50))
        self.assertEqual(aud.call_args.kwargs["expected_members"],50)
        self.assertTrue(run.call_args.kwargs["allow_public_network"])
        self.assertFalse(r["orders_sent"])
        self.assertFalse(r["continuous_collector_verified"])
        self.assertNotIn("USDT",str(r))

    def test_untrusted_audit_will_not_trigger_get(self):
        bad=readiness()
        bad["journal_scope_digest_sha256"]="f"*64
        with patch("crypto_intelligence_agent.j1_n50_supervised_once._strict_owner"), \
                patch("crypto_intelligence_agent.j1_n50_supervised_once.load_private_ranked_scope",
                      return_value=manifest()), \
                patch("pathlib.Path.is_file",return_value=True), \
                patch("crypto_intelligence_agent.j1_n50_supervised_once.audit_existing_rest_resume",
                      return_value=bad), \
                patch("crypto_intelligence_agent.j1_n50_supervised_once.run_current_ranked_epoch_once",
                      side_effect=AssertionError("GET")):
            r=self.invoke()
        self.assertEqual(r["status"],"blocked")
        self.assertEqual(r["requests_attempted"],0)

    def test_incomplete_empty_epoch_not_mistaken_for_bootstrap(self):
        with patch("crypto_intelligence_agent.j1_n50_supervised_once._strict_owner"), \
                patch("crypto_intelligence_agent.j1_n50_supervised_once.load_private_ranked_scope",
                      return_value=manifest()), \
                patch("pathlib.Path.is_file",return_value=False), \
                patch("pathlib.Path.iterdir",return_value=iter([Path("abandoned-lock")])), \
                patch("crypto_intelligence_agent.j1_n50_supervised_once.run_current_ranked_epoch_once",
                      side_effect=AssertionError("GET")):
            r=self.invoke()
        self.assertEqual(r["status"],"blocked")
        self.assertEqual(r["reason"],"existing_epoch_without_journal")

    def test_bootstrap_requires_verified_empty_directory(self):
        success=worker()
        success["new_closed_candles"]=1200
        with patch("crypto_intelligence_agent.j1_n50_supervised_once._strict_owner"), \
                patch("crypto_intelligence_agent.j1_n50_supervised_once.load_private_ranked_scope",
                      return_value=manifest()), \
                patch("pathlib.Path.is_file",return_value=False), \
                patch("pathlib.Path.iterdir",return_value=iter([])), \
                patch("crypto_intelligence_agent.j1_n50_supervised_once.run_current_ranked_epoch_once",
                      return_value=success):
            r=self.invoke(clock_ms=lambda:T+180_000)
        self.assertEqual(r["status"],"research_hour_persisted")
        self.assertEqual(r["decision_action"],"bootstrap_new_empty_epoch")
        self.assertEqual(r["new_closed_candles"],1200)

    def test_wrong_worker_flags_and_invalid_paths_denied(self):
        altered=worker()
        altered["orders_sent"]=True
        with patch("crypto_intelligence_agent.j1_n50_supervised_once._strict_owner"), \
                patch("crypto_intelligence_agent.j1_n50_supervised_once.load_private_ranked_scope",
                      return_value=manifest()), \
                patch("pathlib.Path.is_file",return_value=True), \
                patch("crypto_intelligence_agent.j1_n50_supervised_once.audit_existing_rest_resume",
                      return_value=readiness()), \
                patch("crypto_intelligence_agent.j1_n50_supervised_once.run_current_ranked_epoch_once",
                      return_value=altered):
            self.assertEqual(self.invoke()["status"],"blocked")
        self.assertEqual(
            self.invoke(output_directory=SCOPE)["status"],"blocked")
        self.assertEqual(
            self.invoke(output_directory=Path("relative"))["status"],"blocked")
        self.assertEqual(
            self.invoke(clock_ms=lambda:True)["status"],"blocked")


if __name__=="__main__":
    unittest.main()
