"""D321: prevent reintroducing D320's guaranteed-invalid D286 start time."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import unittest

from scripts.run_j1_auto_closed24h_rank_once import (
    MIN_START_AFTER_CLOSE_MS,MAX_START_AFTER_CLOSE_MS,
)

ROOT=Path(__file__).resolve().parents[1]
D320=ROOT/"deploy/vps/prepare_install_j1_n50_ws_d320_once.sh"
D321=ROOT/"deploy/vps/prepare_install_j1_n50_ws_d321_once.sh"
ROTATE=ROOT/"deploy/systemd/cia-j1-n50-ws-rotate.timer.template"


class N50D286CausalInstallWindowTests(unittest.TestCase):
    def test_initial_rank_is_strictly_60_to_120_seconds_post_close(self):
        self.assertEqual(MIN_START_AFTER_CLOSE_MS,60_000)
        self.assertEqual(MAX_START_AFTER_CLOSE_MS,120_000)

    def test_new_installer_supersedes_invalid_0215_window(self):
        old=D320.read_text("ascii")
        new=D321.read_text("ascii")
        self.assertIn("HH:02:15..HH:02:30",old)
        self.assertIn("HH:01:15..HH:01:30",new)
        self.assertIn('if (( PHASE < 75 )); then',new)
        self.assertIn('elif (( PHASE <= 90 )); then',new)
        self.assertNotIn('if (( PHASE < 135 )); then',new)
        self.assertIn("scripts.run_j1_current_ranked_epoch_once capture-seal",new)
        self.assertIn("scripts.cache_j1_n50_ws_metadata_owner_once",new)
        self.assertIn("scripts.release_j1_n50_ws_owner_once",new)
        self.assertNotIn("rm -rf",new)
        self.assertNotIn("systemctl disable --now cia-j1-rest-hourly.timer",new)

    def test_future_rotation_timer_uses_same_safe_entry_clock(self):
        src=ROTATE.read_text("ascii")
        self.assertIn("OnCalendar=*-*-* *:01:15 UTC",src)
        self.assertIn("AccuracySec=1s",src)
        self.assertIn("Persistent=false",src)
        ws=(ROOT/"deploy/systemd/cia-j1-n50-ws.timer.template").read_text("ascii")
        self.assertIn("OnCalendar=*-*-* *:59:30 UTC",ws)

    @unittest.skipUnless(os.name=="posix","Bash parsing test on Linux only")
    def test_corrected_root_script_parses(self):
        r=subprocess.run(
            ["/usr/bin/bash","-n",str(D321)],
            capture_output=True,text=True,timeout=10,check=False,
        )
        self.assertEqual(r.returncode,0,r.stderr)


if __name__=="__main__":
    unittest.main()
