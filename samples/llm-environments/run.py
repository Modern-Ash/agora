import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from agora.markdown import read_markdown
from agora.model import ConfigureInput, InitInput, Integration
from agora.workspace import AgoraWorkspace


@dataclass(frozen=True)
class EnvironmentExample:
    name: str
    integration: Integration
    provider: str
    model: str
    adapter_path: str


EXAMPLES = (
    EnvironmentExample(
        name="Codex",
        integration="codex",
        provider="openai",
        model="configured-by-codex",
        adapter_path=".agents/skills/agora-objective/SKILL.md",
    ),
    EnvironmentExample(
        name="Claude",
        integration="claude",
        provider="anthropic",
        model="configured-by-claude",
        adapter_path=".claude/commands/agora.objective.md",
    ),
    EnvironmentExample(
        name="Local",
        integration="generic",
        provider="local-runtime",
        model="team-approved-coder",
        adapter_path=".agora/commands/objective.md",
    ),
)


def main() -> None:
    sample_root = Path(tempfile.mkdtemp(prefix="agora-llm-environments-"))
    print(f"Sample root: {sample_root}")

    for example in EXAMPLES:
        home = sample_root / example.name.lower() / "home"
        project = sample_root / example.name.lower() / "project"
        project.mkdir(parents=True)
        os.environ["AGORA_HOME"] = str(home)
        workspace = AgoraWorkspace(cwd=project)
        workspace.configure(
            ConfigureInput(
                integration=example.integration,
                provider=example.provider,
                model=example.model,
                default_method="scrum",
            )
        )
        workspace.initialize(InitInput())

        attributes = read_markdown(project / ".agora" / "project.md").attributes
        adapter = project / example.adapter_path
        if not adapter.is_file():
            raise RuntimeError(f"Expected adapter was not installed: {adapter}")
        print(
            f"{example.name}: integration={attributes['integration']} "
            f"provider={attributes['provider']} model={attributes['model']}"
        )
        print(f"  adapter={adapter}")

    print("No model APIs were called.")


if __name__ == "__main__":
    main()
