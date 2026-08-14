from pathlib import Path

import pytest

from agora.filesystem import template_root
from agora.tools import load_tool_contract, validate_conventional_commit


def test_loads_a_provider_neutral_tool_pack() -> None:
    contract = load_tool_contract(template_root() / "tools" / "repository")

    assert contract.id == "repository"
    assert contract.executable == "git"
    assert contract.operations["status"].capability == "repository.read"
    assert contract.operations["create-branch"].risk == "write"
    assert contract.operations["create-branch"].inputs == ["branch"]
    assert contract.operations["commit"].input_rules == {"message": "conventional-commits/v1.0.0"}


@pytest.mark.parametrize(
    "message",
    [
        "feat: add governed commits",
        "fix(parser): reject an empty description",
        "feat(api)!: remove the legacy endpoint",
        "docs: explain the policy\n\nThis body adds context.",
        "refactor!: change the contract\n\nBREAKING CHANGE: callers must pass an actor",
    ],
)
def test_accepts_conventional_commit_messages(message: str) -> None:
    validate_conventional_commit(message)


@pytest.mark.parametrize(
    ("message", "error"),
    [
        ("record governed work", "must match Conventional Commits"),
        ("feat:add missing space", "must match Conventional Commits"),
        ("feat: ", "must match Conventional Commits"),
        ("feat(core): add rule\nBody without separator", "must begin after a blank line"),
        ("feat: invalid\x00message", "must not contain a null byte"),
    ],
)
def test_rejects_non_conventional_commit_messages(message: str, error: str) -> None:
    with pytest.raises(ValueError, match=error):
        validate_conventional_commit(message)


def test_rejects_undeclared_command_placeholders(tmp_path: Path) -> None:
    tool = tmp_path / "tool"
    (tool / "operations").mkdir(parents=True)
    (tool / "TOOL.md").write_text(
        '---\nschema: "agora/tool/v1"\nid: "tracker"\nname: "Tracker"\n'
        'category: "issue-tracker"\nexecutable: "tracker"\n---\n\n# Tracker\n'
    )
    (tool / "operations" / "view.md").write_text(
        '---\nschema: "agora/tool-operation/v1"\nid: "view"\nname: "View issue"\n'
        'capability: "issue.read"\nrisk: "read"\narguments: ["view","{issue}"]\n'
        "inputs: []\n---\n\n# View issue\n"
    )

    with pytest.raises(ValueError, match="undeclared placeholders: issue"):
        load_tool_contract(tool)


def test_rejects_unknown_tool_input_rules(tmp_path: Path) -> None:
    tool = tmp_path / "tool"
    (tool / "operations").mkdir(parents=True)
    (tool / "TOOL.md").write_text(
        '---\nschema: "agora/tool/v1"\nid: "repository"\nname: "Repository"\n'
        'category: "repository"\nexecutable: "git"\n---\n\n# Repository\n'
    )
    (tool / "operations" / "commit.md").write_text(
        '---\nschema: "agora/tool-operation/v1"\nid: "commit"\nname: "Commit"\n'
        'capability: "repository.write"\nrisk: "write"\n'
        'arguments: ["commit","-m","{message}"]\ninputs: ["message"]\n'
        'input-rules: {"message":"unregistered-rule/v1"}\n---\n\n# Commit\n'
    )

    with pytest.raises(ValueError, match="unsupported input rules: unregistered-rule/v1"):
        load_tool_contract(tool)
