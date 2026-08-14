import base64
import hashlib
import json
import os
import shutil
import tarfile
import tempfile
from dataclasses import asdict
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from agora.model import (
    AddRegistryTrustKeyInput,
    InitInput,
    InstallCatalogPackInput,
    InstallRegistryInput,
    RegistryReleaseRecord,
    UpdateRegistryInput,
)
from agora.registry_distribution import release_signature_payload
from agora.workspace import AgoraWorkspace


def main() -> None:
    repository = Path(__file__).resolve().parents[2]
    runtime = Path(tempfile.mkdtemp(prefix="agora-remote-registry-sample-"))
    project = runtime / "project"
    registry = runtime / "registry"
    project.mkdir()
    registry.mkdir()
    os.environ["AGORA_HOME"] = str(runtime / "home")
    os.environ["AGORA_LOCK_HOME"] = str(runtime / "locks")

    (registry / "REGISTRY.md").write_text(
        '---\nschema: "agora/registry/v1"\nid: "team-catalog"\n'
        'name: "Team Catalog"\nversion: "1.0.0"\n---\n\n# Team Catalog\n',
        encoding="utf-8",
    )
    shutil.copytree(
        repository / "samples" / "custom-lifecycle" / "release-flow",
        registry / "methods" / "release-flow",
    )
    archive_name = "team-catalog-1.0.0.tar.gz"
    archive_path = runtime / archive_name
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(registry, arcname="team-catalog")

    release = RegistryReleaseRecord(
        registry="team-catalog",
        version="1.0.0",
        archive=archive_name,
        sha256=hashlib.sha256(archive_path.read_bytes()).hexdigest(),
        key_id="sample-release",
    )
    private_key = Ed25519PrivateKey.generate()
    signature = base64.b64encode(private_key.sign(release_signature_payload(release))).decode()
    public_key = runtime / "sample-release.pem"
    public_key.write_bytes(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    releases = [
        {
            "version": release.version,
            "archive": release.archive,
            "sha256": release.sha256,
            "signature": signature,
            "key-id": release.key_id,
        }
    ]
    index = runtime / "INDEX.md"
    index.write_text(
        '---\nschema: "agora/registry-index/v1"\nid: "team-catalog"\n'
        f'name: "Team Catalog"\nreleases: {json.dumps(releases, separators=(",", ":"))}\n'
        "---\n\n# Team Catalog releases\n",
        encoding="utf-8",
    )

    agora = AgoraWorkspace(cwd=project)
    agora.initialize(InitInput(integration="generic"))
    trusted_key = agora.add_registry_trust_key(
        AddRegistryTrustKeyInput(
            id="sample-release",
            registry_id="team-catalog",
            public_key=str(public_key),
            scope="project",
        )
    )
    installed_registry = agora.install_registry(
        InstallRegistryInput(
            source=index.as_uri(),
            scope="project",
            version="1.0.0",
            require_signature=True,
        )
    )
    installed_method = agora.install_catalog_pack(
        InstallCatalogPackInput(
            kind="method",
            pack_id="release-flow",
            registry_id="team-catalog",
            scope="project",
        )
    )

    (registry / "REGISTRY.md").write_text(
        '---\nschema: "agora/registry/v1"\nid: "team-catalog"\n'
        'name: "Team Catalog"\nversion: "1.1.0"\n---\n\n# Team Catalog\n',
        encoding="utf-8",
    )
    archive_v2_name = "team-catalog-1.1.0.tar.gz"
    archive_v2_path = runtime / archive_v2_name
    with tarfile.open(archive_v2_path, "w:gz") as archive:
        archive.add(registry, arcname="team-catalog")
    release_v2 = RegistryReleaseRecord(
        registry="team-catalog",
        version="1.1.0",
        archive=archive_v2_name,
        sha256=hashlib.sha256(archive_v2_path.read_bytes()).hexdigest(),
        key_id="sample-release",
    )
    signature_v2 = base64.b64encode(
        private_key.sign(release_signature_payload(release_v2))
    ).decode()
    releases.append(
        {
            "version": release_v2.version,
            "archive": release_v2.archive,
            "sha256": release_v2.sha256,
            "signature": signature_v2,
            "key-id": release_v2.key_id,
        }
    )
    index.write_text(
        '---\nschema: "agora/registry-index/v1"\nid: "team-catalog"\n'
        f'name: "Team Catalog"\nreleases: {json.dumps(releases, separators=(",", ":"))}\n'
        "---\n\n# Team Catalog releases\n",
        encoding="utf-8",
    )
    update_preview = agora.update_registry(UpdateRegistryInput(id="team-catalog"))
    applied_update = agora.update_registry(UpdateRegistryInput(id="team-catalog", apply=True))
    report = agora.validate()
    assert report.ok
    assert installed_registry.signature_verified
    assert update_preview.update_available and not update_preview.applied
    assert applied_update.applied

    print(f"Runtime: {runtime}")
    print(f"Trusted key: {trusted_key.id} ({trusted_key.fingerprint})")
    print("Verified registry:")
    print(json.dumps(asdict(installed_registry), indent=2))
    print("Installed pack:")
    print(json.dumps(asdict(installed_method), indent=2))
    print("Registry update preview:")
    print(json.dumps(asdict(update_preview), indent=2))
    print("Applied registry update:")
    print(json.dumps(asdict(applied_update), indent=2))
    print(f"Validation issues: {len(report.issues)}")


if __name__ == "__main__":
    main()
