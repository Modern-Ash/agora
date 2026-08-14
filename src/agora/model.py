from dataclasses import dataclass, field
from typing import Literal

ActorKind = Literal["human", "ai-agent", "swarm", "service", "automation"]
Integration = Literal["generic", "codex", "claude"]
Method = str

ACTOR_KINDS: tuple[ActorKind, ...] = (
    "human",
    "ai-agent",
    "swarm",
    "service",
    "automation",
)
INTEGRATIONS: tuple[Integration, ...] = ("generic", "codex", "claude")
BUILTIN_METHODS: tuple[Method, ...] = ("scrum", "kanban")


@dataclass(frozen=True)
class UserConfiguration:
    integration: Integration
    provider: str
    model: str
    default_method: Method


@dataclass(frozen=True)
class ProjectConfiguration(UserConfiguration):
    project: str
    created_at: str


@dataclass(frozen=True)
class ActorRecord:
    id: str
    name: str
    kind: ActorKind
    capabilities: list[str]
    path: str
    reference: str


@dataclass
class SwarmRecord:
    id: str
    method: str
    status: str
    branch: str
    required_roles: list[str]
    assignments: dict[str, str]
    objective: str
    path: str


@dataclass
class WorkRecord:
    id: str
    swarm_id: str
    title: str
    description: str
    state: str
    acceptance_criteria: dict[str, str]
    satisfied_criteria: list[str]
    required_artifacts: list[str]
    artifact_kinds: list[str]
    evidence_results: list[str]
    path: str


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class MethodPackRecord:
    id: str
    name: str
    scope: Literal["user", "project"]
    path: str
    required_roles: list[str]
    work_states: list[str]
    terminal_state: str


@dataclass(frozen=True)
class ConfigureInput:
    integration: Integration
    provider: str
    model: str
    default_method: Method
    force: bool = False


@dataclass(frozen=True)
class InitInput:
    target: str | None = None
    integration: Integration | None = None
    provider: str | None = None
    model: str | None = None
    default_method: Method | None = None
    force: bool = False


@dataclass(frozen=True)
class InstallMethodInput:
    source: str
    scope: Literal["user", "project"]
    force: bool = False


@dataclass(frozen=True)
class AddActorInput:
    id: str
    name: str
    kind: ActorKind
    capabilities: list[str]
    scope: Literal["user", "project"]
    description: str | None = None
    force: bool = False


@dataclass(frozen=True)
class CreateSwarmInput:
    id: str
    objective: str
    method: Method | None = None
    branch: str | None = None
    create_branch: bool = True


@dataclass(frozen=True)
class AssignActorInput:
    swarm_id: str
    role_id: str
    actor_id: str


@dataclass(frozen=True)
class CreateWorkInput:
    swarm_id: str
    id: str
    title: str
    actor_id: str
    acceptance_criteria: list[tuple[str, str]] = field(default_factory=list)
    required_artifacts: list[str] = field(default_factory=list)
    description: str = ""


@dataclass(frozen=True)
class WorkActorInput:
    swarm_id: str
    work_id: str
    actor_id: str


@dataclass(frozen=True)
class TransitionWorkInput(WorkActorInput):
    target_state: str = ""


@dataclass(frozen=True)
class AddArtifactInput(WorkActorInput):
    kind: str = ""
    uri: str = ""


@dataclass(frozen=True)
class AddEvidenceInput(WorkActorInput):
    type: str = ""
    result: Literal["success", "failure"] = "failure"
    artifact_refs: list[str] = field(default_factory=list)
