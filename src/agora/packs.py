import re
from typing import Any

from agora.filesystem import assert_slug
from agora.model import PackDependency, PackKind

PACK_KINDS: tuple[PackKind, ...] = ("method", "tool")
PACK_VERSION_PATTERN = re.compile(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)")
CONSTRAINT_PATTERN = re.compile(
    r"(==|=|>=|<=|>|<)?((?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*))"
)


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


def _version_parts(value: str) -> tuple[int, int, int]:
    validate_pack_version(value)
    major, minor, patch = value.split(".")
    return int(major), int(minor), int(patch)
