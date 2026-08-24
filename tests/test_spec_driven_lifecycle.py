from pathlib import Path

import pytest

from agora.model import (
    AddActorInput,
    AddApprovalInput,
    AddArtifactInput,
    AddEvidenceInput,
    AssignActorInput,
    ConfigureInput,
    CreatePatchWorkInput,
    CreateSwarmInput,
    CreateWorkInput,
    InitInput,
    TransitionWorkInput,
    WorkActorInput,
)
from agora.workspace import AgoraWorkspace


def _workspace(tmp_path: Path, monkeypatch) -> AgoraWorkspace:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    specification = tmp_path / "docs" / "specs" / "increment.md"
    specification.parent.mkdir(parents=True)
    specification.write_text("# Increment specification\n", encoding="utf-8")
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


def test_spec_clarification_defers_later_required_artifacts(tmp_path: Path, monkeypatch) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    _form_swarm(workspace)
    workspace.create_work(
        CreateWorkInput(
            swarm_id="delivery",
            id="increment",
            title="Add lifecycle visualization",
            actor_id="owner",
            acceptance_criteria=[("graph", "The lifecycle is visible")],
            required_artifacts=["spec", "implementation-plan", "verification-report"],
        )
    )
    workspace.satisfy_criterion(
        WorkActorInput(swarm_id="delivery", work_id="increment", actor_id="owner"),
        criterion_id="graph",
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
    assert clarified.artifact_kinds == ["spec"]


def test_spec_driven_tracks_criterion_progress_without_transferring_acceptance(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    _form_swarm(workspace)
    workspace.create_work(
        CreateWorkInput(
            swarm_id="delivery",
            id="increment",
            title="Track phased acceptance",
            actor_id="owner",
            acceptance_criteria=[("observable", "The behavior is observable")],
            required_artifacts=["spec"],
        )
    )

    specified = workspace.satisfy_criterion(
        WorkActorInput(swarm_id="delivery", work_id="increment", actor_id="owner"),
        criterion_id="observable",
        stage="specified",
    )
    assert specified.criterion_statuses == {"observable": ["specified"]}
    assert specified.satisfied_criteria == []

    with pytest.raises(ValueError, match="cannot reach verified before: implemented"):
        workspace.satisfy_criterion(
            WorkActorInput(swarm_id="delivery", work_id="increment", actor_id="owner"),
            criterion_id="observable",
            stage="verified",
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


def _walk_increment_to_completion(workspace: AgoraWorkspace) -> None:
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


def test_spec_driven_walks_to_completion_with_evidence_and_approval(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    _form_swarm(workspace)
    _walk_increment_to_completion(workspace)


def test_patch_work_reuses_a_completed_swarm_without_new_ceremony(
    tmp_path: Path, monkeypatch
) -> None:
    """A lightweight fix work item can be created directly against a swarm
    that already reached 'completed', without creating a new swarm, role
    assignment, or branch — the pattern this session repeated ~4 times by
    hand before this feature existed."""
    workspace = _workspace(tmp_path, monkeypatch)
    _form_swarm(workspace)
    _walk_increment_to_completion(workspace)
    assert workspace.show_swarm("delivery").status == "completed"

    patch = workspace.create_patch_work(
        CreatePatchWorkInput(
            swarm_id="delivery",
            parent_work_id="increment",
            id="increment-fix",
            title="Fix a bug found testing the shipped increment",
            actor_id="dev",
            description="The retry path double-charges under a specific race.",
            acceptance_criteria=[("no-double-charge", "Retries never double-charge")],
        )
    )

    assert patch.state == "drafting"
    assert patch.parent_work_ref == "delivery/increment"
    # No new swarm was created — same roles, same branch, same swarm id.
    assert patch.swarm_id == "delivery"
    assert workspace.show_swarm("delivery").assignments == {
        "spec-owner": "project:owner",
        "developer": "project:dev",
    }

    # The swarm's status self-healed back to running now that a non-terminal
    # work item exists (status is derived from work items, not set by hand).
    assert workspace.show_swarm("delivery").status == "running"

    parent = workspace.show_work("delivery", "increment")
    assert "delivery/increment-fix" in parent.child_work_refs

    assert workspace.validate().ok is True
