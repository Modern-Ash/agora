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
BUILTIN_METHODS: tuple[Method, ...] = ("spec-driven", "scrum", "kanban")
DEFAULT_SESSION_TIMEOUT_SECONDS = 3600
MAX_SESSION_TIMEOUT_SECONDS = 86400
DEFAULT_SESSION_MAX_OUTPUT_BYTES = 4 * 1024 * 1024
MAX_SESSION_MAX_OUTPUT_BYTES = 64 * 1024 * 1024


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
    required_artifacts: list[str] | None = None
    required_criterion_stage: str | None = None
    require_successful_evidence: bool = True
    required_approval_roles: list[str] = field(default_factory=list)
    require_clean_git: bool = False
    require_git_commit: bool = False
    required_evidence_types: list[str] = field(default_factory=list)


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
    criterion_stages: list[str] = field(default_factory=lambda: ["satisfied"])
    criterion_stage_roles: dict[str, list[str]] = field(default_factory=dict)


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
    child_work_refs: list[str] = field(default_factory=list)
    budget_limits: dict[str, int] | None = None
    operational_status: WorkOperationalStatus = "active"
    status_reason: str | None = None
    status_by: str | None = None
    status_at: str | None = None
    delegation_id: str | None = None
    parent_work_ref: str | None = None
    criterion_statuses: dict[str, list[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class UsageRecord:
    id: str
    swarm_id: str
    work_id: str
    actor: str
    amounts: dict[str, int]
    evidence_refs: list[str]
    created_at: str
    path: str
    action_id: str | None = None


@dataclass(frozen=True)
class UsageSummary:
    swarm_id: str
    work_id: str
    budget_limits: dict[str, int] | None
    consumed: dict[str, int]
    remaining: dict[str, int] | None
    records: int


@dataclass(frozen=True)
class GateWaiverRecord:
    id: str
    swarm_id: str
    work_id: str
    gate_id: str
    waived_criteria: list[str]
    waived_artifacts: list[str]
    waive_successful_evidence: bool
    waived_approval_roles: list[str]
    reason: str
    evidence_refs: list[str]
    authorized_by: str
    created_at: str
    path: str
    action_id: str | None = None


@dataclass(frozen=True)
class ApprovalDelegationRecord:
    id: str
    swarm_id: str
    work_id: str
    role_id: str
    from_actor: str
    to_actor: str
    reason: str
    status: Literal["active", "used", "revoked"]
    created_at: str
    path: str
    action_id: str | None = None
    used_by: str | None = None
    used_at: str | None = None
    used_action_id: str | None = None
    revoked_by: str | None = None
    revoked_at: str | None = None
    revoked_reason: str | None = None
    revocation_action_id: str | None = None


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
    timeout_seconds: int = DEFAULT_SESSION_TIMEOUT_SECONDS
    max_output_bytes: int = DEFAULT_SESSION_MAX_OUTPUT_BYTES
    output_bytes: int = 0
    termination_reason: str | None = None
    context_sha256: str | None = None
    authentication_verified: bool = False
    authentication_fingerprint: str | None = None
    authentication_public_key: str | None = None
    authorization_sha256: str | None = None
    authorization_signature: str | None = None
    preparation_action_id: str | None = None
    executor: str | None = None


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
class AdoptionInput:
    path: str | None = None
    swarm_id: str = "quickstart"
    base_branch: str | None = None
    allow_dirty: bool = False
    integration: Integration | None = None
    model: str | None = None


@dataclass(frozen=True)
class AdoptionReport:
    ok: bool
    target: str
    initialized: bool
    git_repository: bool
    branch: str | None
    checks: list[DoctorCheck]


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
    environment_required: bool = False


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
    verified_key_ids: list[str] = field(default_factory=list)
    signature_threshold: int = 0


@dataclass(frozen=True)
class RegistryReleaseSignatureRecord:
    key_id: str
    signature: str


@dataclass(frozen=True)
class RegistryReleaseRecord:
    registry: str
    version: str
    archive: str
    sha256: str
    signature: str | None = None
    key_id: str | None = None
    signatures: list[RegistryReleaseSignatureRecord] = field(default_factory=list)


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
    verified_key_ids: list[str] = field(default_factory=list)
    signature_threshold: int = 0
    transparency_required: bool = False
    transparency_proof: str | None = None
    release_archive: str | None = None


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
class TransparencyTrustKeyRecord:
    id: str
    log: str
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
class TransparencyInclusionProofRecord:
    log: str
    key_id: str
    registry: str
    version: str
    archive: str
    sha256: str
    tree_size: int
    leaf_index: int
    root_sha256: str
    inclusion_path: list[str]
    checkpoint_signature: str
    integrated_at: str
    path: str


@dataclass(frozen=True)
class TransparencyVerificationResult:
    log: str
    registry: str
    version: str
    tree_size: int
    leaf_index: int
    root_sha256: str
    key_id: str
    signature_verified: bool
    inclusion_verified: bool
    recorded: bool
    path: str | None = None


@dataclass(frozen=True)
class OrganizationTrustRootRecord:
    id: str
    algorithm: Literal["ed25519"]
    public_key: str
    fingerprint: str
    initial_public_key: str
    initial_fingerprint: str
    scope: Literal["user", "project"]
    path: str
    created_at: str
    source: str | None = None
    last_sequence: int = 0
    last_sha256: str | None = None


@dataclass(frozen=True)
class OrganizationTrustSyncStep:
    id: str
    registry: str
    action: Literal["add", "revoke", "unchanged"]


@dataclass(frozen=True)
class OrganizationTrustSyncResult:
    organization: str
    scope: Literal["user", "project"]
    sequence: int
    sha256: str
    signature_verified: bool
    applied: bool
    source: str
    steps: list[OrganizationTrustSyncStep]
    history_path: str | None = None


@dataclass(frozen=True)
class OrganizationTrustRootRotationRecord:
    organization: str
    rotation: int
    rotated_at: str
    reason: str
    from_public_key: str
    from_fingerprint: str
    to_public_key: str
    to_fingerprint: str
    bundle_sequence: int
    bundle_sha256: str | None
    previous_rotation_sha256: str | None
    old_signature: str
    new_signature: str
    sha256: str
    path: str


@dataclass(frozen=True)
class OrganizationTrustRootRotationResult:
    organization: str
    scope: Literal["user", "project"]
    rotation: int
    from_fingerprint: str
    to_fingerprint: str
    bundle_sequence: int
    sha256: str
    signature_verified: bool
    applied: bool
    source: str
    history_path: str | None = None


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
    verified_key_ids: list[str] = field(default_factory=list)
    signature_threshold: int = 0
    transparency_verified: bool = False
    transparency_proof: str | None = None


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
    transparency_verified: bool = False
    record_path: str | None = None


@dataclass(frozen=True)
class RegistryUpdateAuditEntry:
    registry: str
    scope: Literal["user", "project"]
    from_version: str
    to_version: str
    update_available: bool
    signature_verified: bool


@dataclass(frozen=True)
class RegistryUpdateAuditRecord:
    id: str
    scope: Literal["user", "project"]
    checked_at: str
    entries: list[RegistryUpdateAuditEntry]
    path: str | None = None


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
    registry_scope: Literal["bundled", "user", "project"]
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
class PackUpdateAuditEntry:
    kind: PackKind
    id: str
    scope: Literal["user", "project"]
    registry: str
    registry_scope: Literal["bundled", "user", "project"]
    from_version: str
    to_version: str
    update_available: bool
    modified: bool
    current_sha256: str
    plan_sha256: str


@dataclass(frozen=True)
class PackUpdateAuditRecord:
    id: str
    scope: Literal["user", "project"]
    checked_at: str
    entries: list[PackUpdateAuditEntry]
    path: str | None = None


@dataclass(frozen=True)
class ApplyPackUpdateAuditInput:
    id: str
    scope: Literal["user", "project"]
    force: bool = False


@dataclass(frozen=True)
class PackUpdateAuditApplicationRecord:
    id: str
    scope: Literal["user", "project"]
    audit_sha256: str
    applied_at: str
    force: bool
    packs: list[PackUpdateStep]
    history_paths: list[str]
    path: str


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
    environment_id: str | None
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
class EnvironmentPolicyRecord:
    id: str
    name: str
    allowed_tool_capabilities: list[str]
    required_approval_roles: list[str]
    require_successful_evidence: bool
    path: str


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
    budget_limits: dict[str, int] | None = None
    artifact_promotions: dict[str, str] = field(default_factory=dict)
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
class ActivityRecord:
    timestamp: str
    type: str
    summary: str
    actor: str | None
    swarm_id: str | None
    work_id: str | None
    session_id: str | None
    tool_run_id: str | None
    source: str
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
class OperationalTask:
    id: str
    kind: Literal["assign-role", "execute-work", "resume-work", "retry-session"]
    actor: str | None
    actor_kind: ActorKind | None
    swarm_id: str | None
    work_id: str | None
    role: str | None
    state: str | None
    target_states: list[str]
    blockers: list[str]
    session_id: str | None
    reason: str
    executor: str | None = None
    executor_kind: ActorKind | None = None


@dataclass(frozen=True)
class RunNextInput:
    actor_id: str | None = None
    executor_id: str | None = None
    swarm_id: str | None = None
    work_id: str | None = None
    session_id: str | None = None
    runner: str | None = None
    prepare_only: bool = False
    signature: str | None = None
    timeout_seconds: int | None = None
    max_output_bytes: int | None = None


@dataclass(frozen=True)
class RunPreview:
    task: OperationalTask
    work_title: str
    work_description: str
    method: str
    actor_capabilities: list[str]
    integration: str
    provider: str
    model: str
    authentication_required: bool
    runtime_source: Literal["configured", "override", "not-applicable"]
    timeout_seconds: int | None
    max_output_bytes: int | None
    executor: str | None = None
    executor_kind: ActorKind | None = None
    executor_capabilities: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RunLoopEvent:
    kind: Literal["step-selected", "session-finished", "loop-stopped"]
    step: int
    max_steps: int
    task: OperationalTask | None = None
    session: SessionRecord | None = None
    before_state: str | None = None
    after_state: str | None = None
    stop_reason: (
        Literal["human-attention", "no-agent-action", "no-governed-progress", "max-steps"] | None
    ) = None
    next_actions: list[OperationalTask] | None = None


@dataclass(frozen=True)
class RunLoopResult:
    sessions: list[SessionRecord]
    stop_reason: Literal["human-attention", "no-agent-action", "no-governed-progress", "max-steps"]
    next_actions: list[OperationalTask]


@dataclass(frozen=True)
class ResumeSessionInput:
    session_id: str
    replacement_id: str | None = None
    runner: str | None = None
    prepare_only: bool = False
    signature: str | None = None
    timeout_seconds: int | None = None
    max_output_bytes: int | None = None


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
class CoordinationPolicyRecord:
    mode: Literal["local", "external-lease"]
    resource_id: str | None
    executable: str | None
    arguments: list[str]
    version_arguments: list[str]
    minimum_runtime_version: str | None
    lease_seconds: int
    command_timeout_seconds: int
    path: str


@dataclass(frozen=True)
class ConfigureCoordinationInput:
    mode: Literal["local", "external-lease"]
    resource_id: str | None = None
    executable: str | None = None
    arguments: list[str] = field(default_factory=list)
    version_arguments: list[str] = field(default_factory=list)
    minimum_runtime_version: str | None = None
    lease_seconds: int = 300
    command_timeout_seconds: int = 10
    force: bool = False


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
    signature_threshold: int = 0
    require_transparency: bool = False
    allow_insecure_http: bool = False


@dataclass(frozen=True)
class AddRegistryTrustKeyInput:
    id: str
    registry_id: str
    public_key: str
    scope: Literal["user", "project"]


@dataclass(frozen=True)
class AddTransparencyTrustKeyInput:
    id: str
    log: str
    public_key: str
    scope: Literal["user", "project"]


@dataclass(frozen=True)
class RevokeTransparencyTrustKeyInput:
    id: str
    scope: Literal["user", "project"]
    reason: str
    replaced_by: str | None = None


@dataclass(frozen=True)
class VerifyTransparencyProofInput:
    source: str
    scope: Literal["user", "project"]
    record: bool = False


@dataclass(frozen=True)
class RevokeRegistryTrustKeyInput:
    id: str
    scope: Literal["user", "project"]
    reason: str
    replaced_by: str | None = None


@dataclass(frozen=True)
class AddOrganizationTrustRootInput:
    id: str
    public_key: str
    scope: Literal["user", "project"]


@dataclass(frozen=True)
class SyncOrganizationTrustInput:
    id: str
    scope: Literal["user", "project"]
    source: str | None = None
    apply: bool = False
    allow_insecure_http: bool = False


@dataclass(frozen=True)
class RotateOrganizationTrustRootInput:
    id: str
    scope: Literal["user", "project"]
    source: str
    apply: bool = False
    allow_insecure_http: bool = False


@dataclass(frozen=True)
class UpdateRegistryInput:
    id: str
    scope: Literal["user", "project"] | None = None
    version: str | None = None
    apply: bool = False
    public_key: str | None = None
    require_signature: bool = False
    signature_threshold: int | None = None
    require_transparency: bool = False
    allow_insecure_http: bool = False


@dataclass(frozen=True)
class AuditRegistryUpdatesInput:
    scope: Literal["user", "project"]
    record: bool = False
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
class AuditPackUpdatesInput:
    scope: Literal["user", "project"]
    record: bool = False


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
class PrepareActorKeyRotationInput:
    action_id: str
    swarm_id: str
    rotation: RotateActorKeyInput


@dataclass(frozen=True)
class PrepareActorKeyRevocationInput:
    action_id: str
    swarm_id: str
    target_actor_id: str
    authorized_by: str
    reason: str


@dataclass(frozen=True)
class PrepareActorKeyRecoveryInput:
    action_id: str
    swarm_id: str
    target_actor_id: str
    authorized_by: str
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
class PrepareActorRuntimeInput:
    action_id: str
    swarm_id: str
    runtime: SetActorRuntimeInput


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
class QuickstartInput:
    swarm_id: str = "quickstart"
    objective: str = "Deliver the objective"
    method: Method | None = None
    secure: bool = False
    path: str | None = None
    key_directory: str | None = None
    base_branch: str | None = None
    allow_dirty: bool = False
    integration: Integration | None = None
    provider: str | None = None
    model: str | None = None
    max_delegation_depth: int | None = None
    entrypoint: Literal["quickstart", "setup", "adopt"] = "quickstart"


@dataclass(frozen=True)
class QuickstartResult:
    project: ProjectConfiguration
    swarm: SwarmRecord
    human_actor: str
    ai_actor: str
    assignments: dict[str, str]
    secure: bool
    key_directory: str | None = None


@dataclass(frozen=True)
class PrepareActorAssignmentInput:
    action_id: str
    assignment: AssignActorInput
    authorized_by: str


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
    budget_limits: dict[str, int] | None = None
    artifact_promotions: dict[str, str] = field(default_factory=dict)


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
class DecomposeWorkInput:
    swarm_id: str
    parent_work_id: str
    child_work_id: str
    title: str
    actor_id: str
    acceptance_criteria: list[tuple[str, str]] = field(default_factory=list)
    required_artifacts: list[str] = field(default_factory=list)
    description: str = ""


@dataclass(frozen=True)
class PrepareDecomposeWorkInput:
    action_id: str
    decomposition: DecomposeWorkInput


@dataclass(frozen=True)
class WaiveGateInput:
    id: str
    swarm_id: str
    work_id: str
    gate_id: str
    actor_id: str
    reason: str
    evidence_refs: list[str]
    criteria: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    successful_evidence: bool = False
    approval_roles: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PrepareGateWaiverInput:
    action_id: str
    waiver: WaiveGateInput


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
    stage: str | None = None


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
class AddUsageInput(WorkActorInput):
    id: str
    amounts: dict[str, int] = field(default_factory=dict)
    evidence_refs: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PrepareUsageInput:
    action_id: str
    usage: AddUsageInput


@dataclass(frozen=True)
class AddApprovalInput(WorkActorInput):
    role_id: str = ""
    note: str = ""
    delegation_id: str | None = None


@dataclass(frozen=True)
class PrepareApprovalInput(AddApprovalInput):
    id: str = ""


@dataclass(frozen=True)
class DelegateApprovalInput:
    id: str
    swarm_id: str
    work_id: str
    role_id: str
    actor_id: str
    to_actor_id: str
    reason: str


@dataclass(frozen=True)
class PrepareApprovalDelegationInput:
    action_id: str
    delegation: DelegateApprovalInput


@dataclass(frozen=True)
class RevokeApprovalDelegationInput:
    delegation_id: str
    swarm_id: str
    work_id: str
    actor_id: str
    reason: str
    action_id: str | None = None


@dataclass(frozen=True)
class StartSessionInput:
    actor_id: str
    swarm_id: str
    id: str | None = None
    work_id: str | None = None
    runner: str | None = None
    launch: bool = False
    force: bool = False
    timeout_seconds: int = DEFAULT_SESSION_TIMEOUT_SECONDS
    max_output_bytes: int = DEFAULT_SESSION_MAX_OUTPUT_BYTES
    executor_id: str | None = None


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
    environment_id: str | None = None
    inputs: dict[str, str] = field(default_factory=dict)
    launch: bool = False
    force: bool = False
    read_only_sync: bool = False


@dataclass(frozen=True)
class AddEnvironmentInput:
    id: str
    name: str
    allowed_tool_capabilities: list[str] = field(default_factory=list)
    required_approval_roles: list[str] = field(default_factory=list)
    require_successful_evidence: bool = False
    force: bool = False
