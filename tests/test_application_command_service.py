import base64
import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from agora.application import (
    ActorUnauthorizedError,
    AgoraCommandService,
    ApproveGateCommand,
    CommandPersistenceError,
    EvidenceMissingError,
    GateAlreadyResolvedError,
    ProjectIdentityMismatchError,
    SignatureRequiredError,
    StalePreconditionError,
    approve_gate_authorization_payload,
)
from agora.model import (
    AddActorInput,
    AddArtifactInput,
    AddEvidenceInput,
    AssignActorInput,
    CreateSwarmInput,
    CreateWorkInput,
    InitInput,
    TransitionWorkInput,
    WorkActorInput,
)
from agora.workspace import AgoraWorkspace

TIMESTAMP = datetime(2026, 8, 20, 15, tzinfo=UTC)


@pytest.fixture
def gate_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, AgoraWorkspace, AgoraCommandService]:
    root = tmp_path / "governed-project"
    root.mkdir()
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    workspace = AgoraWorkspace(cwd=root, now=lambda: TIMESTAMP)
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
        CreateSwarmInput(id="delivery", objective="Deliver safely", create_branch=False)
    )
    for role, actor in (
        ("product-owner", "owner"),
        ("scrum-master", "facilitator"),
        ("developer", "developer"),
    ):
        workspace.assign_actor(AssignActorInput(swarm_id="delivery", role_id=role, actor_id=actor))
    workspace.create_work(
        CreateWorkInput(
            swarm_id="delivery",
            id="release",
            title="Release safely",
            actor_id="owner",
            acceptance_criteria=[("accepted", "The release is accepted")],
            required_artifacts=["test-report"],
        )
    )
    for state, actor in (
        ("planned", "developer"),
        ("implementing", "developer"),
        ("reviewing", "developer"),
        ("verifying", "facilitator"),
    ):
        workspace.transition_work(
            TransitionWorkInput(
                swarm_id="delivery",
                work_id="release",
                actor_id=actor,
                target_state=state,
            )
        )
    for stage, actor in (
        ("specified", "owner"),
        ("implemented", "developer"),
        ("verified", "facilitator"),
        ("accepted", "owner"),
    ):
        workspace.satisfy_criterion(
            WorkActorInput(swarm_id="delivery", work_id="release", actor_id=actor),
            "accepted",
            stage,
        )
    report = root / "reports" / "release.txt"
    report.parent.mkdir()
    report.write_text("passed\n", encoding="utf-8")
    workspace.add_artifact(
        AddArtifactInput(
            swarm_id="delivery",
            work_id="release",
            actor_id="developer",
            kind="test-report",
            uri="repo://reports/release.txt",
        )
    )
    workspace.add_evidence(
        AddEvidenceInput(
            swarm_id="delivery",
            work_id="release",
            actor_id="developer",
            type="test-run",
            result="success",
            artifact_refs=["repo://reports/release.txt"],
        )
    )
    return root, workspace, AgoraCommandService(workspace)


def command(**changes: object) -> ApproveGateCommand:
    values: dict[str, object] = {
        "project_identity": "governed-project",
        "swarm_id": "delivery",
        "work_id": "release",
        "gate_id": "completion",
        "actor_id": "owner",
        "decision": "approved",
        "reason": "Evidence reviewed and accepted",
        "expected_state": "verifying",
        "evidence_references": ("repo://reports/release.txt",),
    }
    values.update(changes)
    return ApproveGateCommand(**values)  # type: ignore[arg-type]


def test_serializes_the_immutable_versioned_command() -> None:
    value = command(
        authentication={
            "algorithm": "ed25519",
            "fingerprint": "a" * 64,
            "signature": "c2ln",
        }
    )

    payload = json.loads(value.to_json())

    assert payload["schema"] == "agora/application/approve-gate-command/v1"
    assert payload["decision"] == "approved"
    assert payload["evidence_references"] == ["repo://reports/release.txt"]
    assert "path" not in payload
    with pytest.raises(TypeError):
        value.authentication["signature"] = "changed"  # type: ignore[index]


@pytest.mark.parametrize(
    "decision,event_type",
    [("approved", "approval.added"), ("rejected", "gate.rejected")],
)
def test_applies_approval_and_rejection_as_durable_decisions(
    gate_project: tuple[Path, AgoraWorkspace, AgoraCommandService],
    decision: str,
    event_type: str,
) -> None:
    root, workspace, service = gate_project

    result = service.approve_gate(command(decision=decision))

    assert result.decision == decision
    assert result.role_id == "product-owner"
    assert result.lifecycle.current_state == "verifying"
    assert result.activity.type == event_type
    assert result.activity.actor == "project:owner"
    approvals = workspace.show_work("delivery", "release").approval_roles
    assert ("product-owner" in approvals) is (decision == "approved")
    assert event_type in (root / ".agora" / "activity.md").read_text(encoding="utf-8")


def test_rejects_an_actor_without_gate_authority(
    gate_project: tuple[Path, AgoraWorkspace, AgoraCommandService],
) -> None:
    _, _, service = gate_project

    with pytest.raises(ActorUnauthorizedError) as captured:
        service.approve_gate(command(actor_id="developer"))

    assert captured.value.to_dict()["code"] == "command.actor-unauthorized"


def test_rejects_missing_or_unverified_evidence(
    gate_project: tuple[Path, AgoraWorkspace, AgoraCommandService],
) -> None:
    _, _, service = gate_project

    with pytest.raises(EvidenceMissingError) as captured:
        service.approve_gate(command(evidence_references=("repo://reports/missing.txt",)))

    assert captured.value.to_dict()["code"] == "command.evidence-missing"


def test_rejects_a_stale_expected_state(
    gate_project: tuple[Path, AgoraWorkspace, AgoraCommandService],
) -> None:
    _, _, service = gate_project

    with pytest.raises(StalePreconditionError):
        service.approve_gate(command(expected_state="reviewing"))


def test_rejects_a_different_project_identity(
    gate_project: tuple[Path, AgoraWorkspace, AgoraCommandService],
) -> None:
    _, _, service = gate_project

    with pytest.raises(ProjectIdentityMismatchError):
        service.approve_gate(command(project_identity="another-project"))


def test_requires_the_existing_signed_action_flow_for_authenticated_actors(
    gate_project: tuple[Path, AgoraWorkspace, AgoraCommandService],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, workspace, service = gate_project
    find_actor = workspace._find_actor

    def authenticated_actor(root: Path, actor_id: str):
        actor = find_actor(root, actor_id)
        return replace(actor, authentication_required=True)

    monkeypatch.setattr(workspace, "_find_actor", authenticated_actor)

    with pytest.raises(SignatureRequiredError) as captured:
        service.approve_gate(command())

    assert captured.value.to_dict()["code"] == "command.signature-required"


def test_verifies_inline_authentication_against_the_current_actor_key(
    gate_project: tuple[Path, AgoraWorkspace, AgoraCommandService],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, workspace, service = gate_project
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    fingerprint = hashlib.sha256(public_key).hexdigest()
    find_actor = workspace._find_actor

    def authenticated_actor(root: Path, actor_id: str):
        actor = find_actor(root, actor_id)
        if actor.reference != "project:owner":
            return actor
        return replace(
            actor,
            authentication_required=True,
            authentication_algorithm="ed25519",
            authentication_public_key=base64.b64encode(public_key).decode("ascii"),
            authentication_fingerprint=fingerprint,
        )

    monkeypatch.setattr(workspace, "_find_actor", authenticated_actor)
    monkeypatch.setattr(workspace, "_assert_current_actor_key", lambda actor: None)
    unsigned = command()
    signature = base64.b64encode(
        private_key.sign(approve_gate_authorization_payload(unsigned))
    ).decode("ascii")
    signed = command(
        authentication={
            "algorithm": "ed25519",
            "fingerprint": fingerprint,
            "signature": signature,
        }
    )

    result = service.approve_gate(signed)

    assert result.decision == "approved"
    event = workspace.list_events(
        swarm_id="delivery", work_id="release", type_="approval.added", limit=1
    )[0]
    assert f"authentication={fingerprint}" in event.detail


@pytest.mark.parametrize("decision", ["approved", "rejected"])
def test_rejects_double_submission(
    gate_project: tuple[Path, AgoraWorkspace, AgoraCommandService], decision: str
) -> None:
    _, _, service = gate_project
    request = command(decision=decision)
    service.approve_gate(request)

    with pytest.raises(GateAlreadyResolvedError):
        service.approve_gate(request)


def test_maps_an_intermediate_write_failure_and_rolls_back_every_record(
    gate_project: tuple[Path, AgoraWorkspace, AgoraCommandService],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, workspace, service = gate_project
    work_root = root / ".agora" / "swarms" / "delivery" / "work" / "release"
    paths = [work_root / "approvals.md", work_root / "events.md", root / ".agora" / "activity.md"]
    before = {path: path.read_bytes() for path in paths}
    from agora import filesystem

    original = filesystem._atomic_write_direct
    calls = 0

    def fail_second_write(path: Path, contents: str) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected intermediate failure")
        original(path, contents)

    monkeypatch.setattr(filesystem, "_atomic_write_direct", fail_second_write)

    with pytest.raises(CommandPersistenceError) as captured:
        service.approve_gate(command())

    assert captured.value.to_dict()["code"] == "command.persistence-failed"
    assert {path: path.read_bytes() for path in paths} == before
    assert workspace.show_work("delivery", "release").approval_roles == []
