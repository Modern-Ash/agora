import os
import tempfile
from pathlib import Path

from agora.model import (
    AddActorInput,
    AssignActorInput,
    CreateSwarmInput,
    InitInput,
    InstallToolAdapterInput,
    InvokeToolInput,
)
from agora.workspace import AgoraWorkspace


def main() -> None:
    runtime = Path(tempfile.mkdtemp(prefix="agora-github-actions-cli-sample-"))
    project = runtime / "project"
    project.mkdir()
    os.environ["AGORA_HOME"] = str(runtime / "home")
    os.environ["AGORA_LOCK_HOME"] = str(runtime / "locks")
    agora = AgoraWorkspace(cwd=project)
    agora.initialize(InitInput(integration="generic", default_method="scrum"))
    agora.install_tool_adapter(
        InstallToolAdapterInput(adapter_id="github-actions", scope="project")
    )

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
            id="developer",
            name="Delivery Agent",
            kind="ai-agent",
            capabilities=["implementation"],
            scope="project",
        ),
    )
    for actor in actors:
        agora.add_actor(actor)
    agora.create_swarm(
        CreateSwarmInput(
            id="delivery",
            objective="Run GitHub Actions through the developer's existing CLI",
            create_branch=False,
        )
    )
    for role, actor in (
        ("product-owner", "owner"),
        ("scrum-master", "facilitator"),
        ("developer", "developer"),
    ):
        agora.assign_actor(AssignActorInput(swarm_id="delivery", role_id=role, actor_id=actor))

    listed = agora.invoke_tool(
        InvokeToolInput(
            id="list-github-runs",
            tool_id="github-actions",
            operation_id="list-runs",
            actor_id="developer",
            swarm_id="delivery",
            inputs={"pipeline": "verify.yml"},
        )
    )
    triggered = agora.invoke_tool(
        InvokeToolInput(
            id="trigger-github-verification",
            tool_id="github-actions",
            operation_id="trigger",
            actor_id="developer",
            swarm_id="delivery",
            inputs={"pipeline": "verify.yml", "ref": "main", "parameters": "suite=all"},
        )
    )
    try:
        agora.invoke_tool(
            InvokeToolInput(
                id="cancel-github-run",
                tool_id="github-actions",
                operation_id="cancel-run",
                actor_id="developer",
                swarm_id="delivery",
                inputs={"run": "123"},
            )
        )
    except PermissionError as error:
        rejected = str(error)
    else:
        raise AssertionError("Developer unexpectedly received ci.cancel authority")

    assert listed.command[:3] == ["gh", "run", "list"]
    assert triggered.command[:3] == ["gh", "workflow", "run"]
    assert agora.validate().ok
    print(f"Project: {project}")
    print(f"List command: {listed.command}")
    print(f"Trigger command: {triggered.command}")
    print(f"CLI available: {listed.runtime_available}")
    print(f"Rejected cancel: {rejected}")


if __name__ == "__main__":
    main()
