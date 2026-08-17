import shutil
from pathlib import Path

import pytest

from agora.filesystem import packs_root
from agora.methods import load_method_contract


def test_loads_explicit_transition_graph_gates_and_wip_limits() -> None:
    contract = load_method_contract(packs_root() / "methods" / "scrum")

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
    assert contract.criterion_stages == ["specified", "implemented", "verified", "accepted"]
    assert contract.criterion_stage_roles["implemented"] == ["product-owner", "developer"]
    assert contract.criterion_stage_roles["verified"] == ["product-owner", "scrum-master"]
    assert contract.criterion_stage_roles["accepted"] == ["product-owner"]
    assert contract.gates["completion"].required_criterion_stage == "accepted"


def test_loads_the_spec_driven_pack_with_its_clarification_gate() -> None:
    contract = load_method_contract(packs_root() / "methods" / "spec-driven")

    assert contract.id == "spec-driven"
    assert contract.required_roles == ["spec-owner", "developer"]
    assert contract.work_states == [
        "drafting",
        "clarified",
        "planned",
        "implementing",
        "verifying",
        "completed",
    ]
    assert contract.terminal_state == "completed"
    assert contract.wip_limits == {}

    clarify = next(
        rule
        for rule in contract.transitions
        if rule.source == "drafting" and rule.target == "clarified"
    )
    assert clarify.roles == ["spec-owner"]
    assert clarify.gate == "spec-clarified"
    assert contract.gates["spec-clarified"].required_approval_roles == []
    assert contract.gates["spec-clarified"].require_required_artifacts is True
    assert contract.gates["spec-clarified"].required_artifacts == ["spec"]
    assert contract.gates["spec-clarified"].required_criterion_stage == "specified"

    completion = next(rule for rule in contract.transitions if rule.target == "completed")
    assert completion.roles == ["spec-owner"]
    assert completion.gate == "completion"
    assert contract.gates["completion"].required_approval_roles == ["spec-owner"]
    assert contract.gates["completion"].required_artifacts is None

    rework = next(
        rule
        for rule in contract.transitions
        if rule.source == "verifying" and rule.target == "implementing"
    )
    assert rework.roles == ["developer"]
    assert rework.gate is None


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
    shutil.copytree(packs_root() / "methods" / "scrum", method)
    role = method / "roles" / "developer.md"
    role.write_text(role.read_text().replace('schema: "agora/role/v1"', 'schema: "invalid/role"'))

    with pytest.raises(ValueError, match="Role schema must be agora/role/v1"):
        load_method_contract(method)


def test_loads_optional_git_and_review_gate_policy(tmp_path: Path) -> None:
    method = tmp_path / "scrum"
    shutil.copytree(packs_root() / "methods" / "scrum", method)
    gate = method / "gates" / "completion.md"
    gate.write_text(
        gate.read_text().replace(
            "require-successful-evidence: true",
            "require-successful-evidence: true\nrequire-clean-git: true\n"
            'require-git-commit: true\nrequired-evidence-types: ["code-review"]',
        )
    )

    contract = load_method_contract(method)
    completion = contract.gates["completion"]

    assert completion.require_clean_git is True
    assert completion.require_git_commit is True
    assert completion.required_evidence_types == ["code-review"]


def test_rejects_invalid_role_environment_scope(tmp_path: Path) -> None:
    method = tmp_path / "scrum"
    shutil.copytree(packs_root() / "methods" / "scrum", method)
    role = method / "roles" / "developer.md"
    role.write_text(
        role.read_text().replace(
            'allowed-environments: ["*"]', 'allowed-environments: ["Production"]'
        )
    )

    with pytest.raises(ValueError, match="allowed-environments"):
        load_method_contract(method)
