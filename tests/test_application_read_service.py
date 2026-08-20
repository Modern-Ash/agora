import hashlib
import io
import json
import re
import subprocess
import threading
import time
from dataclasses import FrozenInstanceError, asdict
from datetime import UTC, datetime
from pathlib import Path

import pytest

from agora.application import (
    ActivityFilters,
    ActorFilters,
    AgoraReadService,
    ApproveGateCommand,
    ConcurrentDurableEditError,
    InvalidDurableStateError,
    InvalidReadQueryError,
    ProjectNotFoundError,
    ReadResourceNotFoundError,
    SessionFilters,
    SwarmFilters,
    WorkItemFilters,
    approve_gate_authorization_payload,
)
from agora.application.dto import ArtifactSummary, SerializableDTO
from agora.cli import main
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
    StartSessionInput,
)
from agora.workspace import AgoraWorkspace

TIMESTAMP = datetime(2026, 8, 20, 12, tzinfo=UTC)


@pytest.fixture
def read_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, AgoraWorkspace, AgoraReadService]:
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    workspace = AgoraWorkspace(cwd=root, now=lambda: TIMESTAMP)
    workspace.initialize(
        InitInput(
            integration="generic",
            provider="local-provider",
            model="local-model",
            default_method="scrum",
        )
    )
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
        CreateSwarmInput(id="delivery", objective="Deliver governed work", create_branch=False)
    )
    for role, actor_id in (
        ("product-owner", "owner"),
        ("scrum-master", "facilitator"),
        ("developer", "developer"),
    ):
        workspace.assign_actor(
            AssignActorInput(swarm_id="delivery", role_id=role, actor_id=actor_id)
        )
    workspace.create_work(
        CreateWorkInput(
            swarm_id="delivery",
            id="read-boundary",
            title="Expose reusable reads",
            description="Return durable state without CLI presentation concerns.",
            actor_id="owner",
            acceptance_criteria=[("contract", "Expose a versioned contract")],
            required_artifacts=["test-report"],
        )
    )
    workspace.create_work(
        CreateWorkInput(
            swarm_id="delivery",
            id="unrelated-work",
            title="Remain unrelated",
            actor_id="owner",
        )
    )
    workspace.block_work(
        ChangeWorkStatusInput(
            swarm_id="delivery",
            work_id="unrelated-work",
            actor_id="developer",
            reason="Wait for another durable record",
            id="block-unrelated",
        )
    )
    report = root / "reports" / "read-service.txt"
    report.parent.mkdir()
    report.write_text("verified\n", encoding="utf-8")
    workspace.add_artifact(
        AddArtifactInput(
            swarm_id="delivery",
            work_id="read-boundary",
            actor_id="developer",
            kind="test-report",
            uri="repo://reports/read-service.txt",
        )
    )
    workspace.add_evidence(
        AddEvidenceInput(
            swarm_id="delivery",
            work_id="read-boundary",
            actor_id="developer",
            type="test-run",
            result="success",
            artifact_refs=["repo://reports/read-service.txt"],
        )
    )
    workspace.add_approval(
        AddApprovalInput(
            swarm_id="delivery",
            work_id="read-boundary",
            actor_id="owner",
            role_id="product-owner",
            note="Read boundary accepted",
        )
    )
    return root, workspace, AgoraReadService(workspace)


def test_serializes_deeply_immutable_versioned_dtos(
    read_project: tuple[Path, AgoraWorkspace, AgoraReadService],
) -> None:
    _, _, service = read_project

    detail = service.get_work_item("delivery", "read-boundary")
    payload = json.loads(detail.to_json())

    assert payload == detail.to_dict()
    assert payload["schema"] == "agora/application/work-item-detail/v3"
    assert payload["acceptance_criteria"] == {"contract": "Expose a versioned contract"}
    assert payload["artifacts"][0]["schema"] == "agora/application/artifact-summary/v3"
    assert "path" not in json.dumps(payload)
    with pytest.raises(FrozenInstanceError):
        detail.title = "mutated"  # type: ignore[misc]
    with pytest.raises(TypeError):
        detail.acceptance_criteria["other"] = "mutated"  # type: ignore[index]

    assert payload["artifacts"][0]["produced_by"] == "project:developer"
    assert payload["evidence"][0]["timestamp"] == "2026-08-20T12:00:00Z"
    assert payload["approvals"][0]["actor"] == "project:owner"
    assert payload["approvals"][0]["decision"] == "approved"
    assert payload["artifacts"][0]["activity"] is None

    query_payload = json.loads(WorkItemFilters(swarm_id="delivery").to_json())
    assert query_payload == {
        "operational_status": None,
        "schema": "agora/application/work-item-filters/v1",
        "state": None,
        "swarm_id": "delivery",
    }


def test_reads_a_valid_project_with_values_equivalent_to_workspace_reads(
    read_project: tuple[Path, AgoraWorkspace, AgoraReadService],
) -> None:
    _, workspace, service = read_project
    current_status = workspace.status()
    overview = service.project_overview()
    assert overview.project == current_status.project
    assert dict(overview.counts) == current_status.counts
    assert dict(overview.work_states) == current_status.work_states
    assert {key: list(value) for key, value in overview.attention.items()} == (
        current_status.attention
    )

    actor_records = workspace.list_actors()
    actor_summaries = service.list_actors()
    assert [(item.reference, item.kind) for item in actor_summaries] == [
        (item.reference, item.kind) for item in actor_records
    ]

    swarm_records = workspace.list_swarms()
    swarm_summaries = service.list_swarms()
    assert [(item.id, item.status, dict(item.assignments)) for item in swarm_summaries] == [
        (item.id, item.status, item.assignments) for item in swarm_records
    ]

    work_records = workspace.list_work()
    work_summaries = service.list_work_items()
    assert [(item.swarm_id, item.id, item.state) for item in work_summaries] == [
        (item.swarm_id, item.id, item.state) for item in work_records
    ]

    current_activity = workspace.list_activity(swarm_id="delivery", limit=100)
    activity = service.activity(ActivityFilters(swarm_id="delivery", limit=100))
    assert [(item.timestamp, item.type, item.source) for item in activity] == [
        (item.timestamp, item.type, item.source) for item in current_activity
    ]

    current_artifacts = [
        (item.kind, item.uri) for item in workspace.list_work_artifacts("delivery", "read-boundary")
    ]
    assert [(item.kind, item.uri) for item in service.artifacts("delivery", "read-boundary")] == (
        current_artifacts
    )


def test_applies_work_and_activity_filters(
    read_project: tuple[Path, AgoraWorkspace, AgoraReadService],
) -> None:
    _, _, service = read_project

    blocked = service.list_work_items(
        WorkItemFilters(swarm_id="delivery", operational_status="blocked")
    )
    assert [item.id for item in blocked] == ["unrelated-work"]
    assert service.list_work_items(WorkItemFilters(state="missing-state")) == ()

    created = service.activity(
        ActivityFilters(swarm_id="delivery", work_id="read-boundary", type="work.created")
    )
    assert len(created) == 1
    assert created[0].work_id == "read-boundary"
    with pytest.raises(InvalidReadQueryError, match="require a swarm"):
        service.activity(ActivityFilters(work_id="read-boundary"))
    with pytest.raises(InvalidReadQueryError, match="positive integer"):
        service.activity(ActivityFilters(limit=0))


def test_applies_actor_and_swarm_filters(
    read_project: tuple[Path, AgoraWorkspace, AgoraReadService],
) -> None:
    _, workspace, service = read_project
    status = workspace.show_swarm("delivery").status

    assert [item.reference for item in service.list_actors(ActorFilters(scope="project"))] == [
        item.reference for item in workspace.list_actors("project")
    ]
    assert [item.id for item in service.list_swarms(SwarmFilters(status=status))] == ["delivery"]
    assert service.list_swarms(SwarmFilters(status="missing-status")) == ()
    with pytest.raises(InvalidReadQueryError, match="Actor scope"):
        service.list_actors(ActorFilters(scope="outside"))


def test_reads_sessions_without_exposing_paths_or_internal_records(
    read_project: tuple[Path, AgoraWorkspace, AgoraReadService],
) -> None:
    root, workspace, service = read_project
    durable = workspace.start_session(
        StartSessionInput(
            id="studio-read",
            actor_id="developer",
            swarm_id="delivery",
            work_id="read-boundary",
            launch=False,
        )
    )

    session = service.get_session("studio-read")
    payload = session.to_dict()

    assert service.list_sessions(SessionFilters(status="prepared")) == (session,)
    assert payload["schema"] == "agora/application/session-summary/v1"
    assert payload["record_uri"] == "repo://.agora/sessions/studio-read/SESSION.md"
    assert payload["context_uri"] == "repo://.agora/sessions/studio-read/CONTEXT.md"
    assert "path" not in payload
    assert str(root) not in session.to_json()
    assert durable.path != session.record_uri


def test_every_read_contract_is_json_serializable_immutable_and_rejects_path_values(
    read_project: tuple[Path, AgoraWorkspace, AgoraReadService],
) -> None:
    _, workspace, service = read_project
    workspace.start_session(
        StartSessionInput(
            id="contract-session",
            actor_id="developer",
            swarm_id="delivery",
            work_id="read-boundary",
            launch=False,
        )
    )
    lifecycle = service.lifecycle("delivery", "read-boundary")
    values: tuple[SerializableDTO, ...] = (
        service.project_overview(),
        service.list_actors()[0],
        service.list_swarms()[0],
        service.list_work_items()[0],
        service.get_work_item("delivery", "read-boundary"),
        service.list_sessions()[0],
        service.get_method("delivery"),
        lifecycle,
        lifecycle.states[0],
        lifecycle.transitions[0],
        lifecycle.gates[0],
        service.artifacts("delivery", "read-boundary")[0],
        service.evidence("delivery", "read-boundary")[0],
        service.approvals("delivery", "read-boundary")[0],
        service.activity(ActivityFilters(limit=1))[0],
        service.work_traceability("delivery", "read-boundary"),
        service.specification_history("delivery", "read-boundary"),
        service.specification_revision("delivery", "read-boundary", "invalid"),
        service.gate_decision_options("delivery", "read-boundary"),
        service.work_control_projection("delivery", "read-boundary"),
    )

    for value in values:
        assert json.loads(value.to_json()) == value.to_dict()
        assert value.to_dict()["schema"].startswith("agora/application/")
        assert "PosixPath" not in value.to_json()

    with pytest.raises(TypeError, match="cannot expose pathlib.Path"):
        ArtifactSummary(
            kind="spec",
            uri="repo://docs/spec.md",
            content_sha256=None,
            produced_by=Path("outside"),  # type: ignore[arg-type]
            timestamp="2026-08-20T12:00:00Z",
        )


def test_projects_complete_method_topology_and_core_calculated_availability(
    read_project: tuple[Path, AgoraWorkspace, AgoraReadService],
) -> None:
    _, _, service = read_project

    method = service.get_method("delivery")
    lifecycle = service.lifecycle("delivery", "read-boundary")

    assert method.schema == "agora/application/method-summary/v2"
    assert [state.id for state in method.states] == [
        "specified",
        "planned",
        "implementing",
        "reviewing",
        "verifying",
        "completed",
    ]
    assert method.states[0].initial is True
    assert method.states[-1].terminal is True
    assert any(transition.authorized_roles for transition in method.transitions)
    current = [
        transition
        for transition in lifecycle.transitions
        if transition.source == lifecycle.current_state
    ]
    assert current
    assert all(transition.available is not None for transition in lifecycle.transitions)
    assert lifecycle.schema == "agora/application/lifecycle-projection/v3"
    assert lifecycle.gates[0].required_approval_roles == ("product-owner",)


def test_reads_traceability_without_inferred_material_activity_links(
    read_project: tuple[Path, AgoraWorkspace, AgoraReadService],
) -> None:
    _, _, service = read_project

    traceability = service.work_traceability("delivery", "read-boundary")

    assert traceability.schema == "agora/application/traceability-summary/v2"
    assert traceability.artifacts[0].activity is None
    assert traceability.evidence[0].activity is None
    assert any(event.type == "artifact.added" for event in traceability.activity)


def test_reads_bounded_specification_history_from_the_registered_artifact(
    read_project: tuple[Path, AgoraWorkspace, AgoraReadService],
) -> None:
    root, workspace, service = read_project
    specification = root / "docs" / "spec.md"
    specification.parent.mkdir(exist_ok=True)
    specification.write_text("# Version one\n", encoding="utf-8")
    workspace.add_artifact(
        AddArtifactInput(
            swarm_id="delivery",
            work_id="read-boundary",
            actor_id="developer",
            kind="spec",
            uri="repo://docs/spec.md",
        )
    )
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "Agora Test"], check=True)
    subprocess.run(
        ["git", "-C", str(root), "config", "user.email", "agora@example.invalid"],
        check=True,
    )
    subprocess.run(["git", "-C", str(root), "add", "docs/spec.md"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "docs: add spec"], check=True)
    specification.write_text("# Version two\n", encoding="utf-8")

    history = service.specification_history("delivery", "read-boundary")

    assert history.schema == "agora/application/specification-summary/v1"
    assert history.available is True
    assert history.working_tree is True
    assert [revision.kind for revision in history.revisions] == ["working-tree", "commit"]
    assert history.revisions[1].schema == ("agora/application/specification-revision-summary/v1")


def test_reads_safe_commit_and_working_tree_specification_revision_details(
    read_project: tuple[Path, AgoraWorkspace, AgoraReadService],
) -> None:
    root, workspace, service = read_project
    specification = root / "docs" / "spec-detail.md"
    specification.parent.mkdir(exist_ok=True)
    specification.write_text("# Version one\n", encoding="utf-8")
    workspace.add_artifact(
        AddArtifactInput(
            swarm_id="delivery",
            work_id="read-boundary",
            actor_id="developer",
            kind="spec",
            uri="repo://docs/spec-detail.md",
        )
    )
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "Agora Test"], check=True)
    subprocess.run(
        ["git", "-C", str(root), "config", "user.email", "agora@example.invalid"],
        check=True,
    )
    subprocess.run(["git", "-C", str(root), "add", "docs/spec-detail.md"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "docs: add spec"], check=True)
    sha = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    specification.write_text("# Version two\n\nChanged safely.\n", encoding="utf-8")

    committed = service.specification_revision("delivery", "read-boundary", sha)
    working = service.specification_revision("delivery", "read-boundary", "working-tree")

    assert committed.schema == ("agora/application/specification-revision-detail/v1")
    assert committed.available is True
    assert committed.kind == "commit"
    assert committed.content == "# Version one\n"
    assert committed.diff is not None and "Version one" in committed.diff
    assert working.available is True
    assert working.kind == "working-tree"
    assert working.previous_revision_id == sha
    assert working.content == "# Version two\n\nChanged safely.\n"
    assert working.diff is not None and "+Changed safely." in working.diff
    assert str(root) not in working.to_json()


def test_specification_revision_bounds_large_and_binary_content(
    read_project: tuple[Path, AgoraWorkspace, AgoraReadService],
) -> None:
    root, workspace, service = read_project
    specification = root / "docs" / "bounded-spec.md"
    specification.parent.mkdir(exist_ok=True)
    specification.write_text("initial\n", encoding="utf-8")
    workspace.add_artifact(
        AddArtifactInput(
            swarm_id="delivery",
            work_id="read-boundary",
            actor_id="developer",
            kind="spec",
            uri="repo://docs/bounded-spec.md",
        )
    )
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "Agora Test"], check=True)
    subprocess.run(
        ["git", "-C", str(root), "config", "user.email", "agora@example.invalid"],
        check=True,
    )
    subprocess.run(["git", "-C", str(root), "add", "docs/bounded-spec.md"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "docs: add spec"], check=True)

    specification.write_text("line\n" * 40_000, encoding="utf-8")
    large = service.specification_revision("delivery", "read-boundary", "working-tree")
    assert large.size_bytes == 200_000
    assert large.content_truncated is True
    assert large.content is not None and len(large.content.splitlines()) <= 2_000

    specification.write_bytes(b"binary\0contents")
    binary = service.specification_revision("delivery", "read-boundary", "working-tree")
    assert binary.available is True
    assert binary.binary is True
    assert binary.encoding == "binary"
    assert binary.content is None


def test_specification_revision_invalid_sha_and_git_timeout_are_safe_projections(
    read_project: tuple[Path, AgoraWorkspace, AgoraReadService],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, workspace, service = read_project
    specification = root / "docs" / "timeout-spec.md"
    specification.parent.mkdir(exist_ok=True)
    specification.write_text("tracked\n", encoding="utf-8")
    workspace.add_artifact(
        AddArtifactInput(
            swarm_id="delivery",
            work_id="read-boundary",
            actor_id="developer",
            kind="spec",
            uri="repo://docs/timeout-spec.md",
        )
    )
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "Agora Test"], check=True)
    subprocess.run(
        ["git", "-C", str(root), "config", "user.email", "agora@example.invalid"],
        check=True,
    )
    subprocess.run(["git", "-C", str(root), "add", "docs/timeout-spec.md"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "docs: add spec"], check=True)
    sha = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    invalid = service.specification_revision("delivery", "read-boundary", "--help")
    assert invalid.available is False
    assert invalid.reason == "Specification revision id is invalid"

    from agora import git

    original = git.subprocess.run

    def timeout_show(*args: object, **kwargs: object):
        command = args[0]
        if isinstance(command, list) and "show" in command:
            raise subprocess.TimeoutExpired(command, 5)
        return original(*args, **kwargs)

    monkeypatch.setattr(git.subprocess, "run", timeout_show)
    timed_out = service.specification_revision("delivery", "read-boundary", sha)
    assert timed_out.available is False
    assert timed_out.reason == "Git could not read specification revision"


def test_work_control_projection_is_consistent_and_reuses_core_contracts(
    read_project: tuple[Path, AgoraWorkspace, AgoraReadService],
) -> None:
    _, _, service = read_project

    projection = service.work_control_projection("delivery", "read-boundary")

    assert projection.schema == "agora/application/work-control-projection/v3"
    assert re.fullmatch(r"[0-9a-f]{64}", projection.snapshot_token)
    assert projection.work.schema == "agora/application/work-item-detail/v3"
    assert projection.lifecycle.current_state == projection.work.state
    assert projection.traceability.state == projection.work.state
    assert projection.artifacts == projection.work.artifacts
    assert projection.evidence == projection.work.evidence
    assert projection.approvals == projection.work.approvals
    assert projection.gate_decision_options.current_state == projection.work.state


def test_work_control_projection_serializes_an_interleaved_core_mutation(
    read_project: tuple[Path, AgoraWorkspace, AgoraReadService],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, workspace, service = read_project
    workspace.lock_timeout = 1
    started = threading.Event()
    errors: list[BaseException] = []

    def mutate() -> None:
        started.set()
        try:
            workspace.add_evidence(
                AddEvidenceInput(
                    swarm_id="delivery",
                    work_id="read-boundary",
                    actor_id="developer",
                    type="late-review",
                    result="success",
                    artifact_refs=["repo://reports/read-service.txt"],
                )
            )
        except BaseException as error:  # pragma: no cover - surfaced below
            errors.append(error)

    original = service.get_work_item
    thread: threading.Thread | None = None

    def start_mutation(swarm_id: str, work_id: str):
        nonlocal thread
        work = original(swarm_id, work_id)
        thread = threading.Thread(target=mutate)
        thread.start()
        assert started.wait(timeout=1)
        time.sleep(0.05)
        assert thread.is_alive(), "Core mutation must wait for the projection snapshot lock"
        return work

    monkeypatch.setattr(service, "get_work_item", start_mutation)

    projection = service.work_control_projection("delivery", "read-boundary")
    assert thread is not None
    thread.join(timeout=2)

    assert not thread.is_alive()
    assert errors == []
    assert {item.type for item in projection.evidence} == {"test-run"}
    assert {item.type for item in service.evidence("delivery", "read-boundary")} == {
        "test-run",
        "late-review",
    }


def test_rejects_missing_or_invalid_projects(tmp_path: Path) -> None:
    missing = AgoraReadService.from_path(tmp_path)
    with pytest.raises(ProjectNotFoundError) as missing_error:
        missing.project_overview()
    assert missing_error.value.to_dict()["code"] == "read.project-not-found"


def test_rejects_malformed_durable_project_state(
    read_project: tuple[Path, AgoraWorkspace, AgoraReadService],
) -> None:
    root, _, service = read_project
    manifest = root / ".agora" / "project.md"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            'schema: "agora/project/v1"', 'schema: "agora/project/invalid"'
        ),
        encoding="utf-8",
    )

    with pytest.raises(InvalidDurableStateError) as error:
        service.project_overview()
    assert error.value.to_dict()["code"] == "read.invalid-durable-state"


@pytest.mark.parametrize(
    "operation",
    ["detail", "lifecycle", "artifacts", "evidence", "approvals", "traceability", "specification"],
)
def test_rejects_invalid_slugs_before_resolving_records(
    read_project: tuple[Path, AgoraWorkspace, AgoraReadService], operation: str
) -> None:
    _, _, service = read_project
    calls = {
        "detail": service.get_work_item,
        "lifecycle": service.lifecycle,
        "artifacts": service.artifacts,
        "evidence": service.evidence,
        "approvals": service.approvals,
        "traceability": service.work_traceability,
        "specification": service.specification_history,
    }

    with pytest.raises(InvalidReadQueryError, match=r"must match /\^"):
        calls[operation]("../outside", "read-boundary")

    with pytest.raises(InvalidReadQueryError, match=r"must match /\^"):
        service.get_session("../outside")


def test_reports_missing_durable_records(
    read_project: tuple[Path, AgoraWorkspace, AgoraReadService],
) -> None:
    _, _, service = read_project

    with pytest.raises(ReadResourceNotFoundError) as error:
        service.get_work_item("delivery", "missing-work")
    assert error.value.to_dict()["code"] == "read.resource-not-found"


def test_rejects_repository_artifact_paths_resolving_outside_project(
    read_project: tuple[Path, AgoraWorkspace, AgoraReadService], tmp_path: Path
) -> None:
    root, _, service = read_project
    outside = tmp_path / "outside.txt"
    outside.write_text("outside\n", encoding="utf-8")
    (root / "escape.txt").symlink_to(outside)
    artifacts_path = (
        root / ".agora" / "swarms" / "delivery" / "work" / "read-boundary" / "artifacts.md"
    )
    artifacts_path.write_text(
        f"{artifacts_path.read_text(encoding='utf-8').rstrip()}\n"
        "| test-report | repo://escape.txt | none | project:developer | "
        f"{TIMESTAMP.isoformat()} |\n",
        encoding="utf-8",
    )

    with pytest.raises(InvalidDurableStateError, match="escapes the project"):
        service.artifacts("delivery", "read-boundary")
    with pytest.raises(InvalidDurableStateError, match="escapes the project"):
        service.work_traceability("delivery", "read-boundary")
    with pytest.raises(InvalidDurableStateError, match="escapes the project"):
        service.specification_revision("delivery", "read-boundary", "working-tree")


def test_specification_revision_rejects_repository_uri_traversal(
    read_project: tuple[Path, AgoraWorkspace, AgoraReadService],
) -> None:
    root, _, service = read_project
    artifacts_path = (
        root / ".agora" / "swarms" / "delivery" / "work" / "read-boundary" / "artifacts.md"
    )
    artifacts_path.write_text(
        f"{artifacts_path.read_text(encoding='utf-8').rstrip()}\n"
        f"| spec | repo://../outside.md | none | project:developer | {TIMESTAMP.isoformat()} |\n",
        encoding="utf-8",
    )

    with pytest.raises(InvalidDurableStateError, match="portable file path"):
        service.specification_revision("delivery", "read-boundary", "working-tree")


def test_does_not_infer_absent_durable_relationships(
    read_project: tuple[Path, AgoraWorkspace, AgoraReadService],
) -> None:
    _, workspace, service = read_project

    detail = service.get_work_item("delivery", "unrelated-work")
    assert detail.artifacts == ()
    assert detail.evidence == ()
    assert detail.approvals == ()
    assert detail.parent_work_ref is None
    assert detail.delegation_id is None
    assert detail.child_work_refs == ()

    lifecycle = service.lifecycle("delivery", "unrelated-work")
    contract = workspace.method_contract("delivery")
    expected_targets = tuple(
        rule.target for rule in contract.transitions if rule.source == detail.state
    )
    assert lifecycle.available_transitions == expected_targets
    assert lifecycle.method == "scrum"


def test_work_control_retries_after_one_interleaved_external_markdown_edit(
    read_project: tuple[Path, AgoraWorkspace, AgoraReadService],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, workspace, service = read_project
    work_path = root / ".agora" / "swarms" / "delivery" / "work" / "read-boundary" / "WORK.md"
    original = workspace.work_control_read_set_sha256
    calls = 0

    def fingerprint(swarm_id: str, work_id: str) -> str:
        nonlocal calls
        calls += 1
        if calls == 2:
            work_path.write_text(
                work_path.read_text(encoding="utf-8") + "\nExternally added note.\n",
                encoding="utf-8",
            )
        return original(swarm_id, work_id)

    monkeypatch.setattr(workspace, "work_control_read_set_sha256", fingerprint)

    projection = service.work_control_projection("delivery", "read-boundary")

    assert projection.work.id == "read-boundary"
    assert calls == 4


def test_work_control_never_returns_a_mixed_snapshot_during_repeated_external_edits(
    read_project: tuple[Path, AgoraWorkspace, AgoraReadService],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, workspace, service = read_project
    work_path = root / ".agora" / "swarms" / "delivery" / "work" / "read-boundary" / "WORK.md"
    original = workspace.work_control_read_set_sha256
    calls = 0

    def fingerprint(swarm_id: str, work_id: str) -> str:
        nonlocal calls
        calls += 1
        if calls in {2, 4, 6}:
            work_path.write_text(
                work_path.read_text(encoding="utf-8") + f"\nExternal revision {calls}.\n",
                encoding="utf-8",
            )
        return original(swarm_id, work_id)

    monkeypatch.setattr(workspace, "work_control_read_set_sha256", fingerprint)

    with pytest.raises(ConcurrentDurableEditError) as captured:
        service.work_control_projection("delivery", "read-boundary")

    assert captured.value.retryable is True
    assert captured.value.to_dict()["details"] == {"stale_reason": "external-edit"}


def test_rejects_invalid_durable_external_content_digest(
    read_project: tuple[Path, AgoraWorkspace, AgoraReadService],
) -> None:
    root, _, service = read_project
    artifacts = root / ".agora" / "swarms" / "delivery" / "work" / "read-boundary" / "artifacts.md"
    contents = artifacts.read_text(encoding="utf-8")
    contents = re.sub(
        r"(\| test-report \| repo://reports/read-service\.txt \|) [0-9a-f]{64} (\|)",
        r"\1 NOT-A-SHA256 \2",
        contents,
    )
    assert "NOT-A-SHA256" in contents
    artifacts.write_text(contents, encoding="utf-8")

    with pytest.raises(InvalidDurableStateError, match="64 lowercase hexadecimal"):
        service.artifacts("delivery", "read-boundary")


def _run_json(root: Path, arguments: list[str]) -> object:
    output = io.StringIO()
    errors = io.StringIO()

    assert main(arguments, cwd=root, stdout=output, stderr=errors) == 0
    assert errors.getvalue() == ""
    return json.loads(output.getvalue())


def test_cli_status_characterization_is_preserved_by_the_read_service(
    read_project: tuple[Path, AgoraWorkspace, AgoraReadService],
) -> None:
    root, workspace, _ = read_project

    assert _run_json(root, ["status"]) == asdict(workspace.status())


def test_cli_actor_and_swarm_read_characterization_is_preserved(
    read_project: tuple[Path, AgoraWorkspace, AgoraReadService],
) -> None:
    root, workspace, _ = read_project
    swarm = workspace.show_swarm("delivery")

    assert _run_json(root, ["actor", "list", "--scope", "project"]) == [
        asdict(item) for item in workspace.list_actors("project")
    ]
    assert _run_json(root, ["swarm", "show", "--swarm", "delivery"]) == asdict(swarm)
    assert _run_json(root, ["swarm", "list", "--status", swarm.status]) == [asdict(swarm)]


def test_cli_work_activity_and_material_characterization_is_preserved(
    read_project: tuple[Path, AgoraWorkspace, AgoraReadService],
) -> None:
    root, workspace, _ = read_project
    work = workspace.show_work("delivery", "read-boundary")

    assert _run_json(
        root,
        ["work", "show", "--swarm", "delivery", "--work", "read-boundary"],
    ) == asdict(work)
    assert _run_json(
        root,
        ["work", "list", "--swarm", "delivery", "--state", work.state],
    ) == [asdict(item) for item in workspace.list_work("delivery", work.state)]
    assert _run_json(
        root,
        [
            "activity",
            "list",
            "--swarm",
            "delivery",
            "--work",
            "read-boundary",
            "--limit",
            "3",
        ],
    ) == [
        asdict(item)
        for item in workspace.list_activity(swarm_id="delivery", work_id="read-boundary", limit=3)
    ]


def test_cli_session_and_traceability_characterization_is_preserved(
    read_project: tuple[Path, AgoraWorkspace, AgoraReadService],
) -> None:
    root, workspace, _ = read_project
    session = workspace.start_session(
        StartSessionInput(
            id="cli-compatible",
            actor_id="developer",
            swarm_id="delivery",
            work_id="read-boundary",
            launch=False,
        )
    )

    assert _run_json(root, ["session", "show", "--session", session.id]) == asdict(session)
    assert _run_json(root, ["session", "list", "--status", "prepared"]) == [asdict(session)]
    assert _run_json(
        root,
        ["work", "traceability", "--swarm", "delivery", "--work", "read-boundary"],
    ) == workspace.work_traceability("delivery", "read-boundary")


def test_studio_consumer_contract_fixture_is_versioned_and_portable() -> None:
    path = Path(__file__).parent / "contracts" / "core-0.5-read-contracts.json"
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["core_version"] == "0.5.0"
    assert payload["session"]["schema"] == "agora/application/session-summary/v1"
    assert payload["method"]["schema"] == "agora/application/method-summary/v1"
    assert payload["lifecycle"]["schema"] == "agora/application/lifecycle-projection/v2"
    assert payload["artifact"]["schema"] == "agora/application/artifact-summary/v2"
    assert payload["evidence"]["schema"] == "agora/application/evidence-summary/v2"
    assert payload["approval"]["schema"] == "agora/application/approval-summary/v2"
    assert payload["traceability"]["schema"] == ("agora/application/traceability-summary/v1")
    assert payload["specification"]["schema"] == ("agora/application/specification-summary/v1")
    assert "/tmp/" not in json.dumps(payload)


def test_core_0_6_consumer_fixtures_are_complete_versioned_and_portable() -> None:
    root = Path(__file__).parent / "contracts"
    fixtures = {
        path.name: json.loads(path.read_text(encoding="utf-8"))
        for path in root.glob("core-0.6-*.json")
    }

    assert set(fixtures) == {
        "core-0.6-gate-decision-options.json",
        "core-0.6-prepared-gate-decision.json",
        "core-0.6-specification-revisions.json",
        "core-0.6-work-control-projection.json",
    }
    assert all(value["core_version"] == "0.6.0" for value in fixtures.values())
    serialized = json.dumps(fixtures, sort_keys=True)
    assert "/tmp/" not in serialized
    assert "PosixPath" not in serialized
    assert "private_key" not in serialized

    control = fixtures["core-0.6-work-control-projection.json"]["projection"]
    assert control["schema"] == "agora/application/work-control-projection/v1"
    assert control["work"]["schema"] == "agora/application/work-item-detail/v2"
    assert control["work"]["artifacts"][0]["schema"].endswith("artifact-summary/v2")
    assert control["work"]["evidence"][0]["schema"].endswith("evidence-summary/v2")
    assert control["work"]["approvals"][0]["schema"].endswith("approval-summary/v2")

    scenarios = fixtures["core-0.6-gate-decision-options.json"]["scenarios"]
    options = scenarios["multiple_transitions_gates_roles"]["options"]
    assert {item["transition_target"] for item in options} == {"completed", "reviewing"}
    assert {item["gate_id"] for item in options} == {"completion", "rework-review"}
    assert {item["decision"] for item in options} == {"approved", "rejected"}
    assert {item["role_id"] for item in options} == {"product-owner", "scrum-master"}
    assert {item["authentication_required"] for item in options} == {False, True}

    revisions = fixtures["core-0.6-specification-revisions.json"]
    assert revisions["history"]["schema"].endswith("specification-summary/v1")
    assert all(
        item["schema"].endswith("specification-revision-detail/v1")
        for item in revisions["details"].values()
    )

    prepared = fixtures["core-0.6-prepared-gate-decision.json"]
    assert prepared["command"]["schema"] == "agora/application/approve-gate-command/v2"
    for key in ("prepared_unsigned_actor", "prepared_signed_actor"):
        item = prepared[key]
        assert (
            item["authorization_digest"]
            == hashlib.sha256(item["authorization_payload"].encode("ascii")).hexdigest()
        )


def test_core_0_7_governance_fixture_versions_the_incompatible_contracts() -> None:
    path = Path(__file__).parent / "contracts" / "core-0.7-governance-contracts.json"
    fixture = json.loads(path.read_text(encoding="utf-8"))

    assert fixture["core_version"] == "0.7.0"
    assert fixture["command"]["schema"].endswith("approve-gate-command/v3")
    assert fixture["prepared"]["schema"].endswith("prepared-gate-decision/v2")
    assert fixture["prepared"]["authorization_schema"].endswith("approve-gate-authorization/v3")
    assert (
        fixture["prepared"]["authorization_digest"]
        == hashlib.sha256(fixture["prepared"]["authorization_payload"].encode("ascii")).hexdigest()
    )
    assert fixture["prepared"]["precondition_digest"] == fixture["command"]["precondition_digest"]
    assert fixture["gate_option"]["evidence_references_by_type"] == {
        "review-report": ["repo://reports/review.txt"]
    }
    assert fixture["work_control"]["schema"].endswith("work-control-projection/v2")
    assert re.fullmatch(r"[0-9a-f]{64}", fixture["work_control"]["snapshot_token"])
    serialized = json.dumps(fixture, sort_keys=True)
    assert "/tmp/" not in serialized
    assert "private_key" not in serialized


def test_core_0_8_fixture_is_confirmable_coherent_and_portable() -> None:
    path = Path(__file__).parent / "contracts" / "core-0.8-application-contracts.json"
    fixture = json.loads(path.read_text(encoding="utf-8"))

    assert fixture["core_version"] == "0.8.0"
    assert fixture["artifact"]["schema"].endswith("artifact-summary/v3")
    assert fixture["evidence"]["schema"].endswith("evidence-summary/v3")
    assert fixture["gate_command"]["schema"].endswith("approve-gate-command/v4")
    assert fixture["prepared_gate"]["schema"].endswith("prepared-gate-decision/v3")
    assert fixture["prepared_gate"]["authorization_schema"].endswith(
        "approve-gate-authorization/v4"
    )

    command_values = dict(fixture["gate_command"])
    command_values.pop("schema")
    command_values["evidence_references"] = tuple(command_values["evidence_references"])
    command = ApproveGateCommand(**command_values)
    assert command.to_dict() == fixture["gate_command"]
    assert (
        approve_gate_authorization_payload(command).decode("ascii")
        == fixture["prepared_gate"]["authorization_payload"]
    )
    assert (
        fixture["prepared_gate"]["authorization_digest"]
        == hashlib.sha256(
            fixture["prepared_gate"]["authorization_payload"].encode("ascii")
        ).hexdigest()
    )
    assert fixture["gate_option"]["content_addressed_evidence_required"] is False
    payload = json.loads(fixture["prepared_gate"]["authorization_payload"])
    projection = fixture["gate_decision_projection"]
    for field in (
        "actor_fingerprint",
        "decision",
        "evidence_content_sha256",
        "evidence_references",
        "expires_at",
        "gate_id",
        "precondition_digest",
        "prepared_at",
        "project_identity",
        "reason",
        "role_id",
        "swarm_id",
        "work_id",
    ):
        expected = fixture["gate_command"][field]
        assert fixture["prepared_gate"][field] == expected
        assert payload[field] == expected
        assert projection[field] == expected

    assert set(fixture["prepared_gate"]["evidence_content_sha256"]) < set(
        fixture["gate_option"]["evidence_content_sha256"]
    )
    assert list(fixture["prepared_gate"]["evidence_content_sha256"].values()) == [None]
    assert any(
        digest is not None
        for reference, digest in fixture["gate_option"]["evidence_content_sha256"].items()
        if reference not in fixture["prepared_gate"]["evidence_content_sha256"]
    )
    assert re.fullmatch(r"[0-9a-f]{64}", fixture["prepared_gate"]["precondition_digest"])
    assert fixture["durable_activity"] == projection["activity"]
    assert fixture["durable_activity"]["type"] == "approval.added"
    activity_summary = fixture["durable_activity"]["summary"]
    assert f"gate={fixture['gate_command']['gate_id']}" in activity_summary
    assert f"role={fixture['gate_command']['role_id']}" in activity_summary
    assert f"reason={fixture['gate_command']['reason']}" in activity_summary
    assert "evidence-content-sha256=" in activity_summary
    assert fixture["gate_decision_projection"]["schema"].endswith("gate-decision-projection/v3")
    assert fixture["work_control_projection_schema"].endswith("work-control-projection/v3")
    assert fixture["operational_error"]["schema"].endswith("error/v2")
    assert fixture["budget"]["projection_schema"].endswith("budget-amendment-projection/v1")
    serialized = json.dumps(fixture, sort_keys=True)
    assert "/tmp/" not in serialized
    assert all(secret not in serialized for secret in ("private_key", "signature", "token"))
