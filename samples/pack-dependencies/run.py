import json
import os
import shutil
import tempfile
from dataclasses import asdict
from pathlib import Path

from agora.filesystem import template_root
from agora.markdown import MarkdownDocument, read_markdown, render_markdown
from agora.model import (
    InitInput,
    InstallCatalogPackInput,
    InstallRegistryInput,
    UpdateCatalogPackInput,
)
from agora.workspace import AgoraWorkspace


def _rewrite_manifest(path: Path, **attributes: object) -> None:
    document = read_markdown(path)
    document.attributes.update(attributes)
    path.write_text(render_markdown(document), encoding="utf-8")


def main() -> None:
    runtime = Path(tempfile.mkdtemp(prefix="agora-pack-dependencies-sample-"))
    project = runtime / "project"
    registry = runtime / "dependency-catalog"
    project.mkdir()
    registry.mkdir()
    os.environ["AGORA_HOME"] = str(runtime / "home")
    os.environ["AGORA_LOCK_HOME"] = str(runtime / "locks")

    (registry / "REGISTRY.md").write_text(
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
    tool = registry / "tools" / "delivery-tool"
    shutil.copytree(template_root() / "tools" / "repository", tool)
    _rewrite_manifest(
        tool / "TOOL.md",
        id="delivery-tool",
        name="Delivery Tool",
        version="1.4.0",
        dependencies=[],
    )
    method = registry / "methods" / "delivery-flow"
    shutil.copytree(template_root() / "methods" / "scrum", method)
    _rewrite_manifest(
        method / "METHOD.md",
        id="delivery-flow",
        name="Delivery Flow",
        version="2.0.0",
        dependencies=[
            {
                "kind": "tool",
                "id": "delivery-tool",
                "version": ">=1.0.0,<2.0.0",
            }
        ],
    )

    agora = AgoraWorkspace(cwd=project)
    agora.initialize(InitInput(integration="generic"))
    agora.install_registry(InstallRegistryInput(source=str(registry), scope="project"))
    discovered = agora.search_catalog(registry_id="dependency-catalog")
    installed = agora.install_catalog_pack(
        InstallCatalogPackInput(
            kind="method",
            pack_id="delivery-flow",
            registry_id="dependency-catalog",
            scope="project",
        )
    )
    dependency = agora.show_tool("delivery-tool")
    assert installed.source is not None
    assert dependency.source is not None

    _rewrite_manifest(
        tool / "TOOL.md",
        version="2.1.0",
    )
    _rewrite_manifest(
        method / "METHOD.md",
        version="3.0.0",
        dependencies=[
            {
                "kind": "tool",
                "id": "delivery-tool",
                "version": ">=2.0.0,<3.0.0",
            }
        ],
    )
    agora.install_registry(InstallRegistryInput(source=str(registry), scope="project", force=True))
    update_preview = agora.update_catalog_pack(
        UpdateCatalogPackInput(kind="method", pack_id="delivery-flow")
    )
    update = agora.update_catalog_pack(
        UpdateCatalogPackInput(kind="method", pack_id="delivery-flow", apply=True)
    )
    report = agora.validate()
    assert report.ok

    print(f"Runtime: {runtime}")
    print("Catalog packs:")
    print(json.dumps([asdict(item) for item in discovered], indent=2))
    print("Requested Method Pack:")
    print(json.dumps(asdict(installed), indent=2))
    print("Resolved Tool Pack:")
    print(json.dumps(asdict(dependency), indent=2))
    print("Update preview:")
    print(json.dumps(asdict(update_preview), indent=2))
    print("Applied update:")
    print(json.dumps(asdict(update), indent=2))
    print(f"Validation issues: {len(report.issues)}")


if __name__ == "__main__":
    main()
