import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from agora.filesystem import assert_slug, atomic_write, template_root
from agora.markdown import MarkdownDocument, read_markdown, render_markdown, string_attribute
from agora.model import Integration, ProjectConfiguration, UpgradeChange, UpgradeResult

CURRENT_PROJECT_VERSION = "0.2.0"
VERSION_PATTERN = re.compile(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)")


@dataclass(frozen=True)
class _Mutation:
    path: Path
    contents: str
    change: UpgradeChange


def validate_version(value: str) -> str:
    if not VERSION_PATTERN.fullmatch(value):
        raise ValueError(f"Project version must use MAJOR.MINOR.PATCH: {value}")
    return value


def compare_versions(left: str, right: str) -> int:
    left_parts = tuple(int(part) for part in validate_version(left).split("."))
    right_parts = tuple(int(part) for part in validate_version(right).split("."))
    return (left_parts > right_parts) - (left_parts < right_parts)


def plan_upgrade(root: Path, project: ProjectConfiguration) -> UpgradeResult:
    relation = compare_versions(project.version, CURRENT_PROJECT_VERSION)
    if relation > 0:
        raise ValueError(
            f"Project version {project.version} is newer than this Agora CLI "
            f"({CURRENT_PROJECT_VERSION})"
        )
    if relation == 0:
        return UpgradeResult(
            from_version=project.version,
            to_version=CURRENT_PROJECT_VERSION,
            required=False,
            applied=False,
            id=None,
            record_path=None,
            changes=[],
            warnings=[],
        )
    if project.version != "0.1.0":
        raise ValueError(
            f"No supported migration path from {project.version} to {CURRENT_PROJECT_VERSION}"
        )

    mutations, warnings = _migrate_0_1_0_to_0_2_0(root, project)
    return UpgradeResult(
        from_version=project.version,
        to_version=CURRENT_PROJECT_VERSION,
        required=True,
        applied=False,
        id=None,
        record_path=None,
        changes=[item.change for item in mutations],
        warnings=warnings,
    )


def apply_upgrade(
    root: Path,
    project: ProjectConfiguration,
    *,
    id_: str,
    applied_at: str,
) -> UpgradeResult:
    plan = plan_upgrade(root, project)
    if not plan.required:
        return plan
    mutations, warnings = _migrate_0_1_0_to_0_2_0(root, project)
    upgrade_root = root / ".agora" / "upgrades" / id_
    if upgrade_root.exists():
        raise FileExistsError(f"Upgrade record already exists: {upgrade_root}")

    backup_root = upgrade_root / "backup"
    existing = [item for item in mutations if item.path.exists()]
    created = [item for item in mutations if not item.path.exists()]
    created_directories: set[Path] = set()
    for item in created:
        parent = item.path.parent
        while parent != root and not parent.exists():
            created_directories.add(parent)
            parent = parent.parent
    try:
        for item in existing:
            relative = item.path.relative_to(root)
            atomic_write(backup_root / relative, item.path.read_text(encoding="utf-8"))
        for item in mutations:
            atomic_write(item.path, item.contents)
        record_path = upgrade_root / "UPGRADE.md"
        atomic_write(
            record_path,
            render_markdown(
                MarkdownDocument(
                    attributes={
                        "schema": "agora/upgrade/v1",
                        "id": id_,
                        "from-version": plan.from_version,
                        "to-version": plan.to_version,
                        "status": "completed",
                        "applied-at": applied_at,
                        "changed-files": [item.change.path for item in mutations],
                        "created-files": [item.change.path for item in created],
                        "changes": [
                            f"{item.change.action}:{item.change.path}: {item.change.detail}"
                            for item in mutations
                        ],
                        "backup-root": "backup",
                    },
                    body=(
                        f"# Upgrade {id_}\n\n"
                        "This record identifies the migration and the files backed up before it "
                        "was applied. Project policies and Method Packs were preserved."
                    ),
                )
            ),
        )
    except Exception as error:
        for item in existing:
            backup = backup_root / item.path.relative_to(root)
            if backup.exists():
                atomic_write(item.path, backup.read_text(encoding="utf-8"))
        for item in created:
            if item.path.exists():
                item.path.unlink()
        if upgrade_root.exists():
            shutil.rmtree(upgrade_root)
        for directory in sorted(
            created_directories, key=lambda item: len(item.parts), reverse=True
        ):
            if directory.exists():
                try:
                    directory.rmdir()
                except OSError:
                    pass
        raise RuntimeError(f"Upgrade failed and was rolled back: {error}") from error

    return UpgradeResult(
        from_version=plan.from_version,
        to_version=plan.to_version,
        required=True,
        applied=True,
        id=id_,
        record_path=str(record_path),
        changes=plan.changes,
        warnings=warnings,
    )


def read_upgrade_record(path: Path) -> MarkdownDocument:
    document = read_markdown(path)
    attributes = document.attributes
    if string_attribute(attributes, "schema") != "agora/upgrade/v1":
        raise ValueError(f"Expected schema agora/upgrade/v1: {path}")
    assert_slug(string_attribute(attributes, "id"), "Upgrade id")
    from_version = validate_version(string_attribute(attributes, "from-version"))
    to_version = validate_version(string_attribute(attributes, "to-version"))
    if compare_versions(from_version, to_version) >= 0:
        raise ValueError(f"Upgrade versions must move forward: {path}")
    if string_attribute(attributes, "status") != "completed":
        raise ValueError(f"Upgrade status must be completed: {path}")
    string_attribute(attributes, "applied-at")
    file_lists: dict[str, list[str]] = {}
    for key in ("changed-files", "created-files"):
        value = attributes.get(key)
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise ValueError(f"Expected string array attribute: {key}")
        if any(Path(item).is_absolute() or ".." in Path(item).parts for item in value):
            raise ValueError(f"Upgrade paths must stay within the project: {key}")
        file_lists[key] = value
    changes = attributes.get("changes")
    if not isinstance(changes, list) or any(not isinstance(item, str) for item in changes):
        raise ValueError("Expected string array attribute: changes")
    created = set(file_lists["created-files"])
    changed = set(file_lists["changed-files"])
    if not created.issubset(changed):
        raise ValueError(f"Created files must be included in changed files: {path}")
    backup_name = string_attribute(attributes, "backup-root")
    if backup_name != "backup":
        raise ValueError(f"Upgrade backup root must be backup: {path}")
    for relative in sorted(changed - created):
        backup = path.parent / backup_name / relative
        if not backup.is_file():
            raise ValueError(f"Upgrade backup is missing: {backup}")
    return document


def _migrate_0_1_0_to_0_2_0(
    root: Path, project: ProjectConfiguration
) -> tuple[list[_Mutation], list[str]]:
    mutations: list[_Mutation] = []
    project_path = root / ".agora" / "project.md"
    project_document = read_markdown(project_path)
    project_document.attributes["version"] = CURRENT_PROJECT_VERSION
    _add_update(
        mutations,
        root,
        project_path,
        render_markdown(project_document),
        "Set the project protocol version",
    )

    for path in sorted((root / ".agora" / "swarms").glob("*/work/*/WORK.md")):
        document = read_markdown(path)
        changed = False
        for key, value in (
            ("operational-status", "active"),
            ("status-reason", None),
            ("status-by", None),
            ("status-at", None),
        ):
            if key not in document.attributes:
                document.attributes[key] = value
                changed = True
        if changed:
            _add_update(
                mutations,
                root,
                path,
                render_markdown(document),
                "Materialize operational work status",
            )

    for path in sorted((root / ".agora" / "delegations").glob("*/DELEGATION.md")):
        document = read_markdown(path)
        changed = False
        for key in ("blocked-from", "status-reason", "status-by", "status-at"):
            if key not in document.attributes:
                document.attributes[key] = None
                changed = True
        if changed:
            _add_update(
                mutations,
                root,
                path,
                render_markdown(document),
                "Materialize delegation interruption fields",
            )

    standards_path = root / ".agora" / "STANDARDS.md"
    if not standards_path.exists():
        _add_create(
            mutations,
            root,
            standards_path,
            _render_project_template("STANDARDS.md", project),
            "Install the governed project standards contract",
        )

    commit_operation = root / ".agora" / "tools" / "repository" / "operations" / "commit.md"
    repository_tool = root / ".agora" / "tools" / "repository" / "TOOL.md"
    if not commit_operation.exists() and repository_tool.exists():
        tool_attributes = read_markdown(repository_tool).attributes
        if tool_attributes.get("id") == "repository" and tool_attributes.get("executable") == "git":
            _add_create(
                mutations,
                root,
                commit_operation,
                (template_root() / "tools" / "repository" / "operations" / "commit.md").read_text(
                    encoding="utf-8"
                ),
                "Install the governed Conventional Commit operation",
            )

    command_path = root / ".agora" / "commands" / "status.md"
    if not command_path.exists():
        command_contents = _render_template_command("status", project)
        _add_create(
            mutations,
            root,
            command_path,
            command_contents,
            "Install the portable operational status command",
        )
    else:
        command_contents = command_path.read_text(encoding="utf-8")

    adapter_path = _integration_command_path(root, project.integration, "status")
    warnings = [
        "Existing Method Packs and project policy documents are preserved; review new permissions "
        "before opting in to them."
    ]
    if adapter_path != command_path and not adapter_path.exists():
        _add_create(
            mutations,
            root,
            adapter_path,
            command_contents,
            f"Install the {project.integration} adapter for the status command",
        )
    elif (
        adapter_path != command_path
        and adapter_path.exists()
        and adapter_path.read_text(encoding="utf-8") != command_contents
    ):
        warnings.append(
            f"Preserved customized adapter {adapter_path.relative_to(root)}; synchronize it with "
            ".agora/commands/status.md if validation reports drift."
        )
    return mutations, warnings


def _render_template_command(command_id: str, project: ProjectConfiguration) -> str:
    contents = (template_root() / "commands" / f"{command_id}.md").read_text(encoding="utf-8")
    replacements = {
        "PROJECT_NAME": project.project,
        "INTEGRATION": project.integration,
        "PROVIDER": project.provider,
        "MODEL": project.model,
        "DEFAULT_METHOD": project.default_method,
    }
    for key, value in replacements.items():
        contents = contents.replace(f"{{{{{key}}}}}", value)
    return contents


def _render_project_template(relative: str, project: ProjectConfiguration) -> str:
    contents = (template_root() / "project" / relative).read_text(encoding="utf-8")
    replacements = {
        "PROJECT_NAME": project.project,
        "INTEGRATION": project.integration,
        "PROVIDER": project.provider,
        "MODEL": project.model,
        "DEFAULT_METHOD": project.default_method,
    }
    for key, value in replacements.items():
        contents = contents.replace(f"{{{{{key}}}}}", value)
    return contents


def _integration_command_path(root: Path, integration: Integration, command_id: str) -> Path:
    if integration == "codex":
        return root / ".agents" / "skills" / f"agora-{command_id}" / "SKILL.md"
    if integration == "claude":
        return root / ".claude" / "commands" / f"agora.{command_id}.md"
    return root / ".agora" / "commands" / f"{command_id}.md"


def _add_update(
    mutations: list[_Mutation],
    root: Path,
    path: Path,
    contents: str,
    detail: str,
) -> None:
    mutations.append(
        _Mutation(
            path=path,
            contents=contents,
            change=UpgradeChange("update", str(path.relative_to(root)), detail),
        )
    )


def _add_create(
    mutations: list[_Mutation],
    root: Path,
    path: Path,
    contents: str,
    detail: str,
) -> None:
    mutations.append(
        _Mutation(
            path=path,
            contents=contents,
            change=UpgradeChange("create", str(path.relative_to(root)), detail),
        )
    )
