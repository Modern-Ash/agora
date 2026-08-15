from pathlib import Path

from agora.filesystem import assert_slug, template_root
from agora.markdown import (
    MarkdownDocument,
    optional_string_attribute,
    read_markdown,
    render_markdown,
    string_attribute,
)
from agora.methods import load_method_contract
from agora.model import (
    CatalogPackRecord,
    RegistryRecord,
    RegistrySourceRecord,
    RegistryUpdateAuditEntry,
    RegistryUpdateAuditRecord,
    RegistryUpdateRecord,
)
from agora.registry_distribution import (
    SHA256_PATTERN,
    compare_registry_versions,
    validate_registry_version,
)
from agora.tools import load_tool_contract

REGISTRY_SCOPES = ("project", "user", "bundled")


def bundled_registry() -> RegistryRecord:
    root = template_root()
    return _registry_record(
        id_="agora-bundled",
        name="Agora bundled packs",
        scope="bundled",
        root=root,
    )


def load_registry(root: Path, scope: str) -> RegistryRecord:
    path = root / "REGISTRY.md"
    document = read_markdown(path)
    attributes = document.attributes
    if string_attribute(attributes, "schema") != "agora/registry/v1":
        raise ValueError(f"Registry schema must be agora/registry/v1: {path}")
    id_ = string_attribute(attributes, "id")
    assert_slug(id_, "Registry id")
    name = string_attribute(attributes, "name")
    version = optional_string_attribute(attributes, "version")
    if version is not None:
        validate_registry_version(version)
    if scope not in REGISTRY_SCOPES:
        raise ValueError(f"Unsupported registry scope: {scope}")
    provenance = (
        read_registry_source(root / "SOURCE.md") if (root / "SOURCE.md").is_file() else None
    )
    if provenance is not None:
        if provenance.registry != id_:
            raise ValueError(f"Registry source id does not match REGISTRY.md: {root}")
        if version != provenance.version:
            raise ValueError(f"Registry source version does not match REGISTRY.md: {root}")
    updates: list[RegistryUpdateRecord] = []
    for directory in _pack_directories(root / "updates"):
        update = read_registry_update(directory / "UPDATE.md")
        if update.id != directory.name:
            raise ValueError(
                f"Registry update id {update.id} does not match directory {directory.name}"
            )
        if update.registry != id_:
            raise ValueError(f"Registry update belongs to another registry: {directory}")
        updates.append(update)
    for previous, current in zip(updates, updates[1:], strict=False):
        if previous.to_version != current.from_version:
            raise ValueError(f"Registry update version history is discontinuous: {current.path}")
        if previous.to_sha256 != current.from_sha256:
            raise ValueError(f"Registry update checksum history is discontinuous: {current.path}")
    if updates:
        if provenance is None or version is None:
            raise ValueError(f"Registry update history requires remote provenance: {root}")
        latest = updates[-1]
        if latest.to_version != version or latest.to_sha256 != provenance.sha256:
            raise ValueError(f"Registry update history does not match current provenance: {root}")
    return _registry_record(
        id_=id_,
        name=name,
        scope=scope,
        root=root,
        version=version,
        provenance=provenance,
    )


def read_registry_source(path: Path) -> RegistrySourceRecord:
    document = read_markdown(path)
    attributes = document.attributes
    if string_attribute(attributes, "schema") != "agora/registry-source/v1":
        raise ValueError(f"Expected schema agora/registry-source/v1: {path}")
    registry = string_attribute(attributes, "registry")
    assert_slug(registry, "Registry source id")
    version = validate_registry_version(string_attribute(attributes, "version"))
    index = string_attribute(attributes, "index")
    archive = string_attribute(attributes, "archive")
    sha256 = string_attribute(attributes, "sha256")
    if not SHA256_PATTERN.fullmatch(sha256):
        raise ValueError(f"Registry source sha256 must be 64 lowercase hex characters: {path}")
    verified = attributes.get("signature-verified")
    if not isinstance(verified, bool):
        raise ValueError(f"Registry source signature-verified must be boolean: {path}")
    key_id = optional_string_attribute(attributes, "key-id")
    if verified and key_id is None:
        raise ValueError(f"Verified registry source requires key-id: {path}")
    if key_id is not None:
        assert_slug(key_id, "Registry source key id")
    installed_at = string_attribute(attributes, "installed-at")
    return RegistrySourceRecord(
        registry=registry,
        version=version,
        index=index,
        archive=archive,
        sha256=sha256,
        signature_verified=verified,
        key_id=key_id,
        installed_at=installed_at,
    )


def render_registry_source(record: RegistrySourceRecord) -> str:
    return render_markdown(
        MarkdownDocument(
            attributes={
                "schema": "agora/registry-source/v1",
                "registry": record.registry,
                "version": record.version,
                "index": record.index,
                "archive": record.archive,
                "sha256": record.sha256,
                "signature-verified": record.signature_verified,
                "key-id": record.key_id,
                "installed-at": record.installed_at,
            },
            body=(
                f"# Registry source for {record.registry}\n\n"
                "Agora generated this provenance record after verifying and installing the "
                "selected registry release."
            ),
        )
    )


def read_registry_update(path: Path) -> RegistryUpdateRecord:
    document = read_markdown(path)
    attributes = document.attributes
    if string_attribute(attributes, "schema") != "agora/registry-update/v1":
        raise ValueError(f"Expected schema agora/registry-update/v1: {path}")
    id_ = string_attribute(attributes, "id")
    assert_slug(id_, "Registry update id")
    registry = string_attribute(attributes, "registry")
    assert_slug(registry, "Registry update registry")
    from_version = validate_registry_version(string_attribute(attributes, "from-version"))
    to_version = validate_registry_version(string_attribute(attributes, "to-version"))
    if compare_registry_versions(from_version, to_version) >= 0:
        raise ValueError(f"Registry update must move to a newer version: {path}")
    from_sha256 = string_attribute(attributes, "from-sha256")
    to_sha256 = string_attribute(attributes, "to-sha256")
    if not SHA256_PATTERN.fullmatch(from_sha256) or not SHA256_PATTERN.fullmatch(to_sha256):
        raise ValueError(f"Registry update checksums must be lowercase SHA-256 values: {path}")
    index = string_attribute(attributes, "index")
    signature_verified = attributes.get("signature-verified")
    if not isinstance(signature_verified, bool):
        raise ValueError(f"Registry update signature-verified must be boolean: {path}")
    applied_at = string_attribute(attributes, "applied-at")
    return RegistryUpdateRecord(
        id=id_,
        registry=registry,
        from_version=from_version,
        to_version=to_version,
        from_sha256=from_sha256,
        to_sha256=to_sha256,
        index=index,
        signature_verified=signature_verified,
        applied_at=applied_at,
        path=str(path),
    )


def render_registry_update(record: RegistryUpdateRecord) -> str:
    return render_markdown(
        MarkdownDocument(
            attributes={
                "schema": "agora/registry-update/v1",
                "id": record.id,
                "registry": record.registry,
                "from-version": record.from_version,
                "to-version": record.to_version,
                "from-sha256": record.from_sha256,
                "to-sha256": record.to_sha256,
                "index": record.index,
                "signature-verified": record.signature_verified,
                "applied-at": record.applied_at,
            },
            body=(
                f"# Registry update {record.id}\n\n"
                f"Agora updated `{record.registry}` from {record.from_version} to "
                f"{record.to_version} after release verification."
            ),
        )
    )


def read_registry_update_audit(path: Path) -> RegistryUpdateAuditRecord:
    document = read_markdown(path)
    attributes = document.attributes
    if string_attribute(attributes, "schema") != "agora/registry-update-audit/v1":
        raise ValueError(f"Expected schema agora/registry-update-audit/v1: {path}")
    id_ = string_attribute(attributes, "id")
    assert_slug(id_, "Registry update audit id")
    scope = string_attribute(attributes, "scope")
    if scope not in {"user", "project"}:
        raise ValueError(f"Unsupported registry update audit scope: {path}")
    raw_entries = attributes.get("entries")
    if not isinstance(raw_entries, list):
        raise ValueError(f"Registry update audit entries must be an array: {path}")
    entries: list[RegistryUpdateAuditEntry] = []
    for index, item in enumerate(raw_entries):
        if not isinstance(item, dict) or set(item) != {
            "registry",
            "scope",
            "from-version",
            "to-version",
            "update-available",
            "signature-verified",
        }:
            raise ValueError(f"Registry update audit entry {index} is invalid: {path}")
        registry = item.get("registry")
        entry_scope = item.get("scope")
        from_version = item.get("from-version")
        to_version = item.get("to-version")
        update_available = item.get("update-available")
        signature_verified = item.get("signature-verified")
        if not isinstance(registry, str):
            raise ValueError(f"Registry update audit entry {index} registry is invalid: {path}")
        assert_slug(registry, "Registry update audit registry")
        if entry_scope != scope:
            raise ValueError(f"Registry update audit entry {index} scope is invalid: {path}")
        if not isinstance(from_version, str) or not isinstance(to_version, str):
            raise ValueError(f"Registry update audit entry {index} versions are invalid: {path}")
        validate_registry_version(from_version)
        validate_registry_version(to_version)
        if not isinstance(update_available, bool) or not isinstance(signature_verified, bool):
            raise ValueError(f"Registry update audit entry {index} flags are invalid: {path}")
        relation = compare_registry_versions(to_version, from_version)
        if (relation > 0) != update_available or relation < 0:
            raise ValueError(f"Registry update audit entry {index} relation is invalid: {path}")
        entries.append(
            RegistryUpdateAuditEntry(
                registry=registry,
                scope=scope,  # type: ignore[arg-type]
                from_version=from_version,
                to_version=to_version,
                update_available=update_available,
                signature_verified=signature_verified,
            )
        )
    return RegistryUpdateAuditRecord(
        id=id_,
        scope=scope,  # type: ignore[arg-type]
        checked_at=string_attribute(attributes, "checked-at"),
        entries=entries,
        path=str(path),
    )


def render_registry_update_audit(record: RegistryUpdateAuditRecord) -> str:
    updates = sum(item.update_available for item in record.entries)
    return render_markdown(
        MarkdownDocument(
            attributes={
                "schema": "agora/registry-update-audit/v1",
                "id": record.id,
                "scope": record.scope,
                "checked-at": record.checked_at,
                "entries": [
                    {
                        "registry": item.registry,
                        "scope": item.scope,
                        "from-version": item.from_version,
                        "to-version": item.to_version,
                        "update-available": item.update_available,
                        "signature-verified": item.signature_verified,
                    }
                    for item in record.entries
                ],
            },
            body=(
                f"# Registry update audit {record.id}\n\n"
                f"Checked {len(record.entries)} remote registries and found {updates} updates."
            ),
        )
    )


def discover_registry_packs(registry: RegistryRecord) -> list[CatalogPackRecord]:
    root = Path(registry.path)
    records: list[CatalogPackRecord] = []
    for method_id in registry.methods:
        contract = load_method_contract(root / "methods" / method_id)
        records.append(
            CatalogPackRecord(
                kind="method",
                id=contract.id,
                name=contract.name,
                version=contract.version,
                dependencies=contract.dependencies,
                registry=registry.id,
                registry_scope=registry.scope,
                path=str(root / "methods" / method_id),
                installed=False,
            )
        )
    for tool_id in registry.tools:
        contract = load_tool_contract(root / "tools" / tool_id)
        records.append(
            CatalogPackRecord(
                kind="tool",
                id=contract.id,
                name=contract.name,
                version=contract.version,
                dependencies=contract.dependencies,
                registry=registry.id,
                registry_scope=registry.scope,
                path=str(root / "tools" / tool_id),
                installed=False,
            )
        )
    return records


def _registry_record(
    *,
    id_: str,
    name: str,
    scope: str,
    root: Path,
    version: str | None = None,
    provenance: RegistrySourceRecord | None = None,
) -> RegistryRecord:
    method_ids: list[str] = []
    for directory in _pack_directories(root / "methods"):
        path = directory / "METHOD.md"
        if not path.is_file():
            raise FileNotFoundError(f"Registry Method Pack is missing METHOD.md: {directory}")
        if (directory / "SOURCE.md").exists() or (directory / "updates").exists():
            raise ValueError(
                f"Registry packs must not contain installer-owned metadata: {directory}"
            )
        contract = load_method_contract(directory)
        if contract.id != directory.name:
            raise ValueError(
                f"Method id {contract.id} does not match registry directory {directory.name}"
            )
        method_ids.append(contract.id)
    tool_ids: list[str] = []
    for directory in _pack_directories(root / "tools"):
        path = directory / "TOOL.md"
        if not path.is_file():
            raise FileNotFoundError(f"Registry Tool Pack is missing TOOL.md: {directory}")
        if (directory / "SOURCE.md").exists() or (directory / "updates").exists():
            raise ValueError(
                f"Registry packs must not contain installer-owned metadata: {directory}"
            )
        contract = load_tool_contract(directory)
        if contract.id != directory.name:
            raise ValueError(
                f"Tool id {contract.id} does not match registry directory {directory.name}"
            )
        tool_ids.append(contract.id)
    if not method_ids and not tool_ids:
        raise ValueError(f"Registry must contain at least one Method Pack or Tool Pack: {root}")
    return RegistryRecord(
        id=id_,
        name=name,
        scope=scope,  # type: ignore[arg-type]
        path=str(root),
        methods=method_ids,
        tools=tool_ids,
        version=version,
        source=provenance.index if provenance else None,
        checksum=provenance.sha256 if provenance else None,
        signature_verified=provenance.signature_verified if provenance else False,
    )


def _pack_directories(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(path for path in root.iterdir() if path.is_dir())
