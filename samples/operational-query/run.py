import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path

from agora.model import (
    AddActorInput,
    AssignActorInput,
    CreateSwarmInput,
    CreateWorkInput,
    InitInput,
    StartSessionInput,
)
from agora.workspace import AgoraWorkspace


def main() -> None:
    project = Path(tempfile.mkdtemp(prefix="agora-operational-query-project-"))
    os.environ["AGORA_HOME"] = tempfile.mkdtemp(prefix="agora-operational-query-home-")
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
            objective="Expose inspectable operational state",
            create_branch=False,
        )
    )
    for role, actor_id in (
        ("product-owner", "owner"),
        ("scrum-master", "facilitator"),
        ("developer", "developer"),
    ):
        agora.assign_actor(AssignActorInput(swarm_id="delivery", role_id=role, actor_id=actor_id))
    agora.create_work(
        CreateWorkInput(
            swarm_id="delivery",
            id="inspect-state",
            title="Inspect durable project state",
            actor_id="owner",
        )
    )
    agora.start_session(
        StartSessionInput(
            id="inspection-session",
            actor_id="developer",
            swarm_id="delivery",
            work_id="inspect-state",
        )
    )

    status = agora.status()
    report = agora.validate()
    events = agora.list_events(
        swarm_id="delivery",
        work_id="inspect-state",
        limit=5,
    )

    print(f"Project: {project}")
    print("Status:")
    print(json.dumps(asdict(status), indent=2))
    print("Validation:")
    print(json.dumps(asdict(report), indent=2))
    print("Recent work events:")
    print(json.dumps([asdict(event) for event in events], indent=2))


if __name__ == "__main__":
    main()
