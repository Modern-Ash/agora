import hashlib
import json
import subprocess
from io import StringIO
from pathlib import Path

import pytest

from conftest import swarm_dir
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from agora.cli import main as cli_main
from agora.filesystem import FilesystemTransactionFailure
from agora.model import (
    AddActorInput,
    AddApprovalInput,
    AddArtifactInput,
    AddEnvironmentInput,
    AddEvidenceInput,
    AddUsageInput,
    ApplyLifecycleActionInput,
    AssignActorInput,
    ChangeDelegationStatusInput,
    ChangeWorkStatusInput,
    CreateDelegationInput,
    CreateSwarmInput,
    CreateWorkInput,
    DecomposeWorkInput,
    DelegateApprovalInput,
    DelegationActorInput,
    HandoffActorInput,
    InitInput,
    InvokeToolInput,
    LaunchSessionInput,
    LaunchToolRunInput,
    PrepareActorAssignmentInput,
    PrepareActorKeyRecoveryInput,
    PrepareActorKeyRevocationInput,
    PrepareActorKeyRotationInput,
    PrepareActorRuntimeInput,
    PrepareApprovalDelegationInput,
    PrepareApprovalInput,
    PrepareArtifactInput,
    PrepareCreateDelegationInput,
    PrepareCreateWorkInput,
    PrepareCriterionInput,
    PrepareDecomposeWorkInput,
    PrepareDelegationActionInput,
    PrepareEvidenceInput,
    PrepareGateWaiverInput,
    PrepareLifecycleAuthorizationInput,
    PrepareSessionAuthorizationInput,
    PrepareSessionInput,
    PrepareToolAuthorizationInput,
    PrepareUsageInput,
    PrepareWorkTransitionInput,
    RevokeActorKeyInput,
    RevokeApprovalDelegationInput,
    RotateActorKeyInput,
    SetActorRuntimeInput,
    StartSessionInput,
    TransitionWorkInput,
    WaiveGateInput,
    WorkActorInput,
)
from agora.workspace import AgoraWorkspace


def _write_public_key(private_key: Ed25519PrivateKey, path: Path) -> Path:
    path.write_bytes(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    return path


def _authenticated_project(
    tmp_path: Path, monkeypatch
) -> tuple[Path, AgoraWorkspace, Ed25519PrivateKey, list[list[str]]]:
    root = tmp_path / "project"
    root.mkdir()
    for relative in ("delivery/signed-materials.md", "signed-specialists/result.md"):
        artifact = root / relative
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text("verified signed fixture\n", encoding="utf-8")
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(
        "agora.workspace.shutil.which",
        lambda executable: f"/usr/bin/{executable}",
    )
    calls: list[list[str]] = []

    def run_tool(
        command: list[str], cwd: Path, environment: dict[str, str]
    ) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="clean", stderr="")

    private_key = Ed25519PrivateKey.generate()
    workspace = AgoraWorkspace(cwd=root, tool_runner=run_tool)
    workspace.initialize(InitInput(integration="generic", default_method="scrum"))
    for actor in (
        AddActorInput(
            id="owner",
            name="Product Owner",
            kind="human",
            capabilities=["backlog-management", "acceptance"],
            scope="project",
            public_key=str(tmp_path / "developer.pem"),
            require_authentication=True,
        ),
        AddActorInput(
            id="facilitator",
            name="Scrum Master",
            kind="ai-agent",
            capabilities=["facilitation", "governance"],
            scope="project",
            public_key=str(tmp_path / "developer.pem"),
            require_authentication=True,
        ),
        AddActorInput(
            id="developer",
            name="Authenticated Developer",
            kind="ai-agent",
            capabilities=["implementation"],
            scope="project",
            public_key=str(_write_public_key(private_key, tmp_path / "developer.pem")),
            require_authentication=True,
        ),
    ):
        workspace.add_actor(actor)
    workspace.create_swarm(
        CreateSwarmInput(id="delivery", objective="Ship signed work", create_branch=False)
    )
    for role, actor_id in (
        ("product-owner", "owner"),
        ("scrum-master", "facilitator"),
        ("developer", "developer"),
    ):
        workspace.assign_actor(
            AssignActorInput(swarm_id="delivery", role_id=role, actor_id=actor_id)
        )
    return root, workspace, private_key, calls


def _create_authenticated_work(
    workspace: AgoraWorkspace,
    private_key: Ed25519PrivateKey,
    output_root: Path,
    data: CreateWorkInput | None = None,
    action_id: str = "create-signed-work",
) -> None:
    work = data or CreateWorkInput(
        swarm_id="delivery",
        id="signed-work",
        title="Apply a signed lifecycle mutation",
        actor_id="owner",
    )
    workspace.prepare_create_work(PrepareCreateWorkInput(action_id=action_id, work=work))
    payload = output_root / f"{action_id}.json"
    workspace.prepare_lifecycle_authorization(
        PrepareLifecycleAuthorizationInput(action_id=action_id, output=str(payload))
    )
    signature = output_root / f"{action_id}.sig"
    signature.write_bytes(private_key.sign(payload.read_bytes()))
    workspace.apply_lifecycle_action(
        ApplyLifecycleActionInput(action_id=action_id, signature=str(signature))
    )


def test_applies_a_signed_work_transition_as_a_durable_lifecycle_action(
    tmp_path: Path, monkeypatch
) -> None:
    root, workspace, private_key, _ = _authenticated_project(tmp_path, monkeypatch)
    _create_authenticated_work(workspace, private_key, tmp_path)
    transition = TransitionWorkInput(
        swarm_id="delivery",
        work_id="signed-work",
        actor_id="developer",
        target_state="planned",
    )

    with pytest.raises(PermissionError, match="requires a signed lifecycle action"):
        workspace.transition_work(transition)

    prepared = workspace.prepare_work_transition(
        PrepareWorkTransitionInput(id="plan-signed-work", **transition.__dict__)
    )
    payload_path = tmp_path / "lifecycle-authorization.json"
    authorization = workspace.prepare_lifecycle_authorization(
        PrepareLifecycleAuthorizationInput(
            action_id=prepared.id,
            output=str(payload_path),
        )
    )
    payload = json.loads(payload_path.read_text(encoding="ascii"))
    assert payload["schema"] == "agora/lifecycle-authorization/v1"
    assert payload["kind"] == "work.transition"
    assert payload["parameters"] == {"to": "planned"}
    assert payload["precondition-sha256"] == prepared.precondition_sha256
    signature_path = tmp_path / "lifecycle-authorization.sig"
    signature_path.write_bytes(private_key.sign(payload_path.read_bytes()))

    applied = workspace.apply_lifecycle_action(
        ApplyLifecycleActionInput(action_id=prepared.id, signature=str(signature_path))
    )

    assert applied.status == "applied"
    assert applied.authentication_verified is True
    assert applied.authentication_fingerprint == authorization.fingerprint
    assert workspace.show_work("delivery", "signed-work").state == "planned"
    assert workspace.list_lifecycle_actions("applied")[-1] == applied
    action_path = root / ".agora" / "actions" / prepared.id / "ACTION.md"
    assert action_path.is_file()
    assert workspace.validate().ok

    assert applied.authorization_signature is not None
    replacement = (
        "A" if applied.authorization_signature[0] != "A" else "B"
    ) + applied.authorization_signature[1:]
    action_path.write_text(
        action_path.read_text(encoding="utf-8").replace(
            applied.authorization_signature,
            replacement,
        ),
        encoding="utf-8",
    )
    report = workspace.validate()
    assert not report.ok
    assert any(issue.code == "lifecycle-action.invalid" for issue in report.issues)


@pytest.mark.parametrize("fail_at", [1, 2, 3, 4, 5])
def test_signed_lifecycle_apply_rolls_back_domain_event_activity_and_action(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fail_at: int,
) -> None:
    root, workspace, private_key, _ = _authenticated_project(tmp_path, monkeypatch)
    _create_authenticated_work(workspace, private_key, tmp_path)
    transition = TransitionWorkInput(
        swarm_id="delivery",
        work_id="signed-work",
        actor_id="developer",
        target_state="planned",
    )
    action = workspace.prepare_work_transition(
        PrepareWorkTransitionInput(id="atomic-signed-transition", **transition.__dict__)
    )
    payload = tmp_path / "atomic-signed-transition.json"
    workspace.prepare_lifecycle_authorization(
        PrepareLifecycleAuthorizationInput(action_id=action.id, output=str(payload))
    )
    signature = tmp_path / "atomic-signed-transition.sig"
    signature.write_bytes(private_key.sign(payload.read_bytes()))
    work_root = swarm_dir(root, "delivery") / "work" / "signed-work"
    action_path = root / ".agora" / "actions" / action.id / "ACTION.md"
    tracked = [
        work_root / "WORK.md",
        work_root / "events.md",
        root / ".agora" / "events.md",
        root / ".agora" / "activity.md",
        action_path,
    ]
    before = {path: path.read_bytes() for path in tracked}
    from agora import filesystem

    original = filesystem._atomic_write_direct
    writes = 0

    def fail_selected(path: Path, contents: str) -> None:
        nonlocal writes
        writes += 1
        if writes == fail_at:
            raise OSError(f"signed lifecycle failure {fail_at}")
        original(path, contents)

    monkeypatch.setattr(filesystem, "_atomic_write_direct", fail_selected)

    with pytest.raises(FilesystemTransactionFailure):
        workspace.apply_lifecycle_action(
            ApplyLifecycleActionInput(action_id=action.id, signature=str(signature))
        )

    assert {path: path.read_bytes() for path in tracked} == before
    assert workspace.show_work("delivery", "signed-work").state == "specified"
    assert workspace.list_lifecycle_actions("prepared")[-1].id == action.id
    monkeypatch.setattr(filesystem, "_atomic_write_direct", original)
    assert (
        workspace.apply_lifecycle_action(
            ApplyLifecycleActionInput(action_id=action.id, signature=str(signature))
        ).status
        == "applied"
    )


@pytest.mark.parametrize("fail_at", [1, 2, 3, 4, 5, 6])
def test_signed_actor_key_rotation_rolls_back_identity_history_event_and_activity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fail_at: int,
) -> None:
    root, workspace, private_key, _ = _authenticated_project(tmp_path, monkeypatch)
    replacement_key = Ed25519PrivateKey.generate()
    replacement_path = _write_public_key(replacement_key, tmp_path / "replacement.pem")
    rotation = RotateActorKeyInput(
        actor_id="developer",
        public_key=str(replacement_path),
        reason="Rotate the developer identity before release",
    )
    action = workspace.prepare_actor_key_rotation(
        PrepareActorKeyRotationInput(
            action_id="atomic-key-rotation",
            swarm_id="delivery",
            rotation=rotation,
        )
    )
    payload = tmp_path / "atomic-key-rotation.json"
    workspace.prepare_lifecycle_authorization(
        PrepareLifecycleAuthorizationInput(action_id=action.id, output=str(payload))
    )
    signature = tmp_path / "atomic-key-rotation.sig"
    signature.write_bytes(private_key.sign(payload.read_bytes()))
    actor = next(item for item in workspace.list_actors() if item.id == "developer")
    assert actor.authentication_fingerprint is not None
    key_root = Path(actor.path).with_suffix("") / "keys"
    current_key = key_root / f"{actor.authentication_fingerprint}.md"
    replacement_fingerprint = action.parameters["fingerprint"]
    replacement_record = key_root / f"{replacement_fingerprint}.md"
    action_path = root / ".agora" / "actions" / action.id / "ACTION.md"
    tracked = [
        Path(actor.path),
        current_key,
        root / ".agora" / "events.md",
        root / ".agora" / "activity.md",
        action_path,
    ]
    before = {path: path.read_bytes() for path in tracked}
    from agora import filesystem

    original = filesystem._atomic_write_direct
    writes = 0

    def fail_selected(path: Path, contents: str) -> None:
        nonlocal writes
        writes += 1
        if writes == fail_at:
            raise OSError(f"actor key failure {fail_at}")
        original(path, contents)

    monkeypatch.setattr(filesystem, "_atomic_write_direct", fail_selected)

    with pytest.raises(FilesystemTransactionFailure):
        workspace.apply_lifecycle_action(
            ApplyLifecycleActionInput(action_id=action.id, signature=str(signature))
        )

    assert {path: path.read_bytes() for path in tracked} == before
    assert not replacement_record.exists()
    assert next(item for item in workspace.list_actors() if item.id == "developer") == actor
    monkeypatch.setattr(filesystem, "_atomic_write_direct", original)
    applied = workspace.apply_lifecycle_action(
        ApplyLifecycleActionInput(action_id=action.id, signature=str(signature))
    )
    assert applied.status == "applied"
    assert replacement_record.exists()


@pytest.mark.parametrize("fail_at", [1, 2, 3, 4, 5])
def test_direct_actor_key_rotation_restores_every_record_and_retries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    atomic_write_fault,
    fail_at: int,
) -> None:
    root, workspace, _, _ = _authenticated_project(tmp_path, monkeypatch)
    current_private_key = Ed25519PrivateKey.generate()
    workspace.add_actor(
        AddActorInput(
            id="direct-rotation",
            name="Direct Rotation Actor",
            kind="ai-agent",
            capabilities=["implementation"],
            scope="project",
            public_key=str(_write_public_key(current_private_key, tmp_path / "direct.pem")),
        )
    )
    replacement_private_key = Ed25519PrivateKey.generate()
    replacement_path = _write_public_key(replacement_private_key, tmp_path / "direct-next.pem")
    actor = next(item for item in workspace.list_actors() if item.id == "direct-rotation")
    assert actor.authentication_fingerprint is not None
    key_root = Path(actor.path).with_suffix("") / "keys"
    current_key = key_root / f"{actor.authentication_fingerprint}.md"
    replacement_fingerprint = hashlib.sha256(
        replacement_private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    ).hexdigest()
    replacement_record = key_root / f"{replacement_fingerprint}.md"
    tracked = [
        Path(actor.path),
        current_key,
        root / ".agora" / "events.md",
        root / ".agora" / "activity.md",
    ]
    before = {path: path.read_bytes() for path in tracked}
    request = RotateActorKeyInput(
        actor_id=actor.reference,
        public_key=str(replacement_path),
        reason="Exercise direct rotation rollback",
    )
    atomic_write_fault.arm(fail_at)

    with pytest.raises(FilesystemTransactionFailure):
        workspace.rotate_actor_key(request)

    assert {path: path.read_bytes() for path in tracked} == before
    assert not replacement_record.exists()
    assert next(item for item in workspace.list_actors() if item.id == actor.id) == actor
    atomic_write_fault.restore()
    assert workspace.rotate_actor_key(request).fingerprint == replacement_fingerprint
    assert replacement_record.is_file()


@pytest.mark.parametrize("fail_at", [1, 2, 3, 4])
def test_direct_actor_key_revocation_restores_every_record_and_retries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    atomic_write_fault,
    fail_at: int,
) -> None:
    root, workspace, _, _ = _authenticated_project(tmp_path, monkeypatch)
    current_private_key = Ed25519PrivateKey.generate()
    workspace.add_actor(
        AddActorInput(
            id="direct-revocation",
            name="Direct Revocation Actor",
            kind="ai-agent",
            capabilities=["implementation"],
            scope="project",
            public_key=str(_write_public_key(current_private_key, tmp_path / "revoke.pem")),
        )
    )
    actor = next(item for item in workspace.list_actors() if item.id == "direct-revocation")
    assert actor.authentication_fingerprint is not None
    current_key = (
        Path(actor.path).with_suffix("") / "keys" / f"{actor.authentication_fingerprint}.md"
    )
    tracked = [
        Path(actor.path),
        current_key,
        root / ".agora" / "events.md",
        root / ".agora" / "activity.md",
    ]
    before = {path: path.read_bytes() for path in tracked}
    request = RevokeActorKeyInput(
        actor_id=actor.reference,
        reason="Exercise direct revocation rollback",
    )
    atomic_write_fault.arm(fail_at)

    with pytest.raises(FilesystemTransactionFailure):
        workspace.revoke_actor_key(request)

    assert {path: path.read_bytes() for path in tracked} == before
    assert next(item for item in workspace.list_actors() if item.id == actor.id) == actor
    atomic_write_fault.restore()
    assert workspace.revoke_actor_key(request).status == "revoked"
    assert (
        next(
            item for item in workspace.list_actors() if item.id == actor.id
        ).authentication_revoked_at
        is not None
    )


@pytest.mark.parametrize("fail_at", [1, 2, 3, 4, 5, 6])
def test_signed_actor_key_recovery_restores_action_identity_events_and_retries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    atomic_write_fault,
    fail_at: int,
) -> None:
    root, workspace, _, _ = _authenticated_project(tmp_path, monkeypatch)
    security_private_key = Ed25519PrivateKey.generate()
    workspace.add_actor(
        AddActorInput(
            id="security",
            name="Security Governor",
            kind="human",
            capabilities=["facilitation", "governance"],
            scope="project",
            public_key=str(_write_public_key(security_private_key, tmp_path / "security.pem")),
            require_authentication=True,
        )
    )
    workspace.create_swarm(
        CreateSwarmInput(
            id="identity-governance",
            objective="Govern actor identity recovery",
            create_branch=False,
        )
    )
    for role, actor_id in (
        ("product-owner", "owner"),
        ("scrum-master", "security"),
        ("developer", "developer"),
    ):
        workspace.assign_actor(
            AssignActorInput(
                swarm_id="identity-governance",
                role_id=role,
                actor_id=actor_id,
            )
        )

    revocation = workspace.prepare_actor_key_revocation(
        PrepareActorKeyRevocationInput(
            action_id="revoke-before-recovery",
            swarm_id="identity-governance",
            target_actor_id="developer",
            authorized_by="security",
            reason="Revoke the compromised identity",
        )
    )
    revocation_payload = tmp_path / "revoke-before-recovery.json"
    workspace.prepare_lifecycle_authorization(
        PrepareLifecycleAuthorizationInput(
            action_id=revocation.id,
            output=str(revocation_payload),
        )
    )
    revocation_signature = tmp_path / "revoke-before-recovery.sig"
    revocation_signature.write_bytes(security_private_key.sign(revocation_payload.read_bytes()))
    workspace.apply_lifecycle_action(
        ApplyLifecycleActionInput(
            action_id=revocation.id,
            signature=str(revocation_signature),
        )
    )

    replacement_private_key = Ed25519PrivateKey.generate()
    replacement_path = _write_public_key(replacement_private_key, tmp_path / "recovered.pem")
    recovery = workspace.prepare_actor_key_recovery(
        PrepareActorKeyRecoveryInput(
            action_id="atomic-key-recovery",
            swarm_id="identity-governance",
            target_actor_id="developer",
            authorized_by="security",
            public_key=str(replacement_path),
            reason="Install an independently reviewed replacement",
        )
    )
    recovery_payload = tmp_path / "atomic-key-recovery.json"
    workspace.prepare_lifecycle_authorization(
        PrepareLifecycleAuthorizationInput(
            action_id=recovery.id,
            output=str(recovery_payload),
        )
    )
    recovery_signature = tmp_path / "atomic-key-recovery.sig"
    recovery_signature.write_bytes(security_private_key.sign(recovery_payload.read_bytes()))
    actor = next(item for item in workspace.list_actors() if item.id == "developer")
    assert actor.authentication_fingerprint is not None
    key_root = Path(actor.path).with_suffix("") / "keys"
    current_key = key_root / f"{actor.authentication_fingerprint}.md"
    replacement_record = key_root / f"{recovery.parameters['fingerprint']}.md"
    action_path = root / ".agora" / "actions" / recovery.id / "ACTION.md"
    tracked = [
        Path(actor.path),
        current_key,
        root / ".agora" / "events.md",
        root / ".agora" / "activity.md",
        action_path,
    ]
    before = {path: path.read_bytes() for path in tracked}
    atomic_write_fault.arm(fail_at)

    with pytest.raises(FilesystemTransactionFailure):
        workspace.apply_lifecycle_action(
            ApplyLifecycleActionInput(
                action_id=recovery.id,
                signature=str(recovery_signature),
            )
        )

    assert {path: path.read_bytes() for path in tracked} == before
    assert not replacement_record.exists()
    assert workspace.list_lifecycle_actions("prepared")[-1].id == recovery.id
    assert (
        next(
            item for item in workspace.list_actors() if item.id == actor.id
        ).authentication_revoked_at
        is not None
    )
    atomic_write_fault.restore()
    assert (
        workspace.apply_lifecycle_action(
            ApplyLifecycleActionInput(
                action_id=recovery.id,
                signature=str(recovery_signature),
            )
        ).status
        == "applied"
    )
    assert replacement_record.is_file()
    assert (
        next(
            item for item in workspace.list_actors() if item.id == actor.id
        ).authentication_revoked_at
        is None
    )


@pytest.mark.parametrize("fail_at", [1, 2, 3, 4, 5])
def test_signed_handoff_restores_assignment_record_action_events_and_retries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    atomic_write_fault,
    fail_at: int,
) -> None:
    root, workspace, private_key, _ = _authenticated_project(tmp_path, monkeypatch)
    workspace.add_actor(
        AddActorInput(
            id="incoming-developer",
            name="Incoming Developer",
            kind="human",
            capabilities=["implementation"],
            scope="project",
        )
    )
    action = workspace.prepare_handoff(
        HandoffActorInput(
            id="atomic-signed-handoff",
            swarm_id="delivery",
            role_id="developer",
            from_actor_id="developer",
            to_actor_id="incoming-developer",
            authorized_by="developer",
            reason="Transfer signed responsibility",
        )
    )
    payload = tmp_path / "atomic-signed-handoff.json"
    workspace.prepare_lifecycle_authorization(
        PrepareLifecycleAuthorizationInput(action_id=action.id, output=str(payload))
    )
    signature = tmp_path / "atomic-signed-handoff.sig"
    signature.write_bytes(private_key.sign(payload.read_bytes()))
    swarm_root = swarm_dir(root, "delivery")
    action_path = root / ".agora" / "actions" / action.id / "ACTION.md"
    handoff_path = swarm_root / "handoffs" / action.id / "HANDOFF.md"
    tracked = [
        swarm_root / "SWARM.md",
        swarm_root / "events.md",
        root / ".agora" / "activity.md",
        action_path,
    ]
    before = {path: path.read_bytes() for path in tracked}
    atomic_write_fault.arm(fail_at)

    with pytest.raises(FilesystemTransactionFailure):
        workspace.apply_lifecycle_action(
            ApplyLifecycleActionInput(action_id=action.id, signature=str(signature))
        )

    assert {path: path.read_bytes() for path in tracked} == before
    assert not handoff_path.exists()
    assert workspace.show_swarm("delivery").assignments["developer"] == "project:developer"
    assert workspace.list_lifecycle_actions("prepared")[-1].id == action.id
    atomic_write_fault.restore()
    assert (
        workspace.apply_lifecycle_action(
            ApplyLifecycleActionInput(action_id=action.id, signature=str(signature))
        ).status
        == "applied"
    )
    assert handoff_path.is_file()
    assert workspace.show_swarm("delivery").assignments["developer"] == (
        "project:incoming-developer"
    )


def test_applies_a_signed_granular_gate_waiver(tmp_path: Path, monkeypatch) -> None:
    root, workspace, private_key, _ = _authenticated_project(tmp_path, monkeypatch)
    _create_authenticated_work(
        workspace,
        private_key,
        tmp_path,
        CreateWorkInput(
            swarm_id="delivery",
            id="waived-work",
            title="Authorize a narrow exception",
            actor_id="owner",
            acceptance_criteria=[("external-check", "Receive external confirmation")],
            required_artifacts=["external-report"],
        ),
        action_id="create-waived-work",
    )
    waiver = WaiveGateInput(
        id="accepted-external-risk",
        swarm_id="delivery",
        work_id="waived-work",
        gate_id="completion",
        actor_id="owner",
        reason="External service is unavailable and product governance accepted the risk",
        evidence_refs=["repo://risk/external-service.md"],
        criteria=["external-check"],
        artifacts=["external-report"],
        successful_evidence=True,
        approval_roles=["product-owner"],
    )
    with pytest.raises(PermissionError, match="requires a signed lifecycle action"):
        workspace.waive_gate(waiver)

    stale_transition = workspace.prepare_work_transition(
        PrepareWorkTransitionInput(
            id="plan-before-waiver",
            swarm_id="delivery",
            work_id="waived-work",
            actor_id="developer",
            target_state="planned",
        )
    )

    prepared = workspace.prepare_gate_waiver(
        PrepareGateWaiverInput(action_id="waive-external-risk", waiver=waiver)
    )
    payload_path = tmp_path / "gate-waiver.json"
    workspace.prepare_lifecycle_authorization(
        PrepareLifecycleAuthorizationInput(
            action_id=prepared.id,
            output=str(payload_path),
        )
    )
    payload = json.loads(payload_path.read_text(encoding="ascii"))
    assert payload["kind"] == "gate.waive"
    assert payload["parameters"]["waiver"] == "accepted-external-risk"
    signature_path = tmp_path / "gate-waiver.sig"
    signature_path.write_bytes(private_key.sign(payload_path.read_bytes()))

    applied = workspace.apply_lifecycle_action(
        ApplyLifecycleActionInput(action_id=prepared.id, signature=str(signature_path))
    )
    persisted = workspace.list_gate_waivers("delivery", "waived-work")

    assert applied.status == "applied"
    assert persisted[0].action_id == prepared.id
    assert persisted[0].authorized_by == "project:owner"
    waiver_path = (
        swarm_dir(root, "delivery")
        / "work"
        / "waived-work"
        / "waivers"
        / "accepted-external-risk"
        / "WAIVER.md"
    )
    assert waiver_path.is_file()
    assert workspace.validate().ok
    with pytest.raises(ValueError, match="precondition digest mismatch"):
        workspace.prepare_lifecycle_authorization(
            PrepareLifecycleAuthorizationInput(
                action_id=stale_transition.id,
                output=str(tmp_path / "stale-transition.json"),
            )
        )


def test_applies_a_signed_work_decomposition(tmp_path: Path, monkeypatch) -> None:
    root, workspace, private_key, _ = _authenticated_project(tmp_path, monkeypatch)
    _create_authenticated_work(
        workspace,
        private_key,
        tmp_path,
        CreateWorkInput(
            swarm_id="delivery",
            id="parent-work",
            title="Deliver a governed outcome",
            actor_id="owner",
        ),
        "create-parent-work",
    )
    decomposition = DecomposeWorkInput(
        swarm_id="delivery",
        parent_work_id="parent-work",
        child_work_id="child-work",
        title="Implement a signed child slice",
        actor_id="owner",
        acceptance_criteria=[("reviewed", "The slice is reviewed")],
        required_artifacts=["source-code"],
    )

    with pytest.raises(PermissionError, match="requires a signed lifecycle action"):
        workspace.decompose_work(decomposition)

    prepared = workspace.prepare_decompose_work(
        PrepareDecomposeWorkInput(
            action_id="decompose-parent-work",
            decomposition=decomposition,
        )
    )
    payload_path = tmp_path / "decompose-parent-work.json"
    workspace.prepare_lifecycle_authorization(
        PrepareLifecycleAuthorizationInput(
            action_id=prepared.id,
            output=str(payload_path),
        )
    )
    payload = json.loads(payload_path.read_text(encoding="ascii"))
    assert payload["kind"] == "work.decompose"
    assert payload["work"] == "parent-work"
    assert payload["parameters"]["child-work"] == "child-work"
    signature_path = tmp_path / "decompose-parent-work.sig"
    signature_path.write_bytes(private_key.sign(payload_path.read_bytes()))

    applied = workspace.apply_lifecycle_action(
        ApplyLifecycleActionInput(action_id=prepared.id, signature=str(signature_path))
    )

    assert applied.status == "applied"
    assert workspace.show_work("delivery", "parent-work").child_work_refs == ["delivery/child-work"]
    assert workspace.show_work("delivery", "child-work").parent_work_ref == ("delivery/parent-work")
    assert workspace.validate().ok
    assert (
        "work.decomposed"
        in (
            swarm_dir(root, "delivery") / "work" / "parent-work" / "events.md"
        ).read_text()
    )


def test_authenticated_actor_signs_its_runtime_change(tmp_path: Path, monkeypatch) -> None:
    root, workspace, private_key, _ = _authenticated_project(tmp_path, monkeypatch)
    runtime = SetActorRuntimeInput(
        actor_id="developer",
        integration="generic",
        provider="internal-gateway",
        model="reviewed-model",
    )

    with pytest.raises(PermissionError, match="prepare actor.runtime.update"):
        workspace.set_actor_runtime(runtime)

    prepared = workspace.prepare_actor_runtime(
        PrepareActorRuntimeInput(
            action_id="update-developer-runtime",
            swarm_id="delivery",
            runtime=runtime,
        )
    )
    assert prepared.action == "actor.runtime.update"
    assert prepared.work_id is None
    assert prepared.parameters == {
        "integration": "generic",
        "provider": "internal-gateway",
        "model": "reviewed-model",
        "clear": "false",
    }
    payload_path = tmp_path / "runtime-authorization.json"
    workspace.prepare_lifecycle_authorization(
        PrepareLifecycleAuthorizationInput(
            action_id=prepared.id,
            output=str(payload_path),
        )
    )
    payload = json.loads(payload_path.read_text(encoding="ascii"))
    assert payload["kind"] == "actor.runtime.update"
    assert payload["work"] is None
    signature_path = tmp_path / "runtime-authorization.sig"
    signature_path.write_bytes(private_key.sign(payload_path.read_bytes()))

    applied = workspace.apply_lifecycle_action(
        ApplyLifecycleActionInput(action_id=prepared.id, signature=str(signature_path))
    )

    actor = next(
        item for item in workspace.list_actors("project") if item.reference == "project:developer"
    )
    assert applied.authentication_verified is True
    assert actor.reference == "project:developer"
    assert actor.integration == "generic"
    assert actor.provider == "internal-gateway"
    assert actor.model == "reviewed-model"
    assert workspace.validate().ok
    assert "actor.runtime-updated | actor=project:developer" in (
        root / ".agora" / "events.md"
    ).read_text(encoding="utf-8")


def test_governance_actor_signs_a_vacant_swarm_assignment(tmp_path: Path, monkeypatch) -> None:
    _, workspace, private_key, _ = _authenticated_project(tmp_path, monkeypatch)
    workspace.create_swarm(
        CreateSwarmInput(id="staffing", objective="Authorize role composition", create_branch=False)
    )
    workspace.assign_actor(
        AssignActorInput(swarm_id="staffing", role_id="scrum-master", actor_id="facilitator")
    )

    with pytest.raises(ValueError, match="already assigned.*use a handoff"):
        workspace.assign_actor(
            AssignActorInput(
                swarm_id="staffing",
                role_id="scrum-master",
                actor_id="facilitator",
            )
        )

    prepared = workspace.prepare_actor_assignment(
        PrepareActorAssignmentInput(
            action_id="assign-staffing-owner",
            assignment=AssignActorInput(
                swarm_id="staffing",
                role_id="product-owner",
                actor_id="owner",
            ),
            authorized_by="facilitator",
        )
    )
    assert prepared.action == "swarm.assign"
    assert prepared.parameters == {
        "role": "product-owner",
        "target": "project:owner",
    }
    payload = tmp_path / "assignment.json"
    workspace.prepare_lifecycle_authorization(
        PrepareLifecycleAuthorizationInput(action_id=prepared.id, output=str(payload))
    )
    signature = tmp_path / "assignment.sig"
    signature.write_bytes(private_key.sign(payload.read_bytes()))
    applied = workspace.apply_lifecycle_action(
        ApplyLifecycleActionInput(action_id=prepared.id, signature=str(signature))
    )

    swarm = workspace.show_swarm("staffing")
    assert applied.authentication_verified is True
    assert swarm.assignments["product-owner"] == "project:owner"
    assert "action=assign-staffing-owner" in (Path(swarm.path) / "events.md").read_text(
        encoding="utf-8"
    )
    output = StringIO()
    assert (
        cli_main(
            [
                "swarm",
                "assign-prepare",
                "--id",
                "assign-staffing-developer",
                "--swarm",
                "staffing",
                "--role",
                "developer",
                "--actor",
                "developer",
                "--by",
                "facilitator",
            ],
            cwd=workspace.cwd,
            stdout=output,
        )
        == 0
    )
    assert json.loads(output.getvalue())["action"] == "swarm.assign"
    assert workspace.validate().ok


def test_signed_actor_runtime_change_rechecks_actor_and_method_policy(
    tmp_path: Path, monkeypatch
) -> None:
    root, workspace, _, _ = _authenticated_project(tmp_path, monkeypatch)
    prepared = workspace.prepare_actor_runtime(
        PrepareActorRuntimeInput(
            action_id="stale-runtime-change",
            swarm_id="delivery",
            runtime=SetActorRuntimeInput(actor_id="developer", model="reviewed-model"),
        )
    )
    actor_path = root / ".agora" / "actors" / "developer.md"
    actor_path.write_text(
        actor_path.read_text(encoding="utf-8").replace(
            'name: "Authenticated Developer"', 'name: "Renamed Developer"'
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="precondition digest mismatch"):
        workspace.prepare_lifecycle_authorization(
            PrepareLifecycleAuthorizationInput(
                action_id=prepared.id,
                output=str(tmp_path / "stale-runtime.json"),
            )
        )

    actor_path.write_text(
        actor_path.read_text(encoding="utf-8").replace(
            'name: "Renamed Developer"', 'name: "Authenticated Developer"'
        ),
        encoding="utf-8",
    )
    role_path = root / ".agora" / "methods" / "scrum" / "roles" / "developer.md"
    role_path.write_text(
        role_path.read_text(encoding="utf-8").replace('"actor.runtime.update", ', ""),
        encoding="utf-8",
    )

    with pytest.raises(PermissionError, match="not allowed to perform actor.runtime.update"):
        workspace.apply_lifecycle_action(ApplyLifecycleActionInput(action_id=prepared.id))


def test_cli_prepares_authenticated_actor_runtime_change(tmp_path: Path, monkeypatch) -> None:
    root, _, _, _ = _authenticated_project(tmp_path, monkeypatch)
    output = StringIO()

    assert (
        cli_main(
            [
                "--project",
                str(root),
                "actor",
                "runtime-prepare",
                "--id",
                "cli-runtime-change",
                "--actor",
                "developer",
                "--swarm",
                "delivery",
                "--model",
                "reviewed-model",
            ],
            stdout=output,
        )
        == 0
    )
    record = json.loads(output.getvalue())
    assert record["action"] == "actor.runtime.update"
    assert record["parameters"]["model"] == "reviewed-model"


def test_signs_work_creation_criteria_artifacts_and_evidence(tmp_path: Path, monkeypatch) -> None:
    root, workspace, private_key, _ = _authenticated_project(tmp_path, monkeypatch)

    def sign_and_apply(action_id: str) -> dict[str, object]:
        payload = tmp_path / f"{action_id}.json"
        workspace.prepare_lifecycle_authorization(
            PrepareLifecycleAuthorizationInput(action_id=action_id, output=str(payload))
        )
        signature = tmp_path / f"{action_id}.sig"
        signature.write_bytes(private_key.sign(payload.read_bytes()))
        workspace.apply_lifecycle_action(
            ApplyLifecycleActionInput(action_id=action_id, signature=str(signature))
        )
        return json.loads(payload.read_text(encoding="ascii"))

    creation = CreateWorkInput(
        swarm_id="delivery",
        id="signed-materials",
        title="Persist signed material changes",
        actor_id="owner",
        description="Bind each material mutation to the current work projection.",
        acceptance_criteria=[("verified", "The result has durable evidence")],
        required_artifacts=["implementation"],
    )
    with pytest.raises(PermissionError, match="prepare work.create"):
        workspace.create_work(creation)
    workspace.prepare_create_work(
        PrepareCreateWorkInput(action_id="create-signed-materials", work=creation)
    )
    create_payload = sign_and_apply("create-signed-materials")
    assert create_payload["kind"] == "work.create"
    assert create_payload["work"] == "signed-materials"

    criterion = WorkActorInput(swarm_id="delivery", work_id="signed-materials", actor_id="owner")
    with pytest.raises(PermissionError, match="prepare criterion.satisfy"):
        workspace.satisfy_criterion(criterion, "verified")
    workspace.prepare_satisfy_criterion(
        PrepareCriterionInput(
            id="satisfy-signed-materials",
            **criterion.__dict__,
            criterion_id="verified",
        )
    )
    sign_and_apply("satisfy-signed-materials")

    artifact = AddArtifactInput(
        swarm_id="delivery",
        work_id="signed-materials",
        actor_id="developer",
        kind="implementation",
        uri="repo://delivery/signed-materials.md",
    )
    with pytest.raises(PermissionError, match="prepare artifact.add"):
        workspace.add_artifact(artifact)
    workspace.prepare_add_artifact(
        PrepareArtifactInput(id="add-signed-artifact", **artifact.__dict__)
    )
    sign_and_apply("add-signed-artifact")

    evidence = AddEvidenceInput(
        swarm_id="delivery",
        work_id="signed-materials",
        actor_id="facilitator",
        type="review",
        result="success",
        artifact_refs=["repo://delivery/signed-materials.md"],
    )
    with pytest.raises(PermissionError, match="prepare evidence.add"):
        workspace.add_evidence(evidence)
    workspace.prepare_add_evidence(
        PrepareEvidenceInput(id="add-signed-evidence", **evidence.__dict__)
    )
    evidence_payload = sign_and_apply("add-signed-evidence")
    assert evidence_payload["parameters"]["artifacts"] == (
        '["repo://delivery/signed-materials.md"]'
    )
    assert workspace.validate().ok

    artifact_path = (
        swarm_dir(root, "delivery") / "work" / "signed-materials" / "artifacts.md"
    )
    artifact_path.write_text(
        artifact_path.read_text(encoding="utf-8").replace(
            "repo://delivery/signed-materials.md",
            "repo://delivery/unrecorded.md",
        ),
        encoding="utf-8",
    )
    report = workspace.validate()
    assert not report.ok
    assert any(issue.code == "lifecycle-action.artifact-mismatch" for issue in report.issues)


def test_rejects_lifecycle_signature_replay_and_stale_work_state(
    tmp_path: Path, monkeypatch
) -> None:
    _, workspace, private_key, _ = _authenticated_project(tmp_path, monkeypatch)
    _create_authenticated_work(workspace, private_key, tmp_path)
    base = {
        "swarm_id": "delivery",
        "work_id": "signed-work",
        "actor_id": "developer",
        "target_state": "planned",
    }
    first = workspace.prepare_work_transition(
        PrepareWorkTransitionInput(id="first-transition", **base)
    )
    second = workspace.prepare_work_transition(
        PrepareWorkTransitionInput(id="second-transition", **base)
    )
    payload_path = tmp_path / "first-transition.json"
    workspace.prepare_lifecycle_authorization(
        PrepareLifecycleAuthorizationInput(
            action_id=first.id,
            output=str(payload_path),
        )
    )
    signature_path = tmp_path / "first-transition.sig"
    signature_path.write_bytes(private_key.sign(payload_path.read_bytes()))

    with pytest.raises(ValueError, match="signature is invalid"):
        workspace.apply_lifecycle_action(
            ApplyLifecycleActionInput(action_id=second.id, signature=str(signature_path))
        )

    workspace.apply_lifecycle_action(
        ApplyLifecycleActionInput(action_id=first.id, signature=str(signature_path))
    )
    with pytest.raises(ValueError, match="precondition digest mismatch"):
        workspace.apply_lifecycle_action(
            ApplyLifecycleActionInput(action_id=second.id, signature=str(signature_path))
        )
    report = workspace.validate()
    assert report.ok, report.issues
    assert any(issue.code == "lifecycle-action.precondition-stale" for issue in report.issues)


def test_applies_a_signed_approval_with_role_and_note_bound_to_the_action(
    tmp_path: Path, monkeypatch
) -> None:
    root, workspace, private_key, _ = _authenticated_project(tmp_path, monkeypatch)
    _create_authenticated_work(workspace, private_key, tmp_path)
    approval = AddApprovalInput(
        swarm_id="delivery",
        work_id="signed-work",
        actor_id="owner",
        role_id="product-owner",
        note="Accepted | externally signed",
    )

    with pytest.raises(PermissionError, match="prepare the approval"):
        workspace.add_approval(approval)

    prepared = workspace.prepare_approval(
        PrepareApprovalInput(id="accept-signed-work", **approval.__dict__)
    )
    payload_path = tmp_path / "approval-authorization.json"
    workspace.prepare_lifecycle_authorization(
        PrepareLifecycleAuthorizationInput(
            action_id=prepared.id,
            output=str(payload_path),
        )
    )
    payload = json.loads(payload_path.read_text(encoding="ascii"))
    assert payload["kind"] == "approval.add"
    assert payload["parameters"] == {
        "delegation": "",
        "note": "Accepted | externally signed",
        "role": "product-owner",
    }
    signature_path = tmp_path / "approval-authorization.sig"
    signature_path.write_bytes(private_key.sign(payload_path.read_bytes()))

    applied = workspace.apply_lifecycle_action(
        ApplyLifecycleActionInput(action_id=prepared.id, signature=str(signature_path))
    )

    assert applied.status == "applied"
    assert applied.authentication_verified
    assert workspace.show_work("delivery", "signed-work").approval_roles == ["product-owner"]
    approval_path = swarm_dir(root, "delivery") / "work" / "signed-work"
    assert "Accepted \\| externally signed" in (approval_path / "approvals.md").read_text()
    assert workspace.validate().ok


def test_signs_approval_delegation_use_and_revocation(tmp_path: Path, monkeypatch) -> None:
    _, workspace, private_key, _ = _authenticated_project(tmp_path, monkeypatch)
    workspace.add_actor(
        AddActorInput(
            id="alternate-owner",
            name="Authenticated Alternate Owner",
            kind="human",
            capabilities=["backlog-management", "acceptance"],
            scope="project",
            public_key=str(tmp_path / "developer.pem"),
            require_authentication=True,
        )
    )
    for work_id, action_id in (
        ("delegated-decision", "create-delegated-decision"),
        ("revoked-decision", "create-revoked-decision"),
    ):
        _create_authenticated_work(
            workspace,
            private_key,
            tmp_path,
            CreateWorkInput(
                swarm_id="delivery",
                id=work_id,
                title=f"Exercise {work_id}",
                actor_id="owner",
            ),
            action_id=action_id,
        )

    def authorize(action_id: str) -> None:
        payload_path = tmp_path / f"{action_id}.json"
        workspace.prepare_lifecycle_authorization(
            PrepareLifecycleAuthorizationInput(
                action_id=action_id,
                output=str(payload_path),
            )
        )
        signature_path = tmp_path / f"{action_id}.sig"
        signature_path.write_bytes(private_key.sign(payload_path.read_bytes()))
        workspace.apply_lifecycle_action(
            ApplyLifecycleActionInput(
                action_id=action_id,
                signature=str(signature_path),
            )
        )

    grant = DelegateApprovalInput(
        id="signed-delegation",
        swarm_id="delivery",
        work_id="delegated-decision",
        role_id="product-owner",
        actor_id="owner",
        to_actor_id="alternate-owner",
        reason="Authorize an alternate signer for this decision",
    )
    with pytest.raises(PermissionError, match="prepare approval.delegate"):
        workspace.delegate_approval(grant)
    prepared_grant = workspace.prepare_approval_delegation(
        PrepareApprovalDelegationInput(
            action_id="grant-signed-approval",
            delegation=grant,
        )
    )
    authorize(prepared_grant.id)

    approval = PrepareApprovalInput(
        id="use-signed-delegation",
        swarm_id="delivery",
        work_id="delegated-decision",
        actor_id="alternate-owner",
        role_id="product-owner",
        note="Accepted under delegated authority",
        delegation_id="signed-delegation",
    )
    prepared_approval = workspace.prepare_approval(approval)
    authorize(prepared_approval.id)
    used = workspace.list_approval_delegations("delivery", "delegated-decision", "used")[0]
    assert used.action_id == prepared_grant.id
    assert used.used_action_id == prepared_approval.id

    revoke_grant = DelegateApprovalInput(
        id="revocable-delegation",
        swarm_id="delivery",
        work_id="revoked-decision",
        role_id="product-owner",
        actor_id="owner",
        to_actor_id="alternate-owner",
        reason="Temporary approval coverage",
    )
    prepared_revoke_grant = workspace.prepare_approval_delegation(
        PrepareApprovalDelegationInput(
            action_id="grant-revocable-approval",
            delegation=revoke_grant,
        )
    )
    authorize(prepared_revoke_grant.id)
    revocation = workspace.prepare_revoke_approval_delegation(
        RevokeApprovalDelegationInput(
            delegation_id="revocable-delegation",
            swarm_id="delivery",
            work_id="revoked-decision",
            actor_id="owner",
            reason="Coverage is no longer needed",
            action_id="revoke-signed-approval",
        )
    )
    authorize(revocation.id)
    revoked = workspace.list_approval_delegations("delivery", "revoked-decision", "revoked")[0]
    assert revoked.revocation_action_id == revocation.id
    assert revoked.revoked_reason == "Coverage is no longer needed"
    assert workspace.validate().ok


def test_applies_a_signed_handoff_and_rejects_a_stale_assignment_precondition(
    tmp_path: Path, monkeypatch
) -> None:
    root, workspace, private_key, _ = _authenticated_project(tmp_path, monkeypatch)
    workspace.add_actor(
        AddActorInput(
            id="human-developer",
            name="Human Developer",
            kind="human",
            capabilities=["implementation"],
            scope="project",
        )
    )
    handoff = HandoffActorInput(
        id="handoff-to-human",
        swarm_id="delivery",
        role_id="developer",
        from_actor_id="developer",
        to_actor_id="human-developer",
        authorized_by="developer",
        reason="Human judgment is required",
    )

    with pytest.raises(PermissionError, match="prepare the handoff"):
        workspace.handoff_actor(handoff)

    prepared = workspace.prepare_handoff(handoff)
    stale = workspace.prepare_handoff(
        HandoffActorInput(**{**handoff.__dict__, "id": "stale-handoff-to-human"})
    )
    payload_path = tmp_path / "handoff-authorization.json"
    workspace.prepare_lifecycle_authorization(
        PrepareLifecycleAuthorizationInput(
            action_id=prepared.id,
            output=str(payload_path),
        )
    )
    payload = json.loads(payload_path.read_text(encoding="ascii"))
    assert payload["kind"] == "handoff.create"
    assert payload["work"] is None
    assert payload["parameters"] == {
        "from": "project:developer",
        "reason": "Human judgment is required",
        "role": "developer",
        "to": "project:human-developer",
    }
    signature_path = tmp_path / "handoff-authorization.sig"
    signature_path.write_bytes(private_key.sign(payload_path.read_bytes()))

    applied = workspace.apply_lifecycle_action(
        ApplyLifecycleActionInput(action_id=prepared.id, signature=str(signature_path))
    )

    assert applied.status == "applied"
    assert workspace.show_swarm("delivery").assignments["developer"] == ("project:human-developer")
    assert workspace.list_handoffs("delivery")[0].id == prepared.id
    with pytest.raises(ValueError, match="precondition digest mismatch"):
        workspace.apply_lifecycle_action(ApplyLifecycleActionInput(action_id=stale.id))
    report = workspace.validate()
    assert report.ok, report.issues
    assert any(issue.code == "lifecycle-action.precondition-stale" for issue in report.issues)

    handoff_path = swarm_dir(root, "delivery") / "handoffs" / prepared.id / "HANDOFF.md"
    handoff_path.write_text(
        handoff_path.read_text(encoding="utf-8").replace(
            "Human judgment is required",
            "Unrecorded reason change",
        ),
        encoding="utf-8",
    )
    report = workspace.validate()
    assert not report.ok
    assert any(issue.code == "lifecycle-action.handoff-mismatch" for issue in report.issues)


def test_applies_signed_work_interruptions_with_durable_status_changes(
    tmp_path: Path, monkeypatch
) -> None:
    root, workspace, private_key, _ = _authenticated_project(tmp_path, monkeypatch)
    _create_authenticated_work(workspace, private_key, tmp_path)

    def sign_and_apply(action_id: str) -> tuple[dict[str, object], object]:
        payload_path = tmp_path / f"{action_id}.json"
        workspace.prepare_lifecycle_authorization(
            PrepareLifecycleAuthorizationInput(
                action_id=action_id,
                output=str(payload_path),
            )
        )
        signature_path = tmp_path / f"{action_id}.sig"
        signature_path.write_bytes(private_key.sign(payload_path.read_bytes()))
        return (
            json.loads(payload_path.read_text(encoding="ascii")),
            workspace.apply_lifecycle_action(
                ApplyLifecycleActionInput(
                    action_id=action_id,
                    signature=str(signature_path),
                )
            ),
        )

    blocked = ChangeWorkStatusInput(
        id="pause-signed-work",
        swarm_id="delivery",
        work_id="signed-work",
        actor_id="developer",
        reason="Dependency is unavailable",
    )
    with pytest.raises(PermissionError, match="prepare work.block"):
        workspace.block_work(blocked)
    workspace.prepare_block_work(blocked)
    block_payload, block_action = sign_and_apply(blocked.id or "")
    assert block_payload["kind"] == "work.block"
    assert block_payload["parameters"] == {"reason": "Dependency is unavailable"}
    assert block_action.status == "applied"
    assert workspace.show_work("delivery", "signed-work").operational_status == "blocked"

    resumed = ChangeWorkStatusInput(
        id="resume-signed-work",
        swarm_id="delivery",
        work_id="signed-work",
        actor_id="developer",
        reason="Dependency recovered",
    )
    with pytest.raises(PermissionError, match="prepare work.resume"):
        workspace.resume_work(resumed)
    workspace.prepare_resume_work(resumed)
    sign_and_apply(resumed.id or "")
    assert workspace.show_work("delivery", "signed-work").operational_status == "active"

    cancelled = ChangeWorkStatusInput(
        id="cancel-signed-work",
        swarm_id="delivery",
        work_id="signed-work",
        actor_id="owner",
        reason="Outcome is no longer required",
    )
    with pytest.raises(PermissionError, match="prepare work.cancel"):
        workspace.cancel_work(cancelled)
    workspace.prepare_cancel_work(cancelled)
    sign_and_apply(cancelled.id or "")

    assert workspace.show_work("delivery", "signed-work").operational_status == "cancelled"
    assert [
        item.action for item in workspace.list_work_status_changes("delivery", "signed-work")
    ] == [
        "work.block",
        "work.resume",
        "work.cancel",
    ]
    assert workspace.validate().ok

    status_path = (
        swarm_dir(root, "delivery")
        / "work"
        / "signed-work"
        / "status-changes"
        / "cancel-signed-work"
        / "STATUS.md"
    )
    status_path.write_text(
        status_path.read_text(encoding="utf-8").replace(
            "Outcome is no longer required",
            "Unrecorded cancellation reason",
        ),
        encoding="utf-8",
    )
    report = workspace.validate()
    assert not report.ok
    assert any(issue.code == "lifecycle-action.status-change-mismatch" for issue in report.issues)


def test_applies_signed_delegation_status_decisions_across_parent_and_child(
    tmp_path: Path, monkeypatch
) -> None:
    root, workspace, private_key, _ = _authenticated_project(tmp_path, monkeypatch)
    workspace.add_actor(
        AddActorInput(
            id="specialist",
            name="Specialist Developer",
            kind="ai-agent",
            capabilities=["implementation"],
            scope="project",
        )
    )
    workspace.create_swarm(
        CreateSwarmInput(
            id="specialists",
            objective="Produce delegated results",
            create_branch=False,
        )
    )
    for role, actor_id in (
        ("product-owner", "owner"),
        ("scrum-master", "facilitator"),
        ("developer", "specialist"),
    ):
        workspace.assign_actor(
            AssignActorInput(swarm_id="specialists", role_id=role, actor_id=actor_id)
        )
    workspace.add_actor(
        AddActorInput(
            id="specialist-swarm",
            name="Specialist Swarm",
            kind="swarm",
            capabilities=["implementation"],
            scope="project",
            represented_swarm="specialists",
        )
    )
    workspace.create_swarm(
        CreateSwarmInput(
            id="parent",
            objective="Delegate signed work",
            create_branch=False,
        )
    )
    for role, actor_id in (
        ("product-owner", "owner"),
        ("scrum-master", "facilitator"),
        ("developer", "specialist-swarm"),
    ):
        workspace.assign_actor(AssignActorInput(swarm_id="parent", role_id=role, actor_id=actor_id))
    _create_authenticated_work(
        workspace,
        private_key,
        tmp_path,
        CreateWorkInput(
            swarm_id="parent",
            id="parent-work",
            title="Integrate delegated output",
            actor_id="owner",
        ),
        "create-parent-work",
    )

    def create_delegation(delegation_id: str) -> None:
        workspace.create_delegation(
            CreateDelegationInput(
                id=delegation_id,
                parent_swarm_id="parent",
                parent_work_id="parent-work",
                child_actor_id="specialist-swarm",
                child_work_id=f"{delegation_id}-work",
                actor_id="specialist-swarm",
                title=f"Delegated contract {delegation_id}",
            )
        )

    def sign_and_apply(action_id: str) -> dict[str, object]:
        payload_path = tmp_path / f"{action_id}.json"
        workspace.prepare_lifecycle_authorization(
            PrepareLifecycleAuthorizationInput(
                action_id=action_id,
                output=str(payload_path),
            )
        )
        signature_path = tmp_path / f"{action_id}.sig"
        signature_path.write_bytes(private_key.sign(payload_path.read_bytes()))
        workspace.apply_lifecycle_action(
            ApplyLifecycleActionInput(
                action_id=action_id,
                signature=str(signature_path),
            )
        )
        return json.loads(payload_path.read_text(encoding="ascii"))

    create_delegation("review-contract")
    blocked = ChangeDelegationStatusInput(
        id="block-review-contract",
        delegation_id="review-contract",
        actor_id="facilitator",
        reason="Clarify the requested boundary",
    )
    with pytest.raises(PermissionError, match="prepare delegation.block"):
        workspace.block_delegation(blocked)
    workspace.prepare_block_delegation(blocked)
    block_payload = sign_and_apply(blocked.id or "")
    assert block_payload["swarm"] == "parent"
    assert block_payload["work"] == "parent-work"
    assert block_payload["parameters"] == {
        "delegation": "review-contract",
        "reason": "Clarify the requested boundary",
    }

    resumed = ChangeDelegationStatusInput(
        id="resume-review-contract",
        delegation_id="review-contract",
        actor_id="facilitator",
        reason="The boundary is explicit",
    )
    workspace.prepare_resume_delegation(resumed)
    sign_and_apply(resumed.id or "")

    rejected = ChangeDelegationStatusInput(
        id="reject-review-contract",
        delegation_id="review-contract",
        actor_id="owner",
        reason="The child cannot meet the contract",
    )
    with pytest.raises(PermissionError, match="prepare delegation.reject"):
        workspace.reject_delegation(rejected)
    workspace.prepare_reject_delegation(rejected)
    sign_and_apply(rejected.id or "")
    assert workspace.show_delegation("review-contract").status == "rejected"

    create_delegation("cancel-contract")
    cancelled = ChangeDelegationStatusInput(
        id="cancel-delegated-contract",
        delegation_id="cancel-contract",
        actor_id="owner",
        reason="The parent no longer needs the result",
    )
    with pytest.raises(PermissionError, match="prepare delegation.cancel"):
        workspace.cancel_delegation(cancelled)
    workspace.prepare_cancel_delegation(cancelled)
    sign_and_apply(cancelled.id or "")
    assert workspace.show_delegation("cancel-contract").status == "cancelled"
    assert workspace.validate().ok

    status_path = (
        root
        / ".agora"
        / "delegations"
        / "cancel-contract"
        / "status-changes"
        / "cancel-delegated-contract"
        / "STATUS.md"
    )
    status_path.write_text(
        status_path.read_text(encoding="utf-8").replace(
            "The parent no longer needs the result",
            "Unrecorded delegation reason",
        ),
        encoding="utf-8",
    )
    report = workspace.validate()
    assert not report.ok
    assert any(issue.code == "lifecycle-action.status-change-mismatch" for issue in report.issues)


def test_signs_delegation_creation_acceptance_and_collection(tmp_path: Path, monkeypatch) -> None:
    root, workspace, private_key, _ = _authenticated_project(tmp_path, monkeypatch)
    for actor in (
        AddActorInput(
            id="child-facilitator",
            name="Child Facilitator",
            kind="ai-agent",
            capabilities=["facilitation", "governance"],
            scope="project",
        ),
        AddActorInput(
            id="child-developer",
            name="Child Developer",
            kind="ai-agent",
            capabilities=["implementation"],
            scope="project",
        ),
    ):
        workspace.add_actor(actor)
    workspace.create_swarm(
        CreateSwarmInput(
            id="signed-specialists",
            objective="Produce a signed delegated result",
            create_branch=False,
        )
    )
    for role, actor_id in (
        ("product-owner", "owner"),
        ("scrum-master", "child-facilitator"),
        ("developer", "child-developer"),
    ):
        workspace.assign_actor(
            AssignActorInput(swarm_id="signed-specialists", role_id=role, actor_id=actor_id)
        )
    workspace.add_actor(
        AddActorInput(
            id="signed-specialist-swarm",
            name="Signed Specialist Swarm",
            kind="swarm",
            capabilities=["implementation"],
            scope="project",
            represented_swarm="signed-specialists",
            public_key=str(tmp_path / "developer.pem"),
            require_authentication=True,
        )
    )
    workspace.create_swarm(
        CreateSwarmInput(
            id="signed-parent",
            objective="Integrate a signed delegated result",
            create_branch=False,
        )
    )
    for role, actor_id in (
        ("product-owner", "owner"),
        ("scrum-master", "facilitator"),
        ("developer", "signed-specialist-swarm"),
    ):
        workspace.assign_actor(
            AssignActorInput(swarm_id="signed-parent", role_id=role, actor_id=actor_id)
        )
    _create_authenticated_work(
        workspace,
        private_key,
        tmp_path,
        CreateWorkInput(
            swarm_id="signed-parent",
            id="parent-contract",
            title="Integrate the signed result",
            actor_id="owner",
            required_artifacts=["delegated-result"],
        ),
        "create-parent-contract",
    )

    def export_and_sign(action_id: str) -> tuple[Path, Path]:
        payload = tmp_path / f"{action_id}.json"
        workspace.prepare_lifecycle_authorization(
            PrepareLifecycleAuthorizationInput(action_id=action_id, output=str(payload))
        )
        signature = tmp_path / f"{action_id}.sig"
        signature.write_bytes(private_key.sign(payload.read_bytes()))
        return payload, signature

    def sign_and_apply(action_id: str) -> dict[str, object]:
        payload, signature = export_and_sign(action_id)
        workspace.apply_lifecycle_action(
            ApplyLifecycleActionInput(action_id=action_id, signature=str(signature))
        )
        return json.loads(payload.read_text(encoding="ascii"))

    proposal = CreateDelegationInput(
        id="signed-contract",
        parent_swarm_id="signed-parent",
        parent_work_id="parent-contract",
        child_actor_id="signed-specialist-swarm",
        child_work_id="signed-child-work",
        actor_id="signed-specialist-swarm",
        title="Produce the signed result",
        description="Return a result bound to the delegation contract.",
        acceptance_criteria=[("usable", "The result can be integrated")],
        required_artifacts=["child-result"],
        result_kind="delegated-result",
        budget_limits={"effort": 5},
        artifact_promotions={"child-result": "promoted-child-result"},
    )
    with pytest.raises(PermissionError, match="prepare delegation.create"):
        workspace.create_delegation(proposal)
    workspace.prepare_create_delegation(
        PrepareCreateDelegationInput(action_id="propose-signed-contract", delegation=proposal)
    )
    create_payload = sign_and_apply("propose-signed-contract")
    assert create_payload["parameters"]["delegation"] == "signed-contract"
    assert create_payload["parameters"]["budget-limits"] == '{"effort":5}'
    assert create_payload["parameters"]["artifact-promotions"] == (
        '{"child-result":"promoted-child-result"}'
    )
    assert workspace.show_delegation("signed-contract").status == "proposed"

    acceptance = DelegationActorInput(delegation_id="signed-contract", actor_id="owner")
    with pytest.raises(PermissionError, match="prepare delegation.accept"):
        workspace.accept_delegation(acceptance)
    workspace.prepare_accept_delegation(
        PrepareDelegationActionInput(
            id="accept-signed-contract",
            delegation_id=acceptance.delegation_id,
            actor_id=acceptance.actor_id,
        )
    )
    sign_and_apply("accept-signed-contract")
    assert workspace.show_work("signed-specialists", "signed-child-work").budget_limits == {
        "effort": 5
    }

    for state in ("planned", "implementing", "reviewing", "verifying"):
        workspace.transition_work(
            TransitionWorkInput(
                swarm_id="signed-specialists",
                work_id="signed-child-work",
                actor_id=("child-facilitator" if state == "verifying" else "child-developer"),
                target_state=state,
            )
        )
    workspace.prepare_satisfy_criterion(
        PrepareCriterionInput(
            id="satisfy-signed-child",
            swarm_id="signed-specialists",
            work_id="signed-child-work",
            actor_id="owner",
            criterion_id="usable",
        ),
    )
    sign_and_apply("satisfy-signed-child")
    workspace.add_artifact(
        AddArtifactInput(
            swarm_id="signed-specialists",
            work_id="signed-child-work",
            actor_id="child-developer",
            kind="child-result",
            uri="repo://signed-specialists/result.md",
        )
    )
    workspace.add_evidence(
        AddEvidenceInput(
            swarm_id="signed-specialists",
            work_id="signed-child-work",
            actor_id="child-facilitator",
            type="review",
            result="success",
            artifact_refs=["repo://signed-specialists/result.md"],
        )
    )
    workspace.prepare_approval(
        PrepareApprovalInput(
            id="approve-signed-child",
            swarm_id="signed-specialists",
            work_id="signed-child-work",
            actor_id="owner",
            role_id="product-owner",
        )
    )
    sign_and_apply("approve-signed-child")
    workspace.prepare_add_artifact(
        PrepareArtifactInput(
            id="add-parent-review-artifact",
            swarm_id="signed-parent",
            work_id="parent-contract",
            actor_id="signed-specialist-swarm",
            kind="review-record",
            uri="agora://swarms/signed-parent/work/parent-contract/review",
        )
    )
    sign_and_apply("add-parent-review-artifact")
    workspace.prepare_work_transition(
        PrepareWorkTransitionInput(
            id="complete-signed-child",
            swarm_id="signed-specialists",
            work_id="signed-child-work",
            actor_id="owner",
            target_state="completed",
        )
    )
    sign_and_apply("complete-signed-child")

    collection = DelegationActorInput(
        delegation_id="signed-contract", actor_id="signed-specialist-swarm"
    )
    with pytest.raises(PermissionError, match="prepare delegation.collect"):
        workspace.collect_delegation(collection)
    stale = workspace.prepare_collect_delegation(
        PrepareDelegationActionInput(
            id="collect-stale-contract",
            delegation_id=collection.delegation_id,
            actor_id=collection.actor_id,
        )
    )
    _, stale_signature = export_and_sign(stale.id)
    workspace.prepare_add_evidence(
        PrepareEvidenceInput(
            id="change-parent-evidence",
            swarm_id="signed-parent",
            work_id="parent-contract",
            actor_id="facilitator",
            type="review",
            result="success",
            artifact_refs=["agora://swarms/signed-parent/work/parent-contract/review"],
        )
    )
    sign_and_apply("change-parent-evidence")
    with pytest.raises(ValueError, match="precondition digest mismatch"):
        workspace.apply_lifecycle_action(
            ApplyLifecycleActionInput(action_id=stale.id, signature=str(stale_signature))
        )

    workspace.prepare_collect_delegation(
        PrepareDelegationActionInput(
            id="collect-signed-contract",
            delegation_id=collection.delegation_id,
            actor_id=collection.actor_id,
        )
    )
    sign_and_apply("collect-signed-contract")
    assert workspace.show_delegation("signed-contract").status == "collected"
    assert (
        "promoted-child-result"
        in workspace.show_work("signed-parent", "parent-contract").artifact_kinds
    )
    report = workspace.validate()
    assert {issue.code for issue in report.issues} == {"lifecycle-action.precondition-stale"}

    status_path = (
        root
        / ".agora"
        / "delegations"
        / "signed-contract"
        / "status-changes"
        / "collect-signed-contract"
        / "STATUS.md"
    )
    status_path.write_text(
        status_path.read_text(encoding="utf-8").replace(
            "Completed child result collected into parent work",
            "Unrecorded collection reason",
        ),
        encoding="utf-8",
    )
    report = workspace.validate()
    assert not report.ok
    assert any(issue.code == "lifecycle-action.status-change-mismatch" for issue in report.issues)


def test_launches_an_authenticated_actor_run_with_external_signature(
    tmp_path: Path, monkeypatch
) -> None:
    root, workspace, private_key, calls = _authenticated_project(tmp_path, monkeypatch)
    prepared = workspace.invoke_tool(
        InvokeToolInput(
            id="signed-status",
            tool_id="repository",
            operation_id="status",
            actor_id="developer",
            swarm_id="delivery",
        )
    )
    payload_path = tmp_path / "authorization.json"
    authorization = workspace.prepare_tool_authorization(
        PrepareToolAuthorizationInput(
            run_id=prepared.id,
            output=str(payload_path),
        )
    )
    signature_path = tmp_path / "authorization.sig"
    signature_path.write_bytes(private_key.sign(payload_path.read_bytes()))
    payload = json.loads(payload_path.read_text(encoding="ascii"))
    assert payload["timeout-seconds"] == 300
    assert payload["max-output-bytes"] == 1048576
    assert "environment" not in payload

    completed = workspace.launch_tool_run(
        LaunchToolRunInput(run_id=prepared.id, signature=str(signature_path))
    )

    assert completed.status == "completed"
    assert completed.authentication_verified is True
    assert completed.authentication_fingerprint == authorization.fingerprint
    assert completed.authorization_sha256 == authorization.payload_sha256
    assert calls == [["git", "status", "--short"]]
    run_root = root / ".agora" / "tool-runs" / prepared.id
    assert (run_root / "RESULT.md").is_file()
    assert workspace.validate().ok

    assert completed.authorization_signature is not None
    replacement = (
        "A" if completed.authorization_signature[0] != "A" else "B"
    ) + completed.authorization_signature[1:]
    run_path = run_root / "RUN.md"
    run_path.write_text(
        run_path.read_text(encoding="utf-8").replace(
            completed.authorization_signature,
            replacement,
        ),
        encoding="utf-8",
    )
    report = workspace.validate()
    assert not report.ok
    assert any(issue.code == "tool-run.invalid" for issue in report.issues)


def test_binds_environment_to_authenticated_tool_authorization(tmp_path: Path, monkeypatch) -> None:
    _, workspace, _, _ = _authenticated_project(tmp_path, monkeypatch)
    workspace.add_environment(
        AddEnvironmentInput(
            id="production",
            name="Production",
            allowed_tool_capabilities=["cloud.plan"],
        )
    )
    prepared = workspace.invoke_tool(
        InvokeToolInput(
            id="signed-production-plan",
            tool_id="cloud-infrastructure",
            operation_id="plan",
            actor_id="developer",
            swarm_id="delivery",
            environment_id="production",
            inputs={"environment": "provider-production", "change": "release-v1"},
        )
    )
    payload_path = tmp_path / "production-authorization.json"
    workspace.prepare_tool_authorization(
        PrepareToolAuthorizationInput(run_id=prepared.id, output=str(payload_path))
    )

    payload = json.loads(payload_path.read_text(encoding="ascii"))
    assert payload["environment"] == "production"


def test_rejects_unsigned_immediate_launch_and_signature_replay(
    tmp_path: Path, monkeypatch
) -> None:
    root, workspace, private_key, calls = _authenticated_project(tmp_path, monkeypatch)

    with pytest.raises(ValueError, match="requires signed launch"):
        workspace.invoke_tool(
            InvokeToolInput(
                id="immediate-status",
                tool_id="repository",
                operation_id="status",
                actor_id="developer",
                swarm_id="delivery",
                launch=True,
            )
        )
    assert not (root / ".agora" / "tool-runs" / "immediate-status").exists()

    first = workspace.invoke_tool(
        InvokeToolInput(
            id="first-status",
            tool_id="repository",
            operation_id="status",
            actor_id="developer",
            swarm_id="delivery",
        )
    )
    first_payload = tmp_path / "first.json"
    workspace.prepare_tool_authorization(
        PrepareToolAuthorizationInput(run_id=first.id, output=str(first_payload))
    )
    replayed_signature = tmp_path / "first.sig"
    replayed_signature.write_bytes(private_key.sign(first_payload.read_bytes()))
    second = workspace.invoke_tool(
        InvokeToolInput(
            id="second-status",
            tool_id="repository",
            operation_id="status",
            actor_id="developer",
            swarm_id="delivery",
        )
    )

    with pytest.raises(PermissionError, match="requires a signed tool authorization"):
        workspace.launch_tool_run(LaunchToolRunInput(run_id=second.id))
    with pytest.raises(ValueError, match="signature is invalid"):
        workspace.launch_tool_run(
            LaunchToolRunInput(run_id=second.id, signature=str(replayed_signature))
        )
    assert calls == []


def test_rejects_missing_and_tampered_actor_identity_keys(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    workspace = AgoraWorkspace(cwd=root)
    workspace.initialize(InitInput(integration="generic"))

    with pytest.raises(ValueError, match="must declare --public-key"):
        workspace.add_actor(
            AddActorInput(
                id="developer",
                name="Developer",
                kind="human",
                capabilities=["implementation"],
                scope="project",
                require_authentication=True,
            )
        )

    private_key = Ed25519PrivateKey.generate()
    actor = workspace.add_actor(
        AddActorInput(
            id="developer",
            name="Developer",
            kind="human",
            capabilities=["implementation"],
            scope="project",
            public_key=str(_write_public_key(private_key, tmp_path / "developer.pem")),
            require_authentication=True,
        )
    )
    actor_path = Path(actor.path)
    actor_path.write_text(
        actor_path.read_text(encoding="utf-8").replace(
            actor.authentication_fingerprint or "missing",
            "0" * 64,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="authentication fingerprint mismatch"):
        workspace.list_actors("project")


def test_rotates_actor_keys_and_rejects_the_previous_signer(tmp_path: Path, monkeypatch) -> None:
    root, workspace, previous_private_key, calls = _authenticated_project(tmp_path, monkeypatch)
    prepared = workspace.invoke_tool(
        InvokeToolInput(
            id="before-rotation",
            tool_id="repository",
            operation_id="status",
            actor_id="developer",
            swarm_id="delivery",
        )
    )
    previous_payload = tmp_path / "before-rotation.json"
    workspace.prepare_tool_authorization(
        PrepareToolAuthorizationInput(run_id=prepared.id, output=str(previous_payload))
    )
    previous_signature = tmp_path / "before-rotation.sig"
    previous_signature.write_bytes(previous_private_key.sign(previous_payload.read_bytes()))

    replacement_private_key = Ed25519PrivateKey.generate()
    replacement_path = _write_public_key(replacement_private_key, tmp_path / "replacement.pem")
    rotation = RotateActorKeyInput(
        actor_id="developer",
        public_key=str(replacement_path),
        reason="Scheduled credential rotation",
    )
    with pytest.raises(PermissionError, match="prepare actor.key.rotate"):
        workspace.rotate_actor_key(rotation)

    rotation_action = workspace.prepare_actor_key_rotation(
        PrepareActorKeyRotationInput(
            action_id="rotate-developer-key",
            swarm_id="delivery",
            rotation=rotation,
        )
    )
    rotation_payload = tmp_path / "rotation.json"
    workspace.prepare_lifecycle_authorization(
        PrepareLifecycleAuthorizationInput(
            action_id=rotation_action.id,
            output=str(rotation_payload),
        )
    )
    rotation_signature = tmp_path / "rotation.sig"
    rotation_signature.write_bytes(previous_private_key.sign(rotation_payload.read_bytes()))
    applied_rotation = workspace.apply_lifecycle_action(
        ApplyLifecycleActionInput(
            action_id=rotation_action.id,
            signature=str(rotation_signature),
        )
    )
    replacement = next(
        record
        for record in workspace.list_actor_keys("developer")
        if record.fingerprint == rotation_action.parameters["fingerprint"]
    )
    assert applied_rotation.authentication_fingerprint == rotation_action.parameters["from"]
    assert rotation_action.parameters["reason"] == "Scheduled credential rotation"
    assert rotation_action.parameters["public-key"] == replacement.public_key
    keys = {record.fingerprint: record for record in workspace.list_actor_keys("developer")}
    previous = next(
        record for record in keys.values() if record.fingerprint != replacement.fingerprint
    )
    assert replacement.status == "active"
    assert len(keys) == 2
    assert previous.status == "rotated"
    assert previous.replaced_by == replacement.fingerprint

    with pytest.raises(ValueError, match="signature is invalid"):
        workspace.launch_tool_run(
            LaunchToolRunInput(run_id=prepared.id, signature=str(previous_signature))
        )

    current = workspace.invoke_tool(
        InvokeToolInput(
            id="after-rotation",
            tool_id="repository",
            operation_id="status",
            actor_id="developer",
            swarm_id="delivery",
        )
    )
    current_payload = tmp_path / "after-rotation.json"
    workspace.prepare_tool_authorization(
        PrepareToolAuthorizationInput(run_id=current.id, output=str(current_payload))
    )
    current_signature = tmp_path / "after-rotation.sig"
    current_signature.write_bytes(replacement_private_key.sign(current_payload.read_bytes()))
    completed = workspace.launch_tool_run(
        LaunchToolRunInput(run_id=current.id, signature=str(current_signature))
    )

    assert completed.authentication_fingerprint == replacement.fingerprint
    assert calls == [["git", "status", "--short"]]
    assert workspace.validate().ok
    output = StringIO()
    assert cli_main(["actor", "key", "list", "--actor", "developer"], cwd=root, stdout=output) == 0
    assert len(json.loads(output.getvalue())) == 2

    previous_path = Path(previous.path)
    previous_path.write_text(
        previous_path.read_text(encoding="utf-8").replace(
            replacement.fingerprint,
            "0" * 64,
        ),
        encoding="utf-8",
    )
    report = workspace.validate()
    assert not report.ok
    assert any(issue.code == "actor-key.replacement-missing" for issue in report.issues)


def test_revokes_and_recovers_an_actor_key(tmp_path: Path, monkeypatch) -> None:
    _, workspace, developer_private_key, calls = _authenticated_project(tmp_path, monkeypatch)
    security_private_key = Ed25519PrivateKey.generate()
    workspace.add_actor(
        AddActorInput(
            id="security",
            name="Security Governor",
            kind="human",
            capabilities=["facilitation", "governance"],
            scope="project",
            public_key=str(_write_public_key(security_private_key, tmp_path / "security.pem")),
            require_authentication=True,
        )
    )
    with pytest.raises(PermissionError, match="distinct cryptographic identity"):
        workspace.prepare_actor_key_revocation(
            PrepareActorKeyRevocationInput(
                action_id="reject-shared-key-authorizer",
                swarm_id="delivery",
                target_actor_id="developer",
                authorized_by="facilitator",
                reason="A shared key is not independent authority",
            )
        )
    handoff = workspace.prepare_handoff(
        HandoffActorInput(
            id="handoff-security-governance",
            swarm_id="delivery",
            role_id="scrum-master",
            from_actor_id="facilitator",
            to_actor_id="security",
            authorized_by="facilitator",
            reason="Assign independent key recovery authority",
        )
    )
    handoff_payload = tmp_path / "security-handoff.json"
    workspace.prepare_lifecycle_authorization(
        PrepareLifecycleAuthorizationInput(action_id=handoff.id, output=str(handoff_payload))
    )
    handoff_signature = tmp_path / "security-handoff.sig"
    handoff_signature.write_bytes(developer_private_key.sign(handoff_payload.read_bytes()))
    workspace.apply_lifecycle_action(
        ApplyLifecycleActionInput(action_id=handoff.id, signature=str(handoff_signature))
    )

    with pytest.raises(PermissionError, match="distinct governance actor"):
        workspace.revoke_actor_key(
            RevokeActorKeyInput(actor_id="developer", reason="Credential exposure")
        )
    with pytest.raises(PermissionError, match="cannot administer its own key"):
        workspace.prepare_actor_key_revocation(
            PrepareActorKeyRevocationInput(
                action_id="reject-self-revocation",
                swarm_id="delivery",
                target_actor_id="owner",
                authorized_by="owner",
                reason="Self revocation is not independent",
            )
        )

    revocation_output = StringIO()
    assert (
        cli_main(
            [
                "actor",
                "key",
                "revoke-prepare",
                "--id",
                "revoke-developer-key",
                "--actor",
                "developer",
                "--swarm",
                "delivery",
                "--by",
                "security",
                "--reason",
                "Credential exposure",
            ],
            cwd=workspace.cwd,
            stdout=revocation_output,
        )
        == 0
    )
    revocation = next(
        action
        for action in workspace.list_lifecycle_actions("prepared")
        if action.id == "revoke-developer-key"
    )
    governance_role = workspace.cwd / ".agora" / "methods" / "scrum" / "roles" / "scrum-master.md"
    governance_contents = governance_role.read_text(encoding="utf-8")
    governance_role.write_text(
        governance_contents.replace('"actor.key.revoke", ', ""),
        encoding="utf-8",
    )
    with pytest.raises(PermissionError, match="not allowed to perform actor.key.revoke"):
        workspace.apply_lifecycle_action(ApplyLifecycleActionInput(action_id=revocation.id))
    governance_role.write_text(governance_contents, encoding="utf-8")
    revocation_payload = tmp_path / "revocation.json"
    workspace.prepare_lifecycle_authorization(
        PrepareLifecycleAuthorizationInput(
            action_id=revocation.id,
            output=str(revocation_payload),
        )
    )
    revocation_signature = tmp_path / "revocation.sig"
    revocation_signature.write_bytes(security_private_key.sign(revocation_payload.read_bytes()))
    applied_revocation = workspace.apply_lifecycle_action(
        ApplyLifecycleActionInput(
            action_id=revocation.id,
            signature=str(revocation_signature),
        )
    )
    revoked = next(
        record
        for record in workspace.list_actor_keys("developer")
        if record.fingerprint == revocation.parameters["fingerprint"]
    )

    assert revoked.status == "revoked"
    assert applied_revocation.actor == "project:security"
    assert revocation.parameters["target"] == "project:developer"
    with pytest.raises(PermissionError, match="authentication key is revoked"):
        workspace.invoke_tool(
            InvokeToolInput(
                id="revoked-status",
                tool_id="repository",
                operation_id="status",
                actor_id="developer",
                swarm_id="delivery",
            )
        )
    assert calls == []
    assert workspace.validate().ok

    recovery_private_key = Ed25519PrivateKey.generate()
    recovery_path = _write_public_key(recovery_private_key, tmp_path / "recovery.pem")
    with pytest.raises(PermissionError, match="prepare actor.key.recover"):
        workspace.rotate_actor_key(
            RotateActorKeyInput(
                actor_id="developer",
                public_key=str(recovery_path),
                reason="Replace the revoked credential",
            )
        )
    recovery_output = StringIO()
    assert (
        cli_main(
            [
                "actor",
                "key",
                "recover-prepare",
                "--id",
                "recover-developer-key",
                "--actor",
                "developer",
                "--swarm",
                "delivery",
                "--by",
                "security",
                "--public-key",
                str(recovery_path),
                "--reason",
                "Replace the revoked credential",
            ],
            cwd=workspace.cwd,
            stdout=recovery_output,
        )
        == 0
    )
    recovery = next(
        action
        for action in workspace.list_lifecycle_actions("prepared")
        if action.id == "recover-developer-key"
    )
    recovery_payload = tmp_path / "recovery.json"
    workspace.prepare_lifecycle_authorization(
        PrepareLifecycleAuthorizationInput(
            action_id=recovery.id,
            output=str(recovery_payload),
        )
    )
    recovery_signature = tmp_path / "recovery.sig"
    recovery_signature.write_bytes(security_private_key.sign(recovery_payload.read_bytes()))
    workspace.apply_lifecycle_action(
        ApplyLifecycleActionInput(
            action_id=recovery.id,
            signature=str(recovery_signature),
        )
    )
    recovered = next(
        record
        for record in workspace.list_actor_keys("developer")
        if record.fingerprint == recovery.parameters["fingerprint"]
    )
    actor = next(record for record in workspace.list_actors("project") if record.id == "developer")
    keys = {record.fingerprint: record for record in workspace.list_actor_keys("developer")}
    assert actor.authentication_revoked_at is None
    assert keys[revoked.fingerprint].replaced_by == recovered.fingerprint
    assert keys[recovered.fingerprint].status == "active"
    assert workspace.validate().ok


def test_cli_prepares_actor_key_rotation(tmp_path: Path, monkeypatch) -> None:
    root, _, _, _ = _authenticated_project(tmp_path, monkeypatch)
    replacement_private_key = Ed25519PrivateKey.generate()
    replacement_path = _write_public_key(replacement_private_key, tmp_path / "cli-replacement.pem")
    output = StringIO()

    assert (
        cli_main(
            [
                "actor",
                "key",
                "rotate-prepare",
                "--id",
                "cli-key-rotation",
                "--actor",
                "developer",
                "--swarm",
                "delivery",
                "--public-key",
                str(replacement_path),
                "--reason",
                "Exercise the CLI rotation flow",
            ],
            cwd=root,
            stdout=output,
        )
        == 0
    )
    action = json.loads(output.getvalue())
    assert action["action"] == "actor.key.rotate"
    assert action["parameters"]["reason"] == "Exercise the CLI rotation flow"
    assert len(action["parameters"]["fingerprint"]) == 64


def test_signs_session_launch_and_binds_its_materialized_context(
    tmp_path: Path, monkeypatch
) -> None:
    root, _, private_key, _ = _authenticated_project(tmp_path, monkeypatch)
    calls: list[list[str]] = []

    def launch(command: list[str], cwd: Path, environment: dict[str, str]) -> int:
        calls.append(command)
        return 0

    workspace = AgoraWorkspace(cwd=root, launcher=launch)
    immediate = StartSessionInput(
        id="unsigned-session",
        actor_id="developer",
        swarm_id="delivery",
        runner="/bin/true --agent",
        launch=True,
    )
    with pytest.raises(PermissionError, match="prepare session.prepare"):
        workspace.start_session(immediate)
    assert not (root / ".agora" / "sessions" / "unsigned-session").exists()

    def prepare_signed_session(action_id: str, session_id: str):
        action = workspace.prepare_session(
            PrepareSessionInput(
                action_id=action_id,
                session=StartSessionInput(
                    id=session_id,
                    actor_id="developer",
                    swarm_id="delivery",
                    runner="/bin/true --agent",
                ),
            )
        )
        action_payload = tmp_path / f"{action_id}.json"
        workspace.prepare_lifecycle_authorization(
            PrepareLifecycleAuthorizationInput(
                action_id=action.id,
                output=str(action_payload),
            )
        )
        action_signature = tmp_path / f"{action_id}.sig"
        action_signature.write_bytes(private_key.sign(action_payload.read_bytes()))
        workspace.apply_lifecycle_action(
            ApplyLifecycleActionInput(
                action_id=action.id,
                signature=str(action_signature),
            )
        )
        return next(item for item in workspace.list_sessions() if item.id == session_id)

    prepared = prepare_signed_session("prepare-signed-session", "signed-session")
    assert prepared.preparation_action_id == "prepare-signed-session"
    preparation_action = workspace.list_lifecycle_actions("applied")[-1]
    assert preparation_action.action == "session.prepare"
    assert preparation_action.precondition_sha256 == prepared.context_sha256
    payload_path = tmp_path / "session-authorization.json"
    authorization = workspace.prepare_session_authorization(
        PrepareSessionAuthorizationInput(
            session_id=prepared.id,
            output=str(payload_path),
        )
    )
    payload = json.loads(payload_path.read_text(encoding="ascii"))
    assert payload["context-sha256"] == prepared.context_sha256
    assert payload["launch-command"] == ["/bin/true", "--agent"]
    assert payload["timeout-seconds"] == 3600
    assert payload["max-output-bytes"] == 4 * 1024 * 1024
    signature_path = tmp_path / "session-authorization.sig"
    signature_path.write_bytes(private_key.sign(payload_path.read_bytes()))

    completed = workspace.launch_session(
        LaunchSessionInput(session_id=prepared.id, signature=str(signature_path))
    )
    assert completed.status == "completed"
    assert completed.authentication_verified is True
    assert completed.authentication_fingerprint == authorization.fingerprint
    assert calls == [["/bin/true", "--agent"]]
    assert workspace.validate().ok

    completed_path = Path(completed.path) / "SESSION.md"
    completed_contents = completed_path.read_text(encoding="utf-8")
    completed_path.write_text(
        completed_contents.replace(
            'preparation-action: "prepare-signed-session"',
            'preparation-action: "unrecorded-preparation"',
        ),
        encoding="utf-8",
    )
    report = workspace.validate()
    assert not report.ok
    assert any(issue.code == "lifecycle-action.session-mismatch" for issue in report.issues)
    completed_path.write_text(completed_contents, encoding="utf-8")

    cli_prepare_output = StringIO()
    assert (
        cli_main(
            [
                "session",
                "prepare",
                "--id",
                "prepare-tampered-context",
                "--session",
                "tampered-context",
                "--actor",
                "developer",
                "--swarm",
                "delivery",
                "--runner",
                "/bin/true --agent",
            ],
            cwd=root,
            stdout=cli_prepare_output,
        )
        == 0
    )
    assert json.loads(cli_prepare_output.getvalue())["action"] == "session.prepare"
    preparation_payload = tmp_path / "prepare-tampered-context.json"
    workspace.prepare_lifecycle_authorization(
        PrepareLifecycleAuthorizationInput(
            action_id="prepare-tampered-context",
            output=str(preparation_payload),
        )
    )
    preparation_signature = tmp_path / "prepare-tampered-context.sig"
    preparation_signature.write_bytes(private_key.sign(preparation_payload.read_bytes()))
    workspace.apply_lifecycle_action(
        ApplyLifecycleActionInput(
            action_id="prepare-tampered-context",
            signature=str(preparation_signature),
        )
    )
    tampered = next(item for item in workspace.list_sessions() if item.id == "tampered-context")
    context_path = Path(tampered.context_path)
    original_context = context_path.read_text(encoding="utf-8")
    context_path.write_text(f"{original_context}\nUnapproved context.\n", encoding="utf-8")
    with pytest.raises(ValueError, match="context digest mismatch"):
        workspace.launch_session(LaunchSessionInput(session_id=tampered.id))
    context_path.write_text(original_context, encoding="utf-8")

    cli_payload = tmp_path / "cli-session-authorization.json"
    cli_output = StringIO()
    assert (
        cli_main(
            [
                "session",
                "authorization",
                "--session",
                tampered.id,
                "--output",
                str(cli_payload),
            ],
            cwd=root,
            stdout=cli_output,
        )
        == 0
    )
    cli_signature = tmp_path / "cli-session-authorization.sig"
    cli_signature.write_bytes(private_key.sign(cli_payload.read_bytes()))
    cli_output = StringIO()
    assert (
        cli_main(
            [
                "session",
                "launch",
                "--session",
                tampered.id,
                "--signature",
                str(cli_signature),
            ],
            cwd=root,
            stdout=cli_output,
        )
        == 0
    )
    assert json.loads(cli_output.getvalue())["status"] == "completed"

    assert completed.authorization_signature is not None
    session_path = Path(completed.path) / "SESSION.md"
    replacement = (
        "A" if completed.authorization_signature[0] != "A" else "B"
    ) + completed.authorization_signature[1:]
    session_path.write_text(
        session_path.read_text(encoding="utf-8").replace(
            completed.authorization_signature,
            replacement,
        ),
        encoding="utf-8",
    )
    report = workspace.validate()
    assert not report.ok
    assert any(issue.code == "session.invalid" for issue in report.issues)


def test_signs_evidence_backed_usage_against_current_work_state(
    tmp_path: Path, monkeypatch
) -> None:
    _, workspace, private_key, _ = _authenticated_project(tmp_path, monkeypatch)
    _create_authenticated_work(workspace, private_key, tmp_path)
    usage = AddUsageInput(
        id="model-call-1",
        swarm_id="delivery",
        work_id="signed-work",
        actor_id="developer",
        amounts={"tokens": 1200, "cost-cents": 8},
        evidence_refs=["telemetry://provider/request-1"],
    )

    with pytest.raises(PermissionError, match="prepare usage.add"):
        workspace.add_usage(usage)

    action = workspace.prepare_add_usage(
        PrepareUsageInput(action_id="record-model-usage", usage=usage)
    )
    assert action.action == "usage.add"
    assert json.loads(action.parameters["amounts"]) == {
        "cost-cents": 8,
        "tokens": 1200,
    }
    payload = tmp_path / "record-model-usage.json"
    workspace.prepare_lifecycle_authorization(
        PrepareLifecycleAuthorizationInput(action_id=action.id, output=str(payload))
    )
    signature = tmp_path / "record-model-usage.sig"
    signature.write_bytes(private_key.sign(payload.read_bytes()))

    applied = workspace.apply_lifecycle_action(
        ApplyLifecycleActionInput(action_id=action.id, signature=str(signature))
    )
    records = workspace.list_usage("delivery", "signed-work")

    assert applied.status == "applied"
    assert len(records) == 1
    assert records[0].action_id == action.id
    assert records[0].evidence_refs == ["telemetry://provider/request-1"]
    assert workspace.validate().ok
