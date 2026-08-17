import io
import json
import shlex
import sys
from pathlib import Path

import pytest

import agora.cli as cli
from agora.cli import main
from agora.model import (
    AddActorInput,
    AssignActorInput,
    CreateSwarmInput,
    CreateWorkInput,
    InitInput,
    ResumeSessionInput,
    RunNextInput,
    StartSessionInput,
    TransitionWorkInput,
)
from agora.workspace import AgoraWorkspace


class TtyInput(io.StringIO):
    def isatty(self) -> bool:
        return True


def _scrum_workspace(
    tmp_path: Path,
    monkeypatch,
    *,
    integration: str = "generic",
    model: str = "configured-by-integration",
    launcher=None,
) -> AgoraWorkspace:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    root = tmp_path / "project"
    root.mkdir()
    workspace = AgoraWorkspace(cwd=root, launcher=launcher)
    workspace.initialize(
        InitInput(
            integration=integration,
            provider="test-provider",
            model=model,
            default_method="scrum",
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
    workspace.create_swarm(
        CreateSwarmInput(id="delivery", objective="Ship the increment", create_branch=False)
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
            id="increment",
            title="Ship an increment",
            actor_id="owner",
            acceptance_criteria=[("accepted", "The increment is accepted")],
            required_artifacts=["source-code"],
        )
    )
    return workspace


def test_derives_next_agent_action_and_launches_one_bound_session(
    tmp_path: Path, monkeypatch
) -> None:
    calls: list[list[str]] = []

    def launch(command, cwd, environment):
        calls.append(command)
        assert environment["AGORA_WORK"] == "increment"
        return 0

    workspace = _scrum_workspace(tmp_path, monkeypatch, launcher=launch)

    tasks = workspace.next_actions()
    assert [(task.actor, task.role, task.target_states) for task in tasks] == [
        ("project:developer", "developer", ["planned"])
    ]
    assert workspace.next_actions(human_only=True) == []

    prepared = workspace.run_next(
        RunNextInput(
            actor_id="developer",
            runner="/bin/true --agent",
            prepare_only=True,
        )
    )
    assert prepared.status == "prepared"
    assert workspace.next_actions(actor_id="developer")[0].session_id == prepared.id

    completed = workspace.run_next(RunNextInput(actor_id="developer"))
    assert completed.id == prepared.id
    assert completed.status == "completed"
    assert calls == [["/bin/true", "--agent"]]


def test_retries_a_failed_session_without_overwriting_it(tmp_path: Path, monkeypatch) -> None:
    workspace = _scrum_workspace(
        tmp_path,
        monkeypatch,
        launcher=lambda command, cwd, environment: 9,
    )
    with pytest.raises(RuntimeError, match="exited with code 9"):
        workspace.run_next(
            RunNextInput(
                actor_id="developer",
                runner="/bin/false",
                timeout_seconds=17,
                max_output_bytes=2048,
            )
        )

    failed = workspace.list_sessions("failed")[0]
    retry_workspace = AgoraWorkspace(
        cwd=workspace.project_root(), launcher=lambda command, cwd, environment: 0
    )
    completed = retry_workspace.resume_session(
        ResumeSessionInput(session_id=failed.id, replacement_id="retry-increment")
    )

    assert failed.status == "failed"
    assert completed.id == "retry-increment"
    assert completed.status == "completed"
    assert completed.timeout_seconds == 17
    assert completed.max_output_bytes == 2048
    assert {item.id for item in retry_workspace.list_sessions()} == {
        failed.id,
        "retry-increment",
    }


def test_diagnoses_output_limit_and_marks_a_successful_retry_recovered(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = _scrum_workspace(
        tmp_path,
        monkeypatch,
        launcher=lambda command, cwd, environment: 125,
    )
    with pytest.raises(RuntimeError, match="output-limit"):
        workspace.run_next(
            RunNextInput(actor_id="developer", runner="/bin/false", max_output_bytes=2048)
        )
    failed = workspace.list_sessions("failed")[0]

    diagnosis = workspace.diagnose_session(failed.id)

    assert diagnosis["status"] == "failed"
    assert diagnosis["termination_reason"] == "output-limit"
    assert diagnosis["recommended_command"].endswith("--max-output-bytes 4096")

    retry_workspace = AgoraWorkspace(
        cwd=workspace.project_root(), launcher=lambda command, cwd, environment: 0
    )
    retry = retry_workspace.resume_session(ResumeSessionInput(session_id=failed.id))
    recovered = retry_workspace.diagnose_session(failed.id)

    assert recovered["status"] == "recovered"
    assert recovered["recovered_by"] == retry.id
    assert retry_workspace.status().attention["failed-sessions"] == []


def test_guided_continue_reviews_and_launches_one_agent_action(tmp_path: Path, monkeypatch) -> None:
    workspace = _scrum_workspace(
        tmp_path,
        monkeypatch,
        launcher=lambda command, cwd, environment: 0,
    )
    output = io.StringIO()
    args = type(
        "Args",
        (),
        {
            "yes": False,
            "actor": None,
            "swarm": "delivery",
            "work": "increment",
            "runner": "/bin/true",
            "until_blocked": False,
            "max_steps": 20,
        },
    )()

    result = cli._run_continue_wizard(
        workspace,
        args,
        input_stream=TtyInput("y\n"),
        output_stream=output,
    )

    assert result["applied"] is True
    assert len(workspace.list_sessions()) == 1
    assert "Agora Continue | Next governed action" in output.getvalue()
    assert "Governed action completed" in output.getvalue()


def test_agent_can_persist_governed_mutations_while_its_session_runs(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "project"

    def launch(command, cwd, environment):
        actor_workspace = AgoraWorkspace(cwd=root)
        actor_workspace.transition_work(
            TransitionWorkInput(
                swarm_id=environment["AGORA_SWARM"],
                work_id=environment["AGORA_WORK"],
                actor_id=environment["AGORA_ACTOR"],
                target_state="planned",
            )
        )
        return 0

    workspace = _scrum_workspace(tmp_path, monkeypatch, launcher=launch)
    completed = workspace.run_next(RunNextInput(actor_id="developer", runner="/bin/true --agent"))

    assert completed.status == "completed"
    assert workspace.show_work("delivery", "increment").state == "planned"
    assert workspace.lock_status().active is False


def test_bounded_run_loop_stops_at_human_attention(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "project"
    targets = {
        "specified": "planned",
        "planned": "implementing",
        "implementing": "reviewing",
        "reviewing": "verifying",
    }

    def launch(command, cwd, environment):
        actor_workspace = AgoraWorkspace(cwd=root)
        work = actor_workspace.show_work(environment["AGORA_SWARM"], environment["AGORA_WORK"])
        actor_workspace.transition_work(
            TransitionWorkInput(
                swarm_id=work.swarm_id,
                work_id=work.id,
                actor_id=environment["AGORA_ACTOR"],
                target_state=targets[work.state],
            )
        )
        return 0

    workspace = _scrum_workspace(tmp_path, monkeypatch, launcher=launch)
    result = workspace.run_until_blocked(RunNextInput(runner="/bin/true --agent"), max_steps=10)

    assert len(result.sessions) == 4
    assert result.stop_reason == "human-attention"
    assert workspace.show_work("delivery", "increment").state == "verifying"
    assert result.next_actions[0].actor == "project:owner"


def test_actor_filter_cannot_hide_higher_priority_human_gate(tmp_path: Path, monkeypatch) -> None:
    workspace = _scrum_workspace(tmp_path, monkeypatch)
    for state, actor in (
        ("planned", "developer"),
        ("implementing", "developer"),
        ("reviewing", "developer"),
        ("verifying", "facilitator"),
    ):
        workspace.transition_work(
            TransitionWorkInput(
                swarm_id="delivery",
                work_id="increment",
                actor_id=actor,
                target_state=state,
            )
        )

    result = workspace.run_until_blocked(
        RunNextInput(actor_id="developer", swarm_id="delivery", work_id="increment"),
        max_steps=6,
    )

    assert result.sessions == []
    assert result.stop_reason == "human-attention"
    assert result.next_actions[0].actor == "project:owner"
    preview = workspace.preview_run(
        RunNextInput(actor_id="developer", swarm_id="delivery", work_id="increment")
    )
    assert preview.task.actor == "project:owner"
    assert preview.runtime_source == "not-applicable"
    assert preview.integration == "not-applicable"
    assert preview.timeout_seconds is None
    assert preview.max_output_bytes is None
    with pytest.raises(ValueError, match="human attention from project:owner"):
        workspace.run_next(
            RunNextInput(actor_id="developer", swarm_id="delivery", work_id="increment")
        )


def test_run_preview_exposes_authority_runtime_and_bounds_without_mutation(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = _scrum_workspace(tmp_path, monkeypatch)

    preview = workspace.preview_run(
        RunNextInput(
            actor_id="developer",
            swarm_id="delivery",
            work_id="increment",
            timeout_seconds=45,
            max_output_bytes=8192,
        )
    )

    assert preview.task.actor == "project:developer"
    assert preview.task.role == "developer"
    assert preview.task.state == "specified"
    assert preview.task.target_states == ["planned"]
    assert preview.work_title == "Ship an increment"
    assert preview.method == "scrum"
    assert preview.actor_capabilities == ["implementation"]
    assert preview.integration == "generic"
    assert preview.provider == "test-provider"
    assert preview.model == "configured-by-integration"
    assert preview.authentication_required is False
    assert preview.runtime_source == "configured"
    assert preview.timeout_seconds == 45
    assert preview.max_output_bytes == 8192
    assert workspace.list_sessions() == []


def test_cli_explain_returns_preview_json_without_starting_a_session(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = _scrum_workspace(tmp_path, monkeypatch)
    output = io.StringIO()

    result = main(
        [
            "run",
            "--actor",
            "developer",
            "--swarm",
            "delivery",
            "--work",
            "increment",
            "--timeout-seconds",
            "30",
            "--max-output-bytes",
            "4096",
            "--explain",
        ],
        cwd=workspace.project_root(),
        stdout=output,
    )

    payload = json.loads(output.getvalue())
    assert result == 0
    assert payload["task"]["actor"] == "project:developer"
    assert payload["task"]["target_states"] == ["planned"]
    assert payload["actor_capabilities"] == ["implementation"]
    assert payload["timeout_seconds"] == 30
    assert payload["max_output_bytes"] == 4096
    assert workspace.list_sessions() == []


def test_run_loop_emits_safe_structured_step_events(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "project"

    def launch(command, cwd, environment):
        actor_workspace = AgoraWorkspace(cwd=root)
        actor_workspace.transition_work(
            TransitionWorkInput(
                swarm_id=environment["AGORA_SWARM"],
                work_id=environment["AGORA_WORK"],
                actor_id=environment["AGORA_ACTOR"],
                target_state="planned",
            )
        )
        return 0

    workspace = _scrum_workspace(tmp_path, monkeypatch, launcher=launch)
    events = []

    result = workspace.run_until_blocked(
        RunNextInput(actor_id="developer", runner="/bin/true"),
        max_steps=1,
        observer=events.append,
    )

    assert result.stop_reason == "max-steps"
    assert [event.kind for event in events] == [
        "step-selected",
        "session-finished",
        "loop-stopped",
    ]
    assert events[0].before_state == "specified"
    assert events[1].after_state == "planned"
    assert events[1].session.status == "completed"
    assert events[2].stop_reason == "max-steps"
    stopped = workspace.list_activity(type_="run-loop.stopped")
    assert len(stopped) == 1
    assert stopped[0].summary == "Stopped after 1 session(s): max-steps"
    assert stopped[0].session_id == events[1].session.id
    assert stopped[0].source.endswith("/SUMMARY.md")


def test_run_loop_stops_when_runner_records_no_governed_progress(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = _scrum_workspace(
        tmp_path,
        monkeypatch,
        launcher=lambda command, cwd, environment: 0,
    )

    result = workspace.run_until_blocked(RunNextInput(runner="/bin/true --agent"), max_steps=10)

    assert len(result.sessions) == 1
    assert result.stop_reason == "no-governed-progress"
    assert workspace.show_work("delivery", "increment").state == "specified"


def test_human_inbox_exposes_terminal_gate_obligations(tmp_path: Path, monkeypatch) -> None:
    workspace = _scrum_workspace(tmp_path, monkeypatch)
    for state, actor in (
        ("planned", "developer"),
        ("implementing", "developer"),
        ("reviewing", "developer"),
        ("verifying", "facilitator"),
    ):
        workspace.transition_work(
            TransitionWorkInput(
                swarm_id="delivery",
                work_id="increment",
                actor_id=actor,
                target_state=state,
            )
        )

    inbox = workspace.next_actions(human_only=True)

    assert len(inbox) == 1
    assert inbox[0].actor == "project:owner"
    assert inbox[0].target_states == ["completed"]
    assert "Gate completion failed" in inbox[0].blockers[0]


def test_materializes_non_interactive_native_cli_commands(tmp_path: Path, monkeypatch) -> None:
    workspace = _scrum_workspace(
        tmp_path,
        monkeypatch,
        integration="codex",
        model="gpt-test",
    )

    session = workspace.start_session(
        StartSessionInput(
            id="native-runtime",
            actor_id="developer",
            swarm_id="delivery",
            work_id="increment",
        )
    )

    assert session.launch_command[:4] == ["codex", "exec", "--model", "gpt-test"]
    assert "AGORA_CONTEXT" in session.launch_command[-1]
    assert "human approval" in session.launch_command[-1]


def test_bounds_real_session_runtime_and_persists_timeout_result(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = _scrum_workspace(tmp_path, monkeypatch)
    runner = shlex.join([sys.executable, "-c", "import time; time.sleep(2)"])

    with pytest.raises(RuntimeError, match="exited with code 124"):
        workspace.start_session(
            StartSessionInput(
                id="timed-session",
                actor_id="developer",
                swarm_id="delivery",
                work_id="increment",
                runner=runner,
                launch=True,
                timeout_seconds=1,
                max_output_bytes=1024,
            )
        )

    failed = workspace.list_sessions("failed")[0]
    result = (Path(failed.path) / "RESULT.md").read_text(encoding="utf-8")
    assert failed.exit_code == 124
    assert failed.termination_reason == "timeout"
    assert failed.timeout_seconds == 1
    assert "terminated the session after 1 seconds" in result
    result_path = Path(failed.path) / "RESULT.md"
    result_path.write_text(
        result.replace('termination-reason: "timeout"', 'termination-reason: "output-limit"'),
        encoding="utf-8",
    )
    report = workspace.validate()
    assert any(issue.code == "session.result-invalid" for issue in report.issues)


def test_bounds_real_session_output_and_rejects_invalid_limits(tmp_path: Path, monkeypatch) -> None:
    workspace = _scrum_workspace(tmp_path, monkeypatch)
    runner = shlex.join([sys.executable, "-c", "print('x' * 4096)"])

    with pytest.raises(RuntimeError, match="exited with code 125"):
        workspace.start_session(
            StartSessionInput(
                id="noisy-session",
                actor_id="developer",
                swarm_id="delivery",
                work_id="increment",
                runner=runner,
                launch=True,
                timeout_seconds=5,
                max_output_bytes=256,
            )
        )

    failed = workspace.list_sessions("failed")[0]
    result = (Path(failed.path) / "RESULT.md").read_text(encoding="utf-8")
    assert failed.exit_code == 125
    assert failed.termination_reason == "output-limit"
    assert failed.max_output_bytes == 256
    assert failed.output_bytes <= 512
    assert "session output to 256 bytes" in result or "output exceeded 256 bytes" in result

    with pytest.raises(ValueError, match="Session timeout must be between"):
        workspace.start_session(
            StartSessionInput(
                id="invalid-session",
                actor_id="developer",
                swarm_id="delivery",
                timeout_seconds=0,
            )
        )


def test_exposes_operational_loop_through_the_cli(tmp_path: Path, monkeypatch) -> None:
    workspace = _scrum_workspace(tmp_path, monkeypatch)
    output = io.StringIO()
    errors = io.StringIO()

    assert main(["next", "--actor", "developer"], cwd=workspace.project_root(), stdout=output) == 0
    assert '"kind": "execute-work"' in output.getvalue()
    output.seek(0)
    output.truncate(0)

    assert (
        main(
            [
                "run",
                "--actor",
                "developer",
                "--runner",
                "/bin/true",
                "--prepare-only",
                "--timeout-seconds",
                "42",
                "--max-output-bytes",
                "4096",
            ],
            cwd=workspace.project_root(),
            stdout=output,
            stderr=errors,
        )
        == 0
    )
    assert errors.getvalue() == ""
    assert '"status": "prepared"' in output.getvalue()
    assert '"timeout_seconds": 42' in output.getvalue()
    assert '"max_output_bytes": 4096' in output.getvalue()
