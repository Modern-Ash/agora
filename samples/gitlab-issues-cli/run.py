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
    runtime = Path(tempfile.mkdtemp(prefix="agora-gitlab-issues-cli-sample-"))
    project = runtime / "project"
    project.mkdir()
    os.environ["AGORA_HOME"] = str(runtime / "home")
    os.environ["AGORA_LOCK_HOME"] = str(runtime / "locks")
    agora = AgoraWorkspace(cwd=project)
    agora.initialize(InitInput(integration="generic", default_method="scrum"))
    agora.install_tool_adapter(InstallToolAdapterInput(adapter_id="gitlab-issues", scope="project"))

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
            objective="Manage work through the existing GitLab CLI",
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
            id="search-gitlab-issues",
            tool_id="gitlab-issues",
            operation_id="search",
            actor_id="developer",
            swarm_id="delivery",
            inputs={"query": "governance"},
        )
    )
    transition = agora.invoke_tool(
        InvokeToolInput(
            id="close-gitlab-issue",
            tool_id="gitlab-issues",
            operation_id="transition",
            actor_id="owner",
            swarm_id="delivery",
            inputs={"issue": "42", "state": "close"},
        )
    )
    try:
        agora.invoke_tool(
            InvokeToolInput(
                id="delete-through-transition",
                tool_id="gitlab-issues",
                operation_id="transition",
                actor_id="owner",
                swarm_id="delivery",
                inputs={"issue": "42", "state": "delete"},
            )
        )
    except ValueError as error:
        rejected_transition = str(error)
    else:
        raise AssertionError("Unsafe GitLab issue subcommand was unexpectedly accepted")
    try:
        agora.invoke_tool(
            InvokeToolInput(
                id="unsupported-create",
                tool_id="gitlab-issues",
                operation_id="create",
                actor_id="owner",
                swarm_id="delivery",
                inputs={
                    "project": "example/agora",
                    "type": "Task",
                    "title": "Unsupported create",
                    "description": "No exact native type mapping exists.",
                },
            )
        )
    except FileNotFoundError as error:
        rejected_create = str(error)
    else:
        raise AssertionError("GitLab adapter unexpectedly exposed issue creation")

    assert agora.validate().ok
    print(f"Project: {project}")
    print(f"Search command: {search.command}")
    print(f"Transition command: {transition.command}")
    print(f"CLI available: {search.runtime_available}")
    print(f"Rejected transition: {rejected_transition}")
    print(f"Rejected create: {rejected_create}")


if __name__ == "__main__":
    main()
