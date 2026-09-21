from pathlib import Path

import pytest
from test_adr_0002 import _project

from agora.application import AgoraReadService
from agora.model import AddArtifactInput, AddEvidenceInput, CreateWorkInput, StartSessionInput


def _session(workspace, session_id: str, actor_id: str, work_id: str = "feature"):
    return workspace.start_session(
        StartSessionInput(
            id=session_id,
            actor_id=actor_id,
            swarm_id="delivery",
            work_id=work_id,
        )
    )


def test_artifact_and_review_evidence_bind_exact_sessions_and_digest(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("agora.workspace.shutil.which", lambda executable: f"/usr/bin/{executable}")
    workspace = _project(tmp_path, monkeypatch)
    target = tmp_path / "review-target.md"
    target.write_text("# revision one\n", encoding="utf-8")

    producer = _session(workspace, "producer-session", "developer")
    reviewer = _session(workspace, "reviewer-session", "owner")

    workspace.add_artifact(
        AddArtifactInput(
            swarm_id="delivery",
            work_id="feature",
            actor_id="developer",
            kind="implementation",
            uri="repo://review-target.md",
            session_id=producer.id,
        )
    )
    workspace.add_evidence(
        AddEvidenceInput(
            swarm_id="delivery",
            work_id="feature",
            actor_id="owner",
            type="review",
            result="success",
            artifact_refs=["repo://review-target.md"],
            session_id=reviewer.id,
        )
    )

    artifact = workspace.list_work_artifacts("delivery", "feature")[-1]
    evidence = workspace.list_work_evidence("delivery", "feature")[-1]
    assert artifact.session_id == "producer-session"
    assert evidence.session_id == "reviewer-session"
    assert artifact.content_sha256 is not None
    assert evidence.artifact_content_sha256["repo://review-target.md"] == artifact.content_sha256

    detail = AgoraReadService(workspace).get_work_item("delivery", "feature")
    assert detail.artifacts[-1].session_id == "producer-session"
    assert detail.evidence[-1].session_id == "reviewer-session"


def test_review_digest_becomes_stale_after_new_artifact_revision(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("agora.workspace.shutil.which", lambda executable: f"/usr/bin/{executable}")
    workspace = _project(tmp_path, monkeypatch)
    target = tmp_path / "review-target.md"
    target.write_text("# revision one\n", encoding="utf-8")
    producer = _session(workspace, "producer-session", "developer")
    reviewer = _session(workspace, "reviewer-session", "owner")

    artifact_input = AddArtifactInput(
        swarm_id="delivery",
        work_id="feature",
        actor_id="developer",
        kind="implementation",
        uri="repo://review-target.md",
        session_id=producer.id,
    )
    workspace.add_artifact(artifact_input)
    workspace.add_evidence(
        AddEvidenceInput(
            swarm_id="delivery",
            work_id="feature",
            actor_id="owner",
            type="review",
            result="success",
            artifact_refs=["repo://review-target.md"],
            session_id=reviewer.id,
        )
    )
    reviewed_digest = workspace.list_work_evidence("delivery", "feature")[-1].artifact_content_sha256[
        "repo://review-target.md"
    ]

    target.write_text("# revision two\n", encoding="utf-8")
    workspace.add_artifact(artifact_input)
    current_digest = workspace.list_work_artifacts("delivery", "feature")[-1].content_sha256

    assert reviewed_digest is not None
    assert current_digest is not None
    assert reviewed_digest != current_digest


def test_session_link_rejects_cross_work_and_foreign_executor(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("agora.workspace.shutil.which", lambda executable: f"/usr/bin/{executable}")
    workspace = _project(tmp_path, monkeypatch)
    target = tmp_path / "review-target.md"
    target.write_text("# target\n", encoding="utf-8")
    developer_session = _session(workspace, "developer-session", "developer")

    with pytest.raises(PermissionError, match="must match Session executor"):
        workspace.add_artifact(
            AddArtifactInput(
                swarm_id="delivery",
                work_id="feature",
                actor_id="owner",
                kind="spec",
                uri="repo://review-target.md",
                session_id=developer_session.id,
            )
        )

    workspace.create_work(
        CreateWorkInput(
            swarm_id="delivery",
            id="other-work",
            title="Other work",
            actor_id="owner",
            description="Independent work item.",
            acceptance_criteria=[("done", "Done")],
        )
    )
    other_session = _session(workspace, "other-session", "developer", "other-work")
    with pytest.raises(ValueError, match="same work item"):
        workspace.add_artifact(
            AddArtifactInput(
                swarm_id="delivery",
                work_id="feature",
                actor_id="developer",
                kind="implementation",
                uri="repo://review-target.md",
                session_id=other_session.id,
            )
        )


def test_flavor_projection_context_contains_only_referenced_actors(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("agora.workspace.shutil.which", lambda executable: f"/usr/bin/{executable}")
    workspace = _project(tmp_path, monkeypatch)
    target = tmp_path / "review-target.md"
    target.write_text("# target\n", encoding="utf-8")
    producer = _session(workspace, "producer-session", "developer")
    reviewer = _session(workspace, "reviewer-session", "owner")

    workspace.add_artifact(
        AddArtifactInput(
            swarm_id="delivery",
            work_id="feature",
            actor_id="developer",
            kind="implementation",
            uri="repo://review-target.md",
            session_id=producer.id,
        )
    )
    workspace.add_evidence(
        AddEvidenceInput(
            swarm_id="delivery",
            work_id="feature",
            actor_id="owner",
            type="review",
            result="success",
            artifact_refs=["repo://review-target.md"],
            session_id=reviewer.id,
        )
    )

    context = AgoraReadService(workspace)._flavor_projection_context("delivery", "feature")
    assert {actor.reference for actor in context.actors} == {"project:developer", "project:owner"}
    assert {session.id for session in context.sessions} == {"producer-session", "reviewer-session"}


def test_legacy_artifact_and_evidence_records_have_no_session_link(tmp_path: Path, monkeypatch) -> None:
    workspace = _project(tmp_path, monkeypatch)
    target = tmp_path / "legacy.md"
    target.write_text("# legacy\n", encoding="utf-8")

    workspace.add_artifact(
        AddArtifactInput(
            swarm_id="delivery",
            work_id="feature",
            actor_id="developer",
            kind="implementation",
            uri="repo://legacy.md",
        )
    )
    workspace.add_evidence(
        AddEvidenceInput(
            swarm_id="delivery",
            work_id="feature",
            actor_id="owner",
            type="review",
            result="success",
            artifact_refs=["repo://legacy.md"],
        )
    )

    assert workspace.list_work_artifacts("delivery", "feature")[-1].session_id is None
    assert workspace.list_work_evidence("delivery", "feature")[-1].session_id is None
