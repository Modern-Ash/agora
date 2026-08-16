import shutil
from pathlib import Path

import pytest

from agora.filesystem import template_root
from agora.methods import load_method_contract


def test_loads_explicit_transition_graph_gates_and_wip_limits() -> None:
    contract = load_method_contract(template_root() / "methods" / "scrum")

    assert contract.wip_limits == {"implementing": 2, "reviewing": 2}
    assert any(
        rule.source == "reviewing" and rule.target == "implementing" and rule.roles == ["developer"]
        for rule in contract.transitions
    )
    completion = next(rule for rule in contract.transitions if rule.target == "completed")
    assert completion.roles == ["product-owner"]
    assert completion.gate == "completion"
    assert contract.gates["completion"].require_successful_evidence is True
    assert contract.gates["completion"].required_approval_roles == ["product-owner"]


def test_rejects_an_explicit_transition_without_an_authorized_role(tmp_path: Path) -> None:
    method = tmp_path / "method"
    (method / "roles").mkdir(parents=True)
    (method / "transitions").mkdir()
    (method / "METHOD.md").write_text(
        '---\nschema: "agora/method/v1"\nid: "guarded"\nname: "Guarded"\n'
        'required-roles: ["owner"]\nwork-states: ["open", "done"]\n'
        'terminal-state: "done"\n---\n\n# Guarded\n'
    )
    (method / "roles" / "owner.md").write_text(
        '---\nschema: "agora/role/v1"\nid: "owner"\nrequired-capabilities: []\n'
        'allowed-actor-kinds: ["human"]\nallowed-actions: ["work.transition"]\n'
        "---\n\n# Owner\n"
    )
    (method / "transitions" / "open-done.md").write_text(
        '---\nschema: "agora/transition/v1"\nfrom: "open"\nto: "done"\nroles: []\n---\n\n# Finish\n'
    )

    with pytest.raises(ValueError, match="must define at least one role"):
        load_method_contract(method)


def test_rejects_an_invalid_role_manifest(tmp_path: Path) -> None:
    method = tmp_path / "scrum"
    shutil.copytree(template_root() / "methods" / "scrum", method)
    role = method / "roles" / "developer.md"
    role.write_text(role.read_text().replace('schema: "agora/role/v1"', 'schema: "invalid/role"'))

    with pytest.raises(ValueError, match="Role schema must be agora/role/v1"):
        load_method_contract(method)


def test_rejects_invalid_role_environment_scope(tmp_path: Path) -> None:
    method = tmp_path / "scrum"
    shutil.copytree(template_root() / "methods" / "scrum", method)
    role = method / "roles" / "developer.md"
    role.write_text(
        role.read_text().replace(
            'allowed-environments: ["*"]', 'allowed-environments: ["Production"]'
        )
    )

    with pytest.raises(ValueError, match="allowed-environments"):
        load_method_contract(method)
