import hashlib
import re
from pathlib import Path
from typing import Any

from agora.filesystem import assert_slug
from agora.markdown import (
    MarkdownDocument,
    optional_string_attribute,
    read_markdown,
    render_markdown,
    string_attribute,
)
from agora.model import PackDependency, PackKind, PackSourceRecord

PACK_KINDS: tuple[PackKind, ...] = ("method", "tool")
PACK_VERSION_PATTERN = re.compile(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)")
CONSTRAINT_PATTERN = re.compile(
    r"(==|=|>=|<=|>|<)?((?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*))"
)
PACK_SOURCE_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


def validate_pack_version(value: str) -> str:
    if not PACK_VERSION_PATTERN.fullmatch(value):
        raise ValueError(f"Pack version must use MAJOR.MINOR.PATCH: {value}")
    return value


def compare_pack_versions(left: str, right: str) -> int:
    left_parts = _version_parts(left)
    right_parts = _version_parts(right)
    return (left_parts > right_parts) - (left_parts < right_parts)


def validate_version_constraint(value: str) -> str:
    if value == "*":
        return value
    clauses = value.split(",")
    if not clauses or any(
        not clause or not CONSTRAINT_PATTERN.fullmatch(clause) for clause in clauses
    ):
        raise ValueError(
            "Pack dependency version must be '*' or comma-separated MAJOR.MINOR.PATCH "
            f"comparators: {value}"
        )
    return value


def version_satisfies(version: str, constraint: str) -> bool:
    validate_pack_version(version)
    validate_version_constraint(constraint)
    if constraint == "*":
        return True
    for clause in constraint.split(","):
        match = CONSTRAINT_PATTERN.fullmatch(clause)
        assert match is not None
        operator, required = match.groups()
        relation = compare_pack_versions(version, required)
        if operator in (None, "=", "==") and relation != 0:
            return False
        if operator == ">=" and relation < 0:
            return False
        if operator == "<=" and relation > 0:
            return False
        if operator == ">" and relation <= 0:
            return False
        if operator == "<" and relation >= 0:
            return False
    return True


def pack_manifest_metadata(
    attributes: dict[str, Any], owner: str
) -> tuple[str, list[PackDependency]]:
    raw_version = attributes.get("version", "0.0.0")
    if not isinstance(raw_version, str):
        raise ValueError(f"Pack {owner} version must be a string")
    version = validate_pack_version(raw_version)
    raw_dependencies = attributes.get("dependencies", [])
    if not isinstance(raw_dependencies, list):
        raise ValueError(f"Pack {owner} dependencies must be an array")
    dependencies: list[PackDependency] = []
    seen: set[tuple[str, str]] = set()
    for raw in raw_dependencies:
        if not isinstance(raw, dict) or set(raw) != {"kind", "id", "version"}:
            raise ValueError(f"Pack {owner} dependencies must contain only kind, id, and version")
        kind = raw["kind"]
        id_ = raw["id"]
        constraint = raw["version"]
        if kind not in PACK_KINDS:
            raise ValueError(f"Pack {owner} dependency kind is unsupported: {kind}")
        if not isinstance(id_, str):
            raise ValueError(f"Pack {owner} dependency id must be a string")
        assert_slug(id_, f"Pack {owner} dependency id")
        if not isinstance(constraint, str):
            raise ValueError(f"Pack {owner} dependency version must be a string")
        validate_version_constraint(constraint)
        key = (kind, id_)
        if key in seen:
            raise ValueError(f"Pack {owner} has duplicate dependency: {kind}/{id_}")
        seen.add(key)
        dependencies.append(PackDependency(kind=kind, id=id_, version=constraint))
    return version, dependencies


def pack_reference(kind: str, id_: str, version: str) -> str:
    return f"{kind}/{id_}@{version}"


def pack_tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root)
        if relative.parts[0] in {"SOURCE.md", "updates"}:
            continue
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def read_pack_source(path: Path) -> PackSourceRecord:
    document = read_markdown(path)
    attributes = document.attributes
    if string_attribute(attributes, "schema") != "agora/pack-source/v1":
        raise ValueError(f"Expected schema agora/pack-source/v1: {path}")
    kind = string_attribute(attributes, "kind")
    if kind not in PACK_KINDS:
        raise ValueError(f"Pack source kind is unsupported: {kind}")
    id_ = string_attribute(attributes, "id")
    assert_slug(id_, "Pack source id")
    version = validate_pack_version(string_attribute(attributes, "version"))
    registry = string_attribute(attributes, "registry")
    assert_slug(registry, "Pack source registry")
    registry_scope = string_attribute(attributes, "registry-scope")
    if registry_scope not in {"bundled", "user", "project"}:
        raise ValueError(f"Pack source registry scope is unsupported: {registry_scope}")
    registry_version = optional_string_attribute(attributes, "registry-version")
    if registry_version is not None:
        validate_pack_version(registry_version)
    registry_source = optional_string_attribute(attributes, "registry-source")
    sha256 = string_attribute(attributes, "sha256")
    if not PACK_SOURCE_SHA256_PATTERN.fullmatch(sha256):
        raise ValueError(f"Pack source sha256 must be 64 lowercase hex characters: {path}")
    installed_at = string_attribute(attributes, "installed-at")
    return PackSourceRecord(
        kind=kind,
        id=id_,
        version=version,
        registry=registry,
        registry_scope=registry_scope,
        registry_version=registry_version,
        registry_source=registry_source,
        sha256=sha256,
        installed_at=installed_at,
        path=str(path),
    )


def render_pack_source(record: PackSourceRecord) -> str:
    return render_markdown(
        MarkdownDocument(
            attributes={
                "schema": "agora/pack-source/v1",
                "kind": record.kind,
                "id": record.id,
                "version": record.version,
                "registry": record.registry,
                "registry-scope": record.registry_scope,
                "registry-version": record.registry_version,
                "registry-source": record.registry_source,
                "sha256": record.sha256,
                "installed-at": record.installed_at,
            },
            body=(
                f"# Pack source for {record.kind}/{record.id}\n\n"
                "Agora generated this record when it installed the catalog pack."
            ),
        )
    )


def _version_parts(value: str) -> tuple[int, int, int]:
    validate_pack_version(value)
    major, minor, patch = value.split(".")
    return int(major), int(minor), int(patch)
