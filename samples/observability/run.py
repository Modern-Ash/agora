import os
import shutil
import sys
import tempfile
from pathlib import Path

from agora.filesystem import packs_root
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
    source = runtime / "observability"
    shutil.copytree(packs_root() / "tools" / "observability", source)
    provider = Path(__file__).with_name("provider.py").resolve()
    manifest = read_markdown(source / "TOOL.md")
    manifest.attributes["executable"] = sys.executable
    (source / "TOOL.md").write_text(render_markdown(manifest), encoding="utf-8")
    for path in (source / "operations").glob("*.md"):
        operation = read_markdown(path)
        operation.attributes["arguments"] = [str(provider), *operation.attributes["arguments"]]
        path.write_text(render_markdown(operation), encoding="utf-8")
    return source


def _grant_guarded_resolution(project: Path, agora: AgoraWorkspace) -> None:
    role_path = project / ".agora" / "methods" / "scrum" / "roles" / "developer.md"
    role = read_markdown(role_path)
    role.attributes["allowed-tool-capabilities"].append("incident.resolve")
    role_path.write_text(render_markdown(role), encoding="utf-8")
    operation_path = (
        project / ".agora" / "tools" / "observability" / "operations" / "resolve-incident.md"
    )
    operation = read_markdown(operation_path)
    operation.attributes["approval-role"] = "product-owner"
    operation_path.write_text(render_markdown(operation), encoding="utf-8")
    agora.refresh_pack_lock(RefreshPackLockInput(scope="project"))


def main() -> None:
    runtime = Path(tempfile.mkdtemp(prefix="agora-observability-sample-"))
    project = runtime / "project"
    project.mkdir()
    os.environ["AGORA_HOME"] = str(runtime / "home")
    os.environ["AGORA_LOCK_HOME"] = str(runtime / "locks")
    agora = AgoraWorkspace(cwd=project)
    agora.install_tool(InstallToolInput(source=str(_sample_pack(runtime)), scope="user"))
    agora.initialize(InitInput(integration="generic", default_method="scrum"))
    for actor in (
        AddActorInput(
            "owner", "Product Owner", "human", ["backlog-management", "acceptance"], "project"
        ),
        AddActorInput(
            "facilitator", "Scrum Master", "ai-agent", ["facilitation", "governance"], "project"
        ),
        AddActorInput("developer", "Incident Agent", "ai-agent", ["implementation"], "project"),
    ):
        agora.add_actor(actor)
    agora.create_swarm(
        CreateSwarmInput(
            id="delivery", objective="Observe and resolve an incident", create_branch=False
        )
    )
    for role, actor in (
        ("product-owner", "owner"),
        ("scrum-master", "facilitator"),
        ("developer", "developer"),
    ):
        agora.assign_actor(AssignActorInput("delivery", role, actor))
    agora.create_work(
        CreateWorkInput("delivery", "incident-response", "Restore API health", "owner")
    )
    agora.add_environment(
        AddEnvironmentInput(
            id="production",
            name="Production",
            allowed_tool_capabilities=["observability.read"],
        )
    )
    health = agora.invoke_tool(
        InvokeToolInput(
            id="health-check",
            tool_id="observability",
            operation_id="service-health",
            actor_id="developer",
            swarm_id="delivery",
            work_id="incident-response",
            environment_id="production",
            inputs={"service": "api", "environment": "production"},
            launch=True,
        )
    )
    incident = agora.invoke_tool(
        InvokeToolInput(
            id="declare-incident",
            tool_id="observability",
            operation_id="create-incident",
            actor_id="facilitator",
            swarm_id="delivery",
            work_id="incident-response",
            inputs={
                "service": "api",
                "severity": "high",
                "title": "API errors",
                "summary": "Error threshold exceeded.",
            },
            launch=True,
        )
    )
    _grant_guarded_resolution(project, agora)
    resolution = InvokeToolInput(
        id="resolve-incident",
        tool_id="observability",
        operation_id="resolve-incident",
        actor_id="developer",
        swarm_id="delivery",
        work_id="incident-response",
        inputs={"incident": "INC-42", "resolution": "Health checks recovered."},
        launch=True,
    )
    try:
        agora.invoke_tool(resolution)
    except PermissionError as error:
        rejected = str(error)
    else:
        raise AssertionError("Incident resolved without approval")
    agora.add_approval(
        AddApprovalInput(
            "delivery", "incident-response", "owner", "product-owner", "Recovery evidence reviewed"
        )
    )
    resolved = agora.invoke_tool(resolution)
    report = agora.validate()
    assert report.ok
    print(f"Project: {project}")
    print(f"Health: {health.status} -> {Path(health.path) / 'RESULT.md'}")
    print(f"Incident: {incident.status} -> {Path(incident.path) / 'RESULT.md'}")
    print(f"Rejected resolution: {rejected}")
    print(f"Resolution: {resolved.status} -> {Path(resolved.path) / 'RESULT.md'}")
    print(f"Validation issues: {len(report.issues)}")


if __name__ == "__main__":
    main()
