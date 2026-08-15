import os
import shutil
import sys
import tempfile
from pathlib import Path

from agora.filesystem import template_root
from agora.markdown import read_markdown, render_markdown
from agora.model import (
    AddActorInput,
    AddApprovalInput,
    AddEnvironmentInput,
    AssignActorInput,
    CreateSwarmInput,
    CreateWorkInput,
    InitInput,
    InstallToolInput,
    InvokeToolInput,
    RefreshPackLockInput,
)
from agora.workspace import AgoraWorkspace


def _sample_pack(runtime: Path) -> Path:
    source = runtime / "ci-cd"
    shutil.copytree(template_root() / "tools" / "ci-cd", source)
    provider = Path(__file__).with_name("provider.py").resolve()
    manifest = read_markdown(source / "TOOL.md")
    manifest.attributes["executable"] = sys.executable
    manifest.attributes["authentication-reference"] = "sample-provider-no-auth"
    (source / "TOOL.md").write_text(render_markdown(manifest), encoding="utf-8")
    for path in (source / "operations").glob("*.md"):
        operation = read_markdown(path)
        operation.attributes["arguments"] = [str(provider), *operation.attributes["arguments"]]
        path.write_text(render_markdown(operation), encoding="utf-8")
    return source


def _grant_guarded_deployment(project: Path, agora: AgoraWorkspace) -> None:
    role_path = project / ".agora" / "methods" / "scrum" / "roles" / "developer.md"
    role = read_markdown(role_path)
    role.attributes["allowed-tool-capabilities"].append("deployment.create")
    role_path.write_text(render_markdown(role), encoding="utf-8")
    operation_path = project / ".agora" / "tools" / "ci-cd" / "operations" / "create-deployment.md"
    operation = read_markdown(operation_path)
    operation.attributes["approval-role"] = "product-owner"
    operation_path.write_text(render_markdown(operation), encoding="utf-8")
    agora.refresh_pack_lock(RefreshPackLockInput(scope="project"))


def main() -> None:
    runtime = Path(tempfile.mkdtemp(prefix="agora-ci-cd-sample-"))
    project = runtime / "project"
    project.mkdir()
    os.environ["AGORA_HOME"] = str(runtime / "home")
    os.environ["AGORA_LOCK_HOME"] = str(runtime / "locks")
    agora = AgoraWorkspace(cwd=project)
    agora.install_tool(InstallToolInput(source=str(_sample_pack(runtime)), scope="user"))
    agora.initialize(InitInput(integration="generic", default_method="scrum"))

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
            objective="Run verified delivery through governed CI/CD",
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
            id="release-candidate",
            title="Verify and deploy an immutable release candidate",
            actor_id="owner",
        )
    )

    runs = agora.invoke_tool(
        InvokeToolInput(
            id="list-verification-runs",
            tool_id="ci-cd",
            operation_id="list-runs",
            actor_id="developer",
            swarm_id="delivery",
            work_id="release-candidate",
            inputs={"pipeline": "verify"},
            launch=True,
        )
    )
    triggered = agora.invoke_tool(
        InvokeToolInput(
            id="trigger-verification",
            tool_id="ci-cd",
            operation_id="trigger",
            actor_id="developer",
            swarm_id="delivery",
            work_id="release-candidate",
            inputs={"pipeline": "verify", "ref": "main", "parameters": "suite=all"},
            launch=True,
        )
    )
    try:
        agora.invoke_tool(
            InvokeToolInput(
                id="unauthorized-cancel",
                tool_id="ci-cd",
                operation_id="cancel-run",
                actor_id="developer",
                swarm_id="delivery",
                work_id="release-candidate",
                inputs={"run": "run-42"},
            )
        )
    except PermissionError as error:
        rejected_cancel = str(error)
    else:
        raise AssertionError("Developer unexpectedly received ci.cancel authority")

    _grant_guarded_deployment(project, agora)
    agora.add_environment(
        AddEnvironmentInput(
            id="staging",
            name="Staging",
            allowed_tool_capabilities=["deployment.create"],
        )
    )
    deployment = InvokeToolInput(
        id="deploy-release-candidate",
        tool_id="ci-cd",
        operation_id="create-deployment",
        actor_id="developer",
        swarm_id="delivery",
        work_id="release-candidate",
        environment_id="staging",
        inputs={"environment": "staging", "artifact": "sha256:verified"},
        launch=True,
    )
    try:
        agora.invoke_tool(deployment)
    except PermissionError as error:
        rejected_deployment = str(error)
    else:
        raise AssertionError("Deployment unexpectedly ran without Product Owner approval")
    agora.add_approval(
        AddApprovalInput(
            swarm_id="delivery",
            work_id="release-candidate",
            actor_id="owner",
            role_id="product-owner",
            note="Verified artifact may deploy to staging",
        )
    )
    deployed = agora.invoke_tool(deployment)
    report = agora.validate()
    assert report.ok

    print(f"Project: {project}")
    print(f"Runs: {runs.status} -> {Path(runs.path) / 'RESULT.md'}")
    print(f"Trigger: {triggered.status} -> {Path(triggered.path) / 'RESULT.md'}")
    print(f"Rejected cancel: {rejected_cancel}")
    print(f"Rejected deployment: {rejected_deployment}")
    print(f"Deployment: {deployed.status} -> {Path(deployed.path) / 'RESULT.md'}")
    print(f"Validation issues: {len(report.issues)}")


if __name__ == "__main__":
    main()
