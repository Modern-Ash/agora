import base64
import hashlib
import io
import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from agora.cli import main
from agora.model import (
    AddTransparencyTrustKeyInput,
    InitInput,
    RegistryReleaseRecord,
    RevokeTransparencyTrustKeyInput,
    TransparencyInclusionProofRecord,
    VerifyTransparencyProofInput,
)
from agora.registry_distribution import release_signature_payload
from agora.transparency import render_transparency_proof, transparency_checkpoint_payload
from agora.workspace import AgoraWorkspace


def _write_public_key(path: Path, private_key: Ed25519PrivateKey) -> Path:
    path.write_bytes(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    return path


def _proof(private_key: Ed25519PrivateKey, path: Path) -> TransparencyInclusionProofRecord:
    release = RegistryReleaseRecord(
        registry="community",
        version="1.2.0",
        archive="community-1.2.0.tar.gz",
        sha256="1" * 64,
    )
    leaf = hashlib.sha256(b"\x00" + release_signature_payload(release)).digest()
    sibling = hashlib.sha256(b"independent second leaf").digest()
    root = hashlib.sha256(b"\x01" + leaf + sibling).hexdigest()
    unsigned = TransparencyInclusionProofRecord(
        log="public-log",
        key_id="public-log-2026",
        registry=release.registry,
        version=release.version,
        archive=release.archive,
        sha256=release.sha256,
        tree_size=2,
        leaf_index=0,
        root_sha256=root,
        inclusion_path=[sibling.hex()],
        checkpoint_signature="",
        integrated_at="2026-08-16T12:00:00Z",
        path=str(path),
    )
    return replace(
        unsigned,
        checkpoint_signature=base64.b64encode(
            private_key.sign(transparency_checkpoint_payload(unsigned))
        ).decode(),
    )


def _workspace(tmp_path: Path, monkeypatch) -> tuple[Path, AgoraWorkspace, Ed25519PrivateKey]:
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    workspace = AgoraWorkspace(cwd=project, now=lambda: datetime(2026, 8, 16, 13, tzinfo=UTC))
    workspace.initialize(InitInput(integration="generic"))
    private_key = Ed25519PrivateKey.generate()
    workspace.add_transparency_trust_key(
        AddTransparencyTrustKeyInput(
            id="public-log-2026",
            log="public-log",
            public_key=str(_write_public_key(tmp_path / "log.pem", private_key)),
            scope="project",
        )
    )
    return project, workspace, private_key


def test_cli_verifies_records_and_revalidates_transparency_proof(
    tmp_path: Path, monkeypatch
) -> None:
    project, workspace, private_key = _workspace(tmp_path, monkeypatch)
    source = tmp_path / "PROOF.md"
    source.write_text(render_transparency_proof(_proof(private_key, source)))
    output = io.StringIO()

    assert (
        main(
            [
                "registry",
                "verify-transparency",
                "--source",
                str(source),
                "--scope",
                "project",
                "--record",
            ],
            cwd=project,
            stdout=output,
        )
        == 0
    )

    result = json.loads(output.getvalue())
    recorded = (
        project / ".agora" / "transparency" / "public-log" / "community" / "1.2.0" / "PROOF.md"
    )
    assert result["recorded"] is True
    assert result["inclusion_verified"] is True
    assert result["signature_verified"] is True
    assert Path(result["path"]) == recorded
    assert recorded.is_file()
    report = workspace.validate()
    assert report.ok is True
    assert report.checked["transparency-proofs"] == 1

    workspace.revoke_transparency_trust_key(
        RevokeTransparencyTrustKeyInput(
            id="public-log-2026",
            scope="project",
            reason="Routine rotation after proof integration",
        )
    )
    assert workspace.validate().ok is True

    persisted = _proof(private_key, recorded)
    recorded.write_text(render_transparency_proof(replace(persisted, sha256="2" * 64)))
    report = workspace.validate()
    assert report.ok is False
    assert any(item.code == "transparency-proof.verification-failed" for item in report.issues)


def test_rejects_incomplete_transparency_inclusion_path(tmp_path: Path, monkeypatch) -> None:
    _, workspace, private_key = _workspace(tmp_path, monkeypatch)
    source = tmp_path / "PROOF.md"
    incomplete = replace(_proof(private_key, source), inclusion_path=[])
    incomplete = replace(
        incomplete,
        checkpoint_signature=base64.b64encode(
            private_key.sign(transparency_checkpoint_payload(incomplete))
        ).decode(),
    )
    source.write_text(render_transparency_proof(incomplete))

    with pytest.raises(ValueError, match="incomplete"):
        workspace.verify_transparency_inclusion(
            VerifyTransparencyProofInput(source=str(source), scope="project")
        )


def test_rejects_forged_transparency_checkpoint_signature(tmp_path: Path, monkeypatch) -> None:
    _, workspace, private_key = _workspace(tmp_path, monkeypatch)
    source = tmp_path / "PROOF.md"
    forged = replace(
        _proof(private_key, source),
        checkpoint_signature=base64.b64encode(b"\x00" * 64).decode(),
    )
    source.write_text(render_transparency_proof(forged))

    with pytest.raises(ValueError, match="checkpoint signature is invalid"):
        workspace.verify_transparency_inclusion(
            VerifyTransparencyProofInput(source=str(source), scope="project")
        )


def test_rejects_new_proof_from_revoked_transparency_key(tmp_path: Path, monkeypatch) -> None:
    _, workspace, private_key = _workspace(tmp_path, monkeypatch)
    source = tmp_path / "PROOF.md"
    source.write_text(render_transparency_proof(_proof(private_key, source)))
    workspace.revoke_transparency_trust_key(
        RevokeTransparencyTrustKeyInput(
            id="public-log-2026",
            scope="project",
            reason="Compromised checkpoint authority",
        )
    )

    with pytest.raises(ValueError, match="revoked"):
        workspace.verify_transparency_inclusion(
            VerifyTransparencyProofInput(source=str(source), scope="project", record=True)
        )


def test_validation_rejects_proof_integrated_after_key_revocation(
    tmp_path: Path, monkeypatch
) -> None:
    project, workspace, private_key = _workspace(tmp_path, monkeypatch)
    workspace.revoke_transparency_trust_key(
        RevokeTransparencyTrustKeyInput(
            id="public-log-2026",
            scope="project",
            reason="Compromised checkpoint authority",
        )
    )
    recorded = (
        project / ".agora" / "transparency" / "public-log" / "community" / "1.2.0" / "PROOF.md"
    )
    unsigned = replace(_proof(private_key, recorded), integrated_at="2099-01-01T00:00:00Z")
    proof = replace(
        unsigned,
        checkpoint_signature=base64.b64encode(
            private_key.sign(transparency_checkpoint_payload(unsigned))
        ).decode(),
    )
    recorded.parent.mkdir(parents=True)
    recorded.write_text(render_transparency_proof(proof))

    report = workspace.validate()
    assert report.ok is False
    assert any(
        item.code == "transparency-proof.verification-failed"
        and "after its trust key was revoked" in item.message
        for item in report.issues
    )
