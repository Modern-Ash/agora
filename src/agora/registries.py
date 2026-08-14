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
from agora.model import CatalogPackRecord, RegistryRecord, RegistrySourceRecord
from agora.registry_distribution import SHA256_PATTERN, validate_registry_version
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
