import io
import stat
from pathlib import Path

import pytest

from agora.cli import main
from agora.markdown import read_markdown, strings_attribute
from agora.model import QuickstartInput
from agora.workspace import AgoraWorkspace


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

    project = AgoraWorkspace(cwd=tmp_path / "project")
    assert project.list_actors() == []
    assert project.list_swarms() == []


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
