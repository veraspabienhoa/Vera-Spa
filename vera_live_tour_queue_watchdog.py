"""External GitHub watchdog for the production Live Tour PostgreSQL queue.

This module intentionally uses only the Python standard library so a scheduled
GitHub Actions runner can alert even when the Vera application dependencies or
API process are unhealthy.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from typing import Any
from urllib import error, request


ISSUE_TITLE = "[ALERT] Live Tour PostgreSQL Queue"
LAST_SUCCESS_MAX_SECONDS = 600
OLDEST_PENDING_MAX_SECONDS = 600


def evaluate_health_payload(payload: dict[str, Any]) -> list[str]:
    """Return watchdog conditions from one local production health payload."""
    if not isinstance(payload, dict) or payload.get("watchdog_error"):
        return ["health_unreachable"]

    conditions: list[str] = []
    last_success_age = payload.get("last_success_age")
    oldest_pending = payload.get("oldest_pending")
    try:
        if last_success_age is not None and float(last_success_age) > LAST_SUCCESS_MAX_SECONDS:
            conditions.append("last_success_age")
    except (TypeError, ValueError):
        conditions.append("invalid_last_success_age")
    try:
        if oldest_pending is not None and float(oldest_pending) > OLDEST_PENDING_MAX_SECONDS:
            conditions.append("oldest_pending")
    except (TypeError, ValueError):
        conditions.append("invalid_oldest_pending")
    try:
        if int(payload.get("failed") or 0) > 0:
            conditions.append("failed")
    except (TypeError, ValueError):
        conditions.append("invalid_failed")
    try:
        if int(payload.get("stale_processing") or 0) > 0:
            conditions.append("stale_processing")
    except (TypeError, ValueError):
        conditions.append("invalid_stale_processing")
    return conditions


def _fmt_age(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value):.1f}s"
    except (TypeError, ValueError):
        return "invalid"


def issue_body(payload: dict[str, Any], conditions: list[str], run_url: str) -> str:
    counts = payload.get("counts") if isinstance(payload.get("counts"), dict) else {}
    error_text = str(payload.get("watchdog_error") or "")[:500]
    rows = [
        "Live Tour PostgreSQL queue watchdog detected an unhealthy production state.",
        "",
        f"- Conditions: `{', '.join(conditions)}`",
        f"- last_success_age: `{_fmt_age(payload.get('last_success_age'))}` (alert > {LAST_SUCCESS_MAX_SECONDS}s)",
        f"- oldest_pending: `{_fmt_age(payload.get('oldest_pending'))}` (alert > {OLDEST_PENDING_MAX_SECONDS}s)",
        f"- retry: `{payload.get('retry', 'n/a')}`",
        f"- failed: `{payload.get('failed', 'n/a')}`",
        f"- stale_processing: `{payload.get('stale_processing', 'n/a')}`",
        f"- queue counts: `{json.dumps(counts, ensure_ascii=False, sort_keys=True)}`",
    ]
    if error_text:
        rows.append(f"- health error: `{error_text}`")
    if run_url:
        rows.extend(["", f"Watchdog run: {run_url}"])
    rows.extend([
        "",
        "This issue is managed automatically. It will be closed after the queue returns to a healthy state.",
    ])
    return "\n".join(rows)


def _github_request(token: str, method: str, url: str, payload: dict[str, Any] | None = None) -> Any:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "vera-live-tour-queue-watchdog",
            "Content-Type": "application/json",
        },
    )
    try:
        with request.urlopen(req, timeout=20) as response:
            raw = response.read()
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"GitHub API {method} failed with HTTP {exc.code}: {detail}") from exc
    if not raw:
        return None
    return json.loads(raw.decode("utf-8"))


def _find_open_issue(repo: str, token: str) -> dict[str, Any] | None:
    owner, name = repo.split("/", 1)
    url = f"https://api.github.com/repos/{owner}/{name}/issues?state=open&per_page=100"
    issues = _github_request(token, "GET", url) or []
    for issue in issues:
        if issue.get("pull_request"):
            continue
        if str(issue.get("title") or "") == ISSUE_TITLE:
            return issue
    return None


def sync_issue(
    *, repo: str, token: str, payload: dict[str, Any], conditions: list[str], run_url: str,
) -> str:
    """Open/update one incident issue, or close it on recovery."""
    owner, name = repo.split("/", 1)
    open_issue = _find_open_issue(repo, token)
    active = bool(conditions)

    if active:
        body = issue_body(payload, conditions, run_url)
        if open_issue is None:
            _github_request(
                token,
                "POST",
                f"https://api.github.com/repos/{owner}/{name}/issues",
                {"title": ISSUE_TITLE, "body": body},
            )
            return "opened"
        # Keep a single incident issue current without adding a comment every 5 minutes.
        _github_request(
            token,
            "PATCH",
            f"https://api.github.com/repos/{owner}/{name}/issues/{open_issue['number']}",
            {"body": body},
        )
        return "updated"

    if open_issue is None:
        return "healthy"

    number = open_issue["number"]
    _github_request(
        token,
        "POST",
        f"https://api.github.com/repos/{owner}/{name}/issues/{number}/comments",
        {
            "body": (
                "✅ Live Tour PostgreSQL queue has recovered. "
                f"last_success_age={_fmt_age(payload.get('last_success_age'))}, "
                f"retry={payload.get('retry', 'n/a')}, failed={payload.get('failed', 'n/a')}, "
                f"stale_processing={payload.get('stale_processing', 'n/a')}."
            )
        },
    )
    _github_request(
        token,
        "PATCH",
        f"https://api.github.com/repos/{owner}/{name}/issues/{number}",
        {"state": "closed", "state_reason": "completed"},
    )
    return "recovered"


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1:
        print("usage: vera_live_tour_queue_watchdog.py HEALTH_JSON", file=sys.stderr)
        return 2
    payload = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    conditions = evaluate_health_payload(payload)

    repo = os.getenv("GITHUB_REPOSITORY", "").strip()
    token = os.getenv("GITHUB_TOKEN", "").strip()
    run_url = os.getenv("WATCHDOG_RUN_URL", "").strip()
    if not repo or "/" not in repo or not token:
        print("Watchdog GitHub environment is incomplete", file=sys.stderr)
        return 2

    action = sync_issue(
        repo=repo,
        token=token,
        payload=payload,
        conditions=conditions,
        run_url=run_url,
    )
    print(json.dumps({"active": bool(conditions), "conditions": conditions, "issue_action": action}))
    return 1 if conditions else 0


if __name__ == "__main__":
    raise SystemExit(main())
