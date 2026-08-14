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
    source = runtime / "knowledge-base"
    shutil.copytree(template_root() / "tools" / "knowledge-base", source)
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


def _grant_guarded_publication(project: Path, agora: AgoraWorkspace) -> None:
    role_path = project / ".agora" / "methods" / "scrum" / "roles" / "developer.md"
    role = read_markdown(role_path)
    role.attributes["allowed-tool-capabilities"].append("docs.publish")
    role_path.write_text(render_markdown(role), encoding="utf-8")
    operation_path = project / ".agora" / "tools" / "knowledge-base" / "operations" / "publish.md"
    operation = read_markdown(operation_path)
    operation.attributes["approval-role"] = "product-owner"
    operation_path.write_text(render_markdown(operation), encoding="utf-8")
    agora.refresh_pack_lock(RefreshPackLockInput(scope="project"))


def main() -> None:
    runtime = Path(tempfile.mkdtemp(prefix="agora-knowledge-base-sample-"))
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
            name="Documentation Agent",
            kind="ai-agent",
            capabilities=["implementation"],
            scope="project",
        ),
    ):
        agora.add_actor(actor)
    agora.create_swarm(
        CreateSwarmInput(
            id="delivery",
            objective="Publish reviewed delivery knowledge",
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
            id="knowledge-update",
            title="Create and publish reviewed delivery knowledge",
            actor_id="owner",
        )
    )

    search = agora.invoke_tool(
        InvokeToolInput(
            id="search-architecture",
            tool_id="knowledge-base",
            operation_id="search",
            actor_id="facilitator",
            swarm_id="delivery",
            work_id="knowledge-update",
            inputs={"space": "ENG", "query": "delivery architecture"},
            launch=True,
        )
    )
    created = agora.invoke_tool(
        InvokeToolInput(
            id="create-delivery-guide",
            tool_id="knowledge-base",
            operation_id="create",
            actor_id="developer",
            swarm_id="delivery",
            work_id="knowledge-update",
            inputs={
                "space": "ENG",
                "parent": "architecture",
                "title": "Governed delivery guide",
                "body": "This draft records the reviewed delivery behavior.",
            },
            launch=True,
        )
    )

    _grant_guarded_publication(project, agora)
    publication = InvokeToolInput(
        id="publish-delivery-guide",
        tool_id="knowledge-base",
        operation_id="publish",
        actor_id="developer",
        swarm_id="delivery",
        work_id="knowledge-update",
        inputs={"document": "DOC-43"},
        launch=True,
    )
    try:
        agora.invoke_tool(publication)
    except PermissionError as error:
        rejected_publication = str(error)
    else:
        raise AssertionError("Publication unexpectedly ran without Product Owner approval")
    agora.add_approval(
        AddApprovalInput(
            swarm_id="delivery",
            work_id="knowledge-update",
            actor_id="owner",
            role_id="product-owner",
            note="Reviewed documentation may be published",
        )
    )
    published = agora.invoke_tool(publication)
    try:
        agora.invoke_tool(
            InvokeToolInput(
                id="unauthorized-archive",
                tool_id="knowledge-base",
                operation_id="archive",
                actor_id="owner",
                swarm_id="delivery",
                work_id="knowledge-update",
                inputs={"document": "DOC-43"},
            )
        )
    except PermissionError as error:
        rejected_archive = str(error)
    else:
        raise AssertionError("Product Owner unexpectedly received docs.archive authority")
    report = agora.validate()
    assert report.ok

    print(f"Project: {project}")
    print(f"Search: {search.status} -> {Path(search.path) / 'RESULT.md'}")
    print(f"Create: {created.status} -> {Path(created.path) / 'RESULT.md'}")
    print(f"Rejected publication: {rejected_publication}")
    print(f"Publication: {published.status} -> {Path(published.path) / 'RESULT.md'}")
    print(f"Rejected archive: {rejected_archive}")
    print(f"Validation issues: {len(report.issues)}")


if __name__ == "__main__":
    main()
