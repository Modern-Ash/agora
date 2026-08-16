import os
import tempfile
from pathlib import Path

from agora.markdown import read_markdown, render_markdown
from agora.model import (
    AddActorInput,
    AssignActorInput,
    CreateSwarmInput,
    CreateWorkInput,
    InitInput,
    InstallToolAdapterInput,
    InvokeToolInput,
    RefreshPackLockInput,
)
from agora.workspace import AgoraWorkspace

GITHUB_ADAPTERS = (
    "github-actions",
    "github-issues",
    "github-projects",
    "github-pull-requests",
    "github-releases",
    "github-repository-governance",
    "github-security",
)


def _grant_explicit_release_authority(project: Path, agora: AgoraWorkspace) -> None:
    role_path = project / ".agora" / "methods" / "scrum" / "roles" / "product-owner.md"
    role = read_markdown(role_path)
    capabilities = role.attributes["allowed-tool-capabilities"]
    capabilities.extend(["review.merge", "release.publish"])
    role_path.write_text(render_markdown(role), encoding="utf-8")
    agora.refresh_pack_lock(RefreshPackLockInput(scope="project"))


def main() -> None:
    runtime = Path(tempfile.mkdtemp(prefix="agora-github-end-to-end-sample-"))
    project = runtime / "project"
    project.mkdir()
    os.environ["AGORA_HOME"] = str(runtime / "home")
    os.environ["AGORA_LOCK_HOME"] = str(runtime / "locks")
    agora = AgoraWorkspace(cwd=project)
    agora.initialize(InitInput(integration="generic", default_method="scrum"))
    for adapter in GITHUB_ADAPTERS:
        agora.install_tool_adapter(InstallToolAdapterInput(adapter_id=adapter, scope="project"))

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
            objective="Deliver a governed GitHub change from issue to release",
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
            id="github-change",
            title="Deliver the governed GitHub change",
            actor_id="owner",
        )
    )

    issue = agora.invoke_tool(
        InvokeToolInput(
            id="github-create-issue",
            tool_id="github-issues",
            operation_id="create",
            actor_id="owner",
            swarm_id="delivery",
            work_id="github-change",
            inputs={
                "project": "example/agora",
                "type": "Task",
                "title": "Deliver governed GitHub workflow",
                "description": "Track the complete external delivery lifecycle.",
            },
        )
    )
    branch = agora.invoke_tool(
        InvokeToolInput(
            id="github-create-branch",
            tool_id="repository",
            operation_id="create-branch",
            actor_id="developer",
            swarm_id="delivery",
            work_id="github-change",
            inputs={"branch": "feat/github-governed-workflow"},
        )
    )
    review = agora.invoke_tool(
        InvokeToolInput(
            id="github-create-review",
            tool_id="github-pull-requests",
            operation_id="create",
            actor_id="developer",
            swarm_id="delivery",
            work_id="github-change",
            inputs={
                "project": "example/agora",
                "base": "main",
                "head": "feat/github-governed-workflow",
                "title": "feat(github): complete governed delivery",
                "description": "Closes #42 after governed evidence and acceptance.",
            },
        )
    )
    checks = agora.invoke_tool(
        InvokeToolInput(
            id="github-review-checks",
            tool_id="github-pull-requests",
            operation_id="checks",
            actor_id="developer",
            swarm_id="delivery",
            work_id="github-change",
            inputs={"review": "42"},
        )
    )
    approval = agora.invoke_tool(
        InvokeToolInput(
            id="github-review-approval",
            tool_id="github-pull-requests",
            operation_id="approve",
            actor_id="owner",
            swarm_id="delivery",
            work_id="github-change",
            inputs={"review": "42", "body": "Accepted after governed verification."},
        )
    )

    try:
        agora.invoke_tool(
            InvokeToolInput(
                id="github-merge-before-policy",
                tool_id="github-pull-requests",
                operation_id="merge",
                actor_id="owner",
                swarm_id="delivery",
                work_id="github-change",
                inputs={"review": "42", "method": "squash"},
            )
        )
    except PermissionError as error:
        rejected_merge = str(error)
    else:
        raise AssertionError("Merge unexpectedly bypassed explicit project policy")

    _grant_explicit_release_authority(project, agora)
    merge = agora.invoke_tool(
        InvokeToolInput(
            id="github-merge-review",
            tool_id="github-pull-requests",
            operation_id="merge",
            actor_id="owner",
            swarm_id="delivery",
            work_id="github-change",
            inputs={"review": "42", "method": "squash"},
        )
    )
    close_issue = agora.invoke_tool(
        InvokeToolInput(
            id="github-close-issue",
            tool_id="github-issues",
            operation_id="transition",
            actor_id="owner",
            swarm_id="delivery",
            work_id="github-change",
            inputs={"issue": "42", "state": "close"},
        )
    )
    governance = agora.invoke_tool(
        InvokeToolInput(
            id="github-governance-snapshot",
            tool_id="github-repository-governance",
            operation_id="view-branch-protection",
            actor_id="facilitator",
            swarm_id="delivery",
            work_id="github-change",
            inputs={"project": "example/agora", "branch": "main"},
        )
    )
    security = agora.invoke_tool(
        InvokeToolInput(
            id="github-security-snapshot",
            tool_id="github-security",
            operation_id="list-secret-alerts",
            actor_id="developer",
            swarm_id="delivery",
            work_id="github-change",
            inputs={"project": "example/agora"},
        )
    )
    portfolio = agora.invoke_tool(
        InvokeToolInput(
            id="github-portfolio-snapshot",
            tool_id="github-projects",
            operation_id="list-items",
            actor_id="owner",
            swarm_id="delivery",
            work_id="github-change",
            inputs={"owner": "example", "project": "1", "query": "is:open"},
        )
    )
    release = agora.invoke_tool(
        InvokeToolInput(
            id="github-publish-release",
            tool_id="github-releases",
            operation_id="publish-release",
            actor_id="owner",
            swarm_id="delivery",
            work_id="github-change",
            inputs={
                "project": "example/agora",
                "release": "v1.0.0",
                "title": "Agora 1.0.0",
                "notes": "Governed release from an existing verified tag.",
                "artifact": "dist/agora-1.0.0-py3-none-any.whl",
            },
        )
    )

    assert agora.validate().ok
    print(f"Project: {project}")
    print(f"Issue: {issue.command}")
    print(f"Branch: {branch.command}")
    print(f"Review: {review.command}")
    print(f"Checks: {checks.command}")
    print(f"Approval: {approval.command}")
    print(f"Rejected merge: {rejected_merge}")
    print(f"Merge: {merge.command}")
    print(f"Close issue: {close_issue.command}")
    print(f"Governance snapshot: {governance.command}")
    print(f"Security snapshot: {security.command}")
    print(f"Portfolio snapshot: {portfolio.command}")
    print(f"Release: {release.command}")


if __name__ == "__main__":
    main()
