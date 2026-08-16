import base64
import hashlib
from dataclasses import replace
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from agora.filesystem import assert_slug
from agora.markdown import (
    MarkdownDocument,
    optional_string_attribute,
    read_markdown,
    render_markdown,
    string_attribute,
)
from agora.model import TransparencyTrustKeyRecord
from agora.trust import decode_trusted_public_key

TRANSPARENCY_TRUST_KEY_SCHEMA = "agora/transparency-trust-key/v1"


def transparency_key_from_pem(
    *, id_: str, log: str, public_key_path: Path, scope: str, path: Path, created_at: str
) -> TransparencyTrustKeyRecord:
    assert_slug(id_, "Transparency trust key id")
    assert_slug(log, "Transparency log id")
    _assert_scope(scope)
    if not public_key_path.is_file():
        raise FileNotFoundError(f"Transparency log public key not found: {public_key_path}")
    loaded = serialization.load_pem_public_key(public_key_path.read_bytes())
    if not isinstance(loaded, Ed25519PublicKey):
        raise ValueError(f"Transparency log public key must be Ed25519: {public_key_path}")
    raw = loaded.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return TransparencyTrustKeyRecord(
        id=id_,
        log=log,
        algorithm="ed25519",
        public_key=base64.b64encode(raw).decode(),
        fingerprint=hashlib.sha256(raw).hexdigest(),
        status="active",
        scope=scope,  # type: ignore[arg-type]
        path=str(path),
        created_at=created_at,
    )


def load_transparency_key(path: Path, scope: str) -> TransparencyTrustKeyRecord:
    _assert_scope(scope)
    attributes = read_markdown(path).attributes
    if string_attribute(attributes, "schema") != TRANSPARENCY_TRUST_KEY_SCHEMA:
        raise ValueError(f"Expected schema {TRANSPARENCY_TRUST_KEY_SCHEMA}: {path}")
    id_ = string_attribute(attributes, "id")
    log = string_attribute(attributes, "log")
    assert_slug(id_, "Transparency trust key id")
    assert_slug(log, "Transparency log id")
    if string_attribute(attributes, "algorithm") != "ed25519":
        raise ValueError(f"Transparency trust key algorithm must be ed25519: {path}")
    if string_attribute(attributes, "scope") != scope:
        raise ValueError(f"Transparency trust key scope does not match its location: {path}")
    public_key = string_attribute(attributes, "public-key")
    fingerprint = string_attribute(attributes, "fingerprint")
    if hashlib.sha256(decode_trusted_public_key(public_key)).hexdigest() != fingerprint:
        raise ValueError(f"Transparency trust key fingerprint mismatch: {path}")
    status = string_attribute(attributes, "status")
    if status not in {"active", "revoked"}:
        raise ValueError(f"Unsupported transparency trust key status: {status}")
    revoked_at = optional_string_attribute(attributes, "revoked-at")
    revoked_reason = optional_string_attribute(attributes, "revoked-reason")
    replaced_by = optional_string_attribute(attributes, "replaced-by")
    if replaced_by is not None:
        assert_slug(replaced_by, "Replacement transparency trust key id")
        if replaced_by == id_:
            raise ValueError(f"Transparency trust key cannot replace itself: {path}")
    if status == "active" and any(
        item is not None for item in (revoked_at, revoked_reason, replaced_by)
    ):
        raise ValueError(f"Active transparency trust key has revocation fields: {path}")
    if status == "revoked" and (revoked_at is None or revoked_reason is None):
        raise ValueError(f"Revoked transparency trust key requires date and reason: {path}")
    return TransparencyTrustKeyRecord(
        id=id_,
        log=log,
        algorithm="ed25519",
        public_key=public_key,
        fingerprint=fingerprint,
        status=status,  # type: ignore[arg-type]
        scope=scope,  # type: ignore[arg-type]
        path=str(path),
        created_at=string_attribute(attributes, "created-at"),
        revoked_at=revoked_at,
        revoked_reason=revoked_reason,
        replaced_by=replaced_by,
    )


def render_transparency_key(record: TransparencyTrustKeyRecord) -> str:
    return render_markdown(
        MarkdownDocument(
            attributes={
                "schema": TRANSPARENCY_TRUST_KEY_SCHEMA,
                "id": record.id,
                "log": record.log,
                "algorithm": record.algorithm,
                "public-key": record.public_key,
                "fingerprint": record.fingerprint,
                "status": record.status,
                "scope": record.scope,
                "created-at": record.created_at,
                "revoked-at": record.revoked_at,
                "revoked-reason": record.revoked_reason,
                "replaced-by": record.replaced_by,
            },
            body=(
                f"# Transparency trust key {record.id}\n\n"
                f"This key verifies signed checkpoints from transparency log `{record.log}`."
            ),
        )
    )


def revoke_transparency_key(
    record: TransparencyTrustKeyRecord, *, revoked_at: str, reason: str, replaced_by: str | None
) -> TransparencyTrustKeyRecord:
    if record.status == "revoked":
        raise ValueError(f"Transparency trust key is already revoked: {record.id}")
    if not reason.strip():
        raise ValueError("Transparency trust key revocation reason cannot be empty")
    if replaced_by == record.id:
        raise ValueError("Transparency trust key cannot replace itself")
    return replace(
        record,
        status="revoked",
        revoked_at=revoked_at,
        revoked_reason=reason.strip(),
        replaced_by=replaced_by,
    )


def _assert_scope(scope: str) -> None:
    if scope not in {"user", "project"}:
        raise ValueError(f"Unsupported transparency trust scope: {scope}")
