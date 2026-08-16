import subprocess
from pathlib import Path

import pytest

from agora.filesystem import template_root
from agora.model import (
    AddActorInput,
    AssignActorInput,
    CreateSwarmInput,
    InitInput,
    InstallToolAdapterInput,
    InvokeToolInput,
    ToolRuntimeProbe,
)
from agora.tools import load_tool_contract, probe_tool_runtime, validate_tool_adapter_contract
from agora.workspace import AgoraWorkspace

ADAPTERS = (
    ("github-repository-governance", "repository-governance"),
    ("github-releases", "release-management"),
    ("github-security", "security-scanning"),
    ("github-projects", "portfolio-management"),
)


def _workspace(tmp_path: Path, monkeypatch) -> AgoraWorkspace:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(
        "agora.workspace.shutil.which",
        lambda executable: "/usr/bin/gh" if executable == "gh" else None,
    )
    workspace = AgoraWorkspace(cwd=tmp_path)
    workspace.initialize(InitInput(integration="generic", default_method="scrum"))
    for actor in (
        AddActorInput(
            id="owner",
            name="Owner",
            kind="human",
            capabilities=["backlog-management", "acceptance"],
            scope="project",
        ),
        AddActorInput(
            id="facilitator",
            name="Facilitator",
            kind="ai-agent",
            capabilities=["facilitation", "governance"],
            scope="project",
        ),
        AddActorInput(
            id="developer",
            name="Developer",
            kind="ai-agent",
            capabilities=["implementation"],
            scope="project",
        ),
    ):
        workspace.add_actor(actor)
    workspace.create_swarm(
        CreateSwarmInput(id="delivery", objective="Govern GitHub delivery", create_branch=False)
    )
    for role, actor in (
        ("product-owner", "owner"),
        ("scrum-master", "facilitator"),
        ("developer", "developer"),
    ):
        workspace.assign_actor(AssignActorInput(swarm_id="delivery", role_id=role, actor_id=actor))
    return workspace


@pytest.mark.parametrize(("adapter_id", "tool_id"), ADAPTERS)
def test_loads_complete_github_ecosystem_adapters(adapter_id: str, tool_id: str) -> None:
    adapter = load_tool_contract(template_root() / "adapters" / "cli" / adapter_id)
    implemented = load_tool_contract(template_root() / "tools" / tool_id)

    validate_tool_adapter_contract(adapter, implemented)
    assert adapter.provider == "github"
    assert adapter.executable == "gh"
    assert adapter.version_command == ["--version"]
    assert adapter.minimum_runtime_version == "2.82.1"
    probe = probe_tool_runtime(
        adapter,
        "/usr/bin/gh",
        runner=lambda command: subprocess.CompletedProcess(
            command, 0, "gh version 2.82.1 (test)", ""
        ),
    )
    assert probe.compatible is True


def test_github_release_list_uses_only_supported_json_fields() -> None:
    adapter = load_tool_contract(template_root() / "adapters" / "cli" / "github-releases")

    assert adapter.operations["list-releases"].arguments[-1] == (
        "createdAt,isDraft,isLatest,isPrerelease,name,publishedAt,tagName"
    )


def test_governs_github_policy_release_security_and_projects(tmp_path: Path, monkeypatch) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    for adapter_id, _ in ADAPTERS:
        workspace.install_tool_adapter(
            InstallToolAdapterInput(adapter_id=adapter_id, scope="project")
        )

    rulesets = workspace.invoke_tool(
        InvokeToolInput(
            id="github-rulesets",
            tool_id="github-repository-governance",
            operation_id="list-rulesets",
            actor_id="developer",
            swarm_id="delivery",
            inputs={"project": "example/agora"},
        )
    )
    codeowners = workspace.invoke_tool(
        InvokeToolInput(
            id="github-codeowners",
            tool_id="github-repository-governance",
            operation_id="view-policy-file",
            actor_id="facilitator",
            swarm_id="delivery",
            inputs={"project": "example/agora", "path": ".github/CODEOWNERS"},
        )
    )
    release = workspace.invoke_tool(
        InvokeToolInput(
            id="github-release",
            tool_id="github-releases",
            operation_id="verify-release",
            actor_id="developer",
            swarm_id="delivery",
            inputs={"project": "example/agora", "release": "v1.0.0"},
        )
    )
    secrets = workspace.invoke_tool(
        InvokeToolInput(
            id="github-secret-alerts",
            tool_id="github-security",
            operation_id="list-secret-alerts",
            actor_id="developer",
            swarm_id="delivery",
            inputs={"project": "example/agora"},
        )
    )
    project = workspace.invoke_tool(
        InvokeToolInput(
            id="github-project-create",
            tool_id="github-projects",
            operation_id="create-project",
            actor_id="owner",
            swarm_id="delivery",
            inputs={"owner": "example", "title": "Agora delivery"},
        )
    )

    assert rulesets.command == [
        "gh",
        "api",
        "--method",
        "GET",
        "repos/example/agora/rulesets",
        "--raw-field",
        "per_page=50",
    ]
    assert codeowners.command[-2:] == [
        "--header",
        "Accept: application/vnd.github.raw+json",
    ]
    assert release.command == [
        "gh",
        "release",
        "verify",
        "v1.0.0",
        "--repo",
        "example/agora",
        "--format",
        "json",
    ]
    assert secrets.command[:5] == [
        "gh",
        "api",
        "--method",
        "GET",
        "repos/example/agora/secret-scanning/alerts",
    ]
    redaction = secrets.command[-1]
    assert "secret_type" in redaction
    assert "secret," not in redaction
    assert project.command == [
        "gh",
        "project",
        "create",
        "--owner",
        "example",
        "--title",
        "Agora delivery",
        "--format",
        "json",
    ]
    with pytest.raises(PermissionError, match="release.publish"):
        workspace.invoke_tool(
            InvokeToolInput(
                id="github-release-publish",
                tool_id="github-releases",
                operation_id="publish-release",
                actor_id="owner",
                swarm_id="delivery",
                inputs={
                    "project": "example/agora",
                    "release": "v1.0.0",
                    "title": "Agora 1.0.0",
                    "notes": "Verified release.",
                    "artifact": "dist/agora-1.0.0.whl",
                },
            )
        )
    assert workspace.validate().ok


def test_read_only_sync_launches_and_rejects_write_operations(tmp_path: Path, monkeypatch) -> None:
    prepared = _workspace(tmp_path, monkeypatch)
    prepared.install_tool_adapter(
        InstallToolAdapterInput(adapter_id="github-repository-governance", scope="project")
    )
    prepared.install_tool_adapter(
        InstallToolAdapterInput(adapter_id="github-projects", scope="project")
    )
    calls: list[list[str]] = []

    def run_tool(
        command: list[str], cwd: Path, environment: dict[str, str]
    ) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, '{"nameWithOwner":"example/agora"}', "")

    workspace = AgoraWorkspace(
        cwd=tmp_path,
        tool_runner=run_tool,
        runtime_probe=lambda contract, path: ToolRuntimeProbe(
            available=True,
            executable_path=path,
            version="2.82.1",
            compatible=True,
            detail="compatible test runtime",
        ),
    )
    snapshot = workspace.invoke_tool(
        InvokeToolInput(
            id="github-governance-snapshot",
            tool_id="github-repository-governance",
            operation_id="inspect-repository",
            actor_id="developer",
            swarm_id="delivery",
            inputs={"project": "example/agora"},
            launch=True,
            read_only_sync=True,
        )
    )

    assert snapshot.status == "completed"
    assert calls == [snapshot.command]
    assert (tmp_path / ".agora" / "tool-runs" / snapshot.id / "RESULT.md").is_file()
    with pytest.raises(PermissionError, match="Tool sync requires a read operation"):
        workspace.invoke_tool(
            InvokeToolInput(
                id="github-project-sync-write",
                tool_id="github-projects",
                operation_id="create-project",
                actor_id="owner",
                swarm_id="delivery",
                inputs={"owner": "example", "title": "Must not sync"},
                launch=True,
                read_only_sync=True,
            )
        )
    assert not (tmp_path / ".agora" / "tool-runs" / "github-project-sync-write").exists()
