"""Versioned command contracts for Agora application services."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field

from agora.application.dto import ActivityEntry, LifecycleProjection, SerializableDTO


@dataclass(frozen=True)
class ApproveGateCommand(SerializableDTO):
    project_identity: str
    swarm_id: str
    work_id: str
    gate_id: str
    actor_id: str
    decision: str
    reason: str
    expected_state: str
    transition_target: str
    role_id: str
    evidence_references: tuple[str, ...] = ()
    evidence_content_sha256: Mapping[str, str | None] = field(default_factory=dict)
    actor_fingerprint: str | None = None
    precondition_digest: str | None = None
    prepared_at: str | None = None
    expires_at: str | None = None
    authentication: Mapping[str, str] | None = None
    schema: str = field(default="agora/application/approve-gate-command/v4", init=False)


@dataclass(frozen=True)
class PreparedGateDecision(SerializableDTO):
    command_schema: str
    authorization_schema: str
    authorization_payload: str
    authorization_digest: str
    precondition_digest: str
    project_identity: str
    swarm_id: str
    work_id: str
    expected_state: str
    transition_target: str
    gate_id: str
    decision: str
    actor_id: str
    role_id: str
    reason: str
    evidence_references: tuple[str, ...]
    evidence_content_sha256: Mapping[str, str | None]
    actor_fingerprint: str | None
    authentication_required: bool
    authentication_algorithm: str | None
    authentication_fingerprint: str | None
    authentication_public_key: str | None
    freshness: str
    prepared_at: str
    expires_at: str | None
    schema: str = field(default="agora/application/prepared-gate-decision/v3", init=False)


@dataclass(frozen=True)
class GateDecisionProjection(SerializableDTO):
    project_identity: str
    swarm_id: str
    work_id: str
    gate_id: str
    actor_id: str
    role_id: str
    decision: str
    reason: str
    evidence_references: tuple[str, ...]
    evidence_content_sha256: Mapping[str, str | None]
    actor_fingerprint: str | None
    precondition_digest: str
    prepared_at: str
    expires_at: str | None
    lifecycle: LifecycleProjection
    activity: ActivityEntry
    schema: str = field(default="agora/application/gate-decision-projection/v3", init=False)


@dataclass(frozen=True)
class AmendBudgetCommand(SerializableDTO):
    project_identity: str
    parent_swarm_id: str
    parent_work_id: str
    child_swarm_id: str
    child_work_id: str
    amendment_id: str
    actor_id: str
    role_id: str
    proposed_limits: Mapping[str, int]
    reason: str
    evidence_references: tuple[str, ...] = ()
    precondition_digest: str | None = None
    prepared_at: str | None = None
    expires_at: str | None = None
    authentication: Mapping[str, str] | None = None
    schema: str = field(default="agora/application/amend-budget-command/v1", init=False)


@dataclass(frozen=True)
class PreparedBudgetAmendment(SerializableDTO):
    command_schema: str
    authorization_schema: str
    authorization_payload: str
    authorization_digest: str
    precondition_digest: str
    prepared_at: str
    expires_at: str | None
    project_identity: str
    parent_work_ref: str
    child_work_ref: str
    amendment_id: str
    actor_id: str
    role_id: str
    previous_limits: Mapping[str, int]
    proposed_limits: Mapping[str, int]
    consumed: Mapping[str, int]
    reason: str
    evidence_references: tuple[str, ...]
    authentication_required: bool
    authentication_algorithm: str | None
    authentication_fingerprint: str | None
    authentication_public_key: str | None
    schema: str = field(default="agora/application/prepared-budget-amendment/v1", init=False)


@dataclass(frozen=True)
class BudgetAmendmentProjection(SerializableDTO):
    project_identity: str
    parent_work_ref: str
    child_work_ref: str
    amendment_id: str
    actor_id: str
    role_id: str
    previous_limits: Mapping[str, int]
    proposed_limits: Mapping[str, int]
    consumed: Mapping[str, int]
    remaining: Mapping[str, int]
    reason: str
    evidence_references: tuple[str, ...]
    precondition_digest: str
    prepared_at: str
    expires_at: str | None
    activity: ActivityEntry
    schema: str = field(default="agora/application/budget-amendment-projection/v1", init=False)


def canonicalize_approve_gate_command(command: ApproveGateCommand) -> ApproveGateCommand:
    """Normalize user-controlled text once before validation, signing, and persistence."""

    references = tuple(
        dict.fromkeys(
            reference.strip() for reference in command.evidence_references if reference.strip()
        )
    )
    return ApproveGateCommand(
        project_identity=command.project_identity,
        swarm_id=command.swarm_id,
        work_id=command.work_id,
        gate_id=command.gate_id,
        actor_id=command.actor_id,
        decision=command.decision,
        reason=" ".join(command.reason.split()),
        expected_state=command.expected_state,
        transition_target=command.transition_target,
        role_id=command.role_id,
        evidence_references=references,
        evidence_content_sha256=command.evidence_content_sha256,
        actor_fingerprint=command.actor_fingerprint,
        precondition_digest=command.precondition_digest,
        prepared_at=command.prepared_at,
        expires_at=command.expires_at,
        authentication=command.authentication,
    )


def approve_gate_authorization_payload(command: ApproveGateCommand) -> bytes:
    """Return the canonical bytes an authenticated actor signs for this command."""

    value = canonicalize_approve_gate_command(command).to_dict()
    value.pop("authentication", None)
    value["authorization_schema"] = "agora/application/approve-gate-authorization/v4"
    return (
        json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode("ascii")


def canonicalize_amend_budget_command(command: AmendBudgetCommand) -> AmendBudgetCommand:
    references = tuple(
        dict.fromkeys(
            reference.strip() for reference in command.evidence_references if reference.strip()
        )
    )
    return AmendBudgetCommand(
        project_identity=command.project_identity,
        parent_swarm_id=command.parent_swarm_id,
        parent_work_id=command.parent_work_id,
        child_swarm_id=command.child_swarm_id,
        child_work_id=command.child_work_id,
        amendment_id=command.amendment_id,
        actor_id=command.actor_id,
        role_id=command.role_id,
        proposed_limits=command.proposed_limits,
        reason=" ".join(command.reason.split()),
        evidence_references=references,
        precondition_digest=command.precondition_digest,
        prepared_at=command.prepared_at,
        expires_at=command.expires_at,
        authentication=command.authentication,
    )


def amend_budget_authorization_payload(command: AmendBudgetCommand) -> bytes:
    value = canonicalize_amend_budget_command(command).to_dict()
    value.pop("authentication", None)
    value["authorization_schema"] = "agora/application/amend-budget-authorization/v1"
    return (
        json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode("ascii")
