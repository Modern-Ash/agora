import io
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from conftest import swarm_dir

import agora.upgrades as upgrades
from agora.cli import main
from agora.markdown import read_markdown, render_markdown
from agora.model import InitInput, RefreshPackLockInput, UpgradeInput
from agora.workspace import AgoraWorkspace

TIMESTAMP = datetime(2026, 8, 14, 12, tzinfo=UTC)


@pytest.fixture
def project(tmp_path: Path, monkeypatch) -> tuple[Path, AgoraWorkspace]:
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    return root, AgoraWorkspace(cwd=root, now=lambda: TIMESTAMP)


def test_new_projects_use_the_current_version_and_need_no_upgrade(
    project: tuple[Path, AgoraWorkspace],
) -> None:
    root, workspace = project

    configuration = workspace.initialize(InitInput(integration="generic"))
    result = workspace.upgrade(UpgradeInput())

    assert configuration.version == "0.3.0"
    assert read_markdown(root / ".agora" / "project.md").attributes["version"] == "0.3.0"
    assert result.required is False
    assert result.applied is False
    assert not (root / ".agora" / "upgrades").exists()


def test_upgrades_0_2_without_installing_new_pack_authority(
    project: tuple[Path, AgoraWorkspace],
) -> None:
    root, workspace = project
    workspace.initialize(InitInput(integration="generic", default_method="scrum"))
    project_path = root / ".agora" / "project.md"
    document = read_markdown(project_path)
    document.attributes["version"] = "0.2.0"
    project_path.write_text(render_markdown(document), encoding="utf-8")
    shutil.rmtree(root / ".agora" / "tools" / "code-review")
    workspace.refresh_pack_lock(RefreshPackLockInput(scope="project"))
    role_path = root / ".agora" / "methods" / "scrum" / "roles" / "developer.md"
    role_path.write_text(role_path.read_text(encoding="utf-8") + "\nLocal authority.\n")
    role_before = role_path.read_text(encoding="utf-8")
    workspace.refresh_pack_lock(RefreshPackLockInput(scope="project"))

    plan = workspace.upgrade(UpgradeInput())
    result = workspace.upgrade(UpgradeInput(apply=True, id="upgrade-operational-loop"))

    assert [change.path for change in plan.changes] == [".agora/project.md"]
    assert any("not installed implicitly" in warning for warning in plan.warnings)
    assert result.applied is True
    assert read_markdown(project_path).attributes["version"] == "0.3.0"
    assert role_path.read_text(encoding="utf-8") == role_before
    assert not (root / ".agora" / "tools" / "code-review").exists()
    assert workspace.validate().ok


def test_plans_and_applies_a_non_destructive_legacy_upgrade(
    project: tuple[Path, AgoraWorkspace],
) -> None:
    root, workspace = project
    workspace.initialize(InitInput(integration="codex"))
    project_path = root / ".agora" / "project.md"
    project_document = read_markdown(project_path)
    project_document.attributes["version"] = "0.1.0"
    project_path.write_text(render_markdown(project_document), encoding="utf-8")

    command_path = root / ".agora" / "commands" / "status.md"
    adapter_path = root / ".agents" / "skills" / "agora-status" / "SKILL.md"
    standards_path = root / ".agora" / "STANDARDS.md"
    commit_path = root / ".agora" / "tools" / "repository" / "operations" / "commit.md"
    command_path.unlink()
    adapter_path.unlink()
    standards_path.unlink()
    commit_path.unlink()

    work_path = swarm_dir(root, "legacy") / "work" / "item" / "WORK.md"
    work_path.parent.mkdir(parents=True)
    work_path.write_text(
        """---
schema: "agora/work/v1"
id: "item"
---

# Legacy work
""",
        encoding="utf-8",
    )
    delegation_path = root / ".agora" / "delegations" / "legacy" / "DELEGATION.md"
    delegation_path.parent.mkdir(parents=True)
    delegation_path.write_text(
        """---
schema: "agora/delegation/v1"
id: "legacy"
---

# Legacy delegation
""",
        encoding="utf-8",
    )
    constitution = root / ".agora" / "constitution.md"
    constitution.write_text(
        f"{constitution.read_text()}\nLocal policy remains.\n", encoding="utf-8"
    )
    policy_before = constitution.read_text(encoding="utf-8")
    role = root / ".agora" / "methods" / "scrum" / "roles" / "developer.md"
    role_before = role.read_text(encoding="utf-8")

    plan = workspace.upgrade(UpgradeInput())

    assert plan.required is True
    assert plan.applied is False
    assert project_path.read_text(encoding="utf-8") == render_markdown(project_document)
    assert not command_path.exists()
    assert {change.path for change in plan.changes} == {
        ".agora/project.md",
        ".agora/swarms/legacy/work/item/WORK.md",
        ".agora/delegations/legacy/DELEGATION.md",
        ".agora/STANDARDS.md",
        ".agora/tools/repository/operations/commit.md",
        ".agora/commands/status.md",
        ".agents/skills/agora-status/SKILL.md",
    }

    result = workspace.upgrade(UpgradeInput(apply=True, id="upgrade-legacy"))

    assert result.applied is True
    assert read_markdown(project_path).attributes["version"] == "0.3.0"
    work = read_markdown(work_path).attributes
    assert work["operational-status"] == "active"
    assert work["status-reason"] is None
    delegation = read_markdown(delegation_path).attributes
    assert delegation["blocked-from"] is None
    assert command_path.read_text(encoding="utf-8") == adapter_path.read_text(encoding="utf-8")
    assert "conventional-commits/v1.0.0" in standards_path.read_text(encoding="utf-8")
    assert 'id: "commit"' in commit_path.read_text(encoding="utf-8")
    assert constitution.read_text(encoding="utf-8") == policy_before
    assert role.read_text(encoding="utf-8") == role_before
    record = root / ".agora" / "upgrades" / "upgrade-legacy" / "UPGRADE.md"
    assert record.exists()
    assert (record.parent / "backup" / ".agora" / "project.md").read_text(
        encoding="utf-8"
    ) == render_markdown(project_document)
    assert workspace.upgrade(UpgradeInput(apply=True)).required is False


def test_rolls_back_all_project_changes_when_an_upgrade_write_fails(
    project: tuple[Path, AgoraWorkspace], monkeypatch
) -> None:
    root, workspace = project
    workspace.initialize(InitInput(integration="codex"))
    project_path = root / ".agora" / "project.md"
    document = read_markdown(project_path)
    document.attributes["version"] = "0.1.0"
    project_path.write_text(render_markdown(document), encoding="utf-8")
    before = project_path.read_text(encoding="utf-8")
    command_path = root / ".agora" / "commands" / "status.md"
    adapter_path = root / ".agents" / "skills" / "agora-status" / "SKILL.md"
    adapter_directory = adapter_path.parent
    command_path.unlink()
    adapter_path.unlink()
    adapter_directory.rmdir()
    original_write = upgrades.atomic_write

    def fail_once(path: Path, contents: str) -> None:
        if path.name == "UPGRADE.md":
            raise OSError("injected write failure")
        original_write(path, contents)

    monkeypatch.setattr(upgrades, "atomic_write", fail_once)

    with pytest.raises(RuntimeError, match="rolled back"):
        workspace.upgrade(UpgradeInput(apply=True, id="upgrade-failure"))

    assert project_path.read_text(encoding="utf-8") == before
    assert not command_path.exists()
    assert not adapter_path.exists()
    assert not adapter_directory.exists()
    assert not (root / ".agora" / "upgrades" / "upgrade-failure").exists()


def test_rejects_projects_created_by_a_newer_cli(
    project: tuple[Path, AgoraWorkspace],
) -> None:
    root, workspace = project
    workspace.initialize(InitInput(integration="generic"))
    path = root / ".agora" / "project.md"
    document = read_markdown(path)
    document.attributes["version"] = "9.0.0"
    path.write_text(render_markdown(document), encoding="utf-8")

    with pytest.raises(ValueError, match="newer than this Agora CLI"):
        workspace.upgrade(UpgradeInput())

    report = workspace.validate()
    assert report.ok is False
    assert any(issue.code == "project.version-newer" for issue in report.issues)


def test_cli_previews_and_applies_an_upgrade(project: tuple[Path, AgoraWorkspace]) -> None:
    root, workspace = project
    workspace.initialize(InitInput(integration="generic"))
    path = root / ".agora" / "project.md"
    document = read_markdown(path)
    document.attributes["version"] = "0.1.0"
    path.write_text(render_markdown(document), encoding="utf-8")
    output = io.StringIO()
    errors = io.StringIO()

    assert main(["upgrade"], cwd=root, stdout=output, stderr=errors) == 0
    assert '"applied": false' in output.getvalue()
    assert read_markdown(path).attributes["version"] == "0.1.0"

    output = io.StringIO()
    assert (
        main(
            ["upgrade", "--apply", "--id", "upgrade-cli"],
            cwd=root,
            stdout=output,
            stderr=errors,
        )
        == 0
    )
    assert '"applied": true' in output.getvalue()
    assert errors.getvalue() == ""
    assert read_markdown(path).attributes["version"] == "0.3.0"
    assert workspace.validate().ok is True

    backup = root / ".agora" / "upgrades" / "upgrade-cli" / "backup" / ".agora" / "project.md"
    backup.unlink()
    report = workspace.validate()
    assert report.ok is False
    assert any(issue.code == "upgrade.invalid" for issue in report.issues)
