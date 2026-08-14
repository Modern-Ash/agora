import os
import shutil
import sys
import tempfile
from pathlib import Path

from agora.filesystem import template_root
from agora.markdown import read_markdown, render_markdown
from agora.model import (
    AddActorInput,
    AssignActorInput,
    CreateSwarmInput,
    CreateWorkInput,
    InitInput,
    InstallToolInput,
    InvokeToolInput,
)
from agora.workspace import AgoraWorkspace


def _sample_pack(runtime: Path) -> Path:
    source = runtime / "work-management"
    shutil.copytree(template_root() / "tools" / "work-management", source)
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


def main() -> None:
    runtime = Path(tempfile.mkdtemp(prefix="agora-work-management-sample-"))
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
            name="Developer Agent",
            kind="ai-agent",
            capabilities=["implementation"],
            scope="project",
        ),
    ):
        agora.add_actor(actor)
    agora.create_swarm(
        CreateSwarmInput(
            id="delivery",
            objective="Synchronize governed delivery with external work management",
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
            id="tracker-sync",
            title="Demonstrate governed work-management access",
            actor_id="owner",
        )
    )

    search = agora.invoke_tool(
        InvokeToolInput(
            id="search-ready-items",
            tool_id="work-management",
            operation_id="search",
            actor_id="facilitator",
            swarm_id="delivery",
            work_id="tracker-sync",
            inputs={"query": "project = AGORA and state = Ready"},
            launch=True,
        )
    )
    created = agora.invoke_tool(
        InvokeToolInput(
            id="create-governed-item",
            tool_id="work-management",
            operation_id="create",
            actor_id="owner",
            swarm_id="delivery",
            work_id="tracker-sync",
            inputs={
                "project": "AGORA",
                "type": "Story",
                "title": "Persist governed tool evidence",
                "description": "Keep provider interaction attributable and reviewable.",
            },
            launch=True,
        )
    )
    transitioned = agora.invoke_tool(
        InvokeToolInput(
            id="transition-governed-item",
            tool_id="work-management",
            operation_id="transition",
            actor_id="owner",
            swarm_id="delivery",
            work_id="tracker-sync",
            inputs={"issue": "AGORA-43", "state": "In Progress"},
            launch=True,
        )
    )
    try:
        agora.invoke_tool(
            InvokeToolInput(
                id="unauthorized-transition",
                tool_id="work-management",
                operation_id="transition",
                actor_id="developer",
                swarm_id="delivery",
                work_id="tracker-sync",
                inputs={"issue": "AGORA-43", "state": "Done"},
            )
        )
    except PermissionError as error:
        rejected = str(error)
    else:
        raise AssertionError("Developer unexpectedly received issue.transition authority")
    report = agora.validate()
    assert report.ok

    print(f"Project: {project}")
    print(f"Search: {search.status} -> {Path(search.path) / 'RESULT.md'}")
    print(f"Create: {created.status} -> {Path(created.path) / 'RESULT.md'}")
    print(f"Transition: {transitioned.status} -> {Path(transitioned.path) / 'RESULT.md'}")
    print(f"Rejected transition: {rejected}")
    print(f"Validation issues: {len(report.issues)}")


if __name__ == "__main__":
    main()
