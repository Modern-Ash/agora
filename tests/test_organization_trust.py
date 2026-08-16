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
    RotateOrganizationTrustRootInput,
    SyncOrganizationTrustInput,
)
from agora.organization_trust import (
    organization_trust_root_rotation_payload,
    organization_trust_signature_payload,
    render_organization_trust_bundle,
    render_organization_trust_root_rotation,
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


def _rotation(
    path: Path,
    old_key: Ed25519PrivateKey,
    new_key: Ed25519PrivateKey,
    *,
    bundle_sequence: int,
    bundle_sha256: str | None,
    old_signer: Ed25519PrivateKey | None = None,
    rotation: int = 1,
    previous_rotation_sha256: str | None = None,
) -> Path:
    old_raw = old_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    new_raw = new_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    values = {
        "organization": "example-org",
        "rotation": rotation,
        "rotated_at": "2026-08-15T11:00:00Z",
        "reason": "Scheduled root rotation",
        "from_public_key": base64.b64encode(old_raw).decode(),
        "from_fingerprint": hashlib.sha256(old_raw).hexdigest(),
        "to_public_key": base64.b64encode(new_raw).decode(),
        "to_fingerprint": hashlib.sha256(new_raw).hexdigest(),
        "bundle_sequence": bundle_sequence,
        "bundle_sha256": bundle_sha256,
        "previous_rotation_sha256": previous_rotation_sha256,
    }
    payload = organization_trust_root_rotation_payload(**values)
    path.write_text(
        render_organization_trust_root_rotation(
            **values,
            old_signature=base64.b64encode((old_signer or old_key).sign(payload)).decode(),
            new_signature=base64.b64encode(new_key.sign(payload)).decode(),
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


def test_rotates_organization_root_and_preserves_historical_verification(
    tmp_path: Path, monkeypatch
) -> None:
    workspace, old_root = _workspace(tmp_path, monkeypatch)
    release_key = Ed25519PrivateKey.generate()
    first = _bundle(
        tmp_path / "bundle-1.md",
        old_root,
        sequence=1,
        previous_sha256=None,
        keys=[_key_entry(release_key)],
    )
    applied = workspace.sync_organization_trust(
        SyncOrganizationTrustInput(id="example-org", scope="project", source=str(first), apply=True)
    )
    new_root = Ed25519PrivateKey.generate()
    rotation = _rotation(
        tmp_path / "rotation.md",
        old_root,
        new_root,
        bundle_sequence=1,
        bundle_sha256=applied.sha256,
    )

    preview = workspace.rotate_organization_trust_root(
        RotateOrganizationTrustRootInput(id="example-org", scope="project", source=str(rotation))
    )
    assert preview.applied is False
    assert preview.signature_verified is True
    assert workspace.get_organization_trust_root("example-org", "project").fingerprint == (
        preview.from_fingerprint
    )

    output = io.StringIO()
    assert (
        main(
            [
                "trust",
                "organization",
                "rotate",
                "--id",
                "example-org",
                "--scope",
                "project",
                "--source",
                str(rotation),
                "--apply",
            ],
            cwd=workspace.cwd,
            stdout=output,
        )
        == 0
    )
    assert '"signature_verified": true' in output.getvalue()
    active_root = workspace.get_organization_trust_root("example-org", "project")
    assert active_root.fingerprint == preview.to_fingerprint
    assert active_root.initial_fingerprint == preview.from_fingerprint

    second = _bundle(
        tmp_path / "bundle-2.md",
        new_root,
        sequence=2,
        previous_sha256=applied.sha256,
        keys=[_key_entry(release_key)],
    )
    second_applied = workspace.sync_organization_trust(
        SyncOrganizationTrustInput(
            id="example-org", scope="project", source=str(second), apply=True
        )
    )
    final_root = Ed25519PrivateKey.generate()
    second_rotation = _rotation(
        tmp_path / "rotation-2.md",
        new_root,
        final_root,
        bundle_sequence=2,
        bundle_sha256=second_applied.sha256,
        rotation=2,
        previous_rotation_sha256=preview.sha256,
    )
    workspace.rotate_organization_trust_root(
        RotateOrganizationTrustRootInput(
            id="example-org", scope="project", source=str(second_rotation), apply=True
        )
    )
    report = workspace.validate()
    assert report.ok is True
    assert report.checked["organization-trust-root-rotations"] == 2
    assert report.checked["organization-trust-bundles"] == 2
    assert (
        workspace.get_organization_trust_root("example-org", "project").fingerprint
        == hashlib.sha256(
            final_root.public_key().public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
        ).hexdigest()
    )

    persisted_rotation = (
        workspace.project_root()
        / ".agora"
        / "trust"
        / "organizations"
        / "example-org"
        / "rotations"
        / "00000000000000000001.md"
    )
    assert persisted_rotation.read_text(encoding="utf-8") == rotation.read_text(encoding="utf-8")
    persisted_rotation.write_text(
        persisted_rotation.read_text(encoding="utf-8").replace(
            "Scheduled root rotation", "Rewritten root rotation"
        ),
        encoding="utf-8",
    )
    invalid = workspace.validate()
    assert invalid.ok is False
    assert any(issue.code == "organization-trust-root-rotation.invalid" for issue in invalid.issues)


def test_rejects_invalid_or_stale_organization_root_rotation(tmp_path: Path, monkeypatch) -> None:
    workspace, old_root = _workspace(tmp_path, monkeypatch)
    new_root = Ed25519PrivateKey.generate()
    invalid = _rotation(
        tmp_path / "invalid-rotation.md",
        old_root,
        new_root,
        bundle_sequence=0,
        bundle_sha256=None,
        old_signer=Ed25519PrivateKey.generate(),
    )
    with pytest.raises(ValueError, match="old signature is invalid"):
        workspace.rotate_organization_trust_root(
            RotateOrganizationTrustRootInput(
                id="example-org", scope="project", source=str(invalid), apply=True
            )
        )

    applied = workspace.sync_organization_trust(
        SyncOrganizationTrustInput(
            id="example-org",
            scope="project",
            source=str(
                _bundle(
                    tmp_path / "bundle.md",
                    old_root,
                    sequence=1,
                    previous_sha256=None,
                    keys=[_key_entry(Ed25519PrivateKey.generate())],
                )
            ),
            apply=True,
        )
    )
    assert applied.sequence == 1
    stale = _rotation(
        tmp_path / "stale-rotation.md",
        old_root,
        new_root,
        bundle_sequence=0,
        bundle_sha256=None,
    )
    with pytest.raises(ValueError, match="current feed state"):
        workspace.rotate_organization_trust_root(
            RotateOrganizationTrustRootInput(
                id="example-org", scope="project", source=str(stale), apply=True
            )
        )


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
