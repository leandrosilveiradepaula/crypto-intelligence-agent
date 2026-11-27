"""D546 upgrade installer is an administrator-only, syntax-checked local tool."""
from pathlib import Path
import os
import shutil
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[1]


class InstallerTests(unittest.TestCase):
    @unittest.skipUnless(os.name=="posix" and shutil.which("bash"),
                         "POSIX Bash required for Linux VPS installer")
    def test_shell_syntax(self):
        p=ROOT/"deploy/vps/research/upgrade_j3_executor_d546_once.sh"
        subprocess.run(["bash","-n"],input=p.read_text(encoding="utf-8"),
                       text=True,check=True)


if __name__=="__main__":
    unittest.main()
