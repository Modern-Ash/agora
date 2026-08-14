import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path

from agora.markdown import read_markdown, render_markdown
from agora.model import InitInput, UpgradeInput
from agora.workspace import AgoraWorkspace


def main() -> None:
    project = Path(tempfile.mkdtemp(prefix="agora-upgrade-project-"))
    os.environ["AGORA_HOME"] = tempfile.mkdtemp(prefix="agora-upgrade-home-")
    agora = AgoraWorkspace(cwd=project)
    agora.initialize(InitInput(integration="codex"))

    configuration_path = project / ".agora" / "project.md"
    configuration = read_markdown(configuration_path)
    configuration.attributes["version"] = "0.1.0"
    configuration_path.write_text(render_markdown(configuration), encoding="utf-8")

    (project / ".agora" / "commands" / "status.md").unlink()
    (project / ".agents" / "skills" / "agora-status" / "SKILL.md").unlink()
    (project / ".agora" / "STANDARDS.md").unlink()
    (project / ".agora" / "tools" / "repository" / "operations" / "commit.md").unlink()
    constitution_path = project / ".agora" / "constitution.md"
    constitution_path.write_text(
        f"{constitution_path.read_text()}\nLocal amendment: require human release approval.\n",
        encoding="utf-8",
    )
    constitution_before = constitution_path.read_text(encoding="utf-8")

    plan = agora.upgrade(UpgradeInput())
    result = agora.upgrade(UpgradeInput(apply=True, id="upgrade-sample"))
    report = agora.validate()

    assert plan.applied is False
    assert result.applied is True
    assert constitution_path.read_text(encoding="utf-8") == constitution_before
    assert report.ok

    print(f"Project: {project}")
    print("Plan:")
    print(json.dumps(asdict(plan), indent=2))
    print("Applied migration:")
    print(json.dumps(asdict(result), indent=2))
    print("Validation:")
    print(json.dumps(asdict(report), indent=2))


if __name__ == "__main__":
    main()
