import os
import tempfile
from pathlib import Path

from agora.model import AddActorInput, AssignActorInput, CreateSwarmInput, InitInput
from agora.workspace import AgoraWorkspace


def main() -> None:
    project = Path(tempfile.mkdtemp(prefix="agora-recursive-project-"))
    os.environ["AGORA_HOME"] = tempfile.mkdtemp(prefix="agora-recursive-home-")
    agora = AgoraWorkspace(cwd=project)
    agora.initialize(
        InitInput(
            integration="generic",
            default_method="scrum",
            max_delegation_depth=1,
        )
    )

    for actor in (
        AddActorInput(
            id="owner",
            name="Owner",
            kind="human",
            capabilities=["backlog-management", "acceptance"],
            scope="project",
        ),
        AddActorInput(
            id="facilitator",
            name="Facilitator",
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

    def form_swarm(swarm_id: str, developer: str) -> None:
        agora.create_swarm(
            CreateSwarmInput(
                id=swarm_id,
                objective=f"Deliver the {swarm_id} objective",
                create_branch=False,
            )
        )
        for role, actor_id in (
            ("product-owner", "owner"),
            ("scrum-master", "facilitator"),
            ("developer", developer),
        ):
            agora.assign_actor(AssignActorInput(swarm_id=swarm_id, role_id=role, actor_id=actor_id))

    form_swarm("specialists", "developer")
    agora.add_actor(
        AddActorInput(
            id="specialist-swarm",
            name="Specialist Swarm",
            kind="swarm",
            capabilities=["implementation"],
            scope="project",
            represented_swarm="specialists",
        )
    )
    form_swarm("product-delivery", "specialist-swarm")
    agora.add_actor(
        AddActorInput(
            id="product-swarm",
            name="Product Delivery Swarm",
            kind="swarm",
            capabilities=["implementation"],
            scope="project",
            represented_swarm="product-delivery",
        )
    )

    agora.create_swarm(
        CreateSwarmInput(
            id="portfolio",
            objective="Attempt a second delegation level",
            create_branch=False,
        )
    )
    for role, actor_id in (
        ("product-owner", "owner"),
        ("scrum-master", "facilitator"),
    ):
        agora.assign_actor(AssignActorInput(swarm_id="portfolio", role_id=role, actor_id=actor_id))
    try:
        agora.assign_actor(
            AssignActorInput(
                swarm_id="portfolio",
                role_id="developer",
                actor_id="product-swarm",
            )
        )
    except ValueError as error:
        print(f"Rejected: {error}")

    print(f"Project: {project}")
    print("Delegation: product-delivery -> specialists")
    print(f"Parent status: {agora.show_swarm('product-delivery').status}")
    print(f"Child status: {agora.show_swarm('specialists').status}")
    print("Configured maximum depth: 1")


if __name__ == "__main__":
    main()
