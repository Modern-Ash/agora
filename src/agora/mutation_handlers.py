"""Incremental, declarative mutation handlers behind the Workspace compatibility facade."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from agora.model import (
    ActorRecord,
    MethodContract,
    PrepareArtifactInput,
    PrepareCriterionInput,
    PrepareEvidenceInput,
    SwarmRecord,
    WorkRecord,
)


@dataclass(frozen=True)
class CriterionMutationContext:
    command: PrepareCriterionInput
    swarm: SwarmRecord
    actor: ActorRecord
    work: WorkRecord
    method: MethodContract


@dataclass(frozen=True)
class ArtifactMutationContext:
    command: PrepareArtifactInput
    swarm: SwarmRecord
    actor: ActorRecord
    work: WorkRecord


@dataclass(frozen=True)
class EvidenceMutationContext:
    command: PrepareEvidenceInput
    swarm: SwarmRecord
    actor: ActorRecord
    work: WorkRecord


class WorkLifecycleHandlers:
    """Dispatch one extracted lifecycle family without a service locator or dynamic imports."""

    def __init__(
        self,
        *,
        satisfy_criterion: Callable[[CriterionMutationContext], Any],
        add_artifact: Callable[[ArtifactMutationContext], Any],
        add_evidence: Callable[[EvidenceMutationContext], Any],
    ) -> None:
        self._handlers: Mapping[str, Callable[[object], Any]] = {
            "criterion.satisfy": lambda context: satisfy_criterion(
                _require_context(context, CriterionMutationContext)
            ),
            "artifact.add": lambda context: add_artifact(
                _require_context(context, ArtifactMutationContext)
            ),
            "evidence.add": lambda context: add_evidence(
                _require_context(context, EvidenceMutationContext)
            ),
        }

    @property
    def actions(self) -> tuple[str, ...]:
        return tuple(self._handlers)

    def dispatch(self, action: str, context: object) -> Any:
        try:
            handler = self._handlers[action]
        except KeyError as error:
            raise ValueError(f"No Work Lifecycle handler is registered for {action}") from error
        return handler(context)


def _require_context(value: object, expected: type[Any]) -> Any:
    if not isinstance(value, expected):
        raise TypeError(f"Expected {expected.__name__}, got {type(value).__name__}")
    return value
