"""D544 upgrade is bounded, preserves original policy/paths and rejects drift."""
import hashlib
import os
import shutil
import subprocess
import unittest

from scripts.prepare_j3_executor_upgrade_d544 import updated_runner

OLD=b'''#!/bin/bash
set -euo pipefail
PY=/private/python
OUT=/private/reports
TASK="${1:-}"
if [ "$TASK" = probe ]; then
  echo "D541_OWNER_PROBE=PASS"
elif [ "$TASK" = collect ]; then
  ARGS=(
    --max-gets 100
  )
  "$PY" -m scripts.run_j3_long_history_d528 \\
      --oldest-first
elif [ "$TASK" = replay-annual ]; then
  "$PY" -m scripts.run_j3_long_replay_d529 \\
    --maintenance-stress-bps 50 100 150 \\
    > "$OUT/test.json"
else
  exit 2
fi
'''
SHA=hashlib.sha256(OLD).hexdigest()


class UpgradeTests(unittest.TestCase):
    def test_preserves_paths_and_restricts_new_task(self):
        new=updated_runner(OLD,SHA)
        self.assertIn(b'PY=/private/python',new)
        self.assertIn(b'OUT=/private/reports',new)
        self.assertIn(b'--max-gets 50',new)
        self.assertIn(b'--exact-missing',new)
        self.assertIn(b'--exposure-diagnostics',new)
        self.assertIn(b'--annual-directory "$OUT" --compact',new)
        self.assertIn(b'D544_OWNER_PROBE=PASS',new)
        self.assertIn(b'else\n  exit 2',new)
        self.assertNotIn(b'--oldest-first',new)

    @unittest.skipUnless(os.name=="posix" and shutil.which("bash"),
                         "POSIX Bash required for Linux VPS runner")
    def test_generated_runner_shell_syntax(self):
        subprocess.run(["bash","-n"],input=updated_runner(OLD,SHA),check=True)

    def test_refuses_wrong_digest_and_unexpected_shape(self):
        with self.assertRaises(ValueError):
            updated_runner(OLD,"0"*64)
        modified=OLD.replace(b"--max-gets 100",b"--max-gets 99")
        with self.assertRaises(ValueError):
            updated_runner(modified,hashlib.sha256(modified).hexdigest())


if __name__=="__main__":
    unittest.main()
