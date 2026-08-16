import os
import tempfile
from pathlib import Path

from agora.markdown import read_markdown, strings_attribute
from agora.methods import load_method_contract
from agora.model import (
    AddActorInput,
    AddApprovalInput,
    AddArtifactInput,
    AddEvidenceInput,
    AssignActorInput,
    CreateSwarmInput,
    CreateWorkInput,
    InitInput,
    TransitionWorkInput,
    WorkActorInput,
)
from agora.workspace import AgoraWorkspace

BUNDLED_METHODS = ("spec-driven", "scrum", "kanban")
ACTOR_KINDS = ("human", "ai-agent", "swarm")


def _role_capabilities(project: Path, method_id: str, roles: list[str]) -> list[str]:
    capabilities: set[str] = set()
    role_root = project / ".agora" / "methods" / method_id / "roles"
    for role_id in roles:
        attributes = read_markdown(role_root / f"{role_id}.md").attributes
        capabilities.update(strings_attribute(attributes, "required-capabilities"))
    return sorted(capabilities)


def _add_swarm_actor(
    workspace: AgoraWorkspace,
    *,
    method_id: str,
    capabilities: list[str],
) -> str:
    helper_id = "child-human"
    workspace.add_actor(
        AddActorInput(
            id=helper_id,
            name="Child human",
            kind="human",
            capabilities=capabilities,
            scope="project",
        )
    )
    child = workspace.create_swarm(
        CreateSwarmInput(
            id="child-team",
            objective="Provide a ready nested swarm for role conformance",
            method=method_id,
            create_branch=False,
        )
    )
    for role_id in child.required_roles:
        workspace.assign_actor(
            AssignActorInput(swarm_id=child.id, role_id=role_id, actor_id=helper_id)
        )

    actor_id = "candidate"
    workspace.add_actor(
        AddActorInput(
            id=actor_id,
            name="Candidate swarm",
            kind="swarm",
            capabilities=capabilities,
            scope="project",
            represented_swarm=child.id,
        )
    )
    return actor_id


def _forward_transition(contract, state: str):
    state_index = {item: index for index, item in enumerate(contract.work_states)}
    candidates = [
        transition
        for transition in contract.transitions
        if transition.source == state
        and state_index[transition.target] > state_index[transition.source]
    ]
    if not candidates:
        raise ValueError(f"No forward transition from {contract.id}/{state}")
    return min(candidates, key=lambda item: state_index[item.target])


def _run_case(root: Path, method_id: str, actor_kind: str) -> dict[str, object]:
    project = root / f"{method_id}-{actor_kind}"
    project.mkdir()
    workspace = AgoraWorkspace(cwd=project)
    workspace.initialize(InitInput(integration="generic", default_method=method_id))
    contract = load_method_contract(project / ".agora" / "methods" / method_id)
    capabilities = _role_capabilities(project, method_id, contract.required_roles)

    service_id = "disallowed-service"
    workspace.add_actor(
        AddActorInput(
            id=service_id,
            name="Disallowed service",
            kind="service",
            capabilities=capabilities,
            scope="project",
        )
    )
    if actor_kind == "swarm":
        actor_id = _add_swarm_actor(
            workspace,
            method_id=method_id,
            capabilities=capabilities,
        )
    else:
        actor_id = "candidate"
        workspace.add_actor(
            AddActorInput(
                id=actor_id,
                name=f"Candidate {actor_kind}",
                kind=actor_kind,
                capabilities=capabilities,
                scope="project",
            )
        )

    swarm = workspace.create_swarm(
        CreateSwarmInput(
            id="delivery",
            objective=f"Exercise {method_id} with a {actor_kind} actor",
            method=method_id,
            create_branch=False,
        )
    )
    rejected = 0
    for role_id in contract.required_roles:
        try:
            workspace.assign_actor(
                AssignActorInput(swarm_id=swarm.id, role_id=role_id, actor_id=service_id)
            )
        except ValueError as error:
            if "Actor kind service is not allowed for role" not in str(error):
                raise
            rejected += 1
        else:
            raise AssertionError(f"{method_id}/{role_id} accepted disallowed service actor")
        workspace.assign_actor(
            AssignActorInput(swarm_id=swarm.id, role_id=role_id, actor_id=actor_id)
        )

    work = workspace.create_work(
        CreateWorkInput(
            swarm_id=swarm.id,
            id="self-test",
            title="Exercise the complete governed lifecycle",
            actor_id=actor_id,
            acceptance_criteria=[("verified", "The role matrix is verified")],
            required_artifacts=["spec"],
        )
    )
    work_actor = WorkActorInput(swarm_id=swarm.id, work_id=work.id, actor_id=actor_id)
    workspace.satisfy_criterion(work_actor, "verified")
    artifact_uri = "repo://self-test/spec.md"
    workspace.add_artifact(
        AddArtifactInput(
            swarm_id=swarm.id,
            work_id=work.id,
            actor_id=actor_id,
            kind="spec",
            uri=artifact_uri,
        )
    )
    workspace.add_evidence(
        AddEvidenceInput(
            swarm_id=swarm.id,
            work_id=work.id,
            actor_id=actor_id,
            type="self-test",
            result="success",
            artifact_refs=[artifact_uri],
        )
    )
    approval_roles = sorted(
        {role_id for gate in contract.gates.values() for role_id in gate.required_approval_roles}
    )
    for role_id in approval_roles:
        workspace.add_approval(
            AddApprovalInput(
                swarm_id=swarm.id,
                work_id=work.id,
                actor_id=actor_id,
                role_id=role_id,
                note="Self-test approval",
            )
        )

    while work.state != contract.terminal_state:
        transition = _forward_transition(contract, work.state)
        work = workspace.transition_work(
            TransitionWorkInput(
                swarm_id=swarm.id,
                work_id=work.id,
                actor_id=actor_id,
                target_state=transition.target,
            )
        )

    validation = workspace.validate()
    if not validation.ok:
        issue_codes = ", ".join(issue.code for issue in validation.issues)
        raise ValueError(f"Self-test workspace is invalid: {method_id}/{actor_kind}: {issue_codes}")
    return {
        "method": method_id,
        "actor_kind": actor_kind,
        "roles": contract.required_roles,
        "terminal_state": work.state,
        "disallowed_assignments_rejected": rejected,
    }


def run_role_self_test() -> dict[str, object]:
    previous_home = os.environ.get("AGORA_HOME")
    try:
        with tempfile.TemporaryDirectory(prefix="agora-self-test-") as directory:
            root = Path(directory)
            os.environ["AGORA_HOME"] = str(root / "home")
            cases = [
                _run_case(root, method_id, actor_kind)
                for method_id in BUNDLED_METHODS
                for actor_kind in ACTOR_KINDS
            ]
    finally:
        if previous_home is None:
            os.environ.pop("AGORA_HOME", None)
        else:
            os.environ["AGORA_HOME"] = previous_home

    return {
        "ok": True,
        "scope": "bundled-role-conformance",
        "methods": len(BUNDLED_METHODS),
        "actor_kinds": list(ACTOR_KINDS),
        "cases": cases,
        "role_assignments_verified": sum(len(case["roles"]) for case in cases),
        "disallowed_assignments_rejected": sum(
            int(case["disallowed_assignments_rejected"]) for case in cases
        ),
    }
