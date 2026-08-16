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
    runtime = Path(tempfile.mkdtemp(prefix="agora-gitlab-merge-requests-cli-sample-"))
    project = runtime / "project"
    project.mkdir()
    os.environ["AGORA_HOME"] = str(runtime / "home")
    os.environ["AGORA_LOCK_HOME"] = str(runtime / "locks")
    agora = AgoraWorkspace(cwd=project)
    agora.initialize(InitInput(integration="generic", default_method="scrum"))
    agora.install_tool_adapter(
        InstallToolAdapterInput(adapter_id="gitlab-merge-requests", scope="project")
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
            objective="Review changes through the existing GitLab CLI",
            create_branch=False,
        )
    )
    for role, actor in (
        ("product-owner", "owner"),
        ("scrum-master", "facilitator"),
        ("developer", "developer"),
    ):
        agora.assign_actor(AssignActorInput(swarm_id="delivery", role_id=role, actor_id=actor))

    create = agora.invoke_tool(
        InvokeToolInput(
            id="create-gitlab-review",
            tool_id="gitlab-merge-requests",
            operation_id="create",
            actor_id="developer",
            swarm_id="delivery",
            inputs={
                "project": "example/agora",
                "base": "main",
                "head": "agora/governed-change",
                "title": "feat: add governed review",
                "description": "Implements accepted work with durable evidence.",
            },
        )
    )
    checks = agora.invoke_tool(
        InvokeToolInput(
            id="inspect-gitlab-review-checks",
            tool_id="gitlab-merge-requests",
            operation_id="checks",
            actor_id="developer",
            swarm_id="delivery",
            inputs={"review": "42"},
        )
    )
    try:
        agora.invoke_tool(
            InvokeToolInput(
                id="unsupported-gitlab-merge",
                tool_id="gitlab-merge-requests",
                operation_id="merge",
                actor_id="owner",
                swarm_id="delivery",
                inputs={"review": "42", "method": "squash"},
            )
        )
    except FileNotFoundError as error:
        rejected_merge = str(error)
    else:
        raise AssertionError("GitLab adapter unexpectedly exposed merge")

    assert agora.validate().ok
    print(f"Project: {project}")
    print(f"Create command: {create.command}")
    print(f"Checks command: {checks.command}")
    print(f"CLI available: {create.runtime_available}")
    print(f"Rejected merge: {rejected_merge}")


if __name__ == "__main__":
    main()
