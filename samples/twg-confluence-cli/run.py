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
    runtime = Path(tempfile.mkdtemp(prefix="agora-twg-confluence-cli-sample-"))
    project = runtime / "project"
    project.mkdir()
    os.environ["AGORA_HOME"] = str(runtime / "home")
    os.environ["AGORA_LOCK_HOME"] = str(runtime / "locks")
    agora = AgoraWorkspace(cwd=project)
    agora.initialize(InitInput(integration="generic", default_method="scrum"))
    agora.install_tool_adapter(
        InstallToolAdapterInput(adapter_id="twg-confluence", scope="project")
    )

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
            name="Documentation Agent",
            kind="ai-agent",
            capabilities=["implementation"],
            scope="project",
        ),
    ):
        agora.add_actor(actor)
    agora.create_swarm(
        CreateSwarmInput(
            id="delivery",
            objective="Maintain reviewed Confluence documentation",
            create_branch=False,
        )
    )
    for role, actor in (
        ("product-owner", "owner"),
        ("scrum-master", "facilitator"),
        ("developer", "developer"),
    ):
        agora.assign_actor(AssignActorInput(swarm_id="delivery", role_id=role, actor_id=actor))

    viewed = agora.invoke_tool(
        InvokeToolInput(
            id="view-runbook",
            tool_id="twg-confluence",
            operation_id="view",
            actor_id="developer",
            swarm_id="delivery",
            inputs={"document": "12345"},
        )
    )
    updated = agora.invoke_tool(
        InvokeToolInput(
            id="update-runbook-draft",
            tool_id="twg-confluence",
            operation_id="update",
            actor_id="developer",
            swarm_id="delivery",
            inputs={
                "document": "12345",
                "title": "Delivery runbook",
                "body": "<p>Reviewed recovery steps.</p>",
                "snapshot-token": "v:7",
            },
        )
    )
    try:
        agora.invoke_tool(
            InvokeToolInput(
                id="unsafe-update",
                tool_id="twg-confluence",
                operation_id="update",
                actor_id="developer",
                swarm_id="delivery",
                inputs={
                    "document": "12345",
                    "title": "Unsafe update",
                    "body": "<p>No concurrency token.</p>",
                },
            )
        )
    except ValueError as error:
        rejected_update = str(error)
    else:
        raise AssertionError("Confluence update unexpectedly omitted its snapshot token")
    try:
        agora.invoke_tool(
            InvokeToolInput(
                id="unsupported-search",
                tool_id="twg-confluence",
                operation_id="search",
                actor_id="developer",
                swarm_id="delivery",
                inputs={"space": "ENG", "query": "delivery"},
            )
        )
    except FileNotFoundError as error:
        rejected_search = str(error)
    else:
        raise AssertionError("Confluence adapter unexpectedly exposed unsafe search translation")

    assert agora.validate().ok
    print(f"Project: {project}")
    print(f"View command: {viewed.command}")
    print(f"Update command: {updated.command}")
    print(f"Rejected update: {rejected_update}")
    print(f"Rejected search: {rejected_search}")


if __name__ == "__main__":
    main()
