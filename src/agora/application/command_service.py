"""Governed mutation boundary over Agora Core domain operations."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

from agora.application.commands import (
    ApproveGateCommand,
    GateDecisionProjection,
    PreparedGateDecision,
    approve_gate_authorization_payload,
    canonicalize_approve_gate_command,
)
from agora.application.errors import (
    ActorUnauthorizedError,
    CommandPersistenceError,
    EvidenceMissingError,
    GateAlreadyResolvedError,
    InvalidCommandError,
    ProjectIdentityMismatchError,
    SignatureRequiredError,
    StalePreconditionError,
)
from agora.application.read_service import AgoraReadService
from agora.domain_errors import (
    ActorUnauthorizedRuleError,
    EvidenceMissingRuleError,
    GateAlreadyResolvedRuleError,
    GateDecisionRoleRuleError,
    ProjectIdentityMismatchRuleError,
    SignatureRequiredRuleError,
    StalePreconditionRuleError,
)
from agora.filesystem import assert_slug
from agora.model import GateDecisionInput
from agora.workspace import AgoraWorkspace


class AgoraCommandService:
    """Execute versioned commands while leaving domain rules in AgoraWorkspace."""

    def __init__(self, workspace: AgoraWorkspace) -> None:
        self._workspace = workspace
        self._reads = AgoraReadService(workspace)

    @classmethod
    def from_path(cls, cwd: Path | str) -> AgoraCommandService:
        return cls(AgoraWorkspace(cwd=cwd))

    def approve_gate(self, command: ApproveGateCommand) -> GateDecisionProjection:
        command = self._canonicalize(command)
        self._validate(command)
        if command.precondition_digest is None:
            raise StalePreconditionError(
                "Gate decision requires the precondition digest issued by Core"
            )
        authentication = command.authentication or {}
        try:
            result = self._workspace.decide_gate(
                GateDecisionInput(
                    project_identity=command.project_identity,
                    swarm_id=command.swarm_id,
                    work_id=command.work_id,
                    gate_id=command.gate_id,
                    actor_id=command.actor_id,
                    decision=command.decision,  # type: ignore[arg-type]
                    reason=command.reason,
                    expected_state=command.expected_state,
                    transition_target=command.transition_target,
                    role_id=command.role_id,
                    evidence_refs=list(command.evidence_references),
                    precondition_digest=command.precondition_digest,
                    authentication_payload=(
                        approve_gate_authorization_payload(command) if authentication else None
                    ),
                    authentication_signature=authentication.get("signature"),
                    authentication_fingerprint=authentication.get("fingerprint"),
                )
            )
        except SignatureRequiredRuleError as error:
            raise SignatureRequiredError(str(error)) from error
        except ActorUnauthorizedRuleError as error:
            raise ActorUnauthorizedError(str(error)) from error
        except ProjectIdentityMismatchRuleError as error:
            raise ProjectIdentityMismatchError(str(error)) from error
        except StalePreconditionRuleError as error:
            raise StalePreconditionError(str(error)) from error
        except GateAlreadyResolvedRuleError as error:
            raise GateAlreadyResolvedError(str(error)) from error
        except EvidenceMissingRuleError as error:
            raise EvidenceMissingError(str(error)) from error
        except GateDecisionRoleRuleError as error:
            raise InvalidCommandError(str(error)) from error
        except PermissionError as error:
            if error.errno is not None:
                raise CommandPersistenceError(
                    "Agora could not persist the gate decision"
                ) from error
            raise ActorUnauthorizedError(str(error)) from error
        except FileNotFoundError as error:
            raise InvalidCommandError(str(error)) from error
        except ValueError as error:
            raise InvalidCommandError(str(error)) from error
        except OSError as error:
            raise CommandPersistenceError("Agora could not persist the gate decision") from error
        except RuntimeError as error:
            raise CommandPersistenceError("Agora could not persist the gate decision") from error

        return GateDecisionProjection(
            project_identity=command.project_identity,
            swarm_id=command.swarm_id,
            work_id=command.work_id,
            gate_id=command.gate_id,
            actor_id=result.activity.actor or command.actor_id,
            role_id=result.role_id,
            decision=command.decision,
            reason=command.reason,
            evidence_references=command.evidence_references,
            precondition_digest=result.precondition_digest,
            lifecycle=self._reads.lifecycle(command.swarm_id, command.work_id),
            activity=self._reads.activity_entry(result.activity),
        )

    def prepare_gate_decision(self, command: ApproveGateCommand) -> PreparedGateDecision:
        """Resolve an exact decision and return the canonical bytes an external signer uses."""

        command = self._canonicalize(command)
        self._validate(command)
        if command.precondition_digest is not None:
            raise InvalidCommandError("Preparation commands must not include a precondition digest")
        if command.authentication is not None:
            raise InvalidCommandError("Prepared gate decisions must not include a signature")
        try:
            prepared_record = self._workspace.prepare_gate_decision(
                GateDecisionInput(
                    project_identity=command.project_identity,
                    swarm_id=command.swarm_id,
                    work_id=command.work_id,
                    gate_id=command.gate_id,
                    actor_id=command.actor_id,
                    decision=command.decision,  # type: ignore[arg-type]
                    reason=command.reason,
                    expected_state=command.expected_state,
                    transition_target=command.transition_target,
                    role_id=command.role_id,
                    evidence_refs=list(command.evidence_references),
                )
            )
        except ActorUnauthorizedRuleError as error:
            raise ActorUnauthorizedError(str(error)) from error
        except ProjectIdentityMismatchRuleError as error:
            raise ProjectIdentityMismatchError(str(error)) from error
        except StalePreconditionRuleError as error:
            raise StalePreconditionError(str(error)) from error
        except GateAlreadyResolvedRuleError as error:
            raise GateAlreadyResolvedError(str(error)) from error
        except EvidenceMissingRuleError as error:
            raise EvidenceMissingError(str(error)) from error
        except GateDecisionRoleRuleError as error:
            raise InvalidCommandError(str(error)) from error
        except (FileNotFoundError, ValueError) as error:
            raise InvalidCommandError(str(error)) from error

        command = replace(command, precondition_digest=prepared_record.precondition_digest)
        payload = approve_gate_authorization_payload(command)
        option = prepared_record.option
        assert option.actor_id is not None
        return PreparedGateDecision(
            command_schema=command.schema,
            authorization_schema="agora/application/approve-gate-authorization/v3",
            authorization_payload=payload.decode("ascii"),
            authorization_digest=hashlib.sha256(payload).hexdigest(),
            precondition_digest=prepared_record.precondition_digest,
            project_identity=command.project_identity,
            swarm_id=command.swarm_id,
            work_id=command.work_id,
            expected_state=command.expected_state,
            transition_target=command.transition_target,
            gate_id=command.gate_id,
            decision=command.decision,
            actor_id=option.actor_id,
            role_id=option.role_id,
            reason=command.reason,
            evidence_references=command.evidence_references,
            authentication_required=option.authentication_required,
            authentication_algorithm=option.authentication_algorithm,
            authentication_fingerprint=option.authentication_fingerprint,
            authentication_public_key=option.authentication_public_key,
            freshness="governed-material/v1",
            expires_at=None,
        )

    @staticmethod
    def _canonicalize(command: ApproveGateCommand) -> ApproveGateCommand:
        if not isinstance(command.reason, str):
            raise InvalidCommandError("Gate decision reason must be a string")
        if not isinstance(command.evidence_references, tuple):
            raise InvalidCommandError("Evidence references must be an array")
        if any(not isinstance(reference, str) for reference in command.evidence_references):
            raise InvalidCommandError("Evidence references must be strings")
        return canonicalize_approve_gate_command(command)

    @staticmethod
    def _validate(command: ApproveGateCommand) -> None:
        string_fields = (
            (command.project_identity, "Project identity"),
            (command.swarm_id, "Swarm id"),
            (command.work_id, "Work id"),
            (command.gate_id, "Gate id"),
            (command.actor_id, "Actor id"),
            (command.decision, "Gate decision"),
            (command.reason, "Gate decision reason"),
            (command.expected_state, "Expected state"),
            (command.transition_target, "Transition target"),
            (command.role_id, "Gate decision role id"),
        )
        for value, label in string_fields:
            if not isinstance(value, str):
                raise InvalidCommandError(f"{label} must be a string")
        for value, label in (
            (command.swarm_id, "Swarm id"),
            (command.work_id, "Work id"),
            (command.gate_id, "Gate id"),
            (command.transition_target, "Transition target"),
            (command.role_id, "Gate decision role id"),
        ):
            try:
                assert_slug(value, label)
            except ValueError as error:
                raise InvalidCommandError(str(error)) from error
        if command.decision not in {"approved", "rejected"}:
            raise InvalidCommandError("Gate decision must be approved or rejected")
        if not command.project_identity.strip():
            raise InvalidCommandError("Project identity is required")
        if (
            not isinstance(command.actor_id, str)
            or re.fullmatch(r"(?:(?:project|user):)?[a-z][a-z0-9-]*", command.actor_id) is None
        ):
            raise InvalidCommandError("Actor id must be a safe Agora actor reference")
        try:
            assert_slug(command.expected_state, "Expected state")
        except ValueError as error:
            raise InvalidCommandError(str(error)) from error
        if not command.reason.strip():
            raise InvalidCommandError("Gate decision reason is required")
        if len(command.reason) > 4_000:
            raise InvalidCommandError("Gate decision reason is longer than 4000 characters")
        if not isinstance(command.evidence_references, tuple):
            raise InvalidCommandError("Evidence references must be an array")
        if (
            command.precondition_digest is not None
            and re.fullmatch(r"[0-9a-f]{64}", command.precondition_digest) is None
        ):
            raise InvalidCommandError("Precondition digest must be SHA-256")
        if command.authentication is not None:
            if not isinstance(command.authentication, Mapping):
                raise InvalidCommandError("Authentication must be an object")
            unknown = set(command.authentication) - {"algorithm", "fingerprint", "signature"}
            if unknown:
                raise InvalidCommandError(
                    f"Unknown authentication material: {', '.join(sorted(unknown))}"
                )
            if set(command.authentication) != {"algorithm", "fingerprint", "signature"}:
                raise InvalidCommandError(
                    "Authentication requires algorithm, fingerprint, and signature"
                )
            if command.authentication["algorithm"] != "ed25519":
                raise InvalidCommandError("Authentication algorithm must be ed25519")
            if any(
                not isinstance(value, str) or not value for value in command.authentication.values()
            ):
                raise InvalidCommandError("Authentication values must be non-empty strings")
            if re.fullmatch(r"[0-9a-f]{64}", command.authentication["fingerprint"]) is None:
                raise InvalidCommandError("Authentication fingerprint must be SHA-256")
