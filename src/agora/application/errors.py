"""Stable application-layer errors for service consumers."""

from __future__ import annotations

from typing import Any


class AgoraApplicationError(RuntimeError):
    schema = "agora/application/error/v2"
    code = "read.failed"
    category = "internal"
    retryable = False
    recovery_hint: str | None = None

    def __init__(
        self,
        message: str,
        *,
        durable_path: str | None = None,
        recovery_hint: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.durable_path = durable_path
        self.instance_recovery_hint = recovery_hint or self.recovery_hint
        self.details = _safe_details(details or {})

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "code": self.code,
            "message": self.message,
            "category": self.category,
            "retryable": self.retryable,
            "durable_path": self.durable_path,
            "recovery_hint": self.instance_recovery_hint,
            "details": self.details,
        }


class ProjectNotFoundError(AgoraApplicationError):
    code = "read.project-not-found"
    category = "resource"


class InvalidReadQueryError(AgoraApplicationError):
    code = "read.invalid-query"
    category = "validation"


class ReadResourceNotFoundError(AgoraApplicationError):
    code = "read.resource-not-found"
    category = "resource"


class InvalidDurableStateError(AgoraApplicationError):
    code = "read.invalid-durable-state"
    category = "durable-state"


class InvalidCommandError(AgoraApplicationError):
    code = "command.invalid"
    category = "validation"


class IncompatibleCommandVersionError(AgoraApplicationError):
    code = "command.version-incompatible"
    category = "compatibility"


class ProjectIdentityMismatchError(AgoraApplicationError):
    code = "command.project-identity-mismatch"
    category = "identity"


class ActorUnauthorizedError(AgoraApplicationError):
    code = "command.actor-unauthorized"
    category = "authority"


class GateAlreadyResolvedError(AgoraApplicationError):
    code = "command.gate-already-resolved"
    category = "lifecycle"


class StalePreconditionError(AgoraApplicationError):
    code = "command.stale-precondition"
    category = "concurrency"
    retryable = True


class EvidenceMissingError(AgoraApplicationError):
    code = "command.evidence-missing"
    category = "evidence"


class SignatureRequiredError(AgoraApplicationError):
    code = "command.signature-required"
    category = "authentication"


class CommandPersistenceError(AgoraApplicationError):
    code = "command.persistence-failed"
    category = "transaction"
    retryable = True


class DurableStateInvalidError(InvalidDurableStateError):
    code = "durable-state.invalid"


class ConcurrentDurableEditError(DurableStateInvalidError):
    code = "durable-state.concurrent-edit"
    retryable = True
    recovery_hint = "Retry after the external editor or Git operation finishes."


class ResourceNotFoundError(ReadResourceNotFoundError):
    code = "resource.not-found"


class AuthorityDeniedError(ActorUnauthorizedError):
    code = "authority.denied"


class LifecyclePreconditionFailedError(StalePreconditionError):
    code = "lifecycle.precondition-failed"


class GateEvidenceMissingError(EvidenceMissingError):
    code = "gate.evidence-missing"


class GovernedMaterialStaleError(StalePreconditionError):
    code = "command.governed-material-stale"
    recovery_hint = "Refresh the projection and prepare the command again."


class PreparationExpiredError(StalePreconditionError):
    code = "command.preparation-expired"
    recovery_hint = "Prepare the command again before retrying."


class SignatureInvalidError(ActorUnauthorizedError):
    code = "command.signature-invalid"


class TransactionCommitError(CommandPersistenceError):
    code = "transaction.commit-failed"


class TransactionRollbackError(CommandPersistenceError):
    code = "transaction.rollback-failed"
    retryable = False


class TransactionIndeterminateError(CommandPersistenceError):
    code = "transaction.indeterminate"
    retryable = False
    recovery_hint = "Stop mutations, inspect Git and run `agora validate` before recovery."


class RuntimeIncompatibleError(AgoraApplicationError):
    code = "runtime.incompatible"
    category = "compatibility"


class ProviderExecutionFailedError(AgoraApplicationError):
    code = "provider.execution-failed"
    category = "provider"
    retryable = True


def _safe_details(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        safe: dict[str, Any] = {}
        for key, item in value.items():
            name = str(key)
            normalized = name.lower().replace("-", "_")
            if any(
                secret in normalized
                for secret in (
                    "authorization",
                    "credential",
                    "private_key",
                    "secret",
                    "signature",
                    "token",
                )
            ):
                safe[name] = "[redacted]"
            else:
                safe[name] = _safe_details(item)
        return safe
    if isinstance(value, (list, tuple)):
        return [_safe_details(item) for item in value]
    return str(value)
