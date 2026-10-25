"""J1/WU26 — Read-only audit of PREVIOUS issue_comment probe runs.

This scans one known GitHub Actions workflow on a fixed UTC date and prints
ONLY sanitized run/job identifiers and outcomes. It NEVER triggers workflows,
calls exchange/market APIs, downloads job logs, changes issues, or publishes
raw response data. Job IDs are pointers to separate human/agent log review;
metadata alone is NOT proof the market data API returned HTTP 200.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
import re
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


REPO = "leandrosilveiradepaula/crypto-intelligence-agent"
OWNER = "leandrosilveiradepaula"
WORKFLOW_FILE = "public-feed-smoke.yml"
API_BASE = f"https://api.github.com/repos/{REPO}/actions"
RUN_DATE = "2026-10-25"
PAGE_LIMIT = 100
MAX_RUNS_BYTES = 3 * 1024 * 1024
MAX_JOBS_BYTES = 512 * 1024
MAX_REQUESTS = 65
TIMEOUT_S = 8
TARGETS = {
    "vike-keyless-manifest": "issue_63",
    "hyperliquid-native-btc-info": "issue_72",
}
_ALLOWED_STATUSES = frozenset({"queued", "in_progress", "completed", "waiting", "pending", "requested"})
_ALLOWED_CONCLUSIONS = frozenset({
    "success", "failure", "cancelled", "skipped",
    "timed_out", "action_required", "neutral", "startup_failure",
})
_RUN_TIME = re.compile(r"2026-10-25T\d{2}:\d{2}:\d{2}Z")


class AuditError(ValueError):
    """Do not print remote response bodies, exception details, or tokens."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _pairs_unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise AuditError("duplicate_json_key")
        out[key] = value
    return out


def _reject_nonfinite(_value: str) -> None:
    raise AuditError("nonfinite_json")


def _json(body: bytes) -> Any:
    try:
        return json.loads(body, object_pairs_hook=_pairs_unique, parse_constant=_reject_nonfinite)
    except (ValueError, UnicodeDecodeError, RecursionError) as exc:
        if isinstance(exc, AuditError):
            raise
        raise AuditError("invalid_json") from None


def _date(value: Any) -> str:
    if type(value) is not str or _RUN_TIME.fullmatch(value) is None:
        raise AuditError("invalid_utc_created_at")
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise AuditError("invalid_utc_created_at") from None
    return value


def _number(value: Any, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise AuditError("invalid_" + label)
    return value


def _state(value: Any, *, completion: bool) -> str | None:
    if value is None and completion:
        return None
    allowed = _ALLOWED_CONCLUSIONS if completion else _ALLOWED_STATUSES
    if type(value) is not str or value not in allowed:
        raise AuditError("invalid_run_or_job_state")
    return value


def _get(
    *, path: str, token: str, limit: int, opener: Callable[..., Any],
    requests: list[int],
) -> Any:
    if len(requests) >= MAX_REQUESTS:
        raise AuditError("request_limit_exceeded")
    # A caller cannot redirect this function to arbitrary GitHub API routes.
    base = f"/repos/{REPO}/actions/"
    if (not path.startswith(base) or "//" in path or ".." in path
            or not path.isascii()):
        raise AuditError("unapproved_github_api_path")
    url = "https://api.github.com" + path
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Authorization": "Bearer " + token,
        "User-Agent": "j1-evidence-run-readonly-audit",
    }
    req = Request(url, method="GET", headers=headers)
    requests.append(1)
    try:
        with opener(req, timeout=TIMEOUT_S) as response:
            status = response.getcode() if hasattr(response, "getcode") else response.status
            if status != 200 or response.geturl() != url:
                raise AuditError("unexpected_http_status_or_redirect")
            payload = response.read(limit + 1)
            if not payload or len(payload) > limit:
                raise AuditError("empty_or_oversized_github_response")
            return _json(payload)
    except HTTPError as exc:
        if exc.code in (401, 403):
            raise AuditError("github_actions_read_permission_or_access_missing") from None
        if exc.code == 429:
            raise AuditError("github_api_rate_limited") from None
        raise AuditError("github_http_failure") from None
    except (URLError, OSError, TimeoutError):
        raise AuditError("github_network_failure") from None


def _audit(
    token: str, *, opener: Callable[..., Any],
) -> dict[str, Any]:
    if type(token) is not str or not token or len(token) > 4096:
        raise AuditError("actions_read_token_required")
    req_count: list[int] = []
    query = urlencode({
        "event": "issue_comment",
        "created": RUN_DATE,
        "per_page": str(PAGE_LIMIT),
    })
    runs_url = f"/repos/{REPO}/actions/workflows/{WORKFLOW_FILE}/runs?{query}"
    listing = _get(path=runs_url, token=token, limit=MAX_RUNS_BYTES,
                   opener=opener, requests=req_count)
    if type(listing) is not dict or type(listing.get("workflow_runs")) is not list:
        raise AuditError("workflow_run_list_schema_invalid")
    runs = listing["workflow_runs"]
    count = listing.get("total_count")
    if (type(count) is not int or count < 0 or count > PAGE_LIMIT
            or len(runs) > PAGE_LIMIT or len(runs) > count):
        raise AuditError("pagination_incomplete_or_invalid")
    found: list[dict[str, Any]] = []
    seen_runs: set[int] = set()
    seen_jobs: set[int] = set()
    for run in runs:
        if type(run) is not dict:
            raise AuditError("workflow_run_schema_invalid")
        run_id = _number(run.get("id"), "run_id")
        if run_id in seen_runs:
            raise AuditError("duplicate_workflow_run")
        seen_runs.add(run_id)
        created = _date(run.get("created_at"))
        if run.get("event") != "issue_comment":
            raise AuditError("unexpected_trigger_event")
        if type(run.get("actor")) is not dict or run["actor"].get("login") != OWNER:
            # Do not inspect runs created by other actors or publish other jobs.
            continue
        run_status = _state(run.get("status"), completion=False)
        run_conclusion = _state(run.get("conclusion"), completion=True)
        if run_status != "completed" or run_conclusion is None:
            continue
        jobs_path = f"/repos/{REPO}/actions/runs/{run_id}/jobs?per_page=100"
        response = _get(path=jobs_path, token=token, limit=MAX_JOBS_BYTES,
                        opener=opener, requests=req_count)
        if type(response) is not dict or type(response.get("jobs")) is not list:
            raise AuditError("job_list_schema_invalid")
        job_rows = response["jobs"]
        total = response.get("total_count")
        if (type(total) is not int or total < 0 or total > PAGE_LIMIT
                or len(job_rows) > PAGE_LIMIT or len(job_rows) > total):
            raise AuditError("job_pagination_incomplete_or_invalid")
        for job in job_rows:
            if type(job) is not dict:
                raise AuditError("job_row_schema_invalid")
            name = job.get("name")
            if name not in TARGETS:
                continue
            job_id = _number(job.get("id"), "job_id")
            if job_id in seen_jobs:
                raise AuditError("duplicate_workflow_job")
            seen_jobs.add(job_id)
            job_status = _state(job.get("status"), completion=False)
            conclusion = _state(job.get("conclusion"), completion=True)
            if conclusion == "skipped":
                continue
            found.append({
                "probe": TARGETS[name],
                "run_id": run_id,
                "job_id": job_id,
                "created_at_utc": created,
                "run_status": run_status,
                "run_conclusion": run_conclusion,
                "job_status": job_status,
                "job_conclusion": conclusion,
                "source": "github_actions_issue_comment_metadata_only",
            })
    found.sort(key=lambda x: (x["probe"], x["created_at_utc"], x["run_id"]))
    return {
        "audit_version": "j1-issue-comment-readonly-v1",
        "repository": REPO,
        "workflow_file": WORKFLOW_FILE,
        "event": "issue_comment",
        "utc_date": RUN_DATE,
        "workflow_runs_considered": len(runs),
        "github_read_requests": len(req_count),
        "matches": found,
        "status": "run_job_ids_found_log_review_required" if found else "no_non_skipped_owner_probe_jobs_found",
        "job_metadata_proves_market_http_success": False,
        "live_market_data_authenticated": False,
        "external_rights_authorized": False,
        "ready_for_live_top50": False,
        "no_new_market_requests": True,
    }


def audit_existing_runs(
    *, allow_github_actions_read: bool, token: str, opener: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Only read the repository's public run/job metadata after explicit opt-in."""
    if allow_github_actions_read is not True:
        raise AuditError("explicit_github_actions_read_flag_required")
    if opener is None:
        client = build_opener(ProxyHandler({}), _NoRedirect())
        opener = client.open
    return _audit(token, opener=opener)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read previous issue_comment Actions IDs, NOT market APIs")
    parser.add_argument("--allow-github-actions-read", action="store_true")
    args = parser.parse_args(argv)
    if not args.allow_github_actions_read:
        parser.error("offline by default; pass --allow-github-actions-read")
    # GITHUB_TOKEN is ephemeral and granted only actions:read/contents:read by
    # dedicated owner-only workflow; never echo, persist or interpolate it.
    token = os.environ.get("GITHUB_TOKEN", "")
    try:
        output = audit_existing_runs(
            allow_github_actions_read=True, token=token,
        )
    except AuditError as error:
        print(json.dumps({
            "audit_version": "j1-issue-comment-readonly-v1",
            "status": error.code,
            "no_new_market_requests": True,
            "ready_for_live_top50": False,
        }, sort_keys=True))
        return 2
    print(json.dumps(output, sort_keys=True, ensure_ascii=False))
    return 0 if output["matches"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
