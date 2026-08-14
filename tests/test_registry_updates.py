import base64
import hashlib
import io
import json
import shutil
import tarfile
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from agora.cli import main
from agora.model import (
    AddRegistryTrustKeyInput,
    InitInput,
    InstallRegistryInput,
    RegistryReleaseRecord,
    UpdateRegistryInput,
)
from agora.registries import read_registry_update
from agora.registry_distribution import release_signature_payload
from agora.workspace import AgoraWorkspace

ROOT = Path(__file__).parents[1]


def _public_key(private_key: Ed25519PrivateKey, path: Path) -> Path:
    path.write_bytes(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    return path


def _release(
    distribution: Path,
    version: str,
    private_key: Ed25519PrivateKey | None,
) -> RegistryReleaseRecord:
    registry = distribution / f"source-{version}"
    registry.mkdir()
    (registry / "REGISTRY.md").write_text(
        '---\nschema: "agora/registry/v1"\nid: "team-catalog"\n'
        f'name: "Team Catalog {version}"\nversion: "{version}"\n---\n\n# Team Catalog\n',
        encoding="utf-8",
    )
    shutil.copytree(
        ROOT / "samples" / "custom-lifecycle" / "release-flow",
        registry / "methods" / "release-flow",
    )
    archive_name = f"team-catalog-{version}.tar.gz"
    archive_path = distribution / archive_name
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(registry, arcname="team-catalog")
    release = RegistryReleaseRecord(
        registry="team-catalog",
        version=version,
        archive=archive_name,
        sha256=hashlib.sha256(archive_path.read_bytes()).hexdigest(),
        key_id="team-release" if private_key is not None else None,
    )
    if private_key is None:
        return release
    return RegistryReleaseRecord(
        registry=release.registry,
        version=release.version,
        archive=release.archive,
        sha256=release.sha256,
        signature=base64.b64encode(private_key.sign(release_signature_payload(release))).decode(),
        key_id=release.key_id,
    )


def _write_index(path: Path, releases: list[RegistryReleaseRecord]) -> Path:
    values = [
        {
            "version": item.version,
            "archive": item.archive,
            "sha256": item.sha256,
            **(
                {"signature": item.signature, "key-id": item.key_id}
                if item.signature is not None
                else {}
            ),
        }
        for item in releases
    ]
    path.write_text(
        '---\nschema: "agora/registry-index/v1"\nid: "team-catalog"\n'
        f'name: "Team Catalog"\nreleases: {json.dumps(values, separators=(",", ":"))}\n'
        "---\n\n# Team Catalog releases\n",
        encoding="utf-8",
    )
    return path


def _workspace_with_release(
    tmp_path: Path,
    monkeypatch,
    releases: list[RegistryReleaseRecord],
    private_key: Ed25519PrivateKey,
) -> tuple[AgoraWorkspace, Path]:
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    index = _write_index(tmp_path / "INDEX.md", [releases[0]])
    workspace = AgoraWorkspace(cwd=root)
    workspace.initialize(InitInput(integration="generic"))
    workspace.add_registry_trust_key(
        AddRegistryTrustKeyInput(
            id="team-release",
            registry_id="team-catalog",
            public_key=str(_public_key(private_key, tmp_path / "team-release.pem")),
            scope="project",
        )
    )
    workspace.install_registry(
        InstallRegistryInput(
            source=str(index),
            scope="project",
            require_signature=True,
        )
    )
    _write_index(index, releases)
    return workspace, index


def test_previews_and_applies_signed_registry_updates_with_history(
    tmp_path: Path, monkeypatch
) -> None:
    private_key = Ed25519PrivateKey.generate()
    releases = [_release(tmp_path, version, private_key) for version in ("1.0.0", "1.1.0")]
    workspace, _ = _workspace_with_release(tmp_path, monkeypatch, releases, private_key)

    preview = workspace.update_registry(UpdateRegistryInput(id="team-catalog"))

    assert preview.update_available is True
    assert preview.applied is False
    assert preview.from_version == "1.0.0"
    assert preview.to_version == "1.1.0"
    current = workspace.list_registries()[0]
    assert current.version == "1.0.0"
    assert not (Path(current.path) / "updates").exists()

    applied = workspace.update_registry(UpdateRegistryInput(id="team-catalog", apply=True))

    assert applied.applied is True
    assert applied.record_path is not None
    update = read_registry_update(Path(applied.record_path))
    assert update.from_version == "1.0.0"
    assert update.to_version == "1.1.0"
    assert update.signature_verified is True
    assert workspace.list_registries()[0].version == "1.1.0"
    assert workspace.validate().ok is True

    release_2 = _release(tmp_path, "1.2.0", private_key)
    _write_index(tmp_path / "INDEX.md", [*releases, release_2])
    second = workspace.update_registry(UpdateRegistryInput(id="team-catalog", apply=True))
    assert second.to_version == "1.2.0"
    history = sorted((Path(workspace.list_registries()[0].path) / "updates").glob("*/UPDATE.md"))
    assert len(history) == 2
    assert workspace.validate().ok is True


def test_preview_authenticates_without_downloading_the_archive(tmp_path: Path, monkeypatch) -> None:
    private_key = Ed25519PrivateKey.generate()
    releases = [_release(tmp_path, version, private_key) for version in ("1.0.0", "2.0.0")]
    workspace, _ = _workspace_with_release(tmp_path, monkeypatch, releases, private_key)
    (tmp_path / releases[1].archive).unlink()

    preview = workspace.update_registry(UpdateRegistryInput(id="team-catalog"))

    assert preview.update_available is True
    assert preview.to_version == "2.0.0"
    with pytest.raises(FileNotFoundError, match="archive not found"):
        workspace.update_registry(UpdateRegistryInput(id="team-catalog", apply=True))


def test_rejects_downgrades_and_mutated_release_checksums(tmp_path: Path, monkeypatch) -> None:
    private_key = Ed25519PrivateKey.generate()
    releases = [_release(tmp_path, version, private_key) for version in ("1.0.0", "2.0.0")]
    workspace, index = _workspace_with_release(tmp_path, monkeypatch, releases, private_key)
    workspace.update_registry(UpdateRegistryInput(id="team-catalog", apply=True))

    with pytest.raises(ValueError, match="cannot downgrade"):
        workspace.update_registry(UpdateRegistryInput(id="team-catalog", version="1.0.0"))

    changed_unsigned = RegistryReleaseRecord(
        registry="team-catalog",
        version="2.0.0",
        archive=releases[1].archive,
        sha256="f" * 64,
        key_id="team-release",
    )
    changed = RegistryReleaseRecord(
        registry=changed_unsigned.registry,
        version=changed_unsigned.version,
        archive=changed_unsigned.archive,
        sha256=changed_unsigned.sha256,
        signature=base64.b64encode(
            private_key.sign(release_signature_payload(changed_unsigned))
        ).decode(),
        key_id=changed_unsigned.key_id,
    )
    _write_index(index, [changed])
    with pytest.raises(ValueError, match="changed checksum"):
        workspace.update_registry(UpdateRegistryInput(id="team-catalog"))


def test_signed_registry_cannot_update_to_an_unsigned_release(tmp_path: Path, monkeypatch) -> None:
    private_key = Ed25519PrivateKey.generate()
    signed = _release(tmp_path, "1.0.0", private_key)
    unsigned = _release(tmp_path, "2.0.0", None)
    workspace, _ = _workspace_with_release(tmp_path, monkeypatch, [signed, unsigned], private_key)

    with pytest.raises(ValueError, match="release is unsigned"):
        workspace.update_registry(UpdateRegistryInput(id="team-catalog"))


def test_cli_previews_and_applies_a_registry_update(tmp_path: Path, monkeypatch) -> None:
    private_key = Ed25519PrivateKey.generate()
    releases = [_release(tmp_path, version, private_key) for version in ("1.0.0", "1.1.0")]
    workspace, _ = _workspace_with_release(tmp_path, monkeypatch, releases, private_key)
    output = io.StringIO()
    errors = io.StringIO()

    assert (
        main(
            ["registry", "update", "--id", "team-catalog"],
            cwd=workspace.cwd,
            stdout=output,
            stderr=errors,
        )
        == 0
    )
    assert (
        main(
            ["registry", "update", "--id", "team-catalog", "--apply"],
            cwd=workspace.cwd,
            stdout=output,
            stderr=errors,
        )
        == 0
    )

    assert errors.getvalue() == ""
    assert '"update_available": true' in output.getvalue()
    assert '"applied": true' in output.getvalue()


def test_project_validation_rejects_corrupted_registry_update_history(
    tmp_path: Path, monkeypatch
) -> None:
    private_key = Ed25519PrivateKey.generate()
    releases = [_release(tmp_path, version, private_key) for version in ("1.0.0", "1.1.0")]
    workspace, _ = _workspace_with_release(tmp_path, monkeypatch, releases, private_key)
    applied = workspace.update_registry(UpdateRegistryInput(id="team-catalog", apply=True))
    assert applied.record_path is not None
    record = Path(applied.record_path)
    record.write_text(
        record.read_text(encoding="utf-8").replace(
            "agora/registry-update/v1", "agora/registry-update/v9"
        ),
        encoding="utf-8",
    )

    report = workspace.validate()

    assert report.ok is False
    assert any(issue.code == "registry.invalid" for issue in report.issues)
