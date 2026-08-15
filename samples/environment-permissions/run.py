import os
import tempfile
from pathlib import Path

from agora.model import (
    AddActorInput,
    AddApprovalInput,
    AddEnvironmentInput,
    AddEvidenceInput,
    AssignActorInput,
    CreateSwarmInput,
    CreateWorkInput,
    InitInput,
    InvokeToolInput,
)
from agora.workspace import AgoraWorkspace


def main() -> None:
    runtime = Path(tempfile.mkdtemp(prefix="agora-environment-permissions-sample-"))
    project = runtime / "project"
    project.mkdir()
    os.environ["AGORA_HOME"] = str(runtime / "home")
    os.environ["AGORA_LOCK_HOME"] = str(runtime / "locks")
    agora = AgoraWorkspace(cwd=project)
    agora.initialize(InitInput(integration="generic", default_method="scrum"))

    for actor in (
        AddActorInput(
            "owner", "Product Owner", "human", ["backlog-management", "acceptance"], "project"
        ),
        AddActorInput(
            "facilitator",
            "Scrum Master",
            "ai-agent",
            ["facilitation", "governance"],
            "project",
        ),
        AddActorInput("developer", "Delivery Agent", "ai-agent", ["implementation"], "project"),
    ):
        agora.add_actor(actor)
    agora.create_swarm(
        CreateSwarmInput(
            id="delivery",
            objective="Plan a production change under environment policy",
            create_branch=False,
        )
    )
    for role, actor in (
        ("product-owner", "owner"),
        ("scrum-master", "facilitator"),
        ("developer", "developer"),
    ):
        agora.assign_actor(AssignActorInput("delivery", role, actor))
    agora.create_work(CreateWorkInput("delivery", "release", "Plan release", "owner"))
    agora.add_environment(
        AddEnvironmentInput(
            id="production",
            name="Production",
            allowed_tool_capabilities=["cloud.plan"],
            required_approval_roles=["product-owner"],
            require_successful_evidence=True,
        )
    )

    invocation = InvokeToolInput(
        id="production-plan",
        tool_id="cloud-infrastructure",
        operation_id="plan",
        actor_id="developer",
        swarm_id="delivery",
        work_id="release",
        environment_id="production",
        inputs={"environment": "provider-production", "change": "release-v1"},
    )
    try:
        agora.invoke_tool(invocation)
    except PermissionError as error:
        rejected_without_approval = str(error)
    else:
        raise AssertionError("Environment unexpectedly accepted work without approval")

    agora.add_approval(AddApprovalInput("delivery", "release", "owner", "product-owner"))
    try:
        agora.invoke_tool(invocation)
    except PermissionError as error:
        rejected_without_evidence = str(error)
    else:
        raise AssertionError("Environment unexpectedly accepted work without evidence")

    agora.add_evidence(
        AddEvidenceInput("delivery", "release", "facilitator", type="test-run", result="success")
    )
    prepared = agora.invoke_tool(invocation)
    assert agora.validate().ok

    print(f"Project: {project}")
    print(f"Rejected without approval: {rejected_without_approval}")
    print(f"Rejected without evidence: {rejected_without_evidence}")
    print(f"Prepared environment: {prepared.environment_id}")
    print(f"Tool Run: {Path(prepared.path) / 'RUN.md'}")


if __name__ == "__main__":
    main()
