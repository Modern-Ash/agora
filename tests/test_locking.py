import io
from datetime import UTC, datetime
from pathlib import Path

import pytest

from agora.cli import main
from agora.locking import WorkspaceLock, WorkspaceLockedError, inspect_workspace_lock
from agora.model import AddActorInput, InitInput
from agora.workspace import AgoraWorkspace

TIMESTAMP = datetime(2026, 8, 14, 12, tzinfo=UTC)


def test_reports_the_active_owner_and_releases_the_operating_system_lock(
    tmp_path: Path, monkeypatch
) -> None:
    resource = tmp_path / "project"
    resource.mkdir()
    monkeypatch.setenv("AGORA_LOCK_HOME", str(tmp_path / "locks"))

    assert inspect_workspace_lock(resource).active is False

    with WorkspaceLock(resource, "test-operation", now=TIMESTAMP):
        status = inspect_workspace_lock(resource)

        assert status.active is True
        assert status.operation == "test-operation"
        assert status.pid is not None
        assert status.hostname
        assert status.acquired_at == "2026-08-14T12:00:00Z"
        with pytest.raises(WorkspaceLockedError, match="test-operation"):
            with WorkspaceLock(resource, "competing-operation"):
                pass

    status = inspect_workspace_lock(resource)
    assert status.active is False
    assert status.operation == "test-operation"


def test_shared_readers_coexist_and_still_exclude_a_writer(tmp_path: Path, monkeypatch) -> None:
    resource = tmp_path / "project"
    resource.mkdir()
    monkeypatch.setenv("AGORA_LOCK_HOME", str(tmp_path / "locks"))

    with WorkspaceLock(resource, "reader-one", shared=True):
        with WorkspaceLock(resource, "reader-two", shared=True):
            with pytest.raises(WorkspaceLockedError):
                with WorkspaceLock(resource, "writer"):
                    pass

    with WorkspaceLock(resource, "writer"):
        pass


def test_serializes_initialization_and_project_mutations(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("AGORA_LOCK_HOME", str(tmp_path / "locks"))
    workspace = AgoraWorkspace(cwd=root, now=lambda: TIMESTAMP)

    with WorkspaceLock(root, "other-initialization", now=TIMESTAMP):
        with pytest.raises(WorkspaceLockedError, match="other-initialization"):
            workspace.initialize(InitInput(integration="generic"))
    assert not (root / ".agora" / "project.md").exists()

    with WorkspaceLock(tmp_path / "home", "home-update", now=TIMESTAMP):
        with pytest.raises(WorkspaceLockedError, match="home-update"):
            workspace.initialize(InitInput(integration="generic"))
    assert not (root / ".agora" / "project.md").exists()

    workspace.initialize(InitInput(integration="generic"))
    actor = AddActorInput(
        id="developer",
        name="Developer",
        kind="ai-agent",
        capabilities=["implementation"],
        scope="project",
    )
    with WorkspaceLock(root, "other-project-write", now=TIMESTAMP):
        with pytest.raises(WorkspaceLockedError, match="other-project-write"):
            workspace.add_actor(actor)
    assert not (root / ".agora" / "actors" / "developer.md").exists()

    assert workspace.add_actor(actor).reference == "project:developer"
    assert workspace.lock_status().active is False


def test_releases_the_workspace_lock_when_a_mutation_fails(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("AGORA_LOCK_HOME", str(tmp_path / "locks"))
    workspace = AgoraWorkspace(cwd=root, now=lambda: TIMESTAMP)
    workspace.initialize(InitInput(integration="generic"))
    invalid = AddActorInput(
        id="Invalid id",
        name="Invalid",
        kind="ai-agent",
        capabilities=[],
        scope="project",
    )

    with pytest.raises(ValueError, match="Actor id must match"):
        workspace.add_actor(invalid)

    assert workspace.lock_status().active is False


def test_cli_exposes_runtime_lock_status(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("AGORA_LOCK_HOME", str(tmp_path / "locks"))
    AgoraWorkspace(cwd=root).initialize(InitInput(integration="generic"))
    output = io.StringIO()
    errors = io.StringIO()

    assert main(["lock", "status"], cwd=root, stdout=output, stderr=errors) == 0

    assert '"active": false' in output.getvalue()
    assert '"operation": "initialize"' in output.getvalue()
    assert errors.getvalue() == ""

    output = io.StringIO()
    assert (
        main(
            ["lock", "status", "--scope", "user"],
            cwd=tmp_path,
            stdout=output,
            stderr=errors,
        )
        == 0
    )
    user_home = tmp_path / "home"
    assert f'"resource": "{user_home}"' in output.getvalue()


@pytest.mark.parametrize("value", ["-1", "nan", "inf", "not-a-number"])
def test_rejects_invalid_lock_timeouts(tmp_path: Path, monkeypatch, value: str) -> None:
    monkeypatch.setenv("AGORA_LOCK_TIMEOUT", value)

    with pytest.raises(ValueError, match="AGORA_LOCK_TIMEOUT|Lock timeout"):
        AgoraWorkspace(cwd=tmp_path)
