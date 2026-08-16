import io
import stat
import subprocess
from pathlib import Path

import pytest

from agora.cli import main
from agora.markdown import read_markdown, strings_attribute
from agora.model import InitInput, QuickstartInput
from agora.workspace import AgoraWorkspace


def _git(root: Path, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *arguments], cwd=root, check=False, capture_output=True, text=True
    )
    if check:
        assert result.returncode == 0, result.stderr
    return result


def _existing_repository(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    _git(root, "init", "--initial-branch", "main")
    _git(root, "config", "user.name", "Agora Test")
    _git(root, "config", "user.email", "agora@example.test")
    (root / "existing.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(root, "add", "existing.py")
    _git(root, "commit", "-m", "chore: initialize fixture")
    return root


def test_quickstart_creates_a_valid_simple_swarm_from_method_roles(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    workspace = AgoraWorkspace(cwd=tmp_path)

    result = workspace.quickstart(
        QuickstartInput(
            path="project",
            swarm_id="delivery",
            objective="Deliver the first increment",
            method="kanban",
        )
    )

    assert workspace.cwd == tmp_path / "project"
    assert result.project.default_method == "kanban"
    assert result.secure is False
    assert result.key_directory is None
    actors = {actor.id: actor for actor in workspace.list_actors()}
    assert set(actors) == {"agent", "owner"}
    assert all(not actor.authentication_required for actor in actors.values())
    assert not (workspace.cwd / ".agora" / "quickstart-keys").exists()

    role_root = workspace.cwd / ".agora" / "methods" / "kanban" / "roles"
    for role_id, actor_id in result.assignments.items():
        required = strings_attribute(
            read_markdown(role_root / f"{role_id}.md").attributes,
            "required-capabilities",
        )
        assert set(required).issubset(actors[actor_id].capabilities)
    assert workspace.validate().ok is True


def test_secure_quickstart_keeps_private_keys_outside_agora(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    key_directory = tmp_path / "external-actor-keys"
    output = io.StringIO()
    errors = io.StringIO()

    assert (
        main(
            [
                "quickstart",
                "--path",
                "project",
                "--id",
                "secure-delivery",
                "--objective",
                "Deliver an authenticated increment",
                "--secure",
                "--key-dir",
                str(key_directory),
            ],
            cwd=tmp_path,
            stdout=output,
            stderr=errors,
        )
        == 0
    )

    assert errors.getvalue() == ""
    assert f'"key_directory": "{key_directory}"' in output.getvalue()
    project = tmp_path / "project"
    assert not (project / ".agora" / "quickstart-keys").exists()
    for actor_id in ("owner", "agent"):
        private_path = key_directory / f"{actor_id}-private.pem"
        public_path = key_directory / f"{actor_id}-public.pem"
        assert private_path.is_file()
        assert public_path.is_file()
        assert stat.S_IMODE(private_path.stat().st_mode) == 0o600
    workspace = AgoraWorkspace(cwd=project)
    actors = workspace.list_actors()
    assert all(actor.authentication_required for actor in actors)
    assert all(actor.authentication_public_key is not None for actor in actors)
    assert workspace.validate().ok is True


def test_secure_quickstart_rejects_an_incomplete_external_keypair(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    key_directory = tmp_path / "external-actor-keys"
    key_directory.mkdir()
    (key_directory / "owner-private.pem").write_text("incomplete", encoding="utf-8")
    workspace = AgoraWorkspace(cwd=tmp_path)

    with pytest.raises(FileExistsError, match="keypair is incomplete"):
        workspace.quickstart(
            QuickstartInput(
                path="project",
                objective="Reject partial credentials",
                secure=True,
                key_directory=str(key_directory),
            )
        )

    assert not (tmp_path / "project").exists()
    assert (key_directory / "owner-private.pem").read_text(encoding="utf-8") == "incomplete"


def test_quickstart_refuses_to_reuse_existing_actor_identity(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    workspace = AgoraWorkspace(cwd=tmp_path)
    workspace.quickstart(QuickstartInput(path="project", objective="First objective"))

    with pytest.raises(FileExistsError, match="target already exists"):
        workspace.quickstart(QuickstartInput(objective="Second objective"))


def test_quickstart_defaults_to_the_spec_driven_pack(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    workspace = AgoraWorkspace(cwd=tmp_path)

    result = workspace.quickstart(
        QuickstartInput(path="project", objective="Deliver the first increment")
    )

    assert result.project.default_method == "spec-driven"
    assert set(result.assignments) == {"spec-owner", "developer"}
    assert workspace.validate().ok is True


def test_quickstart_adopts_an_existing_repository_on_a_new_branch(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    root = _existing_repository(tmp_path)

    result = AgoraWorkspace(cwd=root).quickstart(
        QuickstartInput(
            swarm_id="feature",
            objective="Add a feature to the existing package",
            base_branch="main",
        )
    )

    assert result.swarm.branch == "agora/feature"
    assert _git(root, "branch", "--show-current").stdout.strip() == "agora/feature"
    assert (root / "existing.py").read_text(encoding="utf-8") == "VALUE = 1\n"
    assert AgoraWorkspace(cwd=root).validate().ok is True


def test_quickstart_preflight_rejects_ignored_state_before_writing(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    root = _existing_repository(tmp_path)
    (root / ".gitignore").write_text(".agora/\n", encoding="utf-8")
    _git(root, "add", ".gitignore")
    _git(root, "commit", "-m", "chore: ignore Agora state")

    with pytest.raises(ValueError, match="git-persistence"):
        AgoraWorkspace(cwd=root).quickstart(
            QuickstartInput(swarm_id="feature", objective="Adopt safely")
        )

    assert not (root / ".agora").exists()
    assert _git(root, "branch", "--show-current").stdout.strip() == "main"
    assert (
        _git(root, "show-ref", "--verify", "refs/heads/agora/feature", check=False).returncode != 0
    )


def test_quickstart_rolls_back_files_and_branch_after_a_late_failure(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    root = _existing_repository(tmp_path)
    workspace = AgoraWorkspace(cwd=root)
    add_actor = workspace.add_actor
    calls = 0

    def fail_on_second_actor(data):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("injected actor failure")
        return add_actor(data)

    monkeypatch.setattr(workspace, "add_actor", fail_on_second_actor)

    with pytest.raises(RuntimeError, match="injected actor failure"):
        workspace.quickstart(QuickstartInput(swarm_id="feature", objective="Exercise rollback"))

    assert workspace.cwd == root
    assert not (root / ".agora").exists()
    assert (root / "existing.py").read_text(encoding="utf-8") == "VALUE = 1\n"
    assert _git(root, "branch", "--show-current").stdout.strip() == "main"
    assert (
        _git(root, "show-ref", "--verify", "refs/heads/agora/feature", check=False).returncode != 0
    )


def test_quickstart_restores_an_initialized_project_after_failure(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    root = _existing_repository(tmp_path)
    workspace = AgoraWorkspace(cwd=root)
    workspace.initialize(InitInput(integration="generic"))
    _git(root, "add", ".agora")
    _git(root, "commit", "-m", "chore: initialize Agora")
    before = {
        path.relative_to(root / ".agora"): path.read_bytes()
        for path in (root / ".agora").rglob("*")
        if path.is_file()
    }
    add_actor = workspace.add_actor
    calls = 0

    def fail_on_second_actor(data):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("injected initialized-project failure")
        return add_actor(data)

    monkeypatch.setattr(workspace, "add_actor", fail_on_second_actor)

    with pytest.raises(RuntimeError, match="initialized-project failure"):
        workspace.quickstart(
            QuickstartInput(swarm_id="feature", objective="Exercise snapshot rollback")
        )

    after = {
        path.relative_to(root / ".agora"): path.read_bytes()
        for path in (root / ".agora").rglob("*")
        if path.is_file()
    }
    assert after == before
    assert _git(root, "branch", "--show-current").stdout.strip() == "main"
    assert (
        _git(root, "show-ref", "--verify", "refs/heads/agora/feature", check=False).returncode != 0
    )


def test_secure_quickstart_removes_new_keys_when_the_transaction_fails(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    key_directory = tmp_path / "quickstart-keys"
    workspace = AgoraWorkspace(cwd=tmp_path)
    add_actor = workspace.add_actor
    calls = 0

    def fail_on_second_actor(data):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("injected secure failure")
        return add_actor(data)

    monkeypatch.setattr(workspace, "add_actor", fail_on_second_actor)

    with pytest.raises(RuntimeError, match="injected secure failure"):
        workspace.quickstart(
            QuickstartInput(
                path="project",
                objective="Exercise secure rollback",
                secure=True,
                key_directory=str(key_directory),
            )
        )

    assert not (tmp_path / "project").exists()
    assert not key_directory.exists()
