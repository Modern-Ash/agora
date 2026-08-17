import io
import json
import subprocess
from pathlib import Path

from agora.cli import main
from agora.markdown import read_markdown
from agora.workspace import AgoraWorkspace


class TTYInput(io.StringIO):
    def isatty(self) -> bool:
        return True


class TTYOutput(io.StringIO):
    def isatty(self) -> bool:
        return True


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


def test_interactive_setup_applies_a_reviewed_project_plan(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    root = tmp_path / "project"
    root.mkdir()
    output = io.StringIO()
    dialogue = io.StringIO()
    answers = TTYInput("\n\n\n\nno\nyes\n")

    exit_code = main(
        [
            "setup",
            "--integration",
            "generic",
            "--provider",
            "local-runtime",
            "--model",
            "team-model",
            "--method",
            "spec-driven",
            "--objective",
            "Deliver the first guided increment",
        ],
        cwd=root,
        stdin=answers,
        stdout=output,
        stderr=dialogue,
    )

    assert exit_code == 0
    payload = json.loads(output.getvalue())
    assert payload["ok"] is True
    assert payload["applied"] is True
    assert payload["mode"] == "setup"
    assert payload["setup"]["project"]["model"] == "team-model"
    assert payload["setup"]["swarm"]["status"] == "ready"
    assert "Agora Setup | Project" in dialogue.getvalue()
    assert "Agora Setup | Review" in dialogue.getvalue()
    assert "Apply this setup plan" in dialogue.getvalue()
    assert (root / ".agora" / "activity.md").is_file()
    activity = AgoraWorkspace(cwd=root).list_activity(type_="setup.completed")
    assert len(activity) == 1
    assert activity[0].swarm_id == "delivery"


def test_interactive_setup_cancellation_writes_nothing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    root = tmp_path / "project"
    root.mkdir()
    output = io.StringIO()
    dialogue = io.StringIO()
    answers = TTYInput("\n\n\n\nno\nno\n")

    exit_code = main(
        [
            "setup",
            "--integration",
            "generic",
            "--provider",
            "local-runtime",
            "--model",
            "team-model",
            "--method",
            "kanban",
            "--objective",
            "Review without applying",
        ],
        cwd=root,
        stdin=answers,
        stdout=output,
        stderr=dialogue,
    )

    assert exit_code == 0
    assert json.loads(output.getvalue())["applied"] is False
    assert "Setup cancelled" in dialogue.getvalue()
    assert not (root / ".agora").exists()
    assert not (tmp_path / "home").exists()


def test_non_interactive_setup_requires_explicit_consent_and_objective(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    errors = io.StringIO()

    assert (
        main(
            ["setup", "--non-interactive", "--objective", "Missing consent"],
            cwd=tmp_path,
            stderr=errors,
        )
        == 1
    )
    assert "--non-interactive requires --yes" in errors.getvalue()
    assert not (tmp_path / ".agora").exists()

    errors = io.StringIO()
    assert (
        main(
            ["setup", "--non-interactive", "--yes"],
            cwd=tmp_path,
            stderr=errors,
        )
        == 1
    )
    assert "--non-interactive requires --objective" in errors.getvalue()


def test_setup_rejects_non_tty_input_without_automation_flags(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    errors = io.StringIO()

    exit_code = main(
        ["setup"],
        cwd=tmp_path,
        stdin=io.StringIO(),
        stderr=errors,
    )

    assert exit_code == 1
    assert "needs an interactive terminal" in errors.getvalue()
    assert not (tmp_path / ".agora").exists()


def test_interactive_work_start_creates_reviewed_work_and_registers_existing_spec(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    root = tmp_path / "project"
    root.mkdir()
    assert (
        main(
            ["quickstart", "--objective", "Deliver guided work"],
            cwd=root,
            stdout=io.StringIO(),
        )
        == 0
    )
    spec = root / "docs" / "specs" / "dashboard.md"
    spec.parent.mkdir(parents=True)
    spec.write_text("# Dashboard specification\n", encoding="utf-8")
    dialogue = io.StringIO()
    output = io.StringIO()
    answers = TTYInput(
        "Build the delivery dashboard\n"
        "\n"
        "\n"
        "\n"
        "The dashboard presents current work\n"
        "\n"
        "\n"
        "docs/specs/dashboard.md\n"
        "yes\n"
    )

    exit_code = main(
        ["work", "start", "--swarm", "quickstart"],
        cwd=root,
        stdin=answers,
        stdout=output,
        stderr=dialogue,
    )

    payload = json.loads(output.getvalue())
    work = AgoraWorkspace(cwd=root).show_work("quickstart", "build-the-delivery-dashboard")
    assert exit_code == 0
    assert payload["applied"] is True
    assert work.state == "drafting"
    assert work.acceptance_criteria == {
        "the-dashboard-presents-current-work": "The dashboard presents current work"
    }
    assert work.artifact_kinds == ["spec"]
    assert "Agora Work | Review" in dialogue.getvalue()
    assert "agora continue" in dialogue.getvalue()


def test_non_interactive_adopt_runs_preflight_and_bootstraps_existing_git(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    root = _repository(tmp_path)
    output = io.StringIO()
    errors = io.StringIO()

    exit_code = main(
        [
            "adopt",
            "--non-interactive",
            "--yes",
            "--integration",
            "generic",
            "--method",
            "scrum",
            "--id",
            "feature",
            "--base",
            "main",
            "--objective",
            "Add the first governed feature",
        ],
        cwd=root,
        stdout=output,
        stderr=errors,
    )

    assert exit_code == 0
    payload = json.loads(output.getvalue())
    assert payload["mode"] == "adopt"
    assert payload["setup"]["swarm"]["branch"] == "agora/feature"
    assert (root / "README.md").read_text(encoding="utf-8") == "# Existing project\n"
    assert errors.getvalue() == ""
    activity = AgoraWorkspace(cwd=root).list_activity(type_="adopt.completed")
    assert len(activity) == 1


def test_setup_can_persist_reviewed_user_defaults(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setenv("AGORA_HOME", str(home))

    assert (
        main(
            [
                "setup",
                "--non-interactive",
                "--yes",
                "--integration",
                "generic",
                "--provider",
                "local-runtime",
                "--model",
                "approved-model",
                "--method",
                "kanban",
                "--objective",
                "Persist reviewed defaults",
                "--save-user-defaults",
            ],
            cwd=root,
            stdout=io.StringIO(),
            stderr=io.StringIO(),
        )
        == 0
    )

    attributes = read_markdown(home / "config.md").attributes
    assert attributes["integration"] == "generic"
    assert attributes["model"] == "approved-model"
    assert attributes["default-method"] == "kanban"


def test_setup_reviews_existing_project_without_recreating_state(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    root = tmp_path / "project"
    root.mkdir()
    assert (
        main(
            [
                "setup",
                "--non-interactive",
                "--yes",
                "--integration",
                "generic",
                "--objective",
                "Create the governed project",
            ],
            cwd=root,
            stdout=io.StringIO(),
            stderr=io.StringIO(),
        )
        == 0
    )
    before = {
        path.relative_to(root): path.read_bytes()
        for path in (root / ".agora").rglob("*")
        if path.is_file()
    }
    output = TTYOutput()
    dialogue = io.StringIO()

    exit_code = main(
        ["setup"],
        cwd=root,
        stdin=TTYInput("\nno\nyes\n"),
        stdout=output,
        stderr=dialogue,
    )

    assert exit_code == 0
    assert output.getvalue() == ""
    assert "Agora Setup | Existing project" in dialogue.getvalue()
    assert "Agora project is ready" in dialogue.getvalue()
    assert "Checks" in dialogue.getvalue()
    assert "Next steps" in dialogue.getvalue()
    assert "Starter team" not in dialogue.getvalue()
    after = {
        path.relative_to(root): path.read_bytes()
        for path in (root / ".agora").rglob("*")
        if path.is_file()
    }
    assert after == before


def test_interactive_setup_emits_json_when_stdout_is_redirected(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    root = tmp_path / "project"
    root.mkdir()
    output = io.StringIO()

    exit_code = main(
        [
            "setup",
            "--integration",
            "generic",
            "--provider",
            "configured-by-runner",
            "--model",
            "configured-by-runner",
            "--method",
            "spec-driven",
            "--max-delegation-depth",
            "3",
            "--objective",
            "Initialize with structured output",
            "--save-user-defaults",
            "--yes",
        ],
        cwd=root,
        stdin=TTYInput("\n\n\n"),
        stdout=output,
        stderr=io.StringIO(),
    )

    assert exit_code == 0
    payload = json.loads(output.getvalue())
    assert payload["ok"] is True
    assert payload["mode"] == "setup"


def test_interactive_setup_uses_color_on_a_supported_terminal(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.delenv("NO_COLOR", raising=False)
    root = tmp_path / "project"
    root.mkdir()
    dialogue = TTYOutput()

    exit_code = main(
        [
            "setup",
            "--integration",
            "generic",
            "--provider",
            "configured-by-runner",
            "--model",
            "configured-by-runner",
            "--method",
            "spec-driven",
            "--max-delegation-depth",
            "3",
            "--objective",
            "Initialize with color",
            "--save-user-defaults",
            "--yes",
        ],
        cwd=root,
        stdin=TTYInput("\n\n\n"),
        stdout=TTYOutput(),
        stderr=dialogue,
    )

    assert exit_code == 0
    assert "\x1b[" in dialogue.getvalue()
    assert "Agora project is ready" in dialogue.getvalue()
    assert "Next steps" in dialogue.getvalue()


def test_interactive_setup_respects_no_color(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.setenv("NO_COLOR", "1")
    root = tmp_path / "project"
    root.mkdir()
    dialogue = TTYOutput()

    exit_code = main(
        [
            "setup",
            "--integration",
            "generic",
            "--provider",
            "configured-by-runner",
            "--model",
            "configured-by-runner",
            "--method",
            "spec-driven",
            "--max-delegation-depth",
            "3",
            "--objective",
            "Initialize without color",
            "--save-user-defaults",
            "--yes",
        ],
        cwd=root,
        stdin=TTYInput("\n\n\n"),
        stdout=TTYOutput(),
        stderr=dialogue,
    )

    assert exit_code == 0
    assert "\x1b[" not in dialogue.getvalue()


def test_non_interactive_setup_reviews_existing_project_without_objective(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    root = tmp_path / "project"
    root.mkdir()
    assert (
        main(
            ["setup", "--non-interactive", "--yes", "--objective", "Initialize Agora"],
            cwd=root,
            stdout=io.StringIO(),
            stderr=io.StringIO(),
        )
        == 0
    )
    output = io.StringIO()

    exit_code = main(
        ["setup", "--non-interactive", "--yes"],
        cwd=root,
        stdout=output,
        stderr=io.StringIO(),
    )

    assert exit_code == 0
    payload = json.loads(output.getvalue())
    assert payload["mode"] == "setup-existing"
    assert payload["user_defaults_saved"] is False


def test_guided_adopt_rejects_an_initialized_project(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    root = tmp_path / "project"
    root.mkdir()
    assert (
        main(
            ["setup", "--non-interactive", "--yes", "--objective", "Initialize Agora"],
            cwd=root,
            stdout=io.StringIO(),
            stderr=io.StringIO(),
        )
        == 0
    )
    errors = io.StringIO()

    exit_code = main(
        ["adopt", "--non-interactive", "--yes"],
        cwd=root,
        stdout=io.StringIO(),
        stderr=errors,
    )

    assert exit_code == 1
    assert "already initialized; use agora setup" in errors.getvalue()
