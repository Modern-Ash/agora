"""Versioned, immutable application-service read contracts."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field, fields
from pathlib import Path
from types import MappingProxyType
from typing import Any


def _freeze(value: Any) -> Any:
    if isinstance(value, Path):
        raise TypeError("Application DTOs cannot expose pathlib.Path values")
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set):
        return tuple(sorted(_freeze(item) for item in value))
    return value


def _serialize(value: Any) -> Any:
    if isinstance(value, SerializableDTO):
        return value.to_dict()
    if isinstance(value, Mapping):
        return {str(key): _serialize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(item) for item in value]
    if isinstance(value, Path):
        raise TypeError("Application DTOs cannot serialize pathlib.Path values")
    return value


@dataclass(frozen=True)
class SerializableDTO:
    """Base for contracts that are immutable in memory and JSON-compatible at the boundary."""

    def __post_init__(self) -> None:
        for item in fields(self):
            object.__setattr__(self, item.name, _freeze(getattr(self, item.name)))

    def to_dict(self) -> dict[str, Any]:
        return {item.name: _serialize(getattr(self, item.name)) for item in fields(self)}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=True, sort_keys=True)


@dataclass(frozen=True)
class ProjectOverview(SerializableDTO):
    project: str
    version: str
    integration: str
    provider: str
    model: str
    default_method: str
    max_delegation_depth: int
    created_at: str
    branch: str
    counts: Mapping[str, int]
    swarm_statuses: Mapping[str, int]
    work_states: Mapping[str, int]
    work_operational_statuses: Mapping[str, int]
    delegation_statuses: Mapping[str, int]
    session_statuses: Mapping[str, int]
    tool_run_statuses: Mapping[str, int]
    attention: Mapping[str, tuple[str, ...]]
    schema: str = field(default="agora/application/project-overview/v1", init=False)


@dataclass(frozen=True)
class ActorSummary(SerializableDTO):
    id: str
    reference: str
    name: str
    kind: str
    capabilities: tuple[str, ...]
    integration: str | None
    provider: str | None
    model: str | None
    represented_swarm: str | None
    authentication_required: bool
    authentication_fingerprint: str | None
    runtime_fallbacks: tuple[Mapping[str, str], ...] = ()
    authentication_algorithm: str | None = None
    authentication_public_key: str | None = None
    authentication_revoked_at: str | None = None
    authentication_revoked_reason: str | None = None
    schema: str = field(default="agora/application/actor-summary/v1", init=False)


@dataclass(frozen=True)
class SwarmSummary(SerializableDTO):
    id: str
    method: str
    status: str
    branch: str
    objective: str
    required_roles: tuple[str, ...]
    assignments: Mapping[str, str]
    work_states: tuple[str, ...] = ()
    schema: str = field(default="agora/application/swarm-summary/v1", init=False)


@dataclass(frozen=True)
class SessionSummary(SerializableDTO):
    id: str
    actor: str
    executor: str
    swarm_id: str
    work_id: str | None
    roles: tuple[str, ...]
    integration: str
    provider: str
    model: str
    status: str
    record_uri: str
    context_uri: str
    launch_command: tuple[str, ...]
    runtime_available: bool
    created_at: str
    exit_code: int | None
    timeout_seconds: int
    max_output_bytes: int
    output_bytes: int
    termination_reason: str | None
    context_sha256: str | None
    authentication_verified: bool
    authentication_fingerprint: str | None
    authentication_public_key: str | None
    authorization_sha256: str | None
    authorization_signature: str | None
    preparation_action_id: str | None
    schema: str = field(default="agora/application/session-summary/v1", init=False)


@dataclass(frozen=True)
class MethodStateSummary(SerializableDTO):
    id: str
    initial: bool
    terminal: bool
    schema: str = field(default="agora/application/method-state-summary/v1", init=False)


@dataclass(frozen=True)
class GateBlockerSummary(SerializableDTO):
    code: str
    category: str
    message: str
    references: tuple[str, ...]
    schema: str = field(default="agora/application/gate-blocker-summary/v1", init=False)


@dataclass(frozen=True)
class GateSummary(SerializableDTO):
    id: str
    require_all_criteria: bool
    require_required_artifacts: bool
    required_artifacts: tuple[str, ...] | None
    required_criterion_stage: str | None
    require_successful_evidence: bool
    required_evidence_types: tuple[str, ...]
    required_approval_roles: tuple[str, ...]
    require_clean_git: bool
    require_git_commit: bool
    blockers: tuple[GateBlockerSummary, ...] = ()
    satisfied: bool | None = None
    schema: str = field(default="agora/application/gate-summary/v1", init=False)


@dataclass(frozen=True)
class TransitionSummary(SerializableDTO):
    source: str
    target: str
    authorized_roles: tuple[str, ...]
    gate_id: str | None
    required_approval_roles: tuple[str, ...]
    available: bool | None
    blockers: tuple[GateBlockerSummary, ...] = ()
    schema: str = field(default="agora/application/transition-summary/v1", init=False)


@dataclass(frozen=True)
class MethodSummary(SerializableDTO):
    id: str
    name: str
    version: str
    required_roles: tuple[str, ...]
    states: tuple[MethodStateSummary, ...]
    transitions: tuple[TransitionSummary, ...]
    gates: tuple[GateSummary, ...]
    wip_limits: Mapping[str, int]
    criterion_stages: tuple[str, ...]
    criterion_stage_roles: Mapping[str, tuple[str, ...]]
    schema: str = field(default="agora/application/method-summary/v1", init=False)


@dataclass(frozen=True)
class WorkItemSummary(SerializableDTO):
    id: str
    swarm_id: str
    title: str
    state: str
    operational_status: str
    required_artifacts: tuple[str, ...]
    artifact_kinds: tuple[str, ...]
    evidence_results: tuple[str, ...]
    approval_roles: tuple[str, ...]
    child_work_refs: tuple[str, ...]
    budget_limits: Mapping[str, int] | None
    delegation_id: str | None
    parent_work_ref: str | None
    description: str = ""
    acceptance_criteria: Mapping[str, str] = field(default_factory=dict)
    satisfied_criteria: tuple[str, ...] = ()
    status_reason: str | None = None
    status_by: str | None = None
    status_at: str | None = None
    criterion_statuses: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    schema: str = field(default="agora/application/work-item-summary/v1", init=False)


@dataclass(frozen=True)
class ArtifactSummary(SerializableDTO):
    kind: str
    uri: str
    produced_by: str
    timestamp: str
    activity: ActivityEntry | None = None
    schema: str = field(default="agora/application/artifact-summary/v2", init=False)


@dataclass(frozen=True)
class EvidenceSummary(SerializableDTO):
    type: str
    result: str
    artifact_references: tuple[str, ...]
    produced_by: str
    timestamp: str
    activity: ActivityEntry | None = None
    schema: str = field(default="agora/application/evidence-summary/v2", init=False)


@dataclass(frozen=True)
class ApprovalSummary(SerializableDTO):
    role: str
    actor: str
    decision: str
    note: str
    timestamp: str
    activity: ActivityEntry | None = None
    schema: str = field(default="agora/application/approval-summary/v2", init=False)


@dataclass(frozen=True)
class WorkItemDetail(SerializableDTO):
    id: str
    swarm_id: str
    title: str
    description: str
    state: str
    operational_status: str
    status_reason: str | None
    status_by: str | None
    status_at: str | None
    acceptance_criteria: Mapping[str, str]
    satisfied_criteria: tuple[str, ...]
    criterion_statuses: Mapping[str, tuple[str, ...]]
    required_artifacts: tuple[str, ...]
    child_work_refs: tuple[str, ...]
    budget_limits: Mapping[str, int] | None
    delegation_id: str | None
    parent_work_ref: str | None
    artifacts: tuple[ArtifactSummary, ...]
    evidence: tuple[EvidenceSummary, ...]
    approvals: tuple[ApprovalSummary, ...]
    artifact_kinds: tuple[str, ...] = ()
    evidence_results: tuple[str, ...] = ()
    approval_roles: tuple[str, ...] = ()
    schema: str = field(default="agora/application/work-item-detail/v1", init=False)


@dataclass(frozen=True)
class ActivityEntry(SerializableDTO):
    timestamp: str
    type: str
    summary: str
    actor: str | None
    swarm_id: str | None
    work_id: str | None
    session_id: str | None
    tool_run_id: str | None
    source: str
    schema: str = field(default="agora/application/activity-entry/v1", init=False)


@dataclass(frozen=True)
class TraceabilitySummary(SerializableDTO):
    swarm_id: str
    work_id: str
    state: str
    stale: bool
    criteria: tuple[Mapping[str, Any], ...]
    clarifications: Mapping[str, Any]
    gherkin: tuple[Mapping[str, Any], ...]
    consistency: tuple[Mapping[str, Any], ...]
    artifacts: tuple[ArtifactSummary, ...]
    evidence: tuple[EvidenceSummary, ...]
    activity: tuple[ActivityEntry, ...]
    schema: str = field(default="agora/application/traceability-summary/v1", init=False)


@dataclass(frozen=True)
class SpecificationRevisionSummary(SerializableDTO):
    id: str
    kind: str
    sha: str | None
    short_sha: str
    timestamp: str | None
    author: str | None
    subject: str
    uncommitted: bool
    schema: str = field(default="agora/application/specification-revision-summary/v1", init=False)


@dataclass(frozen=True)
class SpecificationSummary(SerializableDTO):
    available: bool
    uri: str | None
    revisions: tuple[SpecificationRevisionSummary, ...]
    has_history: bool
    working_tree: bool
    truncated: bool
    reason: str | None = None
    schema: str = field(default="agora/application/specification-summary/v1", init=False)


@dataclass(frozen=True)
class LifecycleProjection(SerializableDTO):
    swarm_id: str
    work_id: str
    method: str
    current_state: str
    operational_status: str
    terminal_state: str
    available_transitions: tuple[str, ...]
    acceptance_criteria: Mapping[str, str]
    satisfied_criteria: tuple[str, ...]
    criterion_statuses: Mapping[str, tuple[str, ...]]
    required_artifacts: tuple[str, ...]
    artifact_kinds: tuple[str, ...]
    evidence_results: tuple[str, ...]
    approval_roles: tuple[str, ...]
    states: tuple[MethodStateSummary, ...] = ()
    transitions: tuple[TransitionSummary, ...] = ()
    gates: tuple[GateSummary, ...] = ()
    schema: str = field(default="agora/application/lifecycle-projection/v2", init=False)
