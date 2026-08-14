import io
import shutil
from pathlib import Path

import pytest

from agora.cli import main
from agora.filesystem import template_root
from agora.markdown import MarkdownDocument, read_markdown, render_markdown
from agora.model import (
    InitInput,
    InstallCatalogPackInput,
    InstallRegistryInput,
    InstallToolInput,
)
from agora.packs import compare_pack_versions, version_satisfies
from agora.tools import load_tool_contract
from agora.workspace import AgoraWorkspace


def _tool(
    destination: Path,
    id_: str,
    version: str,
    dependencies: list[dict[str, str]] | None = None,
) -> Path:
    shutil.copytree(template_root() / "tools" / "repository", destination)
    document = read_markdown(destination / "TOOL.md")
    document.attributes.update(
        {
            "id": id_,
            "name": id_.replace("-", " ").title(),
            "version": version,
            "dependencies": dependencies or [],
        }
    )
    (destination / "TOOL.md").write_text(render_markdown(document), encoding="utf-8")
    return destination


def _method(
    destination: Path,
    id_: str,
    version: str,
    dependencies: list[dict[str, str]] | None = None,
) -> Path:
    shutil.copytree(template_root() / "methods" / "scrum", destination)
    document = read_markdown(destination / "METHOD.md")
    document.attributes.update(
        {
            "id": id_,
            "name": id_.replace("-", " ").title(),
            "version": version,
            "dependencies": dependencies or [],
        }
    )
    (destination / "METHOD.md").write_text(render_markdown(document), encoding="utf-8")
    return destination


def _registry(destination: Path, packs: list[tuple[str, Path]]) -> Path:
    destination.mkdir()
    (destination / "REGISTRY.md").write_text(
        render_markdown(
            MarkdownDocument(
                attributes={
                    "schema": "agora/registry/v1",
                    "id": "dependency-catalog",
                    "name": "Dependency Catalog",
                },
                body="# Dependency Catalog",
            )
        ),
        encoding="utf-8",
    )
    for kind, source in packs:
        shutil.copytree(source, destination / f"{kind}s" / source.name)
    return destination


def _workspace(tmp_path: Path, monkeypatch) -> AgoraWorkspace:
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    workspace = AgoraWorkspace(cwd=root)
    workspace.initialize(InitInput(integration="generic"))
    return workspace


def test_compares_pack_versions_and_evaluates_constraints() -> None:
    assert compare_pack_versions("1.10.0", "1.9.9") > 0
    assert version_satisfies("1.4.2", ">=1.0.0,<2.0.0") is True
    assert version_satisfies("2.0.0", ">=1.0.0,<2.0.0") is False
    assert version_satisfies("7.3.1", "*") is True

    with pytest.raises(ValueError, match="comma-separated"):
        version_satisfies("1.0.0", "^1.0.0")


def test_rejects_invalid_and_duplicate_dependency_declarations(tmp_path: Path) -> None:
    source = _tool(tmp_path / "tool", "consumer", "1.0.0")
    document = read_markdown(source / "TOOL.md")
    document.attributes["dependencies"] = [
        {"kind": "tool", "id": "provider", "version": "1.0.0"},
        {"kind": "tool", "id": "provider", "version": ">=1.0.0"},
    ]
    (source / "TOOL.md").write_text(render_markdown(document), encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate dependency: tool/provider"):
        load_tool_contract(source)

    document.attributes["dependencies"] = [
        {"kind": "service", "id": "provider", "version": "1.0.0"}
    ]
    (source / "TOOL.md").write_text(render_markdown(document), encoding="utf-8")
    with pytest.raises(ValueError, match="dependency kind is unsupported"):
        load_tool_contract(source)


def test_catalog_install_resolves_and_installs_transitive_dependencies(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    sources = tmp_path / "sources"
    tracker = _tool(sources / "tracker", "tracker", "1.4.0")
    delivery = _method(
        sources / "delivery",
        "delivery",
        "2.0.0",
        [{"kind": "tool", "id": "tracker", "version": ">=1.0.0,<2.0.0"}],
    )
    registry = _registry(tmp_path / "registry", [("tool", tracker), ("method", delivery)])
    workspace.install_registry(InstallRegistryInput(source=str(registry), scope="project"))

    installed = workspace.install_catalog_pack(
        InstallCatalogPackInput(
            kind="method",
            pack_id="delivery",
            registry_id="dependency-catalog",
            scope="project",
        )
    )

    assert installed.version == "2.0.0"
    assert [(item.kind, item.id, item.version) for item in installed.dependencies] == [
        ("tool", "tracker", ">=1.0.0,<2.0.0")
    ]
    assert (workspace.project_root() / ".agora" / "tools" / "tracker" / "TOOL.md").is_file()
    assert workspace.validate().ok is True


def test_catalog_resolution_rejects_missing_dependencies_without_copying(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    method = _method(
        tmp_path / "sources" / "delivery",
        "delivery",
        "1.0.0",
        [{"kind": "tool", "id": "missing", "version": ">=1.0.0"}],
    )
    registry = _registry(tmp_path / "registry", [("method", method)])
    workspace.install_registry(InstallRegistryInput(source=str(registry), scope="project"))

    with pytest.raises(ValueError, match="Cannot resolve dependency tool/missing"):
        workspace.install_catalog_pack(
            InstallCatalogPackInput(kind="method", pack_id="delivery", scope="project")
        )

    assert not (workspace.project_root() / ".agora" / "methods" / "delivery").exists()


def test_catalog_resolution_rejects_dependency_cycles_without_copying(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    sources = tmp_path / "sources"
    alpha = _tool(
        sources / "alpha",
        "alpha",
        "1.0.0",
        [{"kind": "tool", "id": "beta", "version": "1.0.0"}],
    )
    beta = _tool(
        sources / "beta",
        "beta",
        "1.0.0",
        [{"kind": "tool", "id": "alpha", "version": "1.0.0"}],
    )
    registry = _registry(tmp_path / "registry", [("tool", alpha), ("tool", beta)])
    workspace.install_registry(InstallRegistryInput(source=str(registry), scope="project"))

    with pytest.raises(ValueError, match="Pack dependency cycle"):
        workspace.install_catalog_pack(
            InstallCatalogPackInput(kind="tool", pack_id="alpha", scope="project")
        )

    assert not (workspace.project_root() / ".agora" / "tools" / "alpha").exists()
    assert not (workspace.project_root() / ".agora" / "tools" / "beta").exists()


def test_direct_install_and_force_replacement_preserve_composition(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    sources = tmp_path / "sources"
    provider_v1 = _tool(sources / "provider-v1", "provider", "1.0.0")
    provider_v2 = _tool(sources / "provider-v2", "provider", "2.0.0")
    consumer = _tool(
        sources / "consumer",
        "consumer",
        "1.0.0",
        [{"kind": "tool", "id": "provider", "version": ">=1.0.0,<2.0.0"}],
    )

    with pytest.raises(ValueError, match="requires missing tool/provider"):
        workspace.install_tool(InstallToolInput(source=str(consumer), scope="project"))

    workspace.install_tool(InstallToolInput(source=str(provider_v1), scope="project"))
    workspace.install_tool(InstallToolInput(source=str(consumer), scope="project"))
    with pytest.raises(ValueError, match="but 2.0.0 is installed"):
        workspace.install_tool(
            InstallToolInput(source=str(provider_v2), scope="project", force=True)
        )

    assert workspace.show_tool("provider").version == "1.0.0"


def test_validation_reports_a_dependency_broken_outside_the_cli(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    sources = tmp_path / "sources"
    provider = _tool(sources / "provider", "provider", "1.0.0")
    consumer = _tool(
        sources / "consumer",
        "consumer",
        "1.0.0",
        [{"kind": "tool", "id": "provider", "version": "1.0.0"}],
    )
    workspace.install_tool(InstallToolInput(source=str(provider), scope="project"))
    workspace.install_tool(InstallToolInput(source=str(consumer), scope="project"))
    (workspace.project_root() / ".agora" / "tools" / "provider").rename(
        workspace.project_root() / ".agora" / "tools" / "provider-removed"
    )

    report = workspace.validate()

    assert report.ok is False
    assert any(issue.code == "pack.dependency-invalid" for issue in report.issues)


def test_cli_catalog_install_reports_version_and_dependencies(tmp_path: Path, monkeypatch) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    sources = tmp_path / "sources"
    tracker = _tool(sources / "tracker", "tracker", "1.2.0")
    method = _method(
        sources / "delivery",
        "delivery",
        "1.0.0",
        [{"kind": "tool", "id": "tracker", "version": ">=1.0.0"}],
    )
    registry = _registry(tmp_path / "registry", [("tool", tracker), ("method", method)])
    workspace.install_registry(InstallRegistryInput(source=str(registry), scope="project"))
    output = io.StringIO()

    assert (
        main(
            [
                "pack",
                "install",
                "--kind",
                "method",
                "--id",
                "delivery",
                "--scope",
                "project",
            ],
            cwd=workspace.project_root(),
            stdout=output,
        )
        == 0
    )
    rendered = output.getvalue()
    assert '"version": "1.0.0"' in rendered
    assert '"id": "tracker"' in rendered
