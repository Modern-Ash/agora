import base64
import hashlib
import json
import re
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from conftest import swarm_dir
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from agora.application import (
    ActorUnauthorizedError,
    AgoraCommandService,
    AgoraReadService,
    ApproveGateCommand,
    CommandPersistenceError,
    EvidenceMissingError,
    GovernedMaterialStaleError,
    InvalidCommandError,
    PreparationExpiredError,
    ProjectIdentityMismatchError,
    SignatureRequiredError,
    StalePreconditionError,
    TransactionIndeterminateError,
    TransactionRollbackError,
    approve_gate_authorization_payload,
)
from agora.domain_errors import EvidenceMissingRuleError, GateDecisionRoleRuleError
from agora.markdown import read_markdown, render_markdown
from agora.model import (
    AddActorInput,
    AddApprovalInput,
    AddArtifactInput,
    AddEvidenceInput,
    AssignActorInput,
    ChangeWorkStatusInput,
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
        "transition_target": "completed",
        "role_id": "product-owner",
        "evidence_references": ("repo://reports/release.txt",),
    }
    values.update(changes)
    return ApproveGateCommand(**values)  # type: ignore[arg-type]


def prepared_command(service: AgoraCommandService, **changes: object) -> ApproveGateCommand:
    value = command(**changes)
    prepared = service.prepare_gate_decision(value)
    return replace(
        value,
        reason=prepared.reason,
        evidence_references=prepared.evidence_references,
        precondition_digest=prepared.precondition_digest,
        prepared_at=prepared.prepared_at,
        expires_at=prepared.expires_at,
        evidence_content_sha256=prepared.evidence_content_sha256,
        actor_fingerprint=prepared.actor_fingerprint,
    )


def add_external_evidence(
    workspace: AgoraWorkspace,
    *,
    uri: str,
    digest: str | None,
    evidence_type: str = "test-run",
) -> None:
    workspace.add_artifact(
        AddArtifactInput(
            swarm_id="delivery",
            work_id="release",
            actor_id="developer",
            kind="external-report",
            uri=uri,
            content_sha256=digest,
        )
    )
    workspace.add_evidence(
        AddEvidenceInput(
            swarm_id="delivery",
            work_id="release",
            actor_id="developer",
            type=evidence_type,
            result="success",
            artifact_refs=[uri],
        )
    )


def _core_0_8_golden_contract(
    workspace: AgoraWorkspace,
    service: AgoraCommandService,
) -> dict[str, object]:
    selected_reference = "https://evidence.example.invalid/selected-null-digest"
    add_external_evidence(
        workspace,
        uri=selected_reference,
        digest=None,
    )
    reads = AgoraReadService(workspace)
    options_projection = reads.gate_decision_options("delivery", "release")
    work_inspection = reads.work_inspection("delivery", "release")
    option = next(
        item
        for item in options_projection.options
        if item.decision == "approved" and item.gate_id == "completion"
    )
    intent = command(
        reason="  Evidence   reviewed and accepted  ",
        evidence_references=(selected_reference,),
    )
    prepared = service.prepare_gate_decision(intent)
    confirmation = replace(
        intent,
        reason=prepared.reason,
        evidence_references=prepared.evidence_references,
        evidence_content_sha256=prepared.evidence_content_sha256,
        actor_fingerprint=prepared.actor_fingerprint,
        precondition_digest=prepared.precondition_digest,
        prepared_at=prepared.prepared_at,
        expires_at=prepared.expires_at,
    )
    projection = service.approve_gate(confirmation)
    artifact = next(
        item for item in reads.artifacts("delivery", "release") if item.uri == selected_reference
    )
    evidence = next(
        item
        for item in reads.evidence("delivery", "release")
        if selected_reference in item.artifact_references
    )
    return {
        "core_version": "0.8.1",
        "artifact": artifact.to_dict(),
        "evidence": evidence.to_dict(),
        "gate_command": confirmation.to_dict(),
        "prepared_gate": prepared.to_dict(),
        "gate_option": option.to_dict(),
        "gate_options_projection_schema": options_projection.schema,
        "gate_decision_projection": projection.to_dict(),
        "work_control_projection_schema": "agora/application/work-control-projection/v3",
        "work_inspection_schema": work_inspection.schema,
        "durable_activity": projection.activity.to_dict(),
        "operational_error": PreparationExpiredError(
            "The prepared gate decision expired"
        ).to_dict(),
        "budget": {
            "command_schema": "agora/application/amend-budget-command/v1",
            "prepared_schema": "agora/application/prepared-budget-amendment/v1",
            "authorization_schema": "agora/application/amend-budget-authorization/v1",
            "projection_schema": "agora/application/budget-amendment-projection/v1",
            "durable_record_schema": "agora/budget-amendment/v1",
        },
    }


def test_core_0_8_fixture_is_generated_by_a_real_confirmable_gate_flow(
    gate_project: tuple[Path, AgoraWorkspace, AgoraCommandService],
) -> None:
    _, workspace, service = gate_project
    path = Path(__file__).parent / "contracts" / "core-0.8-application-contracts.json"

    assert _core_0_8_golden_contract(workspace, service) == json.loads(
        path.read_text(encoding="utf-8")
    )


def test_serializes_the_immutable_versioned_command() -> None:
    value = command(
        authentication={
            "algorithm": "ed25519",
            "fingerprint": "a" * 64,
            "signature": "c2ln",
        }
    )

    payload = json.loads(value.to_json())

    assert payload["schema"] == "agora/application/approve-gate-command/v4"
    assert payload["decision"] == "approved"
    assert payload["evidence_references"] == ["repo://reports/release.txt"]
    assert "path" not in payload
    with pytest.raises(TypeError):
        value.authentication["signature"] = "changed"  # type: ignore[index]


def test_core_exposes_exact_approve_and_reject_options(
    gate_project: tuple[Path, AgoraWorkspace, AgoraCommandService],
) -> None:
    _, workspace, _ = gate_project

    projection = AgoraReadService(workspace).gate_decision_options("delivery", "release")

    assert projection.schema == ("agora/application/gate-decision-options-projection/v3")
    assert [(item.decision, item.allowed) for item in projection.options] == [
        ("approved", True),
        ("rejected", True),
    ]
    assert {item.transition_target for item in projection.options} == {"completed"}
    assert {item.role_id for item in projection.options} == {"product-owner"}
    assert {item.actor_id for item in projection.options} == {"project:owner"}
    assert projection.options[0].evidence_references == ("repo://reports/release.txt",)
    assert projection.options[0].evidence_references_by_type == {
        "test-run": ("repo://reports/release.txt",)
    }


def test_rejection_remains_available_when_approval_preconditions_are_blocked(
    gate_project: tuple[Path, AgoraWorkspace, AgoraCommandService],
) -> None:
    _, workspace, _ = gate_project
    workspace.create_work(
        CreateWorkInput(
            swarm_id="delivery",
            id="blocked-gate",
            title="Blocked gate",
            actor_id="owner",
            acceptance_criteria=[("missing", "Still missing")],
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
                work_id="blocked-gate",
                actor_id=actor,
                target_state=state,
            )
        )

    options = AgoraReadService(workspace).gate_decision_options("delivery", "blocked-gate").options
    approved = next(item for item in options if item.decision == "approved")
    rejected = next(item for item in options if item.decision == "rejected")

    assert approved.allowed is False
    assert {blocker.category for blocker in approved.blockers} >= {
        "criterion",
        "artifact",
        "evidence",
    }
    assert rejected.allowed is True
    assert rejected.blockers == ()


def test_enumerates_multiple_transitions_gates_roles_and_actors(
    gate_project: tuple[Path, AgoraWorkspace, AgoraCommandService],
) -> None:
    root, workspace, _ = gate_project
    method_root = root / ".agora" / "methods" / "scrum"
    completion = method_root / "gates" / "completion.md"
    completion.write_text(
        completion.read_text(encoding="utf-8").replace(
            'required-approval-roles: ["product-owner"]',
            'required-approval-roles: ["product-owner","scrum-master"]',
        ),
        encoding="utf-8",
    )
    (method_root / "gates" / "rework-review.md").write_text(
        """---
schema: "agora/gate/v1"
id: "rework-review"
require-all-criteria: false
require-required-artifacts: false
require-successful-evidence: false
required-approval-roles: ["scrum-master"]
---

# Rework review gate
""",
        encoding="utf-8",
    )
    (method_root / "transitions" / "08-verifying-reviewing.md").write_text(
        """---
schema: "agora/transition/v1"
from: "verifying"
to: "reviewing"
roles: ["scrum-master"]
gate: "rework-review"
---

# Return to review
""",
        encoding="utf-8",
    )

    options = AgoraReadService(workspace).gate_decision_options("delivery", "release").options

    assert len(options) == 6
    assert {item.transition_target for item in options} == {"completed", "reviewing"}
    assert {item.gate_id for item in options} == {"completion", "rework-review"}
    assert {(item.role_id, item.actor_id) for item in options} == {
        ("product-owner", "project:owner"),
        ("scrum-master", "project:facilitator"),
    }


def test_prepares_a_stable_canonical_authorization_payload(
    gate_project: tuple[Path, AgoraWorkspace, AgoraCommandService],
) -> None:
    _, _, service = gate_project

    prepared = service.prepare_gate_decision(command())
    second = service.prepare_gate_decision(command())

    assert prepared.schema == "agora/application/prepared-gate-decision/v3"
    assert prepared.command_schema == "agora/application/approve-gate-command/v4"
    assert prepared.authorization_schema == ("agora/application/approve-gate-authorization/v4")
    assert prepared.authorization_payload.encode("ascii") == (
        approve_gate_authorization_payload(
            replace(
                command(),
                precondition_digest=prepared.precondition_digest,
                prepared_at=prepared.prepared_at,
                expires_at=prepared.expires_at,
                evidence_content_sha256=prepared.evidence_content_sha256,
                actor_fingerprint=prepared.actor_fingerprint,
            )
        )
    )
    assert (
        prepared.authorization_digest
        == hashlib.sha256(prepared.authorization_payload.encode("ascii")).hexdigest()
    )
    assert prepared == second
    assert prepared.authentication_required is False
    assert prepared.authentication_public_key is None
    assert prepared.freshness == "governed-material/v2"
    assert re.fullmatch(r"[0-9a-f]{64}", prepared.precondition_digest)


def test_prepared_digest_map_contains_only_the_selected_eligible_subset(
    gate_project: tuple[Path, AgoraWorkspace, AgoraCommandService],
) -> None:
    _, workspace, service = gate_project
    unselected = "https://evidence.example.invalid/unselected"
    add_external_evidence(workspace, uri=unselected, digest="b" * 64)

    option = next(
        item
        for item in AgoraReadService(workspace).gate_decision_options("delivery", "release").options
        if item.decision == "approved"
    )
    assert set(option.evidence_content_sha256) == {
        "repo://reports/release.txt",
        unselected,
    }

    prepared = service.prepare_gate_decision(command())
    assert prepared.evidence_content_sha256 == {
        "repo://reports/release.txt": hashlib.sha256(b"passed\n").hexdigest()
    }

    result = service.approve_gate(
        replace(
            command(),
            precondition_digest=prepared.precondition_digest,
            prepared_at=prepared.prepared_at,
            expires_at=prepared.expires_at,
            evidence_content_sha256=prepared.evidence_content_sha256,
            actor_fingerprint=prepared.actor_fingerprint,
        )
    )
    assert result.evidence_content_sha256 == prepared.evidence_content_sha256


def test_prepared_digest_map_has_one_exact_entry_for_each_selected_required_type(
    gate_project: tuple[Path, AgoraWorkspace, AgoraCommandService],
) -> None:
    root, workspace, service = gate_project
    external = "https://evidence.example.invalid/external-audit"
    add_external_evidence(
        workspace,
        uri=external,
        digest="c" * 64,
        evidence_type="external-audit",
    )
    gate = root / ".agora" / "methods" / "scrum" / "gates" / "completion.md"
    gate.write_text(
        gate.read_text(encoding="utf-8").replace(
            "require-successful-evidence: true",
            "require-successful-evidence: true\n"
            'required-evidence-types: ["test-run","external-audit"]',
        ),
        encoding="utf-8",
    )
    references = ("repo://reports/release.txt", external)

    prepared = service.prepare_gate_decision(command(evidence_references=references))

    assert tuple(prepared.evidence_content_sha256) == references
    assert prepared.evidence_content_sha256[external] == "c" * 64


@pytest.mark.parametrize(
    "mutation",
    ["empty", "missing", "additional", "changed", "null"],
)
def test_confirmation_rejects_any_non_exact_evidence_digest_map_as_stale(
    gate_project: tuple[Path, AgoraWorkspace, AgoraCommandService],
    mutation: str,
) -> None:
    _, workspace, service = gate_project
    external = "https://evidence.example.invalid/selected"
    add_external_evidence(workspace, uri=external, digest="d" * 64)
    raw = command(evidence_references=("repo://reports/release.txt", external))
    prepared = service.prepare_gate_decision(raw)
    exact = dict(prepared.evidence_content_sha256)
    if mutation == "empty":
        changed: dict[str, str | None] = {}
    elif mutation == "missing":
        changed = {external: exact[external]}
    elif mutation == "additional":
        changed = {**exact, "https://evidence.example.invalid/extra": "e" * 64}
    elif mutation == "changed":
        changed = {**exact, external: "f" * 64}
    else:
        changed = {**exact, external: None}
    request = replace(
        raw,
        precondition_digest=prepared.precondition_digest,
        prepared_at=prepared.prepared_at,
        expires_at=prepared.expires_at,
        evidence_content_sha256=changed,
        actor_fingerprint=prepared.actor_fingerprint,
    )

    with pytest.raises(GovernedMaterialStaleError) as captured:
        service.approve_gate(request)

    assert captured.value.to_dict()["details"]["stale_reason"] == "evidence-changed"
    assert workspace.show_work("delivery", "release").approval_roles == []


def test_selected_evidence_without_a_digest_round_trips_as_an_explicit_null(
    gate_project: tuple[Path, AgoraWorkspace, AgoraCommandService],
) -> None:
    _, workspace, service = gate_project
    external = "https://evidence.example.invalid/informational"
    add_external_evidence(
        workspace,
        uri=external,
        digest=None,
        evidence_type="informational-review",
    )
    raw = command(evidence_references=(external,))

    prepared = service.prepare_gate_decision(raw)
    assert prepared.evidence_content_sha256 == {external: None}

    result = service.approve_gate(
        replace(
            raw,
            precondition_digest=prepared.precondition_digest,
            prepared_at=prepared.prepared_at,
            expires_at=prepared.expires_at,
            evidence_content_sha256=prepared.evidence_content_sha256,
            actor_fingerprint=prepared.actor_fingerprint,
        )
    )
    assert result.evidence_content_sha256 == {external: None}


def test_canonicalizes_reason_and_evidence_once_for_payload_projection_and_persistence(
    gate_project: tuple[Path, AgoraWorkspace, AgoraCommandService],
) -> None:
    root, _, service = gate_project
    raw = command(
        reason="  Evidence\n\t reviewed   and accepted  ",
        evidence_references=(
            " repo://reports/release.txt ",
            "",
            "repo://reports/release.txt",
            "   ",
        ),
    )

    prepared = service.prepare_gate_decision(raw)
    request = replace(
        raw,
        precondition_digest=prepared.precondition_digest,
        prepared_at=prepared.prepared_at,
        expires_at=prepared.expires_at,
        evidence_content_sha256=prepared.evidence_content_sha256,
        actor_fingerprint=prepared.actor_fingerprint,
    )
    result = service.approve_gate(request)

    assert prepared.reason == "Evidence reviewed and accepted"
    assert prepared.evidence_references == ("repo://reports/release.txt",)
    payload = json.loads(prepared.authorization_payload)
    assert payload["reason"] == prepared.reason
    assert payload["evidence_references"] == ["repo://reports/release.txt"]
    assert result.reason == prepared.reason
    assert result.evidence_references == prepared.evidence_references
    approvals = swarm_dir(root, "delivery") / "work" / "release" / "approvals.md"
    assert "Evidence reviewed and accepted" in approvals.read_text(encoding="utf-8")
    assert "evidence=repo://reports/release.txt" in result.activity.summary
    assert "reason=Evidence reviewed and accepted" in result.activity.summary


def test_required_evidence_types_only_accept_their_own_successful_references(
    gate_project: tuple[Path, AgoraWorkspace, AgoraCommandService],
) -> None:
    root, workspace, service = gate_project
    gate = root / ".agora" / "methods" / "scrum" / "gates" / "completion.md"
    gate.write_text(
        gate.read_text(encoding="utf-8").replace(
            "require-successful-evidence: true",
            'require-successful-evidence: true\nrequired-evidence-types: ["review-report"]',
        ),
        encoding="utf-8",
    )
    review = root / "reports" / "review.txt"
    review.write_text("approved\n", encoding="utf-8")
    workspace.add_artifact(
        AddArtifactInput(
            swarm_id="delivery",
            work_id="release",
            actor_id="developer",
            kind="review-report",
            uri="repo://reports/review.txt",
        )
    )
    workspace.add_evidence(
        AddEvidenceInput(
            swarm_id="delivery",
            work_id="release",
            actor_id="developer",
            type="review-report",
            result="success",
            artifact_refs=["repo://reports/review.txt"],
        )
    )

    approved = next(
        item
        for item in AgoraReadService(workspace).gate_decision_options("delivery", "release").options
        if item.decision == "approved"
    )
    assert approved.evidence_references_by_type == {"review-report": ("repo://reports/review.txt",)}
    assert approved.evidence_references == ("repo://reports/review.txt",)
    with pytest.raises(EvidenceMissingError):
        service.prepare_gate_decision(command())
    prepared = service.prepare_gate_decision(
        command(evidence_references=("repo://reports/review.txt",))
    )
    assert prepared.evidence_references == ("repo://reports/review.txt",)


def test_prepare_revalidates_evidence_and_stale_state(
    gate_project: tuple[Path, AgoraWorkspace, AgoraCommandService],
) -> None:
    _, _, service = gate_project

    with pytest.raises(EvidenceMissingError):
        service.prepare_gate_decision(command(evidence_references=("repo://reports/missing.txt",)))
    with pytest.raises(StalePreconditionError):
        service.prepare_gate_decision(command(expected_state="reviewing"))


def test_unsigned_decision_cannot_change_canonical_command_after_preparation(
    gate_project: tuple[Path, AgoraWorkspace, AgoraCommandService],
) -> None:
    _, _, service = gate_project
    prepared = service.prepare_gate_decision(command())
    changed = command(
        reason="A different durable decision",
        precondition_digest=prepared.precondition_digest,
        prepared_at=prepared.prepared_at,
        expires_at=prepared.expires_at,
        evidence_content_sha256=prepared.evidence_content_sha256,
        actor_fingerprint=prepared.actor_fingerprint,
    )

    with pytest.raises(StalePreconditionError):
        service.approve_gate(changed)


@pytest.mark.parametrize(
    "changed_material",
    ["evidence", "spec", "method", "assignment", "key", "approval", "artifact"],
)
def test_rejects_governed_material_that_changed_after_preparation_without_writes(
    gate_project: tuple[Path, AgoraWorkspace, AgoraCommandService],
    monkeypatch: pytest.MonkeyPatch,
    changed_material: str,
) -> None:
    root, workspace, service = gate_project
    mutable_fingerprint = {"value": None}
    find_actor = workspace._find_actor
    if changed_material == "key":

        def current_actor(root_path: Path, actor_id: str):
            actor = find_actor(root_path, actor_id)
            if actor.reference != "project:owner":
                return actor
            return replace(
                actor,
                authentication_fingerprint=mutable_fingerprint["value"],
            )

        monkeypatch.setattr(workspace, "_find_actor", current_actor)
    if changed_material == "spec":
        spec = root / "docs" / "release.md"
        spec.parent.mkdir()
        spec.write_text("revision one\n", encoding="utf-8")
        workspace.add_artifact(
            AddArtifactInput(
                swarm_id="delivery",
                work_id="release",
                actor_id="developer",
                kind="spec",
                uri="repo://docs/release.md",
            )
        )

    prepared = service.prepare_gate_decision(command())
    request = replace(
        command(),
        precondition_digest=prepared.precondition_digest,
        prepared_at=prepared.prepared_at,
        expires_at=prepared.expires_at,
        evidence_content_sha256=prepared.evidence_content_sha256,
        actor_fingerprint=prepared.actor_fingerprint,
    )

    if changed_material == "evidence":
        workspace.add_evidence(
            AddEvidenceInput(
                swarm_id="delivery",
                work_id="release",
                actor_id="developer",
                type="review-report",
                result="success",
                artifact_refs=["repo://reports/release.txt"],
            )
        )
    elif changed_material == "spec":
        (root / "docs" / "release.md").write_text("revision two\n", encoding="utf-8")
    elif changed_material == "method":
        gate = root / ".agora" / "methods" / "scrum" / "gates" / "completion.md"
        gate.write_text(
            gate.read_text(encoding="utf-8") + "\nAdditional governance guidance.\n",
            encoding="utf-8",
        )
    elif changed_material == "assignment":
        swarm_path = swarm_dir(root, "delivery") / "SWARM.md"
        document = read_markdown(swarm_path)
        assignments = dict(document.attributes["assignments"])
        assignments["product-owner"] = "project:facilitator"
        document.attributes["assignments"] = assignments
        swarm_path.write_text(render_markdown(document), encoding="utf-8")
    elif changed_material == "key":
        mutable_fingerprint["value"] = "b" * 64
    elif changed_material == "approval":
        workspace.add_approval(
            AddApprovalInput(
                swarm_id="delivery",
                work_id="release",
                actor_id="owner",
                role_id="product-owner",
                note="Resolved elsewhere",
            )
        )
    else:
        (root / "reports" / "release.txt").write_text("changed\n", encoding="utf-8")

    work_root = swarm_dir(root, "delivery") / "work" / "release"
    decision_paths = [
        work_root / "approvals.md",
        work_root / "events.md",
        root / ".agora" / "activity.md",
    ]
    before = {path: path.read_bytes() for path in decision_paths}

    with pytest.raises(StalePreconditionError) as captured:
        service.approve_gate(request)

    if changed_material == "key":
        assert captured.value.to_dict()["details"]["stale_reason"] == "actor-key-changed"
    assert {path: path.read_bytes() for path in decision_paths} == before


@pytest.mark.parametrize("operation", ["blocked", "cancelled"])
def test_gate_options_report_non_active_work_as_blocked(
    gate_project: tuple[Path, AgoraWorkspace, AgoraCommandService],
    operation: str,
) -> None:
    _, workspace, _ = gate_project
    change = ChangeWorkStatusInput(
        swarm_id="delivery",
        work_id="release",
        actor_id="developer" if operation == "blocked" else "owner",
        reason=f"Work is {operation}",
        id=f"make-{operation}",
    )
    if operation == "blocked":
        workspace.block_work(change)
    else:
        workspace.cancel_work(change)

    projection = AgoraReadService(workspace).gate_decision_options("delivery", "release")

    assert projection.operational_status == operation
    assert projection.reason == f"Work operational status is {operation}"
    assert projection.options
    assert all(item.allowed is False for item in projection.options)
    assert all(
        any(blocker.code == "work.not-active" for blocker in item.blockers)
        for item in projection.options
    )


def test_terminal_work_has_no_gate_decision_options(
    gate_project: tuple[Path, AgoraWorkspace, AgoraCommandService],
) -> None:
    _, workspace, service = gate_project
    service.approve_gate(prepared_command(service))
    workspace.transition_work(
        TransitionWorkInput(
            swarm_id="delivery",
            work_id="release",
            actor_id="owner",
            target_state="completed",
        )
    )

    projection = AgoraReadService(workspace).gate_decision_options("delivery", "release")

    assert projection.terminal is True
    assert projection.options == ()
    assert projection.reason == "Work is in a terminal state"


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

    result = service.approve_gate(prepared_command(service, decision=decision))

    assert result.decision == decision
    assert result.role_id == "product-owner"
    assert result.lifecycle.current_state == "verifying"
    assert result.activity.type == event_type
    assert result.activity.actor == "project:owner"
    approvals = workspace.show_work("delivery", "release").approval_roles
    assert ("product-owner" in approvals) is (decision == "approved")
    assert event_type in (root / ".agora" / "activity.md").read_text(encoding="utf-8")


def test_returns_the_exact_activity_from_the_gate_transaction_without_a_latest_event_query(
    gate_project: tuple[Path, AgoraWorkspace, AgoraCommandService],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, workspace, service = gate_project

    def forbidden_latest_event_query(*args: object, **kwargs: object) -> list[object]:
        raise AssertionError("CommandService must not search for a latest Activity event")

    monkeypatch.setattr(workspace, "list_activity", forbidden_latest_event_query)

    result = service.approve_gate(prepared_command(service, decision="rejected"))

    assert result.activity.type == "gate.rejected"
    assert result.activity.actor == "project:owner"
    assert result.activity.source.endswith("/work/release/events.md")


def test_rejects_an_actor_without_gate_authority(
    gate_project: tuple[Path, AgoraWorkspace, AgoraCommandService],
) -> None:
    _, _, service = gate_project

    with pytest.raises(ActorUnauthorizedError) as captured:
        service.prepare_gate_decision(command(actor_id="developer"))

    assert captured.value.to_dict()["code"] == "authority.denied"


def test_lifecycle_exposes_gate_policy_and_typed_blockers_before_decision(
    gate_project: tuple[Path, AgoraWorkspace, AgoraCommandService],
) -> None:
    _, workspace, _ = gate_project

    lifecycle = AgoraReadService(workspace).lifecycle("delivery", "release")
    completion = next(
        transition for transition in lifecycle.transitions if transition.gate_id == "completion"
    )

    assert completion.available is False
    assert completion.required_approval_roles == ("product-owner",)
    assert [blocker.code for blocker in completion.blockers] == ["gate.approvals-missing"]
    assert completion.blockers[0].to_dict()["schema"] == (
        "agora/application/gate-blocker-summary/v1"
    )
    gate = next(item for item in lifecycle.gates if item.id == "completion")
    assert gate.satisfied is False
    assert gate.required_evidence_types == ()


def test_rejects_missing_or_unverified_evidence(
    gate_project: tuple[Path, AgoraWorkspace, AgoraCommandService],
) -> None:
    _, _, service = gate_project

    with pytest.raises(EvidenceMissingError) as captured:
        service.prepare_gate_decision(command(evidence_references=("repo://reports/missing.txt",)))

    assert captured.value.to_dict()["code"] == "gate.evidence-missing"


def test_rejects_a_stale_expected_state(
    gate_project: tuple[Path, AgoraWorkspace, AgoraCommandService],
) -> None:
    _, _, service = gate_project

    with pytest.raises(StalePreconditionError):
        service.prepare_gate_decision(command(expected_state="reviewing"))


def test_rejects_a_different_project_identity(
    gate_project: tuple[Path, AgoraWorkspace, AgoraCommandService],
) -> None:
    _, _, service = gate_project

    with pytest.raises(ProjectIdentityMismatchError):
        service.prepare_gate_decision(command(project_identity="another-project"))


def test_requires_the_existing_signed_action_flow_for_authenticated_actors(
    gate_project: tuple[Path, AgoraWorkspace, AgoraCommandService],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, workspace, service = gate_project
    public_key = (
        Ed25519PrivateKey.generate()
        .public_key()
        .public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    )
    fingerprint = hashlib.sha256(public_key).hexdigest()
    find_actor = workspace._find_actor

    def authenticated_actor(root: Path, actor_id: str):
        actor = find_actor(root, actor_id)
        return replace(
            actor,
            authentication_required=True,
            authentication_algorithm="ed25519",
            authentication_public_key=base64.b64encode(public_key).decode("ascii"),
            authentication_fingerprint=fingerprint,
        )

    monkeypatch.setattr(workspace, "_find_actor", authenticated_actor)

    with pytest.raises(SignatureRequiredError) as captured:
        service.approve_gate(prepared_command(service))

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
    add_external_evidence(
        workspace,
        uri="https://evidence.example.invalid/not-selected",
        digest="9" * 64,
    )
    unsigned = command(
        reason="  Evidence\n\t reviewed and accepted  ",
        evidence_references=(
            " repo://reports/release.txt ",
            "repo://reports/release.txt",
        ),
    )
    prepared = service.prepare_gate_decision(unsigned)
    assert prepared.authentication_required is True
    assert prepared.authentication_algorithm == "ed25519"
    assert prepared.authentication_fingerprint == fingerprint
    assert prepared.authentication_public_key == base64.b64encode(public_key).decode("ascii")
    assert "private" not in prepared.to_json().lower()
    signature = base64.b64encode(
        private_key.sign(prepared.authorization_payload.encode("ascii"))
    ).decode("ascii")
    signed = replace(
        unsigned,
        precondition_digest=prepared.precondition_digest,
        prepared_at=prepared.prepared_at,
        expires_at=prepared.expires_at,
        evidence_content_sha256=prepared.evidence_content_sha256,
        actor_fingerprint=prepared.actor_fingerprint,
        authentication={
            "algorithm": "ed25519",
            "fingerprint": fingerprint,
            "signature": signature,
        },
    )

    result = service.approve_gate(signed)

    assert result.decision == "approved"
    assert result.reason == "Evidence reviewed and accepted"
    assert result.evidence_references == ("repo://reports/release.txt",)
    assert result.evidence_content_sha256 == prepared.evidence_content_sha256
    assert (
        json.loads(prepared.authorization_payload)["evidence_content_sha256"]
        == (prepared.to_dict()["evidence_content_sha256"])
    )
    event = workspace.list_events(
        swarm_id="delivery", work_id="release", type_="approval.added", limit=1
    )[0]
    assert f"authentication={fingerprint}" in event.detail
    durable_digests = json.loads(
        workspace._event_detail_value(event.detail, "evidence-content-sha256") or "{}"
    )
    assert durable_digests == prepared.to_dict()["evidence_content_sha256"]


@pytest.mark.parametrize("failure", ["reason", "fingerprint", "signature"])
def test_signed_gate_decision_is_bound_to_the_exact_prepared_payload(
    gate_project: tuple[Path, AgoraWorkspace, AgoraCommandService],
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
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
    prepared = service.prepare_gate_decision(unsigned)
    signature = base64.b64encode(
        private_key.sign(prepared.authorization_payload.encode("ascii"))
    ).decode("ascii")
    authentication = {
        "algorithm": "ed25519",
        "fingerprint": fingerprint,
        "signature": signature,
    }
    if failure == "reason":
        request = replace(
            unsigned,
            reason="Changed after preparation",
            precondition_digest=prepared.precondition_digest,
            prepared_at=prepared.prepared_at,
            expires_at=prepared.expires_at,
            evidence_content_sha256=prepared.evidence_content_sha256,
            actor_fingerprint=prepared.actor_fingerprint,
            authentication=authentication,
        )
    elif failure == "fingerprint":
        request = replace(
            unsigned,
            precondition_digest=prepared.precondition_digest,
            prepared_at=prepared.prepared_at,
            expires_at=prepared.expires_at,
            evidence_content_sha256=prepared.evidence_content_sha256,
            actor_fingerprint=prepared.actor_fingerprint,
            authentication={**authentication, "fingerprint": "0" * 64},
        )
    else:
        request = replace(
            unsigned,
            precondition_digest=prepared.precondition_digest,
            prepared_at=prepared.prepared_at,
            expires_at=prepared.expires_at,
            evidence_content_sha256=prepared.evidence_content_sha256,
            actor_fingerprint=prepared.actor_fingerprint,
            authentication={
                **authentication,
                "signature": base64.b64encode(b"x" * 64).decode("ascii"),
            },
        )

    expected_error = StalePreconditionError if failure == "reason" else ActorUnauthorizedError
    with pytest.raises(expected_error):
        service.approve_gate(request)


@pytest.mark.parametrize("decision", ["approved", "rejected"])
def test_rejects_double_submission(
    gate_project: tuple[Path, AgoraWorkspace, AgoraCommandService], decision: str
) -> None:
    _, _, service = gate_project
    request = prepared_command(service, decision=decision)
    service.approve_gate(request)

    with pytest.raises(StalePreconditionError):
        service.approve_gate(request)


@pytest.mark.parametrize("offset_seconds, expired", [(899, False), (900, True), (901, True)])
def test_prepared_gate_decision_has_an_exact_utc_expiration_boundary(
    gate_project: tuple[Path, AgoraWorkspace, AgoraCommandService],
    offset_seconds: int,
    expired: bool,
) -> None:
    _, workspace, service = gate_project
    request = prepared_command(service)
    assert request.prepared_at == "2026-08-20T15:00:00Z"
    assert request.expires_at == "2026-08-20T15:15:00Z"
    workspace._now = lambda: TIMESTAMP + timedelta(seconds=offset_seconds)

    if expired:
        with pytest.raises(PreparationExpiredError) as captured:
            service.approve_gate(request)
        assert captured.value.to_dict()["code"] == "command.preparation-expired"
        assert workspace.show_work("delivery", "release").approval_roles == []
    else:
        assert service.approve_gate(request).decision == "approved"


def test_project_can_explicitly_disable_preparation_expiration(
    gate_project: tuple[Path, AgoraWorkspace, AgoraCommandService],
) -> None:
    root, workspace, service = gate_project
    project_path = root / ".agora" / "project.md"
    project = read_markdown(project_path)
    project.attributes["gate-decision-ttl-seconds"] = 0
    project_path.write_text(render_markdown(project), encoding="utf-8")

    request = prepared_command(service)
    assert request.expires_at is None
    workspace._now = lambda: TIMESTAMP + timedelta(days=3650)
    assert service.approve_gate(request).decision == "approved"


def test_signed_actor_replay_after_expiration_is_rejected_before_writes(
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
    raw = command()
    prepared = service.prepare_gate_decision(raw)
    authentication = {
        "algorithm": "ed25519",
        "fingerprint": fingerprint,
        "signature": base64.b64encode(
            private_key.sign(prepared.authorization_payload.encode("ascii"))
        ).decode("ascii"),
    }
    request = replace(
        raw,
        precondition_digest=prepared.precondition_digest,
        prepared_at=prepared.prepared_at,
        expires_at=prepared.expires_at,
        evidence_content_sha256=prepared.evidence_content_sha256,
        actor_fingerprint=prepared.actor_fingerprint,
        authentication=authentication,
    )
    workspace._now = lambda: TIMESTAMP + timedelta(seconds=900)

    with pytest.raises(PreparationExpiredError):
        service.approve_gate(request)
    with pytest.raises(PreparationExpiredError):
        service.approve_gate(request)
    assert workspace.show_work("delivery", "release").approval_roles == []


def test_external_evidence_digest_is_durable_and_stales_a_prepared_decision(
    gate_project: tuple[Path, AgoraWorkspace, AgoraCommandService],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, workspace, service = gate_project
    remote_uri = "https://evidence.example.invalid/report"
    original_digest = "a" * 64
    replacement_digest = "b" * 64
    monkeypatch.setattr(
        "socket.create_connection",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network access")),
    )
    workspace.add_artifact(
        AddArtifactInput(
            swarm_id="delivery",
            work_id="release",
            actor_id="developer",
            kind="external-report",
            uri=remote_uri,
            content_sha256=original_digest,
        )
    )
    workspace.add_evidence(
        AddEvidenceInput(
            swarm_id="delivery",
            work_id="release",
            actor_id="developer",
            type="external-audit",
            result="success",
            artifact_refs=[remote_uri],
        )
    )
    gate = root / ".agora" / "methods" / "scrum" / "gates" / "completion.md"
    gate.write_text(
        gate.read_text(encoding="utf-8").replace(
            "require-successful-evidence: true",
            "require-successful-evidence: true\n"
            'required-evidence-types: ["external-audit"]\n'
            "require-content-addressed-evidence: true",
        ),
        encoding="utf-8",
    )
    raw = command(evidence_references=(remote_uri,))
    request = prepared_command(service, evidence_references=(remote_uri,))
    prepared = service.prepare_gate_decision(raw)
    assert AgoraReadService(workspace).artifacts("delivery", "release")[-1].content_sha256 == (
        original_digest
    )
    assert prepared.precondition_digest == request.precondition_digest

    for name in ("artifacts.md", "evidence.md"):
        path = swarm_dir(root, "delivery") / "work" / "release" / name
        path.write_text(
            path.read_text(encoding="utf-8").replace(original_digest, replacement_digest),
            encoding="utf-8",
        )

    with pytest.raises(GovernedMaterialStaleError) as captured:
        service.approve_gate(request)
    assert captured.value.to_dict()["details"]["stale_reason"] in {
        "evidence-changed",
        "governed-material-changed",
    }


def test_content_addressed_gate_blocks_external_evidence_without_digest(
    gate_project: tuple[Path, AgoraWorkspace, AgoraCommandService],
) -> None:
    root, workspace, service = gate_project
    remote_uri = "https://evidence.example.invalid/informational"
    workspace.add_artifact(
        AddArtifactInput(
            swarm_id="delivery",
            work_id="release",
            actor_id="developer",
            kind="external-report",
            uri=remote_uri,
        )
    )
    workspace.add_evidence(
        AddEvidenceInput(
            swarm_id="delivery",
            work_id="release",
            actor_id="developer",
            type="external-audit",
            result="success",
            artifact_refs=[remote_uri],
        )
    )
    assert workspace.list_work_artifacts("delivery", "release")[-1].content_sha256 is None
    gate = root / ".agora" / "methods" / "scrum" / "gates" / "completion.md"
    gate.write_text(
        gate.read_text(encoding="utf-8").replace(
            "require-successful-evidence: true",
            "require-successful-evidence: true\n"
            'required-evidence-types: ["external-audit"]\n'
            "require-content-addressed-evidence: true",
        ),
        encoding="utf-8",
    )

    approved = next(
        option
        for option in AgoraReadService(workspace)
        .gate_decision_options("delivery", "release")
        .options
        if option.decision == "approved"
    )
    assert any(
        blocker.code == "gate.evidence-content-digest-missing" for blocker in approved.blockers
    )
    with pytest.raises(EvidenceMissingError):
        service.prepare_gate_decision(command(evidence_references=(remote_uri,)))


@pytest.mark.parametrize("digest", ["a" * 63, "A" * 64, "not-a-digest"])
def test_rejects_invalid_declared_external_artifact_digest(
    gate_project: tuple[Path, AgoraWorkspace, AgoraCommandService], digest: str
) -> None:
    _, workspace, _ = gate_project

    with pytest.raises(ValueError, match="64 lowercase hexadecimal"):
        workspace.add_artifact(
            AddArtifactInput(
                swarm_id="delivery",
                work_id="release",
                actor_id="developer",
                kind="external-report",
                uri="https://evidence.example.invalid/report",
                content_sha256=digest,
            )
        )


def test_maps_an_intermediate_write_failure_and_rolls_back_every_record(
    gate_project: tuple[Path, AgoraWorkspace, AgoraCommandService],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, workspace, service = gate_project
    work_root = swarm_dir(root, "delivery") / "work" / "release"
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
        service.approve_gate(prepared_command(service))

    assert captured.value.to_dict()["code"] == "transaction.commit-failed"
    assert {path: path.read_bytes() for path in paths} == before
    assert workspace.show_work("delivery", "release").approval_roles == []


def test_surfaces_an_indeterminate_transaction_when_rollback_also_fails(
    gate_project: tuple[Path, AgoraWorkspace, AgoraCommandService],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, service = gate_project
    from agora import filesystem

    original = filesystem._atomic_write_direct
    calls = 0

    def fail_commit_and_rollback(path: Path, contents: str) -> None:
        nonlocal calls
        calls += 1
        if calls in {2, 3}:
            raise OSError(f"injected failure {calls}")
        original(path, contents)

    monkeypatch.setattr(filesystem, "_atomic_write_direct", fail_commit_and_rollback)

    with pytest.raises(TransactionIndeterminateError) as captured:
        service.approve_gate(prepared_command(service))

    payload = captured.value.to_dict()
    assert payload["code"] == "transaction.indeterminate"
    assert payload["retryable"] is False
    assert "inspect Git" in payload["recovery_hint"]
    assert "write_set" not in payload["details"]


def test_maps_verified_rollback_failure_from_the_real_command_service(
    gate_project: tuple[Path, AgoraWorkspace, AgoraCommandService],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, workspace, service = gate_project
    from agora import filesystem

    original = filesystem._atomic_write_direct
    calls = 0

    def restore_then_report_error(path: Path, contents: str) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected commit failure")
        original(path, contents)
        if calls == 3:
            raise OSError("injected rollback report after restoration")

    monkeypatch.setattr(filesystem, "_atomic_write_direct", restore_then_report_error)

    with pytest.raises(TransactionRollbackError) as captured:
        service.approve_gate(prepared_command(service))

    payload = captured.value.to_dict()
    assert payload["code"] == "transaction.rollback-failed"
    assert payload["category"] == "transaction"
    assert payload["retryable"] is False
    assert "verification matched" in payload["recovery_hint"]
    assert payload["details"] == {
        "phase": "rollback",
        "write_count": 3,
        "rollback_error_count": 1,
        "verification_error_count": 0,
    }
    assert workspace.show_work("delivery", "release").approval_roles == []


def test_maps_an_interleaved_external_transaction_edit_to_stale_without_partial_decision(
    gate_project: tuple[Path, AgoraWorkspace, AgoraCommandService],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, workspace, service = gate_project
    from agora import filesystem

    work_root = swarm_dir(root, "delivery") / "work" / "release"
    approvals = work_root / "approvals.md"
    events = work_root / "events.md"
    approvals_before = approvals.read_bytes()
    original = filesystem._atomic_write_direct
    writes = 0

    def external_edit_between_writes(path: Path, contents: str) -> None:
        nonlocal writes
        writes += 1
        original(path, contents)
        if writes == 1:
            events.write_text(
                events.read_text(encoding="utf-8") + "\nExternal editor event.\n",
                encoding="utf-8",
            )

    monkeypatch.setattr(filesystem, "_atomic_write_direct", external_edit_between_writes)

    with pytest.raises(GovernedMaterialStaleError) as captured:
        service.approve_gate(prepared_command(service))

    assert captured.value.to_dict()["details"]["stale_reason"] == "external-edit"
    assert approvals.read_bytes() == approvals_before
    assert "External editor event." in events.read_text(encoding="utf-8")
    assert workspace.show_work("delivery", "release").approval_roles == []


def test_translates_domain_failures_by_type_and_never_by_message(
    gate_project: tuple[Path, AgoraWorkspace, AgoraCommandService],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, workspace, service = gate_project
    request = prepared_command(service)

    def typed_failure(_input: object) -> object:
        raise EvidenceMissingRuleError("opaque domain failure")

    monkeypatch.setattr(workspace, "decide_gate", typed_failure)
    with pytest.raises(EvidenceMissingError, match="opaque domain failure"):
        service.approve_gate(request)

    def misleading_untyped_failure(_input: object) -> object:
        raise ValueError("evidence project identity mismatch already resolved")

    monkeypatch.setattr(workspace, "decide_gate", misleading_untyped_failure)
    with pytest.raises(InvalidCommandError):
        service.approve_gate(request)


def test_ambiguous_gate_role_fails_as_a_controlled_invalid_command(
    gate_project: tuple[Path, AgoraWorkspace, AgoraCommandService],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, workspace, service = gate_project
    request = prepared_command(service)

    def ambiguous_role(_input: object) -> object:
        raise GateDecisionRoleRuleError("No unique gate role is available")

    monkeypatch.setattr(workspace, "decide_gate", ambiguous_role)
    with pytest.raises(InvalidCommandError, match="No unique gate role"):
        service.approve_gate(request)
