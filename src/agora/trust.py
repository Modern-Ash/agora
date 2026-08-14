import base64
import binascii
import hashlib
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
from agora.model import RegistryTrustKeyRecord

TRUST_KEY_SCHEMA = "agora/registry-trust-key/v1"
TRUST_KEY_STATUSES = ("active", "revoked")


def trust_key_from_pem(
    *,
    id_: str,
    registry: str,
    public_key_path: Path,
    scope: str,
    path: Path,
    created_at: str,
) -> RegistryTrustKeyRecord:
    assert_slug(id_, "Registry trust key id")
    assert_slug(registry, "Registry trust key registry")
    _assert_scope(scope)
    if not public_key_path.is_file():
        raise FileNotFoundError(f"Registry public key not found: {public_key_path}")
    loaded = serialization.load_pem_public_key(public_key_path.read_bytes())
    if not isinstance(loaded, Ed25519PublicKey):
        raise ValueError(f"Registry public key must be Ed25519: {public_key_path}")
    raw = loaded.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return RegistryTrustKeyRecord(
        id=id_,
        registry=registry,
        algorithm="ed25519",
        public_key=base64.b64encode(raw).decode(),
        fingerprint=hashlib.sha256(raw).hexdigest(),
        status="active",
        scope=scope,  # type: ignore[arg-type]
        path=str(path),
        created_at=created_at,
    )


def load_trust_key(path: Path, scope: str) -> RegistryTrustKeyRecord:
    _assert_scope(scope)
    document = read_markdown(path)
    attributes = document.attributes
    if string_attribute(attributes, "schema") != TRUST_KEY_SCHEMA:
        raise ValueError(f"Expected schema {TRUST_KEY_SCHEMA}: {path}")
    id_ = string_attribute(attributes, "id")
    assert_slug(id_, "Registry trust key id")
    registry = string_attribute(attributes, "registry")
    assert_slug(registry, "Registry trust key registry")
    algorithm = string_attribute(attributes, "algorithm")
    if algorithm != "ed25519":
        raise ValueError(f"Registry trust key algorithm must be ed25519: {path}")
    public_key = string_attribute(attributes, "public-key")
    raw = decode_trusted_public_key(public_key)
    fingerprint = string_attribute(attributes, "fingerprint")
    actual_fingerprint = hashlib.sha256(raw).hexdigest()
    if fingerprint != actual_fingerprint:
        raise ValueError(f"Registry trust key fingerprint mismatch: {path}")
    status = string_attribute(attributes, "status")
    if status not in TRUST_KEY_STATUSES:
        raise ValueError(f"Unsupported registry trust key status: {status}")
    created_at = string_attribute(attributes, "created-at")
    revoked_at = optional_string_attribute(attributes, "revoked-at")
    revoked_reason = optional_string_attribute(attributes, "revoked-reason")
    replaced_by = optional_string_attribute(attributes, "replaced-by")
    if replaced_by is not None:
        assert_slug(replaced_by, "Replacement registry trust key id")
        if replaced_by == id_:
            raise ValueError(f"Registry trust key cannot replace itself: {path}")
    revocation_values = (revoked_at, revoked_reason)
    if status == "active" and any(value is not None for value in (*revocation_values, replaced_by)):
        raise ValueError(f"Active registry trust key cannot contain revocation fields: {path}")
    if status == "revoked" and any(value is None for value in revocation_values):
        raise ValueError(f"Revoked registry trust key requires date and reason: {path}")
    return RegistryTrustKeyRecord(
        id=id_,
        registry=registry,
        algorithm="ed25519",
        public_key=public_key,
        fingerprint=fingerprint,
        status=status,  # type: ignore[arg-type]
        scope=scope,  # type: ignore[arg-type]
        path=str(path),
        created_at=created_at,
        revoked_at=revoked_at,
        revoked_reason=revoked_reason,
        replaced_by=replaced_by,
    )


def render_trust_key(record: RegistryTrustKeyRecord) -> str:
    return render_markdown(
        MarkdownDocument(
            attributes={
                "schema": TRUST_KEY_SCHEMA,
                "id": record.id,
                "registry": record.registry,
                "algorithm": record.algorithm,
                "public-key": record.public_key,
                "fingerprint": record.fingerprint,
                "status": record.status,
                "created-at": record.created_at,
                "revoked-at": record.revoked_at,
                "revoked-reason": record.revoked_reason,
                "replaced-by": record.replaced_by,
            },
            body=(
                f"# Registry trust key {record.id}\n\n"
                f"This key is trusted for signed releases of registry `{record.registry}`."
            ),
        )
    )


def revoke_trust_key(
    record: RegistryTrustKeyRecord,
    *,
    revoked_at: str,
    reason: str,
    replaced_by: str | None,
) -> RegistryTrustKeyRecord:
    if record.status == "revoked":
        raise ValueError(f"Registry trust key is already revoked: {record.id}")
    if not reason.strip():
        raise ValueError("Registry trust key revocation reason cannot be empty")
    if replaced_by is not None:
        assert_slug(replaced_by, "Replacement registry trust key id")
        if replaced_by == record.id:
            raise ValueError("Registry trust key cannot replace itself")
    return RegistryTrustKeyRecord(
        id=record.id,
        registry=record.registry,
        algorithm=record.algorithm,
        public_key=record.public_key,
        fingerprint=record.fingerprint,
        status="revoked",
        scope=record.scope,
        path=record.path,
        created_at=record.created_at,
        revoked_at=revoked_at,
        revoked_reason=reason.strip(),
        replaced_by=replaced_by,
    )


def decode_trusted_public_key(value: str) -> bytes:
    try:
        raw = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError("Registry trust key public-key must be valid base64") from error
    if len(raw) != 32:
        raise ValueError("Registry trust key public-key must contain 32 Ed25519 bytes")
    Ed25519PublicKey.from_public_bytes(raw)
    return raw


def _assert_scope(scope: str) -> None:
    if scope not in {"user", "project"}:
        raise ValueError(f"Unsupported registry trust scope: {scope}")
