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
    precondition_digest: str | None = None
    authentication: Mapping[str, str] | None = None
    schema: str = field(default="agora/application/approve-gate-command/v3", init=False)


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
    authentication_required: bool
    authentication_algorithm: str | None
    authentication_fingerprint: str | None
    authentication_public_key: str | None
    freshness: str
    expires_at: str | None
    schema: str = field(default="agora/application/prepared-gate-decision/v2", init=False)


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
    precondition_digest: str
    lifecycle: LifecycleProjection
    activity: ActivityEntry
    schema: str = field(default="agora/application/gate-decision-projection/v2", init=False)


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
        precondition_digest=command.precondition_digest,
        authentication=command.authentication,
    )


def approve_gate_authorization_payload(command: ApproveGateCommand) -> bytes:
    """Return the canonical bytes an authenticated actor signs for this command."""

    value = canonicalize_approve_gate_command(command).to_dict()
    value.pop("authentication", None)
    value["authorization_schema"] = "agora/application/approve-gate-authorization/v3"
    return (
        json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode("ascii")
