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
    runtime = Path(tempfile.mkdtemp(prefix="agora-cloud-inventory-cli-sample-"))
    project = runtime / "project"
    project.mkdir()
    os.environ["AGORA_HOME"] = str(runtime / "home")
    os.environ["AGORA_LOCK_HOME"] = str(runtime / "locks")
    agora = AgoraWorkspace(cwd=project)
    agora.initialize(InitInput(integration="generic", default_method="scrum"))
    for adapter_id in ("aws-resource-inventory", "gcp-asset-inventory"):
        agora.install_tool_adapter(InstallToolAdapterInput(adapter_id=adapter_id, scope="project"))

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
            name="Cloud Inventory Agent",
            kind="ai-agent",
            capabilities=["implementation"],
            scope="project",
        ),
    ):
        agora.add_actor(actor)
    agora.create_swarm(
        CreateSwarmInput(
            id="delivery",
            objective="Inspect cloud inventory without deployment authority",
            create_branch=False,
        )
    )
    for role, actor in (
        ("product-owner", "owner"),
        ("scrum-master", "facilitator"),
        ("developer", "developer"),
    ):
        agora.assign_actor(AssignActorInput(swarm_id="delivery", role_id=role, actor_id=actor))

    aws = agora.invoke_tool(
        InvokeToolInput(
            id="list-aws-resources",
            tool_id="aws-resource-inventory",
            operation_id="list-resources",
            actor_id="developer",
            swarm_id="delivery",
            inputs={"environment": "us-east-1"},
        )
    )
    gcp = agora.invoke_tool(
        InvokeToolInput(
            id="list-gcp-resources",
            tool_id="gcp-asset-inventory",
            operation_id="list-resources",
            actor_id="developer",
            swarm_id="delivery",
            inputs={"environment": "projects/agora-production"},
        )
    )
    try:
        agora.invoke_tool(
            InvokeToolInput(
                id="unsupported-aws-plan",
                tool_id="aws-resource-inventory",
                operation_id="plan",
                actor_id="developer",
                swarm_id="delivery",
                inputs={"environment": "us-east-1", "change": "capacity"},
            )
        )
    except FileNotFoundError as error:
        rejected = str(error)
    else:
        raise AssertionError("Read-only AWS adapter unexpectedly exposed plan")

    assert agora.validate().ok
    print(f"Project: {project}")
    print(f"AWS command: {aws.command}")
    print(f"GCP command: {gcp.command}")
    print(f"Rejected plan: {rejected}")


if __name__ == "__main__":
    main()
