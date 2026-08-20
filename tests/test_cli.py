import io
import json
from pathlib import Path

import pytest

from agora import __version__
from agora.cli import main
from agora.model import (
    AddActorInput,
    AssignActorInput,
    ChangeWorkStatusInput,
    CreateSwarmInput,
    CreateWorkInput,
    InitInput,
    ToolRuntimeProbe,
)
from agora.workspace import AgoraWorkspace


def test_cli_reports_package_version(capsys) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])

    assert exit_info.value.code == 0
    assert capsys.readouterr().out == f"agora {__version__}\n"


def test_cli_init_defaults_to_spec_driven(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    output = io.StringIO()
    errors = io.StringIO()

    assert main(["init"], cwd=tmp_path, stdout=output, stderr=errors) == 0

    assert errors.getvalue() == ""
    assert '"default_method": "spec-driven"' in output.getvalue()


def test_lists_activity_from_the_cli(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    output = io.StringIO()
    errors = io.StringIO()

    assert main(["init"], cwd=tmp_path, stdout=output, stderr=errors) == 0
    output.seek(0)
    output.truncate(0)
    assert (
        main(
            ["activity", "list", "--type", "project.initialized", "--limit", "1"],
            cwd=tmp_path,
            stdout=output,
            stderr=errors,
        )
        == 0
    )

    payload = json.loads(output.getvalue())
    assert payload[0]["type"] == "project.initialized"
    assert payload[0]["source"] == "repo://.agora/project.md"
    assert errors.getvalue() == ""

    output.seek(0)
    output.truncate(0)
    assert main(["activity", "rebuild"], cwd=tmp_path, stdout=output, stderr=errors) == 0
    assert json.loads(output.getvalue())["rebuilt"] == 1


def test_targets_a_project_outside_the_current_environment(tmp_path: Path, monkeypatch) -> None:
    project = tmp_path / "project"
    home = tmp_path / "home"
    project.mkdir()
    monkeypatch.setenv("AGORA_HOME", str(home))
    output = io.StringIO()
    errors = io.StringIO()

    assert (
        main(
            ["init", "--path", str(project), "--integration", "claude"],
            stdout=output,
            stderr=errors,
        )
        == 0
    )
    assert (
        main(
            [
                "actor",
                "add",
                "--project",
                str(project),
                "--id",
                "ada",
                "--name",
                "Ada",
                "--kind",
                "ai-agent",
                "--capability",
                "implementation",
            ],
            stdout=output,
            stderr=errors,
        )
        == 0
    )

    assert errors.getvalue() == ""
    assert '"integration": "claude"' in output.getvalue()
    assert '"reference": "project:ada"' in output.getvalue()


def test_manages_environment_policies_from_the_cli(tmp_path: Path, monkeypatch) -> None:
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    output = io.StringIO()
    errors = io.StringIO()

    assert main(["init"], cwd=project, stdout=output, stderr=errors) == 0
    assert (
        main(
            [
                "environment",
                "add",
                "--id",
                "production",
                "--name",
                "Production",
                "--capability",
                "deployment.create",
                "--required-approval-role",
                "product-owner",
                "--require-successful-evidence",
            ],
            cwd=project,
            stdout=output,
            stderr=errors,
        )
        == 0
    )
    assert (
        main(
            ["environment", "show", "--id", "production"],
            cwd=project,
            stdout=output,
            stderr=errors,
        )
        == 0
    )
    assert main(["environment", "list"], cwd=project, stdout=output, stderr=errors) == 0

    assert errors.getvalue() == ""
    assert '"id": "production"' in output.getvalue()
    assert '"require_successful_evidence": true' in output.getvalue()
    assert (project / ".agora" / "environments" / "production.md").is_file()


def test_installs_a_custom_method_without_an_initialized_project(
    tmp_path: Path, monkeypatch
) -> None:
    home = tmp_path / "home"
    source = Path(__file__).parents[1] / "samples" / "custom-lifecycle" / "release-flow"
    monkeypatch.setenv("AGORA_HOME", str(home))
    output = io.StringIO()
    errors = io.StringIO()

    assert (
        main(
            ["method", "install", "--source", str(source), "--scope", "user"],
            stdout=output,
            stderr=errors,
        )
        == 0
    )

    assert errors.getvalue() == ""
    assert '"id": "release-flow"' in output.getvalue()
    assert (home / "methods" / "release-flow" / "METHOD.md").exists()


def test_discovers_and_installs_a_cli_adapter_from_the_cli(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("AGORA_HOME", str(home))
    monkeypatch.setattr(
        "agora.workspace.shutil.which",
        lambda executable: "/usr/bin/gh" if executable == "gh" else None,
    )
    output = io.StringIO()
    errors = io.StringIO()

    assert (
        main(
            ["tool", "adapter", "list", "--available"],
            cwd=tmp_path,
            stdout=output,
            stderr=errors,
        )
        == 0
    )
    assert (
        main(
            ["tool", "adapter", "install", "--id", "github-actions", "--scope", "user"],
            cwd=tmp_path,
            stdout=output,
            stderr=errors,
        )
        == 0
    )

    assert errors.getvalue() == ""
    assert '"transport": "cli"' in output.getvalue()
    assert '"runtime_available": true' in output.getvalue()
    assert (home / "tools" / "github-actions" / "TOOL.md").is_file()


def test_tool_sync_dispatches_an_explicit_read_only_launch(tmp_path: Path, monkeypatch) -> None:
    captured = []

    def invoke_tool(workspace, data):
        captured.append(data)
        return None

    monkeypatch.setattr("agora.cli.AgoraWorkspace.invoke_tool", invoke_tool)

    assert (
        main(
            [
                "tool",
                "sync",
                "--id",
                "github-snapshot",
                "--tool",
                "github-security",
                "--operation",
                "list-code-alerts",
                "--actor",
                "developer",
                "--swarm",
                "delivery",
                "--input",
                "project=example/agora",
            ],
            cwd=tmp_path,
        )
        == 0
    )
    assert len(captured) == 1
    assert captured[0].launch is True
    assert captured[0].read_only_sync is True
    assert captured[0].inputs == {"project": "example/agora"}


def test_shows_captured_tool_result_from_the_cli(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "agora.cli.AgoraWorkspace.show_tool_run",
        lambda workspace, run_id: {
            "run": run_id,
            "status": "completed",
            "stdout": '{"items": [{"key": "AGORA-42"}]}',
        },
    )
    output = io.StringIO()
    errors = io.StringIO()

    assert (
        main(
            ["tool", "result", "--run", "jira-search"],
            cwd=tmp_path,
            stdout=output,
            stderr=errors,
        )
        == 0
    )

    payload = json.loads(output.getvalue())
    assert payload["run"] == "jira-search"
    assert "AGORA-42" in payload["stdout"]
    assert errors.getvalue() == ""


def test_reports_tool_credential_resolution_without_a_secret_value(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        "agora.cli.AgoraWorkspace.resolve_tool_credentials",
        lambda workspace, tool_id: {
            "tool_id": tool_id,
            "resolved_source": "env",
            "checks": [{"source": "env", "satisfied": True, "detail": "AGORA_JIRA_TOKEN is set"}],
        },
    )
    output = io.StringIO()
    errors = io.StringIO()

    assert (
        main(
            ["tool", "credentials", "--tool", "jira"],
            cwd=tmp_path,
            stdout=output,
            stderr=errors,
        )
        == 0
    )

    payload = json.loads(output.getvalue())
    assert payload["tool_id"] == "jira"
    assert payload["resolved_source"] == "env"
    assert errors.getvalue() == ""


def test_filters_cli_adapters_by_checked_runtime_compatibility(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(
        "agora.workspace.shutil.which",
        lambda executable: f"/usr/bin/{executable}" if executable in {"gh", "terraform"} else None,
    )

    def probe(contract, executable_path):
        compatible = contract.executable == "gh" and executable_path is not None
        return ToolRuntimeProbe(
            available=executable_path is not None,
            executable_path=executable_path,
            version="2.82.1" if compatible else "0.14.0" if executable_path else None,
            compatible=compatible,
            detail="test compatibility result",
        )

    monkeypatch.setattr("agora.workspace.probe_tool_runtime", probe)
    output = io.StringIO()
    errors = io.StringIO()

    assert (
        main(
            ["tool", "adapter", "list", "--compatible"],
            cwd=tmp_path,
            stdout=output,
            stderr=errors,
        )
        == 0
    )

    assert errors.getvalue() == ""
    assert output.getvalue().count('"runtime_compatible": true') == 7
    assert '"id": "github-actions"' in output.getvalue()
    assert '"id": "github-issues"' in output.getvalue()
    assert '"id": "github-projects"' in output.getvalue()
    assert '"id": "terraform"' not in output.getvalue()


def test_configures_actor_runtime_and_prepares_a_session_from_the_cli(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    workspace = AgoraWorkspace(cwd=root)
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
    workspace.add_actor(
        AddActorInput(
            id="replacement",
            name="Replacement Developer",
            kind="swarm",
            capabilities=["implementation"],
            scope="project",
        )
    )
    workspace.create_swarm(
        CreateSwarmInput(id="delivery", objective="Deliver work", create_branch=False)
    )
    for role, actor_id in (
        ("product-owner", "owner"),
        ("scrum-master", "facilitator"),
        ("developer", "developer"),
    ):
        workspace.assign_actor(
            AssignActorInput(swarm_id="delivery", role_id=role, actor_id=actor_id)
        )

    output = io.StringIO()
    errors = io.StringIO()
    assert (
        main(
            [
                "actor",
                "add",
                "--id",
                "delivery-link",
                "--name",
                "Delivery Link",
                "--kind",
                "swarm",
                "--capability",
                "implementation",
                "--represented-swarm",
                "delivery",
            ],
            cwd=root,
            stdout=output,
            stderr=errors,
        )
        == 0
    )
    assert (
        main(
            [
                "actor",
                "runtime",
                "--actor",
                "facilitator",
                "--provider",
                "runtime-provider",
                "--model",
                "runtime-model",
            ],
            cwd=root,
            stdout=output,
            stderr=errors,
        )
        == 0
    )
    assert (
        main(
            [
                "swarm",
                "handoff",
                "--id",
                "cli-handoff",
                "--swarm",
                "delivery",
                "--role",
                "developer",
                "--from",
                "developer",
                "--to",
                "replacement",
                "--by",
                "facilitator",
                "--reason",
                "Move delivery to a composite team",
            ],
            cwd=root,
            stdout=output,
            stderr=errors,
        )
        == 0
    )
    assert (
        main(
            [
                "start",
                "--id",
                "review-session",
                "--actor",
                "facilitator",
                "--swarm",
                "delivery",
                "--runner",
                "/bin/true",
            ],
            cwd=root,
            stdout=output,
            stderr=errors,
        )
        == 0
    )
    assert (
        main(
            [
                "tool",
                "invoke",
                "--id",
                "cli-status",
                "--tool",
                "repository",
                "--operation",
                "status",
                "--actor",
                "facilitator",
                "--swarm",
                "delivery",
            ],
            cwd=root,
            stdout=output,
            stderr=errors,
        )
        == 0
    )

    assert errors.getvalue() == ""
    assert '"model": "runtime-model"' in output.getvalue()
    assert '"status": "prepared"' in output.getvalue()
    assert '"tool_id": "repository"' in output.getvalue()
    assert '"to_actor": "project:replacement"' in output.getvalue()
    assert '"represented_swarm": "delivery"' in output.getvalue()


def test_proposes_accepts_and_shows_a_delegation_from_the_cli(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    workspace = AgoraWorkspace(cwd=root)
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

    form_swarm("specialists", "specialist")
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
    form_swarm("delivery", "specialist-swarm")
    workspace.create_work(
        CreateWorkInput(
            swarm_id="delivery",
            id="parent-work",
            title="Integrate specialist work",
            actor_id="owner",
        )
    )

    output = io.StringIO()
    errors = io.StringIO()
    assert (
        main(
            [
                "delegation",
                "create",
                "--id",
                "cli-delegation",
                "--swarm",
                "delivery",
                "--work",
                "parent-work",
                "--to-actor",
                "specialist-swarm",
                "--child-work",
                "specialist-work",
                "--title",
                "Produce specialist work",
                "--criterion",
                "usable:The result is usable",
                "--required-artifact",
                "specialist-result",
                "--budget",
                "effort=8",
                "--promote-artifact",
                "specialist-result=promoted-specialist-result",
                "--by",
                "specialist-swarm",
            ],
            cwd=root,
            stdout=output,
            stderr=errors,
        )
        == 0
    )
    assert (
        main(
            [
                "delegation",
                "accept",
                "--delegation",
                "cli-delegation",
                "--by",
                "owner",
            ],
            cwd=root,
            stdout=output,
            stderr=errors,
        )
        == 0
    )
    assert (
        main(
            [
                "delegation",
                "block",
                "--delegation",
                "cli-delegation",
                "--by",
                "facilitator",
                "--reason",
                "Pause for contract clarification",
                "--id",
                "cli-delegation-blocked",
            ],
            cwd=root,
            stdout=output,
            stderr=errors,
        )
        == 0
    )
    assert (
        main(
            [
                "delegation",
                "resume",
                "--delegation",
                "cli-delegation",
                "--by",
                "facilitator",
                "--reason",
                "The contract is clear",
                "--id",
                "cli-delegation-resumed",
            ],
            cwd=root,
            stdout=output,
            stderr=errors,
        )
        == 0
    )
    assert (
        main(
            ["delegation", "status-changes", "--delegation", "cli-delegation"],
            cwd=root,
            stdout=output,
            stderr=errors,
        )
        == 0
    )
    assert (
        main(
            ["delegation", "show", "--delegation", "cli-delegation"],
            cwd=root,
            stdout=output,
            stderr=errors,
        )
        == 0
    )

    assert errors.getvalue() == ""
    assert '"status": "proposed"' in output.getvalue()
    assert output.getvalue().count('"status": "accepted"') >= 2
    assert '"action": "delegation.block"' in output.getvalue()
    assert '"action": "delegation.resume"' in output.getvalue()
    assert workspace.show_work("specialists", "specialist-work").budget_limits == {"effort": 8}
    assert workspace.show_delegation("cli-delegation").artifact_promotions == {
        "specialist-result": "promoted-specialist-result"
    }
    assert (
        root / ".agora" / "swarms" / "specialists" / "work" / "specialist-work" / "WORK.md"
    ).exists()


def test_blocks_resumes_and_lists_work_status_from_the_cli(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    workspace = AgoraWorkspace(cwd=root)
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
        CreateSwarmInput(id="delivery", objective="Deliver work", create_branch=False)
    )
    for role, actor in (
        ("product-owner", "owner"),
        ("scrum-master", "facilitator"),
        ("developer", "developer"),
    ):
        workspace.assign_actor(AssignActorInput(swarm_id="delivery", role_id=role, actor_id=actor))
    workspace.create_work(
        CreateWorkInput(
            swarm_id="delivery",
            id="cli-work",
            title="Exercise work controls",
            actor_id="owner",
        )
    )
    output = io.StringIO()
    errors = io.StringIO()

    assert (
        main(
            [
                "work",
                "decompose",
                "--swarm",
                "delivery",
                "--work",
                "cli-work",
                "--child",
                "cli-child",
                "--title",
                "Implement the child slice",
                "--criterion",
                "reviewed:The slice is reviewed",
                "--required-artifact",
                "source-code",
                "--by",
                "owner",
            ],
            cwd=root,
            stdout=output,
            stderr=errors,
        )
        == 0
    )

    for arguments in (
        [
            "work",
            "block",
            "--swarm",
            "delivery",
            "--work",
            "cli-work",
            "--by",
            "developer",
            "--reason",
            "Wait for input",
            "--id",
            "cli-work-blocked",
        ],
        [
            "work",
            "list",
            "--swarm",
            "delivery",
            "--operational-status",
            "blocked",
        ],
        [
            "work",
            "resume",
            "--swarm",
            "delivery",
            "--work",
            "cli-work",
            "--by",
            "facilitator",
            "--reason",
            "Input received",
            "--id",
            "cli-work-resumed",
        ],
        ["work", "status-changes", "--swarm", "delivery", "--work", "cli-work"],
    ):
        assert main(arguments, cwd=root, stdout=output, stderr=errors) == 0

    assert errors.getvalue() == ""
    assert workspace.show_work("delivery", "cli-child").parent_work_ref == "delivery/cli-work"
    assert '"operational_status": "blocked"' in output.getvalue()
    assert '"action": "work.resume"' in output.getvalue()


def test_queries_status_and_returns_a_failure_code_for_invalid_state(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    AgoraWorkspace(cwd=root).initialize(InitInput(integration="generic"))
    output = io.StringIO()
    errors = io.StringIO()

    assert main(["status"], cwd=root, stdout=output, stderr=errors) == 0
    assert main(["actor", "list"], cwd=root, stdout=output, stderr=errors) == 0
    assert main(["method", "list"], cwd=root, stdout=output, stderr=errors) == 0
    assert main(["validate"], cwd=root, stdout=output, stderr=errors) == 0
    assert '"project": "project"' in output.getvalue()
    assert '"methods": 3' in output.getvalue()
    assert '"ok": true' in output.getvalue()

    constitution = root / ".agora" / "constitution.md"
    constitution.write_text(
        constitution.read_text().replace(
            'schema: "agora/constitution/v1"', 'schema: "invalid/schema"'
        )
    )
    invalid_output = io.StringIO()
    assert main(["validate"], cwd=root, stdout=invalid_output, stderr=errors) == 1
    assert '"ok": false' in invalid_output.getvalue()
    assert '"code": "document.invalid"' in invalid_output.getvalue()
    assert errors.getvalue() == ""


def test_creates_and_lists_a_granular_gate_waiver_from_the_cli(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    workspace = AgoraWorkspace(cwd=root)
    workspace.initialize(InitInput(integration="generic", default_method="scrum"))
    for actor_id, name, capabilities in (
        ("owner", "Owner", ["backlog-management", "acceptance"]),
        ("alternate-owner", "Alternate Owner", ["backlog-management", "acceptance"]),
        ("facilitator", "Facilitator", ["facilitation", "governance"]),
        ("developer", "Developer", ["implementation"]),
    ):
        workspace.add_actor(
            AddActorInput(
                id=actor_id,
                name=name,
                kind="human",
                capabilities=capabilities,
                scope="project",
            )
        )
    workspace.create_swarm(
        CreateSwarmInput(id="delivery", objective="Test Gate Waivers", create_branch=False)
    )
    for role, actor_id in (
        ("product-owner", "owner"),
        ("scrum-master", "facilitator"),
        ("developer", "developer"),
    ):
        workspace.assign_actor(
            AssignActorInput(swarm_id="delivery", role_id=role, actor_id=actor_id)
        )
    workspace.create_work(
        CreateWorkInput(
            swarm_id="delivery",
            id="release",
            title="Release",
            actor_id="owner",
            acceptance_criteria=[("verified", "Verify the release")],
        )
    )
    output = io.StringIO()
    errors = io.StringIO()

    assert (
        main(
            [
                "gate",
                "waive",
                "--id",
                "accepted-risk",
                "--swarm",
                "delivery",
                "--work",
                "release",
                "--gate",
                "completion",
                "--by",
                "owner",
                "--criterion",
                "verified",
                "--reason",
                "Risk accepted",
                "--evidence",
                "repo://risk/release.md",
            ],
            cwd=root,
            stdout=output,
            stderr=errors,
        )
        == 0
    )
    assert (
        main(
            ["gate", "list", "--swarm", "delivery", "--work", "release"],
            cwd=root,
            stdout=output,
            stderr=errors,
        )
        == 0
    )
    assert (
        main(
            [
                "approval",
                "delegate",
                "--id",
                "alternate-release-approval",
                "--swarm",
                "delivery",
                "--work",
                "release",
                "--role",
                "product-owner",
                "--to",
                "alternate-owner",
                "--by",
                "owner",
                "--reason",
                "Alternate review requested",
            ],
            cwd=root,
            stdout=output,
            stderr=errors,
        )
        == 0
    )
    assert (
        main(
            [
                "approval",
                "add",
                "--swarm",
                "delivery",
                "--work",
                "release",
                "--role",
                "product-owner",
                "--by",
                "alternate-owner",
                "--delegation",
                "alternate-release-approval",
            ],
            cwd=root,
            stdout=output,
            stderr=errors,
        )
        == 0
    )
    assert (
        main(
            [
                "approval",
                "delegations",
                "--swarm",
                "delivery",
                "--work",
                "release",
                "--status",
                "used",
            ],
            cwd=root,
            stdout=output,
            stderr=errors,
        )
        == 0
    )

    assert errors.getvalue() == ""
    assert '"id": "accepted-risk"' in output.getvalue()
    assert '"id": "alternate-release-approval"' in output.getvalue()
    assert '"status": "used"' in output.getvalue()


def _install_kanban_swarm(workspace: AgoraWorkspace) -> None:
    workspace.add_actor(
        AddActorInput(
            id="requester",
            name="Requester",
            kind="human",
            capabilities=["demand-management", "acceptance"],
            scope="project",
        )
    )
    workspace.add_actor(
        AddActorInput(
            id="flow",
            name="Flow Manager",
            kind="ai-agent",
            capabilities=["flow-management", "governance"],
            scope="project",
        )
    )
    workspace.add_actor(
        AddActorInput(
            id="doer",
            name="Delivery",
            kind="ai-agent",
            capabilities=["implementation"],
            scope="project",
        )
    )
    workspace.create_swarm(
        CreateSwarmInput(id="support", objective="Handle inbound requests", method="kanban")
    )
    workspace.assign_actor(
        AssignActorInput(
            swarm_id="support", role_id="service-request-manager", actor_id="requester"
        )
    )
    workspace.assign_actor(
        AssignActorInput(swarm_id="support", role_id="flow-manager", actor_id="flow")
    )
    workspace.assign_actor(
        AssignActorInput(swarm_id="support", role_id="delivery", actor_id="doer")
    )


def test_cli_status_output_is_unchanged_without_the_board_flag(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    workspace = AgoraWorkspace(cwd=tmp_path)
    workspace.initialize(InitInput(integration="generic"))
    workspace.add_actor(
        AddActorInput(
            id="owner",
            name="Owner",
            kind="human",
            capabilities=["specification", "acceptance"],
            scope="project",
        )
    )
    workspace.add_actor(
        AddActorInput(
            id="dev",
            name="Developer",
            kind="ai-agent",
            capabilities=["implementation"],
            scope="project",
        )
    )
    workspace.create_swarm(CreateSwarmInput(id="delivery", objective="Ship the increment"))
    workspace.assign_actor(
        AssignActorInput(swarm_id="delivery", role_id="spec-owner", actor_id="owner")
    )
    workspace.assign_actor(
        AssignActorInput(swarm_id="delivery", role_id="developer", actor_id="dev")
    )
    workspace.create_work(
        CreateWorkInput(swarm_id="delivery", id="feature", title="Ship a feature", actor_id="owner")
    )

    plain_before = io.StringIO()
    errors = io.StringIO()
    assert main(["status"], cwd=tmp_path, stdout=plain_before, stderr=errors) == 0
    assert errors.getvalue() == ""

    plain_after = io.StringIO()
    assert main(["status"], cwd=tmp_path, stdout=plain_after, stderr=errors) == 0
    assert plain_before.getvalue() == plain_after.getvalue()


def test_cli_status_board_with_zero_swarms_shows_a_sensible_message(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    workspace = AgoraWorkspace(cwd=tmp_path)
    workspace.initialize(InitInput(integration="generic"))

    output = io.StringIO()
    errors = io.StringIO()
    assert main(["status", "--board"], cwd=tmp_path, stdout=output, stderr=errors) == 0
    assert errors.getvalue() == ""
    assert "No swarms in this project yet" in output.getvalue()
    assert "Traceback" not in output.getvalue()


def test_cli_status_board_renders_one_swarms_work_states_and_columns(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    workspace = AgoraWorkspace(cwd=tmp_path)
    workspace.initialize(InitInput(integration="generic"))
    workspace.add_actor(
        AddActorInput(
            id="owner",
            name="Owner",
            kind="human",
            capabilities=["specification", "acceptance"],
            scope="project",
        )
    )
    workspace.add_actor(
        AddActorInput(
            id="dev",
            name="Developer",
            kind="ai-agent",
            capabilities=["implementation"],
            scope="project",
        )
    )
    workspace.create_swarm(CreateSwarmInput(id="delivery", objective="Ship the increment"))
    workspace.assign_actor(
        AssignActorInput(swarm_id="delivery", role_id="spec-owner", actor_id="owner")
    )
    workspace.assign_actor(
        AssignActorInput(swarm_id="delivery", role_id="developer", actor_id="dev")
    )
    workspace.create_work(
        CreateWorkInput(swarm_id="delivery", id="feature", title="Ship a feature", actor_id="owner")
    )
    workspace.create_work(
        CreateWorkInput(
            swarm_id="delivery", id="blocked-work", title="Blocked item", actor_id="owner"
        )
    )
    workspace.block_work(
        ChangeWorkStatusInput(
            swarm_id="delivery",
            work_id="blocked-work",
            actor_id="dev",
            reason="Waiting on input",
        )
    )

    output = io.StringIO()
    errors = io.StringIO()
    assert main(["status", "--board"], cwd=tmp_path, stdout=output, stderr=errors) == 0
    assert errors.getvalue() == ""
    rendered = output.getvalue()
    assert "Swarm: delivery" in rendered
    assert "method=spec-driven" in rendered
    assert "drafting" in rendered and "completed" in rendered
    assert "feature: Ship a feature" in rendered
    assert "[!] blocked-work: Blocked item" in rendered


def test_cli_status_board_handles_multiple_swarms_on_different_method_packs(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    workspace = AgoraWorkspace(cwd=tmp_path)
    workspace.initialize(InitInput(integration="generic"))
    workspace.add_actor(
        AddActorInput(
            id="owner",
            name="Owner",
            kind="human",
            capabilities=["specification", "acceptance"],
            scope="project",
        )
    )
    workspace.add_actor(
        AddActorInput(
            id="dev",
            name="Developer",
            kind="ai-agent",
            capabilities=["implementation"],
            scope="project",
        )
    )
    workspace.create_swarm(CreateSwarmInput(id="delivery", objective="Ship the increment"))
    workspace.assign_actor(
        AssignActorInput(swarm_id="delivery", role_id="spec-owner", actor_id="owner")
    )
    workspace.assign_actor(
        AssignActorInput(swarm_id="delivery", role_id="developer", actor_id="dev")
    )
    workspace.create_work(
        CreateWorkInput(swarm_id="delivery", id="feature", title="Ship a feature", actor_id="owner")
    )

    _install_kanban_swarm(workspace)
    workspace.create_work(
        CreateWorkInput(
            swarm_id="support",
            id="ticket",
            title="Handle inbound ticket",
            actor_id="requester",
        )
    )

    output = io.StringIO()
    errors = io.StringIO()
    assert main(["status", "--board"], cwd=tmp_path, stdout=output, stderr=errors) == 0
    assert errors.getvalue() == ""
    rendered = output.getvalue()
    assert "Swarm: delivery" in rendered
    assert "method=spec-driven" in rendered
    assert "Swarm: support" in rendered
    assert "method=kanban" in rendered
    assert "requested" in rendered
    assert "ticket: Handle inbound ticket" in rendered


def test_cli_status_board_truncates_long_ids_and_titles_without_breaking_alignment(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    workspace = AgoraWorkspace(cwd=tmp_path)
    workspace.initialize(InitInput(integration="generic"))
    workspace.add_actor(
        AddActorInput(
            id="owner",
            name="Owner",
            kind="human",
            capabilities=["specification", "acceptance"],
            scope="project",
        )
    )
    workspace.add_actor(
        AddActorInput(
            id="dev",
            name="Developer",
            kind="ai-agent",
            capabilities=["implementation"],
            scope="project",
        )
    )
    long_swarm_id = "delivery-with-an-extremely-long-swarm-identifier-for-testing"
    workspace.create_swarm(CreateSwarmInput(id=long_swarm_id, objective="Ship the increment"))
    workspace.assign_actor(
        AssignActorInput(swarm_id=long_swarm_id, role_id="spec-owner", actor_id="owner")
    )
    workspace.assign_actor(
        AssignActorInput(swarm_id=long_swarm_id, role_id="developer", actor_id="dev")
    )
    long_title = "This is a deliberately very long work item title that should be truncated cleanly"
    workspace.create_work(
        CreateWorkInput(
            swarm_id=long_swarm_id,
            id="very-long-work-item-identifier-for-truncation-testing",
            title=long_title,
            actor_id="owner",
        )
    )

    output = io.StringIO()
    errors = io.StringIO()
    assert main(["status", "--board"], cwd=tmp_path, stdout=output, stderr=errors) == 0
    assert errors.getvalue() == ""
    rendered = output.getvalue()
    assert f"Swarm: {long_swarm_id}" in rendered
    assert long_title not in rendered
    assert "…" in rendered
    lines = [line for line in rendered.splitlines() if line.startswith("  ") and "|" in line]
    widths = {len(line) for line in lines}
    assert len(widths) == 1


def test_cli_status_board_argument_is_a_boolean_flag(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    workspace = AgoraWorkspace(cwd=tmp_path)
    workspace.initialize(InitInput(integration="generic"))

    output = io.StringIO()
    errors = io.StringIO()
    assert main(["status"], cwd=tmp_path, stdout=output, stderr=errors) == 0
    assert "Agora status board" not in output.getvalue()

    output2 = io.StringIO()
    assert main(["status", "--board"], cwd=tmp_path, stdout=output2, stderr=errors) == 0
    assert "Agora status board" in output2.getvalue()
