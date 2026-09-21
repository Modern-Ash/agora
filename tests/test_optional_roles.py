import shutil
from pathlib import Path

import pytest

from agora.filesystem import packs_root
from agora.methods import load_method_contract
from agora.model import (
    AddActorInput,
    AssignActorInput,
    CreateSwarmInput,
    InitInput,
    InstallMethodInput,
)
from agora.workspace import AgoraWorkspace


def optional_pack(
    tmp_path: Path, optional: str = '["scrum-master"]', required: str | None = None
) -> Path:
    method = tmp_path / "scrum"
    shutil.copytree(packs_root() / "methods" / "scrum", method)
    document = method / "METHOD.md"
    text = document.read_text()
    text = text.replace(
        'required-roles: ["product-owner", "scrum-master", "developer"]',
        f"required-roles: {required or ['product-owner', 'developer']!s}".replace("'", '"'),
    )
    text = text.replace("dependencies: []", f"dependencies: []\noptional-roles: {optional}")
    document.write_text(text)
    return method


def test_optional_roles_are_parsed_and_usable_in_stages_transitions_and_gates(tmp_path):
    contract = load_method_contract(optional_pack(tmp_path))
    assert contract.required_roles == ["product-owner", "developer"]
    assert contract.optional_roles == ["scrum-master"]
    assert any("scrum-master" in rule.roles for rule in contract.transitions)


def test_methods_without_optional_roles_are_unchanged():
    contract = load_method_contract(packs_root() / "methods" / "scrum")
    assert contract.optional_roles == []


@pytest.mark.parametrize(
    "optional",
    ['["developer"]', '["scrum-master", "scrum-master"]'],
)
def test_optional_roles_must_be_unique_and_disjoint_from_required_roles(tmp_path, optional):
    with pytest.raises(ValueError, match="unique and disjoint"):
        load_method_contract(optional_pack(tmp_path, optional=optional))


def test_an_optional_role_needs_a_valid_role_file(tmp_path):
    method = optional_pack(tmp_path)
    (method / "roles" / "scrum-master.md").unlink()
    with pytest.raises(ValueError, match="missing role files"):
        load_method_contract(method)


def test_unknown_roles_are_still_rejected_in_stage_roles(tmp_path):
    method = optional_pack(tmp_path, optional="[]")
    with pytest.raises(ValueError, match="unknown roles"):
        load_method_contract(method)


@pytest.fixture
def swarm(tmp_path, monkeypatch):
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    root = tmp_path / "project"
    root.mkdir()
    workspace = AgoraWorkspace(cwd=root)
    workspace.initialize(InitInput(integration="generic", default_method="scrum"))
    workspace.install_method(
        InstallMethodInput(source=str(optional_pack(tmp_path)), scope="project", force=True)
    )
    for actor in (
        AddActorInput("owner", "Owner", "human", ["backlog-management", "acceptance"], "project"),
        AddActorInput("dev", "Dev", "ai-agent", ["implementation"], "project"),
        AddActorInput(
            "facilitator", "Facilitator", "ai-agent", ["facilitation", "governance"], "project"
        ),
    ):
        workspace.add_actor(actor)
    record = workspace.create_swarm(
        CreateSwarmInput("delivery", "Optional roles", create_branch=False)
    )
    return workspace, record


def test_swarm_is_ready_without_the_optional_role_and_records_it(swarm):
    workspace, record = swarm
    assert record.required_roles == ["product-owner", "developer"] and record.optional_roles == [
        "scrum-master"
    ]
    workspace.assign_actor(AssignActorInput("delivery", "product-owner", "owner"))
    ready = workspace.assign_actor(AssignActorInput("delivery", "developer", "dev"))
    assert ready.status == "ready"
    assert workspace.show_swarm("delivery").optional_roles == ["scrum-master"]


def test_optional_role_can_be_assigned_later_and_validates(swarm):
    workspace, _ = swarm
    workspace.assign_actor(AssignActorInput("delivery", "product-owner", "owner"))
    workspace.assign_actor(AssignActorInput("delivery", "developer", "dev"))
    updated = workspace.assign_actor(AssignActorInput("delivery", "scrum-master", "facilitator"))
    assert (
        updated.assignments["scrum-master"] == "project:facilitator" and updated.status == "ready"
    )
    assert workspace.validate().ok


def test_undefined_roles_are_still_rejected_on_assignment(swarm):
    workspace, _ = swarm
    with pytest.raises(ValueError, match="is not defined by swarm"):
        workspace.assign_actor(AssignActorInput("delivery", "auditor", "owner"))


def test_legacy_swarm_files_without_optional_roles_load_and_render_unchanged(tmp_path, monkeypatch):
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    root = tmp_path / "project"
    root.mkdir()
    workspace = AgoraWorkspace(cwd=root)
    workspace.initialize(InitInput(integration="generic", default_method="scrum"))
    record = workspace.create_swarm(CreateSwarmInput("delivery", "Legacy", create_branch=False))
    text = (Path(record.path) / "SWARM.md").read_text(encoding="utf-8")
    assert "optional-roles" not in text and record.optional_roles == []
