from pathlib import Path

import pytest

from agora.model import (
    AddActorInput,
    AssignActorInput,
    CreateSwarmInput,
    InitInput,
    InstallToolAdapterInput,
    InvokeToolInput,
)
from agora.workspace import AgoraWorkspace


def _workspace(tmp_path: Path, monkeypatch) -> AgoraWorkspace:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    workspace = AgoraWorkspace(cwd=tmp_path)
    workspace.initialize(InitInput(integration="generic", default_method="scrum"))
    for actor in (
        AddActorInput(
            id="owner",
            name="Owner",
            kind="human",
            capabilities=["backlog-management", "acceptance"],
            scope="project",
        ),
        AddActorInput(
            id="facilitator",
            name="Facilitator",
            kind="ai-agent",
            capabilities=["facilitation", "governance"],
            scope="project",
        ),
        AddActorInput(
            id="developer",
            name="Developer",
            kind="ai-agent",
            capabilities=["implementation"],
            scope="project",
        ),
    ):
        workspace.add_actor(actor)
    workspace.create_swarm(
        CreateSwarmInput(id="delivery", objective="Review the increment", create_branch=False)
    )
    for role, actor in (
        ("product-owner", "owner"),
        ("scrum-master", "facilitator"),
        ("developer", "developer"),
    ):
        workspace.assign_actor(AssignActorInput(swarm_id="delivery", role_id=role, actor_id=actor))
    return workspace


def test_governs_github_pull_requests_without_granting_merge(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "agora.workspace.shutil.which",
        lambda executable: "/usr/bin/gh" if executable == "gh" else None,
    )
    workspace = _workspace(tmp_path, monkeypatch)

    installed = workspace.install_tool_adapter(
        InstallToolAdapterInput(adapter_id="github-pull-requests", scope="project")
    )
    created = workspace.invoke_tool(
        InvokeToolInput(
            id="create-review",
            tool_id="github-pull-requests",
            operation_id="create",
            actor_id="developer",
            swarm_id="delivery",
            inputs={
                "project": "example/agora",
                "base": "main",
                "head": "agora/delivery",
                "title": "feat(runtime): execute governed work",
                "description": "Adds the local operational loop.",
            },
        )
    )
    approved = workspace.invoke_tool(
        InvokeToolInput(
            id="approve-review",
            tool_id="github-pull-requests",
            operation_id="approve",
            actor_id="owner",
            swarm_id="delivery",
            inputs={"review": "42", "body": "Accepted after governed verification."},
        )
    )
    checks = workspace.invoke_tool(
        InvokeToolInput(
            id="review-checks",
            tool_id="github-pull-requests",
            operation_id="checks",
            actor_id="developer",
            swarm_id="delivery",
            inputs={"review": "42"},
        )
    )

    assert installed.implements == "code-review"
    assert created.command[:5] == ["gh", "pr", "create", "--repo", "example/agora"]
    assert approved.command[:5] == ["gh", "pr", "review", "42", "--approve"]
    assert checks.command == [
        "gh",
        "pr",
        "checks",
        "42",
        "--json",
        "name,state,link,bucket",
    ]
    with pytest.raises(PermissionError, match="review.merge"):
        workspace.invoke_tool(
            InvokeToolInput(
                id="unauthorized-merge",
                tool_id="github-pull-requests",
                operation_id="merge",
                actor_id="owner",
                swarm_id="delivery",
                inputs={"review": "42", "method": "squash"},
            )
        )
    assert workspace.validate().ok
