"""Read-only CLI preflight: denies opt-in, path errors, corrupted audit and leaks."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch
import unittest

from scripts.plan_j1_n50_supervision_once import inspect_n50_epoch_once
from crypto_intelligence_agent.j1_auto_research_epoch import (
    _binding, SCHEMA, STATUS, HOUR_MS,
)

T = 1_800_000_000_000 // HOUR_MS * HOUR_MS


def scope():
    out = {
        "schema_version": SCHEMA, "status": STATUS,
        "closed_hour_end_ms": T,
        "catalog_pre_observed_at_ms": T+65_000,
        "catalog_post_observed_at_ms": T+120_000,
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
    out["scope_digest_sha256"]=_binding(out)
    return out


def audit():
    return {
        "schema_version":"j1_rest_resume_readiness_v1",
        "status":"no_gap",
        "journal_integrity_verified":True,
        "activation_authorized":False,
        "continuous_collector_verified":False,
        "marketwide_top50_verified":False,
        "source_authenticated":False,
        "signal_authorized":False,
        "live_trading_authorized":False,
        "orders_sent":False,
        "network_requests":0,
        "database_mutation_statements":0,
        "reviewed_research_contracts":50,
        "research_closed_24h_ranked_contracts":50,
        "rank_is_sample_only_not_marketwide":True,
        "historical_checkpoint_gaps_present":False,
        "historical_unpublished_hours":0,
        "journal_scope_digest_sha256":scope()["scope_digest_sha256"],
        "last_published_end_ms":T,
        "published_hours":1,
        "stored_candles":1200,
        "catchup_hours":1,
        "catchup_within_worker_limit":True,
        "unobserved_closed_hours":0,
        "next_eligible_end_ms":T+HOUR_MS,
    }


MANIFEST = Path("/private/n50/scope")
JOURNAL = Path("/private/n50/output")


class N50SupervisionCliTests(unittest.TestCase):
    def run_once(self, **override):
        opts=dict(
            manifest_directory=MANIFEST, output_directory=JOURNAL,
            now_ms=T+HOUR_MS+120_000,owner_ok=True,
            allow_private_manifest_read=True,
            allow_private_readonly_audit=True,
        )
        opts.update(override)
        return inspect_n50_epoch_once(**opts)

    def test_full_readonly_path_validates_and_never_issues_network(self):
        with patch("scripts.plan_j1_n50_supervision_once.load_private_ranked_scope",
                   return_value=scope()) as load, \
                patch("scripts.plan_j1_n50_supervision_once.audit_existing_rest_resume",
                      return_value=audit()) as owner_audit, \
                patch("urllib.request.urlopen", side_effect=AssertionError("GET")), \
                patch("sqlite3.connect", side_effect=AssertionError("direct DB")), \
                patch("subprocess.run",side_effect=AssertionError("systemd")):
            out=self.run_once()
        self.assertEqual(out["action"],"run_existing_epoch_once")
        self.assertEqual(out["status"],"needs_external_gate")
        self.assertEqual(load.call_count,1)
        self.assertEqual(owner_audit.call_args.kwargs["expected_members"],50)
        self.assertFalse(out["orders_sent"])
        self.assertEqual(out["network_requests"],0)
        self.assertNotIn("USDT",str(out))

    def test_no_optin_owner_or_malicious_paths_does_not_read(self):
        with patch("scripts.plan_j1_n50_supervision_once.load_private_ranked_scope",
                   side_effect=AssertionError("private read")), \
                patch("scripts.plan_j1_n50_supervision_once.audit_existing_rest_resume",
                      side_effect=AssertionError("sqlite read")):
            for opts in (
                {"allow_private_manifest_read":False},
                {"allow_private_readonly_audit":False},
                {"owner_ok":False},
                {"manifest_directory":JOURNAL},
                {"output_directory":Path("relative/path")},
                {"manifest_directory":Path("/private")},
            ):
                with self.subTest(opts=opts):
                    out=self.run_once(**opts)
                    self.assertEqual(out["status"],"blocked")
                    self.assertEqual(out["network_requests"],0)

    def test_bad_readiness_never_relabels_bootstrap(self):
        with patch("scripts.plan_j1_n50_supervision_once.load_private_ranked_scope",
                   return_value=scope()), \
                patch("scripts.plan_j1_n50_supervision_once.audit_existing_rest_resume",
                      return_value={"status":"journal_unavailable_or_integrity_blocked"}):
            out=self.run_once()
        self.assertEqual(out["status"],"blocked")
        self.assertNotEqual(out["action"],"bootstrap_new_empty_epoch")


if __name__=="__main__":
    unittest.main()
