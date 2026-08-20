"""Explicitly opt-in Jira Cloud smoke; never runs in the normal offline suite."""

import json
import os
import shutil
import uuid
from collections.abc import Callable
from pathlib import Path

import pytest

from agora.model import (
    AddActorInput,
    AssignActorInput,
    CreateSwarmInput,
    CreateWorkInput,
    InitInput,
    InstallToolAdapterInput,
    InvokeToolInput,
    LaunchToolRunInput,
)
from agora.workspace import AgoraWorkspace

RUN_LIVE = os.environ.get("AGORA_RUN_JIRA_LIVE") == "1"
PROJECT = os.environ.get("AGORA_JIRA_LIVE_PROJECT")
NONPRODUCTION = os.environ.get("AGORA_JIRA_LIVE_CONFIRMED_NONPRODUCTION") == "1"

pytestmark = pytest.mark.skipif(
    not RUN_LIVE or not PROJECT or not NONPRODUCTION or shutil.which("acli") is None,
    reason=(
        "Set AGORA_RUN_JIRA_LIVE=1, AGORA_JIRA_LIVE_PROJECT, and "
        "AGORA_JIRA_LIVE_CONFIRMED_NONPRODUCTION=1 with authenticated ACLI"
    ),
)


def test_live_jira_create_is_prepared_bounded_and_reports_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    record_property: Callable[[str, object], None],
) -> None:
    assert PROJECT is not None
    run_suffix = uuid.uuid4().hex[:12]
    root = tmp_path / "jira-live-smoke"
    root.mkdir()
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    workspace = AgoraWorkspace(cwd=root)
    workspace.initialize(InitInput(integration="generic", default_method="scrum"))
    workspace.install_tool_adapter(InstallToolAdapterInput(adapter_id="jira", scope="project"))
    for actor in (
        AddActorInput(
            id="owner",
            name="Jira Smoke Owner",
            kind="human",
            capabilities=["backlog-management", "acceptance"],
            scope="project",
        ),
        AddActorInput(
            id="facilitator",
            name="Jira Smoke Facilitator",
            kind="human",
            capabilities=["facilitation", "governance"],
            scope="project",
        ),
        AddActorInput(
            id="developer",
            name="Jira Smoke Developer",
            kind="human",
            capabilities=["implementation"],
            scope="project",
        ),
    ):
        workspace.add_actor(actor)
    workspace.create_swarm(
        CreateSwarmInput(id="jira-smoke", objective="Exercise Jira safely", create_branch=False)
    )
    for role, actor_id in (
        ("product-owner", "owner"),
        ("scrum-master", "facilitator"),
        ("developer", "developer"),
    ):
        workspace.assign_actor(
            AssignActorInput(swarm_id="jira-smoke", role_id=role, actor_id=actor_id)
        )
    workspace.create_work(
        CreateWorkInput(
            swarm_id="jira-smoke",
            id="live-smoke",
            title="Run an explicitly authorized Jira smoke",
            actor_id="owner",
        )
    )
    prepared = workspace.invoke_tool(
        InvokeToolInput(
            id=f"jira-create-{run_suffix}",
            tool_id="jira",
            operation_id="create",
            actor_id="owner",
            swarm_id="jira-smoke",
            work_id="live-smoke",
            inputs={
                "project": PROJECT,
                "type": os.environ.get("AGORA_JIRA_LIVE_ISSUE_TYPE", "Task"),
                "title": f"Agora Core live smoke {run_suffix}",
                "description": (
                    "Opt-in Agora Core smoke. Safe to archive after verification. "
                    f"Correlation: {run_suffix}."
                ),
            },
            launch=False,
        )
    )
    assert prepared.status == "prepared"

    completed = workspace.launch_tool_run(LaunchToolRunInput(run_id=prepared.id))

    assert completed.status == "completed"
    assert completed.result is not None
    payload = json.loads(completed.result.stdout)
    issue_key = payload["key"]
    cleanup = f"Archive Jira issue {issue_key}; Core intentionally did not delete it."
    record_property("jira_cleanup", cleanup)
    print(cleanup)
