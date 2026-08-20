import io
import json
from dataclasses import FrozenInstanceError, asdict
from datetime import UTC, datetime
from pathlib import Path

import pytest

from agora.application import (
    ActivityFilters,
    ActorFilters,
    AgoraReadService,
    InvalidDurableStateError,
    InvalidReadQueryError,
    ProjectNotFoundError,
    ReadResourceNotFoundError,
    SwarmFilters,
    WorkItemFilters,
)
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
    assert payload["schema"] == "agora/application/work-item-detail/v1"
    assert payload["acceptance_criteria"] == {"contract": "Expose a versioned contract"}
    assert payload["artifacts"][0]["schema"] == "agora/application/artifact-summary/v1"
    assert "path" not in json.dumps(payload)
    with pytest.raises(FrozenInstanceError):
        detail.title = "mutated"  # type: ignore[misc]
    with pytest.raises(TypeError):
        detail.acceptance_criteria["other"] = "mutated"  # type: ignore[index]

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

    current_artifacts = workspace._work_artifact_rows(
        workspace.show_work("delivery", "read-boundary")
    )
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


@pytest.mark.parametrize("operation", ["detail", "lifecycle", "artifacts"])
def test_rejects_invalid_slugs_before_resolving_records(
    read_project: tuple[Path, AgoraWorkspace, AgoraReadService], operation: str
) -> None:
    _, _, service = read_project
    calls = {
        "detail": service.get_work_item,
        "lifecycle": service.lifecycle,
        "artifacts": service.artifacts,
    }

    with pytest.raises(InvalidReadQueryError, match=r"must match /\^"):
        calls[operation]("../outside", "read-boundary")


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
        f"| test-report | repo://escape.txt | project:developer | {TIMESTAMP.isoformat()} |\n",
        encoding="utf-8",
    )

    with pytest.raises(InvalidDurableStateError, match="escapes the project"):
        service.artifacts("delivery", "read-boundary")


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
