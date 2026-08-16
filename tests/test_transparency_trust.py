import io
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from agora.cli import main
from agora.model import (
    AddTransparencyTrustKeyInput,
    InitInput,
    RevokeTransparencyTrustKeyInput,
)
from agora.workspace import AgoraWorkspace


def _pem(path: Path) -> Path:
    key = Ed25519PrivateKey.generate()
    path.write_bytes(
        key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    return path


def test_manages_separate_transparency_log_trust_keys(tmp_path: Path, monkeypatch) -> None:
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    workspace = AgoraWorkspace(cwd=project)
    workspace.initialize(InitInput(integration="generic"))
    output = io.StringIO()

    assert (
        main(
            [
                "trust",
                "transparency",
                "add",
                "--id",
                "rekor-2026",
                "--log",
                "rekor-public",
                "--public-key",
                str(_pem(tmp_path / "rekor-2026.pem")),
                "--scope",
                "project",
            ],
            cwd=project,
            stdout=output,
        )
        == 0
    )
    replacement = workspace.add_transparency_trust_key(
        AddTransparencyTrustKeyInput(
            id="rekor-2027",
            log="rekor-public",
            public_key=str(_pem(tmp_path / "rekor-2027.pem")),
            scope="project",
        )
    )
    revoked = workspace.revoke_transparency_trust_key(
        RevokeTransparencyTrustKeyInput(
            id="rekor-2026",
            scope="project",
            reason="Scheduled checkpoint key rotation",
            replaced_by=replacement.id,
        )
    )

    assert revoked.status == "revoked"
    assert revoked.replaced_by == "rekor-2027"
    assert workspace.list_registry_trust_keys() == []
    assert [item.id for item in workspace.list_transparency_trust_keys("rekor-public")] == [
        "rekor-2026",
        "rekor-2027",
    ]
    report = workspace.validate()
    assert report.ok is True
    assert report.checked["transparency-trust-keys"] == 2


def test_rejects_cross_log_transparency_key_replacement(tmp_path: Path, monkeypatch) -> None:
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    workspace = AgoraWorkspace(cwd=project)
    workspace.initialize(InitInput(integration="generic"))
    for id_, log in (("rekor-key", "rekor-public"), ("other-key", "other-log")):
        workspace.add_transparency_trust_key(
            AddTransparencyTrustKeyInput(
                id=id_,
                log=log,
                public_key=str(_pem(tmp_path / f"{id_}.pem")),
                scope="project",
            )
        )

    with pytest.raises(ValueError, match="active for the same log"):
        workspace.revoke_transparency_trust_key(
            RevokeTransparencyTrustKeyInput(
                id="rekor-key",
                scope="project",
                reason="Invalid replacement test",
                replaced_by="other-key",
            )
        )
