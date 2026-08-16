import base64
import hashlib
import io
import json
import shutil
import tarfile
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from agora.cli import main
from agora.markdown import read_markdown, render_markdown
from agora.model import (
    AddRegistryTrustKeyInput,
    InitInput,
    InstallCatalogPackInput,
    InstallRegistryInput,
    RegistryReleaseRecord,
    RevokeRegistryTrustKeyInput,
    UpdateRegistryInput,
)
from agora.registries import read_registry_source, read_registry_update
from agora.registry_distribution import (
    load_registry_index,
    release_signature_payload,
    select_registry_release,
)
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


def _release_index(
    destination: Path,
    registry: Path,
    *,
    version: str = "1.0.0",
    signed: bool = False,
    checksum: str | None = None,
) -> tuple[Path, Path | None]:
    manifest = registry / "REGISTRY.md"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            'name: "Team Catalog"', f'name: "Team Catalog"\nversion: "{version}"'
        ),
        encoding="utf-8",
    )
    archive_name = f"team-catalog-{version}.tar.gz"
    archive_path = destination / archive_name
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(registry, arcname="team-catalog")
    digest = checksum or hashlib.sha256(archive_path.read_bytes()).hexdigest()
    release = RegistryReleaseRecord(
        registry="team-catalog",
        version=version,
        archive=archive_name,
        sha256=digest,
        key_id="team-release" if signed else None,
    )
    public_key_path: Path | None = None
    signature: str | None = None
    if signed:
        private_key = Ed25519PrivateKey.generate()
        signature = base64.b64encode(private_key.sign(release_signature_payload(release))).decode()
        public_key_path = destination / "team-release.pem"
        public_key_path.write_bytes(
            private_key.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        )
    releases = [
        {
            "version": version,
            "archive": archive_name,
            "sha256": digest,
            **({"signature": signature, "key-id": "team-release"} if signed else {}),
        }
    ]
    index = destination / "INDEX.md"
    index.write_text(
        '---\nschema: "agora/registry-index/v1"\nid: "team-catalog"\n'
        f'name: "Team Catalog"\nreleases: {json.dumps(releases, separators=(",", ":"))}\n'
        "---\n\n# Team Catalog releases\n",
        encoding="utf-8",
    )
    return index, public_key_path


def _threshold_release_index(
    destination: Path,
    registry: Path,
    signers: list[tuple[str, Ed25519PrivateKey]],
    *,
    version: str,
) -> Path:
    manifest = registry / "REGISTRY.md"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            'name: "Team Catalog"', f'name: "Team Catalog"\nversion: "{version}"'
        ),
        encoding="utf-8",
    )
    archive_name = f"team-catalog-{version}.tar.gz"
    archive_path = destination / archive_name
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(registry, arcname="team-catalog")
    release = RegistryReleaseRecord(
        registry="team-catalog",
        version=version,
        archive=archive_name,
        sha256=hashlib.sha256(archive_path.read_bytes()).hexdigest(),
    )
    signatures = [
        {
            "key-id": signer_id,
            "signature": base64.b64encode(
                private_key.sign(release_signature_payload(release))
            ).decode(),
        }
        for signer_id, private_key in signers
    ]
    values = [
        {
            "version": release.version,
            "archive": release.archive,
            "sha256": release.sha256,
            "signatures": signatures,
        }
    ]
    index = destination / "INDEX.md"
    index.write_text(
        '---\nschema: "agora/registry-index/v1"\nid: "team-catalog"\n'
        f'name: "Team Catalog"\nreleases: {json.dumps(values, separators=(",", ":"))}\n'
        "---\n\n# Team Catalog releases\n",
        encoding="utf-8",
    )
    return index


def _trust_signer(
    workspace: AgoraWorkspace,
    destination: Path,
    signer_id: str,
    private_key: Ed25519PrivateKey,
) -> None:
    public_key = destination / f"{signer_id}.pem"
    public_key.write_bytes(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    workspace.add_registry_trust_key(
        AddRegistryTrustKeyInput(
            id=signer_id,
            registry_id="team-catalog",
            public_key=str(public_key),
            scope="project",
        )
    )


def test_discovers_bundled_packs_without_an_initialized_project(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    workspace = AgoraWorkspace(cwd=tmp_path)

    registries = workspace.list_registries()
    methods = workspace.search_catalog(kind="method")
    tools = workspace.search_catalog(kind="tool", query="repository")

    assert [(item.id, item.scope) for item in registries] == [("agora-bundled", "bundled")]
    assert [item.id for item in methods] == ["kanban", "scrum", "spec-driven"]
    assert [(item.id, item.registry) for item in tools] == [
        ("repository", "agora-bundled"),
        ("repository-governance", "agora-bundled"),
    ]


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


def test_installs_a_signed_registry_release_with_durable_provenance(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    source = _registry(
        tmp_path / "source",
        registry_id="team-catalog",
        registry_name="Team Catalog",
    )
    index, public_key = _release_index(tmp_path, source, signed=True)
    assert public_key is not None
    workspace = AgoraWorkspace(cwd=root)
    workspace.initialize(InitInput(integration="generic"))

    installed = workspace.install_registry(
        InstallRegistryInput(
            source=str(index),
            scope="project",
            public_key=str(public_key),
            require_signature=True,
        )
    )

    assert installed.version == "1.0.0"
    assert installed.source == index.as_uri()
    assert installed.checksum is not None
    assert installed.signature_verified is True
    assert (Path(installed.path) / "SOURCE.md").is_file()
    report = workspace.validate()
    assert report.ok is True
    assert report.checked["registries"] == 1


def test_enforces_and_preserves_a_registry_signature_threshold(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    signer_a = Ed25519PrivateKey.generate()
    signer_b = Ed25519PrivateKey.generate()
    source_v1 = _registry(
        tmp_path / "source-v1",
        registry_id="team-catalog",
        registry_name="Team Catalog",
    )
    index = _threshold_release_index(
        tmp_path,
        source_v1,
        [("release-a", signer_a), ("release-b", signer_b)],
        version="1.0.0",
    )
    workspace = AgoraWorkspace(cwd=root)
    workspace.initialize(InitInput(integration="generic"))
    _trust_signer(workspace, tmp_path, "release-a", signer_a)

    with pytest.raises(ValueError, match="requires 2 valid signatures, verified 1"):
        workspace.install_registry(
            InstallRegistryInput(
                source=str(index),
                scope="project",
                signature_threshold=2,
            )
        )
    _trust_signer(workspace, tmp_path, "release-alias", signer_a)
    alias_source = _registry(
        tmp_path / "source-alias",
        registry_id="team-catalog",
        registry_name="Team Catalog",
    )
    _threshold_release_index(
        tmp_path,
        alias_source,
        [("release-a", signer_a), ("release-alias", signer_a)],
        version="1.0.0",
    )
    with pytest.raises(ValueError, match="requires 2 valid signatures, verified 1"):
        workspace.install_registry(
            InstallRegistryInput(
                source=str(index),
                scope="project",
                signature_threshold=2,
            )
        )

    _trust_signer(workspace, tmp_path, "release-b", signer_b)
    install_source = _registry(
        tmp_path / "source-install",
        registry_id="team-catalog",
        registry_name="Team Catalog",
    )
    _threshold_release_index(
        tmp_path,
        install_source,
        [("release-a", signer_a), ("release-b", signer_b)],
        version="1.0.0",
    )
    output = io.StringIO()
    assert (
        main(
            [
                "registry",
                "install",
                "--source",
                str(index),
                "--scope",
                "project",
                "--signature-threshold",
                "2",
            ],
            cwd=root,
            stdout=output,
        )
        == 0
    )
    installed = next(item for item in workspace.list_registries() if item.id == "team-catalog")
    source_record = read_registry_source(Path(installed.path) / "SOURCE.md")
    assert source_record.signature_threshold == 2
    assert source_record.verified_key_ids == ["release-a", "release-b"]
    with pytest.raises(ValueError, match="cannot lower the persisted signature threshold"):
        workspace.update_registry(
            UpdateRegistryInput(
                id="team-catalog",
                scope="project",
                signature_threshold=1,
            )
        )

    source_v2 = _registry(
        tmp_path / "source-v2",
        registry_id="team-catalog",
        registry_name="Team Catalog",
    )
    _threshold_release_index(
        tmp_path,
        source_v2,
        [("release-a", signer_a)],
        version="2.0.0",
    )
    with pytest.raises(ValueError, match="requires 2 valid signatures, verified 1"):
        workspace.update_registry(
            UpdateRegistryInput(id="team-catalog", scope="project", apply=True)
        )

    _threshold_release_index(
        tmp_path,
        source_v2,
        [("release-a", signer_a), ("release-b", signer_b)],
        version="2.0.0",
    )
    updated = workspace.update_registry(
        UpdateRegistryInput(id="team-catalog", scope="project", apply=True)
    )
    assert updated.record_path is not None
    update_record = read_registry_update(Path(updated.record_path))
    assert update_record.signature_threshold == 2
    assert update_record.verified_key_ids == ["release-a", "release-b"]
    assert read_registry_source(Path(installed.path) / "SOURCE.md").signature_threshold == 2
    assert workspace.validate().ok is True

    update_path = Path(updated.record_path)
    document = read_markdown(update_path)
    document.attributes["signature-threshold"] = 1
    update_path.write_text(render_markdown(document), encoding="utf-8")
    invalid = workspace.validate()
    assert invalid.ok is False
    assert any(issue.code == "registry.invalid" for issue in invalid.issues)


def test_rejects_a_remote_registry_checksum_mismatch_before_copy(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    source = _registry(
        tmp_path / "source",
        registry_id="team-catalog",
        registry_name="Team Catalog",
    )
    index, _ = _release_index(tmp_path, source, checksum="0" * 64)

    with pytest.raises(ValueError, match="checksum mismatch"):
        AgoraWorkspace(cwd=tmp_path).install_registry(
            InstallRegistryInput(source=str(index), scope="user")
        )

    assert not (tmp_path / "home" / "registries" / "team-catalog").exists()


def test_rejects_unsafe_remote_registry_archive_paths(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    archive_path = tmp_path / "team-catalog-1.0.0.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        member = tarfile.TarInfo("../outside.md")
        payload = b"outside"
        member.size = len(payload)
        archive.addfile(member, io.BytesIO(payload))
    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    releases = [
        {
            "version": "1.0.0",
            "archive": archive_path.name,
            "sha256": digest,
        }
    ]
    index = tmp_path / "INDEX.md"
    index.write_text(
        '---\nschema: "agora/registry-index/v1"\nid: "team-catalog"\n'
        f'name: "Team Catalog"\nreleases: {json.dumps(releases, separators=(",", ":"))}\n'
        "---\n\n# Unsafe release\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="escapes its destination"):
        AgoraWorkspace(cwd=tmp_path).install_registry(
            InstallRegistryInput(source=str(index), scope="user")
        )

    assert not (tmp_path / "outside.md").exists()


def test_remote_http_requires_explicit_opt_in(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))

    with pytest.raises(PermissionError, match="allow-insecure-http"):
        AgoraWorkspace(cwd=tmp_path).install_registry(
            InstallRegistryInput(source="http://127.0.0.1:9/INDEX.md", scope="user")
        )


def test_downloads_a_registry_over_explicitly_allowed_http(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    source = _registry(
        tmp_path / "source",
        registry_id="team-catalog",
        registry_name="Team Catalog",
    )
    index, _ = _release_index(tmp_path, source)
    handler = partial(SimpleHTTPRequestHandler, directory=str(tmp_path))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        installed = AgoraWorkspace(cwd=tmp_path).install_registry(
            InstallRegistryInput(
                source=f"http://127.0.0.1:{server.server_port}/{index.name}",
                scope="user",
                allow_insecure_http=True,
            )
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join()

    assert installed.version == "1.0.0"
    assert installed.source is not None and installed.source.startswith("http://127.0.0.1:")
    assert installed.signature_verified is False


def test_remote_index_cannot_reference_a_local_archive(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    source = _registry(
        tmp_path / "source",
        registry_id="team-catalog",
        registry_name="Team Catalog",
    )
    index, _ = _release_index(tmp_path, source)
    archive = tmp_path / "team-catalog-1.0.0.tar.gz"
    index.write_text(
        index.read_text(encoding="utf-8").replace(archive.name, archive.as_uri()),
        encoding="utf-8",
    )
    handler = partial(SimpleHTTPRequestHandler, directory=str(tmp_path))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pytest.raises(ValueError, match="cannot reference local archive"):
            AgoraWorkspace(cwd=tmp_path).install_registry(
                InstallRegistryInput(
                    source=f"http://127.0.0.1:{server.server_port}/{index.name}",
                    scope="user",
                    allow_insecure_http=True,
                )
            )
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_rejects_a_registry_signature_from_an_untrusted_key(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    source = _registry(
        tmp_path / "source",
        registry_id="team-catalog",
        registry_name="Team Catalog",
    )
    index, _ = _release_index(tmp_path, source, signed=True)
    untrusted = Ed25519PrivateKey.generate().public_key()
    untrusted_path = tmp_path / "untrusted.pem"
    untrusted_path.write_bytes(
        untrusted.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )

    with pytest.raises(ValueError, match="signature is invalid"):
        AgoraWorkspace(cwd=tmp_path).install_registry(
            InstallRegistryInput(
                source=str(index),
                scope="user",
                public_key=str(untrusted_path),
                require_signature=True,
            )
        )


def test_uses_project_trust_before_a_conflicting_user_key(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    source = _registry(
        tmp_path / "source",
        registry_id="team-catalog",
        registry_name="Team Catalog",
    )
    index, trusted_key = _release_index(tmp_path, source, signed=True)
    assert trusted_key is not None
    untrusted = Ed25519PrivateKey.generate().public_key()
    untrusted_path = tmp_path / "untrusted.pem"
    untrusted_path.write_bytes(
        untrusted.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    workspace = AgoraWorkspace(cwd=root)
    workspace.initialize(InitInput(integration="generic"))
    workspace.add_registry_trust_key(
        AddRegistryTrustKeyInput(
            id="team-release",
            registry_id="team-catalog",
            public_key=str(untrusted_path),
            scope="user",
        )
    )
    workspace.add_registry_trust_key(
        AddRegistryTrustKeyInput(
            id="team-release",
            registry_id="team-catalog",
            public_key=str(trusted_key),
            scope="project",
        )
    )

    installed = workspace.install_registry(
        InstallRegistryInput(
            source=str(index),
            scope="project",
            require_signature=True,
        )
    )

    assert installed.signature_verified is True
    assert workspace.list_registry_trust_keys()[0].scope == "project"


def test_revoked_trust_key_blocks_registry_install_even_with_explicit_pem(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    source = _registry(
        tmp_path / "source",
        registry_id="team-catalog",
        registry_name="Team Catalog",
    )
    index, trusted_key = _release_index(tmp_path, source, signed=True)
    assert trusted_key is not None
    workspace = AgoraWorkspace(cwd=root)
    workspace.initialize(InitInput(integration="generic"))
    workspace.add_registry_trust_key(
        AddRegistryTrustKeyInput(
            id="team-release",
            registry_id="team-catalog",
            public_key=str(trusted_key),
            scope="project",
        )
    )
    workspace.revoke_registry_trust_key(
        RevokeRegistryTrustKeyInput(
            id="team-release",
            scope="project",
            reason="Release key was compromised",
        )
    )
    (tmp_path / "team-catalog-1.0.0.tar.gz").unlink()

    with pytest.raises(PermissionError, match="key is revoked"):
        workspace.install_registry(
            InstallRegistryInput(
                source=str(index),
                scope="project",
                public_key=str(trusted_key),
                require_signature=True,
            )
        )


def test_rejects_an_invalid_signature_before_following_the_archive_url(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    source = _registry(
        tmp_path / "source",
        registry_id="team-catalog",
        registry_name="Team Catalog",
    )
    index, trusted_key = _release_index(tmp_path, source, signed=True)
    assert trusted_key is not None
    index.write_text(
        index.read_text(encoding="utf-8").replace(
            "team-catalog-1.0.0.tar.gz",
            "http://127.0.0.1:9/unreachable.tar.gz",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="signature is invalid"):
        AgoraWorkspace(cwd=tmp_path).install_registry(
            InstallRegistryInput(
                source=str(index),
                scope="user",
                public_key=str(trusted_key),
                require_signature=True,
                allow_insecure_http=True,
            )
        )


def test_selects_the_latest_registry_release_by_default() -> None:
    releases = [
        {"version": version, "archive": f"release-{version}.zip", "sha256": "0" * 64}
        for version in ("1.9.0", "2.0.0", "1.10.0")
    ]
    contents = (
        '---\nschema: "agora/registry-index/v1"\nid: "team-catalog"\n'
        f'name: "Team Catalog"\nreleases: {json.dumps(releases, separators=(",", ":"))}\n'
        "---\n\n# Releases\n"
    ).encode()

    index = load_registry_index(contents, "https://example.com/INDEX.md")

    assert select_registry_release(index, None).version == "2.0.0"
    assert select_registry_release(index, "1.10.0").version == "1.10.0"


def test_cli_installs_a_versioned_signed_registry_release(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    source = _registry(
        tmp_path / "source",
        registry_id="team-catalog",
        registry_name="Team Catalog",
    )
    index, public_key = _release_index(tmp_path, source, signed=True)
    assert public_key is not None
    AgoraWorkspace(cwd=root).initialize(InitInput(integration="generic"))
    output = io.StringIO()
    errors = io.StringIO()

    result = main(
        [
            "registry",
            "install",
            "--source",
            str(index),
            "--scope",
            "project",
            "--version",
            "1.0.0",
            "--public-key",
            str(public_key),
            "--require-signature",
        ],
        cwd=root,
        stdout=output,
        stderr=errors,
    )

    assert result == 0
    assert errors.getvalue() == ""
    assert '"version": "1.0.0"' in output.getvalue()
    assert '"signature_verified": true' in output.getvalue()
