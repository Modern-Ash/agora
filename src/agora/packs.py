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
from agora.model import (
    PackDependency,
    PackKind,
    PackLockEntry,
    PackLockRecord,
    PackRemovalRecord,
    PackRemovalStep,
    PackSourceRecord,
    PackUpdateAuditEntry,
    PackUpdateAuditRecord,
    PackUpdateHistoryRecord,
)

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


def read_pack_update(path: Path) -> PackUpdateHistoryRecord:
    document = read_markdown(path)
    attributes = document.attributes
    if string_attribute(attributes, "schema") != "agora/pack-update/v1":
        raise ValueError(f"Expected schema agora/pack-update/v1: {path}")
    id_ = string_attribute(attributes, "id")
    assert_slug(id_, "Pack update id")
    kind = string_attribute(attributes, "kind")
    if kind not in PACK_KINDS:
        raise ValueError(f"Pack update kind is unsupported: {kind}")
    pack_id = string_attribute(attributes, "pack")
    assert_slug(pack_id, "Pack update pack id")
    from_version = optional_string_attribute(attributes, "from-version")
    from_sha256 = optional_string_attribute(attributes, "from-sha256")
    if (from_version is None) != (from_sha256 is None):
        raise ValueError(f"Pack update from-version and from-sha256 must appear together: {path}")
    if from_version is not None:
        validate_pack_version(from_version)
        assert from_sha256 is not None
        if not PACK_SOURCE_SHA256_PATTERN.fullmatch(from_sha256):
            raise ValueError(f"Pack update from-sha256 is invalid: {path}")
    to_version = validate_pack_version(string_attribute(attributes, "to-version"))
    if from_version is not None and compare_pack_versions(from_version, to_version) > 0:
        raise ValueError(f"Pack update cannot move to an older version: {path}")
    to_sha256 = string_attribute(attributes, "to-sha256")
    if not PACK_SOURCE_SHA256_PATTERN.fullmatch(to_sha256):
        raise ValueError(f"Pack update to-sha256 is invalid: {path}")
    registry = string_attribute(attributes, "registry")
    assert_slug(registry, "Pack update registry")
    registry_scope = string_attribute(attributes, "registry-scope")
    if registry_scope not in {"bundled", "user", "project"}:
        raise ValueError(f"Pack update registry scope is unsupported: {registry_scope}")
    return PackUpdateHistoryRecord(
        id=id_,
        kind=kind,
        pack_id=pack_id,
        from_version=from_version,
        to_version=to_version,
        from_sha256=from_sha256,
        to_sha256=to_sha256,
        registry=registry,
        registry_scope=registry_scope,
        applied_at=string_attribute(attributes, "applied-at"),
        path=str(path),
    )


def render_pack_update(record: PackUpdateHistoryRecord) -> str:
    return render_markdown(
        MarkdownDocument(
            attributes={
                "schema": "agora/pack-update/v1",
                "id": record.id,
                "kind": record.kind,
                "pack": record.pack_id,
                "from-version": record.from_version,
                "to-version": record.to_version,
                "from-sha256": record.from_sha256,
                "to-sha256": record.to_sha256,
                "registry": record.registry,
                "registry-scope": record.registry_scope,
                "applied-at": record.applied_at,
            },
            body=(
                f"# Pack update {record.id}\n\n"
                f"Agora applied {record.kind}/{record.pack_id}@{record.to_version} from "
                f"registry `{record.registry}`."
            ),
        )
    )


def load_pack_update_history(root: Path, kind: PackKind, id_: str) -> list[PackUpdateHistoryRecord]:
    update_root = root / "updates"
    directories = sorted(path for path in update_root.glob("*") if path.is_dir())
    records: list[PackUpdateHistoryRecord] = []
    for directory in directories:
        record = read_pack_update(directory / "UPDATE.md")
        if record.id != directory.name:
            raise ValueError(f"Pack update id does not match its directory: {directory}")
        if record.kind != kind or record.pack_id != id_:
            raise ValueError(f"Pack update belongs to another pack: {directory}")
        records.append(record)
    for previous, current in zip(records, records[1:], strict=False):
        if current.from_version != previous.to_version:
            raise ValueError(f"Pack update version history is discontinuous: {current.path}")
        if current.from_sha256 != previous.to_sha256:
            raise ValueError(f"Pack update checksum history is discontinuous: {current.path}")
    return records


def read_pack_lock(path: Path) -> PackLockRecord:
    document = read_markdown(path)
    attributes = document.attributes
    if string_attribute(attributes, "schema") != "agora/pack-lock/v1":
        raise ValueError(f"Expected schema agora/pack-lock/v1: {path}")
    scope = string_attribute(attributes, "scope")
    if scope not in {"user", "project"}:
        raise ValueError(f"Pack lock scope is unsupported: {scope}")
    raw_packs = attributes.get("packs")
    if not isinstance(raw_packs, list):
        raise ValueError(f"Pack lock packs must be an array: {path}")
    packs: list[PackLockEntry] = []
    seen: set[tuple[str, str]] = set()
    for raw in raw_packs:
        expected = {"kind", "id", "version", "sha256", "registry", "source-sha256"}
        if not isinstance(raw, dict) or set(raw) != expected:
            raise ValueError(f"Pack lock entries have an invalid shape: {path}")
        kind = raw["kind"]
        id_ = raw["id"]
        version = raw["version"]
        sha256 = raw["sha256"]
        registry = raw["registry"]
        source_sha256 = raw["source-sha256"]
        if kind not in PACK_KINDS or not isinstance(id_, str):
            raise ValueError(f"Pack lock kind or id is invalid: {path}")
        assert_slug(id_, "Pack lock pack id")
        if not isinstance(version, str):
            raise ValueError(f"Pack lock version is invalid: {path}")
        validate_pack_version(version)
        if not isinstance(sha256, str) or not PACK_SOURCE_SHA256_PATTERN.fullmatch(sha256):
            raise ValueError(f"Pack lock sha256 is invalid: {path}")
        if registry is not None and not isinstance(registry, str):
            raise ValueError(f"Pack lock registry is invalid: {path}")
        if isinstance(registry, str):
            assert_slug(registry, "Pack lock registry")
        if source_sha256 is not None and (
            not isinstance(source_sha256, str)
            or not PACK_SOURCE_SHA256_PATTERN.fullmatch(source_sha256)
        ):
            raise ValueError(f"Pack lock source-sha256 is invalid: {path}")
        key = (kind, id_)
        if key in seen:
            raise ValueError(f"Pack lock contains a duplicate pack: {kind}/{id_}")
        seen.add(key)
        packs.append(
            PackLockEntry(
                kind=kind,
                id=id_,
                version=version,
                sha256=sha256,
                registry=registry,
                source_sha256=source_sha256,
            )
        )
    if [(item.kind, item.id) for item in packs] != sorted((item.kind, item.id) for item in packs):
        raise ValueError(f"Pack lock entries must be sorted by kind and id: {path}")
    return PackLockRecord(
        scope=scope,
        generated_at=string_attribute(attributes, "generated-at"),
        packs=packs,
        path=str(path),
    )


def render_pack_lock(record: PackLockRecord) -> str:
    return render_markdown(
        MarkdownDocument(
            attributes={
                "schema": "agora/pack-lock/v1",
                "scope": record.scope,
                "generated-at": record.generated_at,
                "packs": [
                    {
                        "kind": item.kind,
                        "id": item.id,
                        "version": item.version,
                        "sha256": item.sha256,
                        "registry": item.registry,
                        "source-sha256": item.source_sha256,
                    }
                    for item in record.packs
                ],
            },
            body=(
                f"# {record.scope.title()} pack composition lock\n\n"
                "Agora generated this deterministic inventory from the installed pack trees."
            ),
        )
    )


def read_pack_removal(path: Path) -> PackRemovalRecord:
    document = read_markdown(path)
    attributes = document.attributes
    if string_attribute(attributes, "schema") != "agora/pack-removal/v1":
        raise ValueError(f"Expected schema agora/pack-removal/v1: {path}")
    id_ = string_attribute(attributes, "id")
    assert_slug(id_, "Pack removal id")
    scope = string_attribute(attributes, "scope")
    if scope not in {"user", "project"}:
        raise ValueError(f"Pack removal scope is unsupported: {scope}")
    requested_kind = string_attribute(attributes, "requested-kind")
    if requested_kind not in PACK_KINDS:
        raise ValueError(f"Pack removal requested kind is unsupported: {requested_kind}")
    requested_id = string_attribute(attributes, "requested-id")
    assert_slug(requested_id, "Pack removal requested id")
    raw_packs = attributes.get("packs")
    if not isinstance(raw_packs, list) or not raw_packs:
        raise ValueError(f"Pack removal packs must be a non-empty array: {path}")
    packs: list[PackRemovalStep] = []
    seen: set[tuple[str, str]] = set()
    for raw in raw_packs:
        expected = {"kind", "id", "version", "sha256", "registry", "reason"}
        if not isinstance(raw, dict) or set(raw) != expected:
            raise ValueError(f"Pack removal entries have an invalid shape: {path}")
        kind = raw["kind"]
        pack_id = raw["id"]
        version = raw["version"]
        sha256 = raw["sha256"]
        registry = raw["registry"]
        reason = raw["reason"]
        if kind not in PACK_KINDS or not isinstance(pack_id, str):
            raise ValueError(f"Pack removal kind or id is invalid: {path}")
        assert_slug(pack_id, "Removed pack id")
        if not isinstance(version, str):
            raise ValueError(f"Removed pack version is invalid: {path}")
        validate_pack_version(version)
        if not isinstance(sha256, str) or not PACK_SOURCE_SHA256_PATTERN.fullmatch(sha256):
            raise ValueError(f"Removed pack sha256 is invalid: {path}")
        if registry is not None and not isinstance(registry, str):
            raise ValueError(f"Removed pack registry is invalid: {path}")
        if isinstance(registry, str):
            assert_slug(registry, "Removed pack registry")
        if reason not in {"requested", "unused-dependency"}:
            raise ValueError(f"Removed pack reason is invalid: {path}")
        key = (kind, pack_id)
        if key in seen:
            raise ValueError(f"Pack removal contains a duplicate pack: {kind}/{pack_id}")
        seen.add(key)
        packs.append(
            PackRemovalStep(
                kind=kind,
                id=pack_id,
                version=version,
                sha256=sha256,
                registry=registry,
                reason=reason,
            )
        )
    requested = [item for item in packs if item.reason == "requested"]
    if (
        len(requested) != 1
        or requested[0].kind != requested_kind
        or requested[0].id != requested_id
        or packs[0] != requested[0]
    ):
        raise ValueError(f"Pack removal does not include its requested pack: {path}")
    return PackRemovalRecord(
        id=id_,
        scope=scope,
        requested_kind=requested_kind,
        requested_id=requested_id,
        removed_at=string_attribute(attributes, "removed-at"),
        packs=packs,
        path=str(path),
    )


def render_pack_removal(record: PackRemovalRecord) -> str:
    return render_markdown(
        MarkdownDocument(
            attributes={
                "schema": "agora/pack-removal/v1",
                "id": record.id,
                "scope": record.scope,
                "requested-kind": record.requested_kind,
                "requested-id": record.requested_id,
                "removed-at": record.removed_at,
                "packs": [
                    {
                        "kind": item.kind,
                        "id": item.id,
                        "version": item.version,
                        "sha256": item.sha256,
                        "registry": item.registry,
                        "reason": item.reason,
                    }
                    for item in record.packs
                ],
            },
            body=(
                f"# Pack removal {record.id}\n\n"
                "This installer-owned record preserves the composition change after the pack "
                "directories are removed."
            ),
        )
    )


def read_pack_update_audit(path: Path) -> PackUpdateAuditRecord:
    document = read_markdown(path)
    attributes = document.attributes
    if string_attribute(attributes, "schema") != "agora/pack-update-audit/v1":
        raise ValueError(f"Expected schema agora/pack-update-audit/v1: {path}")
    id_ = string_attribute(attributes, "id")
    assert_slug(id_, "Pack update audit id")
    scope = string_attribute(attributes, "scope")
    if scope not in {"user", "project"}:
        raise ValueError(f"Unsupported pack update audit scope: {path}")
    raw_entries = attributes.get("entries")
    if not isinstance(raw_entries, list):
        raise ValueError(f"Pack update audit entries must be an array: {path}")
    entries: list[PackUpdateAuditEntry] = []
    seen: set[tuple[str, str]] = set()
    for index, item in enumerate(raw_entries):
        if not isinstance(item, dict) or set(item) != {
            "kind",
            "id",
            "scope",
            "registry",
            "from-version",
            "to-version",
            "update-available",
            "modified",
        }:
            raise ValueError(f"Pack update audit entry {index} is invalid: {path}")
        kind = item.get("kind")
        pack_id = item.get("id")
        entry_scope = item.get("scope")
        registry = item.get("registry")
        from_version = item.get("from-version")
        to_version = item.get("to-version")
        update_available = item.get("update-available")
        modified = item.get("modified")
        if kind not in PACK_KINDS or not isinstance(pack_id, str):
            raise ValueError(f"Pack update audit entry {index} identity is invalid: {path}")
        assert_slug(pack_id, "Pack update audit pack id")
        if entry_scope != scope or not isinstance(registry, str):
            raise ValueError(f"Pack update audit entry {index} source is invalid: {path}")
        assert_slug(registry, "Pack update audit registry")
        if not isinstance(from_version, str) or not isinstance(to_version, str):
            raise ValueError(f"Pack update audit entry {index} versions are invalid: {path}")
        validate_pack_version(from_version)
        validate_pack_version(to_version)
        if not isinstance(update_available, bool) or not isinstance(modified, bool):
            raise ValueError(f"Pack update audit entry {index} flags are invalid: {path}")
        relation = compare_pack_versions(to_version, from_version)
        if relation < 0 or update_available != (relation > 0 or modified):
            raise ValueError(f"Pack update audit entry {index} relation is invalid: {path}")
        key = (kind, pack_id)
        if key in seen:
            raise ValueError(f"Pack update audit contains a duplicate pack: {kind}/{pack_id}")
        seen.add(key)
        entries.append(
            PackUpdateAuditEntry(
                kind=kind,  # type: ignore[arg-type]
                id=pack_id,
                scope=scope,  # type: ignore[arg-type]
                registry=registry,
                from_version=from_version,
                to_version=to_version,
                update_available=update_available,
                modified=modified,
            )
        )
    return PackUpdateAuditRecord(
        id=id_,
        scope=scope,  # type: ignore[arg-type]
        checked_at=string_attribute(attributes, "checked-at"),
        entries=entries,
        path=str(path),
    )


def render_pack_update_audit(record: PackUpdateAuditRecord) -> str:
    updates = sum(item.update_available for item in record.entries)
    modified = sum(item.modified for item in record.entries)
    return render_markdown(
        MarkdownDocument(
            attributes={
                "schema": "agora/pack-update-audit/v1",
                "id": record.id,
                "scope": record.scope,
                "checked-at": record.checked_at,
                "entries": [
                    {
                        "kind": item.kind,
                        "id": item.id,
                        "scope": item.scope,
                        "registry": item.registry,
                        "from-version": item.from_version,
                        "to-version": item.to_version,
                        "update-available": item.update_available,
                        "modified": item.modified,
                    }
                    for item in record.entries
                ],
            },
            body=(
                f"# Pack update audit {record.id}\n\n"
                f"Checked {len(record.entries)} catalog packs, found {updates} updates, and "
                f"detected {modified} locally modified packs."
            ),
        )
    )


def _version_parts(value: str) -> tuple[int, int, int]:
    validate_pack_version(value)
    major, minor, patch = value.split(".")
    return int(major), int(minor), int(patch)
