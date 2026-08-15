import base64
import hashlib
import io
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from agora.cli import main
from agora.model import (
    AddOrganizationTrustRootInput,
    InitInput,
    SyncOrganizationTrustInput,
)
from agora.organization_trust import (
    organization_trust_signature_payload,
    render_organization_trust_bundle,
)
from agora.workspace import AgoraWorkspace


def _pem(path: Path, private_key: Ed25519PrivateKey) -> Path:
    path.write_bytes(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    return path


def _key_entry(
    private_key: Ed25519PrivateKey,
    *,
    status: str = "active",
    revoked_at: str | None = None,
    revoked_reason: str | None = None,
) -> dict[str, object]:
    raw = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return {
        "id": "team-release-2026",
        "registry": "team-catalog",
        "algorithm": "ed25519",
        "public-key": base64.b64encode(raw).decode(),
        "fingerprint": hashlib.sha256(raw).hexdigest(),
        "status": status,
        "created-at": "2026-08-15T10:00:00Z",
        "revoked-at": revoked_at,
        "revoked-reason": revoked_reason,
        "replaced-by": None,
    }


def _bundle(
    path: Path,
    root_key: Ed25519PrivateKey,
    *,
    sequence: int,
    previous_sha256: str | None,
    keys: list[dict[str, object]],
) -> Path:
    generated_at = f"2026-08-15T10:0{sequence}:00Z"
    payload = organization_trust_signature_payload(
        organization="example-org",
        sequence=sequence,
        generated_at=generated_at,
        previous_sha256=previous_sha256,
        keys=keys,
    )
    signature = base64.b64encode(root_key.sign(payload)).decode()
    path.write_text(
        render_organization_trust_bundle(
            organization="example-org",
            sequence=sequence,
            generated_at=generated_at,
            previous_sha256=previous_sha256,
            keys=keys,
            signature=signature,
        ),
        encoding="utf-8",
    )
    return path


def _workspace(tmp_path: Path, monkeypatch) -> tuple[AgoraWorkspace, Ed25519PrivateKey]:
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    workspace = AgoraWorkspace(cwd=project)
    workspace.initialize(InitInput(integration="generic"))
    root_key = Ed25519PrivateKey.generate()
    workspace.add_organization_trust_root(
        AddOrganizationTrustRootInput(
            id="example-org",
            public_key=str(_pem(tmp_path / "organization.pem", root_key)),
            scope="project",
        )
    )
    return workspace, root_key


def test_previews_applies_and_validates_organization_revocation_feed(
    tmp_path: Path, monkeypatch
) -> None:
    workspace, root_key = _workspace(tmp_path, monkeypatch)
    release_key = Ed25519PrivateKey.generate()
    first = _bundle(
        tmp_path / "bundle-1.md",
        root_key,
        sequence=1,
        previous_sha256=None,
        keys=[_key_entry(release_key)],
    )

    preview = workspace.sync_organization_trust(
        SyncOrganizationTrustInput(id="example-org", scope="project", source=str(first))
    )

    assert preview.applied is False
    assert preview.signature_verified is True
    assert preview.steps[0].action == "add"
    assert workspace.list_registry_trust_keys() == []

    applied = workspace.sync_organization_trust(
        SyncOrganizationTrustInput(id="example-org", scope="project", source=str(first), apply=True)
    )
    assert applied.applied is True
    assert workspace.list_registry_trust_keys()[0].status == "active"
    assert applied.history_path is not None
    assert Path(applied.history_path).is_file()

    second = _bundle(
        tmp_path / "bundle-2.md",
        root_key,
        sequence=2,
        previous_sha256=applied.sha256,
        keys=[
            _key_entry(
                release_key,
                status="revoked",
                revoked_at="2026-08-15T10:02:00Z",
                revoked_reason="Compromised release key",
            )
        ],
    )
    revoked = workspace.sync_organization_trust(
        SyncOrganizationTrustInput(
            id="example-org", scope="project", source=str(second), apply=True
        )
    )

    assert revoked.steps[0].action == "revoke"
    assert workspace.list_registry_trust_keys()[0].status == "revoked"
    root = workspace.get_organization_trust_root("example-org", "project")
    assert root.last_sequence == 2
    assert root.last_sha256 == revoked.sha256
    assert workspace.validate().ok is True

    key_path = Path(workspace.list_registry_trust_keys()[0].path)
    key_path.write_text(
        key_path.read_text(encoding="utf-8").replace(
            "Compromised release key", "Locally rewritten reason"
        ),
        encoding="utf-8",
    )
    invalid = workspace.validate()
    assert invalid.ok is False
    assert any(issue.code == "organization-trust-key.history-mismatch" for issue in invalid.issues)


def test_rejects_invalid_signature_and_discontinuous_sequence(tmp_path: Path, monkeypatch) -> None:
    workspace, root_key = _workspace(tmp_path, monkeypatch)
    release_key = Ed25519PrivateKey.generate()
    invalid = _bundle(
        tmp_path / "invalid.md",
        Ed25519PrivateKey.generate(),
        sequence=1,
        previous_sha256=None,
        keys=[_key_entry(release_key)],
    )
    with pytest.raises(ValueError, match="signature is invalid"):
        workspace.sync_organization_trust(
            SyncOrganizationTrustInput(
                id="example-org", scope="project", source=str(invalid), apply=True
            )
        )

    skipped = _bundle(
        tmp_path / "skipped.md",
        root_key,
        sequence=2,
        previous_sha256="0" * 64,
        keys=[_key_entry(release_key)],
    )
    with pytest.raises(ValueError, match="sequence must be 1"):
        workspace.sync_organization_trust(
            SyncOrganizationTrustInput(
                id="example-org", scope="project", source=str(skipped), apply=True
            )
        )
    assert workspace.list_registry_trust_keys() == []


def test_rejects_a_signed_attempt_to_reactivate_a_revoked_key(tmp_path: Path, monkeypatch) -> None:
    workspace, root_key = _workspace(tmp_path, monkeypatch)
    release_key = Ed25519PrivateKey.generate()
    first = _bundle(
        tmp_path / "bundle-1.md",
        root_key,
        sequence=1,
        previous_sha256=None,
        keys=[
            _key_entry(
                release_key,
                status="revoked",
                revoked_at="2026-08-15T10:01:00Z",
                revoked_reason="Compromised before publication",
            )
        ],
    )
    applied = workspace.sync_organization_trust(
        SyncOrganizationTrustInput(id="example-org", scope="project", source=str(first), apply=True)
    )
    second = _bundle(
        tmp_path / "bundle-2.md",
        root_key,
        sequence=2,
        previous_sha256=applied.sha256,
        keys=[_key_entry(release_key)],
    )

    with pytest.raises(PermissionError, match="reactivate revoked key"):
        workspace.sync_organization_trust(
            SyncOrganizationTrustInput(
                id="example-org", scope="project", source=str(second), apply=True
            )
        )
    assert workspace.get_organization_trust_root("example-org", "project").last_sequence == 1


def test_cli_shows_and_previews_an_organization_trust_feed(tmp_path: Path, monkeypatch) -> None:
    workspace, root_key = _workspace(tmp_path, monkeypatch)
    bundle = _bundle(
        tmp_path / "bundle.md",
        root_key,
        sequence=1,
        previous_sha256=None,
        keys=[_key_entry(Ed25519PrivateKey.generate())],
    )
    output = io.StringIO()
    errors = io.StringIO()

    assert (
        main(
            [
                "trust",
                "organization",
                "show",
                "--id",
                "example-org",
                "--scope",
                "project",
            ],
            cwd=workspace.cwd,
            stdout=output,
            stderr=errors,
        )
        == 0
    )
    assert (
        main(
            [
                "trust",
                "organization",
                "sync",
                "--id",
                "example-org",
                "--scope",
                "project",
                "--source",
                str(bundle),
            ],
            cwd=workspace.cwd,
            stdout=output,
            stderr=errors,
        )
        == 0
    )
    assert errors.getvalue() == ""
    assert '"last_sequence": 0' in output.getvalue()
    assert '"signature_verified": true' in output.getvalue()
