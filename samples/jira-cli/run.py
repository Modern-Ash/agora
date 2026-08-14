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
    runtime = Path(tempfile.mkdtemp(prefix="agora-jira-cli-sample-"))
    project = runtime / "project"
    project.mkdir()
    os.environ["AGORA_HOME"] = str(runtime / "home")
    os.environ["AGORA_LOCK_HOME"] = str(runtime / "locks")
    agora = AgoraWorkspace(cwd=project)
    agora.initialize(InitInput(integration="generic", default_method="scrum"))
    agora.install_tool_adapter(InstallToolAdapterInput(adapter_id="jira", scope="project"))

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
            name="Delivery Agent",
            kind="ai-agent",
            capabilities=["implementation"],
            scope="project",
        ),
    ):
        agora.add_actor(actor)
    agora.create_swarm(
        CreateSwarmInput(
            id="delivery",
            objective="Manage Jira work through the existing Atlassian CLI",
            create_branch=False,
        )
    )
    for role, actor in (
        ("product-owner", "owner"),
        ("scrum-master", "facilitator"),
        ("developer", "developer"),
    ):
        agora.assign_actor(AssignActorInput(swarm_id="delivery", role_id=role, actor_id=actor))

    search = agora.invoke_tool(
        InvokeToolInput(
            id="search-jira-work",
            tool_id="jira",
            operation_id="search",
            actor_id="developer",
            swarm_id="delivery",
            inputs={"query": "project = AGORA AND status != Done"},
        )
    )
    transition = agora.invoke_tool(
        InvokeToolInput(
            id="transition-jira-work",
            tool_id="jira",
            operation_id="transition",
            actor_id="owner",
            swarm_id="delivery",
            inputs={"issue": "AGORA-42", "state": "In Progress"},
        )
    )
    try:
        agora.invoke_tool(
            InvokeToolInput(
                id="developer-jira-comment",
                tool_id="jira",
                operation_id="comment",
                actor_id="developer",
                swarm_id="delivery",
                inputs={"issue": "AGORA-42", "body": "Attempted write"},
            )
        )
    except PermissionError as error:
        rejected = str(error)
    else:
        raise AssertionError("Developer unexpectedly received issue.write authority")

    assert agora.validate().ok
    print(f"Project: {project}")
    print(f"Search command: {search.command}")
    print(f"Transition command: {transition.command}")
    print(f"ACLI available: {search.runtime_available}")
    print(f"Rejected comment: {rejected}")


if __name__ == "__main__":
    main()
