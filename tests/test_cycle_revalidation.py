import io
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from agora.cli import main
from agora.console import EngineTrace
from agora.filesystem import atomic_write, filesystem_transaction
from agora.markdown import read_markdown, render_markdown
from agora.model import (
    AddActorInput,
    AddArtifactInput,
    AddEvidenceInput,
    AssignActorInput,
    BindIssueTrackerInput,
    CreateSwarmInput,
    CreateWorkInput,
    ExternalIssueSnapshot,
    InitInput,
    ReopenWorkInput,
    SyncIssueTrackerInput,
    UpgradeInput,
)
from agora.workspace import AgoraWorkspace


def _workspace(tmp_path: Path, monkeypatch) -> AgoraWorkspace:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    workspace = AgoraWorkspace(
        cwd=tmp_path,
        now=lambda: datetime(2026, 8, 30, 12, 0, tzinfo=UTC),
    )
    workspace.initialize(InitInput())
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
    workspace.create_swarm(CreateSwarmInput(id="delivery", objective="Ship safely"))
    workspace.assign_actor(
        AssignActorInput(swarm_id="delivery", role_id="spec-owner", actor_id="owner")
    )
    workspace.assign_actor(
        AssignActorInput(swarm_id="delivery", role_id="developer", actor_id="dev")
    )
    workspace.create_work(
        CreateWorkInput(
            swarm_id="delivery",
            id="bug-42",
            title="Fix production bug",
            actor_id="owner",
            acceptance_criteria=[("fixed", "The bug no longer reproduces")],
            required_artifacts=["test-report"],
        )
    )
    return workspace


def _force_completed_revision(workspace: AgoraWorkspace) -> None:
    swarm = workspace.show_swarm("delivery")
    work = workspace.show_work("delivery", "bug-42")
    work.state = "completed"
    with filesystem_transaction():
        atomic_write(Path(work.path) / "WORK.md", workspace._render_work(work))
        workspace._close_work_revision_writes(work, "project:owner")
    workspace._refresh_swarm_status(workspace.project_root(), swarm, changed_work=work)


def test_non_tty_engine_trace_preserves_json_stdout(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    assert main(["init"], cwd=tmp_path, stdout=io.StringIO()) == 0
    output = io.StringIO()
    trace = io.StringIO()

    assert (
        main(
            ["--trace", "jsonl", "status"],
            cwd=tmp_path,
            stdout=output,
            stderr=trace,
        )
        == 0
    )

    assert json.loads(output.getvalue())["project"] == tmp_path.name
    events = [json.loads(line) for line in trace.getvalue().splitlines()]
    assert [item["phase"] for item in events] == ["command.start", "command.finish"]
    assert all(item["schema"] == "agora/application/engine-trace-event/v1" for item in events)


def test_engine_trace_is_line_oriented_without_a_tty() -> None:
    output = io.StringIO()
    trace = EngineTrace(
        output,
        "compact",
        operation_id="chat-run",
        now=lambda: datetime(2026, 8, 30, 12, 0, tzinfo=UTC),
    )

    trace.emit("gate.evaluate", "blocked", "gate.failed", "Deployment gate is blocked")

    rendered = output.getvalue()
    assert rendered.endswith("\n")
    assert "AGORA 01 !!" in rendered
    assert "gate.evaluate" in rendered


def test_sync_github_alias_uses_the_neutral_tracker_contract(tmp_path: Path, monkeypatch) -> None:
    _workspace(tmp_path, monkeypatch)

    class EmptyGitHubAdapter:
        tracker = "github"

        def __init__(self, root: Path) -> None:
            assert root == tmp_path

        def fetch(self, project: str, external_ids: list[str]) -> list[ExternalIssueSnapshot]:
            assert project == "owner/maitre"
            assert external_ids == []
            return []

    monkeypatch.setattr("agora.cli.GitHubIssueTrackerAdapter", EmptyGitHubAdapter)
    output = io.StringIO()

    assert (
        main(
            ["sync", "github", "--repo", "owner/maitre"],
            cwd=tmp_path,
            stdout=output,
        )
        == 0
    )
    assert json.loads(output.getvalue())["tracker"] == "github"


def test_reopen_preserves_closed_revision_and_appends_structured_evidence(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    report = tmp_path / "report.txt"
    report.write_text("18 tests passed\n", encoding="utf-8")
    workspace.add_artifact(
        AddArtifactInput(
            swarm_id="delivery",
            work_id="bug-42",
            actor_id="dev",
            kind="test-report",
            uri="repo://report.txt",
        )
    )
    evidence = AddEvidenceInput(
        swarm_id="delivery",
        work_id="bug-42",
        actor_id="dev",
        evidence_id="verification-1",
        type="pytest",
        phase="verification",
        result="success",
        artifact_refs=["repo://report.txt"],
        command=["python", "-m", "pytest", "-q"],
        exit_code=0,
        tests_total=18,
        tests_passed=18,
        tests_failed=0,
        environment="test",
        dedupe_key="ci:run:100",
    )
    workspace.add_evidence(evidence)
    workspace.add_evidence(evidence)
    with pytest.raises(ValueError, match="different payload"):
        workspace.add_evidence(
            AddEvidenceInput(**{**evidence.__dict__, "environment": "production"})
        )
    _force_completed_revision(workspace)
    work_path = Path(workspace.show_work("delivery", "bug-42").path)
    closed_before = (work_path / "revisions" / "0001" / "REVISION.md").read_bytes()

    reopened = workspace.reopen_work(
        ReopenWorkInput(
            swarm_id="delivery",
            work_id="bug-42",
            actor_id="owner",
            reason="Issue reopened after production validation",
            source="issue-tracker:github",
            source_id="github:owner/repo:42:event-200",
        )
    )
    replay = workspace.reopen_work(
        ReopenWorkInput(
            swarm_id="delivery",
            work_id="bug-42",
            actor_id="owner",
            reason="Issue reopened after production validation",
            source="issue-tracker:github",
            source_id="github:owner/repo:42:event-200",
        )
    )

    assert reopened.revision == replay.revision == 2
    assert reopened.operational_status == "revalidation"
    assert workspace.show_swarm("delivery").status == "running"
    assert (work_path / "revisions" / "0001" / "snapshot" / "evidence.md").is_file()
    assert (work_path / "evidence" / "verification-1" / "EVIDENCE.md").is_file()
    assert (work_path / "revisions" / "0001" / "REVISION.md").read_bytes() == closed_before
    assert workspace.validate().ok


def test_successful_evidence_rejects_empty_repository_artifact(tmp_path: Path, monkeypatch) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    (tmp_path / "empty.txt").touch()
    workspace.add_artifact(
        AddArtifactInput(
            swarm_id="delivery",
            work_id="bug-42",
            actor_id="dev",
            kind="test-report",
            uri="repo://empty.txt",
        )
    )

    with pytest.raises(ValueError, match="empty artifact"):
        workspace.add_evidence(
            AddEvidenceInput(
                swarm_id="delivery",
                work_id="bug-42",
                actor_id="dev",
                type="pytest",
                result="success",
                artifact_refs=["repo://empty.txt"],
            )
        )


def test_upgrade_from_0_3_materializes_initial_revision_without_changing_authority(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    project_path = tmp_path / ".agora" / "project.md"
    project = read_markdown(project_path)
    project.attributes["version"] = "0.3.0"
    project_path.write_text(render_markdown(project), encoding="utf-8")
    work_path = Path(workspace.show_work("delivery", "bug-42").path)
    work_document = read_markdown(work_path / "WORK.md")
    work_document.attributes.pop("revision")
    (work_path / "WORK.md").write_text(render_markdown(work_document), encoding="utf-8")
    shutil.rmtree(work_path / "revisions")

    result = workspace.upgrade(UpgradeInput(apply=True, id="revision-ledger"))

    assert result.to_version == "0.4.0"
    assert read_markdown(project_path).attributes["version"] == "0.4.0"
    revision = read_markdown(work_path / "revisions" / "0001" / "REVISION.md")
    assert revision.attributes["status"] == "open"
    assert revision.attributes["source"] == "upgrade:0.4.0"
    assert workspace.validate().ok


class _FixtureTracker:
    def __init__(self, tracker: str, snapshots: list[ExternalIssueSnapshot]) -> None:
        self.tracker = tracker
        self.snapshots = snapshots

    def fetch(self, project: str, external_ids: list[str]) -> list[ExternalIssueSnapshot]:
        assert [item.external_id for item in self.snapshots] == external_ids
        assert all(item.project == project for item in self.snapshots)
        return self.snapshots


def _snapshot(tracker: str, state: str, version: int) -> ExternalIssueSnapshot:
    external_id = "42" if tracker == "github" else "MAITRE-42"
    return ExternalIssueSnapshot(
        tracker=tracker,
        project="owner/maitre" if tracker == "github" else "MAITRE",
        external_id=external_id,
        title="Production bug",
        state=state,  # type: ignore[arg-type]
        url=f"https://tracker.example/{external_id}",
        updated_at=f"2026-08-30T12:0{version}:00Z",
        author_subject="canonical-subject",
        author_display_name="Adrian",
        labels=["bug"],
        comment_count=version,
        payload_sha256=str(version) * 64,
    )


def test_github_and_jira_reopen_work_through_the_same_core_contract(
    tmp_path: Path, monkeypatch
) -> None:
    for tracker, project, issue in (
        ("github", "owner/maitre", "42"),
        ("jira", "MAITRE", "MAITRE-42"),
    ):
        root = tmp_path / tracker
        root.mkdir()
        workspace = _workspace(root, monkeypatch)
        workspace.bind_issue_tracker(
            BindIssueTrackerInput(
                id="production-bug",
                swarm_id="delivery",
                work_id="bug-42",
                tracker=tracker,
                project=project,
                external_id=issue,
                reopen_actor_id="owner",
            )
        )
        workspace.sync_issue_tracker(
            SyncIssueTrackerInput(tracker=tracker, project=project),
            _FixtureTracker(tracker, [_snapshot(tracker, "open", 1)]),
        )
        _force_completed_revision(workspace)
        workspace.sync_issue_tracker(
            SyncIssueTrackerInput(tracker=tracker, project=project),
            _FixtureTracker(tracker, [_snapshot(tracker, "closed", 2)]),
        )
        result = workspace.sync_issue_tracker(
            SyncIssueTrackerInput(tracker=tracker, project=project),
            _FixtureTracker(tracker, [_snapshot(tracker, "open", 3)]),
        )
        replay = workspace.sync_issue_tracker(
            SyncIssueTrackerInput(tracker=tracker, project=project),
            _FixtureTracker(tracker, [_snapshot(tracker, "open", 3)]),
        )

        assert result.reopened == 1
        assert replay.reopened == 0
        assert replay.unchanged == 1
        assert workspace.show_work("delivery", "bug-42").revision == 2
        assert workspace.show_work("delivery", "bug-42").operational_status == "revalidation"
        assert result.events[-1].change == "reopened"
