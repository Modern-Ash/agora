import os
import tempfile
from pathlib import Path

from agora.model import (
    AddActorInput,
    AssignActorInput,
    CreateSwarmInput,
    CreateWorkInput,
    HandoffActorInput,
    InitInput,
    TransitionWorkInput,
)
from agora.workspace import AgoraWorkspace


def main() -> None:
    project = Path(tempfile.mkdtemp(prefix="agora-handoff-project-"))
    os.environ["AGORA_HOME"] = tempfile.mkdtemp(prefix="agora-handoff-home-")
    agora = AgoraWorkspace(cwd=project)
    agora.initialize(InitInput(integration="generic", default_method="scrum"))

    actors = (
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
            id="human-developer",
            name="Human Developer",
            kind="human",
            capabilities=["implementation"],
            scope="project",
        ),
        AddActorInput(
            id="ai-developer",
            name="AI Developer",
            kind="ai-agent",
            capabilities=["implementation"],
            scope="project",
        ),
        AddActorInput(
            id="delivery-swarm",
            name="Delivery Swarm",
            kind="swarm",
            capabilities=["implementation"],
            scope="project",
        ),
    )
    for actor in actors:
        agora.add_actor(actor)

    agora.create_swarm(
        CreateSwarmInput(
            id="delivery",
            objective="Continue one delivery across different actor forms",
            create_branch=False,
        )
    )
    for role, actor_id in (
        ("product-owner", "owner"),
        ("scrum-master", "facilitator"),
        ("developer", "human-developer"),
    ):
        agora.assign_actor(AssignActorInput(swarm_id="delivery", role_id=role, actor_id=actor_id))
    agora.create_work(
        CreateWorkInput(
            swarm_id="delivery",
            id="continuity",
            title="Preserve governed execution continuity",
            actor_id="owner",
        )
    )
    agora.transition_work(
        TransitionWorkInput(
            swarm_id="delivery",
            work_id="continuity",
            actor_id="human-developer",
            target_state="planned",
        )
    )

    first = agora.handoff_actor(
        HandoffActorInput(
            id="human-to-ai",
            swarm_id="delivery",
            role_id="developer",
            from_actor_id="human-developer",
            to_actor_id="ai-developer",
            authorized_by="human-developer",
            reason="The plan is ready for autonomous implementation",
            work_id="continuity",
        )
    )
    agora.transition_work(
        TransitionWorkInput(
            swarm_id="delivery",
            work_id="continuity",
            actor_id="ai-developer",
            target_state="implementing",
        )
    )
    second = agora.handoff_actor(
        HandoffActorInput(
            id="ai-to-swarm",
            swarm_id="delivery",
            role_id="developer",
            from_actor_id="ai-developer",
            to_actor_id="delivery-swarm",
            authorized_by="facilitator",
            reason="The implementation now benefits from parallel specialists",
            work_id="continuity",
        )
    )

    swarm = agora.show_swarm("delivery")
    print(f"Project: {project}")
    print(f"First handoff: {first.from_actor} -> {first.to_actor}")
    print(f"Second handoff: {second.from_actor} -> {second.to_actor}")
    print(f"Current Developer: {swarm.assignments['developer']}")
    print(f"Work state: {agora.show_work('delivery', 'continuity').state}")
    print(f"History: {project / '.agora' / 'swarms' / 'delivery' / 'handoffs'}")


if __name__ == "__main__":
    main()
