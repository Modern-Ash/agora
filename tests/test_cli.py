import io
from pathlib import Path

from agora.cli import main
from agora.model import (
    AddActorInput,
    AssignActorInput,
    CreateSwarmInput,
    CreateWorkInput,
    InitInput,
)
from agora.workspace import AgoraWorkspace


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


def test_configures_actor_runtime_and_prepares_a_session_from_the_cli(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    workspace = AgoraWorkspace(cwd=root)
    workspace.initialize(InitInput(integration="generic"))
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
    workspace.initialize(InitInput(integration="generic"))
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
            ["delegation", "show", "--delegation", "cli-delegation"],
            cwd=root,
            stdout=output,
            stderr=errors,
        )
        == 0
    )

    assert errors.getvalue() == ""
    assert '"status": "proposed"' in output.getvalue()
    assert output.getvalue().count('"status": "accepted"') == 2
    assert (
        root / ".agora" / "swarms" / "specialists" / "work" / "specialist-work" / "WORK.md"
    ).exists()
