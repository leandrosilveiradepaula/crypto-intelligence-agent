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
