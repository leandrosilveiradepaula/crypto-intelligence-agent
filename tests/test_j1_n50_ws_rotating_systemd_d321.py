"""D321: future rotating WS services must be inert and isolated."""
from __future__ import annotations

from pathlib import Path
import unittest

from scripts.render_j1_n50_ws_rotating_systemd import (
    render_rotating_ws_systemd,
)

ROOT="/home/cia-probe/agent/j1-n50-ws-epochs"
STATE=ROOT+"/active"


class WSRotatingSystemdUnitTests(unittest.TestCase):
    def render(self,**updates):
        kwargs=dict(owner="cia-probe",
                    repo="/home/cia-probe/agent/j1-n50-ws-code-d321",
                    python="/home/cia-probe/agent/ws-venv/bin/python",
                    epoch_root=ROOT,state_directory=STATE)
        kwargs.update(updates)
        return render_rotating_ws_systemd(**kwargs)

    def test_exact_ws_and_rotation_units_do_not_run_old_n50_rest(self):
        ws,timer,rotator=self.render()
        self.assertIn("scripts.run_j1_n50_ws_owner_active_once",ws)
        self.assertIn(" --state-directory "+STATE,ws)
        self.assertIn("ReadWritePaths="+ROOT,ws)
        self.assertIn("OnFailure=cia-j1-n50-ws-fallback.service",ws)
        self.assertIn("scripts.rotate_j1_n50_ws_epoch_once",rotator)
        self.assertIn(" --epoch-root "+ROOT,rotator)
        self.assertIn("OnCalendar=*-*-* *:02:15 UTC",timer)
        self.assertIn("AccuracySec=1s",timer)
        self.assertIn("Persistent=false",timer)
        self.assertIn("Unit=cia-j1-n50-ws-rotate.service",timer)
        self.assertNotIn("systemctl enable",ws+timer+rotator)
        self.assertNotIn("scripts.run_j1_n50_managed_once",ws+timer+rotator)
        self.assertNotIn("cia-j1-n50-managed.timer",ws+timer+rotator)
        self.assertNotIn("@",ws+timer+rotator)

        old=(Path(__file__).resolve().parents[1]/
             "deploy/systemd/cia-j1-n50-ws.timer.template").read_text("ascii")
        self.assertIn("OnCalendar=*-*-* *:59:30 UTC",old)
        self.assertNotIn("OnCalendar=*-*-* *:02:15 UTC",old)

    def test_untrusted_paths_and_root_are_denied(self):
        for values in (
            {"owner":"root"},{"owner":"cia-probe;rm"},
            {"repo":"../app"},{"repo":ROOT},
            {"epoch_root":"/home/cia-probe/agent/j1-n50-managed-d296-private"},
            {"state_directory":ROOT+"/../old"},
            {"state_directory":ROOT+"/wrong"},
            {"python":"/tmp/py;bad"},
        ):
            with self.subTest(values=values),self.assertRaises(ValueError):
                self.render(**values)


if __name__=="__main__":
    unittest.main()
