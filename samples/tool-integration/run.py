import os
import subprocess
import tempfile
from pathlib import Path

from agora.model import (
    AddActorInput,
    AssignActorInput,
    CreateSwarmInput,
    InitInput,
    InvokeToolInput,
)
from agora.workspace import AgoraWorkspace


def main() -> None:
    project = Path(tempfile.mkdtemp(prefix="agora-tool-project-"))
    os.environ["AGORA_HOME"] = tempfile.mkdtemp(prefix="agora-tool-home-")
    subprocess.run(["git", "init", "-q", str(project)], check=True)
    (project / "README.md").write_text("# Governed project\n")
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
            name="Flow Facilitator",
            kind="ai-agent",
            capabilities=["facilitation", "governance"],
            scope="project",
        ),
        AddActorInput(
            id="developer",
            name="Delivery Agent",
            kind="ai-agent",
            capabilities=["implementation"],
            scope="project",
        ),
    ):
        agora.add_actor(actor)

    agora.create_swarm(
        CreateSwarmInput(
            id="tool-demo",
            objective="Inspect the repository through a governed tool operation",
        )
    )
    for role, actor_id in (
        ("product-owner", "owner"),
        ("scrum-master", "facilitator"),
        ("developer", "developer"),
    ):
        agora.assign_actor(AssignActorInput(swarm_id="tool-demo", role_id=role, actor_id=actor_id))

    run = agora.invoke_tool(
        InvokeToolInput(
            id="repository-status",
            tool_id="repository",
            operation_id="status",
            actor_id="developer",
            swarm_id="tool-demo",
            launch=True,
        )
    )
    print(f"Project: {project}")
    print(f"Tool: {run.tool_id}/{run.operation_id}")
    print(f"Actor: {run.actor}")
    print(f"Status: {run.status} (exit {run.exit_code})")
    print(f"Invocation: {Path(run.path) / 'RUN.md'}")
    print(f"Result: {Path(run.path) / 'RESULT.md'}")


if __name__ == "__main__":
    main()
