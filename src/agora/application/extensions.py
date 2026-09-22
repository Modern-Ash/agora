"""Provider-neutral extension contracts for flavor-owned read projections."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol

from agora.application.dto import (
    ActorSummary,
    ClarificationsProjection,
    LifecycleProjection,
    MetricWindowSummary,
    SerializableDTO,
    SessionSummary,
    TraceabilitySummary,
    UsageSummaryProjection,
    WorkItemDetail,
)


@dataclass(frozen=True)
class FlavorProjectContext(SerializableDTO):
    """Project-local identity and configuration safe for a flavor projector."""

    id: str
    version: str
    integration: str
    default_method: str
    created_at: str
    schema: str = field(default="agora/application/flavor-project-context/v1", init=False)


@dataclass(frozen=True)
class FlavorSelectionSummary(SerializableDTO):
    """Optional provider-neutral active flavor/profile/depth selection."""

    flavor: str | None
    profile: str | None
    depth: str | None
    schema: str = field(default="agora/application/flavor-selection-summary/v1", init=False)


@dataclass(frozen=True)
class FlavorProjectionContext(SerializableDTO):
    """Core-owned facts available to a flavor projector for one work item."""

    project: FlavorProjectContext
    work: WorkItemDetail
    lifecycle: LifecycleProjection
    clarifications: ClarificationsProjection
    traceability: TraceabilitySummary
    sessions: tuple[SessionSummary, ...]
    usage: UsageSummaryProjection
    metrics: tuple[MetricWindowSummary, ...]
    actors: tuple[ActorSummary, ...] = ()
    selection: FlavorSelectionSummary | None = None
    schema: str = field(default="agora/application/flavor-projection-context/v1", init=False)


@dataclass(frozen=True)
class FlavorProjectionContribution(SerializableDTO):
    """Flavor-owned sections and non-authoritative presentation hints."""

    sections: dict[str, object]
    presentation: dict[str, object]
    schema: str = field(default="agora/application/flavor-projection-contribution/v1", init=False)


class FlavorProjectionProvider(Protocol):
    """Installed flavor adapter that projects only from its supplied Core context."""

    projection_schema: str
    projection_schema_document: Mapping[str, object]
    required_sections: tuple[str, ...]

    def project(self, context: FlavorProjectionContext) -> FlavorProjectionContribution:
        """Return flavor-owned sections for the immutable Core context."""


@dataclass(frozen=True)
class FlavorProjection(SerializableDTO):
    """Flattened aggregate returned to a presentation consumer."""

    schema: str
    generated_at: str
    project: dict[str, object]
    sections: dict[str, object]
    lifecycle: dict[str, object]
    clarifications: dict[str, object]
    presentation: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        payload = super().to_dict()
        sections = payload.pop("sections")
        assert isinstance(sections, dict)
        return {**payload, **sections}
