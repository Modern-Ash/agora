import json
import os
import shutil
import tempfile
from pathlib import Path

from agora.model import (
    AddActorInput,
    AssignActorInput,
    CreateSwarmInput,
    CreateWorkInput,
    InitInput,
    InstallToolAdapterInput,
    InvokeToolInput,
)
from agora.workspace import AgoraWorkspace


def main() -> None:
    runtime = Path(tempfile.mkdtemp(prefix="agora-jira-cli-sample-"))
    project = runtime / "project"
    project.mkdir()
    bin_dir = runtime / "bin"
    bin_dir.mkdir()
    acli = bin_dir / "acli"
    shutil.copy2(Path(__file__).with_name("provider.py"), acli)
    acli.chmod(0o755)
    os.environ["AGORA_HOME"] = str(runtime / "home")
    os.environ["AGORA_LOCK_HOME"] = str(runtime / "locks")
    os.environ["AGORA_JIRA_SAMPLE_STATE"] = str(runtime / "jira-state.json")
    os.environ["PATH"] = f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"
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
    agora.create_work(
        CreateWorkInput(
            swarm_id="delivery",
            id="jira-integration",
            title="Exercise governed Jira interaction",
            actor_id="owner",
            acceptance_criteria=[
                ("provider-output", "Agora captures the simulated Jira JSON response"),
                ("authority", "A developer cannot perform an ungranted Jira write"),
            ],
            description="Run the reviewed Jira adapter through an ACLI-compatible process.",
        )
    )

    search = agora.invoke_tool(
        InvokeToolInput(
            id="search-jira-work",
            tool_id="jira",
            operation_id="search",
            actor_id="developer",
            swarm_id="delivery",
            work_id="jira-integration",
            inputs={"query": "project = AGORA AND status != Done"},
            launch=True,
        )
    )
    created = agora.invoke_tool(
        InvokeToolInput(
            id="create-jira-work",
            tool_id="jira",
            operation_id="create",
            actor_id="owner",
            swarm_id="delivery",
            work_id="jira-integration",
            inputs={
                "project": "AGORA",
                "type": "Task",
                "title": "Verify Agora Jira adapter",
                "description": "Created by the governed Jira sample.",
            },
            launch=True,
        )
    )
    created_result = agora.show_tool_run(created.id).result
    assert created_result is not None
    created_issue = json.loads(created_result.stdout)["key"]
    viewed = agora.invoke_tool(
        InvokeToolInput(
            id="view-created-jira-work",
            tool_id="jira",
            operation_id="view",
            actor_id="developer",
            swarm_id="delivery",
            work_id="jira-integration",
            inputs={"issue": created_issue},
            launch=True,
        )
    )
    commented = agora.invoke_tool(
        InvokeToolInput(
            id="comment-created-jira-work",
            tool_id="jira",
            operation_id="comment",
            actor_id="owner",
            swarm_id="delivery",
            work_id="jira-integration",
            inputs={"issue": created_issue, "body": "Governed comment from Agora"},
            launch=True,
        )
    )
    transitioned = agora.invoke_tool(
        InvokeToolInput(
            id="transition-created-jira-work",
            tool_id="jira",
            operation_id="transition",
            actor_id="owner",
            swarm_id="delivery",
            work_id="jira-integration",
            inputs={"issue": created_issue, "state": "In Progress"},
            launch=True,
        )
    )
    final_view = agora.invoke_tool(
        InvokeToolInput(
            id="verify-created-jira-work",
            tool_id="jira",
            operation_id="view",
            actor_id="developer",
            swarm_id="delivery",
            work_id="jira-integration",
            inputs={"issue": created_issue},
            launch=True,
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
                work_id="jira-integration",
                inputs={"issue": created_issue, "body": "Attempted write"},
            )
        )
    except PermissionError as error:
        rejected = str(error)
    else:
        raise AssertionError("Developer unexpectedly received issue.write authority")

    assert agora.validate().ok
    results = {
        run.id: json.loads(inspection.result.stdout)
        for run in (search, created, viewed, commented, transitioned, final_view)
        if (inspection := agora.show_tool_run(run.id)).result is not None
    }
    assert results[final_view.id]["status"] == "In Progress"
    assert results[final_view.id]["comments"] == ["Governed comment from Agora"]
    print(f"Project: {project}")
    print("Mode: deterministic ACLI-compatible process (not Jira Cloud)")
    print(f"ACLI runtime detected: {search.runtime_available}")
    print(f"Created Jira key: {created_issue}")
    for run_id, payload in results.items():
        result = agora.show_tool_run(run_id).result
        assert result is not None
        print(f"{run_id}: {json.dumps(payload, sort_keys=True)}")
        print(f"{run_id} result: {result.path}")
    print(f"Rejected comment: {rejected}")


if __name__ == "__main__":
    main()
