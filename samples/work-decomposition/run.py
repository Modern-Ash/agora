import os
import tempfile
from pathlib import Path

from agora.model import (
    AddActorInput,
    AssignActorInput,
    ChangeWorkStatusInput,
    CreateSwarmInput,
    CreateWorkInput,
    DecomposeWorkInput,
    InitInput,
)
from agora.workspace import AgoraWorkspace


def main() -> None:
    project = Path(tempfile.mkdtemp(prefix="agora-work-decomposition-project-"))
    os.environ["AGORA_HOME"] = tempfile.mkdtemp(prefix="agora-work-decomposition-home-")
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
            id="developer",
            name="Developer",
            kind="ai-agent",
            capabilities=["implementation"],
            scope="project",
        ),
    ):
        agora.add_actor(actor)

    agora.create_swarm(
        CreateSwarmInput(
            id="delivery",
            objective="Deliver a decomposed outcome",
            create_branch=False,
        )
    )
    for role, actor in (
        ("product-owner", "owner"),
        ("scrum-master", "facilitator"),
        ("developer", "developer"),
    ):
        agora.assign_actor(AssignActorInput(swarm_id="delivery", role_id=role, actor_id=actor))

    agora.create_work(
        CreateWorkInput(
            swarm_id="delivery",
            id="parent-outcome",
            title="Deliver the parent outcome",
            actor_id="owner",
        )
    )
    for child_id, title in (
        ("api-contract", "Define the API contract"),
        ("api-tests", "Verify the API contract"),
    ):
        agora.decompose_work(
            DecomposeWorkInput(
                swarm_id="delivery",
                parent_work_id="parent-outcome",
                child_work_id=child_id,
                title=title,
                actor_id="owner",
            )
        )

    try:
        agora.cancel_work(
            ChangeWorkStatusInput(
                swarm_id="delivery",
                work_id="parent-outcome",
                actor_id="owner",
                reason="Demonstrate the closure invariant",
            )
        )
    except ValueError as error:
        print(f"Rejected parent closure: {error}")

    for child_id in ("api-contract", "api-tests"):
        agora.cancel_work(
            ChangeWorkStatusInput(
                swarm_id="delivery",
                work_id=child_id,
                actor_id="owner",
                reason="The sample closes this child explicitly",
            )
        )
    agora.cancel_work(
        ChangeWorkStatusInput(
            swarm_id="delivery",
            work_id="parent-outcome",
            actor_id="owner",
            reason="Every child contract is now closed",
        )
    )

    parent = agora.show_work("delivery", "parent-outcome")
    print(f"Project: {project}")
    print(f"Parent: {parent.operational_status}")
    print(f"Children: {', '.join(parent.child_work_refs)}")
    print(f"Validation issues: {len(agora.validate().issues)}")


if __name__ == "__main__":
    main()
