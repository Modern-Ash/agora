import base64
import binascii
import hashlib
import json
import re
from dataclasses import replace
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
    ActorKeyRecord,
    ActorRecord,
    LifecycleActionRecord,
    SessionRecord,
    ToolRunRecord,
)

ACTOR_KEY_SCHEMA = "agora/actor-key/v1"
ACTOR_KEY_STATUSES = {"active", "rotated", "revoked"}


def actor_identity_from_pem(public_key_path: Path) -> tuple[str, str]:
    if not public_key_path.is_file():
        raise FileNotFoundError(f"Actor public key not found: {public_key_path}")
    loaded = serialization.load_pem_public_key(public_key_path.read_bytes())
    if not isinstance(loaded, Ed25519PublicKey):
        raise ValueError(f"Actor public key must be Ed25519: {public_key_path}")
    raw = loaded.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64.b64encode(raw).decode(), hashlib.sha256(raw).hexdigest()


def validate_actor_identity(actor: ActorRecord) -> Ed25519PublicKey | None:
    values = (
        actor.authentication_algorithm,
        actor.authentication_public_key,
        actor.authentication_fingerprint,
    )
    revocation_values = (actor.authentication_revoked_at, actor.authentication_revoked_reason)
    if any(value is not None for value in revocation_values) and any(
        value is None for value in revocation_values
    ):
        raise ValueError(f"Actor {actor.reference} has incomplete authentication revocation")
    if actor.authentication_revoked_at is not None and all(value is None for value in values):
        raise ValueError(f"Actor {actor.reference} revokes an authentication key it does not have")
    if all(value is None for value in values):
        if actor.authentication_required:
            raise ValueError(f"Actor {actor.reference} requires authentication without a key")
        return None
    if any(value is None for value in values):
        raise ValueError(f"Actor {actor.reference} has incomplete authentication metadata")
    if actor.authentication_algorithm != "ed25519":
        raise ValueError(f"Actor {actor.reference} authentication algorithm must be ed25519")
    raw = _decode_public_key(
        actor.authentication_public_key,
        f"Actor {actor.reference} authentication public key",
    )
    fingerprint = hashlib.sha256(raw).hexdigest()
    if actor.authentication_fingerprint != fingerprint:
        raise ValueError(f"Actor {actor.reference} authentication fingerprint mismatch")
    return Ed25519PublicKey.from_public_bytes(raw)


def assert_actor_identity_available(actor: ActorRecord) -> None:
    validate_actor_identity(actor)
    if actor.authentication_revoked_at is not None:
        raise PermissionError(f"Actor {actor.reference} authentication key is revoked")


def actor_key_from_actor(actor: ActorRecord, path: Path, created_at: str) -> ActorKeyRecord:
    validate_actor_identity(actor)
    if (
        actor.authentication_algorithm is None
        or actor.authentication_public_key is None
        or actor.authentication_fingerprint is None
    ):
        raise ValueError(f"Actor {actor.reference} has no authentication key")
    revoked = actor.authentication_revoked_at is not None
    return ActorKeyRecord(
        actor=actor.reference,
        algorithm="ed25519",
        public_key=actor.authentication_public_key,
        fingerprint=actor.authentication_fingerprint,
        status="revoked" if revoked else "active",
        path=str(path),
        created_at=created_at,
        ended_at=actor.authentication_revoked_at,
        reason=actor.authentication_revoked_reason,
    )


def actor_key_from_pem(
    actor: str, public_key_path: Path, key_root: Path, created_at: str
) -> ActorKeyRecord:
    public_key, fingerprint = actor_identity_from_pem(public_key_path)
    return actor_key_from_public_key(actor, public_key, key_root, created_at)


def actor_key_from_public_key(
    actor: str, public_key: str, key_root: Path, created_at: str
) -> ActorKeyRecord:
    raw = _decode_public_key(public_key, f"Actor {actor} public key")
    fingerprint = hashlib.sha256(raw).hexdigest()
    return ActorKeyRecord(
        actor=actor,
        algorithm="ed25519",
        public_key=public_key,
        fingerprint=fingerprint,
        status="active",
        path=str(key_root / f"{fingerprint}.md"),
        created_at=created_at,
    )


def load_actor_key(path: Path) -> ActorKeyRecord:
    document = read_markdown(path)
    attributes = document.attributes
    if string_attribute(attributes, "schema") != ACTOR_KEY_SCHEMA:
        raise ValueError(f"Expected schema {ACTOR_KEY_SCHEMA}: {path}")
    actor = string_attribute(attributes, "actor")
    if ":" not in actor:
        raise ValueError(f"Actor key must use a scoped actor reference: {path}")
    scope, actor_id = actor.split(":", 1)
    if scope not in {"user", "project"}:
        raise ValueError(f"Actor key has unsupported actor scope: {path}")
    assert_slug(actor_id, "Actor key actor id")
    algorithm = string_attribute(attributes, "algorithm")
    if algorithm != "ed25519":
        raise ValueError(f"Actor key algorithm must be ed25519: {path}")
    public_key = string_attribute(attributes, "public-key")
    raw = _decode_public_key(public_key, f"Actor key {path}")
    fingerprint = string_attribute(attributes, "fingerprint")
    if fingerprint != hashlib.sha256(raw).hexdigest():
        raise ValueError(f"Actor key fingerprint mismatch: {path}")
    status = string_attribute(attributes, "status")
    if status not in ACTOR_KEY_STATUSES:
        raise ValueError(f"Unsupported actor key status: {status}")
    ended_at = optional_string_attribute(attributes, "ended-at")
    reason = optional_string_attribute(attributes, "reason")
    replaced_by = optional_string_attribute(attributes, "replaced-by")
    if replaced_by is not None and not re.fullmatch(r"[0-9a-f]{64}", replaced_by):
        raise ValueError(f"Actor replacement key must be a SHA-256 fingerprint: {path}")
    if replaced_by == fingerprint:
        raise ValueError(f"Actor key cannot replace itself: {path}")
    if status == "active" and any(value is not None for value in (ended_at, reason, replaced_by)):
        raise ValueError(f"Active actor key cannot contain lifecycle fields: {path}")
    if status != "active" and any(value is None for value in (ended_at, reason)):
        raise ValueError(f"Inactive actor key requires an end date and reason: {path}")
    if status == "rotated" and replaced_by is None:
        raise ValueError(f"Rotated actor key requires a replacement fingerprint: {path}")
    return ActorKeyRecord(
        actor=actor,
        algorithm="ed25519",
        public_key=public_key,
        fingerprint=fingerprint,
        status=status,  # type: ignore[arg-type]
        path=str(path),
        created_at=string_attribute(attributes, "created-at"),
        ended_at=ended_at,
        reason=reason,
        replaced_by=replaced_by,
    )


def render_actor_key(record: ActorKeyRecord) -> str:
    return render_markdown(
        MarkdownDocument(
            attributes={
                "schema": ACTOR_KEY_SCHEMA,
                "actor": record.actor,
                "algorithm": record.algorithm,
                "public-key": record.public_key,
                "fingerprint": record.fingerprint,
                "status": record.status,
                "created-at": record.created_at,
                "ended-at": record.ended_at,
                "reason": record.reason,
                "replaced-by": record.replaced_by,
            },
            body=(
                f"# Actor key {record.fingerprint}\n\n"
                f"This public key belongs to `{record.actor}`. Private key material is external."
            ),
        )
    )


def end_actor_key(
    record: ActorKeyRecord,
    *,
    status: str,
    ended_at: str,
    reason: str,
    replaced_by: str | None = None,
) -> ActorKeyRecord:
    if record.status != "active":
        raise ValueError(f"Actor key is not active: {record.fingerprint}")
    if status not in {"rotated", "revoked"}:
        raise ValueError(f"Unsupported actor key transition: {status}")
    if not reason.strip():
        raise ValueError("Actor key lifecycle reason cannot be empty")
    if status == "rotated" and replaced_by is None:
        raise ValueError("Rotated actor key requires a replacement fingerprint")
    return ActorKeyRecord(
        actor=record.actor,
        algorithm=record.algorithm,
        public_key=record.public_key,
        fingerprint=record.fingerprint,
        status=status,  # type: ignore[arg-type]
        path=record.path,
        created_at=record.created_at,
        ended_at=ended_at,
        reason=reason.strip(),
        replaced_by=replaced_by,
    )


def link_actor_key_replacement(record: ActorKeyRecord, replaced_by: str) -> ActorKeyRecord:
    if record.status != "revoked":
        raise ValueError(f"Only a revoked actor key can be linked later: {record.fingerprint}")
    if record.replaced_by is not None:
        raise ValueError(f"Actor key already has a replacement: {record.fingerprint}")
    if not re.fullmatch(r"[0-9a-f]{64}", replaced_by):
        raise ValueError("Replacement actor key must be a SHA-256 fingerprint")
    if replaced_by == record.fingerprint:
        raise ValueError("Actor key cannot replace itself")
    return replace(record, replaced_by=replaced_by)


def _decode_public_key(value: str, label: str) -> bytes:
    try:
        raw = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError(f"{label} must be valid base64") from error
    if len(raw) != 32:
        raise ValueError(f"{label} must contain 32 Ed25519 bytes")
    Ed25519PublicKey.from_public_bytes(raw)
    return raw


def tool_authorization_payload(record: ToolRunRecord) -> bytes:
    value = {
        "schema": "agora/tool-authorization/v1",
        "run": record.id,
        "tool": record.tool_id,
        "operation": record.operation_id,
        "actor": record.actor,
        "swarm": record.swarm_id,
        "work": record.work_id,
        "capability": record.capability,
        "risk": record.risk,
        "inputs": record.inputs,
        "command": record.command,
        "timeout-seconds": record.timeout_seconds,
        "max-output-bytes": record.max_output_bytes,
        "created-at": record.created_at,
    }
    if record.environment_id is not None:
        value["environment"] = record.environment_id
    return (
        json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode()


def session_authorization_payload(record: SessionRecord) -> bytes:
    if record.context_sha256 is None:
        raise ValueError(f"Session has no context digest: {record.id}")
    value = {
        "schema": "agora/session-authorization/v1",
        "session": record.id,
        "actor": record.actor,
        "swarm": record.swarm_id,
        "work": record.work_id,
        "roles": record.roles,
        "integration": record.integration,
        "provider": record.provider,
        "model": record.model,
        "launch-command": record.launch_command,
        "timeout-seconds": record.timeout_seconds,
        "max-output-bytes": record.max_output_bytes,
        "context-sha256": record.context_sha256,
        "created-at": record.created_at,
    }
    if record.executor is not None and record.executor != record.actor:
        value["executor"] = record.executor
    return (
        json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode()


def lifecycle_authorization_payload(record: LifecycleActionRecord) -> bytes:
    value = {
        "schema": "agora/lifecycle-authorization/v1",
        "action": record.id,
        "kind": record.action,
        "actor": record.actor,
        "swarm": record.swarm_id,
        "work": record.work_id,
        "parameters": record.parameters,
        "precondition-sha256": record.precondition_sha256,
        "created-at": record.created_at,
    }
    return (
        json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode()


def verify_lifecycle_authorization(
    actor: ActorRecord,
    record: LifecycleActionRecord,
    signature_path: Path,
) -> tuple[str, str, str, str]:
    return _verify_actor_signature(
        actor,
        lifecycle_authorization_payload(record),
        signature_path,
        f"Lifecycle authorization signature is invalid: {record.id}",
    )


def verify_session_authorization(
    actor: ActorRecord,
    record: SessionRecord,
    signature_path: Path,
) -> tuple[str, str, str, str]:
    return _verify_actor_signature(
        actor,
        session_authorization_payload(record),
        signature_path,
        f"Session authorization signature is invalid: {record.id}",
    )


def verify_tool_authorization(
    actor: ActorRecord,
    record: ToolRunRecord,
    signature_path: Path,
) -> tuple[str, str, str, str]:
    return _verify_actor_signature(
        actor,
        tool_authorization_payload(record),
        signature_path,
        f"Actor authorization signature is invalid: {record.id}",
    )


def _verify_actor_signature(
    actor: ActorRecord,
    payload: bytes,
    signature_path: Path,
    invalid_message: str,
) -> tuple[str, str, str, str]:
    assert_actor_identity_available(actor)
    public_key = validate_actor_identity(actor)
    if public_key is None or actor.authentication_fingerprint is None:
        raise ValueError(f"Actor {actor.reference} has no authentication key")
    if not signature_path.is_file():
        raise FileNotFoundError(f"Actor authorization signature not found: {signature_path}")
    signature = signature_path.read_bytes()
    if len(signature) != 64:
        raise ValueError("Actor authorization signature must contain 64 Ed25519 bytes")
    try:
        public_key.verify(signature, payload)
    except InvalidSignature as error:
        raise ValueError(invalid_message) from error
    assert actor.authentication_public_key is not None
    return (
        actor.authentication_fingerprint,
        hashlib.sha256(payload).hexdigest(),
        actor.authentication_public_key,
        base64.b64encode(signature).decode(),
    )


def validate_persisted_tool_authorization(record: ToolRunRecord) -> None:
    if not record.authentication_verified:
        return
    if record.authentication_public_key is None or record.authorization_signature is None:
        raise ValueError(f"Tool Run authentication evidence is incomplete: {record.id}")
    try:
        public_key_raw = base64.b64decode(record.authentication_public_key, validate=True)
        signature = base64.b64decode(record.authorization_signature, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError(
            f"Tool Run authentication evidence must be valid base64: {record.id}"
        ) from error
    if len(public_key_raw) != 32 or len(signature) != 64:
        raise ValueError(
            f"Tool Run authentication evidence has invalid Ed25519 lengths: {record.id}"
        )
    fingerprint = hashlib.sha256(public_key_raw).hexdigest()
    if record.authentication_fingerprint != fingerprint:
        raise ValueError(f"Tool Run authentication fingerprint mismatch: {record.id}")
    payload = tool_authorization_payload(record)
    if record.authorization_sha256 != hashlib.sha256(payload).hexdigest():
        raise ValueError(f"Tool Run authorization payload digest mismatch: {record.id}")
    try:
        Ed25519PublicKey.from_public_bytes(public_key_raw).verify(signature, payload)
    except InvalidSignature as error:
        raise ValueError(f"Tool Run authorization signature is invalid: {record.id}") from error


def validate_persisted_session_authorization(record: SessionRecord) -> None:
    if not record.authentication_verified:
        return
    if record.authentication_public_key is None or record.authorization_signature is None:
        raise ValueError(f"Session authentication evidence is incomplete: {record.id}")
    try:
        public_key_raw = base64.b64decode(record.authentication_public_key, validate=True)
        signature = base64.b64decode(record.authorization_signature, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError(
            f"Session authentication evidence must be valid base64: {record.id}"
        ) from error
    if len(public_key_raw) != 32 or len(signature) != 64:
        raise ValueError(
            f"Session authentication evidence has invalid Ed25519 lengths: {record.id}"
        )
    fingerprint = hashlib.sha256(public_key_raw).hexdigest()
    if record.authentication_fingerprint != fingerprint:
        raise ValueError(f"Session authentication fingerprint mismatch: {record.id}")
    payload = session_authorization_payload(record)
    if record.authorization_sha256 != hashlib.sha256(payload).hexdigest():
        raise ValueError(f"Session authorization payload digest mismatch: {record.id}")
    try:
        Ed25519PublicKey.from_public_bytes(public_key_raw).verify(signature, payload)
    except InvalidSignature as error:
        raise ValueError(f"Session authorization signature is invalid: {record.id}") from error


def validate_persisted_lifecycle_authorization(record: LifecycleActionRecord) -> None:
    if not record.authentication_verified:
        return
    if record.authentication_public_key is None or record.authorization_signature is None:
        raise ValueError(f"Lifecycle Action authentication evidence is incomplete: {record.id}")
    try:
        public_key_raw = base64.b64decode(record.authentication_public_key, validate=True)
        signature = base64.b64decode(record.authorization_signature, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError(
            f"Lifecycle Action authentication evidence must be valid base64: {record.id}"
        ) from error
    if len(public_key_raw) != 32 or len(signature) != 64:
        raise ValueError(
            f"Lifecycle Action authentication evidence has invalid Ed25519 lengths: {record.id}"
        )
    fingerprint = hashlib.sha256(public_key_raw).hexdigest()
    if record.authentication_fingerprint != fingerprint:
        raise ValueError(f"Lifecycle Action authentication fingerprint mismatch: {record.id}")
    payload = lifecycle_authorization_payload(record)
    if record.authorization_sha256 != hashlib.sha256(payload).hexdigest():
        raise ValueError(f"Lifecycle Action authorization payload digest mismatch: {record.id}")
    try:
        Ed25519PublicKey.from_public_bytes(public_key_raw).verify(signature, payload)
    except InvalidSignature as error:
        raise ValueError(
            f"Lifecycle Action authorization signature is invalid: {record.id}"
        ) from error
