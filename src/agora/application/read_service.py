"""Application-service read boundary over the existing Agora workspace facade."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeVar

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

from agora.application.dto import (
    ActivityEntry,
    ActorSummary,
    ApprovalSummary,
    ArtifactSummary,
    ClarificationsProjection,
    ClarificationSummary,
    EvidenceSummary,
    GateBlockerSummary,
    GateDecisionOptionsProjection,
    GateDecisionOptionSummary,
    GateSummary,
    LifecycleProjection,
    MethodStateSummary,
    MethodSummary,
    MetricWindowSummary,
    ProjectOverview,
    SessionProvenanceSummary,
    SessionSummary,
    SpecificationRevisionDetail,
    SpecificationRevisionSummary,
    SpecificationSummary,
    SwarmSummary,
    TraceabilitySummary,
    TransitionSummary,
    UsageSummaryProjection,
    WorkControlProjection,
    WorkInspection,
    WorkInspectionBlocker,
    WorkInspectionNotModified,
    WorkInspectionTransition,
    WorkItemDetail,
    WorkItemSummary,
)
from agora.application.errors import (
    ConcurrentDurableEditError,
    InvalidDurableStateError,
    InvalidReadQueryError,
    ProjectNotFoundError,
    ReadResourceNotFoundError,
)
from agora.application.extensions import (
    FlavorProjectContext,
    FlavorProjection,
    FlavorProjectionContext,
    FlavorProjectionContribution,
    FlavorProjectionProvider,
)
from agora.application.queries import (
    ActivityFilters,
    ActorFilters,
    SessionFilters,
    SwarmFilters,
    WorkItemFilters,
)
from agora.filesystem import assert_slug
from agora.model import (
    ActivityRecord,
    ActorRecord,
    ApprovalRecord,
    ArtifactRecord,
    EvidenceRecord,
    GateBlockerRecord,
    GatePolicy,
    MethodContract,
    SessionRecord,
    SwarmRecord,
    TransitionAssessmentRecord,
    WorkRecord,
)
from agora.workspace import AgoraWorkspace

ReadResult = TypeVar("ReadResult")

_INSPECTION_TRANSITION_LIMIT = 8
_INSPECTION_BLOCKER_LIMIT = 8
_INSPECTION_ROLE_LIMIT = 8
_INSPECTION_ARTIFACT_LIMIT = 12
_INSPECTION_REFERENCE_LIMIT = 4
_INSPECTION_TEXT_LIMIT = 240
_FLAVOR_PROJECTION_LIMIT = 1_000_000
_PROJECTION_SECTION = re.compile(r"[A-Za-z][A-Za-z0-9._-]{0,99}\Z")
_PROJECTION_SCHEMA = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,199}\Z")
_OPAQUE_SELECTION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}\Z")
_EMBEDDED_LOCATION = re.compile(
    r"(?:\b(?:https?|file|repo)://[^\s<>\"']+)"
    r"|(?<![A-Za-z0-9._-])(?:~?/|\.{1,2}/|\\\\|[A-Za-z]:[\\/])\S*",
    re.IGNORECASE,
)
_SECRET_VALUE = re.compile(
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    r"|\b(?:sk|gh[pousr])_[A-Za-z0-9_-]{8,}"
    r"|\bgithub_pat_[A-Za-z0-9_]{8,}"
    r"|\bglpat-[A-Za-z0-9_-]{8,}"
    r"|\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"
    r"|bearer\s+\S+",
    re.IGNORECASE,
)
_FORBIDDEN_PROJECTION_KEYS = {
    "accesskey",
    "accesstoken",
    "apikey",
    "authorization",
    "credential",
    "credentials",
    "cwd",
    "endpoint",
    "endpointurl",
    "filesystempath",
    "password",
    "path",
    "privatekey",
    "projectpath",
    "root",
    "secret",
    "secrets",
    "token",
    "url",
}
_RESERVED_PROJECTION_SECTIONS = {
    "schema",
    "generated_at",
    "project",
    "lifecycle",
    "clarifications",
    "presentation",
}


class AgoraReadService:
    """Expose versioned read DTOs without moving or duplicating workspace rules."""

    def __init__(
        self,
        workspace: AgoraWorkspace,
        *,
        flavor_projectors: Iterable[FlavorProjectionProvider] = (),
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._workspace = workspace
        self._now = now or (lambda: datetime.now(UTC))
        self._flavor_projectors: dict[str, FlavorProjectionProvider] = {}
        self._flavor_projection_validators: dict[str, Draft202012Validator] = {}
        for projector in flavor_projectors:
            self._register_flavor_projector(projector)

    @classmethod
    def from_path(
        cls,
        cwd: Path | str,
        *,
        flavor_projectors: Iterable[FlavorProjectionProvider] = (),
    ) -> AgoraReadService:
        return cls(AgoraWorkspace(cwd=cwd), flavor_projectors=flavor_projectors)

    def project_overview(self) -> ProjectOverview:
        def read() -> ProjectOverview:
            configuration = self._workspace.show_project()
            status = self._workspace.status()
            return ProjectOverview(
                project=configuration.project,
                version=configuration.version,
                integration=configuration.integration,
                provider=configuration.provider,
                model=configuration.model,
                default_method=configuration.default_method,
                max_delegation_depth=configuration.max_delegation_depth,
                created_at=configuration.created_at,
                gate_decision_ttl_seconds=configuration.gate_decision_ttl_seconds,
                branch=status.branch,
                counts=status.counts,
                swarm_statuses=status.swarm_statuses,
                work_states=status.work_states,
                work_operational_statuses=status.work_operational_statuses,
                delegation_statuses=status.delegation_statuses,
                session_statuses=status.session_statuses,
                tool_run_statuses=status.tool_run_statuses,
                attention=status.attention,
            )

        return self._read("project overview", read)

    def list_actors(self, filters: ActorFilters | None = None) -> tuple[ActorSummary, ...]:
        query = filters or ActorFilters()
        if query.scope not in {"all", "user", "project"}:
            raise InvalidReadQueryError("Actor scope must be all, user, or project")
        return self._read(
            "actors",
            lambda: tuple(
                self._actor_summary(record) for record in self._workspace.list_actors(query.scope)
            ),
        )

    def list_swarms(self, filters: SwarmFilters | None = None) -> tuple[SwarmSummary, ...]:
        query = filters or SwarmFilters()
        return self._read(
            "swarms",
            lambda: tuple(
                self._swarm_summary(record) for record in self._workspace.list_swarms(query.status)
            ),
        )

    def get_swarm(self, swarm_id: str) -> SwarmSummary:
        self._require_slug(swarm_id, "Swarm id")
        return self._read(
            f"swarm {swarm_id}",
            lambda: self._swarm_summary(self._workspace.show_swarm(swarm_id)),
        )

    def list_sessions(self, filters: SessionFilters | None = None) -> tuple[SessionSummary, ...]:
        query = filters or SessionFilters()
        return self._read(
            "sessions",
            lambda: tuple(
                self._session_summary(record)
                for record in self._workspace.list_sessions(query.status)
            ),
        )

    def get_session(self, session_id: str) -> SessionSummary:
        self._require_slug(session_id, "Session id")
        return self._read(
            f"session {session_id}",
            lambda: self._session_summary(self._workspace.show_session(session_id)),
        )

    def get_method(self, swarm_id: str) -> MethodSummary:
        self._require_slug(swarm_id, "Swarm id")
        return self._read(
            f"method for swarm {swarm_id}",
            lambda: self._method_summary(self._workspace.method_contract(swarm_id)),
        )

    def list_work_items(
        self, filters: WorkItemFilters | None = None
    ) -> tuple[WorkItemSummary, ...]:
        query = filters or WorkItemFilters()
        if query.swarm_id is not None:
            self._require_slug(query.swarm_id, "Swarm id")
        return self._read(
            "work items",
            lambda: tuple(
                self._work_summary(record)
                for record in self._workspace.list_work(
                    query.swarm_id,
                    query.state,
                    query.operational_status,
                )
            ),
        )

    def get_work_item(self, swarm_id: str, work_id: str) -> WorkItemDetail:
        self._require_work_slugs(swarm_id, work_id)

        def read() -> WorkItemDetail:
            work = self._workspace.show_work(swarm_id, work_id)
            artifacts, evidence, approvals = self._work_materials(swarm_id, work_id)
            return WorkItemDetail(
                id=work.id,
                swarm_id=work.swarm_id,
                title=work.title,
                description=work.description,
                state=work.state,
                operational_status=work.operational_status,
                status_reason=work.status_reason,
                status_by=work.status_by,
                status_at=work.status_at,
                acceptance_criteria=work.acceptance_criteria,
                satisfied_criteria=work.satisfied_criteria,
                criterion_statuses=work.criterion_statuses,
                required_artifacts=work.required_artifacts,
                artifact_kinds=work.artifact_kinds,
                evidence_results=work.evidence_results,
                approval_roles=work.approval_roles,
                child_work_refs=work.child_work_refs,
                budget_limits=work.budget_limits,
                delegation_id=work.delegation_id,
                parent_work_ref=work.parent_work_ref,
                artifacts=artifacts,
                evidence=evidence,
                approvals=approvals,
            )

        return self._read(f"work item {swarm_id}/{work_id}", read)

    def activity(self, filters: ActivityFilters | None = None) -> tuple[ActivityEntry, ...]:
        query = filters or ActivityFilters()
        if query.swarm_id is not None:
            self._require_slug(query.swarm_id, "Swarm id")
        if query.work_id is not None:
            self._require_slug(query.work_id, "Work id")
        if query.limit < 1:
            raise InvalidReadQueryError("Activity limit must be a positive integer")
        if query.work_id is not None and query.swarm_id is None:
            raise InvalidReadQueryError("Work activity filters require a swarm id")
        return self._read(
            "activity",
            lambda: tuple(
                self.activity_entry(record)
                for record in self._workspace.list_activity(
                    actor_id=query.actor_id,
                    swarm_id=query.swarm_id,
                    work_id=query.work_id,
                    session_id=query.session_id,
                    tool_run_id=query.tool_run_id,
                    type_=query.type,
                    limit=query.limit,
                )
            ),
        )

    def lifecycle(self, swarm_id: str, work_id: str) -> LifecycleProjection:
        self._require_work_slugs(swarm_id, work_id)

        def read() -> LifecycleProjection:
            work = self._workspace.show_work(swarm_id, work_id)
            assessment = self._workspace.inspect_work_lifecycle(swarm_id, work_id)
            contract = assessment.method
            transitions = tuple(self._transition_summary(item) for item in assessment.transitions)
            available = tuple(
                dict.fromkeys(
                    transition.target
                    for transition in transitions
                    if transition.source == work.state
                )
            )
            gate_blockers: dict[str, tuple[GateBlockerSummary, ...]] = {}
            assessed_gates: set[str] = set()
            for transition in transitions:
                if transition.gate_id is not None and transition.source == work.state:
                    assessed_gates.add(transition.gate_id)
                    gate_blockers[transition.gate_id] = transition.blockers
            return LifecycleProjection(
                swarm_id=assessment.swarm_id,
                work_id=work.id,
                method=contract.id,
                current_state=work.state,
                operational_status=work.operational_status,
                terminal_state=contract.terminal_state,
                available_transitions=available,
                acceptance_criteria=work.acceptance_criteria,
                satisfied_criteria=work.satisfied_criteria,
                criterion_statuses=work.criterion_statuses,
                required_artifacts=work.required_artifacts,
                artifact_kinds=work.artifact_kinds,
                evidence_results=work.evidence_results,
                approval_roles=work.approval_roles,
                states=self._method_states(contract),
                transitions=transitions,
                gates=tuple(
                    self._gate_summary(
                        gate,
                        blockers=gate_blockers.get(gate_id, ()),
                        assessed=gate_id in assessed_gates,
                    )
                    for gate_id, gate in contract.gates.items()
                ),
            )

        return self._read(f"lifecycle {swarm_id}/{work_id}", read)

    def artifacts(self, swarm_id: str, work_id: str) -> tuple[ArtifactSummary, ...]:
        self._require_work_slugs(swarm_id, work_id)

        def read() -> tuple[ArtifactSummary, ...]:
            return tuple(
                self._artifact_summary(record)
                for record in self._workspace.list_work_artifacts(swarm_id, work_id)
            )

        return self._read(f"artifacts {swarm_id}/{work_id}", read)

    def evidence(self, swarm_id: str, work_id: str) -> tuple[EvidenceSummary, ...]:
        self._require_work_slugs(swarm_id, work_id)
        return self._read(
            f"evidence {swarm_id}/{work_id}",
            lambda: tuple(
                self._evidence_summary(record)
                for record in self._workspace.list_work_evidence(swarm_id, work_id)
            ),
        )

    def approvals(self, swarm_id: str, work_id: str) -> tuple[ApprovalSummary, ...]:
        self._require_work_slugs(swarm_id, work_id)
        return self._read(
            f"approvals {swarm_id}/{work_id}",
            lambda: tuple(
                self._approval_summary(record)
                for record in self._workspace.list_work_approvals(swarm_id, work_id)
            ),
        )

    def usage_summary(self, swarm_id: str, work_id: str) -> UsageSummaryProjection:
        self._require_work_slugs(swarm_id, work_id)

        def read() -> UsageSummaryProjection:
            record = self._workspace.summarize_usage(swarm_id, work_id)
            return UsageSummaryProjection(
                swarm_id=record.swarm_id,
                work_id=record.work_id,
                budget_limits=None if record.budget_limits is None else dict(record.budget_limits),
                consumed=dict(record.consumed),
                remaining=None if record.remaining is None else dict(record.remaining),
                records=record.records,
                consumed_measurement=dict(record.consumed_measurement),
            )

        return self._read(f"usage {swarm_id}/{work_id}", read)

    @staticmethod
    def _metric_timestamp(value: str, label: str) -> datetime:
        if not isinstance(value, str) or not value:
            raise InvalidReadQueryError(f"{label} must be a timezone-aware timestamp")
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise InvalidReadQueryError(f"{label} must be an ISO-8601 timestamp") from error
        if parsed.tzinfo is None:
            raise InvalidReadQueryError(f"{label} must be timezone-aware")
        return parsed.astimezone(UTC)

    @staticmethod
    def _metric_time(value: datetime) -> str:
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _metric_source_ref(kind: str, *parts: str | None) -> str:
        safe = [str(part).replace(":", "_") for part in parts if part]
        return f"{kind}:" + ":".join(safe)

    def metric_windows(
        self,
        swarm_id: str,
        work_id: str,
        *,
        start: str,
        end: str,
        keys: tuple[str, ...] = (),
    ) -> tuple[MetricWindowSummary, ...]:
        """Derive provider-neutral metric facts from existing durable Core records."""

        self._require_work_slugs(swarm_id, work_id)
        start_at = self._metric_timestamp(start, "Metric window start")
        end_at = self._metric_timestamp(end, "Metric window end")
        if start_at > end_at:
            raise InvalidReadQueryError("Metric window start must not be after end")

        work = self.get_work_item(swarm_id, work_id)
        sessions = tuple(
            item
            for item in self.list_sessions()
            if item.swarm_id == swarm_id and item.work_id == work_id
        )
        usage_records = tuple(self._workspace.list_usage(swarm_id, work_id))

        def within(timestamp: str) -> bool:
            value = self._metric_timestamp(timestamp, "Durable record timestamp")
            return start_at <= value <= end_at

        artifacts = tuple(item for item in work.artifacts if within(item.timestamp))
        evidence = tuple(item for item in work.evidence if within(item.timestamp))
        approvals = tuple(item for item in work.approvals if within(item.timestamp))
        window_sessions = tuple(item for item in sessions if within(item.created_at))
        window_usage = tuple(item for item in usage_records if within(item.created_at))

        base: dict[str, tuple[int, tuple[str, ...]]] = {
            "artifacts.count": (
                len(artifacts),
                tuple(
                    self._metric_source_ref(
                        "artifact", item.content_sha256, item.kind, item.timestamp
                    )
                    for item in artifacts
                ),
            ),
            "evidence.count": (
                len(evidence),
                tuple(
                    self._metric_source_ref("evidence", item.type, item.timestamp)
                    for item in evidence
                ),
            ),
            "evidence.success.count": (
                sum(item.result == "success" for item in evidence),
                tuple(
                    self._metric_source_ref("evidence", item.type, item.timestamp)
                    for item in evidence
                    if item.result == "success"
                ),
            ),
            "evidence.failure.count": (
                sum(item.result == "failure" for item in evidence),
                tuple(
                    self._metric_source_ref("evidence", item.type, item.timestamp)
                    for item in evidence
                    if item.result == "failure"
                ),
            ),
            "approvals.count": (
                len(approvals),
                tuple(
                    self._metric_source_ref("approval", item.role, item.timestamp)
                    for item in approvals
                ),
            ),
            "sessions.count": (
                len(window_sessions),
                tuple(self._metric_source_ref("session", item.id) for item in window_sessions),
            ),
            "sessions.completed.count": (
                sum(item.status == "completed" for item in window_sessions),
                tuple(
                    self._metric_source_ref("session", item.id)
                    for item in window_sessions
                    if item.status == "completed"
                ),
            ),
        }

        usage_dimensions = set(work.budget_limits or {})
        for record in usage_records:
            usage_dimensions.update(record.amounts)
        available_keys = set(base) | {f"usage.{dimension}" for dimension in usage_dimensions}
        selected = tuple(sorted(available_keys)) if not keys else tuple(dict.fromkeys(keys))
        start_text, end_text = self._metric_time(start_at), self._metric_time(end_at)

        results: list[MetricWindowSummary] = []
        rank = {"measured": 2, "provider-reported": 1, "unknown": 0}
        basis = {value: name for name, value in rank.items()}
        for key in selected:
            if key in base:
                value, refs = base[key]
                results.append(
                    MetricWindowSummary(
                        key=key,
                        start=start_text,
                        end=end_text,
                        value=value,
                        count=value,
                        status="available",
                        source_refs=refs,
                    )
                )
                continue
            if not key.startswith("usage.") or key not in available_keys:
                results.append(
                    MetricWindowSummary(
                        key=key,
                        start=start_text,
                        end=end_text,
                        value=None,
                        count=0,
                        status="unavailable",
                    )
                )
                continue
            dimension = key.removeprefix("usage.")
            contributors = tuple(record for record in window_usage if dimension in record.amounts)
            value = sum(record.amounts[dimension] for record in contributors)
            levels = [rank[record.measurement or "unknown"] for record in contributors]
            measurement = basis[min(levels)] if levels else None
            status = "partial" if measurement == "unknown" and contributors else "available"
            results.append(
                MetricWindowSummary(
                    key=key,
                    start=start_text,
                    end=end_text,
                    value=value,
                    count=len(contributors),
                    status=status,
                    source_refs=tuple(
                        self._metric_source_ref("usage", record.id) for record in contributors
                    ),
                    measurement=measurement,
                )
            )
        return tuple(results)

    def work_traceability(self, swarm_id: str, work_id: str) -> TraceabilitySummary:
        self._require_work_slugs(swarm_id, work_id)

        def read() -> TraceabilitySummary:
            record = self._workspace.work_traceability(swarm_id, work_id)
            return TraceabilitySummary(
                swarm_id=str(record["swarm"]),
                work_id=str(record["work"]),
                state=str(record["state"]),
                stale=bool(record["stale"]),
                criteria=tuple(record["criteria"]),  # type: ignore[arg-type]
                clarifications=record["clarifications"],  # type: ignore[arg-type]
                gherkin=tuple(record["gherkin"]),  # type: ignore[arg-type]
                consistency=tuple(record["consistency"]),  # type: ignore[arg-type]
                artifacts=self.artifacts(swarm_id, work_id),
                evidence=self.evidence(swarm_id, work_id),
                activity=self.activity(
                    ActivityFilters(swarm_id=swarm_id, work_id=work_id, limit=500)
                ),
            )

        return self._read(f"traceability {swarm_id}/{work_id}", read)

    def clarifications(self, swarm_id: str, work_id: str) -> ClarificationsProjection:
        self._require_work_slugs(swarm_id, work_id)

        def read() -> ClarificationsProjection:
            records = tuple(
                ClarificationSummary(
                    id=str(record["id"]),
                    status=str(record["status"]),
                    question=str(record["question"]),
                    answer=(str(record["answer"]) if record["answer"] is not None else None),
                    requested_by=str(record["requested_by"]),
                    answered_by=(
                        str(record["answered_by"]) if record["answered_by"] is not None else None
                    ),
                    created_at=str(record["created_at"]),
                )
                for record in self._workspace.work_clarifications(swarm_id, work_id)
            )
            return ClarificationsProjection(
                swarm_id=swarm_id,
                work_id=work_id,
                open=tuple(item for item in records if item.status == "open"),
                resolved=tuple(item for item in records if item.status == "resolved"),
            )

        return self._read(f"clarifications {swarm_id}/{work_id}", read)

    def flavor_projection(
        self,
        projection_schema: str,
        selection_id: str,
        swarm_id: str,
        work_id: str,
    ) -> FlavorProjection:
        """Compose one coherent Core snapshot with a registered flavor projection."""

        self._require_work_slugs(swarm_id, work_id)
        if (
            not isinstance(projection_schema, str)
            or _PROJECTION_SCHEMA.fullmatch(projection_schema) is None
            or ".." in projection_schema
        ):
            raise InvalidReadQueryError("Projection schema is invalid")
        if not isinstance(selection_id, str) or _OPAQUE_SELECTION.fullmatch(selection_id) is None:
            raise InvalidReadQueryError("Selection id must be an opaque identifier")
        projector = self._flavor_projectors.get(projection_schema)
        if projector is None:
            raise ReadResourceNotFoundError(
                f"No flavor projector is registered for schema {projection_schema}"
            )

        def assemble() -> FlavorProjection:
            context = self._flavor_projection_context(swarm_id, work_id)
            try:
                contribution = projector.project(context)
            except Exception as error:
                raise InvalidDurableStateError("Registered flavor projector failed") from error
            sections, presentation = self._validate_flavor_contribution(projector, contribution)
            lifecycle = self._lifecycle_projection_section(context.lifecycle)
            clarifications = self._clarifications_projection_section(context.clarifications)
            identity = {
                "selection_id": selection_id,
                "id": context.project.id,
                "swarm_id": swarm_id,
                "work_id": work_id,
            }
            snapshot_material = {
                "schema": projection_schema,
                "project": identity,
                **sections,
                "lifecycle": lifecycle,
                "clarifications": clarifications,
                "presentation": presentation,
            }
            snapshot = hashlib.sha256(
                json.dumps(
                    snapshot_material,
                    allow_nan=False,
                    ensure_ascii=True,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("ascii")
            ).hexdigest()
            projection = FlavorProjection(
                schema=projection_schema,
                generated_at=self._timestamp(),
                project={**identity, "snapshot": snapshot},
                sections=sections,
                lifecycle=lifecycle,
                clarifications=clarifications,
                presentation=presentation,
            )
            payload = projection.to_dict()
            self._validate_safe_projection(payload)
            try:
                self._flavor_projection_validators[projection_schema].validate(payload)
            except ValidationError as error:
                raise InvalidDurableStateError(
                    "Flavor projector output does not match its registered schema"
                ) from error
            return projection

        def read() -> FlavorProjection:
            with self._workspace.consistent_read("flavor-projection"):
                for _ in range(3):
                    before = self._workspace.work_control_read_set_sha256(swarm_id, work_id)
                    projection = assemble()
                    after = self._workspace.work_control_read_set_sha256(swarm_id, work_id)
                    if before == after:
                        return projection
                raise ConcurrentDurableEditError(
                    "Durable flavor projection material changed during three read attempts",
                    details={"stale_reason": "external-edit"},
                )

        return self._read(f"flavor projection {swarm_id}/{work_id}", read)

    def _register_flavor_projector(self, projector: FlavorProjectionProvider) -> None:
        projection_schema = getattr(projector, "projection_schema", None)
        schema_document = getattr(projector, "projection_schema_document", None)
        required_sections = getattr(projector, "required_sections", None)
        if (
            not isinstance(projection_schema, str)
            or _PROJECTION_SCHEMA.fullmatch(projection_schema) is None
            or ".." in projection_schema
        ):
            raise InvalidReadQueryError("Flavor projector schema is invalid")
        if not isinstance(required_sections, tuple) or not required_sections:
            raise InvalidReadQueryError("Flavor projector must declare required sections")
        if len(set(required_sections)) != len(required_sections):
            raise InvalidReadQueryError("Flavor projector section names must be unique")
        for section in required_sections:
            if not isinstance(section, str) or _PROJECTION_SECTION.fullmatch(section) is None:
                raise InvalidReadQueryError("Flavor projector section name is invalid")
            if section in _RESERVED_PROJECTION_SECTIONS:
                raise InvalidReadQueryError(
                    f"Flavor projector cannot own reserved section {section}"
                )
        if projection_schema in self._flavor_projectors:
            raise InvalidReadQueryError(
                f"Flavor projector schema is already registered: {projection_schema}"
            )
        if not isinstance(schema_document, Mapping):
            raise InvalidReadQueryError("Flavor projector must declare a JSON Schema document")
        try:
            serialized_schema = json.loads(json.dumps(schema_document, allow_nan=False))
        except (TypeError, ValueError) as error:
            raise InvalidReadQueryError(
                "Flavor projector JSON Schema is not JSON-compatible"
            ) from error
        declared_schema = (
            serialized_schema.get("properties", {}).get("schema", {}).get("const")
            if isinstance(serialized_schema, dict)
            else None
        )
        if declared_schema != projection_schema:
            raise InvalidReadQueryError("Flavor projector JSON Schema does not match its schema id")
        self._reject_remote_schema_references(serialized_schema)
        try:
            Draft202012Validator.check_schema(serialized_schema)
            validator = Draft202012Validator(serialized_schema)
        except SchemaError as error:
            raise InvalidReadQueryError("Flavor projector JSON Schema is invalid") from error
        self._flavor_projectors[projection_schema] = projector
        self._flavor_projection_validators[projection_schema] = validator

    @classmethod
    def _reject_remote_schema_references(cls, value: object) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "$ref" and (not isinstance(item, str) or not item.startswith("#")):
                    raise InvalidReadQueryError("Flavor projector schema references must be local")
                cls._reject_remote_schema_references(item)
        elif isinstance(value, list):
            for item in value:
                cls._reject_remote_schema_references(item)

    def _flavor_projection_context(self, swarm_id: str, work_id: str) -> FlavorProjectionContext:
        sessions = tuple(
            session
            for session in self.list_sessions()
            if session.swarm_id == swarm_id and session.work_id == work_id
        )
        configuration = self._workspace.show_project()
        return FlavorProjectionContext(
            project=FlavorProjectContext(
                id=configuration.project,
                version=configuration.version,
                integration=configuration.integration,
                default_method=configuration.default_method,
                created_at=configuration.created_at,
            ),
            work=self.get_work_item(swarm_id, work_id),
            lifecycle=self.lifecycle(swarm_id, work_id),
            clarifications=self.clarifications(swarm_id, work_id),
            traceability=self.work_traceability(swarm_id, work_id),
            sessions=sessions,
            usage=self.usage_summary(swarm_id, work_id),
            metrics=self.metric_windows(
                swarm_id,
                work_id,
                start=configuration.created_at,
                end=self._timestamp(),
            ),
        )

    def _validate_flavor_contribution(
        self,
        projector: FlavorProjectionProvider,
        contribution: object,
    ) -> tuple[dict[str, object], dict[str, object]]:
        if not isinstance(contribution, FlavorProjectionContribution):
            raise InvalidDurableStateError("Flavor projector returned an incompatible contribution")
        serialized = contribution.to_dict()
        sections = serialized["sections"]
        presentation = serialized["presentation"]
        if not isinstance(sections, dict) or not isinstance(presentation, dict):
            raise InvalidDurableStateError("Flavor projector contribution is malformed")
        missing = set(projector.required_sections) - set(sections)
        if missing:
            raise InvalidDurableStateError("Flavor projector omitted one or more required sections")
        for name, section in sections.items():
            if _PROJECTION_SECTION.fullmatch(name) is None:
                raise InvalidDurableStateError("Flavor projector section name is invalid")
            if name in _RESERVED_PROJECTION_SECTIONS:
                raise InvalidDurableStateError(
                    "Flavor projector attempted to replace a Core-owned section"
                )
            self._validate_projection_envelope(section)
        if presentation.get("authoritative") is not False:
            raise InvalidDurableStateError(
                "Flavor projection presentation must be non-authoritative"
            )
        self._validate_safe_projection({**sections, "presentation": presentation})
        return sections, presentation

    @staticmethod
    def _validate_projection_envelope(section: object) -> None:
        if not isinstance(section, dict):
            raise InvalidDurableStateError("Flavor projection section must be an object")
        status = section.get("status")
        if status == "available":
            if "value" not in section or "reason" in section:
                raise InvalidDurableStateError(
                    "Available flavor projection section must contain only a value"
                )
            return
        if status == "unavailable":
            reason = section.get("reason")
            if "value" in section or not isinstance(reason, dict):
                raise InvalidDurableStateError(
                    "Unavailable flavor projection section requires a safe reason"
                )
            code = reason.get("code")
            message = reason.get("message")
            if (
                not isinstance(code, str)
                or _PROJECTION_SECTION.fullmatch(code) is None
                or not isinstance(message, str)
                or not 1 <= len(message) <= 500
            ):
                raise InvalidDurableStateError("Unavailable flavor projection reason is malformed")
            return
        raise InvalidDurableStateError(
            "Flavor projection section status must be available or unavailable"
        )

    @classmethod
    def _validate_safe_projection(cls, payload: object) -> None:
        def walk(value: object, depth: int = 0) -> None:
            if depth > 32:
                raise InvalidDurableStateError("Flavor projection nesting is too deep")
            if isinstance(value, dict):
                for key, item in value.items():
                    normalized = re.sub(r"[^a-z0-9]", "", key.casefold())
                    if normalized in _FORBIDDEN_PROJECTION_KEYS:
                        raise InvalidDurableStateError(
                            "Flavor projection contains a forbidden field"
                        )
                    walk(item, depth + 1)
                return
            if isinstance(value, list):
                for item in value:
                    walk(item, depth + 1)
                return
            if isinstance(value, str):
                candidate = value.strip()
                folded = candidate.casefold()
                if (
                    candidate.startswith(("/", "\\\\", "./", "../", "~/"))
                    or folded.startswith((".agora/", "file://", "repo://"))
                    or _EMBEDDED_LOCATION.search(candidate) is not None
                    or _SECRET_VALUE.search(candidate) is not None
                ):
                    raise InvalidDurableStateError("Flavor projection contains a forbidden value")
                return
            if value is None or isinstance(value, (bool, int)):
                return
            if isinstance(value, float) and math.isfinite(value):
                return
            raise InvalidDurableStateError("Flavor projection contains a non-JSON value")

        walk(payload)
        try:
            encoded = json.dumps(payload, allow_nan=False, ensure_ascii=True).encode("ascii")
        except (TypeError, ValueError) as error:
            raise InvalidDurableStateError("Flavor projection is not valid JSON") from error
        if len(encoded) > _FLAVOR_PROJECTION_LIMIT:
            raise InvalidDurableStateError("Flavor projection exceeds the size limit")

    @staticmethod
    def _lifecycle_projection_section(
        lifecycle: LifecycleProjection,
    ) -> dict[str, object]:
        transitions = []
        for transition in lifecycle.transitions:
            if transition.source != lifecycle.current_state:
                continue
            transitions.append(
                {
                    "source": transition.source,
                    "target": transition.target,
                    "available": transition.available is True,
                    "blockers": [
                        {"code": blocker.code, "message": blocker.message}
                        for blocker in transition.blockers
                    ],
                }
            )
        return {
            "status": "available",
            "value": {
                "source_schema": lifecycle.schema,
                "method": lifecycle.method,
                "current_state": lifecycle.current_state,
                "terminal_state": lifecycle.terminal_state,
                "states": [
                    {
                        "id": state.id,
                        "initial": state.initial,
                        "terminal": state.terminal,
                    }
                    for state in lifecycle.states
                ],
                "transitions": transitions,
            },
        }

    @staticmethod
    def _clarifications_projection_section(
        clarifications: ClarificationsProjection,
    ) -> dict[str, object]:
        def serialize(items: tuple[ClarificationSummary, ...]) -> list[dict[str, object]]:
            values = []
            for item in items:
                value = item.to_dict()
                value.pop("schema")
                values.append(value)
            return values

        return {
            "status": "available",
            "value": {
                "source_schema": clarifications.schema,
                "open": serialize(clarifications.open),
                "resolved": serialize(clarifications.resolved),
            },
        }

    def _timestamp(self) -> str:
        value = self._now()
        if value.tzinfo is None:
            raise InvalidDurableStateError("Projection clock must return a timezone-aware value")
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")

    def specification_history(self, swarm_id: str, work_id: str) -> SpecificationSummary:
        self._require_work_slugs(swarm_id, work_id)

        def read() -> SpecificationSummary:
            history = self._workspace.work_specification_history(swarm_id, work_id)
            return SpecificationSummary(
                available=history.available,
                uri=history.uri,
                revisions=tuple(
                    SpecificationRevisionSummary(
                        id=revision.id,
                        kind=revision.kind,
                        sha=revision.sha,
                        short_sha=revision.short_sha,
                        timestamp=revision.timestamp,
                        author=revision.author,
                        subject=revision.subject,
                        uncommitted=revision.uncommitted,
                    )
                    for revision in history.revisions
                ),
                has_history=history.has_history,
                working_tree=history.working_tree,
                truncated=history.truncated,
                reason=history.reason,
            )

        return self._read(f"specification history {swarm_id}/{work_id}", read)

    def specification_revision(
        self, swarm_id: str, work_id: str, revision_id: str
    ) -> SpecificationRevisionDetail:
        self._require_work_slugs(swarm_id, work_id)
        if not isinstance(revision_id, str) or not revision_id:
            raise InvalidReadQueryError("Specification revision id is required")

        def read() -> SpecificationRevisionDetail:
            detail = self._workspace.work_specification_revision(swarm_id, work_id, revision_id)
            return SpecificationRevisionDetail(
                available=detail.available,
                uri=detail.uri,
                revision_id=detail.revision_id,
                kind=detail.kind,
                sha=detail.sha,
                previous_revision_id=detail.previous_revision_id,
                timestamp=detail.timestamp,
                author=detail.author,
                subject=detail.subject,
                content=detail.content,
                diff=detail.diff,
                size_bytes=detail.size_bytes,
                content_truncated=detail.content_truncated,
                diff_truncated=detail.diff_truncated,
                encoding=detail.encoding,
                binary=detail.binary,
                reason=detail.reason,
            )

        return self._read(f"specification revision {swarm_id}/{work_id}/{revision_id}", read)

    def gate_decision_options(self, swarm_id: str, work_id: str) -> GateDecisionOptionsProjection:
        self._require_work_slugs(swarm_id, work_id)

        def read() -> GateDecisionOptionsProjection:
            work = self._workspace.show_work(swarm_id, work_id)
            contract = self._workspace.method_contract(swarm_id)
            records = self._workspace.inspect_gate_decision_options(swarm_id, work_id)
            options = tuple(
                GateDecisionOptionSummary(
                    swarm_id=record.swarm_id,
                    work_id=record.work_id,
                    expected_state=record.expected_state,
                    transition_source=record.transition_source,
                    transition_target=record.transition_target,
                    gate_id=record.gate_id,
                    decision=record.decision,
                    role_id=record.role_id,
                    actor_id=record.actor_id,
                    allowed=record.allowed,
                    blockers=tuple(self._blocker_summary(blocker) for blocker in record.blockers),
                    evidence_required=record.evidence_required,
                    required_evidence_types=record.required_evidence_types,
                    evidence_references=record.evidence_references,
                    evidence_references_by_type=record.evidence_references_by_type,
                    evidence_content_sha256=record.evidence_content_sha256,
                    content_addressed_evidence_required=(
                        record.content_addressed_evidence_required
                    ),
                    authentication_required=record.authentication_required,
                    authentication_algorithm=record.authentication_algorithm,
                    authentication_fingerprint=record.authentication_fingerprint,
                    unavailable_reason=record.unavailable_reason,
                )
                for record in records
            )
            terminal = work.state == contract.terminal_state
            reason = None
            if terminal:
                reason = "Work is in a terminal state"
            elif work.operational_status != "active":
                reason = f"Work operational status is {work.operational_status}"
            elif not options:
                reason = "No governed gate decisions exist for the current state"
            return GateDecisionOptionsProjection(
                swarm_id=swarm_id,
                work_id=work_id,
                current_state=work.state,
                operational_status=work.operational_status,
                terminal=terminal,
                options=options,
                reason=reason,
            )

        return self._read(f"gate decision options {swarm_id}/{work_id}", read)

    def work_control_projection(self, swarm_id: str, work_id: str) -> WorkControlProjection:
        self._require_work_slugs(swarm_id, work_id)

        def assemble() -> WorkControlProjection:
            work = self.get_work_item(swarm_id, work_id)
            lifecycle = self.lifecycle(swarm_id, work_id)
            traceability = self.work_traceability(swarm_id, work_id)
            specification = self.specification_history(swarm_id, work_id)
            options = self.gate_decision_options(swarm_id, work_id)
            if not (
                work.state == lifecycle.current_state == traceability.state == options.current_state
            ):
                raise InvalidDurableStateError(
                    "Work changed while its control projection was being read"
                )
            material = {
                "work": work.to_dict(),
                "lifecycle": lifecycle.to_dict(),
                "artifacts": [item.to_dict() for item in work.artifacts],
                "evidence": [item.to_dict() for item in work.evidence],
                "approvals": [item.to_dict() for item in work.approvals],
                "traceability": traceability.to_dict(),
                "specification_history": specification.to_dict(),
                "gate_decision_options": options.to_dict(),
            }
            snapshot_token = hashlib.sha256(
                json.dumps(
                    material,
                    ensure_ascii=True,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("ascii")
            ).hexdigest()
            return WorkControlProjection(
                snapshot_token=snapshot_token,
                work=work,
                lifecycle=lifecycle,
                artifacts=work.artifacts,
                evidence=work.evidence,
                approvals=work.approvals,
                traceability=traceability,
                specification_history=specification,
                gate_decision_options=options,
            )

        def read() -> WorkControlProjection:
            with self._workspace.consistent_read("work-control-projection"):
                for _ in range(3):
                    before = self._workspace.work_control_read_set_sha256(swarm_id, work_id)
                    projection = assemble()
                    after = self._workspace.work_control_read_set_sha256(swarm_id, work_id)
                    if before == after:
                        return projection
                raise ConcurrentDurableEditError(
                    "Durable work control material changed during three read attempts",
                    details={"stale_reason": "external-edit"},
                )

        return self._read(f"work control projection {swarm_id}/{work_id}", read)

    def work_inspection(
        self,
        swarm_id: str,
        work_id: str,
        snapshot_token: str | None = None,
    ) -> WorkInspection | WorkInspectionNotModified:
        """Return bounded decision context without assembling audit-heavy control material."""

        self._require_work_slugs(swarm_id, work_id)

        def assemble(snapshot_token: str) -> WorkInspection:
            work = self.get_work_item(swarm_id, work_id)
            work_record = self._workspace.show_work(swarm_id, work_id)
            lifecycle = self.lifecycle(swarm_id, work_id)
            swarm = self.get_swarm(swarm_id)
            if work.state != work_record.state or work.state != lifecycle.current_state:
                raise InvalidDurableStateError(
                    "Work changed while its compact inspection was being read"
                )
            current = tuple(
                transition
                for transition in lifecycle.transitions
                if transition.source == lifecycle.current_state
            )
            visible = current[:_INSPECTION_TRANSITION_LIMIT]
            required_artifacts = tuple(work.required_artifacts)
            missing_artifacts = tuple(
                kind for kind in required_artifacts if kind not in work.artifact_kinds
            )
            status_reason, status_reason_truncated = self._bounded_inspection_text(
                work.status_reason
            )
            terminal = work.state == lifecycle.terminal_state
            reason = None
            if terminal:
                reason = "Work is in a terminal state"
            elif work.operational_status != "active":
                reason = f"Work operational status is {work.operational_status}"
            elif not current:
                reason = "No outgoing transition exists for the current state"
            elif not any(transition.available for transition in current):
                reason = "All outgoing transitions are blocked"
            return WorkInspection(
                snapshot_token=snapshot_token,
                swarm_id=swarm_id,
                work_id=work_id,
                title=work.title,
                revision=work_record.revision,
                method=lifecycle.method,
                state=work.state,
                operational_status=work.operational_status,
                status_reason=status_reason,
                status_reason_truncated=status_reason_truncated,
                terminal=terminal,
                has_budget_limits=work.budget_limits is not None,
                criteria={
                    "total": len(work.acceptance_criteria),
                    "satisfied": len(work.satisfied_criteria),
                },
                materials={
                    "artifacts": len(work.artifacts),
                    "evidence": len(work.evidence),
                    "successful_evidence": sum(
                        evidence.result == "success" for evidence in work.evidence
                    ),
                    "approvals": len(work.approvals),
                },
                required_artifacts=required_artifacts[:_INSPECTION_ARTIFACT_LIMIT],
                missing_artifacts=missing_artifacts[:_INSPECTION_ARTIFACT_LIMIT],
                artifacts_truncated=(
                    len(required_artifacts) > _INSPECTION_ARTIFACT_LIMIT
                    or len(missing_artifacts) > _INSPECTION_ARTIFACT_LIMIT
                ),
                transitions=tuple(
                    self._work_inspection_transition(transition, swarm.assignments)
                    for transition in visible
                ),
                transition_count=len(current),
                transitions_truncated=len(current) > len(visible),
                reason=reason,
            )

        def read() -> WorkInspection | WorkInspectionNotModified:
            with self._workspace.consistent_read("work-inspection"):
                for _ in range(3):
                    before = self._workspace.work_inspection_read_set_sha256(swarm_id, work_id)
                    if snapshot_token == before:
                        after = self._workspace.work_inspection_read_set_sha256(swarm_id, work_id)
                        if before == after:
                            return WorkInspectionNotModified(
                                snapshot_token=before,
                                swarm_id=swarm_id,
                                work_id=work_id,
                            )
                        continue
                    inspection = assemble(before)
                    after = self._workspace.work_inspection_read_set_sha256(swarm_id, work_id)
                    if before == after:
                        return inspection
                raise ConcurrentDurableEditError(
                    "Durable work inspection material changed during three read attempts",
                    details={"stale_reason": "external-edit"},
                )

        return self._read(f"work inspection {swarm_id}/{work_id}", read)

    def _work_inspection_transition(
        self,
        transition: TransitionSummary,
        assignments: Mapping[str, str],
    ) -> WorkInspectionTransition:
        roles = transition.authorized_roles[:_INSPECTION_ROLE_LIMIT]
        approval_roles = transition.required_approval_roles[:_INSPECTION_ROLE_LIMIT]
        blockers = transition.blockers[:_INSPECTION_BLOCKER_LIMIT]
        return WorkInspectionTransition(
            target_state=transition.target,
            gate_id=transition.gate_id,
            authorized_roles=roles,
            assigned_actors={role: assignments[role] for role in roles if role in assignments},
            required_approval_roles=approval_roles,
            required_approval_actors={
                role: assignments[role] for role in approval_roles if role in assignments
            },
            available=bool(transition.available),
            blockers=tuple(self._work_inspection_blocker(blocker) for blocker in blockers),
            blocker_count=len(transition.blockers),
            blockers_truncated=len(transition.blockers) > len(blockers),
        )

    @classmethod
    def _work_inspection_blocker(cls, blocker: GateBlockerSummary) -> WorkInspectionBlocker:
        message, message_truncated = cls._bounded_inspection_text(blocker.message)
        references = blocker.references[:_INSPECTION_REFERENCE_LIMIT]
        return WorkInspectionBlocker(
            code=blocker.code,
            category=blocker.category,
            message=message or "",
            references=references,
            truncated=(message_truncated or len(blocker.references) > _INSPECTION_REFERENCE_LIMIT),
        )

    @staticmethod
    def _bounded_inspection_text(value: str | None) -> tuple[str | None, bool]:
        if value is None or len(value) <= _INSPECTION_TEXT_LIMIT:
            return value, False
        return value[: _INSPECTION_TEXT_LIMIT - 1] + "…", True

    def _work_materials(
        self, swarm_id: str, work_id: str
    ) -> tuple[
        tuple[ArtifactSummary, ...],
        tuple[EvidenceSummary, ...],
        tuple[ApprovalSummary, ...],
    ]:
        return (
            tuple(
                self._artifact_summary(record)
                for record in self._workspace.list_work_artifacts(swarm_id, work_id)
            ),
            tuple(
                self._evidence_summary(record)
                for record in self._workspace.list_work_evidence(swarm_id, work_id)
            ),
            tuple(
                self._approval_summary(record)
                for record in self._workspace.list_work_approvals(swarm_id, work_id)
            ),
        )

    def _read(self, subject: str, operation: Callable[[], ReadResult]) -> ReadResult:
        self._project_root()
        try:
            return operation()
        except FileNotFoundError as error:
            raise ReadResourceNotFoundError(f"Cannot read {subject}: {error}") from error
        except ValueError as error:
            raise InvalidDurableStateError(f"Cannot read {subject}: {error}") from error

    def _project_root(self) -> Path:
        try:
            root = self._workspace.project_root()
        except FileNotFoundError as error:
            raise ProjectNotFoundError(str(error)) from error
        self._require_internal_path(root, root / ".agora" / "project.md")
        return root

    @staticmethod
    def _require_internal_path(root: Path, path: Path) -> None:
        try:
            path.resolve().relative_to(root.resolve())
        except ValueError as error:
            raise InvalidDurableStateError(
                f"Durable record resolves outside the Agora project: {path}"
            ) from error

    @staticmethod
    def _require_slug(value: str, label: str) -> None:
        try:
            assert_slug(value, label)
        except ValueError as error:
            raise InvalidReadQueryError(str(error)) from error

    def _require_work_slugs(self, swarm_id: str, work_id: str) -> None:
        self._require_slug(swarm_id, "Swarm id")
        self._require_slug(work_id, "Work id")

    @staticmethod
    def _actor_summary(record: ActorRecord) -> ActorSummary:
        return ActorSummary(
            id=record.id,
            reference=record.reference,
            name=record.name,
            kind=record.kind,
            capabilities=record.capabilities,
            integration=record.integration,
            provider=record.provider,
            model=record.model,
            runtime_fallbacks=getattr(record, "runtime_fallbacks", ()),
            represented_swarm=record.represented_swarm,
            authentication_required=record.authentication_required,
            authentication_algorithm=record.authentication_algorithm,
            authentication_public_key=record.authentication_public_key,
            authentication_fingerprint=record.authentication_fingerprint,
            authentication_revoked_at=record.authentication_revoked_at,
            authentication_revoked_reason=record.authentication_revoked_reason,
        )

    def _swarm_summary(self, record: SwarmRecord) -> SwarmSummary:
        contract = self._workspace.method_contract(record.id)
        return SwarmSummary(
            id=record.id,
            method=record.method,
            status=record.status,
            branch=record.branch,
            objective=record.objective,
            required_roles=record.required_roles,
            assignments=record.assignments,
            work_states=contract.work_states,
            optional_roles=tuple(record.optional_roles),
        )

    def _session_summary(self, record: SessionRecord) -> SessionSummary:
        root = self._workspace.project_root()
        self._require_internal_path(root, Path(record.path))
        self._require_internal_path(root, Path(record.context_path))
        return SessionSummary(
            id=record.id,
            actor=record.actor,
            executor=record.executor or record.actor,
            swarm_id=record.swarm_id,
            work_id=record.work_id,
            roles=record.roles,
            integration=record.integration,
            provider=record.provider,
            model=record.model,
            execution_profile=record.execution_profile,
            status=record.status,
            record_uri=f"repo://.agora/sessions/{record.id}/SESSION.md",
            context_uri=f"repo://.agora/sessions/{record.id}/CONTEXT.md",
            launch_command=record.launch_command,
            runtime_available=record.runtime_available,
            created_at=record.created_at,
            exit_code=record.exit_code,
            timeout_seconds=record.timeout_seconds,
            max_output_bytes=record.max_output_bytes,
            max_transcript_bytes=record.max_transcript_bytes,
            output_bytes=record.output_bytes,
            termination_reason=record.termination_reason,
            context_sha256=record.context_sha256,
            authentication_verified=record.authentication_verified,
            authentication_fingerprint=record.authentication_fingerprint,
            authentication_public_key=record.authentication_public_key,
            authorization_sha256=record.authorization_sha256,
            authorization_signature=record.authorization_signature,
            preparation_action_id=record.preparation_action_id,
            retry_of=record.retry_of,
            provenance=_session_provenance_summary(record),
        )

    @staticmethod
    def _method_states(contract: MethodContract) -> tuple[MethodStateSummary, ...]:
        initial = contract.work_states[0]
        return tuple(
            MethodStateSummary(
                id=state,
                initial=state == initial,
                terminal=state == contract.terminal_state,
            )
            for state in contract.work_states
        )

    def _method_summary(self, contract: MethodContract) -> MethodSummary:
        return MethodSummary(
            id=contract.id,
            name=contract.name,
            version=contract.version,
            required_roles=contract.required_roles,
            states=self._method_states(contract),
            transitions=tuple(
                TransitionSummary(
                    source=transition.source,
                    target=transition.target,
                    authorized_roles=transition.roles,
                    gate_id=transition.gate,
                    required_approval_roles=(
                        contract.gates[transition.gate].required_approval_roles
                        if transition.gate is not None
                        else ()
                    ),
                    available=None,
                )
                for transition in contract.transitions
            ),
            gates=tuple(self._gate_summary(gate) for gate in contract.gates.values()),
            wip_limits=contract.wip_limits,
            criterion_stages=contract.criterion_stages,
            criterion_stage_roles=contract.criterion_stage_roles,
            gate_decision_ttl_seconds=contract.gate_decision_ttl_seconds,
        )

    @staticmethod
    def _blocker_summary(record: GateBlockerRecord) -> GateBlockerSummary:
        return GateBlockerSummary(
            code=record.code,
            category=record.category,
            message=record.message,
            references=record.references,
        )

    def _transition_summary(self, record: TransitionAssessmentRecord) -> TransitionSummary:
        return TransitionSummary(
            source=record.source,
            target=record.target,
            authorized_roles=record.roles,
            gate_id=record.gate_id,
            required_approval_roles=record.required_approval_roles,
            available=record.available,
            blockers=tuple(self._blocker_summary(item) for item in record.blockers),
        )

    @staticmethod
    def _gate_summary(
        gate: GatePolicy,
        *,
        blockers: tuple[GateBlockerSummary, ...] = (),
        assessed: bool = False,
    ) -> GateSummary:
        return GateSummary(
            id=gate.id,
            require_all_criteria=gate.require_all_criteria,
            require_required_artifacts=gate.require_required_artifacts,
            required_artifacts=gate.required_artifacts,
            required_criterion_stage=gate.required_criterion_stage,
            require_successful_evidence=gate.require_successful_evidence,
            required_evidence_types=gate.required_evidence_types,
            require_content_addressed_evidence=gate.require_content_addressed_evidence,
            required_approval_roles=gate.required_approval_roles,
            require_resolved_clarifications=gate.require_resolved_clarifications,
            require_clean_git=gate.require_clean_git,
            require_git_commit=gate.require_git_commit,
            blockers=blockers,
            satisfied=not blockers if assessed else None,
        )

    @staticmethod
    def _artifact_summary(record: ArtifactRecord) -> ArtifactSummary:
        return ArtifactSummary(
            kind=record.kind,
            uri=record.uri,
            produced_by=record.produced_by,
            timestamp=record.timestamp,
            content_sha256=record.content_sha256,
        )

    @staticmethod
    def _evidence_summary(record: EvidenceRecord) -> EvidenceSummary:
        return EvidenceSummary(
            type=record.type,
            result=record.result,
            artifact_references=record.artifact_references,
            artifact_content_sha256=record.artifact_content_sha256,
            produced_by=record.produced_by,
            timestamp=record.timestamp,
        )

    @staticmethod
    def _approval_summary(record: ApprovalRecord) -> ApprovalSummary:
        return ApprovalSummary(
            role=record.role,
            actor=record.actor,
            decision="approved",
            note=record.note,
            timestamp=record.timestamp,
        )

    @staticmethod
    def _work_summary(record: WorkRecord) -> WorkItemSummary:
        return WorkItemSummary(
            id=record.id,
            swarm_id=record.swarm_id,
            title=record.title,
            description=record.description,
            state=record.state,
            acceptance_criteria=record.acceptance_criteria,
            satisfied_criteria=record.satisfied_criteria,
            operational_status=record.operational_status,
            status_reason=record.status_reason,
            status_by=record.status_by,
            status_at=record.status_at,
            required_artifacts=record.required_artifacts,
            artifact_kinds=record.artifact_kinds,
            evidence_results=record.evidence_results,
            approval_roles=record.approval_roles,
            child_work_refs=record.child_work_refs,
            budget_limits=record.budget_limits,
            delegation_id=record.delegation_id,
            parent_work_ref=record.parent_work_ref,
            criterion_statuses=record.criterion_statuses,
        )

    @staticmethod
    def activity_entry(record: ActivityRecord) -> ActivityEntry:
        """Project one exact durable Activity record into its public contract."""
        return ActivityEntry(
            timestamp=record.timestamp,
            type=record.type,
            summary=record.summary,
            actor=record.actor,
            swarm_id=record.swarm_id,
            work_id=record.work_id,
            session_id=record.session_id,
            tool_run_id=record.tool_run_id,
            source=record.source,
        )


def _session_provenance_summary(record: SessionRecord) -> SessionProvenanceSummary:
    provenance = record.provenance
    if provenance is None:
        return SessionProvenanceSummary(
            runtime_basis="unavailable",
            provider_basis="unavailable",
            model_basis="unavailable",
            selection_reason=None,
            runtime_version=None,
            fallback_used=False,
            fallback_from_integration=None,
            fallback_from_provider=None,
            fallback_from_model=None,
            fallback_reason=None,
        )
    return SessionProvenanceSummary(**asdict(provenance))
