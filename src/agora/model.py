from dataclasses import dataclass, field
from typing import Literal

ActorKind = Literal["human", "ai-agent", "swarm", "service", "automation"]
Integration = Literal["generic", "codex", "claude"]
Method = str
PackKind = Literal["method", "tool"]
ToolRisk = Literal["read", "write", "destructive"]
DelegationStatus = Literal[
    "proposed",
    "accepted",
    "blocked",
    "collected",
    "rejected",
    "cancelled",
]
WorkOperationalStatus = Literal["active", "blocked", "cancelled"]
ValidationSeverity = Literal["error", "warning"]

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
    max_delegation_depth: int


@dataclass(frozen=True)
class ProjectConfiguration(UserConfiguration):
    project: str
    version: str
    created_at: str


@dataclass(frozen=True)
class ActorRecord:
    id: str
    name: str
    kind: ActorKind
    capabilities: list[str]
    path: str
    reference: str
    integration: Integration | None = None
    provider: str | None = None
    model: str | None = None
    represented_swarm: str | None = None
    authentication_required: bool = False
    authentication_algorithm: str | None = None
    authentication_public_key: str | None = None
    authentication_fingerprint: str | None = None
    authentication_revoked_at: str | None = None
    authentication_revoked_reason: str | None = None


@dataclass(frozen=True)
class ActorKeyRecord:
    actor: str
    algorithm: Literal["ed25519"]
    public_key: str
    fingerprint: str
    status: Literal["active", "rotated", "revoked"]
    path: str
    created_at: str
    ended_at: str | None = None
    reason: str | None = None
    replaced_by: str | None = None


@dataclass(frozen=True)
class GatePolicy:
    id: str
    require_all_criteria: bool = True
    require_required_artifacts: bool = True
    require_successful_evidence: bool = True
    required_approval_roles: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TransitionRule:
    source: str
    target: str
    roles: list[str]
    gate: str | None = None


@dataclass(frozen=True)
class PackDependency:
    kind: PackKind
    id: str
    version: str


@dataclass(frozen=True)
class PackSourceRecord:
    kind: PackKind
    id: str
    version: str
    registry: str
    registry_scope: Literal["bundled", "user", "project"]
    registry_version: str | None
    registry_source: str | None
    sha256: str
    installed_at: str
    path: str


@dataclass(frozen=True)
class PackUpdateHistoryRecord:
    id: str
    kind: PackKind
    pack_id: str
    from_version: str | None
    to_version: str
    from_sha256: str | None
    to_sha256: str
    registry: str
    registry_scope: Literal["bundled", "user", "project"]
    applied_at: str
    path: str


@dataclass(frozen=True)
class PackLockEntry:
    kind: PackKind
    id: str
    version: str
    sha256: str
    registry: str | None
    source_sha256: str | None


@dataclass(frozen=True)
class PackLockRecord:
    scope: Literal["user", "project"]
    generated_at: str
    packs: list[PackLockEntry]
    path: str


@dataclass(frozen=True)
class MethodContract:
    id: str
    name: str
    version: str
    dependencies: list[PackDependency]
    required_roles: list[str]
    work_states: list[str]
    terminal_state: str
    transitions: list[TransitionRule]
    gates: dict[str, GatePolicy]
    wip_limits: dict[str, int]


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
    approval_roles: list[str]
    path: str
    operational_status: WorkOperationalStatus = "active"
    status_reason: str | None = None
    status_by: str | None = None
    status_at: str | None = None
    delegation_id: str | None = None
    parent_work_ref: str | None = None


@dataclass(frozen=True)
class SessionRecord:
    id: str
    actor: str
    swarm_id: str
    work_id: str | None
    roles: list[str]
    integration: Integration
    provider: str
    model: str
    status: str
    path: str
    context_path: str
    launch_command: list[str]
    runtime_available: bool
    created_at: str
    exit_code: int | None = None
    context_sha256: str | None = None
    authentication_verified: bool = False
    authentication_fingerprint: str | None = None
    authentication_public_key: str | None = None
    authorization_sha256: str | None = None
    authorization_signature: str | None = None
    preparation_action_id: str | None = None


@dataclass(frozen=True)
class SessionAuthorizationRecord:
    session_id: str
    actor: str
    algorithm: str
    fingerprint: str
    payload_sha256: str
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
    version: str
    dependencies: list[PackDependency]
    scope: Literal["user", "project"]
    path: str
    required_roles: list[str]
    work_states: list[str]
    terminal_state: str
    source: PackSourceRecord | None = None
    updates: list[PackUpdateHistoryRecord] = field(default_factory=list)


@dataclass(frozen=True)
class ToolOperation:
    id: str
    name: str
    capability: str
    risk: ToolRisk
    arguments: list[str]
    inputs: list[str]
    input_rules: dict[str, str] = field(default_factory=dict)
    input_values: dict[str, list[str]] = field(default_factory=dict)
    approval_role: str | None = None
    result_kind: str | None = None


@dataclass(frozen=True)
class ToolContract:
    id: str
    name: str
    version: str
    dependencies: list[PackDependency]
    category: str
    executable: str
    authentication_reference: str | None
    operations: dict[str, ToolOperation]
    provider: str | None = None
    transport: str | None = None
    implements: str | None = None
    implements_operations: list[str] = field(default_factory=list)
    version_command: list[str] = field(default_factory=list)
    minimum_runtime_version: str | None = None
    timeout_seconds: int = 300
    max_output_bytes: int = 1048576


@dataclass(frozen=True)
class ToolPackRecord:
    id: str
    name: str
    version: str
    dependencies: list[PackDependency]
    category: str
    executable: str
    scope: Literal["user", "project"]
    path: str
    operations: list[str]
    provider: str | None = None
    transport: str | None = None
    implements: str | None = None
    implements_operations: list[str] = field(default_factory=list)
    version_command: list[str] = field(default_factory=list)
    minimum_runtime_version: str | None = None
    timeout_seconds: int = 300
    max_output_bytes: int = 1048576
    source: PackSourceRecord | None = None
    updates: list[PackUpdateHistoryRecord] = field(default_factory=list)


@dataclass(frozen=True)
class ToolAdapterRecord:
    id: str
    name: str
    version: str
    provider: str
    transport: str
    implements: str
    implements_operations: list[str]
    executable: str
    runtime_available: bool
    minimum_runtime_version: str | None
    runtime_version: str | None
    runtime_compatible: bool | None
    runtime_detail: str
    installed_scopes: list[str]
    path: str


@dataclass(frozen=True)
class ToolRuntimeProbe:
    available: bool
    executable_path: str | None
    version: str | None
    compatible: bool | None
    detail: str


@dataclass(frozen=True)
class RegistryRecord:
    id: str
    name: str
    scope: Literal["bundled", "user", "project"]
    path: str
    methods: list[str]
    tools: list[str]
    version: str | None = None
    source: str | None = None
    checksum: str | None = None
    signature_verified: bool = False


@dataclass(frozen=True)
class RegistryReleaseRecord:
    registry: str
    version: str
    archive: str
    sha256: str
    signature: str | None = None
    key_id: str | None = None


@dataclass(frozen=True)
class RegistryIndexRecord:
    id: str
    name: str
    source: str
    releases: list[RegistryReleaseRecord]


@dataclass(frozen=True)
class RegistrySourceRecord:
    registry: str
    version: str
    index: str
    archive: str
    sha256: str
    signature_verified: bool
    key_id: str | None
    installed_at: str


@dataclass(frozen=True)
class RegistryTrustKeyRecord:
    id: str
    registry: str
    algorithm: Literal["ed25519"]
    public_key: str
    fingerprint: str
    status: Literal["active", "revoked"]
    scope: Literal["user", "project"]
    path: str
    created_at: str
    revoked_at: str | None = None
    revoked_reason: str | None = None
    replaced_by: str | None = None


@dataclass(frozen=True)
class RegistryUpdateRecord:
    id: str
    registry: str
    from_version: str
    to_version: str
    from_sha256: str
    to_sha256: str
    index: str
    signature_verified: bool
    applied_at: str
    path: str


@dataclass(frozen=True)
class RegistryUpdateResult:
    registry: str
    scope: Literal["user", "project"]
    from_version: str
    to_version: str
    update_available: bool
    applied: bool
    index: str
    checksum: str
    signature_verified: bool
    record_path: str | None = None


@dataclass(frozen=True)
class CatalogPackRecord:
    kind: PackKind
    id: str
    name: str
    version: str
    dependencies: list[PackDependency]
    registry: str
    registry_scope: Literal["bundled", "user", "project"]
    path: str
    installed: bool


@dataclass(frozen=True)
class PackUpdateStep:
    kind: PackKind
    id: str
    from_version: str | None
    to_version: str
    registry: str
    sha256: str


@dataclass(frozen=True)
class PackUpdateResult:
    kind: PackKind
    id: str
    scope: Literal["user", "project"]
    from_version: str
    to_version: str
    update_available: bool
    applied: bool
    modified: bool
    packs: list[PackUpdateStep]
    history_paths: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PackRemovalStep:
    kind: PackKind
    id: str
    version: str
    sha256: str
    registry: str | None
    reason: Literal["requested", "unused-dependency"]


@dataclass(frozen=True)
class PackRemovalRecord:
    id: str
    scope: Literal["user", "project"]
    requested_kind: PackKind
    requested_id: str
    removed_at: str
    packs: list[PackRemovalStep]
    path: str


@dataclass(frozen=True)
class PackRemovalResult:
    kind: PackKind
    id: str
    scope: Literal["user", "project"]
    applied: bool
    packs: list[PackRemovalStep]
    record_path: str | None = None


@dataclass(frozen=True)
class ToolRunRecord:
    id: str
    tool_id: str
    operation_id: str
    actor: str
    swarm_id: str
    work_id: str | None
    capability: str
    risk: ToolRisk
    inputs: dict[str, str]
    command: list[str]
    runtime_available: bool
    status: str
    path: str
    created_at: str
    result_kind: str | None = None
    exit_code: int | None = None
    authentication_verified: bool = False
    authentication_fingerprint: str | None = None
    authentication_public_key: str | None = None
    authorization_sha256: str | None = None
    authorization_signature: str | None = None
    timeout_seconds: int = 300
    max_output_bytes: int = 1048576


@dataclass(frozen=True)
class ToolAuthorizationRecord:
    run_id: str
    actor: str
    algorithm: str
    fingerprint: str
    payload_sha256: str
    path: str


@dataclass(frozen=True)
class HandoffRecord:
    id: str
    swarm_id: str
    role_id: str
    from_actor: str
    to_actor: str
    authorized_by: str
    reason: str
    work_id: str | None
    created_at: str
    path: str


@dataclass(frozen=True)
class DelegationRecord:
    id: str
    parent_swarm_id: str
    parent_work_id: str
    child_swarm_id: str
    child_work_id: str
    represented_by: str
    requested_by: str
    title: str
    description: str
    acceptance_criteria: dict[str, str]
    required_artifacts: list[str]
    result_kind: str
    status: DelegationStatus
    created_at: str
    path: str
    accepted_by: str | None = None
    accepted_at: str | None = None
    collected_by: str | None = None
    collected_at: str | None = None
    blocked_from: str | None = None
    status_reason: str | None = None
    status_by: str | None = None
    status_at: str | None = None


@dataclass(frozen=True)
class StatusChangeRecord:
    id: str
    subject_type: Literal["work", "delegation"]
    subject: str
    action: str
    previous_status: str
    target_status: str
    actor: str
    reason: str
    sequence: int
    created_at: str
    path: str


@dataclass(frozen=True)
class EventRecord:
    timestamp: str
    type: str
    detail: str
    scope: str
    path: str


@dataclass(frozen=True)
class WorkspaceStatus:
    project: str
    integration: Integration
    default_method: str
    branch: str
    counts: dict[str, int]
    swarm_statuses: dict[str, int]
    work_states: dict[str, int]
    work_operational_statuses: dict[str, int]
    delegation_statuses: dict[str, int]
    session_statuses: dict[str, int]
    tool_run_statuses: dict[str, int]
    attention: dict[str, list[str]]


@dataclass(frozen=True)
class WorkspaceLockStatus:
    resource: str
    path: str
    active: bool
    operation: str | None
    pid: int | None
    hostname: str | None
    acquired_at: str | None


@dataclass(frozen=True)
class ValidationIssue:
    severity: ValidationSeverity
    code: str
    path: str
    message: str


@dataclass(frozen=True)
class ValidationReport:
    ok: bool
    project: str
    checked: dict[str, int]
    issues: list[ValidationIssue]


@dataclass(frozen=True)
class UpgradeChange:
    action: Literal["create", "update"]
    path: str
    detail: str


@dataclass(frozen=True)
class UpgradeResult:
    from_version: str
    to_version: str
    required: bool
    applied: bool
    id: str | None
    record_path: str | None
    changes: list[UpgradeChange]
    warnings: list[str]


@dataclass(frozen=True)
class ConfigureInput:
    integration: Integration
    provider: str
    model: str
    default_method: Method
    max_delegation_depth: int = 3
    force: bool = False


@dataclass(frozen=True)
class InitInput:
    target: str | None = None
    integration: Integration | None = None
    provider: str | None = None
    model: str | None = None
    default_method: Method | None = None
    max_delegation_depth: int | None = None
    force: bool = False


@dataclass(frozen=True)
class UpgradeInput:
    apply: bool = False
    id: str | None = None


@dataclass(frozen=True)
class InstallMethodInput:
    source: str
    scope: Literal["user", "project"]
    force: bool = False


@dataclass(frozen=True)
class InstallToolInput:
    source: str
    scope: Literal["user", "project"]
    force: bool = False


@dataclass(frozen=True)
class InstallToolAdapterInput:
    adapter_id: str
    scope: Literal["user", "project"]
    force: bool = False


@dataclass(frozen=True)
class InstallRegistryInput:
    source: str
    scope: Literal["user", "project"]
    force: bool = False
    version: str | None = None
    public_key: str | None = None
    require_signature: bool = False
    allow_insecure_http: bool = False


@dataclass(frozen=True)
class AddRegistryTrustKeyInput:
    id: str
    registry_id: str
    public_key: str
    scope: Literal["user", "project"]


@dataclass(frozen=True)
class RevokeRegistryTrustKeyInput:
    id: str
    scope: Literal["user", "project"]
    reason: str
    replaced_by: str | None = None


@dataclass(frozen=True)
class UpdateRegistryInput:
    id: str
    scope: Literal["user", "project"] | None = None
    version: str | None = None
    apply: bool = False
    public_key: str | None = None
    require_signature: bool = False
    allow_insecure_http: bool = False


@dataclass(frozen=True)
class InstallCatalogPackInput:
    kind: PackKind
    pack_id: str
    scope: Literal["user", "project"]
    registry_id: str | None = None
    force: bool = False


@dataclass(frozen=True)
class UpdateCatalogPackInput:
    kind: PackKind
    pack_id: str
    scope: Literal["user", "project"] | None = None
    registry_id: str | None = None
    apply: bool = False
    force: bool = False


@dataclass(frozen=True)
class RefreshPackLockInput:
    scope: Literal["user", "project"]


@dataclass(frozen=True)
class RemovePackInput:
    kind: PackKind
    pack_id: str
    scope: Literal["user", "project"] | None = None
    apply: bool = False
    with_unused_dependencies: bool = False


@dataclass(frozen=True)
class AddActorInput:
    id: str
    name: str
    kind: ActorKind
    capabilities: list[str]
    scope: Literal["user", "project"]
    description: str | None = None
    integration: Integration | None = None
    provider: str | None = None
    model: str | None = None
    represented_swarm: str | None = None
    public_key: str | None = None
    require_authentication: bool = False
    force: bool = False


@dataclass(frozen=True)
class RotateActorKeyInput:
    actor_id: str
    public_key: str
    reason: str


@dataclass(frozen=True)
class RevokeActorKeyInput:
    actor_id: str
    reason: str


@dataclass(frozen=True)
class PrepareToolAuthorizationInput:
    run_id: str
    output: str
    force: bool = False


@dataclass(frozen=True)
class LaunchToolRunInput:
    run_id: str
    signature: str | None = None


@dataclass(frozen=True)
class SetActorRuntimeInput:
    actor_id: str
    integration: Integration | None = None
    provider: str | None = None
    model: str | None = None
    clear: bool = False


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
class HandoffActorInput:
    swarm_id: str
    role_id: str
    from_actor_id: str
    to_actor_id: str
    authorized_by: str
    reason: str
    id: str | None = None
    work_id: str | None = None


@dataclass(frozen=True)
class CreateDelegationInput:
    parent_swarm_id: str
    parent_work_id: str
    child_actor_id: str
    child_work_id: str
    actor_id: str
    title: str
    acceptance_criteria: list[tuple[str, str]] = field(default_factory=list)
    required_artifacts: list[str] = field(default_factory=list)
    result_kind: str = "delegated-result"
    description: str = ""
    id: str | None = None


@dataclass(frozen=True)
class DelegationActorInput:
    delegation_id: str
    actor_id: str


@dataclass(frozen=True)
class PrepareCreateDelegationInput:
    action_id: str
    delegation: CreateDelegationInput


@dataclass(frozen=True)
class PrepareDelegationActionInput(DelegationActorInput):
    id: str = ""


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
class PrepareCreateWorkInput:
    action_id: str
    work: CreateWorkInput


@dataclass(frozen=True)
class WorkActorInput:
    swarm_id: str
    work_id: str
    actor_id: str


@dataclass(frozen=True)
class ChangeWorkStatusInput(WorkActorInput):
    reason: str = ""
    id: str | None = None


@dataclass(frozen=True)
class ChangeDelegationStatusInput(DelegationActorInput):
    reason: str = ""
    id: str | None = None


@dataclass(frozen=True)
class TransitionWorkInput(WorkActorInput):
    target_state: str = ""


@dataclass(frozen=True)
class PrepareWorkTransitionInput(TransitionWorkInput):
    id: str = ""


@dataclass(frozen=True)
class PrepareCriterionInput(WorkActorInput):
    id: str = ""
    criterion_id: str = ""


@dataclass(frozen=True)
class PrepareLifecycleAuthorizationInput:
    action_id: str
    output: str
    force: bool = False


@dataclass(frozen=True)
class ApplyLifecycleActionInput:
    action_id: str
    signature: str | None = None


@dataclass(frozen=True)
class LifecycleActionRecord:
    id: str
    action: str
    actor: str
    swarm_id: str
    work_id: str | None
    parameters: dict[str, str]
    precondition_sha256: str
    status: Literal["prepared", "applied"]
    path: str
    created_at: str
    applied_at: str | None = None
    authentication_verified: bool = False
    authentication_fingerprint: str | None = None
    authentication_public_key: str | None = None
    authorization_sha256: str | None = None
    authorization_signature: str | None = None


@dataclass(frozen=True)
class LifecycleAuthorizationRecord:
    action_id: str
    actor: str
    algorithm: str
    fingerprint: str
    payload_sha256: str
    path: str


@dataclass(frozen=True)
class AddArtifactInput(WorkActorInput):
    kind: str = ""
    uri: str = ""


@dataclass(frozen=True)
class AddEvidenceInput(WorkActorInput):
    type: str = ""
    result: Literal["success", "failure"] = "failure"
    artifact_refs: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PrepareArtifactInput(AddArtifactInput):
    id: str = ""


@dataclass(frozen=True)
class PrepareEvidenceInput(AddEvidenceInput):
    id: str = ""


@dataclass(frozen=True)
class AddApprovalInput(WorkActorInput):
    role_id: str = ""
    note: str = ""


@dataclass(frozen=True)
class PrepareApprovalInput(AddApprovalInput):
    id: str = ""


@dataclass(frozen=True)
class StartSessionInput:
    actor_id: str
    swarm_id: str
    id: str | None = None
    work_id: str | None = None
    runner: str | None = None
    launch: bool = False
    force: bool = False


@dataclass(frozen=True)
class PrepareSessionInput:
    action_id: str
    session: StartSessionInput


@dataclass(frozen=True)
class PrepareSessionAuthorizationInput:
    session_id: str
    output: str
    force: bool = False


@dataclass(frozen=True)
class LaunchSessionInput:
    session_id: str
    signature: str | None = None


@dataclass(frozen=True)
class InvokeToolInput:
    tool_id: str
    operation_id: str
    actor_id: str
    swarm_id: str
    id: str | None = None
    work_id: str | None = None
    inputs: dict[str, str] = field(default_factory=dict)
    launch: bool = False
    force: bool = False
