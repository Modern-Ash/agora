import base64
import binascii
import hashlib
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from cryptography.exceptions import InvalidSignature
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
from agora.model import (
    RegistryReleaseRecord,
    TransparencyInclusionProofRecord,
    TransparencyTrustKeyRecord,
)
from agora.registry_distribution import (
    SHA256_PATTERN,
    release_signature_payload,
    validate_registry_version,
)
from agora.trust import decode_trusted_public_key

TRANSPARENCY_TRUST_KEY_SCHEMA = "agora/transparency-trust-key/v1"
TRANSPARENCY_PROOF_SCHEMA = "agora/transparency-inclusion-proof/v1"
TRANSPARENCY_CHECKPOINT_SCHEMA = "agora/transparency-checkpoint/v1"
MAX_TRANSPARENCY_PROOF_BYTES = 256 * 1024
TRANSPARENCY_PROOF_ATTRIBUTES = {
    "schema",
    "log",
    "key-id",
    "registry",
    "version",
    "archive",
    "sha256",
    "tree-size",
    "leaf-index",
    "root-sha256",
    "inclusion-path",
    "checkpoint-signature",
    "integrated-at",
}


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


def load_transparency_proof(path: Path) -> TransparencyInclusionProofRecord:
    if not path.is_file():
        raise FileNotFoundError(f"Transparency proof not found: {path}")
    if path.stat().st_size > MAX_TRANSPARENCY_PROOF_BYTES:
        raise ValueError(f"Transparency proof exceeds the size limit: {path}")
    attributes = read_markdown(path).attributes
    unsupported = set(attributes) - TRANSPARENCY_PROOF_ATTRIBUTES
    missing = TRANSPARENCY_PROOF_ATTRIBUTES - set(attributes)
    if unsupported or missing:
        details = []
        if missing:
            details.append(f"missing {', '.join(sorted(missing))}")
        if unsupported:
            details.append(f"unsupported {', '.join(sorted(unsupported))}")
        raise ValueError(
            f"Transparency proof attributes are invalid ({'; '.join(details)}): {path}"
        )
    if string_attribute(attributes, "schema") != TRANSPARENCY_PROOF_SCHEMA:
        raise ValueError(f"Expected schema {TRANSPARENCY_PROOF_SCHEMA}: {path}")
    log = string_attribute(attributes, "log")
    key_id = string_attribute(attributes, "key-id")
    registry = string_attribute(attributes, "registry")
    assert_slug(log, "Transparency log id")
    assert_slug(key_id, "Transparency trust key id")
    assert_slug(registry, "Transparency proof registry")
    version = validate_registry_version(string_attribute(attributes, "version"))
    archive = string_attribute(attributes, "archive")
    sha256 = string_attribute(attributes, "sha256")
    root_sha256 = string_attribute(attributes, "root-sha256")
    if not SHA256_PATTERN.fullmatch(sha256) or not SHA256_PATTERN.fullmatch(root_sha256):
        raise ValueError(f"Transparency proof checksums are invalid: {path}")
    tree_size = attributes.get("tree-size")
    leaf_index = attributes.get("leaf-index")
    if (
        not isinstance(tree_size, int)
        or isinstance(tree_size, bool)
        or tree_size < 1
        or not isinstance(leaf_index, int)
        or isinstance(leaf_index, bool)
        or leaf_index < 0
        or leaf_index >= tree_size
    ):
        raise ValueError(f"Transparency proof tree position is invalid: {path}")
    raw_path = attributes.get("inclusion-path")
    if (
        not isinstance(raw_path, list)
        or len(raw_path) > 64
        or any(not isinstance(item, str) or not SHA256_PATTERN.fullmatch(item) for item in raw_path)
    ):
        raise ValueError(f"Transparency proof inclusion path is invalid: {path}")
    integrated_at = string_attribute(attributes, "integrated-at")
    _parse_timestamp(integrated_at, "Transparency proof integrated-at")
    return TransparencyInclusionProofRecord(
        log=log,
        key_id=key_id,
        registry=registry,
        version=version,
        archive=archive,
        sha256=sha256,
        tree_size=tree_size,
        leaf_index=leaf_index,
        root_sha256=root_sha256,
        inclusion_path=raw_path,
        checkpoint_signature=string_attribute(attributes, "checkpoint-signature"),
        integrated_at=integrated_at,
        path=str(path),
    )


def render_transparency_proof(record: TransparencyInclusionProofRecord) -> str:
    return render_markdown(
        MarkdownDocument(
            attributes={
                "schema": TRANSPARENCY_PROOF_SCHEMA,
                "log": record.log,
                "key-id": record.key_id,
                "registry": record.registry,
                "version": record.version,
                "archive": record.archive,
                "sha256": record.sha256,
                "tree-size": record.tree_size,
                "leaf-index": record.leaf_index,
                "root-sha256": record.root_sha256,
                "inclusion-path": record.inclusion_path,
                "checkpoint-signature": record.checkpoint_signature,
                "integrated-at": record.integrated_at,
            },
            body=(
                f"# Transparency proof {record.registry}@{record.version}\n\n"
                f"This proof binds the release to a signed checkpoint from `{record.log}`."
            ),
        )
    )


def verify_transparency_proof(
    proof: TransparencyInclusionProofRecord, key: TransparencyTrustKeyRecord
) -> None:
    if key.log != proof.log or key.id != proof.key_id:
        raise ValueError("Transparency proof key is not authorized for the declared log")
    release = RegistryReleaseRecord(
        registry=proof.registry,
        version=proof.version,
        archive=proof.archive,
        sha256=proof.sha256,
    )
    leaf_hash = hashlib.sha256(b"\x00" + release_signature_payload(release)).digest()
    calculated = _root_from_inclusion_path(
        leaf_hash,
        proof.leaf_index,
        proof.tree_size,
        [bytes.fromhex(item) for item in proof.inclusion_path],
    )
    if calculated.hex() != proof.root_sha256:
        raise ValueError("Transparency proof does not produce the signed checkpoint root")
    try:
        signature = base64.b64decode(proof.checkpoint_signature, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError("Transparency checkpoint signature must be valid base64") from error
    public_key = Ed25519PublicKey.from_public_bytes(decode_trusted_public_key(key.public_key))
    try:
        public_key.verify(signature, transparency_checkpoint_payload(proof))
    except InvalidSignature as error:
        raise ValueError("Transparency checkpoint signature is invalid") from error
    if key.status == "revoked":
        if key.revoked_at is None:
            raise ValueError("Revoked transparency trust key has no revocation timestamp")
        integrated_at = _parse_timestamp(proof.integrated_at, "Transparency proof integrated-at")
        revoked_at = _parse_timestamp(key.revoked_at, "Transparency key revoked-at")
        if integrated_at >= revoked_at:
            raise ValueError("Transparency proof was integrated after its trust key was revoked")


def transparency_checkpoint_payload(proof: TransparencyInclusionProofRecord) -> bytes:
    return (
        f"{TRANSPARENCY_CHECKPOINT_SCHEMA}\n"
        f"log={proof.log}\n"
        f"tree-size={proof.tree_size}\n"
        f"root-sha256={proof.root_sha256}\n"
        f"integrated-at={proof.integrated_at}\n"
    ).encode()


def _root_from_inclusion_path(
    leaf_hash: bytes, leaf_index: int, tree_size: int, path: list[bytes]
) -> bytes:
    node = leaf_hash
    index = leaf_index
    last = tree_size - 1
    for sibling in path:
        if index & 1 or index == last:
            node = hashlib.sha256(b"\x01" + sibling + node).digest()
            while index and not index & 1:
                index >>= 1
                last >>= 1
        else:
            node = hashlib.sha256(b"\x01" + node + sibling).digest()
        index >>= 1
        last >>= 1
    if last != 0:
        raise ValueError("Transparency proof inclusion path is incomplete")
    return node


def _assert_scope(scope: str) -> None:
    if scope not in {"user", "project"}:
        raise ValueError(f"Unsupported transparency trust scope: {scope}")


def _parse_timestamp(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{label} must be an ISO 8601 timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include a timezone")
    return parsed
