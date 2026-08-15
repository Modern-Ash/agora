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
    source = runtime / "cloud-infrastructure"
    shutil.copytree(template_root() / "tools" / "cloud-infrastructure", source)
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


def _grant_guarded_apply(project: Path, agora: AgoraWorkspace) -> None:
    role_path = project / ".agora" / "methods" / "scrum" / "roles" / "developer.md"
    role = read_markdown(role_path)
    role.attributes["allowed-tool-capabilities"].append("cloud.deploy")
    role_path.write_text(render_markdown(role), encoding="utf-8")
    operation_path = (
        project / ".agora" / "tools" / "cloud-infrastructure" / "operations" / "apply-plan.md"
    )
    operation = read_markdown(operation_path)
    operation.attributes["approval-role"] = "product-owner"
    operation_path.write_text(render_markdown(operation), encoding="utf-8")
    agora.refresh_pack_lock(RefreshPackLockInput(scope="project"))


def main() -> None:
    runtime = Path(tempfile.mkdtemp(prefix="agora-cloud-infrastructure-sample-"))
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
            name="Cloud Delivery Agent",
            kind="ai-agent",
            capabilities=["implementation"],
            scope="project",
        ),
    ):
        agora.add_actor(actor)
    agora.create_swarm(
        CreateSwarmInput(
            id="delivery",
            objective="Plan and apply a reviewed cloud change",
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
            id="capacity-change",
            title="Increase staging API capacity",
            actor_id="owner",
        )
    )

    inspected = agora.invoke_tool(
        InvokeToolInput(
            id="inspect-api-service",
            tool_id="cloud-infrastructure",
            operation_id="inspect-resource",
            actor_id="facilitator",
            swarm_id="delivery",
            work_id="capacity-change",
            inputs={"resource": "service/api", "environment": "staging"},
            launch=True,
        )
    )
    plan = agora.invoke_tool(
        InvokeToolInput(
            id="plan-capacity-change",
            tool_id="cloud-infrastructure",
            operation_id="plan",
            actor_id="developer",
            swarm_id="delivery",
            work_id="capacity-change",
            inputs={"environment": "staging", "change": "increase-api-capacity"},
            launch=True,
        )
    )

    _grant_guarded_apply(project, agora)
    apply_plan = InvokeToolInput(
        id="apply-capacity-plan",
        tool_id="cloud-infrastructure",
        operation_id="apply-plan",
        actor_id="developer",
        swarm_id="delivery",
        work_id="capacity-change",
        inputs={"plan": "plan-42", "environment": "staging"},
        launch=True,
    )
    try:
        agora.invoke_tool(apply_plan)
    except PermissionError as error:
        rejected_apply = str(error)
    else:
        raise AssertionError("Cloud plan unexpectedly applied without Product Owner approval")
    agora.add_approval(
        AddApprovalInput(
            swarm_id="delivery",
            work_id="capacity-change",
            actor_id="owner",
            role_id="product-owner",
            note="Reviewed non-destructive plan may apply to staging",
        )
    )
    applied = agora.invoke_tool(apply_plan)
    try:
        agora.invoke_tool(
            InvokeToolInput(
                id="unauthorized-destroy",
                tool_id="cloud-infrastructure",
                operation_id="destroy-resource",
                actor_id="developer",
                swarm_id="delivery",
                work_id="capacity-change",
                inputs={"resource": "service/api", "environment": "staging"},
            )
        )
    except PermissionError as error:
        rejected_destroy = str(error)
    else:
        raise AssertionError("Developer unexpectedly received cloud.destroy authority")
    report = agora.validate()
    assert report.ok

    print(f"Project: {project}")
    print(f"Inspect: {inspected.status} -> {Path(inspected.path) / 'RESULT.md'}")
    print(f"Plan: {plan.status} -> {Path(plan.path) / 'RESULT.md'}")
    print(f"Rejected apply: {rejected_apply}")
    print(f"Apply: {applied.status} -> {Path(applied.path) / 'RESULT.md'}")
    print(f"Rejected destroy: {rejected_destroy}")
    print(f"Validation issues: {len(report.issues)}")


if __name__ == "__main__":
    main()
