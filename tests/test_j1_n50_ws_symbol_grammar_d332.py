"""J1/D332 owner-only scope-format preflight: no private IDs or side effects."""
from __future__ import annotations

from dataclasses import replace
from io import StringIO
from contextlib import redirect_stdout
import json
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from crypto_intelligence_agent.j1_n50_ws_symbol_grammar_d332 import (
    evaluate_n50_ws_symbol_grammar, observe_n50_ws_symbol_grammar_owner,
    _report,
)
from scripts.audit_j1_n50_ws_symbol_grammar_d332_once import main as cli_main
from test_j1_n50_ws_single_letter_usdt_d332 import short_base_scope
from test_j1_n50_ws_hourly_attestation_d313 import reviewed_scope


OPTINS = [
    "--allow-private-pointer-read",
    "--allow-private-manifest-read",
    "--allow-private-ws-scope-read",
    "--allow-owner-symbol-grammar-audit",
]


class D332OwnerSymbolGrammarTests(unittest.TestCase):
    def test_one_single_base_rejection_is_proven_by_50_member_scope(self):
        out = evaluate_n50_ws_symbol_grammar(short_base_scope())
        self.assertEqual(out["status"], "single_letter_legacy_mismatch_in_scope")
        self.assertEqual(out["reviewed_contracts"], 50)
        self.assertEqual(out["legacy_candle_parser_rejections"], 1)
        self.assertEqual(out["one_character_usdt_bases"], 1)
        self.assertEqual(out["new_candle_parser_rejections"], 0)
        self.assertFalse(out["orders_sent"])
        self.assertFalse(out["marketwide_top50_verified"])
        self.assertFalse(out["live_trading_authorized"])
        serialized = json.dumps(out)
        for private in ("AUSDT", "TST42USDT", "payload", "price", "OHLC"):
            self.assertNotIn(private, serialized)

    def test_no_one_letter_member_abstains_and_wont_restart_ws(self):
        out = evaluate_n50_ws_symbol_grammar(reviewed_scope())
        self.assertEqual(out["status"], "legacy_mismatch_not_established_abstain")
        self.assertEqual(out["reviewed_contracts"], 50)
        self.assertEqual(out["legacy_candle_parser_rejections"], 0)
        self.assertEqual(out["new_candle_parser_rejections"], 0)

    def test_wrong_membership_structure_or_quote_denied_not_counted(self):
        s = short_base_scope()
        rows = list(s.contracts)
        for changed in (
            rows[:49],
            rows + [rows[0]],
            [rows[0]] * 50,
            [replace(rows[0], symbol="A-USDT")] + rows[1:],
            [replace(rows[0], quote_coin="USDC")] + rows[1:],
            [replace(rows[0], symbol="aUSDT", base_coin="a")] + rows[1:],
        ):
            with self.subTest(size=len(changed)):
                out = evaluate_n50_ws_symbol_grammar(
                    replace(s, contracts=tuple(changed)))
                self.assertEqual(out["status"], "scope_symbol_contract_abstain")
                self.assertEqual(out["reviewed_contracts"], 0)
        self.assertEqual(evaluate_n50_ws_symbol_grammar(None)["status"],
                         "scope_symbol_contract_abstain")

    def test_optin_rejects_before_any_private_read(self):
        with patch(
            "crypto_intelligence_agent.j1_n50_ws_symbol_grammar_d332.load_active_n50_ws_epoch",
            side_effect=AssertionError("no owner read without four optins")
        ):
            self.assertEqual(
                observe_n50_ws_symbol_grammar_owner()["status"], "owner_optin_required")
            self.assertEqual(
                observe_n50_ws_symbol_grammar_owner(
                    allow_private_pointer_read=True,
                    allow_private_manifest_read=True,
                    allow_private_ws_scope_read=True)["status"], "owner_optin_required")

    @unittest.skipUnless(os.name == "posix", "owner DAC scope only on POSIX")
    def test_owner_read_mocked_scope_passes_only_after_full_revalidation(self):
        import crypto_intelligence_agent.j1_n50_ws_symbol_grammar_d332 as mod
        ranked = {"test": "fixture_only"}
        digest = "a" * 64
        metadata = "b" * 64
        active = SimpleNamespace(
            status="active_n50_ws_epoch_revalidated",
            manifest_directory=object(),
            ws_directory=object(),
            ranked_scope_sha256=digest,
            ws_metadata_sha256=metadata,
        )
        admitted = SimpleNamespace(
            status="private_n50_ws_admission_loaded_revalidated",
            admission=SimpleNamespace(
                selected_contracts=50, metadata_sha256=metadata,
                ws_scope=short_base_scope(),
            ),
            ranked_scope=ranked,
        )
        scope = tuple(range(50))
        with patch.object(mod.os, "getuid", return_value=1234), patch.object(
            mod.os, "geteuid", return_value=1234
        ), patch.object(mod, "load_active_n50_ws_epoch", return_value=active), patch.object(
            mod, "load_private_ranked_scope", return_value=ranked
        ), patch.object(mod, "validate_ranked_research_scope",
                        return_value=(scope, digest)), patch.object(
            mod, "load_n50_ws_dynamic_admission", return_value=admitted
        ):
            flags = dict(
                allow_private_pointer_read=True,
                allow_private_manifest_read=True,
                allow_private_ws_scope_read=True,
                allow_owner_symbol_grammar_audit=True,
                now_ms=1_800_000_000_000,
            )
            ok = observe_n50_ws_symbol_grammar_owner(**flags)
            self.assertEqual(ok["status"], "single_letter_legacy_mismatch_in_scope")
            self.assertEqual(ok["network_requests"], 0)
            wrong = SimpleNamespace(**vars(admitted))
            wrong.admission = SimpleNamespace(
                selected_contracts=49, metadata_sha256=metadata,
                ws_scope=short_base_scope(),
            )
            with patch.object(mod, "load_n50_ws_dynamic_admission",
                              return_value=wrong):
                no = observe_n50_ws_symbol_grammar_owner(**flags)
                self.assertEqual(no["status"], "owner_ws_scope_integrity_abstain")

    @unittest.skipUnless(os.name == "posix", "owner DAC scope only on POSIX")
    def test_root_owner_rejection_and_default_cli_are_safe(self):
        with patch(
            "crypto_intelligence_agent.j1_n50_ws_symbol_grammar_d332.os.getuid",
            return_value=0
        ), patch(
            "crypto_intelligence_agent.j1_n50_ws_symbol_grammar_d332.os.geteuid",
            return_value=0
        ):
            out = observe_n50_ws_symbol_grammar_owner(
                allow_private_pointer_read=True,
                allow_private_manifest_read=True,
                allow_private_ws_scope_read=True,
                allow_owner_symbol_grammar_audit=True)
        self.assertEqual(out["status"], "owner_environment_abstain")
        with patch(
            "scripts.audit_j1_n50_ws_symbol_grammar_d332_once.observe_n50_ws_symbol_grammar_owner",
            return_value=_report("owner_optin_required"),
        ):
            with redirect_stdout(StringIO()) as s:
                self.assertEqual(cli_main([]), 65)
            doc = json.loads(s.getvalue())
            self.assertEqual(doc["network_requests"], 0)
            self.assertFalse(doc["orders_sent"])

    def test_cli_only_accepts_matching_candidate_counts(self):
        success = evaluate_n50_ws_symbol_grammar(short_base_scope())
        with patch(
            "scripts.audit_j1_n50_ws_symbol_grammar_d332_once.observe_n50_ws_symbol_grammar_owner",
            return_value=success,
        ) as call:
            with redirect_stdout(StringIO()) as s:
                self.assertEqual(cli_main(OPTINS), 0)
            self.assertTrue(call.call_args.kwargs["allow_owner_symbol_grammar_audit"])
            self.assertEqual(json.loads(s.getvalue())["reviewed_contracts"], 50)
        with patch(
            "scripts.audit_j1_n50_ws_symbol_grammar_d332_once.observe_n50_ws_symbol_grammar_owner",
            return_value=evaluate_n50_ws_symbol_grammar(reviewed_scope()),
        ):
            with redirect_stdout(StringIO()):
                self.assertEqual(cli_main(OPTINS), 65)


if __name__ == "__main__":
    unittest.main()
