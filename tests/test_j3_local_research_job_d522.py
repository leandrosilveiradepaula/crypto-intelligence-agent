"""D522 research job isolation and local API contract, no network or real orders."""
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import subprocess
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch, Mock

from crypto_intelligence_agent.j3_local_research_job_d522 import (
    ResearchJob, ResearchBusy, JOB_SCHEMA, DEFAULT_MATRIX,
)
from crypto_intelligence_agent.market_data import DataValidationError
from scripts.serve_paper_profile_lab_d487 import OwnerPaperProfileHandler, PORT

REVISION="a"*64
CUTOFF=1795547640289


def report(raw, *, horizon=4, cutoff=CUTOFF):
    return {"schema_version":"d520-exploratory-combination-research-v1",
            "status":"exploratory_matrix_completed","public_gets":0,
            "profile_revision":REVISION,"horizon_hours":horizon,"as_of_ms":cutoff,
            "manifest":{"matrix_sha256":sha256(raw).hexdigest()},
            "rows":[{} for _ in range(25)],
            **{k:False for k in ("orders_sent","profile_modified",
                "out_of_sample_results_validated","approved_for_live_use",
                "financial_backtest_approved","funding_settlement_verified",
                "liquidation_verified","intrabar_path_verified","winner_selected")}}


class ResearchJobTests(unittest.TestCase):
    def job(self):
        return ResearchJob(policy_file=Path("/owner/policy.json"),
                           history_directory=Path("/owner/history"))

    def test_bounded_request_and_custom_matrix(self):
        job=self.job()
        self.assertEqual(job.status()["status"],"idle")
        for value in ({},{"horizon_hours":0},{"horizon_hours":True},
                      {"horizon_hours":13},{"horizon_hours":4,"as_of_ms":True},
                      {"horizon_hours":4,"path":"/tmp/other"},
                      {"horizon_hours":4,"matrix":{"profiles":[]}}):
            with self.subTest(value=value),self.assertRaises(DataValidationError):
                job.start(value)
        self.assertEqual(job.status()["status"],"idle")

    @patch("crypto_intelligence_agent.j3_local_research_job_d522.snapshot",
           return_value={"revision":REVISION})
    @patch("crypto_intelligence_agent.j3_local_research_job_d522.subprocess.run")
    def test_one_job_and_valid_report_without_shell_or_mutation(self,run,snapshot):
        job=self.job()
        entered=threading.Event()
        release=threading.Event()
        done=threading.Event()
        original=job._run
        def finish(*args):
            try: original(*args)
            finally: done.set()
        job._run=finish
        def child(cmd,**kwargs):
            entered.set()
            if not release.wait(5):
                raise subprocess.TimeoutExpired(cmd,5)
            return SimpleNamespace(returncode=0,stdout=json.dumps(
                report(kwargs["input"])).encode())
        run.side_effect=child
        try:
            start=job.start({"horizon_hours":4,"as_of_ms":CUTOFF})
            self.assertEqual(start["schema_version"],JOB_SCHEMA)
            self.assertEqual(start["strategy_count"],25)
            self.assertTrue(entered.wait(5))
            self.assertEqual(job.status()["status"],"running")
            with self.assertRaises(ResearchBusy):
                job.start({"horizon_hours":4})
        finally:
            release.set()
        self.assertTrue(done.wait(5))
        out=job.status()
        self.assertEqual(out["status"],"completed")
        self.assertEqual(out["report"]["profile_revision"],REVISION)
        self.assertFalse(out["orders_sent"])
        cmd=run.call_args.args[0]
        kw=run.call_args.kwargs
        self.assertIn("scripts.run_j3_combination_research_d520",cmd)
        self.assertIn("--matrix-stdin",cmd)
        self.assertIn("--low-priority",cmd)
        self.assertNotIn("--allow-public-network",cmd)
        self.assertFalse(kw.get("shell",False))
        self.assertEqual(kw["timeout"],300)
        self.assertEqual(kw["input"],DEFAULT_MATRIX.read_bytes())

    @patch("crypto_intelligence_agent.j3_local_research_job_d522.subprocess.run")
    def test_worker_timeout_and_mismatched_profile_fail_closed(self,run):
        raw=DEFAULT_MATRIX.read_bytes()
        fields={"job_id":"test","strategy_count":25,"profile_revision":REVISION,
                "horizon_hours":4,"requested_as_of_ms":CUTOFF,
                "matrix_sha256":sha256(raw).hexdigest()}
        job=self.job()
        run.side_effect=subprocess.TimeoutExpired(["python"],300)
        job._run(["python"],raw,fields)
        self.assertEqual(job.status()["error"],"research_timeout")
        self.assertNotIn("report",job.status())
        run.side_effect=None
        bad=report(raw)
        bad["profile_revision"]="b"*64
        run.return_value=SimpleNamespace(returncode=0,stdout=json.dumps(bad).encode())
        job._run(["python"],raw,fields)
        self.assertEqual(job.status()["error"],"research_unavailable")
        self.assertNotIn("report",job.status())

    def test_loopback_same_origin_gate_and_read_only_status(self):
        h=object.__new__(OwnerPaperProfileHandler)
        h.path="/api/combination-research"
        h.client_address=("127.0.0.1",4321)
        h.headers={"Host":f"127.0.0.1:{PORT}"}
        h._respond=Mock()
        job=Mock()
        job.start.return_value={"status":"running","orders_sent":False}
        job.status.return_value={"status":"idle","orders_sent":False}
        with patch.object(OwnerPaperProfileHandler,"research_job",job):
            h.do_POST()
            self.assertEqual(h._respond.call_args.args[0],403)
            job.start.assert_not_called()
            body=b'{"horizon_hours":4}'
            h.headers.update({"Origin":f"http://127.0.0.1:{PORT}",
                              "X-CIA-Paper-Profile":"1","Content-Type":"application/json",
                              "Content-Length":str(len(body))})
            h.rfile=BytesIO(body)
            h.do_POST()
            self.assertEqual(h._respond.call_args.args[0],202)
            job.start.assert_called_once_with({"horizon_hours":4})
            h.do_GET()
            self.assertEqual(h._respond.call_args.args[0],200)
            job.status.assert_called_once()
            h.client_address=("192.0.2.1",4321)
            h.do_GET()
            self.assertEqual(h._respond.call_args.args[0],403)


if __name__=="__main__":
    unittest.main()
