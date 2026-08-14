import io
from pathlib import Path

from agora.cli import main


def test_targets_a_project_outside_the_current_environment(tmp_path: Path, monkeypatch) -> None:
    project = tmp_path / "project"
    home = tmp_path / "home"
    project.mkdir()
    monkeypatch.setenv("AGORA_HOME", str(home))
    output = io.StringIO()
    errors = io.StringIO()

    assert (
        main(
            ["init", "--path", str(project), "--integration", "claude"],
            stdout=output,
            stderr=errors,
        )
        == 0
    )
    assert (
        main(
            [
                "actor",
                "add",
                "--project",
                str(project),
                "--id",
                "ada",
                "--name",
                "Ada",
                "--kind",
                "ai-agent",
                "--capability",
                "implementation",
            ],
            stdout=output,
            stderr=errors,
        )
        == 0
    )

    assert errors.getvalue() == ""
    assert '"integration": "claude"' in output.getvalue()
    assert '"reference": "project:ada"' in output.getvalue()


def test_installs_a_custom_method_without_an_initialized_project(
    tmp_path: Path, monkeypatch
) -> None:
    home = tmp_path / "home"
    source = Path(__file__).parents[1] / "samples" / "custom-lifecycle" / "release-flow"
    monkeypatch.setenv("AGORA_HOME", str(home))
    output = io.StringIO()
    errors = io.StringIO()

    assert (
        main(
            ["method", "install", "--source", str(source), "--scope", "user"],
            stdout=output,
            stderr=errors,
        )
        == 0
    )

    assert errors.getvalue() == ""
    assert '"id": "release-flow"' in output.getvalue()
    assert (home / "methods" / "release-flow" / "METHOD.md").exists()
