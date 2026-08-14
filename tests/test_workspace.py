import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from agora.model import (
    AddActorInput,
    AddApprovalInput,
    AddArtifactInput,
    AddEvidenceInput,
    AssignActorInput,
    ChangeDelegationStatusInput,
    ChangeWorkStatusInput,
    ConfigureInput,
    CreateDelegationInput,
    CreateSwarmInput,
    CreateWorkInput,
    DelegationActorInput,
    HandoffActorInput,
    InitInput,
    InstallMethodInput,
    InstallToolInput,
    InvokeToolInput,
    SetActorRuntimeInput,
    StartSessionInput,
    TransitionWorkInput,
    WorkActorInput,
)
from agora.workspace import AgoraWorkspace

TIMESTAMP = datetime(2026, 8, 14, 12, tzinfo=UTC)


@pytest.fixture
def project(tmp_path: Path, monkeypatch) -> tuple[Path, AgoraWorkspace]:
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    return root, AgoraWorkspace(cwd=root, now=lambda: TIMESTAMP)


def test_persists_defaults_and_materializes_a_codex_project(
    project: tuple[Path, AgoraWorkspace],
) -> None:
    root, workspace = project
    workspace.configure(
        ConfigureInput(
            integration="codex",
            provider="openai",
            model="configured-by-codex",
            default_method="kanban",
        )
    )

    configuration = workspace.initialize(InitInput())

    assert configuration.integration == "codex"
    assert configuration.default_method == "kanban"
    assert configuration.max_delegation_depth == 3
    assert (root / ".agora" / "methods" / "scrum" / "METHOD.md").exists()
    assert (root / ".agora" / "methods" / "kanban" / "METHOD.md").exists()
    assert (root / ".agents" / "skills" / "agora-objective" / "SKILL.md").exists()
    assert "conventional-commits/v1.0.0" in (root / ".agora" / "STANDARDS.md").read_text()
    assert 'integration: "codex"' in (root / ".agora" / "project.md").read_text()
    assert "max-delegation-depth: 3" in (root / ".agora" / "project.md").read_text()


def test_supports_filesystem_only_environments(
    project: tuple[Path, AgoraWorkspace],
) -> None:
    _, workspace = project
    workspace.initialize(InitInput(integration="generic"))

    git_check = next(item for item in workspace.doctor() if item.name == "git")
    assert git_check.ok is False
    assert git_check.detail == "filesystem-only mode"


def test_validates_every_codex_command_and_detects_a_missing_adapter(
    project: tuple[Path, AgoraWorkspace],
) -> None:
    root, workspace = project
    workspace.initialize(InitInput(integration="codex"))

    report = workspace.validate()

    assert report.ok is True
    assert report.checked["commands"] == 8
    assert report.checked["adapters"] == 8
    missing = root / ".agents" / "skills" / "agora-execute" / "SKILL.md"
    missing.unlink()

    report = workspace.validate()
    integration_check = next(item for item in workspace.doctor() if item.name == "integration")

    assert report.ok is False
    assert any(
        item.code == "adapter.invalid" and item.path.endswith("agora-execute/SKILL.md")
        for item in report.issues
    )
    assert integration_check.ok is False
    assert integration_check.detail == "codex: 7/8 commands available"


def test_detects_claude_adapter_drift_from_portable_markdown(
    project: tuple[Path, AgoraWorkspace],
) -> None:
    root, workspace = project
    workspace.initialize(InitInput(integration="claude"))
    adapter = root / ".claude" / "commands" / "agora.review.md"
    adapter.write_text(f"{adapter.read_text()}\nLocal ungoverned override.\n")

    report = workspace.validate()

    assert report.ok is False
    assert any(
        item.code == "adapter.content-mismatch" and item.path.endswith("agora.review.md")
        for item in report.issues
    )


def test_requires_the_conventional_commits_project_standard(
    project: tuple[Path, AgoraWorkspace],
) -> None:
    root, workspace = project
    workspace.initialize(InitInput(integration="generic"))
    standards = root / ".agora" / "STANDARDS.md"
    standards.write_text(
        standards.read_text().replace('standards: ["conventional-commits/v1.0.0"]', "standards: []")
    )

    report = workspace.validate()

    assert report.ok is False
    assert any(issue.code == "standards.invalid" for issue in report.issues)


def test_installs_and_uses_a_user_defined_method_pack(
    project: tuple[Path, AgoraWorkspace],
) -> None:
    root, workspace = project
    source = Path(__file__).parents[1] / "samples" / "custom-lifecycle" / "release-flow"

    installed = workspace.install_method(InstallMethodInput(source=str(source), scope="user"))
    workspace.configure(
        ConfigureInput(
            integration="generic",
            provider="any-provider",
            model="any-model",
            default_method="release-flow",
        )
    )
    workspace.initialize(InitInput())
    swarm = workspace.create_swarm(
        CreateSwarmInput(
            id="language-neutral-delivery",
            objective="Ship a change in any technology stack",
            create_branch=False,
        )
    )

    assert installed.id == "release-flow"
    assert installed.scope == "user"
    assert (root / ".agora" / "methods" / "release-flow" / "METHOD.md").exists()
    assert swarm.method == "release-flow"
    assert swarm.required_roles == ["cycle-owner", "maker", "validator"]


def test_installs_and_inherits_a_user_tool_pack(
    project: tuple[Path, AgoraWorkspace],
) -> None:
    root, workspace = project
    source = Path(__file__).parents[1] / "templates" / "tools" / "repository"

    installed = workspace.install_tool(InstallToolInput(source=str(source), scope="user"))
    workspace.initialize(InitInput(integration="generic"))
    inherited = workspace.show_tool("repository")

    assert installed.scope == "user"
    assert installed.operations == [
        "commit",
        "create-branch",
        "current-branch",
        "show-revision",
        "status",
    ]
    assert inherited.scope == "project"
    assert (root / ".agora" / "tools" / "repository" / "TOOL.md").exists()


def test_governs_human_ai_and_nested_swarm_actors(
    project: tuple[Path, AgoraWorkspace],
) -> None:
    root, workspace = project
    workspace.initialize(InitInput(integration="generic", default_method="scrum"))
    workspace.add_actor(
        AddActorInput(
            id="owner",
            name="Product Owner",
            kind="human",
            capabilities=["backlog-management", "acceptance"],
            scope="user",
        )
    )
    workspace.add_actor(
        AddActorInput(
            id="facilitator",
            name="Facilitator",
            kind="ai-agent",
            capabilities=["facilitation", "governance"],
            scope="project",
        )
    )
    workspace.add_actor(
        AddActorInput(
            id="delivery-swarm",
            name="Delivery Swarm",
            kind="swarm",
            capabilities=["implementation"],
            scope="project",
        )
    )
    workspace.create_swarm(
        CreateSwarmInput(
            id="first-slice",
            objective="Build the Markdown-first slice",
            create_branch=False,
        )
    )
    assert workspace.show_swarm("first-slice").branch == "filesystem-only"
    workspace.assign_actor(
        AssignActorInput(swarm_id="first-slice", role_id="product-owner", actor_id="owner")
    )
    workspace.assign_actor(
        AssignActorInput(swarm_id="first-slice", role_id="scrum-master", actor_id="facilitator")
    )
    with pytest.raises(ValueError, match="lacks capabilities"):
        workspace.assign_actor(
            AssignActorInput(swarm_id="first-slice", role_id="developer", actor_id="owner")
        )
    assert (
        workspace.assign_actor(
            AssignActorInput(swarm_id="first-slice", role_id="developer", actor_id="delivery-swarm")
        ).status
        == "ready"
    )

    workspace.create_work(
        CreateWorkInput(
            swarm_id="first-slice",
            id="bootstrap",
            title="Bootstrap Agora",
            actor_id="owner",
            acceptance_criteria=[("installable", "Agora initializes a project")],
            required_artifacts=["source-code"],
        )
    )
    with pytest.raises(ValueError, match="allowed targets: planned"):
        workspace.transition_work(
            TransitionWorkInput(
                swarm_id="first-slice",
                work_id="bootstrap",
                actor_id="delivery-swarm",
                target_state="implementing",
            )
        )
    for state in ("planned", "implementing", "reviewing"):
        workspace.transition_work(
            TransitionWorkInput(
                swarm_id="first-slice",
                work_id="bootstrap",
                actor_id="delivery-swarm",
                target_state=state,
            )
        )
    workspace.transition_work(
        TransitionWorkInput(
            swarm_id="first-slice",
            work_id="bootstrap",
            actor_id="delivery-swarm",
            target_state="implementing",
        )
    )
    workspace.transition_work(
        TransitionWorkInput(
            swarm_id="first-slice",
            work_id="bootstrap",
            actor_id="delivery-swarm",
            target_state="reviewing",
        )
    )
    with pytest.raises(PermissionError, match="required roles: scrum-master"):
        workspace.transition_work(
            TransitionWorkInput(
                swarm_id="first-slice",
                work_id="bootstrap",
                actor_id="owner",
                target_state="verifying",
            )
        )
    workspace.transition_work(
        TransitionWorkInput(
            swarm_id="first-slice",
            work_id="bootstrap",
            actor_id="facilitator",
            target_state="verifying",
        )
    )
    with pytest.raises(PermissionError, match="required roles: product-owner"):
        workspace.transition_work(
            TransitionWorkInput(
                swarm_id="first-slice",
                work_id="bootstrap",
                actor_id="delivery-swarm",
                target_state="completed",
            )
        )
    with pytest.raises(ValueError, match="Gate completion failed"):
        workspace.transition_work(
            TransitionWorkInput(
                swarm_id="first-slice",
                work_id="bootstrap",
                actor_id="owner",
                target_state="completed",
            )
        )
    with pytest.raises(PermissionError, match="not allowed to perform criterion.satisfy"):
        workspace.satisfy_criterion(
            WorkActorInput(swarm_id="first-slice", work_id="bootstrap", actor_id="delivery-swarm"),
            "installable",
        )

    workspace.satisfy_criterion(
        WorkActorInput(swarm_id="first-slice", work_id="bootstrap", actor_id="owner"),
        "installable",
    )
    workspace.add_artifact(
        AddArtifactInput(
            swarm_id="first-slice",
            work_id="bootstrap",
            actor_id="delivery-swarm",
            kind="source-code",
            uri="repo://src/agora/workspace.py",
        )
    )
    workspace.add_evidence(
        AddEvidenceInput(
            swarm_id="first-slice",
            work_id="bootstrap",
            actor_id="facilitator",
            type="test-run",
            result="success",
            artifact_refs=["repo://src/agora/workspace.py"],
        )
    )
    workspace.add_approval(
        AddApprovalInput(
            swarm_id="first-slice",
            work_id="bootstrap",
            actor_id="owner",
            role_id="product-owner",
            note="Accepted for completion",
        )
    )
    completed = workspace.transition_work(
        TransitionWorkInput(
            swarm_id="first-slice",
            work_id="bootstrap",
            actor_id="owner",
            target_state="completed",
        )
    )

    assert completed.state == "completed"
    assert workspace.show_swarm("first-slice").status == "completed"
    work_root = root / ".agora" / "swarms" / "first-slice" / "work" / "bootstrap"
    assert "- [x] **installable:**" in (work_root / "WORK.md").read_text()
    assert "work.transitioned" in (work_root / "events.md").read_text()
    assert "| test-run | success |" in (work_root / "evidence.md").read_text()


def test_enforces_wip_limits_from_the_method_pack(
    project: tuple[Path, AgoraWorkspace],
) -> None:
    root, workspace = project
    _prepare_scrum_team(workspace)
    method_path = root / ".agora" / "methods" / "scrum" / "METHOD.md"
    method_path.write_text(method_path.read_text().replace('"implementing":2', '"implementing":1'))
    for work_id in ("first", "second"):
        workspace.create_work(
            CreateWorkInput(
                swarm_id="delivery",
                id=work_id,
                title=f"Work {work_id}",
                actor_id="owner",
            )
        )
        workspace.transition_work(
            TransitionWorkInput(
                swarm_id="delivery",
                work_id=work_id,
                actor_id="developer",
                target_state="planned",
            )
        )
    workspace.transition_work(
        TransitionWorkInput(
            swarm_id="delivery",
            work_id="first",
            actor_id="developer",
            target_state="implementing",
        )
    )

    with pytest.raises(ValueError, match="WIP limit reached for implementing"):
        workspace.transition_work(
            TransitionWorkInput(
                swarm_id="delivery",
                work_id="second",
                actor_id="developer",
                target_state="implementing",
            )
        )


def test_applies_a_method_defined_gate_policy(
    project: tuple[Path, AgoraWorkspace],
) -> None:
    root, workspace = project
    _prepare_scrum_team(workspace)
    workspace.create_work(
        CreateWorkInput(
            swarm_id="delivery",
            id="policy",
            title="Policy-controlled completion",
            actor_id="owner",
            acceptance_criteria=[("accepted", "The outcome is accepted")],
            required_artifacts=["report"],
        )
    )
    for state in ("planned", "implementing", "reviewing"):
        workspace.transition_work(
            TransitionWorkInput(
                swarm_id="delivery",
                work_id="policy",
                actor_id="developer",
                target_state=state,
            )
        )
    workspace.transition_work(
        TransitionWorkInput(
            swarm_id="delivery",
            work_id="policy",
            actor_id="facilitator",
            target_state="verifying",
        )
    )
    gate_path = root / ".agora" / "methods" / "scrum" / "gates" / "completion.md"
    contents = gate_path.read_text()
    gate_path.write_text(contents.replace(": true", ": false"))
    workspace.add_approval(
        AddApprovalInput(
            swarm_id="delivery",
            work_id="policy",
            actor_id="owner",
            role_id="product-owner",
        )
    )

    completed = workspace.transition_work(
        TransitionWorkInput(
            swarm_id="delivery",
            work_id="policy",
            actor_id="owner",
            target_state="completed",
        )
    )

    assert completed.state == "completed"


def test_prepares_and_launches_a_session_with_actor_runtime_override(
    project: tuple[Path, AgoraWorkspace],
) -> None:
    root, workspace = project
    _prepare_scrum_team(workspace)
    runtime = workspace.set_actor_runtime(
        SetActorRuntimeInput(
            actor_id="facilitator",
            integration="generic",
            provider="local-runtime",
            model="governance-model",
        )
    )
    calls: list[tuple[list[str], Path, dict[str, str]]] = []

    def launch(command: list[str], cwd: Path, environment: dict[str, str]) -> int:
        calls.append((command, cwd, environment))
        return 0

    session_workspace = AgoraWorkspace(cwd=root, now=lambda: TIMESTAMP, launcher=launch)
    session = session_workspace.start_session(
        StartSessionInput(
            id="governance-session",
            actor_id="facilitator",
            swarm_id="delivery",
            runner="/bin/true --session-runner",
            launch=True,
        )
    )

    assert runtime.model == "governance-model"
    assert session.status == "completed"
    assert session.integration == "generic"
    assert session.provider == "local-runtime"
    assert session.model == "governance-model"
    assert session.exit_code == 0
    assert calls[0][0] == ["/bin/true", "--session-runner"]
    assert calls[0][1] == root
    assert calls[0][2]["AGORA_ACTOR"] == "project:facilitator"
    context = Path(session.context_path).read_text()
    assert "Model: `governance-model`" in context
    assert "Roles: `scrum-master`" in context
    assert "session.completed" in (root / ".agora" / "events.md").read_text()


def test_governs_and_persists_external_tool_invocations(
    project: tuple[Path, AgoraWorkspace],
) -> None:
    root, workspace = project
    _prepare_scrum_team(workspace)
    calls: list[tuple[list[str], Path, dict[str, str]]] = []

    def run_tool(
        command: list[str], cwd: Path, environment: dict[str, str]
    ) -> subprocess.CompletedProcess[str]:
        calls.append((command, cwd, environment))
        return subprocess.CompletedProcess(command, 0, stdout=" M README.md\n", stderr="")

    tool_workspace = AgoraWorkspace(cwd=root, now=lambda: TIMESTAMP, tool_runner=run_tool)
    run = tool_workspace.invoke_tool(
        InvokeToolInput(
            id="repository-status",
            tool_id="repository",
            operation_id="status",
            actor_id="developer",
            swarm_id="delivery",
            launch=True,
        )
    )

    assert run.status == "completed"
    assert run.command == ["git", "status", "--short"]
    assert calls[0][1] == root
    assert calls[0][2]["AGORA_TOOL_RUN"].endswith("repository-status/RUN.md")
    result = root / ".agora" / "tool-runs" / "repository-status" / "RESULT.md"
    assert "M README.md" in result.read_text()
    assert "tool.completed" in (root / ".agora" / "events.md").read_text()

    commit = tool_workspace.invoke_tool(
        InvokeToolInput(
            id="conventional-commit",
            tool_id="repository",
            operation_id="commit",
            actor_id="developer",
            swarm_id="delivery",
            inputs={"message": "feat(governance): validate repository commits"},
            launch=True,
        )
    )
    assert commit.status == "completed"
    assert commit.command == [
        "git",
        "commit",
        "-m",
        "feat(governance): validate repository commits",
    ]
    with pytest.raises(ValueError, match="must match Conventional Commits"):
        tool_workspace.invoke_tool(
            InvokeToolInput(
                id="invalid-commit",
                tool_id="repository",
                operation_id="commit",
                actor_id="developer",
                swarm_id="delivery",
                inputs={"message": "save current work"},
            )
        )
    assert not (root / ".agora" / "tool-runs" / "invalid-commit").exists()

    failed_workspace = AgoraWorkspace(
        cwd=root,
        now=lambda: TIMESTAMP,
        tool_runner=lambda command, cwd, environment: subprocess.CompletedProcess(
            command, 7, stdout="", stderr="repository unavailable"
        ),
    )
    with pytest.raises(RuntimeError, match="exited with code 7"):
        failed_workspace.invoke_tool(
            InvokeToolInput(
                id="failed-status",
                tool_id="repository",
                operation_id="status",
                actor_id="developer",
                swarm_id="delivery",
                launch=True,
            )
        )
    failed_path = root / ".agora" / "tool-runs" / "failed-status"
    assert 'status: "failed"' in (failed_path / "RUN.md").read_text()
    assert "repository unavailable" in (failed_path / "RESULT.md").read_text()

    with pytest.raises(PermissionError, match="repository.write"):
        tool_workspace.invoke_tool(
            InvokeToolInput(
                id="owner-branch",
                tool_id="repository",
                operation_id="create-branch",
                actor_id="owner",
                swarm_id="delivery",
                inputs={"branch": "feature/denied"},
            )
        )

    tool_workspace.create_work(
        CreateWorkInput(
            swarm_id="delivery",
            id="approved-change",
            title="Approved repository change",
            actor_id="owner",
        )
    )
    operation_path = root / ".agora" / "tools" / "repository" / "operations" / "create-branch.md"
    operation_path.write_text(
        operation_path.read_text().replace(
            'risk: "write"', 'risk: "write"\napproval-role: "product-owner"'
        )
    )
    approved_change = InvokeToolInput(
        id="approved-branch",
        tool_id="repository",
        operation_id="create-branch",
        actor_id="developer",
        swarm_id="delivery",
        work_id="approved-change",
        inputs={"branch": "feature/approved"},
    )
    with pytest.raises(PermissionError, match="requires approval from product-owner"):
        tool_workspace.invoke_tool(approved_change)
    tool_workspace.add_approval(
        AddApprovalInput(
            swarm_id="delivery",
            work_id="approved-change",
            actor_id="owner",
            role_id="product-owner",
        )
    )
    assert tool_workspace.invoke_tool(approved_change).status == "prepared"

    with pytest.raises(ValueError, match=r"missing=\[revision\]"):
        tool_workspace.invoke_tool(
            InvokeToolInput(
                id="missing-revision",
                tool_id="repository",
                operation_id="show-revision",
                actor_id="developer",
                swarm_id="delivery",
            )
        )


def test_governs_work_management_capabilities_by_role(
    project: tuple[Path, AgoraWorkspace],
) -> None:
    root, workspace = project
    _prepare_scrum_team(workspace)

    viewed = workspace.invoke_tool(
        InvokeToolInput(
            id="view-external-work",
            tool_id="work-management",
            operation_id="view",
            actor_id="developer",
            swarm_id="delivery",
            inputs={"issue": "AGORA-42"},
        )
    )
    assert viewed.status == "prepared"
    assert viewed.command == ["workctl", "issue", "view", "AGORA-42", "--output", "json"]

    transitioned = workspace.invoke_tool(
        InvokeToolInput(
            id="transition-external-work",
            tool_id="work-management",
            operation_id="transition",
            actor_id="owner",
            swarm_id="delivery",
            inputs={"issue": "AGORA-42", "state": "In Progress"},
        )
    )
    assert transitioned.capability == "issue.transition"
    assert transitioned.status == "prepared"

    with pytest.raises(PermissionError, match="issue.transition"):
        workspace.invoke_tool(
            InvokeToolInput(
                id="developer-transition",
                tool_id="work-management",
                operation_id="transition",
                actor_id="developer",
                swarm_id="delivery",
                inputs={"issue": "AGORA-42", "state": "Done"},
            )
        )
    assert not (root / ".agora" / "tool-runs" / "developer-transition").exists()


def test_governs_ci_cd_capabilities_by_role(
    project: tuple[Path, AgoraWorkspace],
) -> None:
    root, workspace = project
    _prepare_scrum_team(workspace)

    triggered = workspace.invoke_tool(
        InvokeToolInput(
            id="trigger-ci",
            tool_id="ci-cd",
            operation_id="trigger",
            actor_id="developer",
            swarm_id="delivery",
            inputs={"pipeline": "verify", "ref": "main", "parameters": "suite=all"},
        )
    )
    assert triggered.status == "prepared"
    assert triggered.capability == "ci.run"
    assert triggered.command == [
        "cictl",
        "pipeline",
        "trigger",
        "verify",
        "--ref",
        "main",
        "--parameters",
        "suite=all",
        "--output",
        "json",
    ]

    with pytest.raises(PermissionError, match="ci.cancel"):
        workspace.invoke_tool(
            InvokeToolInput(
                id="cancel-ci",
                tool_id="ci-cd",
                operation_id="cancel-run",
                actor_id="developer",
                swarm_id="delivery",
                inputs={"run": "run-42"},
            )
        )
    with pytest.raises(PermissionError, match="deployment.create"):
        workspace.invoke_tool(
            InvokeToolInput(
                id="deploy-ci",
                tool_id="ci-cd",
                operation_id="create-deployment",
                actor_id="developer",
                swarm_id="delivery",
                inputs={"environment": "production", "artifact": "sha256:abc"},
            )
        )
    assert not (root / ".agora" / "tool-runs" / "cancel-ci").exists()
    assert not (root / ".agora" / "tool-runs" / "deploy-ci").exists()


def test_governs_knowledge_base_capabilities_by_role(
    project: tuple[Path, AgoraWorkspace],
) -> None:
    root, workspace = project
    _prepare_scrum_team(workspace)

    created = workspace.invoke_tool(
        InvokeToolInput(
            id="create-documentation",
            tool_id="knowledge-base",
            operation_id="create",
            actor_id="developer",
            swarm_id="delivery",
            inputs={
                "space": "ENG",
                "parent": "architecture",
                "title": "Governed integration",
                "body": "Document the reviewed behavior.",
            },
        )
    )
    assert created.status == "prepared"
    assert created.capability == "docs.write"
    assert created.command[:4] == ["docsctl", "page", "create", "--space"]

    with pytest.raises(PermissionError, match="docs.publish"):
        workspace.invoke_tool(
            InvokeToolInput(
                id="publish-documentation",
                tool_id="knowledge-base",
                operation_id="publish",
                actor_id="developer",
                swarm_id="delivery",
                inputs={"document": "DOC-42"},
            )
        )
    with pytest.raises(PermissionError, match="docs.archive"):
        workspace.invoke_tool(
            InvokeToolInput(
                id="archive-documentation",
                tool_id="knowledge-base",
                operation_id="archive",
                actor_id="owner",
                swarm_id="delivery",
                inputs={"document": "DOC-42"},
            )
        )
    assert not (root / ".agora" / "tool-runs" / "publish-documentation").exists()
    assert not (root / ".agora" / "tool-runs" / "archive-documentation").exists()


def test_hands_a_running_role_from_ai_to_human_and_swarm(
    project: tuple[Path, AgoraWorkspace],
) -> None:
    root, workspace = project
    _prepare_scrum_team(workspace)
    workspace.add_actor(
        AddActorInput(
            id="human-developer",
            name="Human Developer",
            kind="human",
            capabilities=["implementation"],
            scope="project",
        )
    )
    workspace.add_actor(
        AddActorInput(
            id="delivery-swarm",
            name="Delivery Swarm",
            kind="swarm",
            capabilities=["implementation"],
            scope="project",
        )
    )
    workspace.create_work(
        CreateWorkInput(
            swarm_id="delivery",
            id="handoff-work",
            title="Continue across actor forms",
            actor_id="owner",
        )
    )
    workspace.transition_work(
        TransitionWorkInput(
            swarm_id="delivery",
            work_id="handoff-work",
            actor_id="developer",
            target_state="planned",
        )
    )

    with pytest.raises(ValueError, match="lacks capabilities required by developer"):
        workspace.handoff_actor(
            HandoffActorInput(
                id="incompatible",
                swarm_id="delivery",
                role_id="developer",
                from_actor_id="developer",
                to_actor_id="facilitator",
                authorized_by="developer",
                reason="Attempt an incompatible transfer",
                work_id="handoff-work",
            )
        )

    first = workspace.handoff_actor(
        HandoffActorInput(
            id="to-human",
            swarm_id="delivery",
            role_id="developer",
            from_actor_id="developer",
            to_actor_id="human-developer",
            authorized_by="developer",
            reason="Human judgment is required for the next implementation step",
            work_id="handoff-work",
        )
    )
    assert first.from_actor == "project:developer"
    assert first.to_actor == "project:human-developer"
    assert workspace.show_swarm("delivery").assignments["developer"] == first.to_actor
    with pytest.raises(ValueError, match="is not assigned to swarm"):
        workspace.transition_work(
            TransitionWorkInput(
                swarm_id="delivery",
                work_id="handoff-work",
                actor_id="developer",
                target_state="implementing",
            )
        )

    with pytest.raises(PermissionError, match="handoff.manage"):
        workspace.handoff_actor(
            HandoffActorInput(
                id="unauthorized-management",
                swarm_id="delivery",
                role_id="developer",
                from_actor_id="human-developer",
                to_actor_id="delivery-swarm",
                authorized_by="owner",
                reason="Owner attempts to manage another role",
                work_id="handoff-work",
            )
        )
    second = workspace.handoff_actor(
        HandoffActorInput(
            id="to-swarm",
            swarm_id="delivery",
            role_id="developer",
            from_actor_id="human-developer",
            to_actor_id="delivery-swarm",
            authorized_by="facilitator",
            reason="Parallel implementation is now appropriate",
            work_id="handoff-work",
        )
    )

    assert second.authorized_by == "project:facilitator"
    assert workspace.show_swarm("delivery").assignments["developer"] == "project:delivery-swarm"
    handoff = root / ".agora" / "swarms" / "delivery" / "handoffs" / "to-swarm" / "HANDOFF.md"
    assert 'from: "project:human-developer"' in handoff.read_text()
    assert "Parallel implementation is now appropriate" in handoff.read_text()
    events = (
        root / ".agora" / "swarms" / "delivery" / "work" / "handoff-work" / "events.md"
    ).read_text()
    assert events.count("work.role-handed-off") == 2
    session = workspace.start_session(
        StartSessionInput(
            id="post-handoff",
            actor_id="delivery-swarm",
            swarm_id="delivery",
            work_id="handoff-work",
        )
    )
    context = Path(session.context_path).read_text()
    assert ".agora/swarms/delivery/handoffs/to-human/HANDOFF.md" in context
    assert ".agora/swarms/delivery/handoffs/to-swarm/HANDOFF.md" in context


def test_links_recursive_swarms_and_enforces_cycles_depth_and_readiness(
    project: tuple[Path, AgoraWorkspace],
) -> None:
    root, workspace = project
    workspace.initialize(
        InitInput(
            integration="generic",
            default_method="scrum",
            max_delegation_depth=2,
        )
    )
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

    def create_ready_swarm(swarm_id: str, developer_id: str) -> None:
        workspace.create_swarm(
            CreateSwarmInput(
                id=swarm_id,
                objective=f"Deliver {swarm_id}",
                create_branch=False,
            )
        )
        for role, actor_id in (
            ("product-owner", "owner"),
            ("scrum-master", "facilitator"),
            ("developer", developer_id),
        ):
            workspace.assign_actor(
                AssignActorInput(swarm_id=swarm_id, role_id=role, actor_id=actor_id)
            )

    create_ready_swarm("leaf", "developer")
    with pytest.raises(ValueError, match="Only an actor whose kind is swarm"):
        workspace.add_actor(
            AddActorInput(
                id="invalid-link",
                name="Invalid Link",
                kind="ai-agent",
                capabilities=["implementation"],
                scope="project",
                represented_swarm="leaf",
            )
        )
    workspace.add_actor(
        AddActorInput(
            id="leaf-swarm",
            name="Leaf Swarm",
            kind="swarm",
            capabilities=["implementation"],
            scope="project",
            represented_swarm="leaf",
        )
    )
    create_ready_swarm("middle", "leaf-swarm")
    workspace.add_actor(
        AddActorInput(
            id="middle-swarm",
            name="Middle Swarm",
            kind="swarm",
            capabilities=["implementation"],
            scope="project",
            represented_swarm="middle",
        )
    )
    create_ready_swarm("root", "middle-swarm")
    workspace.add_actor(
        AddActorInput(
            id="root-swarm",
            name="Root Swarm",
            kind="swarm",
            capabilities=["implementation"],
            scope="project",
            represented_swarm="root",
        )
    )

    session = workspace.start_session(
        StartSessionInput(
            id="delegated-session",
            actor_id="middle-swarm",
            swarm_id="root",
        )
    )
    context = Path(session.context_path).read_text()
    assert "Represented swarm: `middle`" in context
    assert ".agora/swarms/middle/SWARM.md" in context
    assert ".agora/swarms/leaf/SWARM.md" in context
    assert (
        'represented-swarm: "middle"'
        in (root / ".agora" / "actors" / "middle-swarm.md").read_text()
    )

    workspace.create_swarm(
        CreateSwarmInput(id="top", objective="Exceed the depth", create_branch=False)
    )
    workspace.assign_actor(
        AssignActorInput(swarm_id="top", role_id="product-owner", actor_id="owner")
    )
    workspace.assign_actor(
        AssignActorInput(swarm_id="top", role_id="scrum-master", actor_id="facilitator")
    )
    with pytest.raises(ValueError, match="Delegation depth 3 exceeds configured maximum 2"):
        workspace.assign_actor(
            AssignActorInput(swarm_id="top", role_id="developer", actor_id="root-swarm")
        )

    with pytest.raises(ValueError, match="Recursive swarm cycle detected"):
        workspace.handoff_actor(
            HandoffActorInput(
                id="cycle",
                swarm_id="leaf",
                role_id="developer",
                from_actor_id="developer",
                to_actor_id="root-swarm",
                authorized_by="facilitator",
                reason="Attempt to delegate back to an ancestor",
            )
        )

    workspace.create_swarm(
        CreateSwarmInput(id="forming-child", objective="Remain forming", create_branch=False)
    )
    workspace.add_actor(
        AddActorInput(
            id="forming-swarm",
            name="Forming Swarm",
            kind="swarm",
            capabilities=["implementation"],
            scope="project",
            represented_swarm="forming-child",
        )
    )
    workspace.create_swarm(
        CreateSwarmInput(id="consumer", objective="Consume child", create_branch=False)
    )
    workspace.assign_actor(
        AssignActorInput(swarm_id="consumer", role_id="product-owner", actor_id="owner")
    )
    workspace.assign_actor(
        AssignActorInput(swarm_id="consumer", role_id="scrum-master", actor_id="facilitator")
    )
    with pytest.raises(ValueError, match="must be ready or running; status=forming"):
        workspace.assign_actor(
            AssignActorInput(swarm_id="consumer", role_id="developer", actor_id="forming-swarm")
        )

    leaf_manifest = root / ".agora" / "swarms" / "leaf" / "SWARM.md"
    leaf_manifest.write_text(
        leaf_manifest.read_text().replace(
            '"developer":"project:developer"',
            '"developer":"project:root-swarm"',
        )
    )
    with pytest.raises(ValueError, match="Recursive swarm cycle detected"):
        workspace.start_session(
            StartSessionInput(
                id="tampered-cycle",
                actor_id="middle-swarm",
                swarm_id="root",
            )
        )


def test_delegates_work_to_a_child_swarm_and_collects_its_result(
    project: tuple[Path, AgoraWorkspace],
) -> None:
    root, workspace = project
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
            id="specialist",
            name="Specialist",
            kind="ai-agent",
            capabilities=["implementation"],
            scope="project",
        ),
    ):
        workspace.add_actor(actor)

    workspace.create_swarm(
        CreateSwarmInput(
            id="specialists",
            objective="Produce a specialist result",
            create_branch=False,
        )
    )
    for role, actor_id in (
        ("product-owner", "owner"),
        ("scrum-master", "facilitator"),
        ("developer", "specialist"),
    ):
        workspace.assign_actor(
            AssignActorInput(swarm_id="specialists", role_id=role, actor_id=actor_id)
        )
    workspace.add_actor(
        AddActorInput(
            id="specialist-swarm",
            name="Specialist Swarm",
            kind="swarm",
            capabilities=["implementation"],
            scope="project",
            represented_swarm="specialists",
        )
    )
    workspace.create_swarm(
        CreateSwarmInput(
            id="delivery",
            objective="Integrate delegated specialist work",
            create_branch=False,
        )
    )
    for role, actor_id in (
        ("product-owner", "owner"),
        ("scrum-master", "facilitator"),
        ("developer", "specialist-swarm"),
    ):
        workspace.assign_actor(
            AssignActorInput(swarm_id="delivery", role_id=role, actor_id=actor_id)
        )
    workspace.create_work(
        CreateWorkInput(
            swarm_id="delivery",
            id="parent-slice",
            title="Integrate the specialist output",
            actor_id="owner",
            required_artifacts=["delegated-result"],
        )
    )

    with pytest.raises(PermissionError, match="delegation.manage"):
        workspace.create_delegation(
            CreateDelegationInput(
                id="unauthorized-task",
                parent_swarm_id="delivery",
                parent_work_id="parent-slice",
                child_actor_id="specialist-swarm",
                child_work_id="unauthorized-child",
                actor_id="owner",
                title="Attempt unauthorized delegation management",
            )
        )

    proposed = workspace.create_delegation(
        CreateDelegationInput(
            id="specialist-task",
            parent_swarm_id="delivery",
            parent_work_id="parent-slice",
            child_actor_id="specialist-swarm",
            child_work_id="child-slice",
            actor_id="specialist-swarm",
            title="Produce the specialist output",
            description="Return a verified result to the parent work item.",
            acceptance_criteria=[("usable", "The output can be integrated")],
            required_artifacts=["child-result"],
            result_kind="delegated-result",
        )
    )
    assert proposed.status == "proposed"
    with pytest.raises(ValueError, match="cannot be collected while proposed"):
        workspace.collect_delegation(
            DelegationActorInput(delegation_id="specialist-task", actor_id="specialist-swarm")
        )

    accepted = workspace.accept_delegation(
        DelegationActorInput(delegation_id="specialist-task", actor_id="owner")
    )
    assert accepted.status == "accepted"
    child_root = root / ".agora" / "swarms" / "specialists" / "work" / "child-slice"
    child_manifest = (child_root / "WORK.md").read_text()
    assert 'delegation: "specialist-task"' in child_manifest
    assert 'parent-work: "delivery/parent-slice"' in child_manifest
    child_session = workspace.start_session(
        StartSessionInput(
            id="delegated-child-session",
            actor_id="specialist",
            swarm_id="specialists",
            work_id="child-slice",
        )
    )
    assert (
        ".agora/delegations/specialist-task/DELEGATION.md"
        in Path(child_session.context_path).read_text()
    )
    with pytest.raises(ValueError, match="is not complete"):
        workspace.collect_delegation(
            DelegationActorInput(delegation_id="specialist-task", actor_id="specialist-swarm")
        )

    for state in ("planned", "implementing", "reviewing"):
        workspace.transition_work(
            TransitionWorkInput(
                swarm_id="specialists",
                work_id="child-slice",
                actor_id="specialist",
                target_state=state,
            )
        )
    workspace.transition_work(
        TransitionWorkInput(
            swarm_id="specialists",
            work_id="child-slice",
            actor_id="facilitator",
            target_state="verifying",
        )
    )
    workspace.satisfy_criterion(
        WorkActorInput(swarm_id="specialists", work_id="child-slice", actor_id="owner"),
        "usable",
    )
    workspace.add_artifact(
        AddArtifactInput(
            swarm_id="specialists",
            work_id="child-slice",
            actor_id="specialist",
            kind="child-result",
            uri="repo://specialists/result.md",
        )
    )
    workspace.add_evidence(
        AddEvidenceInput(
            swarm_id="specialists",
            work_id="child-slice",
            actor_id="facilitator",
            type="review",
            result="success",
            artifact_refs=["repo://specialists/result.md"],
        )
    )
    workspace.add_approval(
        AddApprovalInput(
            swarm_id="specialists",
            work_id="child-slice",
            actor_id="owner",
            role_id="product-owner",
        )
    )
    workspace.transition_work(
        TransitionWorkInput(
            swarm_id="specialists",
            work_id="child-slice",
            actor_id="owner",
            target_state="completed",
        )
    )
    assert workspace.show_swarm("specialists").status == "completed"

    collected = workspace.collect_delegation(
        DelegationActorInput(delegation_id="specialist-task", actor_id="specialist-swarm")
    )
    assert collected.status == "collected"
    assert collected.collected_by == "project:specialist-swarm"
    parent = workspace.show_work("delivery", "parent-slice")
    assert parent.artifact_kinds == ["delegated-result"]
    assert parent.evidence_results == ["success"]
    parent_root = root / ".agora" / "swarms" / "delivery" / "work" / "parent-slice"
    assert (
        "agora://swarms/specialists/work/child-slice" in (parent_root / "artifacts.md").read_text()
    )
    assert "delegation.collected" in (parent_root / "events.md").read_text()
    assert (
        'status: "collected"'
        in (root / ".agora" / "delegations" / "specialist-task" / "DELEGATION.md").read_text()
    )
    with pytest.raises(ValueError, match="cannot be collected while collected"):
        workspace.collect_delegation(
            DelegationActorInput(delegation_id="specialist-task", actor_id="specialist-swarm")
        )


def test_lists_and_summarizes_operational_workspace_state(
    project: tuple[Path, AgoraWorkspace],
) -> None:
    _, workspace = project
    _prepare_scrum_team(workspace)
    workspace.create_work(
        CreateWorkInput(
            swarm_id="delivery",
            id="observable-work",
            title="Expose operational state",
            actor_id="owner",
        )
    )
    workspace.start_session(
        StartSessionInput(
            id="observable-session",
            actor_id="developer",
            swarm_id="delivery",
            work_id="observable-work",
        )
    )
    workspace.invoke_tool(
        InvokeToolInput(
            id="observable-tool-run",
            tool_id="repository",
            operation_id="status",
            actor_id="developer",
            swarm_id="delivery",
            work_id="observable-work",
        )
    )

    status = workspace.status()

    assert status.counts == {
        "actors": 3,
        "methods": 2,
        "tools": 4,
        "swarms": 1,
        "work": 1,
        "delegations": 0,
        "sessions": 1,
        "tool-runs": 1,
    }
    assert status.swarm_statuses == {"ready": 1}
    assert status.work_states == {"specified": 1}
    assert status.attention["active-work"] == ["delivery/observable-work"]
    assert status.attention["unfinished-sessions"] == ["observable-session"]
    assert [item.id for item in workspace.list_methods()] == ["kanban", "scrum"]
    assert [item.id for item in workspace.list_tools()] == [
        "ci-cd",
        "knowledge-base",
        "repository",
        "work-management",
    ]
    assert [item.id for item in workspace.list_actors("project")] == [
        "developer",
        "facilitator",
        "owner",
    ]
    assert [item.id for item in workspace.list_swarms("ready")] == ["delivery"]
    assert [item.id for item in workspace.list_work("delivery", "specified")] == ["observable-work"]
    assert [item.id for item in workspace.list_sessions("prepared")] == ["observable-session"]
    assert [item.id for item in workspace.list_tool_runs("prepared")] == ["observable-tool-run"]
    work_events = workspace.list_events(
        swarm_id="delivery", work_id="observable-work", type_="work.created"
    )
    assert len(work_events) == 1
    assert work_events[0].scope == "work:delivery/observable-work"
    assert workspace.validate().ok is True


def test_validation_reports_multiple_workspace_integrity_errors(
    project: tuple[Path, AgoraWorkspace],
) -> None:
    root, workspace = project
    _prepare_scrum_team(workspace)
    workspace.create_work(
        CreateWorkInput(
            swarm_id="delivery",
            id="invalid-work",
            title="Detect invalid state",
            actor_id="owner",
        )
    )
    work_path = root / ".agora" / "swarms" / "delivery" / "work" / "invalid-work"
    manifest = work_path / "WORK.md"
    manifest.write_text(manifest.read_text().replace('state: "specified"', 'state: "unknown"'))
    actor_path = root / ".agora" / "actors" / "developer.md"
    actor_path.write_text(actor_path.read_text().replace('id: "developer"', 'id: "renamed"'))
    with (work_path / "events.md").open("a", encoding="utf-8") as stream:
        stream.write("- malformed event\n")
    (root / ".agora" / "sessions" / "orphan-session").mkdir()

    report = workspace.validate()
    codes = {item.code for item in report.issues}

    assert report.ok is False
    assert "actor.id-mismatch" in codes
    assert "work.state-invalid" in codes
    assert "events.invalid" in codes
    assert "session.invalid" in codes
    assert report.checked["work"] == 1


def test_blocks_resumes_and_cancels_work_with_durable_history(
    project: tuple[Path, AgoraWorkspace],
) -> None:
    _, workspace = project
    _prepare_scrum_team(workspace)
    workspace.create_work(
        CreateWorkInput(
            swarm_id="delivery",
            id="interruptible-work",
            title="Handle an external dependency",
            actor_id="owner",
        )
    )

    blocked = workspace.block_work(
        ChangeWorkStatusInput(
            swarm_id="delivery",
            work_id="interruptible-work",
            actor_id="developer",
            reason="Waiting for the upstream contract",
            id="work-blocked",
        )
    )

    assert blocked.target_status == "blocked"
    assert workspace.show_swarm("delivery").status == "blocked"
    assert workspace.status().attention["blocked-work"] == ["delivery/interruptible-work"]
    with pytest.raises(ValueError, match="is blocked"):
        workspace.transition_work(
            TransitionWorkInput(
                swarm_id="delivery",
                work_id="interruptible-work",
                actor_id="developer",
                target_state="planned",
            )
        )
    with pytest.raises(FileExistsError, match="work-blocked"):
        workspace.resume_work(
            ChangeWorkStatusInput(
                swarm_id="delivery",
                work_id="interruptible-work",
                actor_id="facilitator",
                reason="This id already belongs to the blocking decision",
                id="work-blocked",
            )
        )
    assert workspace.show_work("delivery", "interruptible-work").operational_status == "blocked"

    workspace.resume_work(
        ChangeWorkStatusInput(
            swarm_id="delivery",
            work_id="interruptible-work",
            actor_id="facilitator",
            reason="The contract is available",
            id="work-resumed",
        )
    )
    assert workspace.show_swarm("delivery").status == "ready"
    workspace.transition_work(
        TransitionWorkInput(
            swarm_id="delivery",
            work_id="interruptible-work",
            actor_id="developer",
            target_state="planned",
        )
    )
    assert workspace.show_swarm("delivery").status == "running"
    workspace.cancel_work(
        ChangeWorkStatusInput(
            swarm_id="delivery",
            work_id="interruptible-work",
            actor_id="owner",
            reason="The product objective no longer needs this work",
            id="work-cancelled",
        )
    )

    work = workspace.show_work("delivery", "interruptible-work")
    assert work.state == "planned"
    assert work.operational_status == "cancelled"
    assert workspace.show_swarm("delivery").status == "cancelled"
    assert [
        item.operational_status
        for item in workspace.list_work("delivery", operational_status="cancelled")
    ] == ["cancelled"]
    assert [
        item.target_status
        for item in workspace.list_work_status_changes("delivery", "interruptible-work")
    ] == ["blocked", "active", "cancelled"]
    with pytest.raises(ValueError, match="cancelled -> active"):
        workspace.resume_work(
            ChangeWorkStatusInput(
                swarm_id="delivery",
                work_id="interruptible-work",
                actor_id="facilitator",
                reason="Attempt to reopen terminally cancelled work",
            )
        )
    assert workspace.validate().ok is True


def test_governs_delegation_interruptions_rejection_and_cancellation(
    project: tuple[Path, AgoraWorkspace],
) -> None:
    _, workspace = project
    _prepare_delegated_scrum_teams(workspace)

    first = workspace.create_delegation(
        CreateDelegationInput(
            id="rejected-delegation",
            parent_swarm_id="delivery",
            parent_work_id="parent-work",
            child_actor_id="specialist-swarm",
            child_work_id="rejected-child-work",
            actor_id="specialist-swarm",
            title="Explore an unsuitable approach",
        )
    )
    workspace.block_delegation(
        ChangeDelegationStatusInput(
            delegation_id=first.id,
            actor_id="facilitator",
            reason="Clarify the requested boundary",
            id="delegation-blocked",
        )
    )
    with pytest.raises(ValueError, match="cannot be accepted while blocked"):
        workspace.accept_delegation(DelegationActorInput(delegation_id=first.id, actor_id="owner"))
    workspace.resume_delegation(
        ChangeDelegationStatusInput(
            delegation_id=first.id,
            actor_id="facilitator",
            reason="The boundary is now explicit",
            id="delegation-resumed",
        )
    )
    workspace.reject_delegation(
        ChangeDelegationStatusInput(
            delegation_id=first.id,
            actor_id="owner",
            reason="The child swarm cannot meet the requested contract",
            id="delegation-rejected",
        )
    )
    assert workspace.show_delegation(first.id).status == "rejected"

    second = workspace.create_delegation(
        CreateDelegationInput(
            id="cancelled-delegation",
            parent_swarm_id="delivery",
            parent_work_id="parent-work",
            child_actor_id="specialist-swarm",
            child_work_id="cancelled-child-work",
            actor_id="specialist-swarm",
            title="Produce a result that becomes unnecessary",
        )
    )
    workspace.accept_delegation(DelegationActorInput(delegation_id=second.id, actor_id="owner"))
    workspace.block_delegation(
        ChangeDelegationStatusInput(
            delegation_id=second.id,
            actor_id="facilitator",
            reason="Parent priorities are under review",
            id="accepted-delegation-blocked",
        )
    )
    workspace.resume_delegation(
        ChangeDelegationStatusInput(
            delegation_id=second.id,
            actor_id="facilitator",
            reason="The priority review is complete",
            id="accepted-delegation-resumed",
        )
    )
    with pytest.raises(ValueError, match="open delegations"):
        workspace.cancel_work(
            ChangeWorkStatusInput(
                swarm_id="delivery",
                work_id="parent-work",
                actor_id="owner",
                reason="Attempt to cancel before closing child contracts",
            )
        )
    assert workspace.show_work("delivery", "parent-work").operational_status == "active"
    workspace.cancel_delegation(
        ChangeDelegationStatusInput(
            delegation_id=second.id,
            actor_id="owner",
            reason="The parent no longer needs this result",
            id="delegation-cancelled",
        )
    )

    cancelled = workspace.show_delegation(second.id)
    assert cancelled.status == "cancelled"
    assert workspace.show_work("specialists", "cancelled-child-work").operational_status == "active"
    assert [item.target_status for item in workspace.list_delegation_status_changes(second.id)] == [
        "accepted",
        "blocked",
        "accepted",
        "cancelled",
    ]
    assert workspace.status().attention["open-delegations"] == []
    assert workspace.validate().ok is True


def test_validation_reports_corrupt_status_change_semantics(
    project: tuple[Path, AgoraWorkspace],
) -> None:
    root, workspace = project
    _prepare_scrum_team(workspace)
    workspace.create_work(
        CreateWorkInput(
            swarm_id="delivery",
            id="audited-work",
            title="Audit interruption history",
            actor_id="owner",
        )
    )
    workspace.block_work(
        ChangeWorkStatusInput(
            swarm_id="delivery",
            work_id="audited-work",
            actor_id="developer",
            reason="Wait for a dependency",
            id="audited-block",
        )
    )
    status_path = (
        root
        / ".agora"
        / "swarms"
        / "delivery"
        / "work"
        / "audited-work"
        / "status-changes"
        / "audited-block"
        / "STATUS.md"
    )
    status_path.write_text(
        status_path.read_text()
        .replace('action: "work.block"', 'action: "work.cancel"')
        .replace("sequence: 1", "sequence: 3")
    )

    report = workspace.validate()
    codes = {item.code for item in report.issues}

    assert report.ok is False
    assert "status-change.transition-invalid" in codes
    assert "status-change.sequence-invalid" in codes


def _prepare_scrum_team(workspace: AgoraWorkspace) -> None:
    workspace.initialize(
        InitInput(
            integration="generic",
            provider="project-provider",
            model="project-model",
            default_method="scrum",
        )
    )
    workspace.add_actor(
        AddActorInput(
            id="owner",
            name="Owner",
            kind="human",
            capabilities=["backlog-management", "acceptance"],
            scope="project",
        )
    )
    workspace.add_actor(
        AddActorInput(
            id="facilitator",
            name="Facilitator",
            kind="ai-agent",
            capabilities=["facilitation", "governance"],
            scope="project",
        )
    )
    workspace.add_actor(
        AddActorInput(
            id="developer",
            name="Developer",
            kind="ai-agent",
            capabilities=["implementation"],
            scope="project",
        )
    )
    workspace.create_swarm(
        CreateSwarmInput(id="delivery", objective="Deliver governed work", create_branch=False)
    )
    for role, actor in (
        ("product-owner", "owner"),
        ("scrum-master", "facilitator"),
        ("developer", "developer"),
    ):
        workspace.assign_actor(AssignActorInput(swarm_id="delivery", role_id=role, actor_id=actor))


def _prepare_delegated_scrum_teams(workspace: AgoraWorkspace) -> None:
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
            id="specialist",
            name="Specialist",
            kind="ai-agent",
            capabilities=["implementation"],
            scope="project",
        ),
    ):
        workspace.add_actor(actor)
    workspace.create_swarm(
        CreateSwarmInput(id="specialists", objective="Produce results", create_branch=False)
    )
    for role, actor in (
        ("product-owner", "owner"),
        ("scrum-master", "facilitator"),
        ("developer", "specialist"),
    ):
        workspace.assign_actor(
            AssignActorInput(swarm_id="specialists", role_id=role, actor_id=actor)
        )
    workspace.add_actor(
        AddActorInput(
            id="specialist-swarm",
            name="Specialist Swarm",
            kind="swarm",
            capabilities=["implementation"],
            scope="project",
            represented_swarm="specialists",
        )
    )
    workspace.create_swarm(
        CreateSwarmInput(id="delivery", objective="Integrate results", create_branch=False)
    )
    for role, actor in (
        ("product-owner", "owner"),
        ("scrum-master", "facilitator"),
        ("developer", "specialist-swarm"),
    ):
        workspace.assign_actor(AssignActorInput(swarm_id="delivery", role_id=role, actor_id=actor))
    workspace.create_work(
        CreateWorkInput(
            swarm_id="delivery",
            id="parent-work",
            title="Integrate delegated work",
            actor_id="owner",
        )
    )
