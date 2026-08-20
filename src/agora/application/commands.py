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
    evidence_references: tuple[str, ...] = ()
    authentication: Mapping[str, str] | None = None
    schema: str = field(default="agora/application/approve-gate-command/v1", init=False)


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
    lifecycle: LifecycleProjection
    activity: ActivityEntry
    schema: str = field(default="agora/application/gate-decision-projection/v1", init=False)


def approve_gate_authorization_payload(command: ApproveGateCommand) -> bytes:
    """Return the canonical bytes an authenticated actor signs for this command."""

    value = command.to_dict()
    value.pop("authentication", None)
    value["authorization_schema"] = "agora/application/approve-gate-authorization/v1"
    return (
        json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode("ascii")
