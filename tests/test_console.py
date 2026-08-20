import io
import time
from types import SimpleNamespace

import pytest

import agora.cli as cli
from agora.console import (
    ActivityContext,
    ConsoleActivity,
    ConsoleResult,
    _fit_terminal_line,
    _orbit_frame,
)
from agora.model import RunLoopEvent


class TtyBuffer(io.StringIO):
    def isatty(self) -> bool:
        return True


def _context() -> ActivityContext:
    return ActivityContext(
        "Governed agent loop",
        "Build visual console",
        "Expose durable delivery state",
        "Phase: implementing -> verifying",
        "project:agent (developer) | studio/visual",
        "Authority: implementation | local actor identity",
        ("AGORA PLAN  Safe execution preview", "  Runtime    codex/openai/model"),
        (
            "Runtime active within implementing -> verifying",
            "Watching durable evidence and transitions",
        ),
    )


def test_console_shows_preflight_context_and_finishes_on_tty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AGORA_NO_PROGRESS", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")
    output = TtyBuffer()

    with ConsoleActivity(output, _context(), interval_seconds=0.01):
        time.sleep(0.03)

    rendered = output.getvalue()
    assert "AGORA PLAN  Safe execution preview" in rendered
    assert "codex/openai/model" in rendered
    assert "Build visual console" in rendered
    assert "Authority: implementation" in rendered
    assert "Now: Runtime active" in rendered
    assert "| A |" in rendered
    assert "AGORA [finished]" in rendered


def test_console_renders_governed_step_events_without_provider_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AGORA_NO_PROGRESS", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")
    output = TtyBuffer()
    task = SimpleNamespace(
        actor="project:agent",
        role="developer",
        target_states=["verifying"],
    )
    session = SimpleNamespace(id="run-visual", status="completed", exit_code=0)
    human = SimpleNamespace(actor="project:owner", role="spec-owner", actor_kind="human")

    with ConsoleActivity(output, _context(), interval_seconds=1) as activity:
        activity.handle_run_event(
            RunLoopEvent(
                kind="step-selected",
                step=1,
                max_steps=6,
                task=task,
                before_state="implementing",
            )
        )
        activity.handle_run_event(
            RunLoopEvent(
                kind="session-finished",
                step=1,
                max_steps=6,
                task=task,
                session=session,
                before_state="implementing",
                after_state="verifying",
            )
        )
        activity.handle_run_event(
            RunLoopEvent(
                kind="loop-stopped",
                step=1,
                max_steps=6,
                stop_reason="human-attention",
                next_actions=[human],
            )
        )

    rendered = output.getvalue()
    assert "SELECT" in rendered
    assert "SESSION completed" in rendered
    assert "implementing -> verifying" in rendered
    assert "HUMAN ATTENTION" in rendered
    assert "project:owner (spec-owner)" in rendered
    assert "provider output" not in rendered


def test_console_rotates_one_stable_live_detail_line() -> None:
    output = TtyBuffer()
    activity = ConsoleActivity(output, _context(), interval_seconds=0.1)
    activity.context = _context()

    activity._render(0)
    activity._render(18)

    rendered = output.getvalue()
    assert "Now: Runtime active within implementing -> verifying" in rendered
    assert "Now: Watching durable evidence and transitions" in rendered


def test_console_prioritizes_governed_live_events_over_rotation() -> None:
    output = TtyBuffer()
    context = ActivityContext(
        **{
            **_context().__dict__,
            "live_detail_provider": lambda: "Evidence recorded · type=verification result=success",
        }
    )
    activity = ConsoleActivity(output, context, interval_seconds=1)

    activity._render(0)

    assert "Now: Evidence recorded · type=verification result=success" in output.getvalue()
    assert "provider reasoning" not in output.getvalue()


def test_live_detail_provider_reports_only_new_durable_activity() -> None:
    previous = SimpleNamespace(
        timestamp="2026-08-17T12:00:00Z",
        type="session.prepared",
        summary="Prepared session",
        source="repo://.agora/sessions/old/SESSION.md",
    )
    current = SimpleNamespace(
        timestamp="2026-08-17T12:00:01Z",
        type="artifact.added",
        summary="kind=verification-report uri=repo://reports/verification.md",
        source="repo://.agora/swarms/delivery/work/item/artifacts.md",
    )
    responses = iter(([previous], [current]))
    read_service = SimpleNamespace(activity=lambda filters: next(responses))

    detail = cli._governed_activity_provider(
        SimpleNamespace(),
        swarm_id="delivery",
        work_id="item",
        read_service=read_service,
    )()

    assert detail == (
        "Artifact registered · kind=verification-report uri=repo://reports/verification.md"
    )


def test_console_stays_silent_off_tty_or_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plain = io.StringIO()
    with ConsoleActivity(plain, _context()):
        pass
    assert plain.getvalue() == ""

    monkeypatch.setenv("AGORA_NO_PROGRESS", "true")
    tty = TtyBuffer()
    with ConsoleActivity(tty, _context()):
        pass
    assert tty.getvalue() == ""


def test_cli_keeps_interactive_progress_out_of_json_stdout(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.delenv("AGORA_NO_PROGRESS", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.setattr(cli, "_dispatch", lambda workspace, args: {"ok": True})
    output = io.StringIO()
    progress = TtyBuffer()

    result = cli.main(
        ["run", "--actor", "project:agent"],
        cwd=tmp_path,
        stdout=output,
        stderr=progress,
    )

    assert result == 0
    assert output.getvalue() == '{\n  "ok": true\n}\n'
    assert "AGORA [finished]" in progress.getvalue()
    assert output.getvalue().count("AGORA") == 0


def test_cli_renders_status_for_a_human_terminal(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.delenv("NO_COLOR", raising=False)
    assert cli.main(["init"], cwd=tmp_path, stdout=io.StringIO()) == 0
    output = TtyBuffer()

    result = cli.main(["status"], cwd=tmp_path, stdout=output)

    rendered = output.getvalue()
    assert result == 0
    assert "Agora status" in rendered
    assert "Project" in rendered
    assert "Attention" in rendered
    assert "\x1b[" in rendered
    assert "{" not in rendered


def test_cli_uses_compact_human_output_for_mutations(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("TERM", "xterm-256color")
    output = TtyBuffer()

    result = cli.main(["init"], cwd=tmp_path, stdout=output)

    rendered = output.getvalue()
    assert result == 0
    assert "Init" in rendered
    assert "Default Method" in rendered
    assert "{" not in rendered


def test_console_renders_actionable_session_diagnosis() -> None:
    output = TtyBuffer()

    ConsoleResult(output).render(
        "session diagnose",
        {
            "id": "failed-run",
            "status": "recovered",
            "actor": "project:agent",
            "swarm_id": "delivery",
            "work_id": "increment",
            "termination_reason": "output-limit",
            "diagnosis": "Recovered by session retry-run.",
            "output_bytes": 4194371,
            "max_output_bytes": 4194304,
            "output_percent": 100.0,
            "recovered_by": "retry-run",
            "recommended_command": "agora next --swarm delivery",
        },
    )

    rendered = output.getvalue()
    assert "Session diagnosis" in rendered
    assert "output-limit" in rendered
    assert "retry-run" in rendered
    assert "agora next --swarm delivery" in rendered


def test_console_fits_terminal_lines_and_orbit_moves() -> None:
    fitted = _fit_terminal_line("A deliberately long governed operation", 32)
    assert fitted == "A deliberately long governed..."
    assert len(fitted) == 31
    assert "o" in _orbit_frame(0)[0]
    assert _orbit_frame(2)[2].endswith("o")
    assert "o" in _orbit_frame(4)[4]
