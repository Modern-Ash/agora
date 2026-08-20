"""Stable application-layer errors for service consumers."""

from __future__ import annotations

from typing import Any


class AgoraApplicationError(RuntimeError):
    schema = "agora/application/error/v1"
    code = "read.failed"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

    def to_dict(self) -> dict[str, Any]:
        return {"schema": self.schema, "code": self.code, "message": self.message}


class ProjectNotFoundError(AgoraApplicationError):
    code = "read.project-not-found"


class InvalidReadQueryError(AgoraApplicationError):
    code = "read.invalid-query"


class ReadResourceNotFoundError(AgoraApplicationError):
    code = "read.resource-not-found"


class InvalidDurableStateError(AgoraApplicationError):
    code = "read.invalid-durable-state"


class InvalidCommandError(AgoraApplicationError):
    code = "command.invalid"


class IncompatibleCommandVersionError(AgoraApplicationError):
    code = "command.version-incompatible"


class ProjectIdentityMismatchError(AgoraApplicationError):
    code = "command.project-identity-mismatch"


class ActorUnauthorizedError(AgoraApplicationError):
    code = "command.actor-unauthorized"


class GateAlreadyResolvedError(AgoraApplicationError):
    code = "command.gate-already-resolved"


class StalePreconditionError(AgoraApplicationError):
    code = "command.stale-precondition"


class EvidenceMissingError(AgoraApplicationError):
    code = "command.evidence-missing"


class SignatureRequiredError(AgoraApplicationError):
    code = "command.signature-required"


class CommandPersistenceError(AgoraApplicationError):
    code = "command.persistence-failed"
