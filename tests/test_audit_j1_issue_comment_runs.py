"""J1/WU26: GitHub Actions run audit. All HTTP mocked; NO network or market data."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import unittest
from urllib.parse import urlparse, parse_qs
from unittest.mock import Mock

from scripts.audit_j1_issue_comment_runs import (
    API_BASE, OWNER, REPO, RUN_DATE, PAGE_LIMIT, MAX_RUNS_BYTES,
    AuditError, audit_existing_runs, _get, _json, main,
)

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "j1-evidence-run-audit.yml"


def run_item(id=111, *, actor=OWNER, status="completed", conclusion="success",
             event="issue_comment", created="2026-10-25T17:49:23Z"):
    return {
        "id": id, "created_at": created, "event": event,
        "actor": {"login": actor}, "status": status, "conclusion": conclusion,
    }


def job_item(id=987, name="vike-keyless-manifest", *,
             status="completed", conclusion="success"):
    return {"id": id, "name": name, "status": status, "conclusion": conclusion}


def fixture():
    runs = [
        run_item(id=222, created="2026-10-25T17:47:13Z"),
        run_item(id=111, created="2026-10-25T17:20:11Z"),
    ]
    jobs = {
        111: [job_item(911, "vike-keyless-manifest", conclusion="success"),
              job_item(912, "hyperliquid-native-btc-info", conclusion="skipped")],
        222: [job_item(921, "vike-keyless-manifest", conclusion="skipped"),
              job_item(922, "hyperliquid-native-btc-info", conclusion="failure")],
    }
    return runs, jobs


class FakeResponse:
    def __init__(self, payload, *, url, code=200):
        self.raw = payload if type(payload) is bytes else json.dumps(payload).encode()
        self.url = url
        self.code = code

    def getcode(self):
        return self.code

    def geturl(self):
        return self.url

    def read(self, length):
        return self.raw[:length]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeGitHub:
    def __init__(self, runs=None, jobs=None):
        default_runs, default_jobs = fixture()
        self.runs = default_runs if runs is None else runs
        self.jobs = default_jobs if jobs is None else jobs
        self.calls = []

    def __call__(self, req, *, timeout):
        self.calls.append((req, timeout))
        self_check = urlparse(req.full_url)
        if self_check.path.endswith("/workflows/public-feed-smoke.yml/runs"):
            payload = {"total_count": len(self.runs), "workflow_runs": self.runs}
        else:
            part = self_check.path.split("/actions/runs/")
            if len(part) != 2 or not part[1].endswith("/jobs"):
                raise AssertionError("unexpected GitHub URL")
            rid = int(part[1].split("/")[0])
            items = self.jobs[rid]
            payload = {"total_count": len(items), "jobs": items}
        return FakeResponse(payload, url=req.full_url)


def audit(fake=None, *, flag=True, token="ephemeral_unit_test_only"):
    return audit_existing_runs(
        allow_github_actions_read=flag, token=token,
        opener=fake or FakeGitHub(),
    )


class J1PreviousRunAuditTests(unittest.TestCase):
    def test_positive_discovers_existing_run_and_job_ids_only(self):
        mock = FakeGitHub()
        result = audit(mock)
        self.assertEqual(result["status"], "run_job_ids_found_log_review_required")
        self.assertEqual(result["event"], "issue_comment")
        self.assertEqual(result["repository"], REPO)
        self.assertEqual(result["utc_date"], RUN_DATE)
        self.assertEqual(result["workflow_runs_considered"], 2)
        self.assertEqual(result["github_read_requests"], 3)
        self.assertEqual(len(result["matches"]), 2)
        self.assertEqual(result["matches"][0]["probe"], "issue_63")
        self.assertEqual(result["matches"][0]["job_id"], 911)
        self.assertEqual(result["matches"][1]["probe"], "issue_72")
        self.assertEqual(result["matches"][1]["run_id"], 222)
        self.assertEqual(result["matches"][1]["job_conclusion"], "failure")
        self.assertTrue(result["no_new_market_requests"])
        for gate in ("job_metadata_proves_market_http_success",
                     "live_market_data_authenticated", "external_rights_authorized",
                     "ready_for_live_top50"):
            self.assertFalse(result[gate])

    def test_only_repository_github_metadata_get_no_market_host(self):
        fake = FakeGitHub()
        audit(fake)
        self.assertEqual(len(fake.calls), 3)
        for req, timeout in fake.calls:
            self.assertEqual(req.get_method(), "GET")
            self.assertEqual(timeout, 8)
            self.assertEqual(urlparse(req.full_url).hostname, "api.github.com")
            self.assertTrue(urlparse(req.full_url).path.startswith(f"/repos/{REPO}/actions/"))
            self.assertEqual(req.get_header("User-agent"), "j1-evidence-run-readonly-audit")
            self.assertTrue(req.get_header("Authorization").startswith("Bearer "))
        first = fake.calls[0][0]
        query = parse_qs(urlparse(first.full_url).query)
        self.assertEqual(query["event"], ["issue_comment"])
        self.assertEqual(query["created"], ["2026-10-25"])
        self.assertEqual(query["per_page"], ["100"])

    def test_no_actual_log_payload_or_prices_in_public_summary(self):
        result = audit()
        content = json.dumps(result, sort_keys=True).lower()
        for phrase in ("wallet", "12345.67", "fundingrate", "token", "authorization",
                       "prices", "body", "secret", "ghp_", "coin"):
            self.assertNotIn(phrase, content)

    def test_no_network_without_explicit_flag_or_token(self):
        for flag, token in ((False, "good"), (0, "good"), (True, ""),
                            (True, None), (True, 1), (True, "x" * 4097)):
            fake = Mock()
            with self.subTest(flag=flag, token=repr(token)[:20]):
                with self.assertRaises(AuditError):
                    audit_existing_runs(
                        allow_github_actions_read=flag, token=token, opener=fake,
                    )
                fake.assert_not_called()

    def test_skipped_jobs_not_evidence_of_probe_execution(self):
        runs = [run_item()]
        jobs = {111: [job_item(10, "vike-keyless-manifest", conclusion="skipped"),
                      job_item(11, "hyperliquid-native-btc-info", conclusion="skipped")]}
        result = audit(FakeGitHub(runs=runs, jobs=jobs))
        self.assertEqual(result["matches"], [])
        self.assertEqual(result["status"], "no_non_skipped_owner_probe_jobs_found")

    def test_unrelated_jobs_not_evidence(self):
        result = audit(FakeGitHub(
            runs=[run_item()],
            jobs={111: [job_item(9, "smoke"), job_item(10, "independent-provider-probe")]},
        ))
        self.assertEqual(result["matches"], [])

    def test_untrusted_actor_not_scanned_or_reported(self):
        fake = FakeGitHub(
            runs=[run_item(actor="someone_else")],
            jobs={111: [job_item(99)]},
        )
        result = audit(fake)
        self.assertEqual(result["matches"], [])
        self.assertEqual(len(fake.calls), 1)

    def test_unknown_event_rejected(self):
        with self.assertRaisesRegex(AuditError, "unexpected_trigger_event"):
            audit(FakeGitHub(runs=[run_item(event="pull_request")]))

    def test_duplicate_run_and_job_ids_rejected(self):
        one = run_item()
        with self.assertRaises(AuditError):
            audit(FakeGitHub(runs=[one, deepcopy(one)]))
        with self.assertRaises(AuditError):
            audit(FakeGitHub(runs=[one], jobs={111: [
                job_item(9, "vike-keyless-manifest"),
                job_item(9, "hyperliquid-native-btc-info"),
            ]}))

    def test_unfinished_workflows_not_labeled_as_run_results(self):
        r = run_item(status="in_progress", conclusion=None)
        fake = FakeGitHub(runs=[r])
        result = audit(fake)
        self.assertFalse(result["matches"])
        self.assertEqual(len(fake.calls), 1)

    def test_valid_failure_run_is_not_falsely_called_success(self):
        r = run_item(conclusion="failure")
        res = audit(FakeGitHub(runs=[r], jobs={111: [
            job_item(5, "vike-keyless-manifest", conclusion="failure"),
        ]}))
        self.assertEqual(res["matches"][0]["run_conclusion"], "failure")
        self.assertEqual(res["matches"][0]["job_conclusion"], "failure")
        self.assertFalse(res["job_metadata_proves_market_http_success"])

    def test_bad_dates_actor_ids_and_status_fail_closed(self):
        changes = [
            {"created_at": "2026-13-33T17:00:00Z"},
            {"created_at": "2026-10-26T00:00:00Z"},
            {"id": True}, {"id": -1}, {"status": "hacked"},
            {"conclusion": "UNKNOWN"},
            {"actor": "leandrosilveiradepaula"},
        ]
        for fields in changes:
            candidate = dict(run_item(), **fields)
            with self.subTest(fields=fields), self.assertRaises(AuditError):
                audit(FakeGitHub(runs=[candidate]))

    def test_pagination_limit_enforced_not_silently_truncated(self):
        too_many = FakeGitHub()
        class MoreRuns:
            def __init__(self, base):
                self.base = base
            def __call__(self, req, *, timeout):
                reply = self.base(req, timeout=timeout)
                if "/workflows/" in req.full_url:
                    return FakeResponse(
                        {"total_count": PAGE_LIMIT + 1, "workflow_runs": self.base.runs},
                        url=req.full_url,
                    )
                return reply
        with self.assertRaisesRegex(AuditError, "pagination"):
            audit(MoreRuns(too_many))
        with self.assertRaisesRegex(AuditError, "pagination"):
            audit(FakeGitHub(runs=[run_item()], jobs={111: [job_item(1)]*101}))

    def test_invalid_raw_json_and_duplicate_key_rejected(self):
        for value in (b"", b"{", b'{"a":1,"a":2}', b'{"v":NaN}', b"\xff"):
            with self.subTest(value=value[:20]), self.assertRaises(AuditError):
                _json(value)

    def test_unapproved_request_route_fails_before_http(self):
        for path in (
            "/repos/other/other/actions/runs",
            "/repos/leandrosilveiradepaula/crypto-intelligence-agent/issues/63",
            f"/repos/{REPO}/actions/../secrets",
            f"/repos/{REPO}/actions//runs",
        ):
            fake = Mock()
            with self.subTest(path=path), self.assertRaises(AuditError):
                _get(path=path, token="one", limit=100, opener=fake, requests=[])
            fake.assert_not_called()

    def test_response_wrong_http_redirect_oversize_rejected(self):
        for reason in ("redirect", "status", "size"):
            fake = FakeGitHub()
            def tampered(req, *, timeout):
                res = fake(req, timeout=timeout)
                if reason == "redirect":
                    res.url = "https://somewhere-else.invalid"
                elif reason == "status":
                    res.code = 401
                else:
                    res.raw = b"X" * (MAX_RUNS_BYTES + 1)
                return res
            with self.subTest(reason=reason), self.assertRaises(AuditError):
                audit(tampered)

    def test_workflow_is_owner_only_read_permission_and_not_market_feed(self):
        source = WORKFLOW.read_text(encoding="utf-8")
        for token in (
            "  pull_request:",
            "github.event.pull_request.head.repo.full_name == github.repository",
            "github.event.pull_request.head.ref == 'audit/j1-run-evidence'",
            "github.event.pull_request.user.login == 'leandrosilveiradepaula'",
            "github.actor == 'leandrosilveiradepaula'",
            "  actions: read",
            "  contents: read",
            "persist-credentials: false",
            "python3 -m scripts.audit_j1_issue_comment_runs --allow-github-actions-read",
            "GITHUB_TOKEN:",
        ):
            with self.subTest(token=token):
                self.assertIn(token, source)
        for forbidden in (
            "issues: write", "contents: write", "actions: write", "secrets.",
            "api.hyperliquid.xyz", "data.vike.io", "/exchange",
            "schedule:", "workflow_dispatch:", "issue_comment:", "pull_request_target:",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
