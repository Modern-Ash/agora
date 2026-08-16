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
    runtime = Path(tempfile.mkdtemp(prefix="agora-gitlab-ci-cli-sample-"))
    project = runtime / "project"
    project.mkdir()
    os.environ["AGORA_HOME"] = str(runtime / "home")
    os.environ["AGORA_LOCK_HOME"] = str(runtime / "locks")
    agora = AgoraWorkspace(cwd=project)
    agora.initialize(InitInput(integration="generic", default_method="scrum"))
    agora.install_tool_adapter(InstallToolAdapterInput(adapter_id="gitlab-ci", scope="project"))

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
            objective="Inspect GitLab pipelines through the existing CLI",
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
            id="list-gitlab-pipelines",
            tool_id="gitlab-ci",
            operation_id="list-runs",
            actor_id="developer",
            swarm_id="delivery",
            inputs={"pipeline": "verify"},
        )
    )
    viewed = agora.invoke_tool(
        InvokeToolInput(
            id="view-gitlab-pipeline",
            tool_id="gitlab-ci",
            operation_id="view-run",
            actor_id="developer",
            swarm_id="delivery",
            inputs={"run": "12345"},
        )
    )
    try:
        agora.invoke_tool(
            InvokeToolInput(
                id="cancel-gitlab-pipeline",
                tool_id="gitlab-ci",
                operation_id="cancel-run",
                actor_id="developer",
                swarm_id="delivery",
                inputs={"run": "12345"},
            )
        )
    except PermissionError as error:
        rejected_cancel = str(error)
    else:
        raise AssertionError("Developer unexpectedly received ci.cancel authority")
    try:
        agora.invoke_tool(
            InvokeToolInput(
                id="unsupported-gitlab-trigger",
                tool_id="gitlab-ci",
                operation_id="trigger",
                actor_id="developer",
                swarm_id="delivery",
                inputs={"pipeline": "verify", "ref": "main", "parameters": "suite=all"},
            )
        )
    except FileNotFoundError as error:
        rejected_trigger = str(error)
    else:
        raise AssertionError("GitLab adapter unexpectedly exposed pipeline trigger")

    assert agora.validate().ok
    print(f"Project: {project}")
    print(f"List command: {listed.command}")
    print(f"View command: {viewed.command}")
    print(f"CLI available: {listed.runtime_available}")
    print(f"Rejected cancel: {rejected_cancel}")
    print(f"Rejected trigger: {rejected_trigger}")


if __name__ == "__main__":
    main()
