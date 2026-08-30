import io
import json
from datetime import UTC, datetime
from pathlib import Path

from agora.cli import main
from agora.model import (
    AddActorInput,
    AddControlBandInput,
    AddEvaluationSuiteInput,
    AddGuardrailInput,
    AddReviewFindingInput,
    AddTriggerInput,
    AssignActorInput,
    CreateIntentInput,
    CreateSwarmInput,
    CreateWorkInput,
    DecideIntentInput,
    DecideReviewFindingInput,
    EvaluateControlBandInput,
    EventRecord,
    IngestTriggerEventInput,
    InitInput,
    RecordEvaluationRunInput,
)
from agora.sdlc import SdlcService
from agora.workspace import AgoraWorkspace


def _workspace(tmp_path: Path, monkeypatch) -> AgoraWorkspace:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    workspace = AgoraWorkspace(
        cwd=tmp_path,
        now=lambda: datetime(2026, 8, 25, 12, 0, tzinfo=UTC),
    )
    workspace.initialize(InitInput())
    return workspace


def _work(workspace: AgoraWorkspace) -> None:
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
            id="developer",
            name="Developer",
            kind="ai-agent",
            capabilities=["implementation"],
            scope="project",
        )
    )
    workspace.create_swarm(CreateSwarmInput(id="delivery", objective="Deliver safely"))
    workspace.assign_actor(
        AssignActorInput(swarm_id="delivery", role_id="spec-owner", actor_id="owner")
    )
    workspace.assign_actor(
        AssignActorInput(swarm_id="delivery", role_id="developer", actor_id="developer")
    )
    workspace.create_work(
        CreateWorkInput(
            swarm_id="delivery",
            id="change",
            title="Governed change",
            actor_id="owner",
        )
    )


def test_intent_has_an_explicit_human_decision(tmp_path: Path, monkeypatch) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    draft = workspace.create_intent(
        CreateIntentInput(
            id="reduce-errors",
            author="operations:ana",
            problem="Customers see elevated API errors.",
            outcome="Restore the API error budget.",
            affected_systems=["api"],
            constraints=["No standing production credentials."],
            open_questions=["Which deployment introduced the regression?"],
            source="incident://INC-42",
        )
    )
    assert draft.status == "draft"
    accepted = workspace.decide_intent(
        DecideIntentInput(
            id=draft.id,
            decision="accepted",
            actor="product:owner",
            reason="The impact and desired outcome are clear.",
        )
    )
    assert accepted.status == "accepted"
    assert accepted.decided_by == "product:owner"
    assert workspace.validate().ok


def test_evaluations_review_findings_and_guardrails_are_structured(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    _work(workspace)
    suite = workspace.add_evaluation_suite(
        AddEvaluationSuiteInput(
            id="agent-regression",
            cases=["create-safe-api", "preserve-auth"],
            minimum_pass_rate=80,
            trigger_paths=[".agents/**", ".agora/methods/**"],
        )
    )
    failed = workspace.record_evaluation_run(
        RecordEvaluationRunInput(
            id="eval-001",
            suite_id=suite.id,
            passed=1,
            total=2,
            evidence=["ci://evals/1"],
            runtime="codex/openai/model-a",
        )
    )
    passed = workspace.record_evaluation_run(
        RecordEvaluationRunInput(
            id="eval-002",
            suite_id=suite.id,
            passed=2,
            total=2,
            evidence=["ci://evals/2"],
        )
    )
    assert failed.result == "failure"
    assert passed.result == "success"
    assert [item.id for item in workspace.impacted_evaluation_suites([".agents/reviewer.md"])] == [
        suite.id
    ]
    assert workspace.impacted_evaluation_suites(["src/api.py"]) == []

    finding = workspace.add_review_finding(
        AddReviewFindingInput(
            id="review-001",
            swarm_id="delivery",
            work_id="change",
            pass_id="security",
            severity="high",
            policy="secure-api/v1",
            summary="The endpoint lacks an authorization check.",
            location="src/api.py:42",
        )
    )
    assert finding.status == "open"

    workspace.add_guardrail(
        AddGuardrailInput(
            id="protected-runtime",
            protected_paths=[".env*", "generated/**"],
            denied_commands=["git reset --hard*", "curl *production*"],
        )
    )
    assert workspace.check_guardrails("file-edit", ".env.production").allowed is False
    assert workspace.check_guardrails("file-edit", "src/api.py").allowed is True
    assert workspace.check_guardrails("command", "git reset --hard HEAD").allowed is False

    metrics = workspace.sdlc_metrics()
    assert metrics.evaluation_runs == 2
    assert metrics.evaluation_pass_rate == 50.0
    assert metrics.open_high_findings == 1
    resolved = workspace.decide_review_finding(
        DecideReviewFindingInput(
            id=finding.id,
            decision="resolved",
            actor="security:reviewer",
            reason="Authorization middleware is now enforced.",
        )
    )
    assert resolved.status == "resolved"
    assert resolved.decided_by == "security:reviewer"
    assert workspace.sdlc_metrics().open_high_findings == 0
    assert workspace.validate().ok


def test_trigger_ingestion_is_idempotent_and_rejects_payload_drift(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    workspace.add_trigger(
        AddTriggerInput(
            id="merged-to-deploy",
            event_type="pull-request.merged",
            action="prepare-deployment",
            parameters={"environment": "staging"},
        )
    )
    first = workspace.ingest_trigger_event(
        IngestTriggerEventInput(
            id="event-001",
            event_type="pull-request.merged",
            dedupe_key="github:repo:pr:42:sha:abc",
            payload={"sha": "abc"},
        )
    )
    replay = workspace.ingest_trigger_event(
        IngestTriggerEventInput(
            id="event-replay",
            event_type="pull-request.merged",
            dedupe_key="github:repo:pr:42:sha:abc",
            payload={"sha": "abc"},
        )
    )
    assert first.id == replay.id == "event-001"
    assert first.actions[0]["action"] == "prepare-deployment"

    try:
        workspace.ingest_trigger_event(
            IngestTriggerEventInput(
                id="event-drift",
                event_type="pull-request.merged",
                dedupe_key="github:repo:pr:42:sha:abc",
                payload={"sha": "different"},
            )
        )
    except ValueError as error:
        assert "different payload" in str(error)
    else:  # pragma: no cover - documents the safety invariant
        raise AssertionError("Payload drift reused a dedupe key")


def test_control_band_breach_proposes_a_new_intent(tmp_path: Path, monkeypatch) -> None:
    workspace = _workspace(tmp_path, monkeypatch)
    workspace.add_control_band(
        AddControlBandInput(
            id="api-errors",
            metric="api.5xx-rate",
            mean=1.0,
            standard_deviation=0.5,
            diagnose_sigma=2,
            propose_sigma=3,
        )
    )
    normal = workspace.evaluate_control_band(
        EvaluateControlBandInput(band_id="api-errors", id="sample-001", value=1.5)
    )
    breach = workspace.evaluate_control_band(
        EvaluateControlBandInput(band_id="api-errors", id="sample-002", value=3.0)
    )
    assert normal.level == "normal"
    assert normal.intent_id is None
    assert breach.level == "propose"
    assert breach.intent_id is not None
    intent = workspace.list_intents("draft")[0]
    assert intent.id == breach.intent_id
    assert intent.source == "agora://control-bands/api-errors/findings/sample-002"
    assert workspace.validate().ok


def test_metrics_derive_cycle_rework_and_human_wait_from_events(tmp_path: Path) -> None:
    state = tmp_path / ".agora"
    state.mkdir()
    (state / "project.md").write_text("project", encoding="utf-8")
    service = SdlcService(
        tmp_path,
        now=lambda: datetime(2026, 8, 25, 13, 0, tzinfo=UTC),
    )
    events = [
        EventRecord("2026-08-25T12:00:00Z", "work.created", "actor=a", "work:s/w", "x"),
        EventRecord(
            "2026-08-25T12:05:00Z",
            "work.transitioned",
            "from=implementing to=verifying actor=a",
            "work:s/w",
            "x",
        ),
        EventRecord(
            "2026-08-25T12:10:00Z",
            "work.transitioned",
            "from=verifying to=implementing actor=a",
            "work:s/w",
            "x",
        ),
        EventRecord(
            "2026-08-25T12:20:00Z",
            "work.transitioned",
            "from=implementing to=verifying actor=a",
            "work:s/w",
            "x",
        ),
        EventRecord(
            "2026-08-25T12:25:00Z",
            "approval.added",
            "role=owner actor=h",
            "work:s/w",
            "x",
        ),
        EventRecord(
            "2026-08-25T12:30:00Z",
            "work.transitioned",
            "from=verifying to=completed actor=h",
            "work:s/w",
            "x",
        ),
    ]
    report = service.metrics(events, work_items=1, completed_work_items=1)
    assert report.rework_count == 1
    assert report.first_pass_rate == 0.0
    assert report.average_cycle_seconds == 1800.0
    assert report.average_human_wait_seconds == 300.0


def test_cli_exposes_intent_and_fail_closed_guardrail(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGORA_HOME", str(tmp_path / "home"))
    output = io.StringIO()
    errors = io.StringIO()
    assert main(["init"], cwd=tmp_path, stdout=output, stderr=errors) == 0
    output.seek(0)
    output.truncate(0)
    assert (
        main(
            [
                "intent",
                "add",
                "--id",
                "safe-change",
                "--author",
                "ana",
                "--problem",
                "Unsafe releases",
                "--outcome",
                "Governed releases",
            ],
            cwd=tmp_path,
            stdout=output,
            stderr=errors,
        )
        == 0
    )
    assert json.loads(output.getvalue())["status"] == "draft"
    output.seek(0)
    output.truncate(0)
    assert (
        main(
            [
                "guardrail",
                "add",
                "--id",
                "no-secrets",
                "--protect-path",
                ".env*",
            ],
            cwd=tmp_path,
            stdout=output,
            stderr=errors,
        )
        == 0
    )
    output.seek(0)
    output.truncate(0)
    assert (
        main(
            ["guardrail", "check", "--action", "file-edit", "--target", ".env.local"],
            cwd=tmp_path,
            stdout=output,
            stderr=errors,
        )
        == 1
    )
    assert json.loads(output.getvalue())["ok"] is False
