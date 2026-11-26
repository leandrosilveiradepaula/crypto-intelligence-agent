"""D544 upgrade installer is an administrator-only, syntax-checked local tool."""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[1]


class InstallerTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("bash"),"bash unavailable")
    def test_shell_syntax(self):
        p=ROOT/"deploy/vps/research/upgrade_j3_executor_d544_once.sh"
        subprocess.run(["bash","-n",str(p)],check=True)


if __name__=="__main__":
    unittest.main()
