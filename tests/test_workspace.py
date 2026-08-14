from datetime import UTC, datetime
from pathlib import Path

import pytest

from agora.model import (
    AddActorInput,
    AddArtifactInput,
    AddEvidenceInput,
    AssignActorInput,
    ConfigureInput,
    CreateSwarmInput,
    CreateWorkInput,
    InitInput,
    InstallMethodInput,
    TransitionWorkInput,
    WorkActorInput,
)
from agora.workspace import AgoraWorkspace

TIMESTAMP = datetime(2026, 8, 14, 12, tzinfo=UTC)


@pytest.fixture
def project(tmp_path: Path, monkeypatch) -> tuple[Path, AgoraWorkspace]:
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    return root, AgoraWorkspace(cwd=root, now=lambda: TIMESTAMP)


def test_persists_defaults_and_materializes_a_codex_project(
    project: tuple[Path, AgoraWorkspace],
) -> None:
    root, workspace = project
    workspace.configure(
        ConfigureInput(
            integration="codex",
            provider="openai",
            model="configured-by-codex",
            default_method="kanban",
        )
    )

    configuration = workspace.initialize(InitInput())

    assert configuration.integration == "codex"
    assert configuration.default_method == "kanban"
    assert (root / ".agora" / "methods" / "scrum" / "METHOD.md").exists()
    assert (root / ".agora" / "methods" / "kanban" / "METHOD.md").exists()
    assert (root / ".agents" / "skills" / "agora-objective" / "SKILL.md").exists()
    assert 'integration: "codex"' in (root / ".agora" / "project.md").read_text()


def test_supports_filesystem_only_environments(
    project: tuple[Path, AgoraWorkspace],
) -> None:
    _, workspace = project
    workspace.initialize(InitInput(integration="generic"))

    git_check = next(item for item in workspace.doctor() if item.name == "git")
    assert git_check.ok is False
    assert git_check.detail == "filesystem-only mode"


def test_installs_and_uses_a_user_defined_method_pack(
    project: tuple[Path, AgoraWorkspace],
) -> None:
    root, workspace = project
    source = Path(__file__).parents[1] / "samples" / "custom-lifecycle" / "release-flow"

    installed = workspace.install_method(InstallMethodInput(source=str(source), scope="user"))
    workspace.configure(
        ConfigureInput(
            integration="generic",
            provider="any-provider",
            model="any-model",
            default_method="release-flow",
        )
    )
    workspace.initialize(InitInput())
    swarm = workspace.create_swarm(
        CreateSwarmInput(
            id="language-neutral-delivery",
            objective="Ship a change in any technology stack",
            create_branch=False,
        )
    )

    assert installed.id == "release-flow"
    assert installed.scope == "user"
    assert (root / ".agora" / "methods" / "release-flow" / "METHOD.md").exists()
    assert swarm.method == "release-flow"
    assert swarm.required_roles == ["cycle-owner", "maker", "validator"]


def test_governs_human_ai_and_nested_swarm_actors(
    project: tuple[Path, AgoraWorkspace],
) -> None:
    root, workspace = project
    workspace.initialize(InitInput(integration="generic", default_method="scrum"))
    workspace.add_actor(
        AddActorInput(
            id="owner",
            name="Product Owner",
            kind="human",
            capabilities=["backlog-management", "acceptance"],
            scope="user",
        )
    )
    workspace.add_actor(
        AddActorInput(
            id="facilitator",
            name="Facilitator",
            kind="ai-agent",
            capabilities=["facilitation", "governance"],
            scope="project",
        )
    )
    workspace.add_actor(
        AddActorInput(
            id="delivery-swarm",
            name="Delivery Swarm",
            kind="swarm",
            capabilities=["implementation"],
            scope="project",
        )
    )
    workspace.create_swarm(
        CreateSwarmInput(
            id="first-slice",
            objective="Build the Markdown-first slice",
            create_branch=False,
        )
    )
    assert workspace.show_swarm("first-slice").branch == "filesystem-only"
    workspace.assign_actor(
        AssignActorInput(swarm_id="first-slice", role_id="product-owner", actor_id="owner")
    )
    workspace.assign_actor(
        AssignActorInput(swarm_id="first-slice", role_id="scrum-master", actor_id="facilitator")
    )
    with pytest.raises(ValueError, match="lacks capabilities"):
        workspace.assign_actor(
            AssignActorInput(swarm_id="first-slice", role_id="developer", actor_id="owner")
        )
    assert (
        workspace.assign_actor(
            AssignActorInput(swarm_id="first-slice", role_id="developer", actor_id="delivery-swarm")
        ).status
        == "ready"
    )

    workspace.create_work(
        CreateWorkInput(
            swarm_id="first-slice",
            id="bootstrap",
            title="Bootstrap Agora",
            actor_id="owner",
            acceptance_criteria=[("installable", "Agora initializes a project")],
            required_artifacts=["source-code"],
        )
    )
    with pytest.raises(ValueError, match="expected planned"):
        workspace.transition_work(
            TransitionWorkInput(
                swarm_id="first-slice",
                work_id="bootstrap",
                actor_id="delivery-swarm",
                target_state="implementing",
            )
        )
    for state in ("planned", "implementing", "reviewing", "verifying"):
        workspace.transition_work(
            TransitionWorkInput(
                swarm_id="first-slice",
                work_id="bootstrap",
                actor_id="delivery-swarm",
                target_state=state,
            )
        )
    with pytest.raises(ValueError, match="Final gate failed"):
        workspace.transition_work(
            TransitionWorkInput(
                swarm_id="first-slice",
                work_id="bootstrap",
                actor_id="owner",
                target_state="completed",
            )
        )
    with pytest.raises(PermissionError, match="not allowed to perform criterion.satisfy"):
        workspace.satisfy_criterion(
            WorkActorInput(swarm_id="first-slice", work_id="bootstrap", actor_id="delivery-swarm"),
            "installable",
        )

    workspace.satisfy_criterion(
        WorkActorInput(swarm_id="first-slice", work_id="bootstrap", actor_id="owner"),
        "installable",
    )
    workspace.add_artifact(
        AddArtifactInput(
            swarm_id="first-slice",
            work_id="bootstrap",
            actor_id="delivery-swarm",
            kind="source-code",
            uri="repo://src/agora/workspace.py",
        )
    )
    workspace.add_evidence(
        AddEvidenceInput(
            swarm_id="first-slice",
            work_id="bootstrap",
            actor_id="facilitator",
            type="test-run",
            result="success",
            artifact_refs=["repo://src/agora/workspace.py"],
        )
    )
    completed = workspace.transition_work(
        TransitionWorkInput(
            swarm_id="first-slice",
            work_id="bootstrap",
            actor_id="owner",
            target_state="completed",
        )
    )

    assert completed.state == "completed"
    assert workspace.show_swarm("first-slice").status == "completed"
    work_root = root / ".agora" / "swarms" / "first-slice" / "work" / "bootstrap"
    assert "- [x] **installable:**" in (work_root / "WORK.md").read_text()
    assert "work.transitioned" in (work_root / "events.md").read_text()
    assert "| test-run | success |" in (work_root / "evidence.md").read_text()
