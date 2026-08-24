import io
import json
import subprocess
from pathlib import Path

import pytest

from conftest import swarm_dir

from agora.cli import main
from agora.markdown import read_markdown, render_markdown
from agora.model import (
    AddActorInput,
    AddArtifactInput,
    AddChecklistInput,
    ApplyLifecycleActionInput,
    AssignActorInput,
    CheckChecklistItemInput,
    CreateSwarmInput,
    CreateWorkInput,
    InitInput,
    SetActorRuntimeInput,
    StartSessionInput,
    WorkActorInput,
)
from agora.workspace import AgoraWorkspace


def _project(tmp_path: Path, monkeypatch, *, tool_runner=None, launcher=None) -> AgoraWorkspace:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    workspace = AgoraWorkspace(cwd=tmp_path, tool_runner=tool_runner, launcher=launcher)
    workspace.initialize(InitInput(integration="generic"))
    workspace.add_actor(
        AddActorInput(
            id="owner",
            name="Owner",
            kind="ai-agent",
            capabilities=["specification", "acceptance"],
            scope="project",
            integration="codex",
            provider="openai",
            model="reviewed-model",
        )
    )
    workspace.add_actor(
        AddActorInput(
            id="developer",
            name="Developer",
            kind="ai-agent",
            capabilities=["implementation"],
            scope="project",
            integration="codex",
            provider="openai",
            model="reviewed-model",
        )
    )
    workspace.create_swarm(CreateSwarmInput(id="delivery", objective="Ship the feature"))
    workspace.assign_actor(
        AssignActorInput(swarm_id="delivery", role_id="spec-owner", actor_id="owner")
    )
    workspace.assign_actor(
        AssignActorInput(swarm_id="delivery", role_id="developer", actor_id="developer")
    )
    workspace.create_work(
        CreateWorkInput(
            swarm_id="delivery",
            id="feature",
            title="Ship a feature",
            actor_id="owner",
            description="Expose a safe endpoint.",
            acceptance_criteria=[("safe-response", "The endpoint returns a safe response")],
        )
    )
    return workspace


def test_checklists_are_attributed_and_do_not_change_gate_criteria(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = _project(tmp_path, monkeypatch)
    before = workspace.show_work("delivery", "feature")
    checklist = workspace.add_checklist(
        AddChecklistInput(
            swarm_id="delivery",
            work_id="feature",
            actor_id="owner",
            title="Language quality",
            items=["No ambiguous pronouns", "Failure behavior is explicit"],
        )
    )
    toggled = workspace.check_checklist_item(
        CheckChecklistItemInput(
            swarm_id="delivery",
            work_id="feature",
            actor_id="owner",
            checklist_id=checklist.id,
            item_index=2,
        )
    )

    assert toggled.checked_items == [2]
    assert toggled.updated_by == "project:owner"
    assert "- [x] Failure behavior is explicit" in Path(toggled.path).read_text()
    after = workspace.show_work("delivery", "feature")
    assert after.satisfied_criteria == before.satisfied_criteria
    assert after.criterion_statuses == before.criterion_statuses


def test_cli_exposes_work_traceability_as_json(tmp_path: Path, monkeypatch) -> None:
    _project(tmp_path, monkeypatch)
    output = io.StringIO()
    errors = io.StringIO()

    assert (
        main(
            ["work", "traceability", "--swarm", "delivery", "--work", "feature"],
            cwd=tmp_path,
            stdout=output,
            stderr=errors,
        )
        == 0
    )
    assert errors.getvalue() == ""
    payload = json.loads(output.getvalue())
    assert payload["work"] == "feature"
    assert payload["criteria"][0]["id"] == "safe-response"


def test_clarify_appends_at_most_five_structured_questions(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("agora.workspace.shutil.which", lambda executable: f"/usr/bin/{executable}")

    def run(command, cwd, environment):
        payload = {
            "questions": [
                {"question": "Which status code is required?", "answer": "200"},
                {"question": "Is authentication required?", "answer": None},
            ]
        }
        return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

    workspace = _project(tmp_path, monkeypatch, tool_runner=run)
    result = workspace.clarify_work(
        WorkActorInput(swarm_id="delivery", work_id="feature", actor_id="owner")
    )

    path = Path(result["path"])
    contents = path.read_text()
    assert 'schema: "agora/clarifications/v1"' in contents
    assert "Which status code is required? | 200 | project:owner" in contents
    assert "Is authentication required? |  | project:owner" in contents
    traceability = workspace.work_traceability("delivery", "feature")
    assert traceability["clarifications"]["stale"] is False
    assert len(traceability["clarifications"]["recorded-input-sha256"]) == 1

    work_path = swarm_dir(tmp_path, "delivery") / "work" / "feature" / "WORK.md"
    document = read_markdown(work_path)
    document.attributes["acceptance-criteria"]["safe-response"] = "A revised safe response"
    work_path.write_text(render_markdown(document))
    stale = workspace.work_traceability("delivery", "feature")
    assert stale["clarifications"]["stale"] is True
    report = workspace.validate()
    assert any(issue.code == "clarifications.stale" for issue in report.issues)


def test_generic_advisory_runner_is_bound_through_a_prepared_action(
    tmp_path: Path, monkeypatch
) -> None:
    observed = {}

    def run(command, cwd, environment):
        observed["command"] = command
        prompt_path = Path(environment["AGORA_ADVISORY_PROMPT"])
        observed["prompt"] = prompt_path.read_text()
        payload = {"questions": [{"question": "What is the timeout?", "answer": None}]}
        return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

    workspace = _project(tmp_path, monkeypatch, tool_runner=run)
    workspace.set_actor_runtime(
        SetActorRuntimeInput(
            actor_id="owner",
            integration="generic",
            provider="internal",
            model="reviewed",
        )
    )
    data = WorkActorInput(swarm_id="delivery", work_id="feature", actor_id="owner")
    prepared = workspace.prepare_work_clarification(
        "clarify-feature", data, runner="/bin/true advise"
    )
    applied = workspace.apply_lifecycle_action(ApplyLifecycleActionInput(action_id=prepared.id))

    assert applied.status == "applied"
    assert observed["command"] == ["/bin/true", "advise"]
    assert "Return only JSON" in observed["prompt"]
    assert (swarm_dir(tmp_path, "delivery") / "work" / "feature" / "clarifications.md").is_file()


def test_consistency_and_gherkin_outputs_reuse_artifact_and_evidence_records(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr("agora.workspace.shutil.which", lambda executable: f"/usr/bin/{executable}")
    responses = [
        {
            "features": {
                "safe-response": (
                    "Feature: Safe response\n\n"
                    "  Scenario: Return the response\n"
                    "    Given an authorized caller\n"
                    "    When the endpoint is requested\n"
                    "    Then a safe response is returned\n"
                )
            }
        },
        {"result": "success", "report": "Every criterion is covered."},
    ]

    def run(command, cwd, environment):
        return subprocess.CompletedProcess(command, 0, json.dumps(responses.pop(0)), "")

    workspace = _project(tmp_path, monkeypatch, tool_runner=run)
    spec = tmp_path / "spec.md"
    spec.write_text("# Spec\n\nThe endpoint returns a safe response.\n")
    workspace.add_artifact(
        AddArtifactInput(
            swarm_id="delivery",
            work_id="feature",
            actor_id="owner",
            kind="spec",
            uri="repo://spec.md",
        )
    )

    gherkin = workspace.generate_work_gherkin(
        WorkActorInput(swarm_id="delivery", work_id="feature", actor_id="owner")
    )
    consistency = workspace.verify_work_consistency(
        WorkActorInput(swarm_id="delivery", work_id="feature", actor_id="owner")
    )

    assert consistency["result"] == "success"
    assert consistency["report"].startswith("repo://.agora/")
    expected_feature_uri = (
        "repo://"
        + swarm_dir(tmp_path, "delivery").relative_to(tmp_path).as_posix()
        + "/work/feature/gherkin/safe-response.feature"
    )
    assert gherkin["features"] == [expected_feature_uri]
    work = workspace.show_work("delivery", "feature")
    assert "consistency-report" in work.artifact_kinds
    assert "gherkin-feature" in work.artifact_kinds
    evidence = (Path(work.path) / "evidence.md").read_text()
    assert "| consistency-check | success |" in evidence
    traceability = workspace.work_traceability("delivery", "feature")
    assert traceability["stale"] is False
    assert traceability["criteria"][0]["gherkin-features"] == gherkin["features"]

    work_path = Path(work.path) / "WORK.md"
    document = read_markdown(work_path)
    document.attributes["acceptance-criteria"]["safe-response"] = (
        "The endpoint returns a newly specified safe response"
    )
    work_path.write_text(render_markdown(document))

    stale = workspace.work_traceability("delivery", "feature")
    assert stale["stale"] is True
    assert stale["gherkin"][0]["stale"] is True
    assert stale["consistency"][0]["stale"] is True
    report = workspace.validate()
    stale_issues = [issue for issue in report.issues if issue.code == "artifact.stale"]
    assert len(stale_issues) == 2
    assert all(issue.severity == "warning" for issue in stale_issues)


def test_runtime_fallback_uses_first_available_runtime_and_records_it(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        "agora.workspace.shutil.which",
        lambda executable: "/usr/bin/claude" if executable == "claude" else None,
    )
    calls = []

    def launch(command, cwd, environment):
        calls.append(command)
        return 0

    workspace = _project(tmp_path, monkeypatch, launcher=launch)
    actor = workspace.set_actor_runtime(
        SetActorRuntimeInput(
            actor_id="developer",
            integration="codex",
            provider="openai",
            model="primary",
            fallbacks=["claude:anthropic:fallback-model", "generic:local:manual"],
        )
    )
    session = workspace.start_session(
        StartSessionInput(
            id="fallback-session",
            actor_id="developer",
            swarm_id="delivery",
            work_id="feature",
            launch=True,
        )
    )

    assert actor.runtime_fallbacks[0]["integration"] == "claude"
    assert calls[0][:2] == ["claude", "--print"]
    assert (session.integration, session.provider, session.model) == (
        "claude",
        "anthropic",
        "fallback-model",
    )
    summary = Path(session.path) / "SUMMARY.md"
    assert 'integration: "claude"' in summary.read_text()


def test_runtime_fallback_rejects_malformed_or_duplicate_entries(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = _project(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="integration:provider:model"):
        workspace.set_actor_runtime(
            SetActorRuntimeInput(actor_id="developer", fallbacks=["claude:anthropic"])
        )
    with pytest.raises(ValueError, match="Duplicate runtime fallback"):
        workspace.set_actor_runtime(
            SetActorRuntimeInput(
                actor_id="developer",
                fallbacks=[
                    "claude:anthropic:fallback-model",
                    "claude:anthropic:fallback-model",
                ],
            )
        )


def test_runtime_fallback_only_skips_failures_with_rate_limit_signatures(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr("agora.workspace.shutil.which", lambda executable: f"/usr/bin/{executable}")
    calls = []

    def fail(command, cwd, environment):
        calls.append(command)
        return 1

    workspace = _project(tmp_path, monkeypatch, launcher=fail)
    workspace.set_actor_runtime(
        SetActorRuntimeInput(
            actor_id="developer",
            integration="codex",
            provider="openai",
            model="primary",
            fallbacks=["claude:anthropic:fallback-model"],
        )
    )
    with pytest.raises(RuntimeError):
        workspace.start_session(
            StartSessionInput(
                id="failed-primary",
                actor_id="developer",
                swarm_id="delivery",
                work_id="feature",
                launch=True,
            )
        )
    assert calls[-1][0] == "codex"

    result_path = tmp_path / ".agora" / "sessions" / "failed-primary" / "RESULT.md"
    result_path.write_text(result_path.read_text().replace("(empty)", "quota exceeded", 1))
    successful_calls = []

    def succeed(command, cwd, environment):
        successful_calls.append(command)
        return 0

    retry_workspace = AgoraWorkspace(cwd=tmp_path, launcher=succeed)
    session = retry_workspace.start_session(
        StartSessionInput(
            id="fallback-after-quota",
            actor_id="developer",
            swarm_id="delivery",
            work_id="feature",
            launch=True,
        )
    )
    assert successful_calls[0][0] == "claude"
    assert session.provider == "anthropic"
