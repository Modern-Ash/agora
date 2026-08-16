from pathlib import Path

import pytest

from agora.model import (
    AddActorInput,
    AddApprovalInput,
    AddArtifactInput,
    AddEvidenceInput,
    AssignActorInput,
    ConfigureInput,
    CreateSwarmInput,
    CreateWorkInput,
    InitInput,
    TransitionWorkInput,
    WorkActorInput,
)
from agora.workspace import AgoraWorkspace


def _workspace(tmp_path: Path, monkeypatch) -> AgoraWorkspace:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    workspace = AgoraWorkspace(cwd=tmp_path)
    workspace.configure(
        ConfigureInput(
            integration="generic",
            provider="configured-by-integration",
            model="configured-by-integration",
            default_method="spec-driven",
        )
    )
    workspace.initialize(InitInput())
    return workspace


def _form_swarm(workspace: AgoraWorkspace) -> None:
    workspace.add_actor(
        AddActorInput(
            id="owner",
            name="Owner",
            kind="human",
            capabilities=["specification", "acceptance"],
            scope="project",
        )
    )
    workspace.add_actor(
        AddActorInput(
            id="dev",
            name="Developer",
            kind="ai-agent",
            capabilities=["implementation"],
            scope="project",
        )
    )
    workspace.create_swarm(CreateSwarmInput(id="delivery", objective="Ship the increment"))
    workspace.assign_actor(
        AssignActorInput(swarm_id="delivery", role_id="spec-owner", actor_id="owner")
    )
    workspace.assign_actor(
        AssignActorInput(swarm_id="delivery", role_id="developer", actor_id="dev")
    )


def test_spec_driven_blocks_clarification_until_criteria_and_spec_artifact_exist(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    _form_swarm(workspace)

    work = workspace.create_work(
        CreateWorkInput(
            swarm_id="delivery",
            id="increment",
            title="Add idempotency",
            actor_id="owner",
            description="Requests must be safe to retry.",
            acceptance_criteria=[("idempotent", "Retried requests do not duplicate effects")],
            required_artifacts=["spec"],
        )
    )
    assert work.state == "drafting"

    with pytest.raises(ValueError):
        workspace.transition_work(
            TransitionWorkInput(
                swarm_id="delivery", work_id="increment", actor_id="owner", target_state="clarified"
            )
        )

    workspace.satisfy_criterion(
        WorkActorInput(swarm_id="delivery", work_id="increment", actor_id="owner"),
        criterion_id="idempotent",
    )
    with pytest.raises(ValueError):
        workspace.transition_work(
            TransitionWorkInput(
                swarm_id="delivery", work_id="increment", actor_id="owner", target_state="clarified"
            )
        )

    workspace.add_artifact(
        AddArtifactInput(
            swarm_id="delivery",
            work_id="increment",
            actor_id="owner",
            kind="spec",
            uri="repo://docs/specs/increment.md",
        )
    )
    clarified = workspace.transition_work(
        TransitionWorkInput(
            swarm_id="delivery", work_id="increment", actor_id="owner", target_state="clarified"
        )
    )
    assert clarified.state == "clarified"


def test_spec_driven_walks_to_completion_with_evidence_and_approval(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    _form_swarm(workspace)

    workspace.create_work(
        CreateWorkInput(
            swarm_id="delivery",
            id="increment",
            title="Add idempotency",
            actor_id="owner",
            description="Requests must be safe to retry.",
            acceptance_criteria=[("idempotent", "Retried requests do not duplicate effects")],
            required_artifacts=["spec"],
        )
    )
    workspace.satisfy_criterion(
        WorkActorInput(swarm_id="delivery", work_id="increment", actor_id="owner"),
        criterion_id="idempotent",
    )
    workspace.add_artifact(
        AddArtifactInput(
            swarm_id="delivery",
            work_id="increment",
            actor_id="owner",
            kind="spec",
            uri="repo://docs/specs/increment.md",
        )
    )
    workspace.transition_work(
        TransitionWorkInput(
            swarm_id="delivery", work_id="increment", actor_id="owner", target_state="clarified"
        )
    )
    workspace.transition_work(
        TransitionWorkInput(
            swarm_id="delivery", work_id="increment", actor_id="dev", target_state="planned"
        )
    )
    workspace.transition_work(
        TransitionWorkInput(
            swarm_id="delivery", work_id="increment", actor_id="dev", target_state="implementing"
        )
    )
    workspace.transition_work(
        TransitionWorkInput(
            swarm_id="delivery", work_id="increment", actor_id="dev", target_state="verifying"
        )
    )
    workspace.add_artifact(
        AddArtifactInput(
            swarm_id="delivery",
            work_id="increment",
            actor_id="dev",
            kind="test-report",
            uri="ci://builds/1/tests",
        )
    )
    workspace.add_evidence(
        AddEvidenceInput(
            swarm_id="delivery",
            work_id="increment",
            actor_id="dev",
            type="test-run",
            result="success",
            artifact_refs=["ci://builds/1/tests"],
        )
    )
    workspace.add_approval(
        AddApprovalInput(
            swarm_id="delivery", work_id="increment", actor_id="owner", role_id="spec-owner"
        )
    )
    completed = workspace.transition_work(
        TransitionWorkInput(
            swarm_id="delivery", work_id="increment", actor_id="owner", target_state="completed"
        )
    )
    assert completed.state == "completed"
    assert workspace.validate().ok is True
