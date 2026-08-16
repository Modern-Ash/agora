import io
import json
from pathlib import Path

import pytest

from agora.cli import main
from agora.markdown import read_markdown, render_markdown
from agora.model import (
    AddActorInput,
    AddUsageInput,
    AssignActorInput,
    CreateSwarmInput,
    CreateWorkInput,
    InitInput,
)
from agora.workspace import AgoraWorkspace


def _budgeted_workspace(tmp_path: Path, monkeypatch) -> AgoraWorkspace:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    root = tmp_path / "project"
    root.mkdir()
    workspace = AgoraWorkspace(cwd=root)
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
        CreateSwarmInput(id="delivery", objective="Measure delivery", create_branch=False)
    )
    for role, actor in (
        ("product-owner", "owner"),
        ("scrum-master", "facilitator"),
        ("developer", "developer"),
    ):
        workspace.assign_actor(AssignActorInput(swarm_id="delivery", role_id=role, actor_id=actor))
    work = workspace.create_work(
        CreateWorkInput(
            swarm_id="delivery",
            id="increment",
            title="Measured increment",
            actor_id="owner",
        )
    )
    work_path = Path(work.path) / "WORK.md"
    document = read_markdown(work_path)
    document.attributes["budget-limits"] = {"cost-cents": 50, "tokens": 100}
    work_path.write_text(render_markdown(document), encoding="utf-8")
    return workspace


def test_accumulates_evidence_backed_usage_and_enforces_work_budget(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = _budgeted_workspace(tmp_path, monkeypatch)
    first = workspace.add_usage(
        AddUsageInput(
            id="model-call-1",
            swarm_id="delivery",
            work_id="increment",
            actor_id="developer",
            amounts={"tokens": 40, "cost-cents": 20},
            evidence_refs=["telemetry://model/call-1"],
        )
    )
    output = io.StringIO()
    assert (
        main(
            [
                "usage",
                "add",
                "--id",
                "model-call-2",
                "--swarm",
                "delivery",
                "--work",
                "increment",
                "--by",
                "developer",
                "--amount",
                "tokens=60",
                "--amount",
                "cost-cents=30",
                "--evidence",
                "telemetry://model/call-2",
            ],
            cwd=workspace.project_root(),
            stdout=output,
        )
        == 0
    )

    assert first.amounts == {"cost-cents": 20, "tokens": 40}
    assert [record.id for record in workspace.list_usage("delivery", "increment")] == [
        "model-call-1",
        "model-call-2",
    ]
    summary = workspace.summarize_usage("delivery", "increment")
    assert summary.budget_limits == {"cost-cents": 50, "tokens": 100}
    assert summary.consumed == {"cost-cents": 50, "tokens": 100}
    assert summary.remaining == {"cost-cents": 0, "tokens": 0}
    assert summary.records == 2
    assert workspace.validate().ok

    with pytest.raises(ValueError, match="Usage exceeds work budget"):
        workspace.add_usage(
            AddUsageInput(
                id="model-call-3",
                swarm_id="delivery",
                work_id="increment",
                actor_id="developer",
                amounts={"tokens": 1},
                evidence_refs=["telemetry://model/call-3"],
            )
        )
    with pytest.raises(ValueError, match="dimensions are not available"):
        workspace.add_usage(
            AddUsageInput(
                id="unknown-dimension",
                swarm_id="delivery",
                work_id="increment",
                actor_id="developer",
                amounts={"gpu-seconds": 1},
                evidence_refs=["telemetry://gpu/run-1"],
            )
        )


def test_summarizes_unbounded_usage_through_cli(tmp_path: Path, monkeypatch) -> None:
    workspace = _budgeted_workspace(tmp_path, monkeypatch)
    workspace.create_work(
        CreateWorkInput(
            swarm_id="delivery",
            id="exploration",
            title="Unbounded exploration",
            actor_id="owner",
        )
    )
    workspace.add_usage(
        AddUsageInput(
            id="runtime-1",
            swarm_id="delivery",
            work_id="exploration",
            actor_id="developer",
            amounts={"gpu-seconds": 12},
            evidence_refs=["telemetry://runtime/1"],
        )
    )
    output = io.StringIO()

    assert (
        main(
            [
                "usage",
                "status",
                "--swarm",
                "delivery",
                "--work",
                "exploration",
            ],
            cwd=workspace.project_root(),
            stdout=output,
        )
        == 0
    )
    result = json.loads(output.getvalue())
    assert result == {
        "budget_limits": None,
        "consumed": {"gpu-seconds": 12},
        "records": 1,
        "remaining": None,
        "swarm_id": "delivery",
        "work_id": "exploration",
    }


def test_validation_detects_usage_tampering(tmp_path: Path, monkeypatch) -> None:
    workspace = _budgeted_workspace(tmp_path, monkeypatch)
    usage = workspace.add_usage(
        AddUsageInput(
            id="model-call",
            swarm_id="delivery",
            work_id="increment",
            actor_id="developer",
            amounts={"tokens": 40},
            evidence_refs=["telemetry://model/call"],
        )
    )
    usage_path = Path(usage.path)
    document = read_markdown(usage_path)
    document.attributes["amounts"] = {"tokens": 101}
    usage_path.write_text(render_markdown(document), encoding="utf-8")

    report = workspace.validate()

    assert report.ok is False
    assert any(issue.code == "usage.budget-exceeded" for issue in report.issues)
