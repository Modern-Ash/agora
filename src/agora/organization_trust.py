import base64
import binascii
import hashlib
import json
from dataclasses import replace
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from agora.filesystem import assert_slug
from agora.markdown import (
    MarkdownDocument,
    optional_string_attribute,
    parse_markdown,
    read_markdown,
    render_markdown,
    string_attribute,
)
from agora.model import (
    OrganizationTrustRootRecord,
    OrganizationTrustRootRotationRecord,
    RegistryTrustKeyRecord,
)
from agora.trust import decode_trusted_public_key

ORGANIZATION_TRUST_ROOT_SCHEMA = "agora/organization-trust-root/v1"
ORGANIZATION_TRUST_BUNDLE_SCHEMA = "agora/organization-trust-bundle/v1"
ORGANIZATION_TRUST_SIGNATURE_SCHEMA = "agora/organization-trust-signature/v1"
ORGANIZATION_TRUST_ROOT_ROTATION_SCHEMA = "agora/organization-trust-root-rotation/v1"
ORGANIZATION_TRUST_ROOT_ROTATION_SIGNATURE_SCHEMA = (
    "agora/organization-trust-root-rotation-signature/v1"
)
MAXIMUM_BUNDLE_BYTES = 1024 * 1024
DOWNLOAD_TIMEOUT = 15


def organization_trust_root_from_pem(
    *, id_: str, public_key_path: Path, scope: str, path: Path, created_at: str
) -> OrganizationTrustRootRecord:
    assert_slug(id_, "Organization trust id")
    _assert_scope(scope)
    if not public_key_path.is_file():
        raise FileNotFoundError(f"Organization trust public key not found: {public_key_path}")
    loaded = serialization.load_pem_public_key(public_key_path.read_bytes())
    if not isinstance(loaded, Ed25519PublicKey):
        raise ValueError(f"Organization trust public key must be Ed25519: {public_key_path}")
    raw = loaded.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return OrganizationTrustRootRecord(
        id=id_,
        algorithm="ed25519",
        public_key=base64.b64encode(raw).decode(),
        fingerprint=hashlib.sha256(raw).hexdigest(),
        initial_public_key=base64.b64encode(raw).decode(),
        initial_fingerprint=hashlib.sha256(raw).hexdigest(),
        scope=scope,  # type: ignore[arg-type]
        path=str(path),
        created_at=created_at,
    )


def load_organization_trust_root(path: Path, scope: str) -> OrganizationTrustRootRecord:
    _assert_scope(scope)
    document = read_markdown(path)
    attributes = document.attributes
    base_attributes = {
        "schema",
        "id",
        "algorithm",
        "public-key",
        "fingerprint",
        "scope",
        "created-at",
        "source",
        "last-sequence",
        "last-sha256",
    }
    initial_attributes = {"initial-public-key", "initial-fingerprint"}
    if frozenset(attributes) not in {
        frozenset(base_attributes),
        frozenset(base_attributes | initial_attributes),
    }:
        raise ValueError(f"Organization trust root contains unsupported attributes: {path}")
    if string_attribute(attributes, "schema") != ORGANIZATION_TRUST_ROOT_SCHEMA:
        raise ValueError(f"Expected schema {ORGANIZATION_TRUST_ROOT_SCHEMA}: {path}")
    id_ = string_attribute(attributes, "id")
    assert_slug(id_, "Organization trust id")
    if string_attribute(attributes, "algorithm") != "ed25519":
        raise ValueError(f"Organization trust root algorithm must be ed25519: {path}")
    if string_attribute(attributes, "scope") != scope:
        raise ValueError(f"Organization trust root scope does not match its location: {path}")
    public_key = string_attribute(attributes, "public-key")
    raw = decode_trusted_public_key(public_key)
    fingerprint = string_attribute(attributes, "fingerprint")
    if hashlib.sha256(raw).hexdigest() != fingerprint:
        raise ValueError(f"Organization trust root fingerprint mismatch: {path}")
    if initial_attributes <= set(attributes):
        initial_public_key = string_attribute(attributes, "initial-public-key")
        initial_raw = decode_trusted_public_key(initial_public_key)
        initial_fingerprint = string_attribute(attributes, "initial-fingerprint")
        if hashlib.sha256(initial_raw).hexdigest() != initial_fingerprint:
            raise ValueError(f"Organization trust initial root fingerprint mismatch: {path}")
    else:
        initial_public_key = public_key
        initial_fingerprint = fingerprint
    last_sequence = attributes.get("last-sequence")
    if not isinstance(last_sequence, int) or isinstance(last_sequence, bool) or last_sequence < 0:
        raise ValueError(f"Organization trust last-sequence must be a non-negative integer: {path}")
    last_sha256 = optional_string_attribute(attributes, "last-sha256")
    if (last_sequence == 0) != (last_sha256 is None):
        raise ValueError(f"Organization trust sequence and checksum state are inconsistent: {path}")
    if last_sha256 is not None and not _is_sha256(last_sha256):
        raise ValueError(f"Organization trust last-sha256 is invalid: {path}")
    return OrganizationTrustRootRecord(
        id=id_,
        algorithm="ed25519",
        public_key=public_key,
        fingerprint=fingerprint,
        initial_public_key=initial_public_key,
        initial_fingerprint=initial_fingerprint,
        scope=scope,  # type: ignore[arg-type]
        path=str(path),
        created_at=string_attribute(attributes, "created-at"),
        source=optional_string_attribute(attributes, "source"),
        last_sequence=last_sequence,
        last_sha256=last_sha256,
    )


def render_organization_trust_root(record: OrganizationTrustRootRecord) -> str:
    return render_markdown(
        MarkdownDocument(
            attributes={
                "schema": ORGANIZATION_TRUST_ROOT_SCHEMA,
                "id": record.id,
                "algorithm": record.algorithm,
                "public-key": record.public_key,
                "fingerprint": record.fingerprint,
                "initial-public-key": record.initial_public_key,
                "initial-fingerprint": record.initial_fingerprint,
                "scope": record.scope,
                "created-at": record.created_at,
                "source": record.source,
                "last-sequence": record.last_sequence,
                "last-sha256": record.last_sha256,
            },
            body=(
                f"# Organization trust root {record.id}\n\n"
                "This public key verifies organization-managed registry trust bundles."
            ),
        )
    )


def load_organization_trust_bundle(
    contents: bytes, *, root: OrganizationTrustRootRecord
) -> tuple[int, str | None, list[RegistryTrustKeyRecord], str, str]:
    try:
        text = contents.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("Organization trust bundle must be UTF-8") from error
    document = parse_markdown(text)
    attributes = document.attributes
    expected_attributes = {
        "schema",
        "organization",
        "sequence",
        "generated-at",
        "previous-sha256",
        "keys",
        "signature",
    }
    if set(attributes) != expected_attributes:
        raise ValueError("Organization trust bundle contains unsupported attributes")
    if string_attribute(attributes, "schema") != ORGANIZATION_TRUST_BUNDLE_SCHEMA:
        raise ValueError(f"Expected schema {ORGANIZATION_TRUST_BUNDLE_SCHEMA}")
    organization = string_attribute(attributes, "organization")
    assert_slug(organization, "Organization trust id")
    if organization != root.id:
        raise ValueError(f"Organization trust bundle belongs to {organization}, expected {root.id}")
    sequence = attributes.get("sequence")
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
        raise ValueError("Organization trust bundle sequence must be a positive integer")
    generated_at = string_attribute(attributes, "generated-at")
    previous_sha256 = optional_string_attribute(attributes, "previous-sha256")
    if previous_sha256 is not None and not _is_sha256(previous_sha256):
        raise ValueError("Organization trust bundle previous-sha256 is invalid")
    raw_keys = attributes.get("keys")
    if not isinstance(raw_keys, list):
        raise ValueError("Organization trust bundle keys must be an array")
    keys = [_bundle_key(item, root.scope, index) for index, item in enumerate(raw_keys)]
    ids = [item.id for item in keys]
    if len(ids) != len(set(ids)):
        raise ValueError("Organization trust bundle contains duplicate key ids")
    signature = string_attribute(attributes, "signature")
    payload = organization_trust_signature_payload(
        organization=organization,
        sequence=sequence,
        generated_at=generated_at,
        previous_sha256=previous_sha256,
        keys=raw_keys,
    )
    try:
        signature_bytes = base64.b64decode(signature, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError("Organization trust bundle signature must be valid base64") from error
    public_key = Ed25519PublicKey.from_public_bytes(decode_trusted_public_key(root.public_key))
    try:
        public_key.verify(signature_bytes, payload)
    except InvalidSignature as error:
        raise ValueError("Organization trust bundle signature is invalid") from error
    checksum = organization_trust_bundle_checksum(payload, signature)
    return sequence, previous_sha256, keys, checksum, generated_at


def organization_trust_signature_payload(
    *,
    organization: str,
    sequence: int,
    generated_at: str,
    previous_sha256: str | None,
    keys: list[object],
) -> bytes:
    statement = {
        "schema": ORGANIZATION_TRUST_SIGNATURE_SCHEMA,
        "organization": organization,
        "sequence": sequence,
        "generated-at": generated_at,
        "previous-sha256": previous_sha256,
        "keys": keys,
    }
    return (
        json.dumps(statement, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()


def organization_trust_bundle_checksum(payload: bytes, signature: str) -> str:
    return hashlib.sha256(payload + signature.encode("ascii") + b"\n").hexdigest()


def render_organization_trust_bundle(
    *,
    organization: str,
    sequence: int,
    generated_at: str,
    previous_sha256: str | None,
    keys: list[dict[str, object]],
    signature: str,
) -> str:
    return render_markdown(
        MarkdownDocument(
            attributes={
                "schema": ORGANIZATION_TRUST_BUNDLE_SCHEMA,
                "organization": organization,
                "sequence": sequence,
                "generated-at": generated_at,
                "previous-sha256": previous_sha256,
                "keys": keys,
                "signature": signature,
            },
            body=(
                f"# Organization trust bundle {organization}/{sequence}\n\n"
                "This signed snapshot distributes registry release keys and revocations."
            ),
        )
    )


def load_organization_trust_root_rotation(
    contents: bytes, *, scope: str, path: str = ""
) -> OrganizationTrustRootRotationRecord:
    _assert_scope(scope)
    try:
        document = parse_markdown(contents.decode("utf-8"))
    except UnicodeDecodeError as error:
        raise ValueError("Organization trust root rotation must be UTF-8") from error
    attributes = document.attributes
    expected = {
        "schema",
        "organization",
        "rotation",
        "rotated-at",
        "reason",
        "from-public-key",
        "from-fingerprint",
        "to-public-key",
        "to-fingerprint",
        "bundle-sequence",
        "bundle-sha256",
        "previous-rotation-sha256",
        "old-signature",
        "new-signature",
    }
    if set(attributes) != expected:
        raise ValueError("Organization trust root rotation contains unsupported attributes")
    if string_attribute(attributes, "schema") != ORGANIZATION_TRUST_ROOT_ROTATION_SCHEMA:
        raise ValueError(f"Expected schema {ORGANIZATION_TRUST_ROOT_ROTATION_SCHEMA}")
    organization = string_attribute(attributes, "organization")
    assert_slug(organization, "Organization trust id")
    rotation = attributes.get("rotation")
    bundle_sequence = attributes.get("bundle-sequence")
    if not isinstance(rotation, int) or isinstance(rotation, bool) or rotation < 1:
        raise ValueError("Organization trust root rotation number must be positive")
    if (
        not isinstance(bundle_sequence, int)
        or isinstance(bundle_sequence, bool)
        or bundle_sequence < 0
    ):
        raise ValueError("Organization trust root rotation bundle sequence must be non-negative")
    rotated_at = string_attribute(attributes, "rotated-at")
    reason = string_attribute(attributes, "reason").strip()
    if not reason:
        raise ValueError("Organization trust root rotation reason cannot be empty")
    from_public_key = string_attribute(attributes, "from-public-key")
    to_public_key = string_attribute(attributes, "to-public-key")
    from_raw = decode_trusted_public_key(from_public_key)
    to_raw = decode_trusted_public_key(to_public_key)
    from_fingerprint = string_attribute(attributes, "from-fingerprint")
    to_fingerprint = string_attribute(attributes, "to-fingerprint")
    if hashlib.sha256(from_raw).hexdigest() != from_fingerprint:
        raise ValueError("Organization trust root rotation source fingerprint mismatch")
    if hashlib.sha256(to_raw).hexdigest() != to_fingerprint:
        raise ValueError("Organization trust root rotation target fingerprint mismatch")
    if from_fingerprint == to_fingerprint:
        raise ValueError("Organization trust root rotation must change the public key")
    bundle_sha256 = optional_string_attribute(attributes, "bundle-sha256")
    previous_rotation_sha256 = optional_string_attribute(attributes, "previous-rotation-sha256")
    if (bundle_sequence == 0) != (bundle_sha256 is None):
        raise ValueError("Organization trust root rotation bundle state is inconsistent")
    for name, value in (
        ("bundle-sha256", bundle_sha256),
        ("previous-rotation-sha256", previous_rotation_sha256),
    ):
        if value is not None and not _is_sha256(value):
            raise ValueError(f"Organization trust root rotation {name} is invalid")
    old_signature = string_attribute(attributes, "old-signature")
    new_signature = string_attribute(attributes, "new-signature")
    payload = organization_trust_root_rotation_payload(
        organization=organization,
        rotation=rotation,
        rotated_at=rotated_at,
        reason=reason,
        from_public_key=from_public_key,
        from_fingerprint=from_fingerprint,
        to_public_key=to_public_key,
        to_fingerprint=to_fingerprint,
        bundle_sequence=bundle_sequence,
        bundle_sha256=bundle_sha256,
        previous_rotation_sha256=previous_rotation_sha256,
    )
    for label, public_key, signature in (
        ("old", from_raw, old_signature),
        ("new", to_raw, new_signature),
    ):
        try:
            signature_bytes = base64.b64decode(signature, validate=True)
        except (binascii.Error, ValueError) as error:
            raise ValueError(
                f"Organization trust root rotation {label} signature must be valid base64"
            ) from error
        try:
            Ed25519PublicKey.from_public_bytes(public_key).verify(signature_bytes, payload)
        except InvalidSignature as error:
            raise ValueError(
                f"Organization trust root rotation {label} signature is invalid"
            ) from error
    checksum = hashlib.sha256(
        payload + old_signature.encode("ascii") + b"\n" + new_signature.encode("ascii") + b"\n"
    ).hexdigest()
    return OrganizationTrustRootRotationRecord(
        organization=organization,
        rotation=rotation,
        rotated_at=rotated_at,
        reason=reason,
        from_public_key=from_public_key,
        from_fingerprint=from_fingerprint,
        to_public_key=to_public_key,
        to_fingerprint=to_fingerprint,
        bundle_sequence=bundle_sequence,
        bundle_sha256=bundle_sha256,
        previous_rotation_sha256=previous_rotation_sha256,
        old_signature=old_signature,
        new_signature=new_signature,
        sha256=checksum,
        path=path,
    )


def organization_trust_root_rotation_payload(
    *,
    organization: str,
    rotation: int,
    rotated_at: str,
    reason: str,
    from_public_key: str,
    from_fingerprint: str,
    to_public_key: str,
    to_fingerprint: str,
    bundle_sequence: int,
    bundle_sha256: str | None,
    previous_rotation_sha256: str | None,
) -> bytes:
    statement = {
        "schema": ORGANIZATION_TRUST_ROOT_ROTATION_SIGNATURE_SCHEMA,
        "organization": organization,
        "rotation": rotation,
        "rotated-at": rotated_at,
        "reason": reason,
        "from-public-key": from_public_key,
        "from-fingerprint": from_fingerprint,
        "to-public-key": to_public_key,
        "to-fingerprint": to_fingerprint,
        "bundle-sequence": bundle_sequence,
        "bundle-sha256": bundle_sha256,
        "previous-rotation-sha256": previous_rotation_sha256,
    }
    return (
        json.dumps(statement, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()


def render_organization_trust_root_rotation(
    *,
    organization: str,
    rotation: int,
    rotated_at: str,
    reason: str,
    from_public_key: str,
    from_fingerprint: str,
    to_public_key: str,
    to_fingerprint: str,
    bundle_sequence: int,
    bundle_sha256: str | None,
    previous_rotation_sha256: str | None,
    old_signature: str,
    new_signature: str,
) -> str:
    return render_markdown(
        MarkdownDocument(
            attributes={
                "schema": ORGANIZATION_TRUST_ROOT_ROTATION_SCHEMA,
                "organization": organization,
                "rotation": rotation,
                "rotated-at": rotated_at,
                "reason": reason,
                "from-public-key": from_public_key,
                "from-fingerprint": from_fingerprint,
                "to-public-key": to_public_key,
                "to-fingerprint": to_fingerprint,
                "bundle-sequence": bundle_sequence,
                "bundle-sha256": bundle_sha256,
                "previous-rotation-sha256": previous_rotation_sha256,
                "old-signature": old_signature,
                "new-signature": new_signature,
            },
            body=(
                f"# Organization trust root rotation {organization}/{rotation}\n\n"
                "Both the outgoing and incoming public roots sign this transition."
            ),
        )
    )


def read_organization_trust_source(source: str, *, allow_insecure_http: bool) -> tuple[bytes, str]:
    parsed = urlparse(source)
    if parsed.scheme in {"http", "https"}:
        if parsed.scheme == "http" and not allow_insecure_http:
            raise PermissionError("HTTP organization trust sources require --allow-insecure-http")
        request = Request(source, headers={"User-Agent": "agora-framework/0.2"})
        try:
            with urlopen(request, timeout=DOWNLOAD_TIMEOUT) as response:
                resolved = response.geturl()
                resolved_scheme = urlparse(resolved).scheme
                if resolved_scheme == "http" and not allow_insecure_http:
                    raise PermissionError(
                        "HTTP organization trust sources require --allow-insecure-http"
                    )
                if resolved_scheme not in {"http", "https"}:
                    raise ValueError("Remote organization trust source must use HTTPS")
                declared = response.headers.get("Content-Length")
                if declared is not None and int(declared) > MAXIMUM_BUNDLE_BYTES:
                    raise ValueError("Organization trust document exceeds maximum size")
                data = response.read(MAXIMUM_BUNDLE_BYTES + 1)
                if len(data) > MAXIMUM_BUNDLE_BYTES:
                    raise ValueError("Organization trust document exceeds maximum size")
                return data, resolved
        except (HTTPError, URLError) as error:
            raise RuntimeError(
                f"Could not download organization trust document: {error}"
            ) from error
    if parsed.scheme == "file":
        path = Path(unquote(parsed.path)).resolve()
    elif not parsed.scheme:
        path = Path(source).expanduser().resolve()
    else:
        raise ValueError(f"Unsupported organization trust source scheme: {parsed.scheme}")
    if not path.is_file():
        raise FileNotFoundError(f"Organization trust document not found: {path}")
    if path.stat().st_size > MAXIMUM_BUNDLE_BYTES:
        raise ValueError("Organization trust document exceeds maximum size")
    return path.read_bytes(), path.as_uri()


def advance_organization_trust_root(
    root: OrganizationTrustRootRecord, *, source: str, sequence: int, checksum: str
) -> OrganizationTrustRootRecord:
    return replace(root, source=source, last_sequence=sequence, last_sha256=checksum)


def _bundle_key(item: object, scope: str, index: int) -> RegistryTrustKeyRecord:
    if not isinstance(item, dict) or any(not isinstance(key, str) for key in item):
        raise ValueError(f"Organization trust bundle key {index} must be an object")
    expected_attributes = {
        "id",
        "registry",
        "algorithm",
        "public-key",
        "fingerprint",
        "status",
        "created-at",
        "revoked-at",
        "revoked-reason",
        "replaced-by",
    }
    if set(item) != expected_attributes:
        raise ValueError(f"Organization trust bundle key {index} has unsupported attributes")

    def required(name: str) -> str:
        value = item.get(name)
        if not isinstance(value, str) or not value:
            raise ValueError(f"Organization trust bundle key {index} requires {name}")
        return value

    def optional(name: str) -> str | None:
        value = item.get(name)
        if value is not None and (not isinstance(value, str) or not value):
            raise ValueError(
                f"Organization trust bundle key {index} {name} must be a string or null"
            )
        return value

    id_ = required("id")
    registry = required("registry")
    assert_slug(id_, "Registry trust key id")
    assert_slug(registry, "Registry trust key registry")
    if required("algorithm") != "ed25519":
        raise ValueError(f"Organization trust bundle key {id_} algorithm must be ed25519")
    public_key = required("public-key")
    raw = decode_trusted_public_key(public_key)
    fingerprint = required("fingerprint")
    if hashlib.sha256(raw).hexdigest() != fingerprint:
        raise ValueError(f"Organization trust bundle key {id_} fingerprint mismatch")
    status = required("status")
    if status not in {"active", "revoked"}:
        raise ValueError(f"Organization trust bundle key {id_} has unsupported status")
    revoked_at = optional("revoked-at")
    revoked_reason = optional("revoked-reason")
    replaced_by = optional("replaced-by")
    if replaced_by is not None:
        assert_slug(replaced_by, "Replacement registry trust key id")
        if replaced_by == id_:
            raise ValueError(f"Organization trust bundle key {id_} cannot replace itself")
    if status == "active" and any(
        value is not None for value in (revoked_at, revoked_reason, replaced_by)
    ):
        raise ValueError(f"Active organization trust key {id_} has revocation fields")
    if status == "revoked" and (revoked_at is None or revoked_reason is None):
        raise ValueError(f"Revoked organization trust key {id_} requires date and reason")
    return RegistryTrustKeyRecord(
        id=id_,
        registry=registry,
        algorithm="ed25519",
        public_key=public_key,
        fingerprint=fingerprint,
        status=status,  # type: ignore[arg-type]
        scope=scope,  # type: ignore[arg-type]
        path="",
        created_at=required("created-at"),
        revoked_at=revoked_at,
        revoked_reason=revoked_reason,
        replaced_by=replaced_by,
    )


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _assert_scope(scope: str) -> None:
    if scope not in {"user", "project"}:
        raise ValueError(f"Unsupported organization trust scope: {scope}")
