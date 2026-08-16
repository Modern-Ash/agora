import io
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from agora.cli import main
from agora.model import (
    AddActorInput,
    AddApprovalInput,
    AddArtifactInput,
    AddEnvironmentInput,
    AddEvidenceInput,
    AssignActorInput,
    ChangeDelegationStatusInput,
    ChangeWorkStatusInput,
    ConfigureInput,
    CreateDelegationInput,
    CreateSwarmInput,
    CreateWorkInput,
    DecomposeWorkInput,
    DelegateApprovalInput,
    DelegationActorInput,
    HandoffActorInput,
    InitInput,
    InstallMethodInput,
    InstallToolAdapterInput,
    InstallToolInput,
    InvokeToolInput,
    RevokeApprovalDelegationInput,
    SetActorRuntimeInput,
    StartSessionInput,
    ToolRuntimeProbe,
    TransitionWorkInput,
    WaiveGateInput,
    WorkActorInput,
)
from agora.workspace import AgoraWorkspace

TIMESTAMP = datetime(2026, 8, 14, 12, tzinfo=UTC)


@pytest.fixture
def project(tmp_path: Path, monkeypatch) -> tuple[Path, AgoraWorkspace]:
    root = tmp_path / "project"
    root.mkdir()
    for relative in ("src/agora/workspace.py", "specialists/result.md"):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("verified fixture\n", encoding="utf-8")
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
    assert (root / ".agora" / "environments" / "README.md").exists()
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


def test_doctor_fails_when_git_ignores_governance_state(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    root = tmp_path / "project"
    root.mkdir()
    subprocess.run(["git", "init", "--initial-branch", "main"], cwd=root, check=True)
    (root / ".gitignore").write_text(".agora/\n", encoding="utf-8")
    workspace = AgoraWorkspace(cwd=root)
    workspace.initialize(InitInput(integration="generic"))
    output = io.StringIO()

    exit_code = main(["doctor"], cwd=root, stdout=output, stderr=io.StringIO())

    assert exit_code == 1
    report = json.loads(output.getvalue())
    persistence = next(check for check in report["checks"] if check["name"] == "git-persistence")
    assert persistence["ok"] is False
    assert persistence["detail"].startswith("ignored: .agora/")


def test_doctor_reports_native_runtime_availability(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    workspace = AgoraWorkspace(cwd=tmp_path)
    workspace.initialize(InitInput(integration="codex"))
    monkeypatch.setattr("agora.workspace.shutil.which", lambda executable: None)

    unavailable = next(item for item in workspace.doctor() if item.name == "runtime")

    assert unavailable.ok is False
    assert unavailable.detail == "codex not found on PATH"

    monkeypatch.setattr(
        "agora.workspace.shutil.which",
        lambda executable: "/opt/team/bin/codex" if executable == "codex" else None,
    )
    available = next(item for item in workspace.doctor() if item.name == "runtime")
    assert available.ok is True
    assert available.detail == "/opt/team/bin/codex"


def test_defaults_new_projects_to_spec_driven_without_prior_configuration(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    workspace = AgoraWorkspace(cwd=tmp_path)

    configuration = workspace.initialize(InitInput())

    assert configuration.default_method == "spec-driven"
    assert (tmp_path / ".agora" / "methods" / "spec-driven" / "METHOD.md").exists()
    assert (tmp_path / ".agora" / "methods" / "scrum" / "METHOD.md").exists()
    assert (tmp_path / ".agora" / "methods" / "kanban" / "METHOD.md").exists()


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
    source = Path(__file__).parents[1] / "packs" / "tools" / "repository"

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
    assert workspace.validate().ok
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


def test_waives_only_named_outstanding_gate_obligations(
    project: tuple[Path, AgoraWorkspace],
) -> None:
    root, workspace = project
    _prepare_scrum_team(workspace)
    workspace.create_work(
        CreateWorkInput(
            swarm_id="delivery",
            id="exceptional-release",
            title="Release with accepted residual risk",
            actor_id="owner",
            acceptance_criteria=[("load-test", "Complete the load test")],
            required_artifacts=["performance-report"],
        )
    )
    for state, actor in (
        ("planned", "developer"),
        ("implementing", "developer"),
        ("reviewing", "developer"),
        ("verifying", "facilitator"),
    ):
        workspace.transition_work(
            TransitionWorkInput(
                swarm_id="delivery",
                work_id="exceptional-release",
                actor_id=actor,
                target_state=state,
            )
        )

    with pytest.raises(PermissionError, match="not allowed to perform gate.waive"):
        workspace.waive_gate(
            WaiveGateInput(
                id="developer-exception",
                swarm_id="delivery",
                work_id="exceptional-release",
                gate_id="completion",
                actor_id="developer",
                reason="Unauthorized",
                evidence_refs=["repo://risk/unauthorized.md"],
                criteria=["load-test"],
            )
        )
    with pytest.raises(ValueError, match="not outstanding gate obligations"):
        workspace.waive_gate(
            WaiveGateInput(
                id="invalid-exception",
                swarm_id="delivery",
                work_id="exceptional-release",
                gate_id="completion",
                actor_id="owner",
                reason="Invalid scope",
                evidence_refs=["repo://risk/invalid.md"],
                criteria=["undeclared"],
            )
        )

    waiver = workspace.waive_gate(
        WaiveGateInput(
            id="accepted-release-risk",
            swarm_id="delivery",
            work_id="exceptional-release",
            gate_id="completion",
            actor_id="owner",
            reason="Customer deadline accepted by product governance",
            evidence_refs=["repo://risk/accepted-release-risk.md"],
            criteria=["load-test"],
            artifacts=["performance-report"],
            successful_evidence=True,
            approval_roles=["product-owner"],
        )
    )
    completed = workspace.transition_work(
        TransitionWorkInput(
            swarm_id="delivery",
            work_id="exceptional-release",
            actor_id="owner",
            target_state="completed",
        )
    )

    assert completed.state == "completed"
    assert workspace.list_gate_waivers("delivery", "exceptional-release") == [waiver]
    assert workspace.validate().checked["gate-waivers"] == 1
    waiver_path = Path(waiver.path)
    waiver_path.write_text(waiver_path.read_text().replace('gate: "completion"', 'gate: "unknown"'))
    report = workspace.validate()
    assert any(issue.code == "gate-waiver.gate-missing" for issue in report.issues)


def test_delegates_one_work_scoped_approval_and_supports_revocation(
    project: tuple[Path, AgoraWorkspace],
) -> None:
    root, workspace = project
    _prepare_scrum_team(workspace)
    workspace.add_actor(
        AddActorInput(
            id="alternate-owner",
            name="Alternate Product Owner",
            kind="human",
            capabilities=["backlog-management", "acceptance"],
            scope="project",
        )
    )
    for work_id in ("delegated-approval", "revoked-approval"):
        workspace.create_work(
            CreateWorkInput(
                swarm_id="delivery",
                id=work_id,
                title=f"Exercise {work_id}",
                actor_id="owner",
            )
        )

    delegated = workspace.delegate_approval(
        DelegateApprovalInput(
            id="release-approval",
            swarm_id="delivery",
            work_id="delegated-approval",
            role_id="product-owner",
            actor_id="owner",
            to_actor_id="alternate-owner",
            reason="The primary owner is unavailable for this decision",
        )
    )
    assert delegated.status == "active"
    with pytest.raises(ValueError, match="active Approval Delegations"):
        workspace.cancel_work(
            ChangeWorkStatusInput(
                swarm_id="delivery",
                work_id="delegated-approval",
                actor_id="owner",
                reason="Attempt closure while approval authority remains active",
            )
        )
    with pytest.raises(ValueError, match="active Approval Delegations"):
        workspace.handoff_actor(
            HandoffActorInput(
                swarm_id="delivery",
                role_id="product-owner",
                from_actor_id="owner",
                to_actor_id="alternate-owner",
                authorized_by="owner",
                reason="Attempt a role transfer while authority remains active",
            )
        )
    with pytest.raises(ValueError, match="Revoke the active Approval Delegation"):
        workspace.add_approval(
            AddApprovalInput(
                swarm_id="delivery",
                work_id="delegated-approval",
                actor_id="owner",
                role_id="product-owner",
            )
        )
    with pytest.raises(PermissionError, match="belongs to project:alternate-owner"):
        workspace.add_approval(
            AddApprovalInput(
                swarm_id="delivery",
                work_id="delegated-approval",
                actor_id="developer",
                role_id="product-owner",
                delegation_id="release-approval",
            )
        )

    approved = workspace.add_approval(
        AddApprovalInput(
            swarm_id="delivery",
            work_id="delegated-approval",
            actor_id="alternate-owner",
            role_id="product-owner",
            note="Approved under delegated authority",
            delegation_id="release-approval",
        )
    )
    used = workspace.list_approval_delegations("delivery", "delegated-approval", "used")[0]
    assert approved.approval_roles == ["product-owner"]
    assert used.status == "used"
    assert used.used_by == "project:alternate-owner"
    approval_path = Path(approved.path) / "approvals.md"
    assert "project:alternate-owner via approval-delegation:release-approval" in (
        approval_path.read_text()
    )
    with pytest.raises(ValueError, match="is not active"):
        workspace.add_approval(
            AddApprovalInput(
                swarm_id="delivery",
                work_id="delegated-approval",
                actor_id="alternate-owner",
                role_id="product-owner",
                delegation_id="release-approval",
            )
        )

    workspace.delegate_approval(
        DelegateApprovalInput(
            id="withdrawn-approval",
            swarm_id="delivery",
            work_id="revoked-approval",
            role_id="product-owner",
            actor_id="owner",
            to_actor_id="alternate-owner",
            reason="Temporary coverage",
        )
    )
    revoked = workspace.revoke_approval_delegation(
        RevokeApprovalDelegationInput(
            delegation_id="withdrawn-approval",
            swarm_id="delivery",
            work_id="revoked-approval",
            actor_id="owner",
            reason="The primary owner resumed the decision",
        )
    )
    assert revoked.status == "revoked"
    assert revoked.revoked_by == "project:owner"
    assert revoked.revoked_reason == "The primary owner resumed the decision"
    with pytest.raises(ValueError, match="is not active"):
        workspace.add_approval(
            AddApprovalInput(
                swarm_id="delivery",
                work_id="revoked-approval",
                actor_id="alternate-owner",
                role_id="product-owner",
                delegation_id="withdrawn-approval",
            )
        )
    assert workspace.validate().ok
    delegation_path = (
        root
        / ".agora"
        / "swarms"
        / "delivery"
        / "work"
        / "revoked-approval"
        / "approval-delegations"
        / "withdrawn-approval"
        / "DELEGATION.md"
    )
    assert delegation_path.is_file()
    delegation_path.write_text(
        delegation_path.read_text().replace('status: "revoked"', 'status: "used"')
    )
    report = workspace.validate()
    assert any(issue.code == "approval-delegation.invalid" for issue in report.issues)


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


def test_discovers_installs_and_governs_the_github_actions_cli_adapter(
    project: tuple[Path, AgoraWorkspace], monkeypatch
) -> None:
    root, workspace = project
    monkeypatch.setattr(
        "agora.workspace.shutil.which",
        lambda executable: "/usr/bin/gh" if executable == "gh" else None,
    )

    available = workspace.list_tool_adapters(available_only=True)
    assert [(item.id, item.provider, item.transport) for item in available] == [
        ("github-actions", "github", "cli"),
        ("github-issues", "github", "cli"),
        ("github-projects", "github", "cli"),
        ("github-pull-requests", "github", "cli"),
        ("github-releases", "github", "cli"),
        ("github-repository-governance", "github", "cli"),
        ("github-security", "github", "cli"),
    ]
    assert available[0].runtime_available is True
    assert available[0].installed_scopes == []

    _prepare_scrum_team(workspace)
    installed = workspace.install_tool_adapter(
        InstallToolAdapterInput(adapter_id="github-actions", scope="project")
    )
    assert installed.executable == "gh"
    assert installed.implements == "ci-cd"
    adapters = {item.id: item for item in workspace.list_tool_adapters()}
    assert adapters["github-actions"].installed_scopes == ["project"]

    calls: list[list[str]] = []

    def run_tool(
        command: list[str], cwd: Path, environment: dict[str, str]
    ) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout='[{"status":"completed"}]', stderr="")

    governed = AgoraWorkspace(
        cwd=root,
        now=lambda: TIMESTAMP,
        tool_runner=run_tool,
        runtime_probe=lambda contract, path: ToolRuntimeProbe(
            available=True,
            executable_path=path,
            version="2.82.1",
            compatible=True,
            detail="compatible test runtime",
        ),
    )
    listed = governed.invoke_tool(
        InvokeToolInput(
            id="github-actions-runs",
            tool_id="github-actions",
            operation_id="list-runs",
            actor_id="developer",
            swarm_id="delivery",
            inputs={"pipeline": "verify.yml"},
            launch=True,
        )
    )
    triggered = governed.invoke_tool(
        InvokeToolInput(
            id="github-actions-trigger",
            tool_id="github-actions",
            operation_id="trigger",
            actor_id="developer",
            swarm_id="delivery",
            inputs={"pipeline": "verify.yml", "ref": "main", "parameters": "suite=all"},
            launch=True,
        )
    )

    assert listed.status == "completed"
    assert calls[0][:5] == ["gh", "run", "list", "--workflow", "verify.yml"]
    assert triggered.command == [
        "gh",
        "workflow",
        "run",
        "verify.yml",
        "--ref",
        "main",
        "--raw-field",
        "suite=all",
    ]

    incompatible = AgoraWorkspace(
        cwd=root,
        now=lambda: TIMESTAMP,
        tool_runner=run_tool,
        runtime_probe=lambda contract, path: ToolRuntimeProbe(
            available=True,
            executable_path=path,
            version="2.0.0",
            compatible=False,
            detail="Runtime 2.0.0 does not satisfy minimum version 2.45.0",
        ),
    )
    with pytest.raises(RuntimeError, match="runtime compatibility check failed"):
        incompatible.invoke_tool(
            InvokeToolInput(
                id="github-actions-incompatible",
                tool_id="github-actions",
                operation_id="list-runs",
                actor_id="developer",
                swarm_id="delivery",
                inputs={"pipeline": "verify.yml"},
                launch=True,
            )
        )
    assert not (root / ".agora" / "tool-runs" / "github-actions-incompatible").exists()

    with pytest.raises(PermissionError, match="ci.cancel"):
        governed.invoke_tool(
            InvokeToolInput(
                id="github-actions-cancel",
                tool_id="github-actions",
                operation_id="cancel-run",
                actor_id="developer",
                swarm_id="delivery",
                inputs={"run": "123"},
            )
        )

    cancel_path = root / ".agora" / "tools" / "github-actions" / "operations" / "cancel-run.md"
    cancel_path.write_text(cancel_path.read_text().replace("ci.cancel", "ci.read"))
    report = governed.validate()
    assert any(item.code == "tool-adapter.contract-invalid" for item in report.issues)


def test_installs_and_governs_the_gitlab_ci_cli_adapter(
    project: tuple[Path, AgoraWorkspace], monkeypatch
) -> None:
    root, workspace = project
    monkeypatch.setattr(
        "agora.workspace.shutil.which",
        lambda executable: "/usr/bin/glab" if executable == "glab" else None,
    )
    _prepare_scrum_team(workspace)
    installed = workspace.install_tool_adapter(
        InstallToolAdapterInput(adapter_id="gitlab-ci", scope="project")
    )
    assert installed.implements_operations == ["list-runs", "view-run", "cancel-run"]

    listed = workspace.invoke_tool(
        InvokeToolInput(
            id="gitlab-ci-runs",
            tool_id="gitlab-ci",
            operation_id="list-runs",
            actor_id="developer",
            swarm_id="delivery",
            inputs={"pipeline": "verify"},
        )
    )
    viewed = workspace.invoke_tool(
        InvokeToolInput(
            id="gitlab-ci-run",
            tool_id="gitlab-ci",
            operation_id="view-run",
            actor_id="developer",
            swarm_id="delivery",
            inputs={"run": "12345"},
        )
    )

    assert listed.command == [
        "glab",
        "ci",
        "list",
        "--name",
        "verify",
        "--per-page",
        "50",
        "--output",
        "json",
    ]
    assert viewed.command == [
        "glab",
        "ci",
        "get",
        "--pipeline-id",
        "12345",
        "--with-job-details",
        "--output",
        "json",
    ]
    with pytest.raises(PermissionError, match="ci.cancel"):
        workspace.invoke_tool(
            InvokeToolInput(
                id="gitlab-ci-cancel",
                tool_id="gitlab-ci",
                operation_id="cancel-run",
                actor_id="developer",
                swarm_id="delivery",
                inputs={"run": "12345"},
            )
        )
    assert not (root / ".agora" / "tool-runs" / "gitlab-ci-cancel").exists()

    for operation in ("trigger", "view-deployment", "create-deployment"):
        run_id = f"gitlab-ci-unsupported-{operation}"
        with pytest.raises(FileNotFoundError, match=operation):
            workspace.invoke_tool(
                InvokeToolInput(
                    id=run_id,
                    tool_id="gitlab-ci",
                    operation_id=operation,
                    actor_id="developer",
                    swarm_id="delivery",
                )
            )
        assert not (root / ".agora" / "tool-runs" / run_id).exists()
    assert workspace.validate().ok


def test_discovers_installs_and_governs_the_terraform_cli_adapter(
    project: tuple[Path, AgoraWorkspace], monkeypatch
) -> None:
    root, workspace = project
    monkeypatch.setattr(
        "agora.workspace.shutil.which",
        lambda executable: "/usr/local/bin/terraform" if executable == "terraform" else None,
    )

    available = workspace.list_tool_adapters(available_only=True)
    assert [(item.id, item.implements) for item in available] == [
        ("terraform", "cloud-infrastructure")
    ]

    _prepare_scrum_team(workspace)
    installed = workspace.install_tool_adapter(
        InstallToolAdapterInput(adapter_id="terraform", scope="project")
    )
    assert installed.provider == "hashicorp"
    assert installed.implements == "cloud-infrastructure"
    workspace.add_environment(
        AddEnvironmentInput(
            id="staging",
            name="Staging",
            allowed_tool_capabilities=["cloud.read", "cloud.plan"],
        )
    )

    governed = AgoraWorkspace(cwd=root, now=lambda: TIMESTAMP)
    resources = governed.invoke_tool(
        InvokeToolInput(
            id="terraform-resources",
            tool_id="terraform",
            operation_id="list-resources",
            actor_id="developer",
            swarm_id="delivery",
            environment_id="staging",
            inputs={"environment": "infra/staging"},
        )
    )
    plan = governed.invoke_tool(
        InvokeToolInput(
            id="terraform-plan",
            tool_id="terraform",
            operation_id="plan",
            actor_id="developer",
            swarm_id="delivery",
            environment_id="staging",
            inputs={"environment": "infra/staging", "change": "plans/capacity.tfplan"},
        )
    )

    assert resources.command == ["terraform", "-chdir=infra/staging", "state", "list"]
    assert plan.command == [
        "terraform",
        "-chdir=infra/staging",
        "plan",
        "-input=false",
        "-no-color",
        "-out=plans/capacity.tfplan",
    ]
    with pytest.raises(PermissionError, match="cloud.deploy"):
        governed.invoke_tool(
            InvokeToolInput(
                id="terraform-apply",
                tool_id="terraform",
                operation_id="apply-plan",
                actor_id="developer",
                swarm_id="delivery",
                inputs={
                    "environment": "infra/staging",
                    "plan": "plans/capacity.tfplan",
                },
            )
        )
    with pytest.raises(PermissionError, match="cloud.destroy"):
        governed.invoke_tool(
            InvokeToolInput(
                id="terraform-destroy",
                tool_id="terraform",
                operation_id="destroy-resource",
                actor_id="developer",
                swarm_id="delivery",
                inputs={
                    "environment": "infra/staging",
                    "resource": "aws_instance.api",
                },
            )
        )
    assert governed.validate().ok


def test_installs_and_governs_the_github_issues_cli_adapter(
    project: tuple[Path, AgoraWorkspace], monkeypatch
) -> None:
    root, workspace = project
    monkeypatch.setattr(
        "agora.workspace.shutil.which",
        lambda executable: "/usr/bin/gh" if executable == "gh" else None,
    )
    _prepare_scrum_team(workspace)
    installed = workspace.install_tool_adapter(
        InstallToolAdapterInput(adapter_id="github-issues", scope="project")
    )
    assert installed.implements == "work-management"

    searched = workspace.invoke_tool(
        InvokeToolInput(
            id="github-issue-search",
            tool_id="github-issues",
            operation_id="search",
            actor_id="developer",
            swarm_id="delivery",
            inputs={"query": "repo:openai/codex is:open label:bug"},
        )
    )
    created = workspace.invoke_tool(
        InvokeToolInput(
            id="github-issue-create",
            tool_id="github-issues",
            operation_id="create",
            actor_id="owner",
            swarm_id="delivery",
            inputs={
                "project": "example/agora",
                "type": "Task",
                "title": "Review governed adapter",
                "description": "Verify the CLI-first operation contract.",
            },
        )
    )
    transitioned = workspace.invoke_tool(
        InvokeToolInput(
            id="github-issue-close",
            tool_id="github-issues",
            operation_id="transition",
            actor_id="owner",
            swarm_id="delivery",
            inputs={"issue": "42", "state": "close"},
        )
    )

    assert searched.command[:3] == ["gh", "search", "issues"]
    assert created.command[:5] == [
        "gh",
        "issue",
        "create",
        "--repo",
        "example/agora",
    ]
    assert transitioned.command == ["gh", "issue", "close", "42"]
    with pytest.raises(ValueError, match="state must be one of: close, reopen"):
        workspace.invoke_tool(
            InvokeToolInput(
                id="github-issue-unsafe-transition",
                tool_id="github-issues",
                operation_id="transition",
                actor_id="owner",
                swarm_id="delivery",
                inputs={"issue": "42", "state": "delete"},
            )
        )
    assert not (root / ".agora" / "tool-runs" / "github-issue-unsafe-transition").exists()
    assert workspace.validate().ok


def test_installs_and_governs_the_gitlab_issues_cli_adapter(
    project: tuple[Path, AgoraWorkspace], monkeypatch
) -> None:
    root, workspace = project
    monkeypatch.setattr(
        "agora.workspace.shutil.which",
        lambda executable: "/usr/bin/glab" if executable == "glab" else None,
    )
    _prepare_scrum_team(workspace)
    installed = workspace.install_tool_adapter(
        InstallToolAdapterInput(adapter_id="gitlab-issues", scope="project")
    )
    assert installed.implements_operations == ["search", "view", "comment", "transition"]

    searched = workspace.invoke_tool(
        InvokeToolInput(
            id="gitlab-issue-search",
            tool_id="gitlab-issues",
            operation_id="search",
            actor_id="developer",
            swarm_id="delivery",
            inputs={"query": "governed adapter"},
        )
    )
    viewed = workspace.invoke_tool(
        InvokeToolInput(
            id="gitlab-issue-view",
            tool_id="gitlab-issues",
            operation_id="view",
            actor_id="developer",
            swarm_id="delivery",
            inputs={"issue": "https://gitlab.com/example/agora/-/issues/42"},
        )
    )
    transitioned = workspace.invoke_tool(
        InvokeToolInput(
            id="gitlab-issue-close",
            tool_id="gitlab-issues",
            operation_id="transition",
            actor_id="owner",
            swarm_id="delivery",
            inputs={"issue": "42", "state": "close"},
        )
    )

    assert searched.command == [
        "glab",
        "issue",
        "list",
        "--search",
        "governed adapter",
        "--all",
        "--per-page",
        "50",
        "--output",
        "json",
    ]
    assert viewed.command == [
        "glab",
        "issue",
        "view",
        "https://gitlab.com/example/agora/-/issues/42",
        "--output",
        "json",
    ]
    assert transitioned.command == ["glab", "issue", "close", "42"]
    with pytest.raises(ValueError, match="state must be one of: close, reopen"):
        workspace.invoke_tool(
            InvokeToolInput(
                id="gitlab-issue-unsafe-transition",
                tool_id="gitlab-issues",
                operation_id="transition",
                actor_id="owner",
                swarm_id="delivery",
                inputs={"issue": "42", "state": "delete"},
            )
        )
    with pytest.raises(FileNotFoundError, match="create"):
        workspace.invoke_tool(
            InvokeToolInput(
                id="gitlab-issue-create",
                tool_id="gitlab-issues",
                operation_id="create",
                actor_id="owner",
                swarm_id="delivery",
                inputs={
                    "project": "example/agora",
                    "type": "Task",
                    "title": "Unsafe type mapping",
                    "description": "Create is intentionally absent.",
                },
            )
        )
    assert not (root / ".agora" / "tool-runs" / "gitlab-issue-unsafe-transition").exists()
    assert not (root / ".agora" / "tool-runs" / "gitlab-issue-create").exists()
    assert workspace.validate().ok


def test_installs_and_governs_the_gitlab_merge_request_cli_adapter(
    project: tuple[Path, AgoraWorkspace], monkeypatch
) -> None:
    root, workspace = project
    monkeypatch.setattr(
        "agora.workspace.shutil.which",
        lambda executable: "/usr/bin/glab" if executable == "glab" else None,
    )
    _prepare_scrum_team(workspace)
    installed = workspace.install_tool_adapter(
        InstallToolAdapterInput(adapter_id="gitlab-merge-requests", scope="project")
    )
    assert installed.implements_operations == ["view", "create", "comment", "checks"]

    viewed = workspace.invoke_tool(
        InvokeToolInput(
            id="gitlab-mr-view",
            tool_id="gitlab-merge-requests",
            operation_id="view",
            actor_id="developer",
            swarm_id="delivery",
            inputs={"review": "42"},
        )
    )
    created = workspace.invoke_tool(
        InvokeToolInput(
            id="gitlab-mr-create",
            tool_id="gitlab-merge-requests",
            operation_id="create",
            actor_id="developer",
            swarm_id="delivery",
            inputs={
                "project": "example/agora",
                "base": "main",
                "head": "agora/governed-change",
                "title": "feat: add governed review",
                "description": "Implements the accepted work.",
            },
        )
    )
    commented = workspace.invoke_tool(
        InvokeToolInput(
            id="gitlab-mr-comment",
            tool_id="gitlab-merge-requests",
            operation_id="comment",
            actor_id="developer",
            swarm_id="delivery",
            inputs={"review": "42", "body": "Verification evidence is attached."},
        )
    )
    checks = workspace.invoke_tool(
        InvokeToolInput(
            id="gitlab-mr-checks",
            tool_id="gitlab-merge-requests",
            operation_id="checks",
            actor_id="developer",
            swarm_id="delivery",
            inputs={"review": "42"},
        )
    )

    assert viewed.command == ["glab", "mr", "view", "42", "--output", "json"]
    assert created.command == [
        "glab",
        "mr",
        "create",
        "--repo",
        "example/agora",
        "--target-branch",
        "main",
        "--source-branch",
        "agora/governed-change",
        "--title",
        "feat: add governed review",
        "--description",
        "Implements the accepted work.",
        "--yes",
    ]
    assert commented.command == [
        "glab",
        "mr",
        "note",
        "--message",
        "Verification evidence is attached.",
        "42",
    ]
    assert checks.command == [
        "glab",
        "ci",
        "get",
        "--merge-request",
        "42",
        "--output",
        "json",
    ]
    for operation in ("list", "approve", "request-changes", "merge"):
        run_id = f"gitlab-mr-unsupported-{operation}"
        with pytest.raises(FileNotFoundError, match=operation):
            workspace.invoke_tool(
                InvokeToolInput(
                    id=run_id,
                    tool_id="gitlab-merge-requests",
                    operation_id=operation,
                    actor_id="owner",
                    swarm_id="delivery",
                )
            )
        assert not (root / ".agora" / "tool-runs" / run_id).exists()
    assert workspace.validate().ok


def test_governs_partial_aws_and_gcp_inventory_adapters(
    project: tuple[Path, AgoraWorkspace], monkeypatch
) -> None:
    root, workspace = project
    available_paths = {
        "aws": "/usr/local/bin/aws",
        "gcloud": "/usr/bin/gcloud",
    }
    monkeypatch.setattr(
        "agora.workspace.shutil.which",
        lambda executable: available_paths.get(executable),
    )
    available = workspace.list_tool_adapters(available_only=True)
    assert [(item.id, item.implements_operations) for item in available] == [
        ("aws-resource-inventory", ["inspect-resource", "list-resources"]),
        ("gcp-asset-inventory", ["inspect-resource", "list-resources"]),
    ]

    _prepare_scrum_team(workspace)
    for adapter_id in ("aws-resource-inventory", "gcp-asset-inventory"):
        workspace.install_tool_adapter(
            InstallToolAdapterInput(adapter_id=adapter_id, scope="project")
        )
    workspace.add_environment(
        AddEnvironmentInput(
            id="inventory",
            name="Cloud inventory",
            allowed_tool_capabilities=["cloud.read"],
        )
    )

    aws_resources = workspace.invoke_tool(
        InvokeToolInput(
            id="aws-inventory",
            tool_id="aws-resource-inventory",
            operation_id="list-resources",
            actor_id="developer",
            swarm_id="delivery",
            environment_id="inventory",
            inputs={"environment": "us-east-1"},
        )
    )
    gcp_resource = workspace.invoke_tool(
        InvokeToolInput(
            id="gcp-resource",
            tool_id="gcp-asset-inventory",
            operation_id="inspect-resource",
            actor_id="developer",
            swarm_id="delivery",
            environment_id="inventory",
            inputs={
                "environment": "projects/agora-production",
                "resource": (
                    "//compute.googleapis.com/projects/agora-production/"
                    "zones/us-central1-a/instances/api"
                ),
            },
        )
    )

    assert aws_resources.command[:6] == [
        "aws",
        "resourcegroupstaggingapi",
        "get-resources",
        "--region",
        "us-east-1",
        "--max-items",
    ]
    assert gcp_resource.command[:5] == [
        "gcloud",
        "asset",
        "search-all-resources",
        "--scope=projects/agora-production",
        "--query=name=//compute.googleapis.com/projects/agora-production/zones/us-central1-a/instances/api",
    ]
    for adapter_id in ("aws-resource-inventory", "gcp-asset-inventory"):
        with pytest.raises(FileNotFoundError, match="plan"):
            workspace.invoke_tool(
                InvokeToolInput(
                    id=f"{adapter_id}-unsupported-plan",
                    tool_id=adapter_id,
                    operation_id="plan",
                    actor_id="developer",
                    swarm_id="delivery",
                    inputs={"environment": "production", "change": "change-42"},
                )
            )
    assert workspace.validate().ok


def test_discovers_installs_and_governs_the_jira_acli_adapter(
    project: tuple[Path, AgoraWorkspace], monkeypatch
) -> None:
    root, workspace = project
    monkeypatch.setattr(
        "agora.workspace.shutil.which",
        lambda executable: "/usr/local/bin/acli" if executable == "acli" else None,
    )
    available = workspace.list_tool_adapters(available_only=True)
    assert [(item.id, item.provider) for item in available] == [("jira", "atlassian")]

    _prepare_scrum_team(workspace)
    workspace.install_tool_adapter(InstallToolAdapterInput(adapter_id="jira", scope="project"))
    searched = workspace.invoke_tool(
        InvokeToolInput(
            id="jira-search",
            tool_id="jira",
            operation_id="search",
            actor_id="developer",
            swarm_id="delivery",
            inputs={"query": "project = AGORA AND status != Done"},
        )
    )
    created = workspace.invoke_tool(
        InvokeToolInput(
            id="jira-create",
            tool_id="jira",
            operation_id="create",
            actor_id="owner",
            swarm_id="delivery",
            inputs={
                "project": "AGORA",
                "type": "Task",
                "title": "Review ACLI adapter",
                "description": "Verify the governed Jira command contract.",
            },
        )
    )
    transitioned = workspace.invoke_tool(
        InvokeToolInput(
            id="jira-transition",
            tool_id="jira",
            operation_id="transition",
            actor_id="owner",
            swarm_id="delivery",
            inputs={"issue": "AGORA-42", "state": "In Progress"},
        )
    )

    assert searched.command[:6] == [
        "acli",
        "jira",
        "workitem",
        "search",
        "--jql",
        "project = AGORA AND status != Done",
    ]
    assert created.command[:8] == [
        "acli",
        "jira",
        "workitem",
        "create",
        "--project",
        "AGORA",
        "--type",
        "Task",
    ]
    assert transitioned.command == [
        "acli",
        "jira",
        "workitem",
        "transition",
        "--key",
        "AGORA-42",
        "--status",
        "In Progress",
        "--yes",
        "--json",
    ]
    with pytest.raises(PermissionError, match="issue.write"):
        workspace.invoke_tool(
            InvokeToolInput(
                id="jira-developer-comment",
                tool_id="jira",
                operation_id="comment",
                actor_id="developer",
                swarm_id="delivery",
                inputs={"issue": "AGORA-42", "body": "Unauthorized write"},
            )
        )
    assert not (root / ".agora" / "tool-runs" / "jira-developer-comment").exists()
    assert workspace.validate().ok


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


def test_installs_and_governs_the_twg_confluence_adapter(
    project: tuple[Path, AgoraWorkspace],
) -> None:
    _, workspace = project
    _prepare_scrum_team(workspace)
    workspace.install_tool_adapter(
        InstallToolAdapterInput(adapter_id="twg-confluence", scope="project")
    )

    viewed = workspace.invoke_tool(
        InvokeToolInput(
            id="view-confluence-page",
            tool_id="twg-confluence",
            operation_id="view",
            actor_id="developer",
            swarm_id="delivery",
            inputs={"document": "12345"},
        )
    )
    created = workspace.invoke_tool(
        InvokeToolInput(
            id="create-confluence-draft",
            tool_id="twg-confluence",
            operation_id="create",
            actor_id="developer",
            swarm_id="delivery",
            inputs={
                "space": "131073",
                "parent": "12345",
                "title": "Governed delivery",
                "body": "<p>Reviewed content</p>",
            },
        )
    )
    updated = workspace.invoke_tool(
        InvokeToolInput(
            id="update-confluence-draft",
            tool_id="twg-confluence",
            operation_id="update",
            actor_id="developer",
            swarm_id="delivery",
            inputs={
                "document": "67890",
                "title": "Governed delivery",
                "body": "<p>Updated reviewed content</p>",
                "snapshot-token": "v:3",
            },
        )
    )

    assert viewed.command[:5] == ["twg", "confluence", "content", "get", "12345"]
    assert created.command[:7] == [
        "twg",
        "confluence",
        "content",
        "create",
        "--space-id",
        "131073",
        "--parent-id",
    ]
    assert updated.command[4:8] == ["67890", "--snapshot-token", "v:3", "--title"]
    with pytest.raises(ValueError, match=r"missing=\[snapshot-token\]"):
        workspace.invoke_tool(
            InvokeToolInput(
                id="unsafe-confluence-update",
                tool_id="twg-confluence",
                operation_id="update",
                actor_id="developer",
                swarm_id="delivery",
                inputs={
                    "document": "67890",
                    "title": "Unsafe update",
                    "body": "<p>Missing concurrency token</p>",
                },
            )
        )
    with pytest.raises(FileNotFoundError, match="search"):
        workspace.invoke_tool(
            InvokeToolInput(
                id="unsupported-confluence-search",
                tool_id="twg-confluence",
                operation_id="search",
                actor_id="developer",
                swarm_id="delivery",
                inputs={"space": "131073", "query": "delivery"},
            )
        )
    assert workspace.validate().ok


def test_governs_cloud_infrastructure_capabilities_by_role(
    project: tuple[Path, AgoraWorkspace],
) -> None:
    root, workspace = project
    _prepare_scrum_team(workspace)
    workspace.add_environment(
        AddEnvironmentInput(
            id="staging",
            name="Staging",
            allowed_tool_capabilities=["cloud.read", "cloud.plan"],
        )
    )

    plan = workspace.invoke_tool(
        InvokeToolInput(
            id="plan-cloud-change",
            tool_id="cloud-infrastructure",
            operation_id="plan",
            actor_id="developer",
            swarm_id="delivery",
            environment_id="staging",
            inputs={"environment": "staging", "change": "increase-api-capacity"},
        )
    )
    assert plan.status == "prepared"
    assert plan.capability == "cloud.plan"
    assert plan.command == [
        "cloudctl",
        "change",
        "plan",
        "--environment",
        "staging",
        "--change",
        "increase-api-capacity",
        "--output",
        "json",
    ]

    with pytest.raises(PermissionError, match="cloud.deploy"):
        workspace.invoke_tool(
            InvokeToolInput(
                id="apply-cloud-change",
                tool_id="cloud-infrastructure",
                operation_id="apply-plan",
                actor_id="developer",
                swarm_id="delivery",
                inputs={"plan": "plan-42", "environment": "staging"},
            )
        )
    with pytest.raises(PermissionError, match="cloud.destroy"):
        workspace.invoke_tool(
            InvokeToolInput(
                id="destroy-cloud-resource",
                tool_id="cloud-infrastructure",
                operation_id="destroy-resource",
                actor_id="developer",
                swarm_id="delivery",
                inputs={"resource": "service/api", "environment": "staging"},
            )
        )
    assert not (root / ".agora" / "tool-runs" / "apply-cloud-change").exists()
    assert not (root / ".agora" / "tool-runs" / "destroy-cloud-resource").exists()


def test_enforces_environment_capabilities_role_scope_approvals_and_evidence(
    project: tuple[Path, AgoraWorkspace],
) -> None:
    root, workspace = project
    _prepare_scrum_team(workspace)
    workspace.create_work(
        CreateWorkInput(
            swarm_id="delivery",
            id="release",
            title="Release a reviewed change",
            actor_id="owner",
        )
    )
    workspace.add_environment(
        AddEnvironmentInput(
            id="production",
            name="Production",
            allowed_tool_capabilities=["cloud.plan"],
            required_approval_roles=["product-owner"],
            require_successful_evidence=True,
        )
    )
    invocation = InvokeToolInput(
        id="production-plan",
        tool_id="cloud-infrastructure",
        operation_id="plan",
        actor_id="developer",
        swarm_id="delivery",
        work_id="release",
        environment_id="production",
        inputs={"environment": "provider-production", "change": "release-v1"},
    )

    with pytest.raises(PermissionError, match="requires approval from: product-owner"):
        workspace.invoke_tool(invocation)
    workspace.add_approval(
        AddApprovalInput(
            swarm_id="delivery",
            work_id="release",
            actor_id="owner",
            role_id="product-owner",
        )
    )
    with pytest.raises(PermissionError, match="requires successful work evidence"):
        workspace.invoke_tool(invocation)
    workspace.add_artifact(
        AddArtifactInput(
            swarm_id="delivery",
            work_id="release",
            actor_id="developer",
            kind="test-report",
            uri="ci://builds/release/tests",
        )
    )
    workspace.add_evidence(
        AddEvidenceInput(
            swarm_id="delivery",
            work_id="release",
            actor_id="facilitator",
            type="test-run",
            result="success",
            artifact_refs=["ci://builds/release/tests"],
        )
    )
    prepared = workspace.invoke_tool(invocation)
    assert prepared.environment_id == "production"
    assert 'environment: "production"' in (Path(prepared.path) / "RUN.md").read_text()

    role_path = root / ".agora" / "methods" / "scrum" / "roles" / "developer.md"
    role_path.write_text(
        role_path.read_text().replace(
            'allowed-environments: ["*"]', 'allowed-environments: ["staging"]'
        )
    )
    with pytest.raises(PermissionError, match="Actor roles do not allow"):
        workspace.invoke_tool(
            InvokeToolInput(**{**invocation.__dict__, "id": "role-denied-production-plan"})
        )
    report = workspace.validate()
    assert not report.ok
    assert {"role.environment-missing", "tool-run.environment-policy"}.issubset(
        {issue.code for issue in report.issues}
    )


def test_rejects_missing_or_insufficient_environment_policy(
    project: tuple[Path, AgoraWorkspace],
) -> None:
    _, workspace = project
    _prepare_scrum_team(workspace)
    with pytest.raises(ValueError, match="at least one tool capability"):
        workspace.add_environment(
            AddEnvironmentInput(id="empty", name="Empty", allowed_tool_capabilities=[])
        )
    with pytest.raises(ValueError, match="requires a governed environment"):
        workspace.invoke_tool(
            InvokeToolInput(
                id="unscoped-plan",
                tool_id="cloud-infrastructure",
                operation_id="plan",
                actor_id="developer",
                swarm_id="delivery",
                inputs={"environment": "provider-sandbox", "change": "test"},
            )
        )
    workspace.add_environment(
        AddEnvironmentInput(
            id="sandbox",
            name="Sandbox",
            allowed_tool_capabilities=["cloud.read"],
        )
    )
    with pytest.raises(PermissionError, match="does not allow tool capability cloud.plan"):
        workspace.invoke_tool(
            InvokeToolInput(
                id="capability-denied-plan",
                tool_id="cloud-infrastructure",
                operation_id="plan",
                actor_id="developer",
                swarm_id="delivery",
                environment_id="sandbox",
                inputs={"environment": "provider-sandbox", "change": "test"},
            )
        )


def test_governs_observability_and_incident_capabilities_by_role(
    project: tuple[Path, AgoraWorkspace],
) -> None:
    root, workspace = project
    _prepare_scrum_team(workspace)
    workspace.add_environment(
        AddEnvironmentInput(
            id="production",
            name="Production",
            allowed_tool_capabilities=["observability.read"],
        )
    )

    health = workspace.invoke_tool(
        InvokeToolInput(
            id="inspect-service-health",
            tool_id="observability",
            operation_id="service-health",
            actor_id="developer",
            swarm_id="delivery",
            environment_id="production",
            inputs={"service": "api", "environment": "production"},
        )
    )
    assert health.status == "prepared"
    assert health.capability == "observability.read"

    incident = workspace.invoke_tool(
        InvokeToolInput(
            id="create-service-incident",
            tool_id="observability",
            operation_id="create-incident",
            actor_id="facilitator",
            swarm_id="delivery",
            inputs={
                "service": "api",
                "severity": "high",
                "title": "API errors",
                "summary": "Error rate exceeded the reviewed threshold.",
            },
        )
    )
    assert incident.capability == "incident.write"

    with pytest.raises(PermissionError, match="incident.resolve"):
        workspace.invoke_tool(
            InvokeToolInput(
                id="resolve-service-incident",
                tool_id="observability",
                operation_id="resolve-incident",
                actor_id="developer",
                swarm_id="delivery",
                inputs={"incident": "INC-42", "resolution": "Service recovered"},
            )
        )
    assert not (root / ".agora" / "tool-runs" / "resolve-service-incident").exists()


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

    with pytest.raises(ValueError, match="must also be required artifacts"):
        workspace.create_delegation(
            CreateDelegationInput(
                id="invalid-promotion",
                parent_swarm_id="delivery",
                parent_work_id="parent-slice",
                child_actor_id="specialist-swarm",
                child_work_id="invalid-promotion-child",
                actor_id="specialist-swarm",
                title="Promote an optional artifact",
                artifact_promotions={"release-note": "specialist-result"},
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
            artifact_promotions={"child-result": "specialist-result"},
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
    assert parent.artifact_kinds == ["delegated-result", "specialist-result"]
    assert parent.evidence_results == ["success"]
    parent_root = root / ".agora" / "swarms" / "delivery" / "work" / "parent-slice"
    assert (
        "agora://swarms/specialists/work/child-slice" in (parent_root / "artifacts.md").read_text()
    )
    assert (
        "agora://swarms/specialists/work/child-slice/artifacts/child-result"
        in (parent_root / "artifacts.md").read_text()
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
        "methods": 3,
        "tools": 11,
        "environments": 0,
        "swarms": 1,
        "work": 1,
        "delegations": 0,
        "sessions": 1,
        "tool-runs": 1,
        "usage": 0,
    }
    assert status.swarm_statuses == {"ready": 1}
    assert status.work_states == {"specified": 1}
    assert status.attention["active-work"] == ["delivery/observable-work"]
    assert status.attention["unfinished-sessions"] == ["observable-session"]
    assert [item.id for item in workspace.list_methods()] == [
        "kanban",
        "scrum",
        "spec-driven",
    ]
    assert [item.id for item in workspace.list_tools()] == [
        "ci-cd",
        "cloud-infrastructure",
        "code-review",
        "knowledge-base",
        "observability",
        "portfolio-management",
        "release-management",
        "repository",
        "repository-governance",
        "security-scanning",
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


def test_decomposes_work_and_requires_children_to_close(
    project: tuple[Path, AgoraWorkspace],
) -> None:
    root, workspace = project
    _prepare_scrum_team(workspace)
    workspace.create_work(
        CreateWorkInput(
            swarm_id="delivery",
            id="parent-work",
            title="Deliver the parent outcome",
            actor_id="owner",
        )
    )
    decomposition = DecomposeWorkInput(
        swarm_id="delivery",
        parent_work_id="parent-work",
        child_work_id="child-work",
        title="Implement the child slice",
        actor_id="owner",
        acceptance_criteria=[("reviewed", "The child slice is reviewed")],
        required_artifacts=["source-code"],
    )

    with pytest.raises(PermissionError, match="not allowed to perform work.decompose"):
        workspace.decompose_work(
            DecomposeWorkInput(**{**decomposition.__dict__, "actor_id": "developer"})
        )
    with pytest.raises(ValueError, match="must differ"):
        workspace.decompose_work(
            DecomposeWorkInput(
                **{
                    **decomposition.__dict__,
                    "child_work_id": "parent-work",
                }
            )
        )

    child = workspace.decompose_work(decomposition)
    parent = workspace.show_work("delivery", "parent-work")

    assert child.parent_work_ref == "delivery/parent-work"
    assert parent.child_work_refs == ["delivery/child-work"]
    assert (
        'parent-work: "delivery/parent-work"'
        in (root / ".agora" / "swarms" / "delivery" / "work" / "child-work" / "WORK.md").read_text()
    )
    with pytest.raises(FileExistsError, match="Work already exists"):
        workspace.decompose_work(decomposition)

    for state, actor in (
        ("planned", "developer"),
        ("implementing", "developer"),
        ("reviewing", "developer"),
        ("verifying", "facilitator"),
    ):
        workspace.transition_work(
            TransitionWorkInput(
                swarm_id="delivery",
                work_id="parent-work",
                actor_id=actor,
                target_state=state,
            )
        )
    with pytest.raises(ValueError, match="has open child work"):
        workspace.transition_work(
            TransitionWorkInput(
                swarm_id="delivery",
                work_id="parent-work",
                actor_id="owner",
                target_state="completed",
            )
        )
    with pytest.raises(ValueError, match="has open child work"):
        workspace.cancel_work(
            ChangeWorkStatusInput(
                swarm_id="delivery",
                work_id="parent-work",
                actor_id="owner",
                reason="Cancel the parent",
            )
        )

    workspace.cancel_work(
        ChangeWorkStatusInput(
            swarm_id="delivery",
            work_id="child-work",
            actor_id="owner",
            reason="The child is no longer required",
        )
    )
    workspace.add_artifact(
        AddArtifactInput(
            swarm_id="delivery",
            work_id="parent-work",
            actor_id="developer",
            kind="review-record",
            uri="agora://swarms/delivery/work/child-work/review",
        )
    )
    workspace.add_evidence(
        AddEvidenceInput(
            swarm_id="delivery",
            work_id="parent-work",
            actor_id="facilitator",
            type="review",
            result="success",
            artifact_refs=["agora://swarms/delivery/work/child-work/review"],
        )
    )
    workspace.add_approval(
        AddApprovalInput(
            swarm_id="delivery",
            work_id="parent-work",
            actor_id="owner",
            role_id="product-owner",
            note="Child closure reviewed",
        )
    )
    completed = workspace.transition_work(
        TransitionWorkInput(
            swarm_id="delivery",
            work_id="parent-work",
            actor_id="owner",
            target_state="completed",
        )
    )

    assert completed.state == "completed"


def test_verifies_local_artifacts_and_binds_successful_evidence(
    project: tuple[Path, AgoraWorkspace],
) -> None:
    root, workspace = project
    _prepare_scrum_team(workspace)
    workspace.create_work(
        CreateWorkInput(
            swarm_id="delivery",
            id="verified-feature",
            title="Verify repository evidence",
            actor_id="owner",
        )
    )

    with pytest.raises(FileNotFoundError, match="Repository artifact does not exist"):
        workspace.add_artifact(
            AddArtifactInput(
                swarm_id="delivery",
                work_id="verified-feature",
                actor_id="developer",
                kind="source-code",
                uri="repo://src/missing.py",
            )
        )

    artifact = root / "src" / "feature.py"
    artifact.write_text("FEATURE = True\n", encoding="utf-8")
    workspace.add_artifact(
        AddArtifactInput(
            swarm_id="delivery",
            work_id="verified-feature",
            actor_id="developer",
            kind="source-code",
            uri="repo://src/feature.py",
        )
    )
    with pytest.raises(ValueError, match="requires at least one artifact"):
        workspace.add_evidence(
            AddEvidenceInput(
                swarm_id="delivery",
                work_id="verified-feature",
                actor_id="facilitator",
                type="test-run",
                result="success",
            )
        )
    with pytest.raises(ValueError, match="unregistered work artifacts"):
        workspace.add_evidence(
            AddEvidenceInput(
                swarm_id="delivery",
                work_id="verified-feature",
                actor_id="facilitator",
                type="test-run",
                result="success",
                artifact_refs=["ci://builds/unregistered/tests"],
            )
        )
    workspace.add_evidence(
        AddEvidenceInput(
            swarm_id="delivery",
            work_id="verified-feature",
            actor_id="facilitator",
            type="test-run",
            result="success",
            artifact_refs=["repo://src/feature.py"],
        )
    )
    assert workspace.validate().ok is True

    artifact.unlink()
    report = workspace.validate()
    assert report.ok is False
    assert any(issue.code == "artifact.reference-invalid" for issue in report.issues)


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


def test_propagates_and_enforces_delegation_budgets(
    project: tuple[Path, AgoraWorkspace],
) -> None:
    _, workspace = project
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
            id="leaf-developer",
            name="Leaf Developer",
            kind="ai-agent",
            capabilities=["implementation"],
            scope="project",
        ),
    ):
        workspace.add_actor(actor)

    def form_swarm(swarm_id: str, developer: str) -> None:
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
            ("developer", developer),
        ):
            workspace.assign_actor(
                AssignActorInput(swarm_id=swarm_id, role_id=role, actor_id=actor_id)
            )

    form_swarm("leaf", "leaf-developer")
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
    form_swarm("middle", "leaf-swarm")
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
    form_swarm("root", "middle-swarm")
    workspace.create_work(
        CreateWorkInput(
            swarm_id="root",
            id="root-work",
            title="Fund bounded delegated work",
            actor_id="owner",
        )
    )
    root_delegation = workspace.create_delegation(
        CreateDelegationInput(
            id="root-to-middle",
            parent_swarm_id="root",
            parent_work_id="root-work",
            child_actor_id="middle-swarm",
            child_work_id="middle-work",
            actor_id="middle-swarm",
            title="Deliver within a bounded allocation",
            budget_limits={"effort": 10, "tokens": 100},
        )
    )
    workspace.accept_delegation(
        DelegationActorInput(delegation_id=root_delegation.id, actor_id="owner")
    )

    middle_work = workspace.show_work("middle", "middle-work")
    assert middle_work.budget_limits == {"effort": 10, "tokens": 100}

    first = workspace.create_delegation(
        CreateDelegationInput(
            id="middle-to-leaf-one",
            parent_swarm_id="middle",
            parent_work_id="middle-work",
            child_actor_id="leaf-swarm",
            child_work_id="leaf-work-one",
            actor_id="leaf-swarm",
            title="Use the first allocation",
            budget_limits={"effort": 6, "tokens": 80},
        )
    )
    with pytest.raises(ValueError, match="exceeds parent work allocation"):
        workspace.create_delegation(
            CreateDelegationInput(
                id="middle-to-leaf-two",
                parent_swarm_id="middle",
                parent_work_id="middle-work",
                child_actor_id="leaf-swarm",
                child_work_id="leaf-work-two",
                actor_id="leaf-swarm",
                title="Exceed the remaining allocation",
                budget_limits={"effort": 5, "tokens": 20},
            )
        )
    with pytest.raises(ValueError, match="not available from parent work"):
        workspace.create_delegation(
            CreateDelegationInput(
                id="middle-to-leaf-cost",
                parent_swarm_id="middle",
                parent_work_id="middle-work",
                child_actor_id="leaf-swarm",
                child_work_id="leaf-work-cost",
                actor_id="leaf-swarm",
                title="Invent an unavailable dimension",
                budget_limits={"cost-cents": 1},
            )
        )
    with pytest.raises(ValueError, match="cannot be negative"):
        workspace.create_delegation(
            CreateDelegationInput(
                id="middle-to-leaf-negative",
                parent_swarm_id="middle",
                parent_work_id="middle-work",
                child_actor_id="leaf-swarm",
                child_work_id="leaf-work-negative",
                actor_id="leaf-swarm",
                title="Reject a negative allocation",
                budget_limits={"effort": -1},
            )
        )

    workspace.reject_delegation(
        ChangeDelegationStatusInput(
            delegation_id=first.id,
            actor_id="owner",
            reason="The leaf rejects this allocation",
        )
    )
    second = workspace.create_delegation(
        CreateDelegationInput(
            id="middle-to-leaf-two",
            parent_swarm_id="middle",
            parent_work_id="middle-work",
            child_actor_id="leaf-swarm",
            child_work_id="leaf-work-two",
            actor_id="leaf-swarm",
            title="Use the released allocation",
            budget_limits={"effort": 10, "tokens": 100},
        )
    )
    workspace.accept_delegation(DelegationActorInput(delegation_id=second.id, actor_id="owner"))

    assert workspace.show_work("leaf", "leaf-work-two").budget_limits == {
        "effort": 10,
        "tokens": 100,
    }
    assert workspace.validate().ok
