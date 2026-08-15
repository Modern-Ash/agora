import os
import tempfile
from pathlib import Path

from agora.model import (
    AddActorInput,
    AssignActorInput,
    CreateSwarmInput,
    CreateWorkInput,
    InitInput,
    TransitionWorkInput,
    WaiveGateInput,
)
from agora.workspace import AgoraWorkspace


def main() -> None:
    project = Path(tempfile.mkdtemp(prefix="agora-gate-waiver-project-"))
    os.environ["AGORA_HOME"] = tempfile.mkdtemp(prefix="agora-gate-waiver-home-")
    agora = AgoraWorkspace(cwd=project)
    agora.initialize(InitInput(integration="generic", default_method="scrum"))

    actors = (
        ("owner", "Product Owner", ["backlog-management", "acceptance"]),
        ("facilitator", "Scrum Master", ["facilitation", "governance"]),
        ("developer", "Developer", ["implementation"]),
    )
    for actor_id, name, capabilities in actors:
        agora.add_actor(
            AddActorInput(
                id=actor_id,
                name=name,
                kind="human",
                capabilities=capabilities,
                scope="project",
            )
        )
    agora.create_swarm(
        CreateSwarmInput(id="delivery", objective="Release with explicit risk", create_branch=False)
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
            id="release-candidate",
            title="Release the candidate",
            actor_id="owner",
            acceptance_criteria=[("load-test", "Complete the external load test")],
            required_artifacts=["performance-report"],
        )
    )
    for state, actor_id in (
        ("planned", "developer"),
        ("implementing", "developer"),
        ("reviewing", "developer"),
        ("verifying", "facilitator"),
    ):
        agora.transition_work(
            TransitionWorkInput(
                swarm_id="delivery",
                work_id="release-candidate",
                actor_id=actor_id,
                target_state=state,
            )
        )

    completion = TransitionWorkInput(
        swarm_id="delivery",
        work_id="release-candidate",
        actor_id="owner",
        target_state="completed",
    )
    try:
        agora.transition_work(completion)
    except ValueError as error:
        print(f"Rejected completion: {error}")

    waiver = agora.waive_gate(
        WaiveGateInput(
            id="accepted-release-risk",
            swarm_id="delivery",
            work_id="release-candidate",
            gate_id="completion",
            actor_id="owner",
            reason="Product governance accepted the external service outage risk",
            evidence_refs=["repo://risk/accepted-release-risk.md"],
            criteria=["load-test"],
            artifacts=["performance-report"],
            successful_evidence=True,
            approval_roles=["product-owner"],
        )
    )
    completed = agora.transition_work(completion)

    print(f"Project: {project}")
    print(f"Waiver: {waiver.path}")
    print(f"State: {completed.state}")
    print(f"Validation issues: {len(agora.validate().issues)}")


if __name__ == "__main__":
    main()
