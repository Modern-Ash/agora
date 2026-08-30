"""Provider-neutral AI-native SDLC records.

The module intentionally does not run an LLM, poll a provider, or execute a shell.  It persists the
contracts that external CI, webhook, monitoring, and agent runners can drive while Agora retains
idempotency, deterministic policy checks, and a Markdown-first audit trail.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from agora.filesystem import assert_slug, atomic_write, filesystem_transaction, write_new
from agora.markdown import (
    MarkdownDocument,
    optional_string_attribute,
    read_markdown,
    record_attribute,
    render_markdown,
    string_attribute,
    strings_attribute,
)
from agora.model import (
    AddControlBandInput,
    AddEvaluationSuiteInput,
    AddGuardrailInput,
    AddReviewFindingInput,
    AddTriggerInput,
    ControlBandFindingRecord,
    ControlBandRecord,
    CreateIntentInput,
    DecideIntentInput,
    DecideReviewFindingInput,
    EvaluateControlBandInput,
    EvaluationRunRecord,
    EvaluationSuiteRecord,
    EventRecord,
    GuardrailDecisionRecord,
    GuardrailRecord,
    IngestTriggerEventInput,
    IntentRecord,
    RecordEvaluationRunInput,
    ReviewFindingRecord,
    SdlcMetricsRecord,
    TriggerEventRecord,
    TriggerRecord,
)


class SdlcService:
    def __init__(self, root: Path, now: Callable[[], datetime] | None = None) -> None:
        self.root = root.resolve()
        self.state = self.root / ".agora"
        self._now = now or (lambda: datetime.now(UTC))

    def _timestamp(self) -> str:
        return self._now().astimezone(UTC).isoformat().replace("+00:00", "Z")

    def _require_project(self) -> None:
        if not (self.state / "project.md").is_file():
            raise FileNotFoundError("Agora project is not initialized")

    # Intent intake -----------------------------------------------------

    def create_intent(self, data: CreateIntentInput) -> IntentRecord:
        self._require_project()
        assert_slug(data.id, "Intent id")
        _require_text(data.author, "Intent author")
        _require_text(data.problem, "Intent problem")
        _require_text(data.outcome, "Intent outcome")
        _require_text_list(data.affected_systems, "Affected systems")
        _require_text_list(data.constraints, "Constraints")
        _require_text_list(data.open_questions, "Open questions")
        if data.source is not None:
            _require_text(data.source, "Intent source")
        record = IntentRecord(
            id=data.id,
            status="draft",
            author=data.author,
            problem=data.problem,
            outcome=data.outcome,
            affected_systems=list(data.affected_systems),
            constraints=list(data.constraints),
            open_questions=list(data.open_questions),
            source=data.source,
            created_at=self._timestamp(),
            decided_by=None,
            decided_at=None,
            decision_reason=None,
            path=str(self.state / "intents" / data.id / "INTENT.md"),
        )
        write_new(Path(record.path), _render_intent(record))
        return record

    def decide_intent(self, data: DecideIntentInput) -> IntentRecord:
        assert_slug(data.id, "Intent id")
        if data.decision not in {"accepted", "rejected"}:
            raise ValueError("Intent decision must be accepted or rejected")
        _require_text(data.actor, "Decision actor")
        _require_text(data.reason, "Decision reason")
        current = self.get_intent(data.id)
        if current.status != "draft":
            raise ValueError(f"Intent {data.id} is already {current.status}")
        decided = replace(
            current,
            status=data.decision,
            decided_by=data.actor,
            decided_at=self._timestamp(),
            decision_reason=data.reason,
        )
        atomic_write(Path(decided.path), _render_intent(decided))
        return decided

    def get_intent(self, intent_id: str) -> IntentRecord:
        assert_slug(intent_id, "Intent id")
        return _load_intent(self.state / "intents" / intent_id / "INTENT.md")

    def list_intents(self, status: str | None = None) -> list[IntentRecord]:
        records = [
            _load_intent(path) for path in sorted((self.state / "intents").glob("*/INTENT.md"))
        ]
        if status is not None:
            if status not in {"draft", "accepted", "rejected"}:
                raise ValueError("Intent status must be draft, accepted, or rejected")
            records = [record for record in records if record.status == status]
        return records

    # Continuous evaluations ------------------------------------------

    def add_evaluation_suite(self, data: AddEvaluationSuiteInput) -> EvaluationSuiteRecord:
        self._require_project()
        assert_slug(data.id, "Evaluation suite id")
        if not data.cases:
            raise ValueError("Evaluation suite requires at least one case")
        _require_text_list(data.cases, "Evaluation cases")
        _require_text_list(data.trigger_paths, "Evaluation trigger paths")
        if len(set(data.cases)) != len(data.cases):
            raise ValueError("Evaluation cases must be unique")
        if isinstance(data.minimum_pass_rate, bool) or not 0 <= data.minimum_pass_rate <= 100:
            raise ValueError("Minimum pass rate must be between 0 and 100")
        record = EvaluationSuiteRecord(
            id=data.id,
            cases=list(data.cases),
            minimum_pass_rate=data.minimum_pass_rate,
            trigger_paths=list(data.trigger_paths),
            created_at=self._timestamp(),
            path=str(self.state / "evaluations" / "suites" / data.id / "SUITE.md"),
        )
        write_new(Path(record.path), _render_evaluation_suite(record))
        return record

    def get_evaluation_suite(self, suite_id: str) -> EvaluationSuiteRecord:
        assert_slug(suite_id, "Evaluation suite id")
        return _load_evaluation_suite(self.state / "evaluations" / "suites" / suite_id / "SUITE.md")

    def list_evaluation_suites(self) -> list[EvaluationSuiteRecord]:
        return [
            _load_evaluation_suite(path)
            for path in sorted((self.state / "evaluations" / "suites").glob("*/SUITE.md"))
        ]

    def impacted_evaluation_suites(self, paths: list[str]) -> list[EvaluationSuiteRecord]:
        _require_text_list(paths, "Changed paths")
        normalized = [path.replace("\\", "/").removeprefix("./") for path in paths]
        return [
            suite
            for suite in self.list_evaluation_suites()
            if any(
                fnmatch.fnmatchcase(path, pattern)
                for path in normalized
                for pattern in suite.trigger_paths
            )
        ]

    def record_evaluation_run(self, data: RecordEvaluationRunInput) -> EvaluationRunRecord:
        assert_slug(data.id, "Evaluation run id")
        suite = self.get_evaluation_suite(data.suite_id)
        if isinstance(data.total, bool) or data.total < 1:
            raise ValueError("Evaluation total must be a positive integer")
        if isinstance(data.passed, bool) or not 0 <= data.passed <= data.total:
            raise ValueError("Evaluation passed count must be between zero and total")
        _require_text_list(data.evidence, "Evaluation evidence")
        pass_rate = round(data.passed * 100 / data.total, 4)
        record = EvaluationRunRecord(
            id=data.id,
            suite_id=suite.id,
            passed=data.passed,
            total=data.total,
            pass_rate=pass_rate,
            result="success" if pass_rate >= suite.minimum_pass_rate else "failure",
            evidence=list(data.evidence),
            runtime=data.runtime,
            created_at=self._timestamp(),
            path=str(self.state / "evaluations" / "runs" / data.id / "RUN.md"),
        )
        write_new(Path(record.path), _render_evaluation_run(record))
        return record

    def list_evaluation_runs(self, suite_id: str | None = None) -> list[EvaluationRunRecord]:
        records = [
            _load_evaluation_run(path)
            for path in sorted((self.state / "evaluations" / "runs").glob("*/RUN.md"))
        ]
        return [record for record in records if suite_id is None or record.suite_id == suite_id]

    # Structured review ------------------------------------------------

    def add_review_finding(self, data: AddReviewFindingInput) -> ReviewFindingRecord:
        self._require_project()
        assert_slug(data.id, "Review finding id")
        assert_slug(data.swarm_id, "Swarm id")
        assert_slug(data.work_id, "Work id")
        assert_slug(data.pass_id, "Review pass id")
        if data.severity not in {"low", "medium", "high", "critical"}:
            raise ValueError("Review severity must be low, medium, high, or critical")
        _require_text(data.policy, "Review policy")
        _require_text(data.summary, "Review summary")
        record = ReviewFindingRecord(
            id=data.id,
            swarm_id=data.swarm_id,
            work_id=data.work_id,
            pass_id=data.pass_id,
            severity=data.severity,
            status="open",
            policy=data.policy,
            summary=data.summary,
            location=data.location,
            created_at=self._timestamp(),
            decided_by=None,
            decided_at=None,
            decision_reason=None,
            path=str(self.state / "reviews" / "findings" / data.id / "FINDING.md"),
        )
        write_new(Path(record.path), _render_review_finding(record))
        return record

    def decide_review_finding(self, data: DecideReviewFindingInput) -> ReviewFindingRecord:
        assert_slug(data.id, "Review finding id")
        if data.decision not in {"resolved", "waived"}:
            raise ValueError("Review finding decision must be resolved or waived")
        _require_text(data.actor, "Review decision actor")
        _require_text(data.reason, "Review decision reason")
        path = self.state / "reviews" / "findings" / data.id / "FINDING.md"
        current = _load_review_finding(path)
        if current.status != "open":
            raise ValueError(f"Review finding {data.id} is already {current.status}")
        decided = replace(
            current,
            status=data.decision,
            decided_by=data.actor,
            decided_at=self._timestamp(),
            decision_reason=data.reason,
        )
        atomic_write(path, _render_review_finding(decided))
        return decided

    def list_review_findings(
        self, swarm_id: str | None = None, work_id: str | None = None
    ) -> list[ReviewFindingRecord]:
        records = [
            _load_review_finding(path)
            for path in sorted((self.state / "reviews" / "findings").glob("*/FINDING.md"))
        ]
        return [
            record
            for record in records
            if (swarm_id is None or record.swarm_id == swarm_id)
            and (work_id is None or record.work_id == work_id)
        ]

    # Deterministic guardrails ----------------------------------------

    def add_guardrail(self, data: AddGuardrailInput) -> GuardrailRecord:
        self._require_project()
        assert_slug(data.id, "Guardrail id")
        _require_text_list(data.protected_paths, "Protected paths")
        _require_text_list(data.denied_commands, "Denied commands")
        if not data.protected_paths and not data.denied_commands:
            raise ValueError("Guardrail requires at least one protected path or denied command")
        record = GuardrailRecord(
            id=data.id,
            protected_paths=list(data.protected_paths),
            denied_commands=list(data.denied_commands),
            created_at=self._timestamp(),
            path=str(self.state / "guardrails" / f"{data.id}.md"),
        )
        write_new(Path(record.path), _render_guardrail(record))
        return record

    def list_guardrails(self) -> list[GuardrailRecord]:
        return [_load_guardrail(path) for path in sorted((self.state / "guardrails").glob("*.md"))]

    def check_guardrails(self, action: str, target: str) -> GuardrailDecisionRecord:
        if action not in {"file-edit", "command"}:
            raise ValueError("Guardrail action must be file-edit or command")
        _require_text(target, "Guardrail target")
        normalized = target.replace("\\", "/").removeprefix("./")
        blockers: list[str] = []
        for guardrail in self.list_guardrails():
            patterns = (
                guardrail.protected_paths if action == "file-edit" else guardrail.denied_commands
            )
            if any(fnmatch.fnmatchcase(normalized, pattern) for pattern in patterns):
                blockers.append(guardrail.id)
        return GuardrailDecisionRecord(
            action=action,
            target=target,
            allowed=not blockers,
            blockers=blockers,
        )

    # Idempotent event triggers ---------------------------------------

    def add_trigger(self, data: AddTriggerInput) -> TriggerRecord:
        self._require_project()
        assert_slug(data.id, "Trigger id")
        _require_text(data.event_type, "Trigger event type")
        _require_text(data.action, "Trigger action")
        _require_string_map(data.parameters, "Trigger parameters")
        record = TriggerRecord(
            id=data.id,
            event_type=data.event_type,
            action=data.action,
            parameters=dict(data.parameters),
            enabled=True,
            created_at=self._timestamp(),
            path=str(self.state / "triggers" / "rules" / f"{data.id}.md"),
        )
        write_new(Path(record.path), _render_trigger(record))
        return record

    def list_triggers(self) -> list[TriggerRecord]:
        return [
            _load_trigger(path) for path in sorted((self.state / "triggers" / "rules").glob("*.md"))
        ]

    def ingest_trigger_event(self, data: IngestTriggerEventInput) -> TriggerEventRecord:
        self._require_project()
        assert_slug(data.id, "Trigger event id")
        _require_text(data.event_type, "Trigger event type")
        _require_text(data.dedupe_key, "Trigger dedupe key")
        _require_string_map(data.payload, "Trigger payload")
        for existing in self.list_trigger_events():
            if existing.dedupe_key == data.dedupe_key:
                expected = _payload_sha256(data.event_type, data.payload)
                if existing.payload_sha256 != expected:
                    raise ValueError("Trigger dedupe key was already used with a different payload")
                return existing
        matches = [
            trigger
            for trigger in self.list_triggers()
            if trigger.enabled and trigger.event_type == data.event_type
        ]
        record = TriggerEventRecord(
            id=data.id,
            event_type=data.event_type,
            dedupe_key=data.dedupe_key,
            payload_sha256=_payload_sha256(data.event_type, data.payload),
            matched_triggers=[trigger.id for trigger in matches],
            actions=[
                {
                    "trigger": trigger.id,
                    "action": trigger.action,
                    "parameters": trigger.parameters,
                }
                for trigger in matches
            ],
            created_at=self._timestamp(),
            path=str(self.state / "triggers" / "events" / data.id / "EVENT.md"),
        )
        write_new(Path(record.path), _render_trigger_event(record, data.payload))
        return record

    def list_trigger_events(self) -> list[TriggerEventRecord]:
        return [
            _load_trigger_event(path)
            for path in sorted((self.state / "triggers" / "events").glob("*/EVENT.md"))
        ]

    # Deterministic control bands -------------------------------------

    def add_control_band(self, data: AddControlBandInput) -> ControlBandRecord:
        self._require_project()
        assert_slug(data.id, "Control band id")
        _require_text(data.metric, "Control band metric")
        if data.standard_deviation <= 0:
            raise ValueError("Control band standard deviation must be positive")
        if data.diagnose_sigma <= 0 or data.propose_sigma <= data.diagnose_sigma:
            raise ValueError("Propose sigma must be greater than positive diagnose sigma")
        record = ControlBandRecord(
            id=data.id,
            metric=data.metric,
            mean=float(data.mean),
            standard_deviation=float(data.standard_deviation),
            diagnose_sigma=float(data.diagnose_sigma),
            propose_sigma=float(data.propose_sigma),
            created_at=self._timestamp(),
            path=str(self.state / "control-bands" / data.id / "BAND.md"),
        )
        write_new(Path(record.path), _render_control_band(record))
        return record

    def get_control_band(self, band_id: str) -> ControlBandRecord:
        assert_slug(band_id, "Control band id")
        return _load_control_band(self.state / "control-bands" / band_id / "BAND.md")

    def list_control_bands(self) -> list[ControlBandRecord]:
        return [
            _load_control_band(path)
            for path in sorted((self.state / "control-bands").glob("*/BAND.md"))
        ]

    def evaluate_control_band(self, data: EvaluateControlBandInput) -> ControlBandFindingRecord:
        assert_slug(data.id, "Control band finding id")
        band = self.get_control_band(data.band_id)
        z_score = abs(float(data.value) - band.mean) / band.standard_deviation
        level = (
            "propose"
            if z_score >= band.propose_sigma
            else "diagnose"
            if z_score >= band.diagnose_sigma
            else "normal"
        )
        intent_id = f"{band.id}-{data.id}" if level == "propose" else None
        path = self.state / "control-bands" / band.id / "findings" / data.id / "FINDING.md"
        finding = ControlBandFindingRecord(
            id=data.id,
            band_id=band.id,
            metric=band.metric,
            value=float(data.value),
            z_score=round(z_score, 6),
            level=level,
            intent_id=intent_id,
            created_at=self._timestamp(),
            path=str(path),
        )
        with filesystem_transaction():
            write_new(path, _render_control_band_finding(finding))
            if intent_id is not None:
                self.create_intent(
                    CreateIntentInput(
                        id=intent_id,
                        author=data.author,
                        problem=(
                            f"Control band {band.id} detected {band.metric} at {data.value:g} "
                            f"({z_score:.2f} sigma from its baseline)."
                        ),
                        outcome=f"Restore {band.metric} to its reviewed control band.",
                        affected_systems=[band.metric],
                        constraints=["Diagnosis and remediation must pass normal Agora gates."],
                        open_questions=["What change caused the control-band breach?"],
                        source=f"agora://control-bands/{band.id}/findings/{data.id}",
                    )
                )
        return finding

    def list_control_band_findings(self) -> list[ControlBandFindingRecord]:
        return [
            _load_control_band_finding(path)
            for path in sorted((self.state / "control-bands").glob("*/findings/*/FINDING.md"))
        ]

    # Lifecycle metrics ------------------------------------------------

    def metrics(
        self,
        events: Iterable[EventRecord],
        *,
        work_items: int,
        completed_work_items: int,
    ) -> SdlcMetricsRecord:
        ordered = sorted(events, key=lambda item: (item.timestamp, item.scope, item.type))
        by_work: dict[str, list[EventRecord]] = defaultdict(list)
        for event in ordered:
            if event.scope.startswith("work:"):
                by_work[event.scope].append(event)
        transition_count = sum(event.type == "work.transitioned" for event in ordered)
        reworked: set[str] = set()
        cycle_seconds: list[float] = []
        human_wait_seconds: list[float] = []
        completed_scopes: set[str] = set()
        for scope, scope_events in by_work.items():
            transitions = [item for item in scope_events if item.type == "work.transitioned"]
            if any(
                "to=implementing" in item.detail
                and ("from=verifying" in item.detail or "from=reviewing" in item.detail)
                for item in transitions
            ):
                reworked.add(scope)
            completed = next(
                (item for item in reversed(transitions) if "to=completed" in item.detail), None
            )
            if completed is not None:
                completed_scopes.add(scope)
                start = scope_events[0]
                cycle_seconds.append(_seconds_between(start.timestamp, completed.timestamp))
            for index, item in enumerate(scope_events):
                if item.type == "work.transitioned" and (
                    "to=verifying" in item.detail or "to=reviewing" in item.detail
                ):
                    decision = next(
                        (
                            candidate
                            for candidate in scope_events[index + 1 :]
                            if candidate.type in {"approval.added", "work.transitioned"}
                        ),
                        None,
                    )
                    if decision is not None:
                        human_wait_seconds.append(
                            _seconds_between(item.timestamp, decision.timestamp)
                        )
        eval_runs = self.list_evaluation_runs()
        findings = self.list_review_findings()
        intent_counts = Counter(record.status for record in self.list_intents())
        band_counts = Counter(record.level for record in self.list_control_band_findings())
        first_pass_rate = (
            round((len(completed_scopes - reworked) * 100) / len(completed_scopes), 4)
            if completed_scopes
            else None
        )
        evaluation_pass_rate = (
            round(sum(run.result == "success" for run in eval_runs) * 100 / len(eval_runs), 4)
            if eval_runs
            else None
        )
        return SdlcMetricsRecord(
            generated_at=self._timestamp(),
            work_items=work_items,
            completed_work_items=completed_work_items,
            transition_count=transition_count,
            rework_count=len(reworked),
            first_pass_rate=first_pass_rate,
            average_cycle_seconds=_average(cycle_seconds),
            average_human_wait_seconds=_average(human_wait_seconds),
            evaluation_runs=len(eval_runs),
            evaluation_pass_rate=evaluation_pass_rate,
            open_high_findings=sum(
                finding.status == "open" and finding.severity in {"high", "critical"}
                for finding in findings
            ),
            intents={key: intent_counts.get(key, 0) for key in ("draft", "accepted", "rejected")},
            control_band_findings={
                key: band_counts.get(key, 0) for key in ("normal", "diagnose", "propose")
            },
        )

    def validate(self) -> list[tuple[str, Path, str]]:
        """Load every SDLC record; callers translate failures to their validation contract."""

        families: list[tuple[str, Iterable[Path], Callable[[Path], object]]] = [
            ("intent.invalid", (self.state / "intents").glob("*/INTENT.md"), _load_intent),
            (
                "evaluation-suite.invalid",
                (self.state / "evaluations" / "suites").glob("*/SUITE.md"),
                _load_evaluation_suite,
            ),
            (
                "evaluation-run.invalid",
                (self.state / "evaluations" / "runs").glob("*/RUN.md"),
                _load_evaluation_run,
            ),
            (
                "review-finding.invalid",
                (self.state / "reviews" / "findings").glob("*/FINDING.md"),
                _load_review_finding,
            ),
            (
                "guardrail.invalid",
                (self.state / "guardrails").glob("*.md"),
                _load_guardrail,
            ),
            (
                "trigger.invalid",
                (self.state / "triggers" / "rules").glob("*.md"),
                _load_trigger,
            ),
            (
                "trigger-event.invalid",
                (self.state / "triggers" / "events").glob("*/EVENT.md"),
                _load_trigger_event,
            ),
            (
                "control-band.invalid",
                (self.state / "control-bands").glob("*/BAND.md"),
                _load_control_band,
            ),
            (
                "control-band-finding.invalid",
                (self.state / "control-bands").glob("*/findings/*/FINDING.md"),
                _load_control_band_finding,
            ),
        ]
        failures: list[tuple[str, Path, str]] = []
        for code, paths, loader in families:
            for path in sorted(paths):
                try:
                    loader(path)
                except Exception as error:
                    failures.append((code, path, str(error)))
        return failures


def _render_intent(record: IntentRecord) -> str:
    return render_markdown(
        MarkdownDocument(
            attributes={
                "schema": "agora/intent/v1",
                "id": record.id,
                "status": record.status,
                "author": record.author,
                "affected-systems": record.affected_systems,
                "constraints": record.constraints,
                "open-questions": record.open_questions,
                "source": record.source,
                "created-at": record.created_at,
                "decided-by": record.decided_by,
                "decided-at": record.decided_at,
                "decision-reason": record.decision_reason,
            },
            body=(
                f"# Intent {record.id}\n\n## Problem\n\n{record.problem}"
                f"\n\n## Proposed outcome\n\n{record.outcome}"
            ),
        )
    )


def _load_intent(path: Path) -> IntentRecord:
    document = _read_schema(path, "agora/intent/v1")
    status = string_attribute(document.attributes, "status")
    if status not in {"draft", "accepted", "rejected"}:
        raise ValueError(f"Unsupported intent status: {status}")
    return IntentRecord(
        id=string_attribute(document.attributes, "id"),
        status=status,  # type: ignore[arg-type]
        author=string_attribute(document.attributes, "author"),
        problem=_section(document.body, "Problem"),
        outcome=_section(document.body, "Proposed outcome"),
        affected_systems=strings_attribute(document.attributes, "affected-systems"),
        constraints=strings_attribute(document.attributes, "constraints"),
        open_questions=strings_attribute(document.attributes, "open-questions"),
        source=optional_string_attribute(document.attributes, "source"),
        created_at=string_attribute(document.attributes, "created-at"),
        decided_by=optional_string_attribute(document.attributes, "decided-by"),
        decided_at=optional_string_attribute(document.attributes, "decided-at"),
        decision_reason=optional_string_attribute(document.attributes, "decision-reason"),
        path=str(path),
    )


def _render_evaluation_suite(record: EvaluationSuiteRecord) -> str:
    return render_markdown(
        MarkdownDocument(
            attributes={
                "schema": "agora/evaluation-suite/v1",
                "id": record.id,
                "cases": record.cases,
                "minimum-pass-rate": record.minimum_pass_rate,
                "trigger-paths": record.trigger_paths,
                "created-at": record.created_at,
            },
            body=(
                f"# Evaluation suite {record.id}\n\n"
                "Runs real accepted tasks against a reviewed outcome contract."
            ),
        )
    )


def _load_evaluation_suite(path: Path) -> EvaluationSuiteRecord:
    document = _read_schema(path, "agora/evaluation-suite/v1")
    rate = document.attributes.get("minimum-pass-rate")
    if isinstance(rate, bool) or not isinstance(rate, int) or not 0 <= rate <= 100:
        raise ValueError("Minimum pass rate must be an integer between 0 and 100")
    return EvaluationSuiteRecord(
        id=string_attribute(document.attributes, "id"),
        cases=strings_attribute(document.attributes, "cases"),
        minimum_pass_rate=rate,
        trigger_paths=strings_attribute(document.attributes, "trigger-paths"),
        created_at=string_attribute(document.attributes, "created-at"),
        path=str(path),
    )


def _render_evaluation_run(record: EvaluationRunRecord) -> str:
    return render_markdown(
        MarkdownDocument(
            attributes={
                "schema": "agora/evaluation-run/v1",
                "id": record.id,
                "suite": record.suite_id,
                "passed": record.passed,
                "total": record.total,
                "pass-rate": record.pass_rate,
                "result": record.result,
                "evidence": record.evidence,
                "runtime": record.runtime,
                "created-at": record.created_at,
            },
            body=(
                f"# Evaluation run {record.id}\n\nResult: {record.result} ({record.pass_rate:g}%)."
            ),
        )
    )


def _load_evaluation_run(path: Path) -> EvaluationRunRecord:
    document = _read_schema(path, "agora/evaluation-run/v1")
    passed = _int_attribute(document, "passed")
    total = _int_attribute(document, "total")
    rate = _number_attribute(document, "pass-rate")
    result = string_attribute(document.attributes, "result")
    if result not in {"success", "failure"}:
        raise ValueError(f"Unsupported evaluation result: {result}")
    if total < 1 or not 0 <= passed <= total:
        raise ValueError("Invalid evaluation counts")
    return EvaluationRunRecord(
        id=string_attribute(document.attributes, "id"),
        suite_id=string_attribute(document.attributes, "suite"),
        passed=passed,
        total=total,
        pass_rate=rate,
        result=result,  # type: ignore[arg-type]
        evidence=strings_attribute(document.attributes, "evidence"),
        runtime=optional_string_attribute(document.attributes, "runtime"),
        created_at=string_attribute(document.attributes, "created-at"),
        path=str(path),
    )


def _render_review_finding(record: ReviewFindingRecord) -> str:
    return render_markdown(
        MarkdownDocument(
            attributes={
                "schema": "agora/review-finding/v1",
                "id": record.id,
                "swarm": record.swarm_id,
                "work": record.work_id,
                "pass": record.pass_id,
                "severity": record.severity,
                "status": record.status,
                "policy": record.policy,
                "location": record.location,
                "created-at": record.created_at,
                "decided-by": record.decided_by,
                "decided-at": record.decided_at,
                "decision-reason": record.decision_reason,
            },
            body=f"# Review finding {record.id}\n\n## Summary\n\n{record.summary}",
        )
    )


def _load_review_finding(path: Path) -> ReviewFindingRecord:
    document = _read_schema(path, "agora/review-finding/v1")
    severity = string_attribute(document.attributes, "severity")
    status = string_attribute(document.attributes, "status")
    if severity not in {"low", "medium", "high", "critical"}:
        raise ValueError(f"Unsupported review severity: {severity}")
    if status not in {"open", "resolved", "waived"}:
        raise ValueError(f"Unsupported review finding status: {status}")
    return ReviewFindingRecord(
        id=string_attribute(document.attributes, "id"),
        swarm_id=string_attribute(document.attributes, "swarm"),
        work_id=string_attribute(document.attributes, "work"),
        pass_id=string_attribute(document.attributes, "pass"),
        severity=severity,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        policy=string_attribute(document.attributes, "policy"),
        summary=_section(document.body, "Summary"),
        location=optional_string_attribute(document.attributes, "location"),
        created_at=string_attribute(document.attributes, "created-at"),
        decided_by=optional_string_attribute(document.attributes, "decided-by"),
        decided_at=optional_string_attribute(document.attributes, "decided-at"),
        decision_reason=optional_string_attribute(document.attributes, "decision-reason"),
        path=str(path),
    )


def _render_guardrail(record: GuardrailRecord) -> str:
    return render_markdown(
        MarkdownDocument(
            attributes={
                "schema": "agora/guardrail/v1",
                "id": record.id,
                "protected-paths": record.protected_paths,
                "denied-commands": record.denied_commands,
                "created-at": record.created_at,
            },
            body=(
                f"# Guardrail {record.id}\n\n"
                "Deterministic pre-action policy for external runtime hooks."
            ),
        )
    )


def _load_guardrail(path: Path) -> GuardrailRecord:
    document = _read_schema(path, "agora/guardrail/v1")
    return GuardrailRecord(
        id=string_attribute(document.attributes, "id"),
        protected_paths=strings_attribute(document.attributes, "protected-paths"),
        denied_commands=strings_attribute(document.attributes, "denied-commands"),
        created_at=string_attribute(document.attributes, "created-at"),
        path=str(path),
    )


def _render_trigger(record: TriggerRecord) -> str:
    return render_markdown(
        MarkdownDocument(
            attributes={
                "schema": "agora/trigger/v1",
                "id": record.id,
                "event-type": record.event_type,
                "action": record.action,
                "parameters": record.parameters,
                "enabled": record.enabled,
                "created-at": record.created_at,
            },
            body=(
                f"# Trigger {record.id}\n\n"
                "Routes one durable external event to a governed action intent."
            ),
        )
    )


def _load_trigger(path: Path) -> TriggerRecord:
    document = _read_schema(path, "agora/trigger/v1")
    enabled = document.attributes.get("enabled")
    if not isinstance(enabled, bool):
        raise ValueError("Trigger enabled must be Boolean")
    return TriggerRecord(
        id=string_attribute(document.attributes, "id"),
        event_type=string_attribute(document.attributes, "event-type"),
        action=string_attribute(document.attributes, "action"),
        parameters=record_attribute(document.attributes, "parameters"),
        enabled=enabled,
        created_at=string_attribute(document.attributes, "created-at"),
        path=str(path),
    )


def _render_trigger_event(record: TriggerEventRecord, payload: dict[str, str]) -> str:
    return render_markdown(
        MarkdownDocument(
            attributes={
                "schema": "agora/trigger-event/v1",
                "id": record.id,
                "event-type": record.event_type,
                "dedupe-key": record.dedupe_key,
                "payload-sha256": record.payload_sha256,
                "matched-triggers": record.matched_triggers,
                "actions": record.actions,
                "created-at": record.created_at,
            },
            body=(
                f"# Trigger event {record.id}\n\n## Payload\n\n```json\n"
                f"{json.dumps(payload, indent=2, sort_keys=True)}\n```"
            ),
        )
    )


def _load_trigger_event(path: Path) -> TriggerEventRecord:
    document = _read_schema(path, "agora/trigger-event/v1")
    actions = document.attributes.get("actions")
    if not isinstance(actions, list) or any(not isinstance(item, dict) for item in actions):
        raise ValueError("Trigger event actions must be an object array")
    return TriggerEventRecord(
        id=string_attribute(document.attributes, "id"),
        event_type=string_attribute(document.attributes, "event-type"),
        dedupe_key=string_attribute(document.attributes, "dedupe-key"),
        payload_sha256=string_attribute(document.attributes, "payload-sha256"),
        matched_triggers=strings_attribute(document.attributes, "matched-triggers"),
        actions=actions,
        created_at=string_attribute(document.attributes, "created-at"),
        path=str(path),
    )


def _render_control_band(record: ControlBandRecord) -> str:
    return render_markdown(
        MarkdownDocument(
            attributes={
                "schema": "agora/control-band/v1",
                "id": record.id,
                "metric": record.metric,
                "mean": record.mean,
                "standard-deviation": record.standard_deviation,
                "diagnose-sigma": record.diagnose_sigma,
                "propose-sigma": record.propose_sigma,
                "created-at": record.created_at,
            },
            body=(
                f"# Control band {record.id}\n\n"
                "Detection is deterministic; diagnosis remains governed agent work."
            ),
        )
    )


def _load_control_band(path: Path) -> ControlBandRecord:
    document = _read_schema(path, "agora/control-band/v1")
    record = ControlBandRecord(
        id=string_attribute(document.attributes, "id"),
        metric=string_attribute(document.attributes, "metric"),
        mean=_number_attribute(document, "mean"),
        standard_deviation=_number_attribute(document, "standard-deviation"),
        diagnose_sigma=_number_attribute(document, "diagnose-sigma"),
        propose_sigma=_number_attribute(document, "propose-sigma"),
        created_at=string_attribute(document.attributes, "created-at"),
        path=str(path),
    )
    if record.standard_deviation <= 0 or record.propose_sigma <= record.diagnose_sigma:
        raise ValueError("Invalid control band thresholds")
    return record


def _render_control_band_finding(record: ControlBandFindingRecord) -> str:
    return render_markdown(
        MarkdownDocument(
            attributes={
                "schema": "agora/control-band-finding/v1",
                "id": record.id,
                "band": record.band_id,
                "metric": record.metric,
                "value": record.value,
                "z-score": record.z_score,
                "level": record.level,
                "intent": record.intent_id,
                "created-at": record.created_at,
            },
            body=f"# Control-band finding {record.id}\n\nLevel: {record.level}.",
        )
    )


def _load_control_band_finding(path: Path) -> ControlBandFindingRecord:
    document = _read_schema(path, "agora/control-band-finding/v1")
    level = string_attribute(document.attributes, "level")
    if level not in {"normal", "diagnose", "propose"}:
        raise ValueError(f"Unsupported control-band level: {level}")
    return ControlBandFindingRecord(
        id=string_attribute(document.attributes, "id"),
        band_id=string_attribute(document.attributes, "band"),
        metric=string_attribute(document.attributes, "metric"),
        value=_number_attribute(document, "value"),
        z_score=_number_attribute(document, "z-score"),
        level=level,  # type: ignore[arg-type]
        intent_id=optional_string_attribute(document.attributes, "intent"),
        created_at=string_attribute(document.attributes, "created-at"),
        path=str(path),
    )


def _read_schema(path: Path, schema: str) -> MarkdownDocument:
    document = read_markdown(path)
    actual = string_attribute(document.attributes, "schema")
    if actual != schema:
        raise ValueError(f"Expected schema {schema}, found {actual}")
    return document


def _section(body: str, title: str) -> str:
    marker = f"## {title}\n"
    if marker not in body:
        raise ValueError(f"Missing section: {title}")
    remainder = body.split(marker, 1)[1]
    value = remainder.split("\n## ", 1)[0].strip()
    return _require_text(value, title)


def _require_text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()


def _require_text_list(values: list[str], label: str) -> None:
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValueError(f"{label} must contain non-empty strings")


def _require_string_map(values: dict[str, str], label: str) -> None:
    if any(
        not isinstance(key, str)
        or not key.strip()
        or not isinstance(value, str)
        or not value.strip()
        for key, value in values.items()
    ):
        raise ValueError(f"{label} must contain non-empty string keys and values")


def _number_attribute(document: MarkdownDocument, key: str) -> float:
    value = document.attributes.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Expected numeric attribute: {key}")
    return float(value)


def _int_attribute(document: MarkdownDocument, key: str) -> int:
    value = document.attributes.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"Expected integer attribute: {key}")
    return value


def _payload_sha256(event_type: str, payload: dict[str, str]) -> str:
    encoded = json.dumps(
        {"event-type": event_type, "payload": payload},
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _seconds_between(start: str, end: str) -> float:
    first = datetime.fromisoformat(start.replace("Z", "+00:00"))
    last = datetime.fromisoformat(end.replace("Z", "+00:00"))
    return max(0.0, (last - first).total_seconds())


def _average(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None
