import base64
import hashlib
import os
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

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


def main() -> None:
    runtime = Path(tempfile.mkdtemp(prefix="agora-organization-trust-sample-"))
    project = runtime / "project"
    publisher = runtime / "external-publisher"
    project.mkdir()
    publisher.mkdir()
    os.environ["AGORA_HOME"] = str(runtime / "home")

    organization_key = Ed25519PrivateKey.generate()
    organization_public = publisher / "example-org-root.pem"
    organization_public.write_bytes(
        organization_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    release_key = Ed25519PrivateKey.generate()
    release_public = release_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    keys: list[dict[str, object]] = [
        {
            "id": "team-release-2026",
            "registry": "team-catalog",
            "algorithm": "ed25519",
            "public-key": base64.b64encode(release_public).decode(),
            "fingerprint": hashlib.sha256(release_public).hexdigest(),
            "status": "active",
            "created-at": "2026-08-15T12:00:00Z",
            "revoked-at": None,
            "revoked-reason": None,
            "replaced-by": None,
        }
    ]
    payload = organization_trust_signature_payload(
        organization="example-org",
        sequence=1,
        generated_at="2026-08-15T12:01:00Z",
        previous_sha256=None,
        keys=keys,
    )
    bundle = publisher / "BUNDLE.md"
    bundle.write_text(
        render_organization_trust_bundle(
            organization="example-org",
            sequence=1,
            generated_at="2026-08-15T12:01:00Z",
            previous_sha256=None,
            keys=keys,
            signature=base64.b64encode(organization_key.sign(payload)).decode(),
        ),
        encoding="utf-8",
    )

    agora = AgoraWorkspace(cwd=project)
    agora.initialize(InitInput(integration="generic"))
    agora.add_organization_trust_root(
        AddOrganizationTrustRootInput(
            id="example-org",
            public_key=str(organization_public),
            scope="project",
        )
    )
    preview = agora.sync_organization_trust(
        SyncOrganizationTrustInput(id="example-org", scope="project", source=str(bundle))
    )
    assert preview.applied is False
    assert not agora.list_registry_trust_keys()
    applied = agora.sync_organization_trust(
        SyncOrganizationTrustInput(
            id="example-org", scope="project", source=str(bundle), apply=True
        )
    )
    assert agora.validate().ok
    print(f"Project: {project}")
    print(f"Preview: {preview.steps[0].action} {preview.steps[0].id}")
    print(f"Applied bundle: {applied.organization}/{applied.sequence}")
    print(f"History: {applied.history_path}")


if __name__ == "__main__":
    main()
