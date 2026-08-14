import io
import shutil
from pathlib import Path

import pytest

from agora.cli import main
from agora.model import InitInput, InstallCatalogPackInput, InstallRegistryInput
from agora.workspace import AgoraWorkspace

ROOT = Path(__file__).parents[1]


def _registry(
    destination: Path,
    *,
    registry_id: str,
    registry_name: str,
    method_name: str = "Release Flow",
) -> Path:
    destination.mkdir(parents=True)
    (destination / "REGISTRY.md").write_text(
        f'---\nschema: "agora/registry/v1"\nid: "{registry_id}"\n'
        f'name: "{registry_name}"\n---\n\n# {registry_name}\n',
        encoding="utf-8",
    )
    method = destination / "methods" / "release-flow"
    shutil.copytree(ROOT / "samples" / "custom-lifecycle" / "release-flow", method)
    manifest = method / "METHOD.md"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            'name: "Release Flow"', f'name: "{method_name}"'
        ),
        encoding="utf-8",
    )
    return destination


def test_discovers_bundled_packs_without_an_initialized_project(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    workspace = AgoraWorkspace(cwd=tmp_path)

    registries = workspace.list_registries()
    methods = workspace.search_catalog(kind="method")
    tools = workspace.search_catalog(kind="tool", query="repository")

    assert [(item.id, item.scope) for item in registries] == [("agora-bundled", "bundled")]
    assert [item.id for item in methods] == ["kanban", "scrum"]
    assert [(item.id, item.registry) for item in tools] == [("repository", "agora-bundled")]


def test_installs_a_user_registry_and_its_method_into_a_project(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    source = _registry(
        tmp_path / "source-registry",
        registry_id="team-catalog",
        registry_name="Team Catalog",
    )
    workspace = AgoraWorkspace(cwd=root)
    workspace.initialize(InitInput(integration="generic"))

    registry = workspace.install_registry(InstallRegistryInput(source=str(source), scope="user"))
    discovered = workspace.search_catalog(
        kind="method", query="release", registry_id="team-catalog"
    )
    installed = workspace.install_catalog_pack(
        InstallCatalogPackInput(
            kind="method",
            pack_id="release-flow",
            registry_id="team-catalog",
            scope="project",
        )
    )

    assert registry.methods == ["release-flow"]
    assert len(discovered) == 1
    assert discovered[0].installed is False
    assert installed.id == "release-flow"
    assert installed.scope == "project"
    assert workspace.search_catalog(kind="method", query="release")[0].installed is True
    assert (root / ".agora" / "methods" / "release-flow" / "METHOD.md").exists()


def test_project_registry_takes_precedence_over_user_registry(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    workspace = AgoraWorkspace(cwd=root)
    workspace.initialize(InitInput(integration="generic"))
    user_source = _registry(
        tmp_path / "user-source",
        registry_id="user-catalog",
        registry_name="User Catalog",
        method_name="User Release Flow",
    )
    project_source = _registry(
        tmp_path / "project-source",
        registry_id="project-catalog",
        registry_name="Project Catalog",
        method_name="Project Release Flow",
    )
    workspace.install_registry(InstallRegistryInput(source=str(user_source), scope="user"))
    workspace.install_registry(InstallRegistryInput(source=str(project_source), scope="project"))

    installed = workspace.install_catalog_pack(
        InstallCatalogPackInput(kind="method", pack_id="release-flow", scope="project")
    )

    assert installed.name == "Project Release Flow"
    report = workspace.validate()
    assert report.ok is True
    assert report.checked["registries"] == 1

    manifest = root / ".agora" / "registries" / "project-catalog" / "REGISTRY.md"
    manifest.write_text(manifest.read_text().replace("agora/registry/v1", "agora/registry/v9"))
    corrupted = workspace.validate()
    assert corrupted.ok is False
    assert any(issue.code == "registry.invalid" for issue in corrupted.issues)


def test_rejects_an_invalid_registry_before_copying_it(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    source = tmp_path / "empty-registry"
    source.mkdir()
    (source / "REGISTRY.md").write_text(
        '---\nschema: "agora/registry/v1"\nid: "empty"\nname: "Empty"\n---\n\n# Empty\n'
    )
    (source / "methods" / "incomplete").mkdir(parents=True)
    workspace = AgoraWorkspace(cwd=root)
    workspace.initialize(InitInput(integration="generic"))

    with pytest.raises(FileNotFoundError, match="missing METHOD.md"):
        workspace.install_registry(InstallRegistryInput(source=str(source), scope="project"))

    assert not (root / ".agora" / "registries" / "empty").exists()


def test_cli_installs_searches_and_selects_a_catalog_pack(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    source = _registry(
        tmp_path / "cli-source",
        registry_id="cli-catalog",
        registry_name="CLI Catalog",
    )
    AgoraWorkspace(cwd=root).initialize(InitInput(integration="generic"))
    output = io.StringIO()
    errors = io.StringIO()

    assert (
        main(
            ["registry", "install", "--source", str(source), "--scope", "user"],
            cwd=root,
            stdout=output,
            stderr=errors,
        )
        == 0
    )
    assert (
        main(
            ["pack", "search", "--kind", "method", "--registry", "cli-catalog"],
            cwd=root,
            stdout=output,
            stderr=errors,
        )
        == 0
    )
    assert (
        main(
            [
                "pack",
                "install",
                "--kind",
                "method",
                "--id",
                "release-flow",
                "--registry",
                "cli-catalog",
            ],
            cwd=root,
            stdout=output,
            stderr=errors,
        )
        == 0
    )

    assert errors.getvalue() == ""
    assert '"registry": "cli-catalog"' in output.getvalue()
    assert '"id": "release-flow"' in output.getvalue()
    assert (root / ".agora" / "methods" / "release-flow" / "METHOD.md").exists()
