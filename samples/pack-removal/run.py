import json
import os
import shutil
import tempfile
from dataclasses import asdict
from pathlib import Path

from agora.filesystem import packs_root
from agora.markdown import MarkdownDocument, read_markdown, render_markdown
from agora.model import InitInput, InstallCatalogPackInput, InstallRegistryInput, RemovePackInput
from agora.packs import read_pack_lock, read_pack_removal
from agora.workspace import AgoraWorkspace


def _rewrite_manifest(path: Path, **attributes: object) -> None:
    document = read_markdown(path)
    document.attributes.update(attributes)
    path.write_text(render_markdown(document), encoding="utf-8")


def main() -> None:
    runtime = Path(tempfile.mkdtemp(prefix="agora-pack-removal-sample-"))
    project = runtime / "project"
    registry = runtime / "removal-catalog"
    project.mkdir()
    registry.mkdir()
    os.environ["AGORA_HOME"] = str(runtime / "home")
    os.environ["AGORA_LOCK_HOME"] = str(runtime / "locks")

    (registry / "REGISTRY.md").write_text(
        render_markdown(
            MarkdownDocument(
                attributes={
                    "schema": "agora/registry/v1",
                    "id": "removal-catalog",
                    "name": "Removal Catalog",
                },
                body="# Removal Catalog",
            )
        ),
        encoding="utf-8",
    )
    tool = registry / "tools" / "delivery-tool"
    shutil.copytree(packs_root() / "tools" / "repository", tool)
    _rewrite_manifest(
        tool / "TOOL.md",
        id="delivery-tool",
        name="Delivery Tool",
        version="1.0.0",
        dependencies=[],
    )
    method = registry / "methods" / "delivery-flow"
    shutil.copytree(packs_root() / "methods" / "scrum", method)
    _rewrite_manifest(
        method / "METHOD.md",
        id="delivery-flow",
        name="Delivery Flow",
        version="1.0.0",
        dependencies=[{"kind": "tool", "id": "delivery-tool", "version": "1.0.0"}],
    )

    agora = AgoraWorkspace(cwd=project)
    agora.initialize(InitInput(integration="generic"))
    agora.install_registry(InstallRegistryInput(source=str(registry), scope="project"))
    agora.install_catalog_pack(
        InstallCatalogPackInput(
            kind="method",
            pack_id="delivery-flow",
            registry_id="removal-catalog",
            scope="project",
        )
    )
    removal = RemovePackInput(
        kind="method",
        pack_id="delivery-flow",
        scope="project",
        with_unused_dependencies=True,
    )
    preview = agora.remove_pack(removal)
    applied = agora.remove_pack(RemovePackInput(**{**removal.__dict__, "apply": True}))
    assert applied.record_path is not None
    record = read_pack_removal(Path(applied.record_path))
    pack_lock = read_pack_lock(project / ".agora" / "PACKS.lock.md")
    report = agora.validate()
    assert report.ok

    print(f"Runtime: {runtime}")
    print("Removal preview:")
    print(json.dumps(asdict(preview), indent=2))
    print("Applied removal:")
    print(json.dumps(asdict(applied), indent=2))
    print("Durable removal record:")
    print(json.dumps(asdict(record), indent=2))
    print("Resulting pack composition lock:")
    print(json.dumps(asdict(pack_lock), indent=2))
    print(f"Validated removal records: {report.checked['pack-removals']}")


if __name__ == "__main__":
    main()
