import base64
import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from conftest import swarm_dir
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from agora.application import (
    ActorUnauthorizedError,
    AgoraCommandService,
    AmendBudgetCommand,
    GovernedMaterialStaleError,
    InvalidCommandError,
    TransactionCommitError,
)
from agora.model import (
    AddActorInput,
    AddUsageInput,
    AssignActorInput,
    CreateSwarmInput,
    CreateWorkInput,
    DecomposeWorkInput,
    InitInput,
)
from agora.workspace import AgoraWorkspace

NOW = datetime(2026, 8, 20, 12, tzinfo=UTC)


@pytest.fixture
def budget_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, AgoraWorkspace, AgoraCommandService]:
    root = tmp_path / "budget-project"
    root.mkdir()
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    workspace = AgoraWorkspace(cwd=root, now=lambda: NOW)
    workspace.initialize(InitInput(integration="generic", default_method="scrum"))
    workspace.add_actor(
        AddActorInput(
            id="owner",
            name="Owner",
            kind="human",
            capabilities=["backlog-management", "acceptance"],
            scope="project",
        )
    )
    workspace.add_actor(
        AddActorInput(
            id="developer",
            name="Developer",
            kind="ai-agent",
            capabilities=["implementation"],
            scope="project",
        )
    )
    workspace.add_actor(
        AddActorInput(
            id="facilitator",
            name="Facilitator",
            kind="human",
            capabilities=["facilitation", "governance"],
            scope="project",
        )
    )
    workspace.create_swarm(
        CreateSwarmInput(id="delivery", objective="Deliver", create_branch=False)
    )
    workspace.assign_actor(
        AssignActorInput(swarm_id="delivery", role_id="product-owner", actor_id="owner")
    )
    workspace.assign_actor(
        AssignActorInput(swarm_id="delivery", role_id="developer", actor_id="developer")
    )
    workspace.assign_actor(
        AssignActorInput(swarm_id="delivery", role_id="scrum-master", actor_id="facilitator")
    )
    workspace.create_work(
        CreateWorkInput(
            swarm_id="delivery",
            id="parent",
            title="Parent",
            actor_id="owner",
            acceptance_criteria=[("done", "Done")],
        )
    )
    parent = workspace.show_work("delivery", "parent")
    parent.budget_limits = {"effort": 20}
    (Path(parent.path) / "WORK.md").write_text(workspace._render_work(parent), encoding="utf-8")
    workspace.decompose_work(
        DecomposeWorkInput(
            swarm_id="delivery",
            parent_work_id="parent",
            child_work_id="child",
            title="Child",
            actor_id="owner",
            acceptance_criteria=[("done", "Done")],
        )
    )
    return root, workspace, AgoraCommandService(workspace)


def command(amendment_id: str = "increase-child", **changes: object) -> AmendBudgetCommand:
    values: dict[str, object] = {
        "project_identity": "budget-project",
        "parent_swarm_id": "delivery",
        "parent_work_id": "parent",
        "child_swarm_id": "delivery",
        "child_work_id": "child",
        "amendment_id": amendment_id,
        "actor_id": "owner",
        "role_id": "product-owner",
        "proposed_limits": {"effort": 10},
        "reason": "Fund the delegated work",
    }
    values.update(changes)
    return AmendBudgetCommand(**values)  # type: ignore[arg-type]


def prepared(service: AgoraCommandService, value: AmendBudgetCommand) -> AmendBudgetCommand:
    projection = service.prepare_budget_amendment(value)
    return replace(
        value,
        reason=projection.reason,
        evidence_references=projection.evidence_references,
        precondition_digest=projection.precondition_digest,
        prepared_at=projection.prepared_at,
        expires_at=projection.expires_at,
    )


def test_prepares_and_applies_an_auditable_budget_amendment(
    budget_project: tuple[Path, AgoraWorkspace, AgoraCommandService],
) -> None:
    root, workspace, service = budget_project
    value = command()
    preparation = service.prepare_budget_amendment(value)

    assert preparation.schema == "agora/application/prepared-budget-amendment/v1"
    assert preparation.previous_limits == {}
    assert preparation.proposed_limits == {"effort": 10}
    assert preparation.consumed == {}
    assert json.loads(preparation.authorization_payload)["authorization_schema"].endswith("/v1")

    result = service.amend_budget(prepared(service, value))

    assert result.schema == "agora/application/budget-amendment-projection/v1"
    assert result.remaining == {"effort": 10}
    assert result.activity.type == "budget.amended"
    assert workspace.show_work("delivery", "child").budget_limits == {"effort": 10}
    amendment = (
        swarm_dir(root, "delivery")
        / "work"
        / "child"
        / "budget-amendments"
        / "increase-child"
        / "AMENDMENT.md"
    )
    assert amendment.is_file()
    assert "agora/budget-amendment/v1" in amendment.read_text(encoding="utf-8")
    validation = workspace.validate()
    assert validation.ok, validation.issues
    assert validation.checked["budget-amendments"] == 1


def test_rejects_child_authority_parent_capacity_and_consumed_floor(
    budget_project: tuple[Path, AgoraWorkspace, AgoraCommandService],
) -> None:
    _, workspace, service = budget_project
    with pytest.raises(ActorUnauthorizedError):
        service.prepare_budget_amendment(command(actor_id="developer", role_id="developer"))
    with pytest.raises(InvalidCommandError, match="parent capacity"):
        service.prepare_budget_amendment(command(proposed_limits={"effort": 21}))

    service.amend_budget(prepared(service, command()))
    workspace.add_usage(
        AddUsageInput(
            id="spent",
            swarm_id="delivery",
            work_id="child",
            actor_id="developer",
            amounts={"effort": 7},
            evidence_refs=["repo://usage-receipt"],
        )
    )
    with pytest.raises(InvalidCommandError, match="below consumed"):
        service.prepare_budget_amendment(command("reduce-child", proposed_limits={"effort": 6}))


def test_rejects_stale_material_without_writes(
    budget_project: tuple[Path, AgoraWorkspace, AgoraCommandService],
) -> None:
    root, _, service = budget_project
    request = prepared(service, command())
    child = swarm_dir(root, "delivery") / "work" / "child" / "WORK.md"
    child.write_text(child.read_text(encoding="utf-8") + "\nExternal note.\n", encoding="utf-8")

    with pytest.raises(GovernedMaterialStaleError):
        service.amend_budget(request)
    assert not (child.parent / "budget-amendments" / "increase-child").exists()


@pytest.mark.parametrize("fail_at", [1, 2, 3, 4])
def test_rolls_back_every_budget_record_on_each_write_failure(
    budget_project: tuple[Path, AgoraWorkspace, AgoraCommandService],
    monkeypatch: pytest.MonkeyPatch,
    fail_at: int,
) -> None:
    root, workspace, service = budget_project
    request = prepared(service, command())
    child_root = swarm_dir(root, "delivery") / "work" / "child"
    tracked = [child_root / "WORK.md", child_root / "events.md", root / ".agora" / "activity.md"]
    before = {path: path.read_bytes() for path in tracked}
    from agora import filesystem

    original = filesystem._atomic_write_direct
    calls = 0

    def fail_selected(path: Path, contents: str) -> None:
        nonlocal calls
        calls += 1
        if calls == fail_at:
            raise OSError("injected budget failure")
        original(path, contents)

    monkeypatch.setattr(filesystem, "_atomic_write_direct", fail_selected)
    with pytest.raises(TransactionCommitError):
        service.amend_budget(request)

    assert {path: path.read_bytes() for path in tracked} == before
    assert workspace.show_work("delivery", "child").budget_limits == {}
    assert not (child_root / "budget-amendments" / "increase-child").exists()


def test_signed_parent_authority_applies_the_exact_prepared_amendment(
    budget_project: tuple[Path, AgoraWorkspace, AgoraCommandService],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, workspace, service = budget_project
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
    preparation = service.prepare_budget_amendment(raw)
    signature = base64.b64encode(
        private_key.sign(preparation.authorization_payload.encode("ascii"))
    ).decode("ascii")
    request = replace(
        raw,
        precondition_digest=preparation.precondition_digest,
        prepared_at=preparation.prepared_at,
        expires_at=preparation.expires_at,
        authentication={
            "algorithm": "ed25519",
            "fingerprint": fingerprint,
            "signature": signature,
        },
    )

    result = service.amend_budget(request)

    assert result.proposed_limits == {"effort": 10}
    assert result.actor_id == "project:owner"
