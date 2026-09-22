import subprocess
from pathlib import Path

import pytest

from agora.application import AgoraReadService
from agora.model import (
    AddActorInput,
    AssignActorInput,
    CreateSwarmInput,
    CreateWorkInput,
    InitInput,
)
from agora.workspace import AgoraWorkspace


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _workspace(tmp_path: Path, monkeypatch) -> AgoraWorkspace:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    _git(tmp_path, "init", "-b", "main")
    _git(tmp_path, "config", "user.email", "agora@example.test")
    _git(tmp_path, "config", "user.name", "Agora Test")
    (tmp_path / "README.md").write_text("# test\n", encoding="utf-8")
    _git(tmp_path, "add", "README.md")
    _git(tmp_path, "commit", "-m", "initial")

    workspace = AgoraWorkspace(cwd=tmp_path)
    workspace.initialize(InitInput(integration="generic", default_method="scrum"))
    for actor in (
        AddActorInput("owner", "Owner", "human", ["backlog-management", "acceptance"], "project"),
        AddActorInput("facilitator", "Facilitator", "human", ["facilitation", "governance"], "project"),
        AddActorInput("developer", "Developer", "human", ["implementation"], "project"),
    ):
        workspace.add_actor(actor)
    workspace.create_swarm(
        CreateSwarmInput(
            id="delivery",
            objective="Deliver isolated work",
            method="scrum",
            create_branch=False,
        )
    )
    for role, actor in (
        ("product-owner", "owner"),
        ("scrum-master", "facilitator"),
        ("developer", "developer"),
    ):
        workspace.assign_actor(AssignActorInput("delivery", role, actor))

    _git(tmp_path, "add", ".agora")
    _git(tmp_path, "commit", "-m", "bootstrap agora")
    return workspace


def test_create_work_can_own_isolated_branch_and_expose_it(tmp_path: Path, monkeypatch) -> None:
    workspace = _workspace(tmp_path, monkeypatch)

    work = workspace.create_work(
        CreateWorkInput(
            swarm_id="delivery",
            id="issue-42",
            title="Implement issue 42",
            actor_id="owner",
            base_branch="main",
            branch="ai-sdlc/issue-42-implement",
            create_branch=True,
        )
    )

    assert work.base_branch == "main"
    assert work.branch == "ai-sdlc/issue-42-implement"
    assert _git(tmp_path, "branch", "--show-current") == "ai-sdlc/issue-42-implement"

    reloaded = workspace.show_work("delivery", "issue-42")
    assert reloaded.base_branch == "main"
    assert reloaded.branch == "ai-sdlc/issue-42-implement"

    projected = AgoraReadService(workspace).get_work_item("delivery", "issue-42")
    assert projected.base_branch == "main"
    assert projected.branch == "ai-sdlc/issue-42-implement"


def test_create_work_branch_fails_closed_on_dirty_tree(tmp_path: Path, monkeypatch) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    (tmp_path / "README.md").write_text("# dirty\n", encoding="utf-8")

    with pytest.raises(ValueError, match="clean working tree"):
        workspace.create_work(
            CreateWorkInput(
                swarm_id="delivery",
                id="issue-43",
                title="Implement issue 43",
                actor_id="owner",
                base_branch="main",
                branch="ai-sdlc/issue-43-implement",
                create_branch=True,
            )
        )

    assert _git(tmp_path, "branch", "--show-current") == "main"
