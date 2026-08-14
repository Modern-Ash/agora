import json
import os
import shutil
import tempfile
from dataclasses import asdict
from pathlib import Path

from agora.model import CreateSwarmInput, InitInput, InstallCatalogPackInput, InstallRegistryInput
from agora.workspace import AgoraWorkspace


def main() -> None:
    repository = Path(__file__).resolve().parents[2]
    runtime = Path(tempfile.mkdtemp(prefix="agora-registry-sample-"))
    project = runtime / "project"
    registry_source = runtime / "team-registry"
    project.mkdir()
    registry_source.mkdir()
    os.environ["AGORA_HOME"] = str(runtime / "home")
    os.environ["AGORA_LOCK_HOME"] = str(runtime / "locks")

    (registry_source / "REGISTRY.md").write_text(
        '---\nschema: "agora/registry/v1"\nid: "team-catalog"\n'
        'name: "Team Catalog"\n---\n\n# Team Catalog\n',
        encoding="utf-8",
    )
    shutil.copytree(
        repository / "samples" / "custom-lifecycle" / "release-flow",
        registry_source / "methods" / "release-flow",
    )

    agora = AgoraWorkspace(cwd=project)
    agora.initialize(InitInput(integration="generic"))
    registry = agora.install_registry(
        InstallRegistryInput(source=str(registry_source), scope="user")
    )
    discovered = agora.search_catalog(kind="method", query="release", registry_id="team-catalog")
    installed = agora.install_catalog_pack(
        InstallCatalogPackInput(
            kind="method",
            pack_id="release-flow",
            registry_id="team-catalog",
            scope="project",
        )
    )
    swarm = agora.create_swarm(
        CreateSwarmInput(
            id="registry-delivery",
            objective="Deliver through a discovered lifecycle",
            method="release-flow",
            create_branch=False,
        )
    )
    report = agora.validate()
    assert report.ok

    print(f"Runtime: {runtime}")
    print("Registry:")
    print(json.dumps(asdict(registry), indent=2))
    print("Discovered packs:")
    print(json.dumps([asdict(item) for item in discovered], indent=2))
    print("Installed pack:")
    print(json.dumps(asdict(installed), indent=2))
    print(f"Swarm method: {swarm.method}")
    print(f"Validation issues: {len(report.issues)}")


if __name__ == "__main__":
    main()
