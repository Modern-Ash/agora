from pathlib import Path

import pytest

from agora.filesystem import template_root
from agora.tools import load_tool_contract


def test_loads_a_provider_neutral_tool_pack() -> None:
    contract = load_tool_contract(template_root() / "tools" / "repository")

    assert contract.id == "repository"
    assert contract.executable == "git"
    assert contract.operations["status"].capability == "repository.read"
    assert contract.operations["create-branch"].risk == "write"
    assert contract.operations["create-branch"].inputs == ["branch"]


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
