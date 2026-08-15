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
    runtime = Path(tempfile.mkdtemp(prefix="agora-terraform-cli-sample-"))
    project = runtime / "project"
    project.mkdir()
    os.environ["AGORA_HOME"] = str(runtime / "home")
    os.environ["AGORA_LOCK_HOME"] = str(runtime / "locks")
    agora = AgoraWorkspace(cwd=project)
    agora.initialize(InitInput(integration="generic", default_method="scrum"))
    agora.install_tool_adapter(InstallToolAdapterInput(adapter_id="terraform", scope="project"))

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
            name="Infrastructure Agent",
            kind="ai-agent",
            capabilities=["implementation"],
            scope="project",
        ),
    ):
        agora.add_actor(actor)
    agora.create_swarm(
        CreateSwarmInput(
            id="delivery",
            objective="Plan infrastructure through the existing Terraform CLI",
            create_branch=False,
        )
    )
    for role, actor in (
        ("product-owner", "owner"),
        ("scrum-master", "facilitator"),
        ("developer", "developer"),
    ):
        agora.assign_actor(AssignActorInput(swarm_id="delivery", role_id=role, actor_id=actor))

    resources = agora.invoke_tool(
        InvokeToolInput(
            id="list-terraform-resources",
            tool_id="terraform",
            operation_id="list-resources",
            actor_id="developer",
            swarm_id="delivery",
            inputs={"environment": "infra/staging"},
        )
    )
    plan = agora.invoke_tool(
        InvokeToolInput(
            id="plan-terraform-capacity",
            tool_id="terraform",
            operation_id="plan",
            actor_id="developer",
            swarm_id="delivery",
            inputs={"environment": "infra/staging", "change": "plans/capacity.tfplan"},
        )
    )
    try:
        agora.invoke_tool(
            InvokeToolInput(
                id="apply-terraform-capacity",
                tool_id="terraform",
                operation_id="apply-plan",
                actor_id="developer",
                swarm_id="delivery",
                inputs={
                    "environment": "infra/staging",
                    "plan": "plans/capacity.tfplan",
                },
            )
        )
    except PermissionError as error:
        rejected = str(error)
    else:
        raise AssertionError("Developer unexpectedly received cloud.deploy authority")

    assert agora.validate().ok
    print(f"Project: {project}")
    print(f"List command: {resources.command}")
    print(f"Plan command: {plan.command}")
    print(f"CLI available: {resources.runtime_available}")
    print(f"Rejected apply: {rejected}")


if __name__ == "__main__":
    main()
