import json
import subprocess
from pathlib import Path

import pytest

from agora.tracker_adapters import GitHubIssueTrackerAdapter, JiraIssueTrackerAdapter


class _Runner:
    def __init__(self, payload: dict[str, object], *, provider: str) -> None:
        self.payload = payload
        self.provider = provider
        self.commands: list[list[str]] = []

    def __call__(self, command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        assert cwd.is_absolute()
        self.commands.append(command)
        if command[-1] == "--version":
            version = "gh version 2.45.1" if self.provider == "github" else "acli version 1.3.15"
            return subprocess.CompletedProcess(command, 0, version, "")
        return subprocess.CompletedProcess(command, 0, json.dumps(self.payload), "")


def test_github_adapter_uses_reviewed_cli_and_normalizes_identity(tmp_path: Path) -> None:
    runner = _Runner(
        {
            "number": 42,
            "title": "Production failure",
            "state": "OPEN",
            "stateReason": None,
            "url": "https://github.example/owner/repo/issues/42",
            "updatedAt": "2026-08-30T12:00:00Z",
            "author": {"login": "adrian", "name": "Adrian"},
            "labels": [{"name": "bug"}],
            "milestone": {"title": "v2"},
            "comments": [{"id": "one"}],
        },
        provider="github",
    )

    snapshot = GitHubIssueTrackerAdapter(tmp_path, runner).fetch("owner/repo", ["42"])[0]

    assert runner.commands[0] == ["gh", "--version"]
    assert runner.commands[1][:4] == ["gh", "issue", "view", "42"]
    assert snapshot.tracker == "github"
    assert snapshot.state == "open"
    assert snapshot.author_subject == "adrian"
    assert snapshot.author_display_name == "Adrian"
    assert snapshot.labels == ["bug"]
    assert len(snapshot.payload_sha256) == 64


def test_jira_adapter_uses_same_snapshot_contract(tmp_path: Path) -> None:
    runner = _Runner(
        {
            "key": "MAITRE-42",
            "self": "https://jira.example/rest/api/3/issue/MAITRE-42",
            "fields": {
                "key": "MAITRE-42",
                "summary": "Production failure",
                "status": {"name": "Done"},
                "reporter": {"accountId": "subject-1", "displayName": "Adrian"},
                "labels": ["bug"],
                "updated": "2026-08-30T12:00:00Z",
                "comment": {"total": 1, "comments": [{"id": "one"}]},
            },
        },
        provider="jira",
    )

    snapshot = JiraIssueTrackerAdapter(tmp_path, runner).fetch("MAITRE", ["MAITRE-42"])[0]

    assert runner.commands[0] == ["acli", "--version"]
    assert runner.commands[1][:5] == ["acli", "jira", "workitem", "view", "MAITRE-42"]
    assert snapshot.tracker == "jira"
    assert snapshot.state == "closed"
    assert snapshot.author_subject == "subject-1"
    assert snapshot.author_display_name == "Adrian"
    assert snapshot.comment_count == 1


def test_provider_failure_does_not_expose_stderr(tmp_path: Path) -> None:
    def runner(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        if command[-1] == "--version":
            return subprocess.CompletedProcess(command, 0, "gh version 2.45.1", "")
        return subprocess.CompletedProcess(command, 1, "", "token=super-secret")

    with pytest.raises(RuntimeError, match="provider output was not exposed") as captured:
        GitHubIssueTrackerAdapter(tmp_path, runner).fetch("owner/repo", ["42"])

    assert "super-secret" not in str(captured.value)


def test_adapter_rejects_runtime_below_reviewed_minimum(tmp_path: Path) -> None:
    def runner(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, "gh version 2.44.0", "")

    with pytest.raises(RuntimeError, match="not verifiably compatible"):
        GitHubIssueTrackerAdapter(tmp_path, runner).fetch("owner/repo", ["42"])
