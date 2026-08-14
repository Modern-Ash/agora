import os
import subprocess
import tempfile
from pathlib import Path

from agora.model import (
    AddActorInput,
    AddApprovalInput,
    AddArtifactInput,
    AddEvidenceInput,
    AssignActorInput,
    ConfigureInput,
    CreateSwarmInput,
    CreateWorkInput,
    InitInput,
    StartSessionInput,
    TransitionWorkInput,
    WorkActorInput,
)
from agora.workspace import AgoraWorkspace


def main() -> None:
    project = Path(tempfile.mkdtemp(prefix="agora-sample-project-"))
    os.environ["AGORA_HOME"] = tempfile.mkdtemp(prefix="agora-sample-home-")
    subprocess.run(["git", "init", "-q", str(project)], check=True)
    agora = AgoraWorkspace(cwd=project)

    print(f"Project: {project}")
    print("1. Configure the user and initialize a Codex-ready project")
    agora.configure(
        ConfigureInput(
            integration="codex",
            provider="openai",
            model="configured-by-codex",
            default_method="scrum",
        )
    )
    agora.initialize(InitInput())

    print("2. Register a human, an AI agent, and a nested swarm")
    agora.add_actor(
        AddActorInput(
            id="owner",
            name="Human Product Owner",
            kind="human",
            capabilities=["backlog-management", "acceptance"],
            scope="user",
        )
    )
    agora.add_actor(
        AddActorInput(
            id="facilitator",
            name="AI Facilitator",
            kind="ai-agent",
            capabilities=["facilitation", "governance"],
            scope="project",
        )
    )
    agora.add_actor(
        AddActorInput(
            id="delivery-swarm",
            name="Delivery Swarm",
            kind="swarm",
            capabilities=["implementation"],
            scope="project",
        )
    )

    print("3. Create an Agora branch and form the swarm")
    agora.create_swarm(
        CreateSwarmInput(id="first-slice", objective="Deliver governed Markdown-first work")
    )
    agora.assign_actor(
        AssignActorInput(swarm_id="first-slice", role_id="product-owner", actor_id="owner")
    )
    agora.assign_actor(
        AssignActorInput(swarm_id="first-slice", role_id="scrum-master", actor_id="facilitator")
    )
    agora.assign_actor(
        AssignActorInput(swarm_id="first-slice", role_id="developer", actor_id="delivery-swarm")
    )

    print("4. Create work and prepare a governed Codex session")
    agora.create_work(
        CreateWorkInput(
            swarm_id="first-slice",
            id="bootstrap",
            title="Bootstrap Agora",
            actor_id="owner",
            acceptance_criteria=[("installable", "Agora initializes locally")],
            required_artifacts=["source-code"],
        )
    )
    session = agora.start_session(
        StartSessionInput(
            id="bootstrap-session",
            actor_id="delivery-swarm",
            swarm_id="first-slice",
            work_id="bootstrap",
        )
    )
    print(f"   Session context: {session.context_path}")

    print("5. Advance through the graph, including Scrum Master verification")
    for state in ("planned", "implementing", "reviewing"):
        agora.transition_work(
            TransitionWorkInput(
                swarm_id="first-slice",
                work_id="bootstrap",
                actor_id="delivery-swarm",
                target_state=state,
            )
        )
    agora.transition_work(
        TransitionWorkInput(
            swarm_id="first-slice",
            work_id="bootstrap",
            actor_id="facilitator",
            target_state="verifying",
        )
    )

    print("6. Confirm that completion is rejected without artifacts and evidence")
    try:
        agora.transition_work(
            TransitionWorkInput(
                swarm_id="first-slice",
                work_id="bootstrap",
                actor_id="owner",
                target_state="completed",
            )
        )
    except ValueError as error:
        print(f"   Rejected: {error}")

    print("7. Satisfy the gate and complete")
    agora.satisfy_criterion(
        WorkActorInput(swarm_id="first-slice", work_id="bootstrap", actor_id="owner"),
        "installable",
    )
    agora.add_artifact(
        AddArtifactInput(
            swarm_id="first-slice",
            work_id="bootstrap",
            actor_id="delivery-swarm",
            kind="source-code",
            uri="repo://src/agora/workspace.py",
        )
    )
    agora.add_evidence(
        AddEvidenceInput(
            swarm_id="first-slice",
            work_id="bootstrap",
            actor_id="facilitator",
            type="test-run",
            result="success",
            artifact_refs=["repo://src/agora/workspace.py"],
        )
    )
    agora.add_approval(
        AddApprovalInput(
            swarm_id="first-slice",
            work_id="bootstrap",
            actor_id="owner",
            role_id="product-owner",
            note="The increment satisfies the objective",
        )
    )
    agora.transition_work(
        TransitionWorkInput(
            swarm_id="first-slice",
            work_id="bootstrap",
            actor_id="owner",
            target_state="completed",
        )
    )

    branch = subprocess.run(
        ["git", "-C", str(project), "branch", "--show-current"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    print(f"Branch: {branch}")
    print(f"Swarm: {agora.show_swarm('first-slice').status}")
    print(f"Work: {agora.show_work('first-slice', 'bootstrap').state}")
    print(f"Persisted at: {project / '.agora' / 'swarms' / 'first-slice'}")


if __name__ == "__main__":
    main()
