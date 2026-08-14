from pathlib import Path

from agora.filesystem import assert_slug, template_root
from agora.markdown import read_markdown, string_attribute
from agora.methods import load_method_contract
from agora.model import CatalogPackRecord, RegistryRecord
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
    if scope not in REGISTRY_SCOPES:
        raise ValueError(f"Unsupported registry scope: {scope}")
    return _registry_record(id_=id_, name=name, scope=scope, root=root)


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
    )


def _pack_directories(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(path for path in root.iterdir() if path.is_dir())
