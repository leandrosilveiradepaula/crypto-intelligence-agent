"""Private Vision CLI exercises existing ZIP/sidecar audit and no network."""
from contextlib import redirect_stdout
from io import StringIO
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
from decimal import Decimal
import os
import unittest

from scripts.replay_private_vision_dynamic import (
    private_vision_dynamic_replay,VisionReplayPrivateError,main,
)
from test_offline_vision_month import synthetic_zip
from crypto_intelligence_agent.vision_dynamic_replay import HOUR_MS


@unittest.skipUnless(os.name=="posix","owner-only POSIX private files required")
class VisionReplayCLI(unittest.TestCase):
    def test_two_private_assets_readonly_and_sanitized(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);root.chmod(0o700)
            manifests=[]
            first=None
            for sym in ("BTCUSDT","ETHUSDT"):
                folder=root/sym;folder.mkdir(mode=0o700)
                archives=[]
                for y,m in ((2026,8),(2026,9)):
                    blob,name,digest,cutoff=synthetic_zip(year=y,month=m,symbol=sym)
                    raw=folder/name;raw.write_bytes(blob);raw.chmod(0o600)
                    check=folder/(name+".CHECKSUM")
                    check.write_text(digest+"  "+name+"\n",encoding="ascii");check.chmod(0o600)
                    archives.append({"name":name,"sha256":digest})
                manifest=folder/"manifest.json"
                manifest.write_text(json.dumps({"schema_version":"vision-local-series-v1",
                    "as_of_ms":cutoff,"archives":archives}),encoding="ascii")
                manifest.chmod(0o600)
                manifests.append(str(manifest))
                if first is None:
                    from datetime import datetime,timezone
                    first=int(datetime(2026,8,2,tzinfo=timezone.utc).timestamp()*1000)
            # Isolate independently audited manifest failures from replay logic.
            from scripts.audit_private_vision_multiasset import audit_private_vision_multiasset_coverage
            audit_private_vision_multiasset_coverage(
                manifest_paths=tuple(manifests),
                allow_personal_nonproduction_research=True)
            with patch("socket.create_connection",side_effect=AssertionError("network")):
                result=private_vision_dynamic_replay(
                    manifest_paths=tuple(manifests),
                    allow_personal_nonproduction_research=True,
                    first_decision_ms=first,
                    last_decision_ms=first+24*HOUR_MS)
            self.assertEqual((result["asset_count"],result["decisions_count"]),(2,2))
            self.assertEqual(result["local_archives_audited"],4)
            self.assertFalse(result["marketwide_top50_verified"])
            self.assertFalse(result["orders_sent"])
            self.assertEqual(result["network_requests"],0)
            from test_vision_intrabar_stress import terms
            stressed=private_vision_dynamic_replay(
                manifest_paths=tuple(manifests),
                allow_personal_nonproduction_research=True,
                first_decision_ms=first,last_decision_ms=first+24*HOUR_MS,
                stress_assumptions=terms(),
                stress_selection_cost_bps=Decimal("0"))
            self.assertIn("hypothetical_intrabar_oos",stressed)
            extra=stressed["hypothetical_intrabar_oos"]
            self.assertFalse(extra["financial_backtest_approved"])
            self.assertFalse(extra["orders_sent"])
            self.assertNotIn("BTCUSDT",str(stressed))

            from crypto_intelligence_agent.vision_stress_sensitivity import (
                compare_costed_vision_oos_stress_scenarios,
            )
            from crypto_intelligence_agent.offline_vision_month import inspect_offline_vision_month
            from crypto_intelligence_agent.synthetic_margin_envelope import SyntheticMarginBasis
            from dataclasses import replace
            from scripts.audit_private_bybit_json import _read_private_file
            # Re-read only the already verified temporary fixture archives for
            # an independent comparison against the underlying PRE22 auditor.
            checked_groups=[]
            for manifest_path in manifests:
                manifest=json.loads(Path(manifest_path).read_text(encoding="ascii"))
                months=[]
                for entry in manifest["archives"]:
                    raw=Path(manifest_path).parent/entry["name"]
                    months.append(inspect_offline_vision_month(
                        raw.read_bytes(),archive_name=entry["name"],
                        expected_sha256=entry["sha256"],as_of_ms=manifest["as_of_ms"]))
                checked_groups.append(tuple(months))
            high=terms(50)
            low=replace(high,margin=SyntheticMarginBasis(
                high.margin.requested_margin_quote,1,
                high.margin.requested_margin_quote,high.margin.quote_currency))
            with patch("socket.create_connection",side_effect=AssertionError("network")):
                pair=private_vision_dynamic_replay(
                    manifest_paths=tuple(manifests),
                    allow_personal_nonproduction_research=True,
                    first_decision_ms=first,last_decision_ms=first+24*HOUR_MS,
                    stress_assumptions=high,stress_selection_cost_bps=Decimal("0"),
                    audit_oos_leverage_pair=True)
            expected=compare_costed_vision_oos_stress_scenarios(
                tuple(checked_groups),
                as_of_ms=checked_groups[0][-1].end_open_exclusive_ms+HOUR_MS,
                cost_bps_per_side=Decimal("0"),assumptions_grid=(low,high))
            self.assertEqual(pair["hypothetical_oos_leverage_pair"],
                             expected.sanitized_report())
            self.assertEqual(
                [case["leverage_at_intent"] for case in
                 pair["hypothetical_oos_leverage_pair"]["scenarios"]],[1,50])
            self.assertEqual(
                pair["hypothetical_oos_leverage_pair"]["scenarios"][0]["hypothetical_margin_quote"],
                pair["hypothetical_oos_leverage_pair"]["scenarios"][1]["hypothetical_margin_quote"])
            self.assertFalse(pair["hypothetical_oos_leverage_pair"]["live_trading_authorized"])
            from crypto_intelligence_agent.vision_oos_robustness import (
                OOSRobustnessPolicy, audit_oos_robustness,
            )
            review_policy = OOSRobustnessPolicy(
                1, 1, Decimal("0"), Decimal("0"), Decimal("0.2"),
                Decimal("1"), True)
            with patch("socket.create_connection",side_effect=AssertionError("network")):
                screened = private_vision_dynamic_replay(
                    manifest_paths=tuple(manifests),
                    allow_personal_nonproduction_research=True,
                    first_decision_ms=first,last_decision_ms=first+24*HOUR_MS,
                    stress_assumptions=high,stress_selection_cost_bps=Decimal("0"),
                    audit_oos_leverage_pair=True,
                    oos_robustness_policy=review_policy)
            self.assertEqual(
                screened["hypothetical_oos_robustness"],
                audit_oos_robustness(expected,policy=review_policy).sanitized_report())
            self.assertFalse(screened["hypothetical_oos_robustness"]["financial_backtest_approved"])
            self.assertFalse(screened["hypothetical_oos_robustness"]["all_synthetic_conditions_met"])
            self.assertNotIn("BTCUSDT",json.dumps(screened))
            self.assertNotIn(str(root),json.dumps(screened))
            with self.assertRaises(VisionReplayPrivateError):
                private_vision_dynamic_replay(
                    manifest_paths=tuple(manifests),
                    allow_personal_nonproduction_research=True,
                    first_decision_ms=first,last_decision_ms=first+24*HOUR_MS,
                    oos_robustness_policy=review_policy)
            self.assertNotIn("hypothetical_oos_leverage_pair",stressed)
            self.assertNotIn("BTCUSDT",json.dumps(pair))
            self.assertNotIn(str(root),json.dumps(pair))
            with redirect_stdout(StringIO()) as leverage_output:
                rc_pair=main([
                    "--manifest",manifests[0],"--manifest",manifests[1],
                    "--first-decision-ms",str(first),
                    "--last-decision-ms",str(first+24*HOUR_MS),
                    "--allow-personal-nonproduction-research",
                    "--audit-intrabar-stress",
                    "--stress-margin-quote","2","--stress-leverage","50",
                    "--stress-stop-fraction","0.01",
                    "--stress-target-fraction","0.03",
                    "--stress-maintenance-bps","0",
                    "--stress-fee-bps","0",
                    "--stress-slippage-bps","0",
                    "--stress-funding-bps","0",
                    "--stress-selection-cost-bps","0",
                    "--audit-oos-leverage-pair"])
            self.assertEqual(rc_pair,0)
            cli_pair=json.loads(leverage_output.getvalue())
            self.assertEqual(cli_pair["hypothetical_oos_leverage_pair"]["scenario_count"],2)
            with redirect_stdout(StringIO()) as robust_output:
                rc_robust=main([
                    "--manifest",manifests[0],"--manifest",manifests[1],
                    "--first-decision-ms",str(first),
                    "--last-decision-ms",str(first+24*HOUR_MS),
                    "--allow-personal-nonproduction-research",
                    "--audit-intrabar-stress",
                    "--stress-margin-quote","2","--stress-leverage","50",
                    "--stress-stop-fraction","0.01",
                    "--stress-target-fraction","0.03",
                    "--stress-maintenance-bps","0",
                    "--stress-fee-bps","0",
                    "--stress-slippage-bps","0",
                    "--stress-funding-bps","0",
                    "--stress-selection-cost-bps","0",
                    "--audit-oos-leverage-pair",
                    "--audit-oos-robustness",
                    "--robust-min-folds","1",
                    "--robust-min-exposures-per-fold","1",
                    "--robust-max-liquidation-fraction","0",
                    "--robust-max-ambiguity-fraction","0",
                    "--robust-max-single-loss-over-margin","0.2",
                    "--robust-max-drawdown-quote","1",
                    "--robust-require-nonnegative-adverse"])
            self.assertEqual(rc_robust,0)
            self.assertIn("hypothetical_oos_robustness",robust_output.getvalue())
            self.assertNotIn("BTCUSDT",robust_output.getvalue())
            self.assertNotIn(str(root),robust_output.getvalue())
            with redirect_stdout(StringIO()) as invalid_robust:
                bad_robust=main([
                    "--manifest",manifests[0],"--manifest",manifests[1],
                    "--first-decision-ms",str(first),
                    "--last-decision-ms",str(first+24*HOUR_MS),
                    "--allow-personal-nonproduction-research",
                    "--audit-oos-robustness", "--robust-min-folds","1"])
            self.assertEqual(bad_robust,1)
            self.assertEqual(json.loads(invalid_robust.getvalue())["status"],
                             "private_vision_dynamic_replay_rejected")
            self.assertNotIn("BTCUSDT",leverage_output.getvalue())
            self.assertNotIn(str(root),leverage_output.getvalue())
            with redirect_stdout(StringIO()) as rejected_pair:
                bad=main([
                    "--manifest",manifests[0],"--manifest",manifests[1],
                    "--first-decision-ms",str(first),
                    "--last-decision-ms",str(first+24*HOUR_MS),
                    "--allow-personal-nonproduction-research",
                    "--audit-oos-leverage-pair"])
            self.assertEqual(bad,1)
            self.assertEqual(json.loads(rejected_pair.getvalue())["status"],
                             "private_vision_dynamic_replay_rejected")
            with self.assertRaises(VisionReplayPrivateError):
                private_vision_dynamic_replay(
                    manifest_paths=tuple(manifests),
                    allow_personal_nonproduction_research=True,
                    first_decision_ms=first,last_decision_ms=first+24*HOUR_MS,
                    stress_assumptions=low,audit_oos_leverage_pair=True)

            from crypto_intelligence_agent.vision_risk_sensitivity import VisionRiskShocks
            with patch("socket.create_connection",side_effect=AssertionError("network")):
                sensitivity=private_vision_dynamic_replay(
                    manifest_paths=tuple(manifests),
                    allow_personal_nonproduction_research=True,
                    first_decision_ms=first,last_decision_ms=first+24*HOUR_MS,
                    stress_assumptions=terms(),
                    stress_selection_cost_bps=Decimal("0"),
                    risk_shocks=VisionRiskShocks(*[Decimal("5") for _ in range(6)]))
            self.assertIn("hypothetical_risk_sensitivity",sensitivity)
            self.assertEqual(len(sensitivity["hypothetical_risk_sensitivity"]["scenarios"]),4)
            self.assertNotIn("BTCUSDT",json.dumps(sensitivity))
            self.assertNotIn(str(root),json.dumps(sensitivity))
            with redirect_stdout(StringIO()) as sensitivity_output:
                rc_sensitivity=main([
                    "--manifest",manifests[0],"--manifest",manifests[1],
                    "--first-decision-ms",str(first),
                    "--last-decision-ms",str(first+24*HOUR_MS),
                    "--allow-personal-nonproduction-research",
                    "--audit-intrabar-stress",
                    "--stress-margin-quote","2","--stress-leverage","50",
                    "--stress-stop-fraction","0.01",
                    "--stress-target-fraction","0.03",
                    "--stress-maintenance-bps","0",
                    "--stress-fee-bps","0",
                    "--stress-slippage-bps","0",
                    "--stress-funding-bps","0",
                    "--stress-selection-cost-bps","0",
                    "--audit-stress-sensitivity",
                    "--risk-extra-entry-fee-bps","5",
                    "--risk-extra-exit-fee-bps","5",
                    "--risk-extra-entry-slippage-bps","5",
                    "--risk-extra-exit-slippage-bps","5",
                    "--risk-extra-maintenance-bps","5",
                    "--risk-funding-shock-bps","20"])
            self.assertEqual(rc_sensitivity,0)
            self.assertIn("hypothetical_risk_sensitivity",sensitivity_output.getvalue())
            self.assertNotIn("BTCUSDT",sensitivity_output.getvalue())
            self.assertNotIn(str(root),sensitivity_output.getvalue())
            with redirect_stdout(StringIO()) as forbidden_output:
                forbidden=main([
                    "--manifest",manifests[0],"--manifest",manifests[1],
                    "--first-decision-ms",str(first),
                    "--last-decision-ms",str(first+24*HOUR_MS),
                    "--allow-personal-nonproduction-research",
                    "--audit-stress-sensitivity",
                    "--risk-extra-entry-fee-bps","5"])
            self.assertEqual(forbidden,1)
            self.assertEqual(json.loads(forbidden_output.getvalue())["status"],
                             "private_vision_dynamic_replay_rejected")

            with patch("socket.create_connection",side_effect=AssertionError("network")):
                baseline=private_vision_dynamic_replay(
                    manifest_paths=tuple(manifests),
                    allow_personal_nonproduction_research=True,
                    first_decision_ms=first,last_decision_ms=first+24*HOUR_MS,
                    costed_oos_bps=Decimal("5"))
            self.assertEqual(baseline["hypothetical_costed_oos"]["fold_count"],1)
            self.assertFalse(baseline["hypothetical_costed_oos"]["financial_backtest_approved"])
            self.assertNotIn("BTCUSDT",json.dumps(baseline))
            with redirect_stdout(StringIO()) as out:
                rc=main(["--manifest",manifests[0],"--manifest",manifests[1],
                    "--first-decision-ms",str(first),
                    "--last-decision-ms",str(first+24*HOUR_MS),
                    "--allow-personal-nonproduction-research",
                    "--costed-oos","--oos-cost-bps","5"])
            self.assertEqual(rc,0)
            self.assertIn("hypothetical_costed_oos",out.getvalue())
            self.assertEqual(result["data_stored"],False)
            self.assertNotIn("BTCUSDT",json.dumps(result))
            with redirect_stdout(StringIO()) as output:
                rc=main(["--manifest",manifests[0],"--manifest",manifests[1],
                    "--first-decision-ms",str(first),
                    "--last-decision-ms",str(first+24*HOUR_MS)])
            self.assertEqual(rc,1)
            with redirect_stdout(StringIO()) as stress_output:
                rc_stress=main([
                    "--manifest",manifests[0],"--manifest",manifests[1],
                    "--first-decision-ms",str(first),
                    "--last-decision-ms",str(first+24*HOUR_MS),
                    "--allow-personal-nonproduction-research",
                    "--audit-intrabar-stress",
                    "--stress-margin-quote","2","--stress-leverage","50",
                    "--stress-stop-fraction","0.01",
                    "--stress-target-fraction","0.03",
                    "--stress-maintenance-bps","0",
                    "--stress-fee-bps","0",
                    "--stress-slippage-bps","0",
                    "--stress-funding-bps","0",
                    "--stress-selection-cost-bps","0"])
            self.assertEqual(rc_stress,0)
            self.assertIn("hypothetical_intrabar_oos",stress_output.getvalue())
            self.assertNotIn("BTCUSDT",stress_output.getvalue())
            self.assertNotIn(str(root),output.getvalue())
            self.assertEqual(json.loads(output.getvalue())["status"],
                             "private_vision_dynamic_replay_rejected")

    def test_no_optin_rejects_before_read(self):
        with patch("socket.create_connection",side_effect=AssertionError("network")):
            with self.assertRaises(VisionReplayPrivateError):
                private_vision_dynamic_replay(manifest_paths=("bad","other"),
                    first_decision_ms=1,last_decision_ms=1)
