"""Serializable query inputs for Agora application read services."""

from dataclasses import dataclass, field

from agora.application.dto import SerializableDTO


@dataclass(frozen=True)
class ActorFilters(SerializableDTO):
    scope: str = "all"
    schema: str = field(default="agora/application/actor-filters/v1", init=False)


@dataclass(frozen=True)
class SwarmFilters(SerializableDTO):
    status: str | None = None
    schema: str = field(default="agora/application/swarm-filters/v1", init=False)


@dataclass(frozen=True)
class WorkItemFilters(SerializableDTO):
    swarm_id: str | None = None
    state: str | None = None
    operational_status: str | None = None
    schema: str = field(default="agora/application/work-item-filters/v1", init=False)


@dataclass(frozen=True)
class ActivityFilters(SerializableDTO):
    actor_id: str | None = None
    swarm_id: str | None = None
    work_id: str | None = None
    session_id: str | None = None
    tool_run_id: str | None = None
    type: str | None = None
    limit: int = 50
    schema: str = field(default="agora/application/activity-filters/v1", init=False)
