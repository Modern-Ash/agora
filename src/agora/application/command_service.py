"""Governed mutation boundary over Agora Core domain operations."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

from agora.application.commands import (
    AmendBudgetCommand,
    ApproveGateCommand,
    BudgetAmendmentProjection,
    GateDecisionProjection,
    PreparedBudgetAmendment,
    PreparedGateDecision,
    amend_budget_authorization_payload,
    approve_gate_authorization_payload,
    canonicalize_amend_budget_command,
    canonicalize_approve_gate_command,
)
from agora.application.errors import (
    AgoraApplicationError,
    AuthorityDeniedError,
    CommandPersistenceError,
    GateAlreadyResolvedError,
    GateEvidenceMissingError,
    GovernedMaterialStaleError,
    InvalidCommandError,
    LifecyclePreconditionFailedError,
    PreparationExpiredError,
    ProjectIdentityMismatchError,
    SignatureInvalidError,
    SignatureRequiredError,
    StalePreconditionError,
    TransactionCommitError,
    TransactionIndeterminateError,
    TransactionRollbackError,
)
from agora.application.read_service import AgoraReadService
from agora.domain_errors import (
    ActorUnauthorizedRuleError,
    EvidenceMissingRuleError,
    GateAlreadyResolvedRuleError,
    GateDecisionRoleRuleError,
    GovernedMaterialStaleRuleError,
    PreparationExpiredRuleError,
    ProjectIdentityMismatchRuleError,
    SignatureInvalidRuleError,
    SignatureRequiredRuleError,
    StalePreconditionRuleError,
)
from agora.filesystem import FilesystemTransactionFailure, assert_slug
from agora.model import BudgetAmendmentInput, GateDecisionInput
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
                    evidence_content_sha256=dict(command.evidence_content_sha256),
                    prepared_actor_fingerprint=command.actor_fingerprint,
                    precondition_digest=command.precondition_digest,
                    prepared_at=command.prepared_at,
                    expires_at=command.expires_at,
                    authentication_payload=(
                        approve_gate_authorization_payload(command) if authentication else None
                    ),
                    authentication_signature=authentication.get("signature"),
                    authentication_fingerprint=authentication.get("fingerprint"),
                )
            )
        except SignatureRequiredRuleError as error:
            raise SignatureRequiredError(str(error)) from error
        except SignatureInvalidRuleError as error:
            raise SignatureInvalidError(str(error)) from error
        except ActorUnauthorizedRuleError as error:
            raise AuthorityDeniedError(str(error)) from error
        except ProjectIdentityMismatchRuleError as error:
            raise ProjectIdentityMismatchError(str(error)) from error
        except PreparationExpiredRuleError as error:
            raise PreparationExpiredError(str(error)) from error
        except GovernedMaterialStaleRuleError as error:
            raise GovernedMaterialStaleError(
                str(error), details={"stale_reason": error.stale_reason}
            ) from error
        except StalePreconditionRuleError as error:
            raise LifecyclePreconditionFailedError(
                str(error), details={"stale_reason": error.stale_reason}
            ) from error
        except GateAlreadyResolvedRuleError as error:
            raise GateAlreadyResolvedError(str(error)) from error
        except EvidenceMissingRuleError as error:
            raise GateEvidenceMissingError(str(error)) from error
        except GateDecisionRoleRuleError as error:
            raise InvalidCommandError(str(error)) from error
        except PermissionError as error:
            if error.errno is not None:
                raise CommandPersistenceError(
                    "Agora could not persist the gate decision"
                ) from error
            raise AuthorityDeniedError(str(error)) from error
        except FileNotFoundError as error:
            raise InvalidCommandError(str(error)) from error
        except ValueError as error:
            raise InvalidCommandError(str(error)) from error
        except FilesystemTransactionFailure as error:
            raise self._transaction_error(error) from error
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
            evidence_content_sha256=command.evidence_content_sha256,
            actor_fingerprint=command.actor_fingerprint,
            precondition_digest=result.precondition_digest,
            prepared_at=command.prepared_at or "",
            expires_at=command.expires_at,
            lifecycle=self._reads.lifecycle(command.swarm_id, command.work_id),
            activity=self._reads.activity_entry(result.activity),
        )

    def amend_budget(self, command: AmendBudgetCommand) -> BudgetAmendmentProjection:
        command = self._canonicalize_budget(command)
        self._validate_budget(command)
        if command.precondition_digest is None:
            raise StalePreconditionError(
                "Budget amendment requires the precondition digest issued by Core"
            )
        authentication = command.authentication or {}
        try:
            result = self._workspace.amend_budget(
                BudgetAmendmentInput(
                    project_identity=command.project_identity,
                    parent_swarm_id=command.parent_swarm_id,
                    parent_work_id=command.parent_work_id,
                    child_swarm_id=command.child_swarm_id,
                    child_work_id=command.child_work_id,
                    amendment_id=command.amendment_id,
                    actor_id=command.actor_id,
                    role_id=command.role_id,
                    proposed_limits=dict(command.proposed_limits),
                    reason=command.reason,
                    evidence_refs=list(command.evidence_references),
                    precondition_digest=command.precondition_digest,
                    prepared_at=command.prepared_at,
                    expires_at=command.expires_at,
                    authentication_payload=(
                        amend_budget_authorization_payload(command) if authentication else None
                    ),
                    authentication_signature=authentication.get("signature"),
                    authentication_fingerprint=authentication.get("fingerprint"),
                )
            )
        except SignatureRequiredRuleError as error:
            raise SignatureRequiredError(str(error)) from error
        except SignatureInvalidRuleError as error:
            raise SignatureInvalidError(str(error)) from error
        except ActorUnauthorizedRuleError as error:
            raise AuthorityDeniedError(str(error)) from error
        except ProjectIdentityMismatchRuleError as error:
            raise ProjectIdentityMismatchError(str(error)) from error
        except PreparationExpiredRuleError as error:
            raise PreparationExpiredError(str(error)) from error
        except GovernedMaterialStaleRuleError as error:
            raise GovernedMaterialStaleError(
                str(error), details={"stale_reason": error.stale_reason}
            ) from error
        except EvidenceMissingRuleError as error:
            raise GateEvidenceMissingError(str(error)) from error
        except FilesystemTransactionFailure as error:
            raise self._transaction_error(error) from error
        except PermissionError as error:
            raise AuthorityDeniedError(str(error)) from error
        except (FileNotFoundError, FileExistsError, ValueError) as error:
            raise InvalidCommandError(str(error)) from error
        except OSError as error:
            raise CommandPersistenceError("Agora could not persist the budget amendment") from error
        assert command.prepared_at is not None
        amendment = result.amendment
        return BudgetAmendmentProjection(
            project_identity=amendment.project_identity,
            parent_work_ref=amendment.parent_work_ref,
            child_work_ref=amendment.child_work_ref,
            amendment_id=amendment.id,
            actor_id=amendment.actor,
            role_id=amendment.role,
            previous_limits=amendment.previous_limits,
            proposed_limits=amendment.proposed_limits,
            consumed=amendment.consumed,
            remaining=result.remaining,
            reason=amendment.reason,
            evidence_references=tuple(amendment.evidence_refs),
            precondition_digest=amendment.precondition_digest,
            prepared_at=command.prepared_at,
            expires_at=command.expires_at,
            activity=self._reads.activity_entry(result.activity),
        )

    def prepare_budget_amendment(self, command: AmendBudgetCommand) -> PreparedBudgetAmendment:
        command = self._canonicalize_budget(command)
        self._validate_budget(command)
        if command.precondition_digest is not None or command.authentication is not None:
            raise InvalidCommandError(
                "Budget amendment preparation cannot include confirmation material"
            )
        if command.prepared_at is not None or command.expires_at is not None:
            raise InvalidCommandError("Preparation timestamps are issued only by Core")
        try:
            prepared = self._workspace.prepare_budget_amendment(
                BudgetAmendmentInput(
                    project_identity=command.project_identity,
                    parent_swarm_id=command.parent_swarm_id,
                    parent_work_id=command.parent_work_id,
                    child_swarm_id=command.child_swarm_id,
                    child_work_id=command.child_work_id,
                    amendment_id=command.amendment_id,
                    actor_id=command.actor_id,
                    role_id=command.role_id,
                    proposed_limits=dict(command.proposed_limits),
                    reason=command.reason,
                    evidence_refs=list(command.evidence_references),
                )
            )
        except ActorUnauthorizedRuleError as error:
            raise AuthorityDeniedError(str(error)) from error
        except ProjectIdentityMismatchRuleError as error:
            raise ProjectIdentityMismatchError(str(error)) from error
        except EvidenceMissingRuleError as error:
            raise GateEvidenceMissingError(str(error)) from error
        except (FileNotFoundError, FileExistsError, ValueError) as error:
            raise InvalidCommandError(str(error)) from error
        canonical = replace(
            command,
            precondition_digest=prepared.precondition_digest,
            prepared_at=prepared.prepared_at,
            expires_at=prepared.expires_at,
        )
        payload = amend_budget_authorization_payload(canonical)
        actor = prepared.actor
        return PreparedBudgetAmendment(
            command_schema=canonical.schema,
            authorization_schema="agora/application/amend-budget-authorization/v1",
            authorization_payload=payload.decode("ascii"),
            authorization_digest=hashlib.sha256(payload).hexdigest(),
            precondition_digest=prepared.precondition_digest,
            prepared_at=prepared.prepared_at,
            expires_at=prepared.expires_at,
            project_identity=canonical.project_identity,
            parent_work_ref=prepared.parent_work_ref,
            child_work_ref=prepared.child_work_ref,
            amendment_id=canonical.amendment_id,
            actor_id=actor.reference,
            role_id=prepared.role,
            previous_limits=prepared.previous_limits,
            proposed_limits=prepared.proposed_limits,
            consumed=prepared.consumed,
            reason=canonical.reason,
            evidence_references=canonical.evidence_references,
            authentication_required=actor.authentication_required,
            authentication_algorithm=actor.authentication_algorithm,
            authentication_fingerprint=actor.authentication_fingerprint,
            authentication_public_key=actor.authentication_public_key,
        )

    def prepare_gate_decision(self, command: ApproveGateCommand) -> PreparedGateDecision:
        """Resolve an exact decision and return the canonical bytes an external signer uses."""

        command = self._canonicalize(command)
        self._validate(command)
        if command.precondition_digest is not None:
            raise InvalidCommandError("Preparation commands must not include a precondition digest")
        if command.authentication is not None:
            raise InvalidCommandError("Prepared gate decisions must not include a signature")
        if command.prepared_at is not None or command.expires_at is not None:
            raise InvalidCommandError("Preparation timestamps are issued only by Core")
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
            raise AuthorityDeniedError(str(error)) from error
        except ProjectIdentityMismatchRuleError as error:
            raise ProjectIdentityMismatchError(str(error)) from error
        except GovernedMaterialStaleRuleError as error:
            raise GovernedMaterialStaleError(
                str(error), details={"stale_reason": error.stale_reason}
            ) from error
        except StalePreconditionRuleError as error:
            raise LifecyclePreconditionFailedError(
                str(error), details={"stale_reason": error.stale_reason}
            ) from error
        except GateAlreadyResolvedRuleError as error:
            raise GateAlreadyResolvedError(str(error)) from error
        except EvidenceMissingRuleError as error:
            raise GateEvidenceMissingError(str(error)) from error
        except GateDecisionRoleRuleError as error:
            raise InvalidCommandError(str(error)) from error
        except (FileNotFoundError, ValueError) as error:
            raise InvalidCommandError(str(error)) from error

        selected_content_sha256 = {
            reference: prepared_record.option.evidence_content_sha256.get(reference)
            for reference in command.evidence_references
        }
        command = replace(
            command,
            precondition_digest=prepared_record.precondition_digest,
            prepared_at=prepared_record.prepared_at,
            expires_at=prepared_record.expires_at,
            evidence_content_sha256=selected_content_sha256,
            actor_fingerprint=prepared_record.option.authentication_fingerprint,
        )
        payload = approve_gate_authorization_payload(command)
        option = prepared_record.option
        assert option.actor_id is not None
        return PreparedGateDecision(
            command_schema=command.schema,
            authorization_schema="agora/application/approve-gate-authorization/v4",
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
            evidence_content_sha256=command.evidence_content_sha256,
            actor_fingerprint=command.actor_fingerprint,
            authentication_required=option.authentication_required,
            authentication_algorithm=option.authentication_algorithm,
            authentication_fingerprint=option.authentication_fingerprint,
            authentication_public_key=option.authentication_public_key,
            freshness="governed-material/v2",
            prepared_at=prepared_record.prepared_at,
            expires_at=prepared_record.expires_at,
        )

    @staticmethod
    def _canonicalize(command: ApproveGateCommand) -> ApproveGateCommand:
        if not isinstance(command.reason, str):
            raise InvalidCommandError("Gate decision reason must be a string")
        if not isinstance(command.evidence_references, tuple):
            raise InvalidCommandError("Evidence references must be an array")
        if not isinstance(command.evidence_content_sha256, Mapping):
            raise InvalidCommandError("Evidence content digests must be an object")
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
        for value, label in (
            (command.prepared_at, "Prepared at"),
            (command.expires_at, "Expires at"),
        ):
            if value is not None and not isinstance(value, str):
                raise InvalidCommandError(f"{label} must be an ISO-8601 string")
        if command.precondition_digest is not None and command.prepared_at is None:
            raise InvalidCommandError("Prepared at is required with a precondition digest")
        if command.actor_fingerprint is not None and (
            not isinstance(command.actor_fingerprint, str)
            or re.fullmatch(r"[0-9a-f]{64}", command.actor_fingerprint) is None
        ):
            raise InvalidCommandError("Prepared actor fingerprint must be SHA-256 or null")
        if any(
            digest is not None
            and (not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None)
            for digest in command.evidence_content_sha256.values()
        ):
            raise InvalidCommandError("Evidence content digests must be SHA-256 or null")
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

    @staticmethod
    def _canonicalize_budget(command: AmendBudgetCommand) -> AmendBudgetCommand:
        if not isinstance(command.reason, str):
            raise InvalidCommandError("Budget amendment reason must be a string")
        if not isinstance(command.evidence_references, tuple):
            raise InvalidCommandError("Evidence references must be an array")
        if any(not isinstance(reference, str) for reference in command.evidence_references):
            raise InvalidCommandError("Evidence references must be strings")
        return canonicalize_amend_budget_command(command)

    @staticmethod
    def _validate_budget(command: AmendBudgetCommand) -> None:
        for value, label in (
            (command.project_identity, "Project identity"),
            (command.parent_swarm_id, "Parent Swarm id"),
            (command.parent_work_id, "Parent Work id"),
            (command.child_swarm_id, "Child Swarm id"),
            (command.child_work_id, "Child Work id"),
            (command.amendment_id, "Budget Amendment id"),
            (command.actor_id, "Actor id"),
            (command.role_id, "Role id"),
            (command.reason, "Budget amendment reason"),
        ):
            if not isinstance(value, str):
                raise InvalidCommandError(f"{label} must be a string")
        for value, label in (
            (command.parent_swarm_id, "Parent Swarm id"),
            (command.parent_work_id, "Parent Work id"),
            (command.child_swarm_id, "Child Swarm id"),
            (command.child_work_id, "Child Work id"),
            (command.amendment_id, "Budget Amendment id"),
            (command.role_id, "Role id"),
        ):
            try:
                assert_slug(value, label)
            except ValueError as error:
                raise InvalidCommandError(str(error)) from error
        if not command.project_identity.strip() or not command.reason.strip():
            raise InvalidCommandError("Project identity and amendment reason are required")
        if re.fullmatch(r"(?:(?:project|user):)?[a-z][a-z0-9-]*", command.actor_id) is None:
            raise InvalidCommandError("Actor id must be a safe Agora actor reference")
        if not isinstance(command.proposed_limits, Mapping) or not command.proposed_limits:
            raise InvalidCommandError("Proposed limits must be a non-empty object")
        for dimension, limit in command.proposed_limits.items():
            try:
                assert_slug(str(dimension), "Budget dimension")
            except ValueError as error:
                raise InvalidCommandError(str(error)) from error
            if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0:
                raise InvalidCommandError(
                    f"Budget limit {dimension} must be a non-negative integer"
                )
        if (
            command.precondition_digest is not None
            and re.fullmatch(r"[0-9a-f]{64}", command.precondition_digest) is None
        ):
            raise InvalidCommandError("Precondition digest must be SHA-256")
        if command.precondition_digest is not None and command.prepared_at is None:
            raise InvalidCommandError("Prepared at is required with a precondition digest")
        for value, label in (
            (command.prepared_at, "Prepared at"),
            (command.expires_at, "Expires at"),
        ):
            if value is not None and not isinstance(value, str):
                raise InvalidCommandError(f"{label} must be an ISO-8601 string")
        if command.authentication is not None:
            if not isinstance(command.authentication, Mapping):
                raise InvalidCommandError("Authentication must be an object")
            if set(command.authentication) != {"algorithm", "fingerprint", "signature"}:
                raise InvalidCommandError(
                    "Authentication requires algorithm, fingerprint, and signature"
                )
            if command.authentication["algorithm"] != "ed25519":
                raise InvalidCommandError("Authentication algorithm must be ed25519")
            if re.fullmatch(r"[0-9a-f]{64}", command.authentication["fingerprint"]) is None:
                raise InvalidCommandError("Authentication fingerprint must be SHA-256")

    @staticmethod
    def _transaction_error(error: FilesystemTransactionFailure) -> AgoraApplicationError:
        details = {
            "phase": error.phase,
            "write_count": len(error.write_set),
            "rollback_error_count": len(error.rollback_errors),
            "verification_error_count": len(error.verification_errors),
        }
        if error.phase == "concurrent-edit":
            return GovernedMaterialStaleError(
                "Durable material changed while the transaction was committing",
                recovery_hint=error.recovery_hint,
                details={**details, "stale_reason": "external-edit"},
            )
        if error.indeterminate:
            return TransactionIndeterminateError(
                "Filesystem transaction state is indeterminate",
                recovery_hint=error.recovery_hint,
                details=details,
            )
        if error.phase == "rollback":
            return TransactionRollbackError(
                "Filesystem transaction rollback failed",
                recovery_hint=error.recovery_hint,
                details=details,
            )
        return TransactionCommitError(
            "Filesystem transaction commit failed",
            recovery_hint=error.recovery_hint,
            details=details,
        )
