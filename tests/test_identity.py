import json
import subprocess
from io import StringIO
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from agora.cli import main as cli_main
from agora.model import (
    AddActorInput,
    AddApprovalInput,
    AddArtifactInput,
    AddEvidenceInput,
    ApplyLifecycleActionInput,
    AssignActorInput,
    ChangeDelegationStatusInput,
    ChangeWorkStatusInput,
    CreateDelegationInput,
    CreateSwarmInput,
    CreateWorkInput,
    DelegationActorInput,
    HandoffActorInput,
    InitInput,
    InvokeToolInput,
    LaunchSessionInput,
    LaunchToolRunInput,
    PrepareApprovalInput,
    PrepareCreateDelegationInput,
    PrepareDelegationActionInput,
    PrepareLifecycleAuthorizationInput,
    PrepareSessionAuthorizationInput,
    PrepareToolAuthorizationInput,
    PrepareWorkTransitionInput,
    RevokeActorKeyInput,
    RotateActorKeyInput,
    StartSessionInput,
    TransitionWorkInput,
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


def _create_authenticated_work(workspace: AgoraWorkspace) -> None:
    workspace.create_work(
        CreateWorkInput(
            swarm_id="delivery",
            id="signed-work",
            title="Apply a signed lifecycle mutation",
            actor_id="owner",
        )
    )


def test_applies_a_signed_work_transition_as_a_durable_lifecycle_action(
    tmp_path: Path, monkeypatch
) -> None:
    root, workspace, private_key, _ = _authenticated_project(tmp_path, monkeypatch)
    _create_authenticated_work(workspace)
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
    assert workspace.list_lifecycle_actions("applied") == [applied]
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


def test_rejects_lifecycle_signature_replay_and_stale_work_state(
    tmp_path: Path, monkeypatch
) -> None:
    _, workspace, private_key, _ = _authenticated_project(tmp_path, monkeypatch)
    _create_authenticated_work(workspace)
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
    _create_authenticated_work(workspace)
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
    approval_path = root / ".agora" / "swarms" / "delivery" / "work" / "signed-work"
    assert "Accepted \\| externally signed" in (approval_path / "approvals.md").read_text()
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

    handoff_path = root / ".agora" / "swarms" / "delivery" / "handoffs" / prepared.id / "HANDOFF.md"
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
    _create_authenticated_work(workspace)

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
        root
        / ".agora"
        / "swarms"
        / "delivery"
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
    workspace.create_work(
        CreateWorkInput(
            swarm_id="parent",
            id="parent-work",
            title="Integrate delegated output",
            actor_id="owner",
        )
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
    workspace.create_work(
        CreateWorkInput(
            swarm_id="signed-parent",
            id="parent-contract",
            title="Integrate the signed result",
            actor_id="owner",
            required_artifacts=["delegated-result"],
        )
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
    )
    with pytest.raises(PermissionError, match="prepare delegation.create"):
        workspace.create_delegation(proposal)
    workspace.prepare_create_delegation(
        PrepareCreateDelegationInput(action_id="propose-signed-contract", delegation=proposal)
    )
    create_payload = sign_and_apply("propose-signed-contract")
    assert create_payload["parameters"]["delegation"] == "signed-contract"
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

    for state in ("planned", "implementing", "reviewing", "verifying"):
        workspace.transition_work(
            TransitionWorkInput(
                swarm_id="signed-specialists",
                work_id="signed-child-work",
                actor_id=("child-facilitator" if state == "verifying" else "child-developer"),
                target_state=state,
            )
        )
    workspace.satisfy_criterion(
        WorkActorInput(
            swarm_id="signed-specialists", work_id="signed-child-work", actor_id="owner"
        ),
        "usable",
    )
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
    workspace.add_evidence(
        AddEvidenceInput(
            swarm_id="signed-parent",
            work_id="parent-contract",
            actor_id="facilitator",
            type="review",
            result="success",
        )
    )
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
    replacement = workspace.rotate_actor_key(
        RotateActorKeyInput(
            actor_id="developer",
            public_key=str(
                _write_public_key(replacement_private_key, tmp_path / "replacement.pem")
            ),
            reason="Scheduled credential rotation",
        )
    )
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
    _, workspace, _, calls = _authenticated_project(tmp_path, monkeypatch)
    revoked = workspace.revoke_actor_key(
        RevokeActorKeyInput(actor_id="developer", reason="Credential exposure")
    )

    assert revoked.status == "revoked"
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
    recovered = workspace.rotate_actor_key(
        RotateActorKeyInput(
            actor_id="developer",
            public_key=str(_write_public_key(recovery_private_key, tmp_path / "recovery.pem")),
            reason="Replace the revoked credential",
        )
    )
    actor = next(record for record in workspace.list_actors("project") if record.id == "developer")
    keys = {record.fingerprint: record for record in workspace.list_actor_keys("developer")}
    assert actor.authentication_revoked_at is None
    assert keys[revoked.fingerprint].replaced_by == recovered.fingerprint
    assert keys[recovered.fingerprint].status == "active"
    assert workspace.validate().ok


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
    with pytest.raises(ValueError, match="requires signed session launch"):
        workspace.start_session(immediate)
    assert not (root / ".agora" / "sessions" / "unsigned-session").exists()

    prepared = workspace.start_session(
        StartSessionInput(
            id="signed-session",
            actor_id="developer",
            swarm_id="delivery",
            runner="/bin/true --agent",
        )
    )
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

    tampered = workspace.start_session(
        StartSessionInput(
            id="tampered-context",
            actor_id="developer",
            swarm_id="delivery",
            runner="/bin/true --agent",
        )
    )
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
