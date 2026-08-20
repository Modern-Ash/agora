"""Application-service read boundary over the existing Agora workspace facade."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from agora.application.dto import (
    ActivityEntry,
    ActorSummary,
    ApprovalSummary,
    ArtifactSummary,
    EvidenceSummary,
    LifecycleProjection,
    ProjectOverview,
    SwarmSummary,
    WorkItemDetail,
    WorkItemSummary,
)
from agora.application.errors import (
    InvalidDurableStateError,
    InvalidReadQueryError,
    ProjectNotFoundError,
    ReadResourceNotFoundError,
)
from agora.application.queries import ActivityFilters, ActorFilters, SwarmFilters, WorkItemFilters
from agora.filesystem import assert_slug
from agora.model import ActivityRecord, ActorRecord, SwarmRecord, WorkRecord
from agora.workspace import AgoraWorkspace

ReadResult = TypeVar("ReadResult")


class AgoraReadService:
    """Expose versioned read DTOs without moving or duplicating workspace rules."""

    def __init__(self, workspace: AgoraWorkspace) -> None:
        self._workspace = workspace

    @classmethod
    def from_path(cls, cwd: Path | str) -> AgoraReadService:
        return cls(AgoraWorkspace(cwd=cwd))

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
            artifacts, evidence, approvals = self._work_materials(work)
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
                self._activity_entry(record)
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
            swarm = self._workspace.show_swarm(swarm_id)
            work = self._workspace.show_work(swarm_id, work_id)
            contract = self._workspace.method_contract(swarm_id)
            available = tuple(
                dict.fromkeys(
                    transition.target
                    for transition in contract.transitions
                    if transition.source == work.state
                )
            )
            return LifecycleProjection(
                swarm_id=swarm.id,
                work_id=work.id,
                method=swarm.method,
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
            )

        return self._read(f"lifecycle {swarm_id}/{work_id}", read)

    def artifacts(self, swarm_id: str, work_id: str) -> tuple[ArtifactSummary, ...]:
        self._require_work_slugs(swarm_id, work_id)

        def read() -> tuple[ArtifactSummary, ...]:
            work = self._workspace.show_work(swarm_id, work_id)
            artifacts, _, _ = self._work_materials(work)
            return artifacts

        return self._read(f"artifacts {swarm_id}/{work_id}", read)

    def _work_materials(
        self, work: WorkRecord
    ) -> tuple[
        tuple[ArtifactSummary, ...],
        tuple[EvidenceSummary, ...],
        tuple[ApprovalSummary, ...],
    ]:
        root = self._workspace.project_root()
        self._require_internal_path(root, Path(work.path))
        artifact_rows = self._workspace._work_artifact_rows(work)
        for _, uri in artifact_rows:
            self._workspace._assert_artifact_reference(root, uri)
        artifacts = tuple(ArtifactSummary(kind=kind, uri=uri) for kind, uri in artifact_rows)
        evidence = tuple(
            EvidenceSummary(type=type_, result=result, artifact_references=references)
            for type_, result, references in self._workspace._work_evidence_rows(work)
        )
        approvals = tuple(ApprovalSummary(role=role) for role in work.approval_roles)
        return artifacts, evidence, approvals

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
    def _activity_entry(record: ActivityRecord) -> ActivityEntry:
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
