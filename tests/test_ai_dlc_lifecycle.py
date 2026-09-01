import json
import subprocess
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

_ROLES = {
    "product-owner": ("po", "human", ["specification", "acceptance"]),
    "architect": ("arch", "ai-agent", ["specification"]),
    "builder": ("build", "ai-agent", ["implementation"]),
    "operator": ("ops", "ai-agent", ["implementation"]),
    "quality-reviewer": ("qa", "human", ["acceptance"]),
}


def _workspace(tmp_path: Path, monkeypatch) -> AgoraWorkspace:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    docs = tmp_path / "docs"
    docs.mkdir(parents=True)
    for name in ("intent", "units-of-work", "architecture", "domain-model"):
        (docs / f"{name}.md").write_text(f"# {name}\n", encoding="utf-8")

    def run(command, cwd, environment):
        return subprocess.CompletedProcess(command, 0, json.dumps({"questions": []}), "")

    workspace = AgoraWorkspace(cwd=tmp_path, tool_runner=run)
    workspace.configure(
        ConfigureInput(
            integration="generic",
            provider="configured-by-integration",
            model="configured-by-integration",
            default_method="ai-dlc",
        )
    )
    workspace.initialize(InitInput())
    return workspace


def _form_swarm(workspace: AgoraWorkspace) -> None:
    for _role_id, (actor_id, kind, caps) in _ROLES.items():
        workspace.add_actor(
            AddActorInput(id=actor_id, name=actor_id, kind=kind, capabilities=caps, scope="project")
        )
    workspace.create_swarm(CreateSwarmInput(id="delivery", objective="Deliver via AI-DLC"))
    for role_id, (actor_id, _kind, _caps) in _ROLES.items():
        workspace.assign_actor(
            AssignActorInput(swarm_id="delivery", role_id=role_id, actor_id=actor_id)
        )


def _wa(actor_id: str) -> WorkActorInput:
    return WorkActorInput(swarm_id="delivery", work_id="feature", actor_id=actor_id)


def _artifact(workspace: AgoraWorkspace, actor_id: str, kind: str) -> None:
    workspace.add_artifact(
        AddArtifactInput(
            swarm_id="delivery",
            work_id="feature",
            actor_id=actor_id,
            kind=kind,
            uri=f"repo://docs/{kind}.md",
        )
    )


def _approve(workspace: AgoraWorkspace, actor_id: str, role_id: str) -> None:
    workspace.add_approval(
        AddApprovalInput(
            swarm_id="delivery",
            work_id="feature",
            actor_id=actor_id,
            role_id=role_id,
            note="approved",
        )
    )


def _evidence(workspace: AgoraWorkspace, actor_id: str, evidence_type: str) -> None:
    workspace.add_evidence(
        AddEvidenceInput(
            swarm_id="delivery",
            work_id="feature",
            actor_id=actor_id,
            type=evidence_type,
            result="success",
            artifact_refs=["repo://docs/intent.md"],
        )
    )


def _transition(workspace: AgoraWorkspace, actor_id: str, target: str):
    return workspace.transition_work(
        TransitionWorkInput(
            swarm_id="delivery", work_id="feature", actor_id=actor_id, target_state=target
        )
    )


def _seed_work(workspace: AgoraWorkspace) -> None:
    workspace.create_work(
        CreateWorkInput(
            swarm_id="delivery",
            id="feature",
            title="Ship a feature via AI-DLC",
            actor_id="po",
            description="Exercise every phase gate.",
            acceptance_criteria=[("value", "The feature delivers its stated value")],
            required_artifacts=["intent"],
        )
    )


def _drive_to_inception(workspace: AgoraWorkspace) -> None:
    _artifact(workspace, "po", "intent")
    workspace.clarify_work(_wa("po"), runner="/bin/true")
    _transition(workspace, "po", "ideation")

    workspace.satisfy_criterion(_wa("po"), "value", stage="elaborated")
    _artifact(workspace, "po", "units-of-work")
    _approve(workspace, "po", "product-owner")
    _transition(workspace, "po", "inception")


def _drive_to_construction(workspace: AgoraWorkspace) -> None:
    _drive_to_inception(workspace)
    workspace.satisfy_criterion(_wa("arch"), "value", stage="designed")
    _artifact(workspace, "arch", "architecture")
    _artifact(workspace, "arch", "domain-model")
    _approve(workspace, "arch", "architect")
    _approve(workspace, "po", "product-owner")
    _transition(workspace, "arch", "construction")


def _drive_to_operation(workspace: AgoraWorkspace) -> None:
    _drive_to_construction(workspace)
    workspace.satisfy_criterion(_wa("build"), "value", stage="built")
    workspace.satisfy_criterion(_wa("qa"), "value", stage="verified")
    _evidence(workspace, "build", "test-suite")
    _approve(workspace, "qa", "quality-reviewer")
    _transition(workspace, "qa", "operation")


def test_ai_dlc_happy_path_reaches_completed(tmp_path: Path, monkeypatch) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    _form_swarm(workspace)
    _seed_work(workspace)
    _drive_to_operation(workspace)

    workspace.satisfy_criterion(_wa("ops"), "value", stage="deployed")
    workspace.satisfy_criterion(_wa("po"), "value", stage="accepted")
    _evidence(workspace, "ops", "deployment")
    _approve(workspace, "po", "product-owner")

    completed = _transition(workspace, "po", "completed")
    assert completed.state == "completed"


def test_ai_dlc_rework_operation_back_to_construction(tmp_path: Path, monkeypatch) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    _form_swarm(workspace)
    _seed_work(workspace)
    _drive_to_operation(workspace)

    reworked = _transition(workspace, "qa", "construction")
    assert reworked.state == "construction"

    forward = _transition(workspace, "qa", "operation")
    assert forward.state == "operation"


def test_ai_dlc_rework_construction_back_to_inception(tmp_path: Path, monkeypatch) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    _form_swarm(workspace)
    _seed_work(workspace)
    _drive_to_construction(workspace)

    reworked = _transition(workspace, "arch", "inception")
    assert reworked.state == "inception"


def test_ai_dlc_build_gate_blocks_without_verified_evidence(tmp_path: Path, monkeypatch) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    _form_swarm(workspace)
    _seed_work(workspace)
    _drive_to_construction(workspace)

    with pytest.raises(ValueError):
        _transition(workspace, "qa", "operation")
