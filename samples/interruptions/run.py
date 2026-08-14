import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path

from agora.model import (
    AddActorInput,
    AssignActorInput,
    ChangeDelegationStatusInput,
    ChangeWorkStatusInput,
    CreateDelegationInput,
    CreateSwarmInput,
    CreateWorkInput,
    DelegationActorInput,
    InitInput,
)
from agora.workspace import AgoraWorkspace


def main() -> None:
    project = Path(tempfile.mkdtemp(prefix="agora-interruptions-project-"))
    os.environ["AGORA_HOME"] = tempfile.mkdtemp(prefix="agora-interruptions-home-")
    agora = AgoraWorkspace(cwd=project)
    agora.initialize(InitInput(integration="generic", default_method="scrum"))

    for actor in (
        AddActorInput(
            id="owner",
            name="Product Owner",
            kind="human",
            capabilities=["backlog-management", "acceptance"],
            scope="project",
        ),
        AddActorInput(
            id="facilitator",
            name="Scrum Master",
            kind="ai-agent",
            capabilities=["facilitation", "governance"],
            scope="project",
        ),
        AddActorInput(
            id="specialist",
            name="Specialist",
            kind="ai-agent",
            capabilities=["implementation"],
            scope="project",
        ),
    ):
        agora.add_actor(actor)

    form_swarm(agora, "specialists", "specialist")
    agora.add_actor(
        AddActorInput(
            id="specialist-swarm",
            name="Specialist Swarm",
            kind="swarm",
            capabilities=["implementation"],
            represented_swarm="specialists",
            scope="project",
        )
    )
    form_swarm(agora, "delivery", "specialist-swarm")
    agora.create_work(
        CreateWorkInput(
            swarm_id="delivery",
            id="parent-work",
            title="Integrate a specialist result",
            actor_id="owner",
        )
    )

    agora.block_work(
        ChangeWorkStatusInput(
            swarm_id="delivery",
            work_id="parent-work",
            actor_id="specialist-swarm",
            reason="The child contract needs clarification",
        )
    )
    agora.resume_work(
        ChangeWorkStatusInput(
            swarm_id="delivery",
            work_id="parent-work",
            actor_id="facilitator",
            reason="The child contract is now explicit",
        )
    )

    cancellable = agora.create_delegation(
        CreateDelegationInput(
            id="cancellable-task",
            parent_swarm_id="delivery",
            parent_work_id="parent-work",
            child_actor_id="specialist-swarm",
            child_work_id="cancellable-child-work",
            actor_id="specialist-swarm",
            title="Produce a bounded specialist result",
        )
    )
    agora.block_delegation(
        ChangeDelegationStatusInput(
            delegation_id=cancellable.id,
            actor_id="facilitator",
            reason="Confirm the expected result boundary",
        )
    )
    agora.resume_delegation(
        ChangeDelegationStatusInput(
            delegation_id=cancellable.id,
            actor_id="facilitator",
            reason="The boundary is confirmed",
        )
    )
    agora.accept_delegation(DelegationActorInput(delegation_id=cancellable.id, actor_id="owner"))
    agora.cancel_delegation(
        ChangeDelegationStatusInput(
            delegation_id=cancellable.id,
            actor_id="owner",
            reason="The parent objective no longer needs this result",
        )
    )

    rejectable = agora.create_delegation(
        CreateDelegationInput(
            id="rejectable-task",
            parent_swarm_id="delivery",
            parent_work_id="parent-work",
            child_actor_id="specialist-swarm",
            child_work_id="rejected-child-work",
            actor_id="specialist-swarm",
            title="Request work outside the child boundary",
        )
    )
    agora.reject_delegation(
        ChangeDelegationStatusInput(
            delegation_id=rejectable.id,
            actor_id="owner",
            reason="The child swarm cannot satisfy this contract",
        )
    )

    report = agora.validate()
    if not report.ok:
        raise RuntimeError(json.dumps(asdict(report), indent=2))

    print(f"Project: {project}")
    print("Work status history:")
    print(
        json.dumps(
            [asdict(item) for item in agora.list_work_status_changes("delivery", "parent-work")],
            indent=2,
        )
    )
    print("Delegation status history:")
    print(
        json.dumps(
            [asdict(item) for item in agora.list_delegation_status_changes(cancellable.id)],
            indent=2,
        )
    )
    print("Workspace status:")
    print(json.dumps(asdict(agora.status()), indent=2))


def form_swarm(agora: AgoraWorkspace, swarm_id: str, developer: str) -> None:
    agora.create_swarm(
        CreateSwarmInput(
            id=swarm_id,
            objective=f"Deliver {swarm_id} work",
            create_branch=False,
        )
    )
    for role, actor in (
        ("product-owner", "owner"),
        ("scrum-master", "facilitator"),
        ("developer", developer),
    ):
        agora.assign_actor(AssignActorInput(swarm_id=swarm_id, role_id=role, actor_id=actor))


if __name__ == "__main__":
    main()
