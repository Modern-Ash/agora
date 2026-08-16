import io
import json
import subprocess
from pathlib import Path

from agora.cli import main
from agora.model import AdoptionInput
from agora.workspace import AgoraWorkspace


def _git(root: Path, *arguments: str) -> None:
    result = subprocess.run(
        ["git", *arguments], cwd=root, check=False, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


def _repository(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    _git(root, "init", "--initial-branch", "main")
    _git(root, "config", "user.name", "Agora Test")
    _git(root, "config", "user.email", "agora@example.test")
    (root / "README.md").write_text("# Existing project\n", encoding="utf-8")
    _git(root, "add", "README.md")
    _git(root, "commit", "-m", "chore: initialize fixture")
    return root


def test_checks_a_clean_existing_repository_without_mutating_it(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    root = _repository(tmp_path)
    before = {path.relative_to(root) for path in root.rglob("*")}

    report = AgoraWorkspace(cwd=root).check_adoption(
        AdoptionInput(swarm_id="feature", base_branch="main")
    )

    assert report.ok is True
    assert report.initialized is False
    assert report.git_repository is True
    assert report.branch == "main"
    assert all(check.ok for check in report.checks)
    assert {path.relative_to(root) for path in root.rglob("*")} == before
    assert not (root / ".agora").exists()


def test_cli_rejects_ignored_governance_state_without_writing_project_files(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    root = _repository(tmp_path)
    (root / ".gitignore").write_text(".agora/\n", encoding="utf-8")
    _git(root, "add", ".gitignore")
    _git(root, "commit", "-m", "chore: ignore local state")
    output = io.StringIO()
    errors = io.StringIO()

    exit_code = main(
        ["adopt", "--check", "--id", "feature", "--base", "main"],
        cwd=root,
        stdout=output,
        stderr=errors,
    )

    assert exit_code == 1
    assert errors.getvalue() == ""
    report = json.loads(output.getvalue())
    persistence = next(check for check in report["checks"] if check["name"] == "git-persistence")
    assert persistence["name"] == "git-persistence"
    assert persistence["ok"] is False
    assert persistence["detail"].startswith("ignored: .agora/")
    assert not (root / ".agora").exists()


def test_reports_dirty_state_and_requires_an_explicit_override(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    root = _repository(tmp_path)
    (root / "README.md").write_text("# Local change\n", encoding="utf-8")
    workspace = AgoraWorkspace(cwd=root)

    rejected = workspace.check_adoption(AdoptionInput(swarm_id="feature"))
    accepted = workspace.check_adoption(AdoptionInput(swarm_id="feature", allow_dirty=True))

    assert rejected.ok is False
    assert next(check for check in rejected.checks if check.name == "git-clean").ok is False
    assert accepted.ok is True


def test_detects_target_branch_and_partial_state_collisions(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    root = _repository(tmp_path)
    _git(root, "branch", "agora/feature")
    (root / ".agora").mkdir()

    report = AgoraWorkspace(cwd=root).check_adoption(AdoptionInput(swarm_id="feature"))

    checks = {check.name: check for check in report.checks}
    assert report.ok is False
    assert checks["partial-agora-state"].ok is False
    assert checks["git-target-branch"].ok is False


def test_requires_git_for_the_existing_repository_adoption_path(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    root = tmp_path / "project"
    root.mkdir()

    report = AgoraWorkspace(cwd=root).check_adoption(AdoptionInput())

    assert report.ok is False
    assert report.git_repository is False
    assert next(check for check in report.checks if check.name == "git-repository").ok is False
