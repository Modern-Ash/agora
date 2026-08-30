"""Reviewed native-CLI adapters for the provider-neutral issue tracker port."""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from agora.filesystem import packs_root
from agora.issue_tracking import snapshot_payload_sha256
from agora.model import ExternalIssueSnapshot
from agora.tools import load_tool_contract, probe_tool_runtime

TrackerRunner = Callable[[list[str], Path], subprocess.CompletedProcess[str]]


def _default_runner(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


class GitHubIssueTrackerAdapter:
    tracker = "github"

    def __init__(self, root: Path, runner: TrackerRunner | None = None) -> None:
        self.root = root.resolve()
        self._runner = runner or _default_runner
        self._executable: str | None = None

    def fetch(self, project: str, external_ids: Sequence[str]) -> list[ExternalIssueSnapshot]:
        self._executable = self._executable or _reviewed_executable(
            self.root, "github-issues", self._runner
        )
        return [self._fetch_one(project, issue_id) for issue_id in external_ids]

    def _fetch_one(self, project: str, issue_id: str) -> ExternalIssueSnapshot:
        command = [
            self._executable or "gh",
            "issue",
            "view",
            issue_id,
            "--repo",
            project,
            "--json",
            ("number,title,state,stateReason,url,updatedAt,author,labels,milestone,comments"),
        ]
        result = self._runner(command, self.root)
        payload = _load_provider_json(result, "GitHub issue")
        return normalize_github_issue(project, payload)


class JiraIssueTrackerAdapter:
    tracker = "jira"

    def __init__(
        self,
        root: Path,
        runner: TrackerRunner | None = None,
        *,
        closed_states: Sequence[str] = ("done", "closed", "resolved"),
    ) -> None:
        self.root = root.resolve()
        self._runner = runner or _default_runner
        self.closed_states = {item.casefold() for item in closed_states}
        self._executable: str | None = None

    def fetch(self, project: str, external_ids: Sequence[str]) -> list[ExternalIssueSnapshot]:
        self._executable = self._executable or _reviewed_executable(self.root, "jira", self._runner)
        return [self._fetch_one(project, issue_id) for issue_id in external_ids]

    def _fetch_one(self, project: str, issue_id: str) -> ExternalIssueSnapshot:
        command = [
            self._executable or "acli",
            "jira",
            "workitem",
            "view",
            issue_id,
            "--fields",
            "key,summary,status,reporter,labels,updated,comment",
            "--json",
        ]
        result = self._runner(command, self.root)
        payload = _load_provider_json(result, "Jira issue")
        return normalize_jira_issue(project, payload, self.closed_states)


def normalize_github_issue(project: str, payload: dict[str, Any]) -> ExternalIssueSnapshot:
    external_id = str(_required(payload, "number"))
    state_value = str(_required(payload, "state")).casefold()
    if state_value not in {"open", "closed"}:
        raise ValueError(f"Unsupported GitHub issue state: {state_value}")
    author = payload.get("author")
    labels = payload.get("labels", [])
    comments = payload.get("comments", [])
    milestone = payload.get("milestone")
    if not isinstance(labels, list) or not isinstance(comments, list):
        raise ValueError("GitHub issue labels and comments must be arrays")
    normalized = {
        "number": external_id,
        "title": str(_required(payload, "title")),
        "state": state_value,
        "url": str(_required(payload, "url")),
        "updatedAt": str(_required(payload, "updatedAt")),
        "author": author,
        "labels": labels,
        "milestone": milestone,
        "comments": comments,
    }
    return ExternalIssueSnapshot(
        tracker="github",
        project=project,
        external_id=external_id,
        title=normalized["title"],
        state=state_value,  # type: ignore[arg-type]
        url=normalized["url"],
        updated_at=normalized["updatedAt"],
        author_subject=_nested_string(author, "login"),
        author_display_name=_nested_string(author, "name") or _nested_string(author, "login"),
        labels=[str(_required(item, "name")) for item in labels if isinstance(item, dict)],
        milestone=_nested_string(milestone, "title"),
        comment_count=len(comments),
        payload_sha256=snapshot_payload_sha256(normalized),
    )


def normalize_jira_issue(
    project: str, payload: dict[str, Any], closed_states: set[str]
) -> ExternalIssueSnapshot:
    fields_value = payload.get("fields", payload)
    if not isinstance(fields_value, dict):
        raise ValueError("Jira issue fields must be an object")
    fields: dict[str, Any] = fields_value
    external_id = str(payload.get("key") or _required(fields, "key"))
    status_value = fields.get("status")
    status_name = (
        _nested_string(status_value, "name")
        if isinstance(status_value, dict)
        else str(status_value or "")
    )
    if not status_name:
        raise ValueError("Jira issue status is missing")
    state = "closed" if status_name.casefold() in closed_states else "open"
    reporter = fields.get("reporter")
    labels = fields.get("labels", [])
    if not isinstance(labels, list):
        raise ValueError("Jira issue labels must be an array")
    comment = fields.get("comment", {})
    comment_count = 0
    if isinstance(comment, dict):
        total = comment.get("total", len(comment.get("comments", [])))
        if isinstance(total, int) and not isinstance(total, bool):
            comment_count = total
    normalized = {
        "key": external_id,
        "summary": str(_required(fields, "summary")),
        "status": status_name,
        "url": str(payload.get("self") or fields.get("url") or f"jira://{external_id}"),
        "updated": str(_required(fields, "updated")),
        "reporter": reporter,
        "labels": labels,
        "comment-count": comment_count,
    }
    return ExternalIssueSnapshot(
        tracker="jira",
        project=project,
        external_id=external_id,
        title=normalized["summary"],
        state=state,
        url=normalized["url"],
        updated_at=normalized["updated"],
        author_subject=_nested_string(reporter, "accountId"),
        author_display_name=_nested_string(reporter, "displayName"),
        labels=[str(item) for item in labels],
        milestone=None,
        comment_count=comment_count,
        payload_sha256=snapshot_payload_sha256(normalized),
    )


def _load_provider_json(result: subprocess.CompletedProcess[str], label: str) -> dict[str, Any]:
    if result.returncode != 0:
        raise RuntimeError(
            f"{label} read failed with exit {result.returncode}; provider output was not exposed"
        )
    if len(result.stdout.encode("utf-8")) > 1024 * 1024:
        raise RuntimeError(f"{label} response exceeds the 1 MiB capture limit")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise ValueError(f"{label} returned invalid JSON") from error
    if not isinstance(payload, dict):
        raise ValueError(f"{label} response must be a JSON object")
    return payload


def _reviewed_executable(root: Path, adapter_id: str, runner: TrackerRunner) -> str:
    """Enforce the bundled reviewed adapter's declared executable and minimum version."""
    contract = load_tool_contract(packs_root() / "adapters" / "cli" / adapter_id)
    # Injected runners are deterministic test/replay boundaries and do not inspect host PATH.
    executable = (
        shutil.which(contract.executable) if runner is _default_runner else contract.executable
    )
    probe = probe_tool_runtime(
        contract,
        executable,
        runner=lambda command: runner(command, root),
    )
    if not probe.available:
        raise FileNotFoundError(probe.detail)
    if probe.compatible is not True:
        raise RuntimeError(
            f"Reviewed {adapter_id} adapter runtime is not verifiably compatible: {probe.detail}"
        )
    return executable or contract.executable


def _required(value: dict[str, Any], key: str) -> Any:
    result = value.get(key)
    if result is None or result == "":
        raise ValueError(f"Provider issue field is missing: {key}")
    return result


def _nested_string(value: object, key: str) -> str | None:
    if not isinstance(value, dict):
        return None
    child = value.get(key)
    return child if isinstance(child, str) and child else None
