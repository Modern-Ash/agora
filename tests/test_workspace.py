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
