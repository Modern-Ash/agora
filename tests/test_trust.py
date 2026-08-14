import io
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from agora.cli import main
from agora.model import (
    AddRegistryTrustKeyInput,
    InitInput,
    RevokeRegistryTrustKeyInput,
)
from agora.workspace import AgoraWorkspace


def _public_key(path: Path) -> Path:
    key = Ed25519PrivateKey.generate().public_key()
    path.write_bytes(
        key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    return path


def test_rotates_and_validates_project_registry_trust_keys(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    workspace = AgoraWorkspace(cwd=root)
    workspace.initialize(InitInput(integration="generic"))
    workspace.add_registry_trust_key(
        AddRegistryTrustKeyInput(
            id="team-2025",
            registry_id="team-catalog",
            public_key=str(_public_key(tmp_path / "old.pem")),
            scope="project",
        )
    )
    replacement = workspace.add_registry_trust_key(
        AddRegistryTrustKeyInput(
            id="team-2026",
            registry_id="team-catalog",
            public_key=str(_public_key(tmp_path / "new.pem")),
            scope="project",
        )
    )

    revoked = workspace.revoke_registry_trust_key(
        RevokeRegistryTrustKeyInput(
            id="team-2025",
            scope="project",
            reason="Scheduled annual rotation",
            replaced_by="team-2026",
        )
    )

    assert revoked.status == "revoked"
    assert revoked.replaced_by == replacement.id
    assert revoked.revoked_at is not None
    assert workspace.validate().ok is True

    Path(replacement.path).unlink()
    invalid = workspace.validate()
    assert invalid.ok is False
    assert any(issue.code == "trust-key.replacement-missing" for issue in invalid.issues)


def test_rejects_duplicate_and_invalid_replacement_trust_keys(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    workspace = AgoraWorkspace(cwd=root)
    workspace.initialize(InitInput(integration="generic"))
    public_key = _public_key(tmp_path / "key.pem")
    data = AddRegistryTrustKeyInput(
        id="team-release",
        registry_id="team-catalog",
        public_key=str(public_key),
        scope="project",
    )
    workspace.add_registry_trust_key(data)

    with pytest.raises(FileExistsError, match="Rotate with a new key id"):
        workspace.add_registry_trust_key(data)
    with pytest.raises(ValueError, match="must match"):
        workspace.revoke_registry_trust_key(
            RevokeRegistryTrustKeyInput(
                id="team-release",
                scope="project",
                reason="Invalid replacement path",
                replaced_by="../outside",
            )
        )


def test_cli_adds_lists_and_revokes_a_user_trust_key(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    public_key = _public_key(tmp_path / "key.pem")
    output = io.StringIO()
    errors = io.StringIO()

    assert (
        main(
            [
                "trust",
                "add",
                "--id",
                "team-release",
                "--registry",
                "team-catalog",
                "--public-key",
                str(public_key),
                "--scope",
                "user",
            ],
            cwd=tmp_path,
            stdout=output,
            stderr=errors,
        )
        == 0
    )
    assert (
        main(
            ["trust", "list", "--registry", "team-catalog"],
            cwd=tmp_path,
            stdout=output,
            stderr=errors,
        )
        == 0
    )
    assert (
        main(
            [
                "trust",
                "revoke",
                "--id",
                "team-release",
                "--scope",
                "user",
                "--reason",
                "Retired release key",
            ],
            cwd=tmp_path,
            stdout=output,
            stderr=errors,
        )
        == 0
    )

    assert errors.getvalue() == ""
    assert '"fingerprint":' in output.getvalue()
    assert '"status": "revoked"' in output.getvalue()
