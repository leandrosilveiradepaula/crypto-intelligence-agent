"""D546 preserves the existing restricted runner and adds two fixed tasks."""
import hashlib
import os
import shutil
import subprocess
import unittest

from scripts.prepare_j3_executor_campaign_d546 import updated_runner
from scripts.prepare_j3_executor_upgrade_d544 import updated_runner as upgrade_d544
from test_j3_executor_upgrade_d544 import OLD,SHA


class CampaignUpgradeTests(unittest.TestCase):
    def test_chained_upgrade_is_narrow(self):
        old=upgrade_d544(OLD,SHA)
        digest=hashlib.sha256(old).hexdigest()
        result=updated_runner(old,digest)
        self.assertIn(b"D546_OWNER_PROBE=PASS",result)
        self.assertIn(b"^campaign-trade-5m-(365|730)$",result)
        self.assertIn(b'--directory "$HISTORY" --days "$DAYS"',result)
        self.assertIn(b"--exact-missing",result)
        self.assertIn(b"--exposure-diagnostics",result)
        self.assertIn(b'else\n  exit 2',result)
        with self.assertRaises(ValueError):
            updated_runner(old,"0"*64)
        with self.assertRaises(ValueError):
            updated_runner(result,hashlib.sha256(result).hexdigest())

    @unittest.skipUnless(os.name=="posix" and shutil.which("bash"),"POSIX Bash required")
    def test_runner_syntax(self):
        old=upgrade_d544(OLD,SHA)
        result=updated_runner(old,hashlib.sha256(old).hexdigest())
        subprocess.run(["bash","-n"],input=result,check=True)


if __name__=="__main__":
    unittest.main()
