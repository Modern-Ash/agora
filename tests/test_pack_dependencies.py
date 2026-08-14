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
    RefreshPackLockInput,
    RemovePackInput,
    UpdateCatalogPackInput,
)
from agora.packs import (
    compare_pack_versions,
    read_pack_lock,
    read_pack_removal,
    version_satisfies,
)
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


def test_catalog_install_persists_pack_provenance(tmp_path: Path, monkeypatch) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    source = _tool(tmp_path / "sources" / "tracker", "tracker", "1.0.0")
    registry = _registry(tmp_path / "registry", [("tool", source)])
    workspace.install_registry(InstallRegistryInput(source=str(registry), scope="project"))

    installed = workspace.install_catalog_pack(
        InstallCatalogPackInput(kind="tool", pack_id="tracker", scope="project")
    )

    assert installed.source is not None
    assert installed.source.registry == "dependency-catalog"
    assert installed.source.version == "1.0.0"
    assert len(installed.source.sha256) == 64
    assert Path(installed.source.path).is_file()
    assert workspace.validate().checked["pack-sources"] == 1


def test_previews_and_applies_a_dependency_aware_pack_update(tmp_path: Path, monkeypatch) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    first = tmp_path / "first"
    provider_v1 = _tool(first / "provider", "provider", "1.0.0")
    consumer_v1 = _method(
        first / "consumer",
        "consumer",
        "1.0.0",
        [{"kind": "tool", "id": "provider", "version": ">=1.0.0,<2.0.0"}],
    )
    registry_v1 = _registry(
        tmp_path / "registry-v1", [("tool", provider_v1), ("method", consumer_v1)]
    )
    workspace.install_registry(InstallRegistryInput(source=str(registry_v1), scope="project"))
    workspace.install_catalog_pack(
        InstallCatalogPackInput(kind="method", pack_id="consumer", scope="project")
    )

    second = tmp_path / "second"
    provider_v2 = _tool(second / "provider", "provider", "2.0.0")
    consumer_v2 = _method(
        second / "consumer",
        "consumer",
        "2.0.0",
        [{"kind": "tool", "id": "provider", "version": ">=2.0.0,<3.0.0"}],
    )
    registry_v2 = _registry(
        tmp_path / "registry-v2", [("tool", provider_v2), ("method", consumer_v2)]
    )
    workspace.install_registry(
        InstallRegistryInput(source=str(registry_v2), scope="project", force=True)
    )

    preview = workspace.update_catalog_pack(
        UpdateCatalogPackInput(kind="method", pack_id="consumer")
    )

    assert preview.update_available is True
    assert preview.applied is False
    assert [(item.kind, item.id, item.from_version, item.to_version) for item in preview.packs] == [
        ("tool", "provider", "1.0.0", "2.0.0"),
        ("method", "consumer", "1.0.0", "2.0.0"),
    ]
    assert workspace.show_tool("provider").version == "1.0.0"
    assert (
        next(item for item in workspace.list_methods() if item.id == "consumer").version == "1.0.0"
    )

    original_replace = Path.replace

    def fail_second_swap(path: Path, target: Path) -> Path:
        if path.name == "consumer" and ".pack-plan-stage-" in str(path):
            raise OSError("simulated second pack swap failure")
        return original_replace(path, target)

    with monkeypatch.context() as transaction_patch:
        transaction_patch.setattr(Path, "replace", fail_second_swap)
        with pytest.raises(OSError, match="second pack swap failure"):
            workspace.update_catalog_pack(
                UpdateCatalogPackInput(kind="method", pack_id="consumer", apply=True)
            )
    assert workspace.show_tool("provider").version == "1.0.0"
    assert (
        next(item for item in workspace.list_methods() if item.id == "consumer").version == "1.0.0"
    )

    applied = workspace.update_catalog_pack(
        UpdateCatalogPackInput(kind="method", pack_id="consumer", apply=True)
    )

    assert applied.applied is True
    assert len(applied.history_paths) == 2
    assert all(Path(path).is_file() for path in applied.history_paths)
    assert workspace.show_tool("provider").version == "2.0.0"
    consumer = next(item for item in workspace.list_methods() if item.id == "consumer")
    assert consumer.version == "2.0.0"
    assert consumer.source is not None
    assert len(consumer.updates) == 1
    assert consumer.updates[0].from_version == "1.0.0"
    assert consumer.updates[0].to_version == "2.0.0"
    assert workspace.show_tool("provider").updates[0].to_version == "2.0.0"
    assert workspace.validate().ok is True


def test_pack_update_protects_local_modifications(tmp_path: Path, monkeypatch) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    source_v1 = _tool(tmp_path / "first" / "tracker", "tracker", "1.0.0")
    registry_v1 = _registry(tmp_path / "registry-v1", [("tool", source_v1)])
    workspace.install_registry(InstallRegistryInput(source=str(registry_v1), scope="project"))
    workspace.install_catalog_pack(
        InstallCatalogPackInput(kind="tool", pack_id="tracker", scope="project")
    )
    installed_manifest = workspace.project_root() / ".agora" / "tools" / "tracker" / "TOOL.md"
    installed_manifest.write_text(
        installed_manifest.read_text(encoding="utf-8") + "\nLocal policy amendment.\n",
        encoding="utf-8",
    )
    source_v2 = _tool(tmp_path / "second" / "tracker", "tracker", "2.0.0")
    registry_v2 = _registry(tmp_path / "registry-v2", [("tool", source_v2)])
    workspace.install_registry(
        InstallRegistryInput(source=str(registry_v2), scope="project", force=True)
    )

    preview = workspace.update_catalog_pack(UpdateCatalogPackInput(kind="tool", pack_id="tracker"))
    assert preview.modified is True
    report = workspace.validate()
    assert report.ok is False
    assert any(issue.code == "pack-source.modified" for issue in report.issues)
    assert any(issue.code == "pack-lock.drift" for issue in report.issues)
    lock = workspace.refresh_pack_lock(RefreshPackLockInput(scope="project"))
    assert any(item.id == "tracker" and item.sha256 != item.source_sha256 for item in lock.packs)
    refreshed = workspace.validate()
    assert refreshed.ok is True
    assert any(issue.code == "pack-source.modified" for issue in refreshed.issues)
    with pytest.raises(ValueError, match="locally modified"):
        workspace.update_catalog_pack(
            UpdateCatalogPackInput(kind="tool", pack_id="tracker", apply=True)
        )
    assert workspace.show_tool("tracker").version == "1.0.0"

    workspace.update_catalog_pack(
        UpdateCatalogPackInput(kind="tool", pack_id="tracker", apply=True, force=True)
    )
    assert workspace.show_tool("tracker").version == "2.0.0"


def test_pack_update_rejects_mutable_versions_and_direct_installs(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    direct = _tool(tmp_path / "direct", "direct", "1.0.0")
    workspace.install_tool(InstallToolInput(source=str(direct), scope="project"))
    with pytest.raises(ValueError, match="not installed from a catalog"):
        workspace.update_catalog_pack(UpdateCatalogPackInput(kind="tool", pack_id="direct"))

    source = _tool(tmp_path / "first" / "tracker", "tracker", "1.0.0")
    registry = _registry(tmp_path / "registry-v1", [("tool", source)])
    workspace.install_registry(InstallRegistryInput(source=str(registry), scope="project"))
    workspace.install_catalog_pack(
        InstallCatalogPackInput(kind="tool", pack_id="tracker", scope="project")
    )
    changed = _tool(tmp_path / "changed" / "tracker", "tracker", "1.0.0")
    document = read_markdown(changed / "TOOL.md")
    document.attributes["name"] = "Changed Without Version"
    (changed / "TOOL.md").write_text(render_markdown(document), encoding="utf-8")
    changed_registry = _registry(tmp_path / "registry-v1-changed", [("tool", changed)])
    workspace.install_registry(
        InstallRegistryInput(source=str(changed_registry), scope="project", force=True)
    )

    with pytest.raises(ValueError, match="changed content"):
        workspace.update_catalog_pack(UpdateCatalogPackInput(kind="tool", pack_id="tracker"))


def test_cli_previews_and_applies_a_pack_update(tmp_path: Path, monkeypatch) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    source_v1 = _tool(tmp_path / "first" / "tracker", "tracker", "1.0.0")
    registry_v1 = _registry(tmp_path / "registry-v1", [("tool", source_v1)])
    workspace.install_registry(InstallRegistryInput(source=str(registry_v1), scope="project"))
    workspace.install_catalog_pack(
        InstallCatalogPackInput(kind="tool", pack_id="tracker", scope="project")
    )
    source_v2 = _tool(tmp_path / "second" / "tracker", "tracker", "2.0.0")
    registry_v2 = _registry(tmp_path / "registry-v2", [("tool", source_v2)])
    workspace.install_registry(
        InstallRegistryInput(source=str(registry_v2), scope="project", force=True)
    )
    output = io.StringIO()

    assert (
        main(
            ["pack", "update", "--kind", "tool", "--id", "tracker"],
            cwd=workspace.project_root(),
            stdout=output,
        )
        == 0
    )
    assert '"update_available": true' in output.getvalue()
    assert '"applied": false' in output.getvalue()
    output.seek(0)
    output.truncate(0)
    assert (
        main(
            ["pack", "update", "--kind", "tool", "--id", "tracker", "--apply"],
            cwd=workspace.project_root(),
            stdout=output,
        )
        == 0
    )
    assert '"applied": true' in output.getvalue()
    assert workspace.show_tool("tracker").version == "2.0.0"


def test_pack_lock_tracks_managed_mutations_and_cli_refreshes_manual_changes(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    lock_path = workspace.project_root() / ".agora" / "PACKS.lock.md"
    initial = read_pack_lock(lock_path)
    assert [(item.kind, item.id) for item in initial.packs] == [
        ("method", "kanban"),
        ("method", "scrum"),
        ("tool", "repository"),
        ("tool", "work-management"),
    ]
    direct = _tool(tmp_path / "direct", "direct", "1.0.0")
    workspace.install_tool(InstallToolInput(source=str(direct), scope="project"))
    installed = read_pack_lock(lock_path)
    assert ("tool", "direct") in [(item.kind, item.id) for item in installed.packs]
    manifest = workspace.project_root() / ".agora" / "tools" / "direct" / "TOOL.md"
    manifest.write_text(manifest.read_text(encoding="utf-8") + "\nLocal amendment.\n")
    assert any(issue.code == "pack-lock.drift" for issue in workspace.validate().issues)
    output = io.StringIO()

    assert (
        main(
            ["pack", "lock", "--scope", "project"],
            cwd=workspace.project_root(),
            stdout=output,
        )
        == 0
    )
    assert '"scope": "project"' in output.getvalue()
    assert workspace.validate().ok is True


def test_validation_rejects_pack_update_history_that_disagrees_with_source(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    source_v1 = _tool(tmp_path / "first" / "tracker", "tracker", "1.0.0")
    registry_v1 = _registry(tmp_path / "registry-v1", [("tool", source_v1)])
    workspace.install_registry(InstallRegistryInput(source=str(registry_v1), scope="project"))
    workspace.install_catalog_pack(
        InstallCatalogPackInput(kind="tool", pack_id="tracker", scope="project")
    )
    source_v2 = _tool(tmp_path / "second" / "tracker", "tracker", "2.0.0")
    registry_v2 = _registry(tmp_path / "registry-v2", [("tool", source_v2)])
    workspace.install_registry(
        InstallRegistryInput(source=str(registry_v2), scope="project", force=True)
    )
    update = workspace.update_catalog_pack(
        UpdateCatalogPackInput(kind="tool", pack_id="tracker", apply=True)
    )
    history_path = Path(update.history_paths[0])
    document = read_markdown(history_path)
    document.attributes["to-sha256"] = "0" * 64
    history_path.write_text(render_markdown(document), encoding="utf-8")

    report = workspace.validate()

    assert report.ok is False
    assert any(issue.code == "pack-update.source-mismatch" for issue in report.issues)


def test_pack_removal_previews_and_prunes_unused_dependencies(tmp_path: Path, monkeypatch) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    sources = tmp_path / "sources"
    provider = _tool(sources / "provider", "provider", "1.0.0")
    consumer = _method(
        sources / "consumer",
        "consumer",
        "1.0.0",
        [{"kind": "tool", "id": "provider", "version": "1.0.0"}],
    )
    registry = _registry(tmp_path / "registry", [("tool", provider), ("method", consumer)])
    workspace.install_registry(InstallRegistryInput(source=str(registry), scope="project"))
    workspace.install_catalog_pack(
        InstallCatalogPackInput(kind="method", pack_id="consumer", scope="project")
    )

    preview = workspace.remove_pack(
        RemovePackInput(kind="method", pack_id="consumer", scope="project")
    )
    assert preview.applied is False
    assert [(item.kind, item.id, item.reason) for item in preview.packs] == [
        ("method", "consumer", "requested")
    ]
    assert (workspace.project_root() / ".agora" / "methods" / "consumer").is_dir()

    applied = workspace.remove_pack(
        RemovePackInput(
            kind="method",
            pack_id="consumer",
            scope="project",
            with_unused_dependencies=True,
            apply=True,
        )
    )
    assert applied.applied is True
    assert [(item.kind, item.id, item.reason) for item in applied.packs] == [
        ("method", "consumer", "requested"),
        ("tool", "provider", "unused-dependency"),
    ]
    assert applied.record_path is not None
    removal = read_pack_removal(Path(applied.record_path))
    assert removal.requested_id == "consumer"
    assert removal.packs == applied.packs
    lock = read_pack_lock(workspace.project_root() / ".agora" / "PACKS.lock.md")
    assert not {("method", "consumer"), ("tool", "provider")} & {
        (item.kind, item.id) for item in lock.packs
    }
    report = workspace.validate()
    assert report.ok is True
    assert report.checked["pack-removals"] == 1


def test_pack_removal_blocks_dependents_and_preserves_shared_dependencies(
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
    observer = _tool(
        sources / "observer",
        "observer",
        "1.0.0",
        [{"kind": "tool", "id": "provider", "version": "1.0.0"}],
    )
    registry = _registry(
        tmp_path / "registry",
        [("tool", provider), ("tool", consumer), ("tool", observer)],
    )
    workspace.install_registry(InstallRegistryInput(source=str(registry), scope="project"))
    workspace.install_catalog_pack(
        InstallCatalogPackInput(kind="tool", pack_id="consumer", scope="project")
    )
    workspace.install_catalog_pack(
        InstallCatalogPackInput(kind="tool", pack_id="observer", scope="project")
    )

    with pytest.raises(
        ValueError, match="required by installed packs: tool/consumer, tool/observer"
    ):
        workspace.remove_pack(RemovePackInput(kind="tool", pack_id="provider"))

    removed = workspace.remove_pack(
        RemovePackInput(
            kind="tool",
            pack_id="consumer",
            with_unused_dependencies=True,
            apply=True,
        )
    )
    assert [(item.kind, item.id) for item in removed.packs] == [("tool", "consumer")]
    assert workspace.show_tool("provider").version == "1.0.0"


def test_pack_removal_blocks_durable_runtime_references(tmp_path: Path, monkeypatch) -> None:
    workspace = _workspace(tmp_path, monkeypatch)

    with pytest.raises(ValueError, match="project default method scrum"):
        workspace.remove_pack(RemovePackInput(kind="method", pack_id="scrum"))


def test_pack_removal_rolls_back_a_multi_pack_failure(tmp_path: Path, monkeypatch) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    sources = tmp_path / "sources"
    provider = _tool(sources / "provider", "provider", "1.0.0")
    consumer = _tool(
        sources / "consumer",
        "consumer",
        "1.0.0",
        [{"kind": "tool", "id": "provider", "version": "1.0.0"}],
    )
    registry = _registry(tmp_path / "registry", [("tool", provider), ("tool", consumer)])
    workspace.install_registry(InstallRegistryInput(source=str(registry), scope="project"))
    workspace.install_catalog_pack(
        InstallCatalogPackInput(kind="tool", pack_id="consumer", scope="project")
    )
    original_lock = (workspace.project_root() / ".agora" / "PACKS.lock.md").read_text()
    original_replace = Path.replace

    def fail_provider_move(path: Path, target: Path) -> Path:
        if path.name == "provider" and ".pack-removal-stage-" in str(target):
            raise OSError("simulated pack removal failure")
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", fail_provider_move)
    with pytest.raises(OSError, match="simulated pack removal failure"):
        workspace.remove_pack(
            RemovePackInput(
                kind="tool",
                pack_id="consumer",
                with_unused_dependencies=True,
                apply=True,
            )
        )

    assert workspace.show_tool("consumer").version == "1.0.0"
    assert workspace.show_tool("provider").version == "1.0.0"
    assert (workspace.project_root() / ".agora" / "PACKS.lock.md").read_text() == original_lock
    assert not (workspace.project_root() / ".agora" / "pack-removals").exists()


def test_cli_previews_and_applies_pack_removal(tmp_path: Path, monkeypatch) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    source = _tool(tmp_path / "temporary", "temporary", "1.0.0")
    workspace.install_tool(InstallToolInput(source=str(source), scope="project"))
    output = io.StringIO()

    assert (
        main(
            ["pack", "remove", "--kind", "tool", "--id", "temporary"],
            cwd=workspace.project_root(),
            stdout=output,
        )
        == 0
    )
    assert '"applied": false' in output.getvalue()
    assert workspace.show_tool("temporary").version == "1.0.0"
    output.seek(0)
    output.truncate(0)

    assert (
        main(
            ["pack", "remove", "--kind", "tool", "--id", "temporary", "--apply"],
            cwd=workspace.project_root(),
            stdout=output,
        )
        == 0
    )
    assert '"applied": true' in output.getvalue()
    assert '"record_path":' in output.getvalue()
