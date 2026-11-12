"""J1/D317 public WS CLI: no real network, no systemd and no orders."""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
import os
import unittest
from unittest.mock import patch

from scripts.run_j1_n50_ws_owner_cached_once import main

PATHS=["--manifest-directory","/tmp/cached-private-rank",
       "--ws-directory","/tmp/cached-private-ws"]
PERMITS=[
    "--allow-private-manifest-read",
    "--allow-private-ws-scope-read",
    "--allow-private-ws-writer",
    "--allow-public-websocket",
    "--confirm-region-and-personal-research",
]


class OwnerN50WSCliTests(unittest.TestCase):
    def invoke(self,args,**patches):
        buf=StringIO()
        with redirect_stdout(buf):
            rc=main(args)
        report=json.loads(buf.getvalue())
        self.assertFalse(report["orders_sent"])
        self.assertFalse(report["systemd_modified"])
        self.assertFalse(report["marketwide_top50_verified"])
        self.assertEqual(report["http_gets"],0)
        self.assertNotIn("USDT",buf.getvalue())
        return rc,report

    def test_default_and_any_missing_permission_never_start_runner(self):
        with patch(
            "scripts.run_j1_n50_ws_owner_cached_once.run_cached_n50_ws_owner_window",
            side_effect=AssertionError("must never start without optins"),
        ):
            r,p=self.invoke(PATHS)
            self.assertEqual(r,77)
            self.assertEqual(p["status"],"ws_owner_window_optin_required")
            for i in range(len(PERMITS)):
                partial=PERMITS[:i]+PERMITS[i+1:]
                r,p=self.invoke(PATHS+partial)
                self.assertEqual(r,77)
                self.assertEqual(p["status"],"ws_owner_window_optin_required")

    @unittest.skipUnless(os.name=="posix","owner POSIX executor")
    def test_root_denied_before_session_factory(self):
        with patch("scripts.run_j1_n50_ws_owner_cached_once.os.getuid",return_value=0),\
             patch("scripts.run_j1_n50_ws_owner_cached_once.os.geteuid",return_value=0),\
             patch("scripts.run_j1_n50_ws_owner_cached_once.run_cached_n50_ws_owner_window",
                   side_effect=AssertionError("must not start root")):
            r,p=self.invoke(PATHS+PERMITS)
        self.assertEqual(r,77)
        self.assertEqual(p["status"],"ws_owner_window_preflight_abstain")

    @unittest.skipUnless(os.name=="posix","owner POSIX executor")
    def test_fully_authorized_cli_injects_existing_public_ws_only(self):
        result=dict(
            status="ws_owner_hour_50_observed_local_only",
            orders_sent=False,systemd_modified=False,http_gets=0,
            marketwide_top50_verified=False,
        )
        def fake_socket():
            raise AssertionError("real WS factory must only be passed, not called by CLI")
        with patch("scripts.run_j1_n50_ws_owner_cached_once.os.getuid",return_value=1000),\
             patch("scripts.run_j1_n50_ws_owner_cached_once.os.geteuid",return_value=1000),\
             patch("crypto_intelligence_agent.bybit_public_ws_once._real_session_factory",
                   new=fake_socket),\
             patch("scripts.run_j1_n50_ws_owner_cached_once.run_cached_n50_ws_owner_window",
                   return_value=result) as runner:
            rc,doc=self.invoke(PATHS+PERMITS)
        self.assertEqual(rc,0)
        self.assertEqual(doc["status"],result["status"])
        self.assertIs(runner.call_args.kwargs["session_factory"],fake_socket)
        self.assertFalse(runner.call_args.kwargs["allow_create_ws_journal"])
        self.assertTrue(runner.call_args.kwargs["allow_private_ws_writer"])

    @unittest.skipUnless(os.name=="posix","owner POSIX executor")
    def test_runtime_failure_is_sanitized_and_no_retry(self):
        with patch("scripts.run_j1_n50_ws_owner_cached_once.os.getuid",return_value=1000),\
             patch("scripts.run_j1_n50_ws_owner_cached_once.os.geteuid",return_value=1000),\
             patch("scripts.run_j1_n50_ws_owner_cached_once.run_cached_n50_ws_owner_window",
                   side_effect=ValueError("secret path /tmp/token")) as runner:
            rc,p=self.invoke(PATHS+PERMITS)
        self.assertEqual(rc,65)
        self.assertEqual(p["status"],"ws_owner_window_integrity_abstain")
        self.assertEqual(runner.call_count,1)


if __name__=="__main__":
    unittest.main()
