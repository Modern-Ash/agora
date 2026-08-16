import hashlib
import json
import math
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable, Iterable, Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import replace
from datetime import UTC, datetime
from functools import wraps
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from agora.coordination import (
    ExternalLease,
    LeaseRunner,
    load_coordination_policy,
    render_coordination_policy,
)
from agora.filesystem import (
    agora_home,
    append_entry,
    assert_slug,
    atomic_write,
    copy_template_tree,
    find_project_root,
    template_root,
    write_new,
)
from agora.git import create_branch, current_branch, is_git_repository
from agora.identity import (
    actor_identity_from_pem,
    actor_key_from_actor,
    actor_key_from_pem,
    actor_key_from_public_key,
    assert_actor_identity_available,
    end_actor_key,
    lifecycle_authorization_payload,
    link_actor_key_replacement,
    load_actor_key,
    render_actor_key,
    session_authorization_payload,
    tool_authorization_payload,
    validate_actor_identity,
    validate_persisted_lifecycle_authorization,
    validate_persisted_session_authorization,
    validate_persisted_tool_authorization,
    verify_lifecycle_authorization,
    verify_session_authorization,
    verify_tool_authorization,
)
from agora.locking import WorkspaceLock, inspect_workspace_lock
from agora.markdown import (
    MarkdownDocument,
    optional_integer_record_attribute,
    optional_string_attribute,
    read_markdown,
    record_attribute,
    render_markdown,
    string_attribute,
    strings_attribute,
)
from agora.methods import load_method_contract
from agora.model import (
    ACTOR_KINDS,
    DEFAULT_SESSION_MAX_OUTPUT_BYTES,
    DEFAULT_SESSION_TIMEOUT_SECONDS,
    INTEGRATIONS,
    MAX_SESSION_MAX_OUTPUT_BYTES,
    MAX_SESSION_TIMEOUT_SECONDS,
    ActorKeyRecord,
    ActorRecord,
    AddActorInput,
    AddApprovalInput,
    AddArtifactInput,
    AddEnvironmentInput,
    AddEvidenceInput,
    AddOrganizationTrustRootInput,
    AddRegistryTrustKeyInput,
    AddTransparencyTrustKeyInput,
    AddUsageInput,
    ApplyLifecycleActionInput,
    ApplyPackUpdateAuditInput,
    ApprovalDelegationRecord,
    AssignActorInput,
    AuditPackUpdatesInput,
    AuditRegistryUpdatesInput,
    CatalogPackRecord,
    ChangeDelegationStatusInput,
    ChangeWorkStatusInput,
    ConfigureCoordinationInput,
    ConfigureInput,
    CoordinationPolicyRecord,
    CreateDelegationInput,
    CreateSwarmInput,
    CreateWorkInput,
    DecomposeWorkInput,
    DelegateApprovalInput,
    DelegationActorInput,
    DelegationRecord,
    DoctorCheck,
    EnvironmentPolicyRecord,
    EventRecord,
    GatePolicy,
    GateWaiverRecord,
    HandoffActorInput,
    HandoffRecord,
    InitInput,
    InstallCatalogPackInput,
    InstallMethodInput,
    InstallRegistryInput,
    InstallToolAdapterInput,
    InstallToolInput,
    Integration,
    InvokeToolInput,
    LaunchSessionInput,
    LaunchToolRunInput,
    LifecycleActionRecord,
    LifecycleAuthorizationRecord,
    Method,
    MethodContract,
    MethodPackRecord,
    OperationalTask,
    OrganizationTrustRootRecord,
    OrganizationTrustRootRotationRecord,
    OrganizationTrustRootRotationResult,
    OrganizationTrustSyncResult,
    OrganizationTrustSyncStep,
    PackKind,
    PackLockEntry,
    PackLockRecord,
    PackRemovalRecord,
    PackRemovalResult,
    PackRemovalStep,
    PackSourceRecord,
    PackUpdateAuditApplicationRecord,
    PackUpdateAuditEntry,
    PackUpdateAuditRecord,
    PackUpdateHistoryRecord,
    PackUpdateResult,
    PackUpdateStep,
    PrepareActorAssignmentInput,
    PrepareActorKeyRecoveryInput,
    PrepareActorKeyRevocationInput,
    PrepareActorKeyRotationInput,
    PrepareActorRuntimeInput,
    PrepareApprovalDelegationInput,
    PrepareApprovalInput,
    PrepareArtifactInput,
    PrepareCreateDelegationInput,
    PrepareCreateWorkInput,
    PrepareCriterionInput,
    PrepareDecomposeWorkInput,
    PrepareDelegationActionInput,
    PrepareEvidenceInput,
    PrepareGateWaiverInput,
    PrepareLifecycleAuthorizationInput,
    PrepareSessionAuthorizationInput,
    PrepareSessionInput,
    PrepareToolAuthorizationInput,
    PrepareUsageInput,
    PrepareWorkTransitionInput,
    ProjectConfiguration,
    QuickstartInput,
    QuickstartResult,
    RefreshPackLockInput,
    RegistryRecord,
    RegistryReleaseRecord,
    RegistrySourceRecord,
    RegistryTrustKeyRecord,
    RegistryUpdateAuditEntry,
    RegistryUpdateAuditRecord,
    RegistryUpdateRecord,
    RegistryUpdateResult,
    RemovePackInput,
    ResumeSessionInput,
    RevokeActorKeyInput,
    RevokeApprovalDelegationInput,
    RevokeRegistryTrustKeyInput,
    RevokeTransparencyTrustKeyInput,
    RotateActorKeyInput,
    RotateOrganizationTrustRootInput,
    RunLoopResult,
    RunNextInput,
    SessionAuthorizationRecord,
    SessionRecord,
    SetActorRuntimeInput,
    StartSessionInput,
    StatusChangeRecord,
    SwarmRecord,
    SyncOrganizationTrustInput,
    ToolAdapterRecord,
    ToolAuthorizationRecord,
    ToolContract,
    ToolPackRecord,
    ToolRisk,
    ToolRunRecord,
    ToolRuntimeProbe,
    TransitionRule,
    TransitionWorkInput,
    TransparencyInclusionProofRecord,
    TransparencyTrustKeyRecord,
    TransparencyVerificationResult,
    UpdateCatalogPackInput,
    UpdateRegistryInput,
    UpgradeInput,
    UpgradeResult,
    UsageRecord,
    UsageSummary,
    UserConfiguration,
    ValidationIssue,
    ValidationReport,
    VerifyTransparencyProofInput,
    WaiveGateInput,
    WorkActorInput,
    WorkOperationalStatus,
    WorkRecord,
    WorkspaceLockStatus,
    WorkspaceStatus,
)
from agora.organization_trust import (
    advance_organization_trust_root,
    load_organization_trust_bundle,
    load_organization_trust_root,
    load_organization_trust_root_rotation,
    organization_trust_root_from_pem,
    read_organization_trust_source,
    render_organization_trust_root,
)
from agora.packs import (
    compare_pack_versions,
    load_pack_update_history,
    pack_reference,
    pack_tree_sha256,
    pack_update_plan_sha256,
    read_pack_lock,
    read_pack_removal,
    read_pack_source,
    read_pack_update_audit,
    read_pack_update_audit_application,
    render_pack_lock,
    render_pack_removal,
    render_pack_source,
    render_pack_update,
    render_pack_update_audit,
    render_pack_update_audit_application,
    version_satisfies,
)
from agora.registries import (
    bundled_registry,
    discover_registry_packs,
    load_registry,
    read_registry_source,
    read_registry_update_audit,
    render_registry_source,
    render_registry_update,
    render_registry_update_audit,
)
from agora.registry_distribution import (
    compare_registry_versions,
    download_registry_release,
    inspect_registry_release,
)
from agora.tools import (
    CAPABILITY_PATTERN,
    DEFAULT_TOOL_MAX_OUTPUT_BYTES,
    DEFAULT_TOOL_TIMEOUT_SECONDS,
    MAX_TOOL_MAX_OUTPUT_BYTES,
    MAX_TOOL_TIMEOUT_SECONDS,
    load_tool_contract,
    probe_tool_runtime,
    validate_operation_inputs,
    validate_tool_adapter_contract,
)
from agora.transparency import (
    load_transparency_key,
    load_transparency_proof,
    render_transparency_key,
    render_transparency_proof,
    require_proof_matches_release,
    revoke_transparency_key,
    transparency_key_from_pem,
    verify_transparency_proof,
)
from agora.trust import load_trust_key, render_trust_key, revoke_trust_key, trust_key_from_pem
from agora.upgrades import (
    CURRENT_PROJECT_VERSION,
    apply_upgrade,
    compare_versions,
    plan_upgrade,
    read_upgrade_record,
    validate_version,
)


def _locked_mutation(scope: str) -> Callable:
    def decorate(method: Callable) -> Callable:
        @wraps(method)
        def guarded(self: "AgoraWorkspace", *args: object, **kwargs: object) -> object:
            resources = self._mutation_resources(scope, args, kwargs)
            with self._mutation_lock(resources, method.__name__):
                return method(self, *args, **kwargs)

        return guarded

    return decorate


class AgoraWorkspace:
    def __init__(
        self,
        cwd: Path | str | None = None,
        now: Callable[[], datetime] | None = None,
        launcher: Callable[[list[str], Path, dict[str, str]], int] | None = None,
        tool_runner: (
            Callable[[list[str], Path, dict[str, str]], subprocess.CompletedProcess[str]] | None
        ) = None,
        runtime_probe: Callable[[ToolContract, str | None], ToolRuntimeProbe] | None = None,
        lease_runner: LeaseRunner | None = None,
        lock_timeout: float | None = None,
    ) -> None:
        self.cwd = Path(cwd or Path.cwd()).resolve()
        self._now = now or (lambda: datetime.now(UTC))
        self._launcher = launcher
        self._tool_runner = tool_runner
        self._runtime_probe = runtime_probe or probe_tool_runtime
        self._lease_runner = lease_runner
        configured_timeout = os.environ.get("AGORA_LOCK_TIMEOUT", "0")
        try:
            self.lock_timeout = float(configured_timeout) if lock_timeout is None else lock_timeout
        except ValueError as error:
            raise ValueError("AGORA_LOCK_TIMEOUT must be a non-negative number") from error
        if not math.isfinite(self.lock_timeout) or self.lock_timeout < 0:
            raise ValueError("Lock timeout must be a finite non-negative number")
        self._lock_depth = 0
        self._lock_resources: tuple[Path, ...] = ()

    @_locked_mutation("home")
    def configure(self, data: ConfigureInput) -> UserConfiguration:
        self._assert_integration(data.integration)
        self._assert_delegation_depth(data.max_delegation_depth)
        self._assert_method_available(
            data.default_method,
            template_root() / "methods",
            agora_home() / "methods",
        )
        configuration = UserConfiguration(
            integration=data.integration,
            provider=data.provider,
            model=data.model,
            default_method=data.default_method,
            max_delegation_depth=data.max_delegation_depth,
        )
        home = agora_home()
        (home / "actors").mkdir(parents=True, exist_ok=True)
        (home / "methods").mkdir(parents=True, exist_ok=True)
        (home / "tools").mkdir(parents=True, exist_ok=True)
        write_new(
            home / "config.md",
            render_markdown(
                MarkdownDocument(
                    attributes={
                        "schema": "agora/user-config/v1",
                        "integration": configuration.integration,
                        "provider": configuration.provider,
                        "model": configuration.model,
                        "default-method": configuration.default_method,
                        "max-delegation-depth": configuration.max_delegation_depth,
                        "updated-at": self._timestamp(),
                    },
                    body=(
                        "# Agora user configuration\n\nDefaults used when initializing a project."
                    ),
                )
            ),
            data.force,
        )
        self._write_pack_lock("user")
        return configuration

    @_locked_mutation("target")
    def initialize(self, data: InitInput) -> ProjectConfiguration:
        target = (self.cwd / (data.target or ".")).resolve()
        target.mkdir(parents=True, exist_ok=True)
        user = self._load_user_configuration()
        configuration = ProjectConfiguration(
            project=target.name,
            version=CURRENT_PROJECT_VERSION,
            integration=data.integration or (user.integration if user else "generic"),
            provider=data.provider or (user.provider if user else "configured-by-integration"),
            model=data.model or (user.model if user else "configured-by-integration"),
            default_method=data.default_method or (user.default_method if user else "spec-driven"),
            max_delegation_depth=(
                data.max_delegation_depth
                if data.max_delegation_depth is not None
                else (user.max_delegation_depth if user else 3)
            ),
            created_at=self._timestamp(),
        )
        self._assert_integration(configuration.integration)
        self._assert_delegation_depth(configuration.max_delegation_depth)
        self._assert_method_available(
            configuration.default_method,
            template_root() / "methods",
            agora_home() / "methods",
        )

        agora = target / ".agora"
        write_new(
            agora / "project.md",
            render_markdown(
                MarkdownDocument(
                    attributes={
                        "schema": "agora/project/v1",
                        "version": configuration.version,
                        "project": configuration.project,
                        "integration": configuration.integration,
                        "provider": configuration.provider,
                        "model": configuration.model,
                        "default-method": configuration.default_method,
                        "max-delegation-depth": configuration.max_delegation_depth,
                        "created-at": configuration.created_at,
                    },
                    body=(
                        "# Agora project\n\n"
                        "This file selects the local agent integration and governance defaults."
                    ),
                )
            ),
            data.force,
        )
        replacements = {
            "PROJECT_NAME": configuration.project,
            "INTEGRATION": configuration.integration,
            "PROVIDER": configuration.provider,
            "MODEL": configuration.model,
            "DEFAULT_METHOD": configuration.default_method,
        }
        root = template_root()
        copy_template_tree(root / "project", agora, replacements, data.force)
        copy_template_tree(root / "methods", agora / "methods", replacements, data.force)
        user_methods = agora_home() / "methods"
        if user_methods.exists():
            copy_template_tree(user_methods, agora / "methods", replacements, force=True)
        copy_template_tree(root / "tools", agora / "tools", replacements, data.force)
        user_tools = agora_home() / "tools"
        if user_tools.exists():
            copy_template_tree(user_tools, agora / "tools", replacements, force=True)
        copy_template_tree(root / "commands", agora / "commands", replacements, data.force)
        self._install_integration(target, configuration.integration, replacements, force=data.force)
        self._write_pack_lock("project", project_root=target)

        project_events = agora / "events.md"
        if not project_events.exists():
            write_new(project_events, "# Project events\n\n")
        append_entry(
            project_events,
            (
                f"- {configuration.created_at} | project.initialized | "
                f"integration={configuration.integration} | method={configuration.default_method}"
            ),
        )
        return configuration

    @_locked_mutation("project")
    def upgrade(self, data: UpgradeInput) -> UpgradeResult:
        root = self.project_root()
        project = self._load_project_configuration(root)
        plan = plan_upgrade(root, project)
        if not data.apply or not plan.required:
            return plan
        upgrade_id = data.id or self._now().astimezone(UTC).strftime("upgrade-%Y%m%dt%H%M%sz")
        assert_slug(upgrade_id, "Upgrade id")
        return apply_upgrade(
            root,
            project,
            id_=upgrade_id,
            applied_at=self._timestamp(),
        )

    @_locked_mutation("project")
    def add_environment(self, data: AddEnvironmentInput) -> EnvironmentPolicyRecord:
        assert_slug(data.id, "Environment id")
        if not data.name.strip():
            raise ValueError("Environment name must not be empty")
        if not data.allowed_tool_capabilities:
            raise ValueError("Environment policy must allow at least one tool capability")
        if len(set(data.allowed_tool_capabilities)) != len(data.allowed_tool_capabilities):
            raise ValueError("Environment tool capabilities must be unique")
        for capability in data.allowed_tool_capabilities:
            if CAPABILITY_PATTERN.fullmatch(capability) is None:
                raise ValueError(f"Invalid environment tool capability: {capability}")
        if len(set(data.required_approval_roles)) != len(data.required_approval_roles):
            raise ValueError("Environment approval roles must be unique")
        for role_id in data.required_approval_roles:
            assert_slug(role_id, "Environment approval role id")

        root = self.project_root()
        path = root / ".agora" / "environments" / f"{data.id}.md"
        record = EnvironmentPolicyRecord(
            id=data.id,
            name=data.name.strip(),
            allowed_tool_capabilities=data.allowed_tool_capabilities,
            required_approval_roles=data.required_approval_roles,
            require_successful_evidence=data.require_successful_evidence,
            path=str(path),
        )
        write_new(path, self._render_environment(record), data.force)
        append_entry(
            root / ".agora" / "events.md",
            f"- {self._timestamp()} | environment.configured | environment={record.id}",
        )
        return record

    @_locked_mutation("project")
    def configure_coordination(self, data: ConfigureCoordinationInput) -> CoordinationPolicyRecord:
        if data.mode not in {"local", "external-lease"}:
            raise ValueError(f"Unsupported coordination mode: {data.mode}")
        record = CoordinationPolicyRecord(
            mode=data.mode,
            resource_id=data.resource_id,
            executable=data.executable,
            arguments=data.arguments,
            version_arguments=data.version_arguments,
            minimum_runtime_version=data.minimum_runtime_version,
            lease_seconds=data.lease_seconds,
            command_timeout_seconds=data.command_timeout_seconds,
            path=str(self.project_root() / ".agora" / "coordination.md"),
        )
        contents = render_coordination_policy(record)
        candidate = Path(record.path)
        with tempfile.TemporaryDirectory(prefix="agora-coordination-") as temporary:
            temporary_path = Path(temporary) / "coordination.md"
            temporary_path.write_text(contents, encoding="utf-8")
            load_coordination_policy(temporary_path)
        write_new(candidate, contents, data.force)
        append_entry(
            self.project_root() / ".agora" / "events.md",
            f"- {self._timestamp()} | coordination.configured | mode={record.mode}",
        )
        return record

    def show_coordination(self) -> CoordinationPolicyRecord:
        path = self.project_root() / ".agora" / "coordination.md"
        if path.is_file():
            return load_coordination_policy(path)
        return CoordinationPolicyRecord(
            mode="local",
            resource_id=None,
            executable=None,
            arguments=[],
            version_arguments=[],
            minimum_runtime_version=None,
            lease_seconds=300,
            command_timeout_seconds=10,
            path=str(path),
        )

    def show_environment(self, environment_id: str) -> EnvironmentPolicyRecord:
        assert_slug(environment_id, "Environment id")
        return self._load_environment(
            self.project_root() / ".agora" / "environments" / f"{environment_id}.md"
        )

    def list_environments(self) -> list[EnvironmentPolicyRecord]:
        root = self.project_root() / ".agora" / "environments"
        return [
            self._load_environment(path)
            for path in sorted(root.glob("*.md"))
            if path.name != "README.md"
        ]

    @_locked_mutation("scoped")
    def install_method(self, data: InstallMethodInput) -> MethodPackRecord:
        source = Path(data.source).expanduser().resolve()
        if not source.is_dir():
            raise FileNotFoundError(f"Method Pack directory not found: {source}")
        method_file = source / "METHOD.md"
        if not method_file.is_file():
            raise FileNotFoundError(f"Method Pack is missing METHOD.md: {source}")
        if (source / "SOURCE.md").exists() or (source / "updates").exists():
            raise ValueError("Direct Method Pack sources must not contain installer-owned metadata")

        contract = load_method_contract(source)
        self._assert_candidate_composition("method", contract, data.scope)
        record = self._install_method_snapshot(source, data.scope, data.force, contract)
        self._write_pack_lock(data.scope)
        return record

    @_locked_mutation("scoped")
    def install_tool(self, data: InstallToolInput) -> ToolPackRecord:
        source = Path(data.source).expanduser().resolve()
        if not source.is_dir():
            raise FileNotFoundError(f"Tool Pack directory not found: {source}")
        if not (source / "TOOL.md").is_file():
            raise FileNotFoundError(f"Tool Pack is missing TOOL.md: {source}")
        if (source / "SOURCE.md").exists() or (source / "updates").exists():
            raise ValueError("Direct Tool Pack sources must not contain installer-owned metadata")
        contract = load_tool_contract(source)
        if contract.implements is not None:
            implemented = self._implemented_tool_contract(contract.implements, data.scope)
            validate_tool_adapter_contract(contract, implemented)
        self._assert_candidate_composition("tool", contract, data.scope)
        record = self._install_tool_snapshot(source, data.scope, data.force, contract)
        self._write_pack_lock(data.scope)
        return record

    def install_tool_adapter(self, data: InstallToolAdapterInput) -> ToolPackRecord:
        assert_slug(data.adapter_id, "Tool adapter id")
        adapters = {record.id: record for record in self.list_tool_adapters()}
        adapter = adapters.get(data.adapter_id)
        if adapter is None:
            raise FileNotFoundError(f"Bundled Tool adapter not found: {data.adapter_id}")
        return self.install_tool(
            InstallToolInput(source=adapter.path, scope=data.scope, force=data.force)
        )

    def list_tool_adapters(
        self,
        available_only: bool = False,
        compatible_only: bool = False,
        check_runtime: bool = False,
    ) -> list[ToolAdapterRecord]:
        project = self._optional_project_root()
        records: list[ToolAdapterRecord] = []
        for manifest in sorted((template_root() / "adapters").glob("*/*/TOOL.md")):
            contract = load_tool_contract(manifest.parent)
            if not contract.provider or not contract.transport or not contract.implements:
                raise ValueError(f"Bundled Tool adapter is missing adapter metadata: {manifest}")
            implemented = load_tool_contract(template_root() / "tools" / contract.implements)
            validate_tool_adapter_contract(contract, implemented)
            executable_path = shutil.which(contract.executable)
            runtime_available = executable_path is not None
            if available_only and not runtime_available:
                continue
            probe = (
                self._runtime_probe(contract, executable_path)
                if check_runtime or compatible_only
                else ToolRuntimeProbe(
                    available=runtime_available,
                    executable_path=executable_path,
                    version=None,
                    compatible=None,
                    detail="Runtime version not checked",
                )
            )
            if compatible_only and probe.compatible is not True:
                continue
            installed_scopes: list[str] = []
            if (agora_home() / "tools" / contract.id / "TOOL.md").is_file():
                installed_scopes.append("user")
            if (
                project is not None
                and (project / ".agora" / "tools" / contract.id / "TOOL.md").is_file()
            ):
                installed_scopes.append("project")
            records.append(
                ToolAdapterRecord(
                    id=contract.id,
                    name=contract.name,
                    version=contract.version,
                    provider=contract.provider,
                    transport=contract.transport,
                    implements=contract.implements,
                    implements_operations=sorted(
                        contract.implements_operations or implemented.operations
                    ),
                    executable=contract.executable,
                    runtime_available=runtime_available,
                    minimum_runtime_version=contract.minimum_runtime_version,
                    runtime_version=probe.version,
                    runtime_compatible=probe.compatible,
                    runtime_detail=probe.detail,
                    installed_scopes=installed_scopes,
                    path=str(manifest.parent),
                )
            )
        return records

    def _implemented_tool_contract(self, tool_id: str, scope: str) -> ToolContract:
        assert_slug(tool_id, "Implemented Tool Pack id")
        candidates: list[Path] = []
        if scope == "project":
            project = self._optional_project_root()
            if project is not None:
                candidates.append(project / ".agora" / "tools" / tool_id)
        candidates.extend(
            [
                agora_home() / "tools" / tool_id,
                template_root() / "tools" / tool_id,
            ]
        )
        for candidate in candidates:
            if (candidate / "TOOL.md").is_file():
                return load_tool_contract(candidate)
        raise FileNotFoundError(f"Implemented Tool Pack not found: {tool_id}")

    def _install_method_snapshot(
        self,
        source: Path,
        scope: str,
        force: bool,
        contract: MethodContract | None = None,
        provenance: PackSourceRecord | None = None,
    ) -> MethodPackRecord:
        contract = contract or load_method_contract(source)
        destination_root = agora_home() if scope == "user" else self.project_root() / ".agora"
        destination = destination_root / "methods" / contract.id
        if destination.exists() and not force:
            raise FileExistsError(
                f"Method Pack already exists: {destination}. Pass --force to replace its files."
            )
        self._copy_pack_snapshot(source, destination, force, provenance)
        return self._method_pack_record(contract, scope, destination)

    def _install_tool_snapshot(
        self,
        source: Path,
        scope: str,
        force: bool,
        contract: ToolContract | None = None,
        provenance: PackSourceRecord | None = None,
    ) -> ToolPackRecord:
        contract = contract or load_tool_contract(source)
        destination_root = agora_home() if scope == "user" else self.project_root() / ".agora"
        destination = destination_root / "tools" / contract.id
        if destination.exists() and not force:
            raise FileExistsError(
                f"Tool Pack already exists: {destination}. Pass --force to replace its files."
            )
        self._copy_pack_snapshot(source, destination, force, provenance)
        return self._tool_pack_record(contract, scope, destination)

    @staticmethod
    def _copy_pack_snapshot(
        source: Path,
        destination: Path,
        force: bool,
        provenance: PackSourceRecord | None,
    ) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=f".{destination.name}-stage-", dir=destination.parent
        ) as temporary:
            staged = Path(temporary) / destination.name
            copy_template_tree(source, staged, {}, False)
            if provenance is not None:
                atomic_write(staged / "SOURCE.md", render_pack_source(provenance))
            if (staged / "METHOD.md").is_file():
                load_method_contract(staged)
            else:
                load_tool_contract(staged)
            backup = destination.with_name(f".{destination.name}-pack-backup")
            if backup.exists():
                raise RuntimeError(f"Pack backup path already exists: {backup}")
            replaced = destination.exists()
            if replaced:
                destination.replace(backup)
            try:
                staged.replace(destination)
            except Exception:
                if replaced:
                    backup.replace(destination)
                raise
            if replaced:
                shutil.rmtree(backup)

    @_locked_mutation("scoped")
    def install_registry(self, data: InstallRegistryInput) -> RegistryRecord:
        if (
            not isinstance(data.signature_threshold, int)
            or isinstance(data.signature_threshold, bool)
            or data.signature_threshold < 0
        ):
            raise ValueError("Registry signature threshold must be a non-negative integer")
        required_threshold = max(data.signature_threshold, 1 if data.require_signature else 0)
        source = Path(data.source).expanduser().resolve()
        if source.is_dir():
            if (
                data.version
                or data.public_key
                or data.require_signature
                or data.signature_threshold
                or data.require_transparency
                or data.allow_insecure_http
            ):
                raise ValueError("Remote registry options cannot be used with a local directory")
            return self._install_registry_snapshot(source, data.scope, data.force)
        if "://" not in data.source and not source.is_file():
            raise FileNotFoundError(f"Registry directory or index not found: {source}")
        with download_registry_release(
            data.source,
            version=data.version,
            public_key=data.public_key,
            require_signature=data.require_signature,
            signature_threshold=required_threshold,
            allow_insecure_http=data.allow_insecure_http,
            trusted_keys=self.list_registry_trust_keys(),
        ) as (registry_root, index, release, verified_key_ids, archive):
            if (registry_root / "SOURCE.md").exists() or (registry_root / "updates").exists():
                raise ValueError(
                    "Remote registry archives must not contain installer-owned SOURCE.md or updates"
                )
            registry = load_registry(registry_root, data.scope)
            if registry.id != index.id:
                raise ValueError(
                    f"Registry archive id {registry.id} does not match index id {index.id}"
                )
            if registry.version != release.version:
                raise ValueError(
                    f"Registry archive version {registry.version or 'missing'} does not match "
                    f"release {release.version}"
                )
            destination_root = (
                agora_home() if data.scope == "user" else self.project_root() / ".agora"
            )
            existing_source = destination_root / "registries" / registry.id / "SOURCE.md"
            inherited_transparency = (
                read_registry_source(existing_source).transparency_required
                if existing_source.is_file()
                else False
            )
            transparency_required = data.require_transparency or inherited_transparency
            transparency_proof = None
            if transparency_required:
                transparency_proof = self._required_recorded_transparency_proof(release, data.scope)
            provenance = RegistrySourceRecord(
                registry=registry.id,
                version=release.version,
                index=index.source,
                archive=archive,
                sha256=release.sha256,
                signature_verified=bool(verified_key_ids),
                key_id=verified_key_ids[0] if verified_key_ids else None,
                installed_at=self._timestamp(),
                verified_key_ids=verified_key_ids,
                signature_threshold=(
                    required_threshold if required_threshold > 0 else (1 if verified_key_ids else 0)
                ),
                transparency_required=transparency_required,
                transparency_proof=transparency_proof,
                release_archive=release.archive if transparency_required else None,
            )
            return self._install_registry_snapshot(
                registry_root,
                data.scope,
                data.force,
                provenance=provenance,
            )

    def _install_registry_snapshot(
        self,
        source: Path,
        scope: str,
        force: bool,
        *,
        provenance: RegistrySourceRecord | None = None,
        update: RegistryUpdateRecord | None = None,
    ) -> RegistryRecord:
        registry = load_registry(source, scope)
        destination_root = agora_home() if scope == "user" else self.project_root() / ".agora"
        destination = destination_root / "registries" / registry.id
        existing_source = destination / "SOURCE.md"
        if existing_source.is_file():
            existing = read_registry_source(existing_source)
            if existing.transparency_required and (
                provenance is None or not provenance.transparency_required
            ):
                raise ValueError(
                    "Registry replacement cannot lower the persisted transparency requirement"
                )
        if destination.exists() and not force:
            raise FileExistsError(
                f"Registry already exists: {destination}. Pass --force to replace its files."
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=f".{registry.id}-install-", dir=destination.parent
        ) as temporary:
            staged = Path(temporary) / registry.id
            copy_template_tree(source, staged, {}, False)
            if provenance is not None:
                atomic_write(staged / "SOURCE.md", render_registry_source(provenance))
            existing_updates = destination / "updates"
            if update is not None and existing_updates.is_dir():
                copy_template_tree(existing_updates, staged / "updates", {}, False)
            if update is not None:
                update_path = staged / "updates" / update.id / "UPDATE.md"
                if update_path.exists():
                    raise FileExistsError(f"Registry update record already exists: {update_path}")
                atomic_write(update_path, render_registry_update(update))
            load_registry(staged, scope)
            backup = destination.with_name(f".{registry.id}-backup")
            if backup.exists():
                raise FileExistsError(f"Registry backup already exists: {backup}")
            if destination.exists():
                destination.rename(backup)
            try:
                staged.rename(destination)
            except Exception:
                if backup.exists():
                    backup.rename(destination)
                raise
            if backup.exists():
                shutil.rmtree(backup)
        return load_registry(destination, scope)

    @_locked_mutation("registry-update")
    def update_registry(self, data: UpdateRegistryInput) -> RegistryUpdateResult:
        assert_slug(data.id, "Registry id")
        current, scope = self._installed_registry_for_update(data.id, data.scope)
        if current.source is None or current.version is None or current.checksum is None:
            raise ValueError(f"Registry is not a remotely installed release: {data.id}")
        provenance = read_registry_source(Path(current.path) / "SOURCE.md")
        requested_threshold = (
            provenance.signature_threshold
            if data.signature_threshold is None
            else data.signature_threshold
        )
        if (
            not isinstance(requested_threshold, int)
            or isinstance(requested_threshold, bool)
            or requested_threshold < 0
        ):
            raise ValueError("Registry signature threshold must be a non-negative integer")
        requested_threshold = max(requested_threshold, 1 if data.require_signature else 0)
        if requested_threshold < provenance.signature_threshold:
            raise ValueError(
                "Registry update cannot lower the persisted signature threshold from "
                f"{provenance.signature_threshold} to {requested_threshold}"
            )
        signature_required = requested_threshold > 0
        transparency_required = provenance.transparency_required or data.require_transparency
        trusted_keys = self.list_registry_trust_keys()
        index, release, verified_key_ids = inspect_registry_release(
            current.source,
            version=data.version,
            public_key=data.public_key,
            require_signature=signature_required,
            signature_threshold=requested_threshold,
            allow_insecure_http=data.allow_insecure_http,
            trusted_keys=trusted_keys,
        )
        if index.id != current.id:
            raise ValueError(f"Registry index id changed from {current.id} to {index.id}")
        relation = compare_registry_versions(release.version, current.version)
        if relation < 0:
            raise ValueError(
                f"Registry updates cannot downgrade {current.id} from {current.version} "
                f"to {release.version}"
            )
        if relation == 0:
            if release.sha256 != current.checksum:
                raise ValueError(
                    f"Registry release {current.id}@{current.version} changed checksum in its index"
                )
            transparency_proof = None
            if transparency_required:
                transparency_proof = self._required_recorded_transparency_proof(release, scope)
            return RegistryUpdateResult(
                registry=current.id,
                scope=scope,
                from_version=current.version,
                to_version=release.version,
                update_available=False,
                applied=False,
                index=index.source,
                checksum=release.sha256,
                signature_verified=bool(verified_key_ids),
                transparency_verified=transparency_proof is not None,
            )
        transparency_proof = None
        if transparency_required:
            transparency_proof = self._required_recorded_transparency_proof(release, scope)
        preview = RegistryUpdateResult(
            registry=current.id,
            scope=scope,
            from_version=current.version,
            to_version=release.version,
            update_available=True,
            applied=False,
            index=index.source,
            checksum=release.sha256,
            signature_verified=bool(verified_key_ids),
            transparency_verified=transparency_proof is not None,
        )
        if not data.apply:
            return preview
        with download_registry_release(
            current.source,
            version=release.version,
            public_key=data.public_key,
            require_signature=signature_required,
            signature_threshold=requested_threshold,
            allow_insecure_http=data.allow_insecure_http,
            trusted_keys=trusted_keys,
        ) as (registry_root, applied_index, applied_release, applied_key_ids, archive):
            if applied_release != release:
                raise RuntimeError("Registry index changed while applying the selected release")
            if transparency_required:
                reapplied_proof = self._required_recorded_transparency_proof(applied_release, scope)
                if reapplied_proof != transparency_proof:
                    raise RuntimeError("Registry transparency proof changed while applying update")
            if (registry_root / "SOURCE.md").exists() or (registry_root / "updates").exists():
                raise ValueError(
                    "Remote registry archives must not contain installer-owned SOURCE.md or updates"
                )
            candidate = load_registry(registry_root, scope)
            if candidate.id != current.id or candidate.version != release.version:
                raise ValueError(
                    "Registry update archive does not match the selected id and version"
                )
            applied_at = self._timestamp()
            update_id = self._now().astimezone(UTC).strftime("update-%Y%m%dt%H%M%S%fz")
            destination_root = agora_home() if scope == "user" else self.project_root() / ".agora"
            record_path = (
                destination_root / "registries" / current.id / "updates" / update_id / "UPDATE.md"
            )
            update = RegistryUpdateRecord(
                id=update_id,
                registry=current.id,
                from_version=current.version,
                to_version=release.version,
                from_sha256=current.checksum,
                to_sha256=release.sha256,
                index=applied_index.source,
                signature_verified=bool(applied_key_ids),
                applied_at=applied_at,
                path=str(record_path),
                verified_key_ids=applied_key_ids,
                signature_threshold=requested_threshold,
                transparency_verified=transparency_required,
                transparency_proof=transparency_proof,
            )
            provenance = RegistrySourceRecord(
                registry=current.id,
                version=release.version,
                index=applied_index.source,
                archive=archive,
                sha256=release.sha256,
                signature_verified=bool(applied_key_ids),
                key_id=applied_key_ids[0] if applied_key_ids else None,
                installed_at=applied_at,
                verified_key_ids=applied_key_ids,
                signature_threshold=requested_threshold,
                transparency_required=transparency_required,
                transparency_proof=transparency_proof,
                release_archive=release.archive if transparency_required else None,
            )
            self._install_registry_snapshot(
                registry_root,
                scope,
                True,
                provenance=provenance,
                update=update,
            )
        return RegistryUpdateResult(
            registry=current.id,
            scope=scope,
            from_version=current.version,
            to_version=release.version,
            update_available=True,
            applied=True,
            index=applied_index.source,
            checksum=release.sha256,
            signature_verified=bool(applied_key_ids),
            transparency_verified=transparency_required,
            record_path=str(record_path),
        )

    def audit_registry_updates(self, data: AuditRegistryUpdatesInput) -> RegistryUpdateAuditRecord:
        if data.scope not in {"user", "project"}:
            raise ValueError(f"Unsupported registry update audit scope: {data.scope}")
        candidates = [
            item
            for item in self.list_registries()
            if item.scope == data.scope and item.source is not None
        ]
        entries: list[RegistryUpdateAuditEntry] = []
        for registry in candidates:
            result = self.update_registry(
                UpdateRegistryInput(
                    id=registry.id,
                    scope=data.scope,
                    allow_insecure_http=data.allow_insecure_http,
                )
            )
            entries.append(
                RegistryUpdateAuditEntry(
                    registry=result.registry,
                    scope=result.scope,
                    from_version=result.from_version,
                    to_version=result.to_version,
                    update_available=result.update_available,
                    signature_verified=result.signature_verified,
                )
            )
        audit_id = self._now().astimezone(UTC).strftime("audit-%Y%m%dt%H%M%S%fz")
        root = agora_home() if data.scope == "user" else self.project_root() / ".agora"
        path = root / "notifications" / "registry-updates" / audit_id / "AUDIT.md"
        record = RegistryUpdateAuditRecord(
            id=audit_id,
            scope=data.scope,
            checked_at=self._timestamp(),
            entries=entries,
            path=str(path) if data.record else None,
        )
        if not data.record:
            return record
        return self._record_registry_update_audit(data, record)

    @_locked_mutation("scoped")
    def _record_registry_update_audit(
        self, data: AuditRegistryUpdatesInput, record: RegistryUpdateAuditRecord
    ) -> RegistryUpdateAuditRecord:
        assert record.path is not None
        path = Path(record.path)
        if path.exists():
            raise FileExistsError(f"Registry update audit already exists: {path}")
        atomic_write(path, render_registry_update_audit(record))
        return read_registry_update_audit(path)

    @_locked_mutation("scoped")
    def add_registry_trust_key(self, data: AddRegistryTrustKeyInput) -> RegistryTrustKeyRecord:
        assert_slug(data.id, "Registry trust key id")
        assert_slug(data.registry_id, "Registry trust key registry")
        root = agora_home() if data.scope == "user" else self.project_root() / ".agora"
        destination = root / "trust" / "keys" / f"{data.id}.md"
        if destination.exists():
            raise FileExistsError(
                f"Registry trust key already exists: {destination}. Rotate with a new key id."
            )
        record = trust_key_from_pem(
            id_=data.id,
            registry=data.registry_id,
            public_key_path=Path(data.public_key).expanduser().resolve(),
            scope=data.scope,
            path=destination,
            created_at=self._timestamp(),
        )
        atomic_write(destination, render_trust_key(record))
        return load_trust_key(destination, data.scope)

    def list_registry_trust_keys(
        self, registry_id: str | None = None
    ) -> list[RegistryTrustKeyRecord]:
        if registry_id is not None:
            assert_slug(registry_id, "Registry id")
        records: list[RegistryTrustKeyRecord] = []
        project = self._optional_project_root()
        if project is not None:
            records.extend(self._trust_keys_at(project / ".agora" / "trust" / "keys", "project"))
        records.extend(self._trust_keys_at(agora_home() / "trust" / "keys", "user"))
        return [item for item in records if registry_id is None or item.registry == registry_id]

    @_locked_mutation("scoped")
    def revoke_registry_trust_key(
        self, data: RevokeRegistryTrustKeyInput
    ) -> RegistryTrustKeyRecord:
        assert_slug(data.id, "Registry trust key id")
        root = agora_home() if data.scope == "user" else self.project_root() / ".agora"
        path = root / "trust" / "keys" / f"{data.id}.md"
        if not path.is_file():
            raise FileNotFoundError(f"Registry trust key not found: {path}")
        record = load_trust_key(path, data.scope)
        if data.replaced_by is not None:
            assert_slug(data.replaced_by, "Replacement registry trust key id")
            replacement_path = path.with_name(f"{data.replaced_by}.md")
            if not replacement_path.is_file():
                raise FileNotFoundError(
                    f"Replacement registry trust key not found: {replacement_path}"
                )
            replacement = load_trust_key(replacement_path, data.scope)
            if replacement.registry != record.registry or replacement.status != "active":
                raise ValueError(
                    "Replacement registry trust key must be active for the same registry"
                )
        revoked = revoke_trust_key(
            record,
            revoked_at=self._timestamp(),
            reason=data.reason,
            replaced_by=data.replaced_by,
        )
        atomic_write(path, render_trust_key(revoked))
        return load_trust_key(path, data.scope)

    @_locked_mutation("scoped")
    def add_transparency_trust_key(
        self, data: AddTransparencyTrustKeyInput
    ) -> TransparencyTrustKeyRecord:
        assert_slug(data.id, "Transparency trust key id")
        assert_slug(data.log, "Transparency log id")
        root = agora_home() if data.scope == "user" else self.project_root() / ".agora"
        destination = root / "trust" / "transparency" / f"{data.id}.md"
        if destination.exists():
            raise FileExistsError(
                f"Transparency trust key already exists: {destination}. Rotate with a new key id."
            )
        record = transparency_key_from_pem(
            id_=data.id,
            log=data.log,
            public_key_path=Path(data.public_key).expanduser().resolve(),
            scope=data.scope,
            path=destination,
            created_at=self._timestamp(),
        )
        atomic_write(destination, render_transparency_key(record))
        return load_transparency_key(destination, data.scope)

    def list_transparency_trust_keys(
        self, log: str | None = None
    ) -> list[TransparencyTrustKeyRecord]:
        if log is not None:
            assert_slug(log, "Transparency log id")
        records: list[TransparencyTrustKeyRecord] = []
        project = self._optional_project_root()
        if project is not None:
            records.extend(
                self._transparency_keys_at(project / ".agora" / "trust" / "transparency", "project")
            )
        records.extend(self._transparency_keys_at(agora_home() / "trust" / "transparency", "user"))
        return [item for item in records if log is None or item.log == log]

    @_locked_mutation("scoped")
    def revoke_transparency_trust_key(
        self, data: RevokeTransparencyTrustKeyInput
    ) -> TransparencyTrustKeyRecord:
        assert_slug(data.id, "Transparency trust key id")
        root = agora_home() if data.scope == "user" else self.project_root() / ".agora"
        path = root / "trust" / "transparency" / f"{data.id}.md"
        if not path.is_file():
            raise FileNotFoundError(f"Transparency trust key not found: {path}")
        record = load_transparency_key(path, data.scope)
        if data.replaced_by is not None:
            assert_slug(data.replaced_by, "Replacement transparency trust key id")
            replacement_path = path.with_name(f"{data.replaced_by}.md")
            if not replacement_path.is_file():
                raise FileNotFoundError(
                    f"Replacement transparency trust key not found: {replacement_path}"
                )
            replacement = load_transparency_key(replacement_path, data.scope)
            if replacement.log != record.log or replacement.status != "active":
                raise ValueError(
                    "Replacement transparency trust key must be active for the same log"
                )
        revoked = revoke_transparency_key(
            record,
            revoked_at=self._timestamp(),
            reason=data.reason,
            replaced_by=data.replaced_by,
        )
        atomic_write(path, render_transparency_key(revoked))
        return load_transparency_key(path, data.scope)

    @_locked_mutation("scoped")
    def verify_transparency_inclusion(
        self, data: VerifyTransparencyProofInput
    ) -> TransparencyVerificationResult:
        if data.scope not in {"user", "project"}:
            raise ValueError(f"Unsupported transparency proof scope: {data.scope}")
        source = Path(data.source).expanduser().resolve()
        proof = load_transparency_proof(source)
        key = next(
            (key for key in self.list_transparency_trust_keys() if key.id == proof.key_id),
            None,
        )
        if key is None:
            raise ValueError(
                f"Trusted transparency key not found: {proof.key_id} for log {proof.log}"
            )
        if key.status != "active":
            raise ValueError(f"Transparency trust key is revoked: {proof.key_id}")
        verify_transparency_proof(proof, key)
        path: Path | None = None
        if data.record:
            root = agora_home() if data.scope == "user" else self.project_root() / ".agora"
            path = root / "transparency" / proof.log / proof.registry / proof.version / "PROOF.md"
            if path.exists():
                raise FileExistsError(f"Transparency proof already recorded: {path}")
            persisted = replace(proof, path=str(path))
            atomic_write(path, render_transparency_proof(persisted))
            verify_transparency_proof(load_transparency_proof(path), key)
        return TransparencyVerificationResult(
            log=proof.log,
            registry=proof.registry,
            version=proof.version,
            tree_size=proof.tree_size,
            leaf_index=proof.leaf_index,
            root_sha256=proof.root_sha256,
            key_id=proof.key_id,
            signature_verified=True,
            inclusion_verified=True,
            recorded=data.record,
            path=str(path) if path is not None else None,
        )

    def _required_recorded_transparency_proof(
        self, release: RegistryReleaseRecord, scope: str
    ) -> str:
        root = agora_home() if scope == "user" else self.project_root() / ".agora"
        candidates = sorted(
            (root / "transparency").glob(f"*/{release.registry}/{release.version}/PROOF.md")
        )
        if not candidates:
            raise FileNotFoundError(
                "Required recorded transparency proof not found for "
                f"{release.registry}@{release.version}"
            )
        errors: list[str] = []
        for path in candidates:
            try:
                proof = load_transparency_proof(path)
                require_proof_matches_release(proof, release)
                key = next(
                    (key for key in self.list_transparency_trust_keys() if key.id == proof.key_id),
                    None,
                )
                if key is None:
                    raise ValueError(f"Transparency trust key not found: {proof.key_id}")
                if key.status != "active":
                    raise ValueError(f"Transparency trust key is revoked: {proof.key_id}")
                verify_transparency_proof(proof, key)
                return path.relative_to(root).as_posix()
            except Exception as error:
                errors.append(str(error))
        raise ValueError(
            f"No valid recorded transparency proof for {release.registry}@{release.version}: "
            + "; ".join(errors)
        )

    @_locked_mutation("scoped")
    def add_organization_trust_root(
        self, data: AddOrganizationTrustRootInput
    ) -> OrganizationTrustRootRecord:
        assert_slug(data.id, "Organization trust id")
        root = agora_home() if data.scope == "user" else self.project_root() / ".agora"
        destination = root / "trust" / "organizations" / data.id / "ROOT.md"
        if destination.exists():
            raise FileExistsError(f"Organization trust root already exists: {destination}")
        record = organization_trust_root_from_pem(
            id_=data.id,
            public_key_path=Path(data.public_key).expanduser().resolve(),
            scope=data.scope,
            path=destination,
            created_at=self._timestamp(),
        )
        atomic_write(destination, render_organization_trust_root(record))
        return load_organization_trust_root(destination, data.scope)

    def get_organization_trust_root(self, id_: str, scope: str) -> OrganizationTrustRootRecord:
        assert_slug(id_, "Organization trust id")
        root = agora_home() if scope == "user" else self.project_root() / ".agora"
        path = root / "trust" / "organizations" / id_ / "ROOT.md"
        if not path.is_file():
            raise FileNotFoundError(f"Organization trust root not found: {path}")
        return load_organization_trust_root(path, scope)

    @_locked_mutation("scoped")
    def rotate_organization_trust_root(
        self, data: RotateOrganizationTrustRootInput
    ) -> OrganizationTrustRootRotationResult:
        root_record = self.get_organization_trust_root(data.id, data.scope)
        contents, resolved_source = read_organization_trust_source(
            data.source, allow_insecure_http=data.allow_insecure_http
        )
        scope_root = agora_home() if data.scope == "user" else self.project_root() / ".agora"
        organization_root = scope_root / "trust" / "organizations" / data.id
        rotation_paths = sorted((organization_root / "rotations").glob("*.md"))
        previous = (
            load_organization_trust_root_rotation(
                rotation_paths[-1].read_bytes(), scope=data.scope, path=str(rotation_paths[-1])
            )
            if rotation_paths
            else None
        )
        rotation = load_organization_trust_root_rotation(contents, scope=data.scope)
        expected_rotation = 1 if previous is None else previous.rotation + 1
        expected_previous = None if previous is None else previous.sha256
        if rotation.organization != data.id:
            raise ValueError(
                f"Organization trust root rotation belongs to {rotation.organization}, "
                f"expected {data.id}"
            )
        if rotation.rotation != expected_rotation:
            raise ValueError(
                f"Organization trust root rotation must be {expected_rotation}, "
                f"got {rotation.rotation}"
            )
        if rotation.previous_rotation_sha256 != expected_previous:
            raise ValueError("Organization trust root rotation does not continue its history")
        if (
            rotation.from_public_key != root_record.public_key
            or rotation.from_fingerprint != root_record.fingerprint
        ):
            raise ValueError("Organization trust root rotation does not start at the active root")
        if (
            rotation.bundle_sequence != root_record.last_sequence
            or rotation.bundle_sha256 != root_record.last_sha256
        ):
            raise ValueError(
                "Organization trust root rotation does not bind the current feed state"
            )

        history_path = organization_root / "rotations" / f"{rotation.rotation:020d}.md"
        result = OrganizationTrustRootRotationResult(
            organization=data.id,
            scope=data.scope,
            rotation=rotation.rotation,
            from_fingerprint=rotation.from_fingerprint,
            to_fingerprint=rotation.to_fingerprint,
            bundle_sequence=rotation.bundle_sequence,
            sha256=rotation.sha256,
            signature_verified=True,
            applied=data.apply,
            source=resolved_source,
            history_path=str(history_path) if data.apply else None,
        )
        if not data.apply:
            return result
        if history_path.exists():
            raise FileExistsError(
                f"Organization trust root rotation already exists: {history_path}"
            )

        trust_root = scope_root / "trust"
        with tempfile.TemporaryDirectory(prefix=".trust-stage-", dir=scope_root) as temporary:
            staged = Path(temporary) / "trust"
            copy_template_tree(trust_root, staged, {}, False)
            staged_organization = staged / "organizations" / data.id
            staged_history = staged_organization / "rotations" / history_path.name
            atomic_write(staged_history, contents.decode("utf-8"))
            updated_root = replace(
                root_record,
                public_key=rotation.to_public_key,
                fingerprint=rotation.to_fingerprint,
                created_at=rotation.rotated_at,
            )
            atomic_write(
                staged_organization / "ROOT.md", render_organization_trust_root(updated_root)
            )
            backup = scope_root / ".trust-backup"
            if backup.exists():
                raise FileExistsError(f"Organization trust backup already exists: {backup}")
            trust_root.replace(backup)
            try:
                staged.replace(trust_root)
            except Exception:
                backup.replace(trust_root)
                raise
            shutil.rmtree(backup)
        return result

    @_locked_mutation("scoped")
    def sync_organization_trust(
        self, data: SyncOrganizationTrustInput
    ) -> OrganizationTrustSyncResult:
        root_record = self.get_organization_trust_root(data.id, data.scope)
        source = data.source or root_record.source
        if source is None:
            raise ValueError("First organization trust sync requires --source")
        contents, resolved_source = read_organization_trust_source(
            source, allow_insecure_http=data.allow_insecure_http
        )
        sequence, previous_sha256, incoming, checksum, _ = load_organization_trust_bundle(
            contents, root=root_record
        )
        expected_sequence = root_record.last_sequence + 1
        if sequence != expected_sequence:
            raise ValueError(
                f"Organization trust bundle sequence must be {expected_sequence}, got {sequence}"
            )
        if previous_sha256 != root_record.last_sha256:
            raise ValueError("Organization trust bundle does not continue the applied history")

        scope_root = agora_home() if data.scope == "user" else self.project_root() / ".agora"
        keys_root = scope_root / "trust" / "keys"
        existing = {item.id: item for item in self._trust_keys_at(keys_root, data.scope)}
        projected = dict(existing)
        steps: list[OrganizationTrustSyncStep] = []
        for item in incoming:
            path = keys_root / f"{item.id}.md"
            candidate = replace(item, path=str(path))
            current = existing.get(item.id)
            action = self._organization_trust_action(current, candidate)
            steps.append(
                OrganizationTrustSyncStep(
                    id=item.id,
                    registry=item.registry,
                    action=action,
                )
            )
            if action != "unchanged":
                projected[item.id] = candidate
        for item in projected.values():
            if item.replaced_by is None:
                continue
            replacement = projected.get(item.replaced_by)
            if replacement is None:
                raise ValueError(
                    f"Organization trust replacement key does not exist: {item.replaced_by}"
                )
            if replacement.registry != item.registry or replacement.status != "active":
                raise ValueError(
                    "Organization trust replacement key must be active for the same registry"
                )

        history_path = (
            scope_root / "trust" / "organizations" / data.id / "history" / f"{sequence:020d}.md"
        )
        result = OrganizationTrustSyncResult(
            organization=data.id,
            scope=data.scope,
            sequence=sequence,
            sha256=checksum,
            signature_verified=True,
            applied=data.apply,
            source=resolved_source,
            steps=steps,
            history_path=str(history_path) if data.apply else None,
        )
        if not data.apply:
            return result
        if history_path.exists():
            raise FileExistsError(f"Organization trust history already exists: {history_path}")
        self._apply_organization_trust_sync(
            scope_root=scope_root,
            root_record=root_record,
            resolved_source=resolved_source,
            sequence=sequence,
            checksum=checksum,
            contents=contents,
            incoming=incoming,
            steps=steps,
        )
        return result

    @staticmethod
    def _organization_trust_action(
        current: RegistryTrustKeyRecord | None, incoming: RegistryTrustKeyRecord
    ) -> str:
        if current is None:
            return "add"
        immutable_current = (
            current.registry,
            current.algorithm,
            current.public_key,
            current.fingerprint,
            current.created_at,
        )
        immutable_incoming = (
            incoming.registry,
            incoming.algorithm,
            incoming.public_key,
            incoming.fingerprint,
            incoming.created_at,
        )
        if immutable_current != immutable_incoming:
            raise ValueError(f"Organization trust bundle attempts to redefine key {incoming.id}")
        if current.status == "revoked" and incoming.status == "active":
            raise PermissionError(
                f"Organization trust bundle attempts to reactivate revoked key {incoming.id}"
            )
        if current.status == "active" and incoming.status == "revoked":
            return "revoke"
        revocation_current = (
            current.revoked_at,
            current.revoked_reason,
            current.replaced_by,
        )
        revocation_incoming = (
            incoming.revoked_at,
            incoming.revoked_reason,
            incoming.replaced_by,
        )
        if revocation_current != revocation_incoming:
            raise ValueError(
                f"Organization trust bundle attempts to rewrite key {incoming.id} history"
            )
        return "unchanged"

    @staticmethod
    def _apply_organization_trust_sync(
        *,
        scope_root: Path,
        root_record: OrganizationTrustRootRecord,
        resolved_source: str,
        sequence: int,
        checksum: str,
        contents: bytes,
        incoming: list[RegistryTrustKeyRecord],
        steps: list[OrganizationTrustSyncStep],
    ) -> None:
        trust_root = scope_root / "trust"
        scope_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".trust-stage-", dir=scope_root) as temporary:
            staged = Path(temporary) / "trust"
            if trust_root.exists():
                copy_template_tree(trust_root, staged, {}, False)
            else:
                staged.mkdir(parents=True)
            staged_keys = staged / "keys"
            for item, step in zip(incoming, steps, strict=True):
                if step.action == "unchanged":
                    continue
                staged_path = staged_keys / f"{item.id}.md"
                atomic_write(staged_path, render_trust_key(replace(item, path=str(staged_path))))
            organization_root = staged / "organizations" / root_record.id
            history_path = organization_root / "history" / f"{sequence:020d}.md"
            if history_path.exists():
                raise FileExistsError(f"Organization trust history already exists: {history_path}")
            try:
                history_contents = contents.decode("utf-8")
            except UnicodeDecodeError as error:
                raise ValueError("Organization trust bundle must be UTF-8") from error
            atomic_write(history_path, history_contents)
            updated_root = advance_organization_trust_root(
                root_record,
                source=resolved_source,
                sequence=sequence,
                checksum=checksum,
            )
            atomic_write(
                organization_root / "ROOT.md", render_organization_trust_root(updated_root)
            )
            backup = scope_root / ".trust-backup"
            if backup.exists():
                raise FileExistsError(f"Organization trust backup already exists: {backup}")
            replaced = trust_root.exists()
            if replaced:
                trust_root.replace(backup)
            try:
                staged.replace(trust_root)
            except Exception:
                if replaced:
                    backup.replace(trust_root)
                raise
            if replaced:
                shutil.rmtree(backup)

    def list_registries(self) -> list[RegistryRecord]:
        records = [bundled_registry()]
        records.extend(self._registries_at(agora_home() / "registries", "user"))
        project = self._optional_project_root()
        if project is not None:
            records.extend(self._registries_at(project / ".agora" / "registries", "project"))
        priority = {"project": 0, "user": 1, "bundled": 2}
        return sorted(records, key=lambda item: (priority[item.scope], item.id))

    def search_catalog(
        self,
        kind: str | None = None,
        query: str | None = None,
        registry_id: str | None = None,
    ) -> list[CatalogPackRecord]:
        if kind is not None and kind not in {"method", "tool"}:
            raise ValueError(f"Unsupported pack kind: {kind}")
        if registry_id is not None:
            assert_slug(registry_id, "Registry id")
        normalized = query.lower().strip() if query else None
        project = self._optional_project_root()
        records: list[CatalogPackRecord] = []
        for registry in self.list_registries():
            if registry_id is not None and registry.id != registry_id:
                continue
            for pack in discover_registry_packs(registry):
                if kind is not None and pack.kind != kind:
                    continue
                if (
                    normalized
                    and normalized not in pack.id.lower()
                    and normalized not in pack.name.lower()
                ):
                    continue
                installed = (agora_home() / f"{pack.kind}s" / pack.id).is_dir() or (
                    project is not None
                    and (project / ".agora" / f"{pack.kind}s" / pack.id).is_dir()
                )
                records.append(CatalogPackRecord(**{**pack.__dict__, "installed": installed}))
        priority = {"project": 0, "user": 1, "bundled": 2}
        return sorted(
            records,
            key=lambda item: (item.kind, item.id, priority[item.registry_scope], item.registry),
        )

    @_locked_mutation("scoped")
    def install_catalog_pack(
        self, data: InstallCatalogPackInput
    ) -> MethodPackRecord | ToolPackRecord:
        if data.kind not in {"method", "tool"}:
            raise ValueError(f"Unsupported pack kind: {data.kind}")
        if data.scope is not None and data.scope not in {"user", "project"}:
            raise ValueError(f"Unsupported pack scope: {data.scope}")
        assert_slug(data.pack_id, "Pack id")
        matches = [
            item
            for item in self.search_catalog(data.kind, registry_id=data.registry_id)
            if item.id == data.pack_id
        ]
        if not matches:
            origin = f" in registry {data.registry_id}" if data.registry_id else ""
            raise FileNotFoundError(f"Catalog pack not found: {data.kind}/{data.pack_id}{origin}")
        selected = matches[0]
        self._assert_pack_destination_available(data.kind, data.pack_id, data.scope, data.force)
        plan = self._resolve_catalog_install(selected, data.scope, data.force)
        for pack in plan:
            self._assert_pack_destination_available(pack.kind, pack.id, data.scope, data.force)
        update_id = (
            self._now().astimezone(UTC).strftime("update-%Y%m%dt%H%M%S%fz")
            if any(self._pack_destination(pack.kind, pack.id, data.scope).exists() for pack in plan)
            else None
        )
        records, _ = self._apply_catalog_plan(
            plan,
            data.scope,
            update_id=update_id,
            applied_at=self._timestamp() if update_id else None,
        )
        self._write_pack_lock(data.scope)
        return next(
            record
            for record in records
            if isinstance(record, MethodPackRecord if selected.kind == "method" else ToolPackRecord)
            and record.id == selected.id
        )

    @_locked_mutation("pack-update")
    def update_catalog_pack(self, data: UpdateCatalogPackInput) -> PackUpdateResult:
        if data.kind not in {"method", "tool"}:
            raise ValueError(f"Unsupported pack kind: {data.kind}")
        if data.scope is not None and data.scope not in {"user", "project"}:
            raise ValueError(f"Unsupported pack scope: {data.scope}")
        assert_slug(data.pack_id, "Pack id")
        current, scope = self._installed_pack_for_update(data.kind, data.pack_id, data.scope)
        if current.source is None:
            raise ValueError(f"Pack was not installed from a catalog: {data.kind}/{data.pack_id}")
        registry_id = data.registry_id or current.source.registry
        matches = [
            item
            for item in self.search_catalog(data.kind, registry_id=registry_id)
            if item.id == data.pack_id
        ]
        if not matches:
            raise FileNotFoundError(
                f"Catalog pack not found: {data.kind}/{data.pack_id} in registry {registry_id}"
            )
        selected = next(
            (item for item in matches if item.registry_scope == current.source.registry_scope),
            matches[0],
        )
        candidate_sha256 = pack_tree_sha256(Path(selected.path))
        relation = compare_pack_versions(selected.version, current.version)
        if relation < 0:
            raise ValueError(
                f"Pack updates cannot downgrade {data.kind}/{data.pack_id} from "
                f"{current.version} to {selected.version}"
            )
        if relation == 0 and candidate_sha256 != current.source.sha256:
            raise ValueError(
                f"Catalog pack {data.kind}/{data.pack_id}@{current.version} changed content"
            )

        current_root = Path(current.path)
        root_modified = pack_tree_sha256(current_root) != current.source.sha256
        if relation == 0 and not root_modified:
            return PackUpdateResult(
                kind=data.kind,
                id=data.pack_id,
                scope=scope,
                from_version=current.version,
                to_version=selected.version,
                update_available=False,
                applied=False,
                modified=False,
                packs=[],
            )

        plan = self._resolve_catalog_install(selected, scope, True)
        installed = self._installed_pack_contracts(scope)
        modified_packs: list[str] = []
        steps: list[PackUpdateStep] = []
        for pack in plan:
            key = (pack.kind, pack.id)
            existing = installed.get(key)
            destination = self._pack_destination(pack.kind, pack.id, scope)
            if existing is not None:
                source_path = destination / "SOURCE.md"
                provenance = read_pack_source(source_path) if source_path.is_file() else None
                if provenance is None or pack_tree_sha256(destination) != provenance.sha256:
                    modified_packs.append(f"{pack.kind}/{pack.id}")
            steps.append(
                PackUpdateStep(
                    kind=pack.kind,
                    id=pack.id,
                    from_version=existing.version if existing is not None else None,
                    to_version=pack.version,
                    registry=pack.registry,
                    registry_scope=pack.registry_scope,
                    sha256=pack_tree_sha256(Path(pack.path)),
                )
            )
        modified = bool(modified_packs)
        result = PackUpdateResult(
            kind=data.kind,
            id=data.pack_id,
            scope=scope,
            from_version=current.version,
            to_version=selected.version,
            update_available=True,
            applied=False,
            modified=modified,
            packs=steps,
        )
        if not data.apply:
            return result
        if modified and not data.force:
            raise ValueError(
                "Pack update would replace locally modified or untracked packs: "
                f"{', '.join(modified_packs)}. Pass --force after reviewing the changes."
            )
        update_id = self._now().astimezone(UTC).strftime("update-%Y%m%dt%H%M%S%fz")
        _, history_paths = self._apply_catalog_plan(
            plan,
            scope,
            update_id=update_id,
            applied_at=self._timestamp(),
        )
        self._write_pack_lock(scope)
        return PackUpdateResult(
            **{**result.__dict__, "applied": True, "history_paths": history_paths}
        )

    def audit_pack_updates(self, data: AuditPackUpdatesInput) -> PackUpdateAuditRecord:
        if data.scope not in {"user", "project"}:
            raise ValueError(f"Unsupported pack update audit scope: {data.scope}")
        root = agora_home() if data.scope == "user" else self.project_root() / ".agora"
        installed = self._installed_pack_contracts(data.scope)
        entries: list[PackUpdateAuditEntry] = []
        for (kind, pack_id), _ in sorted(installed.items()):
            source_path = root / f"{kind}s" / pack_id / "SOURCE.md"
            if not source_path.is_file():
                continue
            source = read_pack_source(source_path)
            result = self.update_catalog_pack(
                UpdateCatalogPackInput(
                    kind=kind,  # type: ignore[arg-type]
                    pack_id=pack_id,
                    scope=data.scope,
                )
            )
            entries.append(
                PackUpdateAuditEntry(
                    kind=kind,  # type: ignore[arg-type]
                    id=pack_id,
                    scope=data.scope,
                    registry=source.registry,
                    registry_scope=source.registry_scope,
                    from_version=result.from_version,
                    to_version=result.to_version,
                    update_available=result.update_available,
                    modified=result.modified,
                    current_sha256=pack_tree_sha256(root / f"{kind}s" / pack_id),
                    plan_sha256=pack_update_plan_sha256(result.packs),
                )
            )
        audit_id = self._now().astimezone(UTC).strftime("audit-%Y%m%dt%H%M%S%fz")
        path = root / "notifications" / "pack-updates" / audit_id / "AUDIT.md"
        record = PackUpdateAuditRecord(
            id=audit_id,
            scope=data.scope,
            checked_at=self._timestamp(),
            entries=entries,
            path=str(path) if data.record else None,
        )
        if not data.record:
            return record
        return self._record_pack_update_audit(data, record)

    @_locked_mutation("scoped")
    def _record_pack_update_audit(
        self, data: AuditPackUpdatesInput, record: PackUpdateAuditRecord
    ) -> PackUpdateAuditRecord:
        assert record.path is not None
        path = Path(record.path)
        if path.exists():
            raise FileExistsError(f"Pack update audit already exists: {path}")
        atomic_write(path, render_pack_update_audit(record))
        return read_pack_update_audit(path)

    @_locked_mutation("pack-update")
    def apply_pack_update_audit(
        self, data: ApplyPackUpdateAuditInput
    ) -> PackUpdateAuditApplicationRecord:
        assert_slug(data.id, "Pack update audit id")
        if data.scope not in {"user", "project"}:
            raise ValueError(f"Unsupported pack update audit scope: {data.scope}")
        root = agora_home() if data.scope == "user" else self.project_root() / ".agora"
        audit_path = root / "notifications" / "pack-updates" / data.id / "AUDIT.md"
        if not audit_path.is_file():
            raise FileNotFoundError(f"Pack update audit not found: {audit_path}")
        application_path = audit_path.with_name("APPLICATION.md")
        if application_path.exists():
            raise FileExistsError(f"Pack update audit was already applied: {application_path}")
        audit = read_pack_update_audit(audit_path)
        if audit.scope != data.scope or audit.id != data.id:
            raise ValueError("Pack update audit identity does not match the requested application")
        audit_sha256 = hashlib.sha256(audit_path.read_bytes()).hexdigest()

        installed = self._installed_pack_contracts(data.scope)
        managed = {
            key for key in installed if (root / f"{key[0]}s" / key[1] / "SOURCE.md").is_file()
        }
        audited = {(item.kind, item.id) for item in audit.entries}
        if managed != audited:
            raise ValueError("Installed catalog pack set changed after the audit")

        merged_plan: list[CatalogPackRecord] = []
        planned: dict[tuple[str, str], CatalogPackRecord] = {}
        merged_steps: list[PackUpdateStep] = []
        step_keys: set[tuple[str, str]] = set()
        for entry in audit.entries:
            current, _ = self._installed_pack_for_update(entry.kind, entry.id, data.scope)
            assert current.source is not None
            if current.source.registry_scope != entry.registry_scope:
                raise ValueError(f"Pack update audit is stale for {entry.kind}/{entry.id}")
            result = self.update_catalog_pack(
                UpdateCatalogPackInput(
                    kind=entry.kind,
                    pack_id=entry.id,
                    scope=data.scope,
                    registry_id=entry.registry,
                )
            )
            current_sha256 = pack_tree_sha256(root / f"{entry.kind}s" / entry.id)
            actual = (
                result.from_version,
                result.to_version,
                result.update_available,
                result.modified,
                current_sha256,
                pack_update_plan_sha256(result.packs),
            )
            expected = (
                entry.from_version,
                entry.to_version,
                entry.update_available,
                entry.modified,
                entry.current_sha256,
                entry.plan_sha256,
            )
            if actual != expected:
                raise ValueError(f"Pack update audit is stale for {entry.kind}/{entry.id}")
            if entry.modified and not data.force:
                raise ValueError(
                    f"Pack update audit contains local modifications for {entry.kind}/{entry.id}; "
                    "pass --force after reviewing their replacement"
                )
            if not entry.update_available:
                continue

            matches = [
                item
                for item in self.search_catalog(entry.kind, registry_id=entry.registry)
                if item.id == entry.id
                and item.version == entry.to_version
                and item.registry_scope == entry.registry_scope
            ]
            if not matches:
                raise FileNotFoundError(
                    f"Audited catalog target not found: {entry.kind}/{entry.id}@{entry.to_version}"
                )
            selected = matches[0]
            for pack in self._resolve_catalog_install(selected, data.scope, True):
                key = (pack.kind, pack.id)
                existing = planned.get(key)
                if existing is not None:
                    if existing.version != pack.version or pack_tree_sha256(
                        Path(existing.path)
                    ) != pack_tree_sha256(Path(pack.path)):
                        raise ValueError(f"Audited pack plans conflict for {pack.kind}/{pack.id}")
                    continue
                planned[key] = pack
                merged_plan.append(pack)
            for step in result.packs:
                key = (step.kind, step.id)
                if key not in step_keys:
                    merged_steps.append(step)
                    step_keys.add(key)

        if not merged_plan:
            raise ValueError("Pack update audit contains no applicable updates")
        prospective = dict(installed)
        for pack in merged_plan:
            prospective[(pack.kind, pack.id)] = self._catalog_pack_contract(pack)
        issues = self._pack_composition_issues(prospective)
        if issues:
            raise ValueError(issues[0][1])

        applied_at = self._timestamp()
        update_id = self._now().astimezone(UTC).strftime("update-%Y%m%dt%H%M%S%fz")
        _, history_paths = self._apply_catalog_plan(
            merged_plan,
            data.scope,
            update_id=update_id,
            applied_at=applied_at,
        )
        self._write_pack_lock(data.scope)
        record = PackUpdateAuditApplicationRecord(
            id=data.id,
            scope=data.scope,
            audit_sha256=audit_sha256,
            applied_at=applied_at,
            force=data.force,
            packs=merged_steps,
            history_paths=[str(Path(path).relative_to(root)) for path in history_paths],
            path=str(application_path),
        )
        atomic_write(application_path, render_pack_update_audit_application(record))
        return read_pack_update_audit_application(application_path)

    @_locked_mutation("pack-update")
    def remove_pack(self, data: RemovePackInput) -> PackRemovalResult:
        if data.kind not in {"method", "tool"}:
            raise ValueError(f"Unsupported pack kind: {data.kind}")
        if data.scope is not None and data.scope not in {"user", "project"}:
            raise ValueError(f"Unsupported pack scope: {data.scope}")
        assert_slug(data.pack_id, "Pack id")
        _, scope = self._installed_pack_for_update(data.kind, data.pack_id, data.scope)
        steps = self._pack_removal_plan(
            data.kind,
            data.pack_id,
            scope,
            with_unused_dependencies=data.with_unused_dependencies,
        )
        result = PackRemovalResult(
            kind=data.kind,
            id=data.pack_id,
            scope=scope,
            applied=False,
            packs=steps,
        )
        if not data.apply:
            return result

        root = agora_home() if scope == "user" else self.project_root() / ".agora"
        removal_id = self._now().astimezone(UTC).strftime("removal-%Y%m%dt%H%M%S%fz")
        record_path = root / "pack-removals" / removal_id / "REMOVAL.md"
        if record_path.parent.exists():
            raise FileExistsError(f"Pack removal record already exists: {record_path}")
        record = PackRemovalRecord(
            id=removal_id,
            scope=scope,
            requested_kind=data.kind,
            requested_id=data.pack_id,
            removed_at=self._timestamp(),
            packs=steps,
            path=str(record_path),
        )

        with tempfile.TemporaryDirectory(prefix=".pack-removal-stage-", dir=root) as temporary:
            staging_root = Path(temporary)
            moved: list[tuple[Path, Path]] = []
            published_record = False
            published_lock = False
            old_lock = root / "PACKS.lock.md"
            lock_backup = staging_root / "previous-PACKS.lock.md"
            try:
                for step in steps:
                    destination = self._pack_destination(step.kind, step.id, scope)
                    backup = staging_root / "removed" / f"{step.kind}s" / step.id
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    destination.replace(backup)
                    moved.append((destination, backup))

                staged_record = staging_root / "record" / "REMOVAL.md"
                atomic_write(staged_record, render_pack_removal(record))
                staged_lock = staging_root / "next-PACKS.lock.md"
                next_lock = self._build_pack_lock(scope, root, generated_at=self._timestamp())
                atomic_write(staged_lock, render_pack_lock(next_lock))

                record_path.parent.parent.mkdir(parents=True, exist_ok=True)
                staged_record.parent.replace(record_path.parent)
                published_record = True
                if old_lock.exists():
                    old_lock.replace(lock_backup)
                staged_lock.replace(old_lock)
                published_lock = True
            except Exception:
                if published_lock and old_lock.exists():
                    old_lock.unlink()
                if lock_backup.exists():
                    lock_backup.replace(old_lock)
                if published_record and record_path.parent.exists():
                    shutil.rmtree(record_path.parent)
                for destination, backup in reversed(moved):
                    if backup.exists():
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        backup.replace(destination)
                raise

        return PackRemovalResult(
            **{**result.__dict__, "applied": True, "record_path": str(record_path)}
        )

    def _pack_removal_plan(
        self,
        kind: PackKind,
        id_: str,
        scope: str,
        *,
        with_unused_dependencies: bool,
    ) -> list[PackRemovalStep]:
        installed = self._installed_pack_contracts(scope)
        requested_key = (kind, id_)
        requested = installed.get(requested_key)
        if requested is None:
            raise FileNotFoundError(f"Installed pack not found: {kind}/{id_} at {scope} scope")

        dependents: dict[tuple[str, str], set[tuple[str, str]]] = {key: set() for key in installed}
        for owner_key, contract in installed.items():
            for dependency in contract.dependencies:
                dependency_key = (dependency.kind, dependency.id)
                if dependency_key in dependents:
                    dependents[dependency_key].add(owner_key)
        blockers = sorted(dependents[requested_key])
        if blockers:
            rendered = ", ".join(f"{owner_kind}/{owner_id}" for owner_kind, owner_id in blockers)
            raise ValueError(f"Cannot remove {kind}/{id_}; required by installed packs: {rendered}")

        dependency_order: list[tuple[str, str]] = []
        visited: set[tuple[str, str]] = set()

        def visit(key: tuple[str, str]) -> None:
            contract = installed[key]
            for dependency in contract.dependencies:
                dependency_key = (dependency.kind, dependency.id)
                if dependency_key not in installed or dependency_key in visited:
                    continue
                visited.add(dependency_key)
                dependency_order.append(dependency_key)
                visit(dependency_key)

        visit(requested_key)
        removal_keys = {requested_key}
        if with_unused_dependencies:
            changed = True
            while changed:
                changed = False
                for dependency_key in dependency_order:
                    if dependency_key in removal_keys:
                        continue
                    if dependents[dependency_key].issubset(removal_keys):
                        removal_keys.add(dependency_key)
                        changed = True

        ordered_keys = [requested_key] + [
            key for key in dependency_order if key in removal_keys and key != requested_key
        ]
        self._assert_packs_not_in_use(scope, ordered_keys)
        steps: list[PackRemovalStep] = []
        for key in ordered_keys:
            contract = installed[key]
            destination = self._pack_destination(key[0], key[1], scope)
            source_path = destination / "SOURCE.md"
            source = read_pack_source(source_path) if source_path.is_file() else None
            steps.append(
                PackRemovalStep(
                    kind=key[0],
                    id=key[1],
                    version=contract.version,
                    sha256=pack_tree_sha256(destination),
                    registry=source.registry if source is not None else None,
                    reason="requested" if key == requested_key else "unused-dependency",
                )
            )
        return steps

    def _assert_packs_not_in_use(self, scope: str, keys: list[tuple[str, str]]) -> None:
        key_set = set(keys)
        references: list[str] = []
        if scope == "user":
            user = self._load_user_configuration()
            if user is not None and ("method", user.default_method) in key_set:
                references.append(f"user default method {user.default_method}")
        else:
            root = self.project_root()
            project = self._load_project_configuration(root)
            if ("method", project.default_method) in key_set:
                references.append(f"project default method {project.default_method}")
            for swarm in self.list_swarms():
                if ("method", swarm.method) in key_set:
                    references.append(f"swarm {swarm.id} method {swarm.method}")
            for run in self.list_tool_runs():
                if ("tool", run.tool_id) in key_set:
                    references.append(f"tool run {run.id} tool {run.tool_id}")
        if references:
            raise ValueError(
                "Cannot remove packs referenced by durable state: " + ", ".join(references)
            )

    def _apply_catalog_plan(
        self,
        plan: list[CatalogPackRecord],
        scope: str,
        *,
        update_id: str | None = None,
        applied_at: str | None = None,
    ) -> tuple[list[MethodPackRecord | ToolPackRecord], list[str]]:
        if (update_id is None) != (applied_at is None):
            raise ValueError("Pack update id and timestamp must appear together")
        root = agora_home() if scope == "user" else self.project_root() / ".agora"
        root.mkdir(parents=True, exist_ok=True)
        staged_packs: list[
            tuple[
                CatalogPackRecord,
                MethodContract | ToolContract,
                Path,
                Path,
                Path,
            ]
        ] = []
        history_paths: list[str] = []
        with tempfile.TemporaryDirectory(prefix=".pack-plan-stage-", dir=root) as temporary:
            staging_root = Path(temporary)
            for pack in plan:
                source = Path(pack.path)
                destination = self._pack_destination(pack.kind, pack.id, scope)
                staged = staging_root / f"{pack.kind}s" / pack.id
                copy_template_tree(source, staged, {}, False)
                provenance = self._pack_source_for_catalog(pack, scope)
                atomic_write(staged / "SOURCE.md", render_pack_source(provenance))
                existing_updates = destination / "updates"
                if existing_updates.is_dir():
                    copy_template_tree(existing_updates, staged / "updates", {}, False)
                if update_id is not None:
                    manifest = destination / ("METHOD.md" if pack.kind == "method" else "TOOL.md")
                    existing = (
                        load_method_contract(destination)
                        if pack.kind == "method" and manifest.is_file()
                        else (
                            load_tool_contract(destination)
                            if pack.kind == "tool" and manifest.is_file()
                            else None
                        )
                    )
                    history_path = destination / "updates" / update_id / "UPDATE.md"
                    update = PackUpdateHistoryRecord(
                        id=update_id,
                        kind=pack.kind,
                        pack_id=pack.id,
                        from_version=existing.version if existing is not None else None,
                        to_version=pack.version,
                        from_sha256=(
                            pack_tree_sha256(destination) if existing is not None else None
                        ),
                        to_sha256=provenance.sha256,
                        registry=pack.registry,
                        registry_scope=pack.registry_scope,
                        applied_at=applied_at or "",
                        path=str(history_path),
                    )
                    staged_history = staged / "updates" / update_id / "UPDATE.md"
                    if staged_history.exists():
                        raise FileExistsError(f"Pack update record already exists: {history_path}")
                    atomic_write(staged_history, render_pack_update(update))
                    history_paths.append(str(history_path))
                history = load_pack_update_history(staged, pack.kind, pack.id)
                if history and (
                    history[-1].to_version != provenance.version
                    or history[-1].to_sha256 != provenance.sha256
                ):
                    raise ValueError(f"Pack update history does not match staged source: {staged}")
                contract = (
                    load_method_contract(staged)
                    if pack.kind == "method"
                    else load_tool_contract(staged)
                )
                backup = destination.with_name(f".{destination.name}-pack-backup")
                if backup.exists():
                    raise RuntimeError(f"Pack backup path already exists: {backup}")
                staged_packs.append((pack, contract, staged, destination, backup))

            swapped: list[tuple[Path, Path, bool]] = []
            try:
                for _, _, staged, destination, backup in staged_packs:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    replaced = destination.exists()
                    if replaced:
                        destination.replace(backup)
                    try:
                        staged.replace(destination)
                    except Exception:
                        if replaced:
                            backup.replace(destination)
                        raise
                    swapped.append((destination, backup, replaced))
            except Exception:
                for destination, backup, replaced in reversed(swapped):
                    if destination.exists():
                        shutil.rmtree(destination)
                    if replaced:
                        backup.replace(destination)
                raise

            records: list[MethodPackRecord | ToolPackRecord] = []
            for pack, contract, _, destination, _ in staged_packs:
                if pack.kind == "method":
                    assert isinstance(contract, MethodContract)
                    records.append(self._method_pack_record(contract, scope, destination))
                else:
                    assert isinstance(contract, ToolContract)
                    records.append(self._tool_pack_record(contract, scope, destination))
            for _, backup, replaced in swapped:
                if replaced:
                    shutil.rmtree(backup)
            return records, history_paths

    def _installed_pack_for_update(
        self, kind: PackKind, id_: str, requested_scope: str | None
    ) -> tuple[MethodPackRecord | ToolPackRecord, str]:
        scopes = [requested_scope] if requested_scope else ["project", "user"]
        project = self._optional_project_root()
        for scope in scopes:
            if scope == "project" and project is None:
                continue
            root = agora_home() if scope == "user" else project / ".agora"  # type: ignore[operator]
            path = root / f"{kind}s" / id_
            manifest = path / ("METHOD.md" if kind == "method" else "TOOL.md")
            if not manifest.is_file():
                continue
            if kind == "method":
                return self._method_pack_record(load_method_contract(path), scope, path), scope
            return self._tool_pack_record(load_tool_contract(path), scope, path), scope
        scope_detail = f" at {requested_scope} scope" if requested_scope else ""
        raise FileNotFoundError(f"Installed pack not found: {kind}/{id_}{scope_detail}")

    def _pack_destination(self, kind: PackKind, id_: str, scope: str) -> Path:
        root = agora_home() if scope == "user" else self.project_root() / ".agora"
        return root / f"{kind}s" / id_

    @_locked_mutation("scoped")
    def refresh_pack_lock(self, data: RefreshPackLockInput) -> PackLockRecord:
        if data.scope not in {"user", "project"}:
            raise ValueError(f"Unsupported pack lock scope: {data.scope}")
        return self._write_pack_lock(data.scope)

    def _write_pack_lock(self, scope: str, *, project_root: Path | None = None) -> PackLockRecord:
        root = agora_home() if scope == "user" else (project_root or self.project_root()) / ".agora"
        record = self._build_pack_lock(scope, root, generated_at=self._timestamp())
        atomic_write(Path(record.path), render_pack_lock(record))
        return read_pack_lock(Path(record.path))

    @staticmethod
    def _build_pack_lock(scope: str, root: Path, *, generated_at: str) -> PackLockRecord:
        entries: list[PackLockEntry] = []
        for kind, manifest in (("method", "METHOD.md"), ("tool", "TOOL.md")):
            for path in sorted((root / f"{kind}s").glob(f"*/{manifest}")):
                contract = (
                    load_method_contract(path.parent)
                    if kind == "method"
                    else load_tool_contract(path.parent)
                )
                source_path = path.parent / "SOURCE.md"
                source = read_pack_source(source_path) if source_path.is_file() else None
                entries.append(
                    PackLockEntry(
                        kind=kind,
                        id=contract.id,
                        version=contract.version,
                        sha256=pack_tree_sha256(path.parent),
                        registry=source.registry if source is not None else None,
                        source_sha256=source.sha256 if source is not None else None,
                    )
                )
        entries.sort(key=lambda item: (item.kind, item.id))
        return PackLockRecord(
            scope=scope,
            generated_at=generated_at,
            packs=entries,
            path=str(root / "PACKS.lock.md"),
        )

    def _resolve_catalog_install(
        self, selected: CatalogPackRecord, scope: str, force: bool
    ) -> list[CatalogPackRecord]:
        installed = self._installed_pack_contracts(scope)
        planned = dict(installed)
        catalog = self.search_catalog()
        ordered: list[CatalogPackRecord] = []
        selected_packs: dict[tuple[str, str], CatalogPackRecord] = {}

        def visit(pack: CatalogPackRecord) -> None:
            key = (pack.kind, pack.id)
            previous = selected_packs.get(key)
            if previous is not None:
                if previous.version != pack.version:
                    raise ValueError(
                        f"Pack resolution selected conflicting versions for {pack.kind}/{pack.id}: "
                        f"{previous.version} and {pack.version}"
                    )
                return
            contract = self._catalog_pack_contract(pack)
            selected_packs[key] = pack
            planned[key] = contract
            for dependency in contract.dependencies:
                dependency_key = (dependency.kind, dependency.id)
                available = planned.get(dependency_key)
                if available is not None and version_satisfies(
                    available.version, dependency.version
                ):
                    continue
                current = installed.get(dependency_key)
                if current is not None and not force:
                    raise ValueError(
                        "Installed "
                        f"{pack_reference(dependency.kind, dependency.id, current.version)} "
                        f"does not satisfy {dependency.version}; pass --force to replace it"
                    )
                candidates = [
                    candidate
                    for candidate in catalog
                    if candidate.kind == dependency.kind
                    and candidate.id == dependency.id
                    and version_satisfies(candidate.version, dependency.version)
                ]
                if not candidates:
                    raise ValueError(
                        f"Cannot resolve dependency {dependency.kind}/{dependency.id} "
                        f"{dependency.version} required by "
                        f"{pack_reference(pack.kind, pack.id, pack.version)}"
                    )
                visit(candidates[0])
            ordered.append(pack)

        visit(selected)
        issues = self._pack_composition_issues(planned)
        if issues:
            raise ValueError(issues[0][1])
        return ordered

    def _pack_source_for_catalog(self, pack: CatalogPackRecord, scope: str) -> PackSourceRecord:
        registry = next(
            (
                item
                for item in self.list_registries()
                if item.id == pack.registry and item.scope == pack.registry_scope
            ),
            None,
        )
        if registry is None:
            raise FileNotFoundError(
                f"Registry disappeared while resolving {pack.kind}/{pack.id}: {pack.registry}"
            )
        root = agora_home() if scope == "user" else self.project_root() / ".agora"
        return PackSourceRecord(
            kind=pack.kind,
            id=pack.id,
            version=pack.version,
            registry=registry.id,
            registry_scope=registry.scope,
            registry_version=registry.version,
            registry_source=registry.source,
            sha256=pack_tree_sha256(Path(pack.path)),
            installed_at=self._timestamp(),
            path=str(root / f"{pack.kind}s" / pack.id / "SOURCE.md"),
        )

    def _assert_candidate_composition(
        self,
        kind: PackKind,
        contract: MethodContract | ToolContract,
        scope: str,
    ) -> None:
        installed = self._installed_pack_contracts(scope)
        installed[(kind, contract.id)] = contract
        issues = self._pack_composition_issues(installed)
        if issues:
            raise ValueError(issues[0][1])

    def _installed_pack_contracts(
        self, scope: str
    ) -> dict[tuple[str, str], MethodContract | ToolContract]:
        root = agora_home() if scope == "user" else self.project_root() / ".agora"
        contracts: dict[tuple[str, str], MethodContract | ToolContract] = {}
        for path in sorted((root / "methods").glob("*/METHOD.md")):
            contract = load_method_contract(path.parent)
            contracts[("method", contract.id)] = contract
        for path in sorted((root / "tools").glob("*/TOOL.md")):
            contract = load_tool_contract(path.parent)
            contracts[("tool", contract.id)] = contract
        return contracts

    @staticmethod
    def _catalog_pack_contract(pack: CatalogPackRecord) -> MethodContract | ToolContract:
        source = Path(pack.path)
        return load_method_contract(source) if pack.kind == "method" else load_tool_contract(source)

    def _assert_pack_destination_available(
        self, kind: PackKind, id_: str, scope: str, force: bool
    ) -> None:
        root = agora_home() if scope == "user" else self.project_root() / ".agora"
        destination = root / f"{kind}s" / id_
        if destination.exists() and not force:
            raise FileExistsError(
                f"{kind.title()} Pack already exists: {destination}. "
                "Pass --force to replace its files."
            )

    @staticmethod
    def _pack_composition_issues(
        contracts: dict[tuple[str, str], MethodContract | ToolContract],
    ) -> list[tuple[tuple[str, str], str]]:
        issues: list[tuple[tuple[str, str], str]] = []
        for key, contract in sorted(contracts.items()):
            owner = pack_reference(key[0], key[1], contract.version)
            for dependency in contract.dependencies:
                target = contracts.get((dependency.kind, dependency.id))
                if target is None:
                    issues.append(
                        (
                            key,
                            f"{owner} requires missing {dependency.kind}/{dependency.id} "
                            f"{dependency.version}",
                        )
                    )
                elif not version_satisfies(target.version, dependency.version):
                    issues.append(
                        (
                            key,
                            f"{owner} requires {dependency.kind}/{dependency.id} "
                            f"{dependency.version}, but {target.version} is installed",
                        )
                    )

        states: dict[tuple[str, str], str] = {}
        stack: list[tuple[str, str]] = []

        def visit(key: tuple[str, str]) -> None:
            state = states.get(key)
            if state == "done":
                return
            if state == "active":
                start = stack.index(key)
                cycle = stack[start:] + [key]
                rendered = " -> ".join(
                    pack_reference(item[0], item[1], contracts[item].version) for item in cycle
                )
                issues.append((key, f"Pack dependency cycle: {rendered}"))
                return
            states[key] = "active"
            stack.append(key)
            for dependency in contracts[key].dependencies:
                target = (dependency.kind, dependency.id)
                if target in contracts:
                    visit(target)
            stack.pop()
            states[key] = "done"

        for key in sorted(contracts):
            visit(key)
        return issues

    @staticmethod
    def _validate_pack_source(
        kind: PackKind,
        pack_root: Path,
        contract: MethodContract | ToolContract,
        inspect: Callable[[str, str, Path, Callable[[], object]], object | None],
        issue: Callable[[str, Path, str, str], None],
    ) -> None:
        path = pack_root / "SOURCE.md"
        if not path.exists():
            return
        source = inspect(
            "pack-sources",
            "pack-source.invalid",
            path,
            lambda: read_pack_source(path),
        )
        if not isinstance(source, PackSourceRecord):
            return
        if source.kind != kind or source.id != contract.id or source.version != contract.version:
            issue(
                "pack-source.mismatch",
                path,
                f"Pack source does not match {kind}/{contract.id}@{contract.version}",
                "error",
            )
        if pack_tree_sha256(pack_root) != source.sha256:
            issue(
                "pack-source.modified",
                path,
                "Installed pack content differs from its catalog source",
                "warning",
            )
        update_root = pack_root / "updates"
        if update_root.is_dir():
            history = inspect(
                "pack-histories",
                "pack-update.invalid",
                update_root,
                lambda: load_pack_update_history(pack_root, kind, contract.id),
            )
            if isinstance(history, list) and history:
                latest = history[-1]
                if latest.to_version != source.version or latest.to_sha256 != source.sha256:
                    issue(
                        "pack-update.source-mismatch",
                        Path(latest.path),
                        "Latest pack update does not match current SOURCE.md",
                        "error",
                    )

    def show_tool(self, tool_id: str) -> ToolPackRecord:
        assert_slug(tool_id, "Tool id")
        path = self.project_root() / ".agora" / "tools" / tool_id
        contract = load_tool_contract(path)
        return self._tool_pack_record(contract, "project", path)

    def list_methods(self) -> list[MethodPackRecord]:
        method_root = self.project_root() / ".agora" / "methods"
        records: list[MethodPackRecord] = []
        for path in sorted(method_root.glob("*/METHOD.md")):
            contract = load_method_contract(path.parent)
            records.append(self._method_pack_record(contract, "project", path.parent))
        return records

    def list_tools(self) -> list[ToolPackRecord]:
        tool_root = self.project_root() / ".agora" / "tools"
        return [
            self._tool_pack_record(load_tool_contract(path.parent), "project", path.parent)
            for path in sorted(tool_root.glob("*/TOOL.md"))
        ]

    @_locked_mutation("scoped")
    def add_actor(self, data: AddActorInput) -> ActorRecord:
        assert_slug(data.id, "Actor id")
        if data.kind not in ACTOR_KINDS:
            raise ValueError(f"Unsupported actor kind: {data.kind}")
        if data.integration is not None:
            self._assert_integration(data.integration)
        if data.require_authentication and data.public_key is None:
            raise ValueError("An actor requiring authentication must declare --public-key")
        authentication_public_key: str | None = None
        authentication_fingerprint: str | None = None
        if data.public_key is not None:
            authentication_public_key, authentication_fingerprint = actor_identity_from_pem(
                Path(data.public_key).expanduser().resolve()
            )
        root = agora_home() if data.scope == "user" else self.project_root() / ".agora"
        if data.represented_swarm is not None:
            assert_slug(data.represented_swarm, "Represented swarm id")
            if data.kind != "swarm":
                raise ValueError("Only an actor whose kind is swarm may represent a project swarm")
            if data.scope != "project":
                raise ValueError("A represented swarm actor must use project scope")
            self._load_swarm(self.project_root(), data.represented_swarm)
        path = root / "actors" / f"{data.id}.md"
        if path.exists() and data.force:
            existing = self._find_actor(self.project_root(), f"{data.scope}:{data.id}")
            if (
                existing.authentication_fingerprint is not None
                or authentication_fingerprint is not None
            ):
                raise ValueError(
                    "Actor authentication identity cannot be replaced with --force; "
                    "use `agora actor key rotate`"
                )
        if authentication_fingerprint is not None:
            pending_key_path = path.with_suffix("") / "keys" / f"{authentication_fingerprint}.md"
            if pending_key_path.exists() and not data.force:
                raise FileExistsError(f"Actor key already exists: {pending_key_path}")
        capabilities = sorted(set(data.capabilities))
        description = data.description or (
            "Describe this actor's operating context and constraints."
        )
        attributes = {
            "schema": "agora/actor/v1",
            "id": data.id,
            "name": data.name,
            "kind": data.kind,
            "capabilities": capabilities,
            "scope": data.scope,
            "created-at": self._timestamp(),
        }
        if data.integration is not None:
            attributes["integration"] = data.integration
        if data.provider is not None:
            attributes["provider"] = data.provider
        if data.model is not None:
            attributes["model"] = data.model
        if data.represented_swarm is not None:
            attributes["represented-swarm"] = data.represented_swarm
        attributes["authentication-required"] = data.require_authentication
        if authentication_public_key is not None:
            attributes["authentication-algorithm"] = "ed25519"
            attributes["authentication-public-key"] = authentication_public_key
            attributes["authentication-fingerprint"] = authentication_fingerprint
        write_new(
            path,
            render_markdown(
                MarkdownDocument(
                    attributes=attributes,
                    body=f"# {data.name}\n\n{description}",
                )
            ),
            data.force,
        )
        record = ActorRecord(
            id=data.id,
            name=data.name,
            kind=data.kind,
            capabilities=capabilities,
            path=str(path),
            reference=f"{data.scope}:{data.id}",
            integration=data.integration,
            provider=data.provider,
            model=data.model,
            represented_swarm=data.represented_swarm,
            authentication_required=data.require_authentication,
            authentication_algorithm="ed25519" if authentication_public_key else None,
            authentication_public_key=authentication_public_key,
            authentication_fingerprint=authentication_fingerprint,
        )
        if authentication_fingerprint is not None:
            key_path = self._actor_key_root(record) / f"{authentication_fingerprint}.md"
            key = actor_key_from_actor(record, key_path, attributes["created-at"])
            write_new(key_path, render_actor_key(key), data.force)
        return record

    @_locked_mutation("actor-runtime")
    def rotate_actor_key(self, data: RotateActorKeyInput) -> ActorKeyRecord:
        if not data.reason.strip():
            raise ValueError("Actor key rotation reason cannot be empty")
        root = self.project_root()
        actor = self._find_actor(root, data.actor_id)
        if actor.authentication_fingerprint is None:
            raise ValueError(f"Actor {actor.reference} has no authentication key to rotate")
        if actor.authentication_required:
            action = (
                "actor.key.recover"
                if actor.authentication_revoked_at is not None
                else "actor.key.rotate"
            )
            raise PermissionError(
                f"Actor {actor.reference} requires a signed lifecycle action; "
                f"prepare {action} before replacing its key"
            )
        current = self._ensure_current_actor_key(actor)
        created_at = self._timestamp()
        replacement = actor_key_from_pem(
            actor.reference,
            Path(data.public_key).expanduser().resolve(),
            self._actor_key_root(actor),
            created_at,
        )
        self._validate_actor_key_replacement(current, replacement)
        return self._apply_actor_key_rotation(root, actor, current, replacement, data.reason)

    @_locked_mutation("project")
    def prepare_actor_key_rotation(
        self, data: PrepareActorKeyRotationInput
    ) -> LifecycleActionRecord:
        assert_slug(data.action_id, "Lifecycle Action id")
        if not data.rotation.reason.strip():
            raise ValueError("Actor key rotation reason cannot be empty")
        root = self.project_root()
        swarm = self._load_swarm(root, data.swarm_id)
        actor = self._require_actor_for_action(
            root, swarm, data.rotation.actor_id, "actor.key.rotate"
        )
        assert_actor_identity_available(actor)
        current = self._ensure_current_actor_key(actor)
        replacement = actor_key_from_pem(
            actor.reference,
            Path(data.rotation.public_key).expanduser().resolve(),
            self._actor_key_root(actor),
            self._timestamp(),
        )
        self._validate_actor_key_replacement(current, replacement)
        return self._prepare_lifecycle_action(
            root,
            id_=data.action_id,
            action="actor.key.rotate",
            actor=actor,
            swarm=swarm,
            work=None,
            parameters={
                "from": current.fingerprint,
                "public-key": replacement.public_key,
                "fingerprint": replacement.fingerprint,
                "reason": data.rotation.reason.strip(),
            },
        )

    @_locked_mutation("project")
    def prepare_actor_key_revocation(
        self, data: PrepareActorKeyRevocationInput
    ) -> LifecycleActionRecord:
        assert_slug(data.action_id, "Lifecycle Action id")
        if not data.reason.strip():
            raise ValueError("Actor key revocation reason cannot be empty")
        root = self.project_root()
        swarm = self._load_swarm(root, data.swarm_id)
        authorizer, target, current = self._validate_actor_key_administrator(
            root,
            swarm,
            target_actor_id=data.target_actor_id,
            authorized_by=data.authorized_by,
            action="actor.key.revoke",
            target_must_be_revoked=False,
        )
        return self._prepare_lifecycle_action(
            root,
            id_=data.action_id,
            action="actor.key.revoke",
            actor=authorizer,
            swarm=swarm,
            work=None,
            parameters={
                "target": target.reference,
                "fingerprint": current.fingerprint,
                "reason": data.reason.strip(),
            },
        )

    @_locked_mutation("project")
    def prepare_actor_key_recovery(
        self, data: PrepareActorKeyRecoveryInput
    ) -> LifecycleActionRecord:
        assert_slug(data.action_id, "Lifecycle Action id")
        if not data.reason.strip():
            raise ValueError("Actor key recovery reason cannot be empty")
        root = self.project_root()
        swarm = self._load_swarm(root, data.swarm_id)
        authorizer, target, current = self._validate_actor_key_administrator(
            root,
            swarm,
            target_actor_id=data.target_actor_id,
            authorized_by=data.authorized_by,
            action="actor.key.recover",
            target_must_be_revoked=True,
        )
        replacement = actor_key_from_pem(
            target.reference,
            Path(data.public_key).expanduser().resolve(),
            self._actor_key_root(target),
            self._timestamp(),
        )
        self._validate_actor_key_replacement(current, replacement)
        if replacement.fingerprint == authorizer.authentication_fingerprint:
            raise ValueError("Recovery key must differ from the governance authorizer key")
        return self._prepare_lifecycle_action(
            root,
            id_=data.action_id,
            action="actor.key.recover",
            actor=authorizer,
            swarm=swarm,
            work=None,
            parameters={
                "target": target.reference,
                "from": current.fingerprint,
                "public-key": replacement.public_key,
                "fingerprint": replacement.fingerprint,
                "reason": data.reason.strip(),
            },
        )

    def _validate_actor_key_administrator(
        self,
        root: Path,
        swarm: SwarmRecord,
        *,
        target_actor_id: str,
        authorized_by: str,
        action: str,
        target_must_be_revoked: bool,
    ) -> tuple[ActorRecord, ActorRecord, ActorKeyRecord]:
        authorizer = self._require_actor_for_action(root, swarm, authorized_by, action)
        if not authorizer.authentication_required:
            raise PermissionError(
                f"Actor key administrator {authorizer.reference} must require authentication"
            )
        assert_actor_identity_available(authorizer)
        self._assert_current_actor_key(authorizer)
        target = self._find_actor(root, target_actor_id)
        if target.reference not in swarm.assignments.values():
            raise ValueError(f"Actor {target.reference} is not assigned to swarm {swarm.id}")
        if target.reference == authorizer.reference:
            raise PermissionError("An actor cannot administer its own key revocation or recovery")
        if target.authentication_fingerprint is None:
            raise ValueError(f"Actor {target.reference} has no authentication key")
        if target.authentication_fingerprint == authorizer.authentication_fingerprint:
            raise PermissionError(
                "Actor key administrator must use a distinct cryptographic identity"
            )
        is_revoked = target.authentication_revoked_at is not None
        if is_revoked != target_must_be_revoked:
            expected = "revoked" if target_must_be_revoked else "active"
            raise ValueError(f"Actor authentication key must be {expected}: {target.reference}")
        return authorizer, target, self._ensure_current_actor_key(target)

    @staticmethod
    def _validate_actor_key_replacement(
        current: ActorKeyRecord, replacement: ActorKeyRecord
    ) -> None:
        if replacement.fingerprint == current.fingerprint:
            raise ValueError("Replacement actor key must differ from the current key")
        if Path(replacement.path).exists():
            raise ValueError(f"Actor key fingerprint was already used: {replacement.fingerprint}")

    def _apply_actor_key_rotation(
        self,
        root: Path,
        actor: ActorRecord,
        current: ActorKeyRecord,
        replacement: ActorKeyRecord,
        reason: str,
    ) -> ActorKeyRecord:
        created_at = replacement.created_at
        if current.status == "active":
            previous = end_actor_key(
                current,
                status="rotated",
                ended_at=created_at,
                reason=reason,
                replaced_by=replacement.fingerprint,
            )
        else:
            previous = link_actor_key_replacement(current, replacement.fingerprint)

        write_new(Path(replacement.path), render_actor_key(replacement))
        atomic_write(Path(previous.path), render_actor_key(previous))
        actor_path = Path(actor.path)
        document = read_markdown(actor_path)
        document.attributes.update(
            {
                "authentication-algorithm": "ed25519",
                "authentication-public-key": replacement.public_key,
                "authentication-fingerprint": replacement.fingerprint,
                "authentication-updated-at": created_at,
            }
        )
        document.attributes.pop("authentication-revoked-at", None)
        document.attributes.pop("authentication-revoked-reason", None)
        atomic_write(actor_path, render_markdown(document))
        self._append_actor_event(
            root,
            actor,
            "actor.key-rotated",
            f"from={current.fingerprint} to={replacement.fingerprint}",
        )
        return replacement

    @_locked_mutation("actor-runtime")
    def revoke_actor_key(self, data: RevokeActorKeyInput) -> ActorKeyRecord:
        if not data.reason.strip():
            raise ValueError("Actor key revocation reason cannot be empty")
        root = self.project_root()
        actor = self._find_actor(root, data.actor_id)
        if actor.authentication_fingerprint is None:
            raise ValueError(f"Actor {actor.reference} has no authentication key to revoke")
        if actor.authentication_required:
            raise PermissionError(
                f"Actor {actor.reference} requires a signed lifecycle action; "
                "prepare actor.key.revoke through a distinct governance actor"
            )
        if actor.authentication_revoked_at is not None:
            raise ValueError(f"Actor authentication key is already revoked: {actor.reference}")
        current = self._ensure_current_actor_key(actor)
        return self._apply_actor_key_revocation(root, actor, current, data.reason)

    def _apply_actor_key_revocation(
        self,
        root: Path,
        actor: ActorRecord,
        current: ActorKeyRecord,
        reason: str,
    ) -> ActorKeyRecord:
        revoked_at = self._timestamp()
        revoked = end_actor_key(
            current,
            status="revoked",
            ended_at=revoked_at,
            reason=reason,
        )
        atomic_write(Path(revoked.path), render_actor_key(revoked))
        actor_path = Path(actor.path)
        document = read_markdown(actor_path)
        document.attributes["authentication-revoked-at"] = revoked_at
        document.attributes["authentication-revoked-reason"] = reason.strip()
        atomic_write(actor_path, render_markdown(document))
        self._append_actor_event(
            root,
            actor,
            "actor.key-revoked",
            f"fingerprint={revoked.fingerprint}",
        )
        return revoked

    def list_actor_keys(self, actor_id: str) -> list[ActorKeyRecord]:
        actor = self._find_actor(self.project_root(), actor_id)
        records = [load_actor_key(path) for path in self._actor_key_root(actor).glob("*.md")]
        return sorted(records, key=lambda record: (record.created_at, record.fingerprint))

    @_locked_mutation("actor-runtime")
    def set_actor_runtime(self, data: SetActorRuntimeInput) -> ActorRecord:
        root = self.project_root()
        actor = self._validate_actor_runtime(root, data)
        if actor.authentication_required:
            raise PermissionError(
                f"Actor {actor.reference} requires a signed lifecycle action; "
                "prepare actor.runtime.update before changing its runtime"
            )
        return self._apply_actor_runtime(root, actor, data)

    @_locked_mutation("project")
    def prepare_actor_runtime(self, data: PrepareActorRuntimeInput) -> LifecycleActionRecord:
        assert_slug(data.action_id, "Lifecycle Action id")
        root = self.project_root()
        swarm = self._load_swarm(root, data.swarm_id)
        actor = self._validate_actor_runtime(root, data.runtime)
        actor = self._require_actor_for_action(root, swarm, actor.reference, "actor.runtime.update")
        assert_actor_identity_available(actor)
        self._assert_current_actor_key(actor)
        return self._prepare_lifecycle_action(
            root,
            id_=data.action_id,
            action="actor.runtime.update",
            actor=actor,
            swarm=swarm,
            work=None,
            parameters=self._actor_runtime_parameters(data.runtime),
        )

    def _validate_actor_runtime(self, root: Path, data: SetActorRuntimeInput) -> ActorRecord:
        actor = self._find_actor(root, data.actor_id)
        if not data.clear and not any((data.integration, data.provider, data.model)):
            raise ValueError("Provide an integration, provider, model, or --clear")
        if data.integration is not None:
            self._assert_integration(data.integration)
        return actor

    def _apply_actor_runtime(
        self, root: Path, actor: ActorRecord, data: SetActorRuntimeInput
    ) -> ActorRecord:
        path = Path(actor.path)
        document = read_markdown(path)
        if data.clear:
            for key in ("integration", "provider", "model"):
                document.attributes.pop(key, None)
        else:
            if data.integration is not None:
                document.attributes["integration"] = data.integration
            if data.provider is not None:
                document.attributes["provider"] = data.provider
            if data.model is not None:
                document.attributes["model"] = data.model
        document.attributes["runtime-updated-at"] = self._timestamp()
        atomic_write(path, render_markdown(document))
        event_path = (
            agora_home() / "events.md"
            if actor.reference.startswith("user:")
            else root / ".agora" / "events.md"
        )
        if not event_path.exists():
            write_new(event_path, "# Agora events\n\n")
        append_entry(
            event_path,
            f"- {self._timestamp()} | actor.runtime-updated | actor={actor.reference}",
        )
        return self._find_actor(root, actor.reference)

    @staticmethod
    def _actor_runtime_parameters(data: SetActorRuntimeInput) -> dict[str, str]:
        return {
            "integration": data.integration or "",
            "provider": data.provider or "",
            "model": data.model or "",
            "clear": "true" if data.clear else "false",
        }

    def list_actors(self, scope: str = "all") -> list[ActorRecord]:
        if scope not in {"all", "user", "project"}:
            raise ValueError("Actor scope must be all, user, or project")
        root = self.project_root()
        sources = []
        if scope in {"all", "project"}:
            sources.append(("project", root / ".agora" / "actors"))
        if scope in {"all", "user"}:
            sources.append(("user", agora_home() / "actors"))
        return [
            self._find_actor(root, f"{actor_scope}:{path.stem}")
            for actor_scope, actor_root in sources
            if actor_root.exists()
            for path in sorted(actor_root.glob("*.md"))
            if path.name != "README.md"
        ]

    @_locked_mutation("project")
    def create_swarm(self, data: CreateSwarmInput) -> SwarmRecord:
        assert_slug(data.id, "Swarm id")
        root = self.project_root()
        project = self._load_project_configuration(root)
        method = data.method or project.default_method
        self._assert_method_available(method, root / ".agora" / "methods")
        contract = load_method_contract(root / ".agora" / "methods" / method)
        branch = data.branch or f"agora/{data.id}"
        swarm_path = root / ".agora" / "swarms" / data.id
        if swarm_path.exists():
            raise FileExistsError(f"Swarm already exists: {data.id}")
        if data.create_branch and is_git_repository(root):
            create_branch(root, branch)
        effective_branch = current_branch(root) if is_git_repository(root) else "filesystem-only"
        record = SwarmRecord(
            id=data.id,
            method=method,
            status="forming",
            branch=effective_branch,
            required_roles=contract.required_roles,
            assignments={},
            objective=data.objective,
            path=str(swarm_path),
        )
        write_new(swarm_path / "SWARM.md", self._render_swarm(record))
        write_new(swarm_path / "events.md", "# Swarm events\n\n")
        write_new(swarm_path / "interactions.md", "# Interactions\n\n")
        write_new(swarm_path / "artifacts.md", "# Swarm artifacts\n\n")
        write_new(swarm_path / "evidence.md", "# Swarm evidence\n\n")
        (swarm_path / "work").mkdir(parents=True)
        (swarm_path / "handoffs").mkdir(parents=True)
        self._append_swarm_event(root, data.id, "swarm.created", f"branch={record.branch}")
        return record

    @_locked_mutation("project")
    def assign_actor(self, data: AssignActorInput) -> SwarmRecord:
        root = self.project_root()
        swarm, actor = self._validate_actor_assignment(root, data)
        return self._apply_actor_assignment(root, swarm, actor, data.role_id)

    @_locked_mutation("project")
    def prepare_actor_assignment(self, data: PrepareActorAssignmentInput) -> LifecycleActionRecord:
        assert_slug(data.action_id, "Lifecycle Action id")
        root = self.project_root()
        swarm, actor = self._validate_actor_assignment(root, data.assignment)
        authorizer = self._require_actor_for_action(root, swarm, data.authorized_by, "swarm.assign")
        assert_actor_identity_available(authorizer)
        self._assert_current_actor_key(authorizer)
        return self._prepare_lifecycle_action(
            root,
            id_=data.action_id,
            action="swarm.assign",
            actor=authorizer,
            swarm=swarm,
            work=None,
            parameters={
                "role": data.assignment.role_id,
                "target": actor.reference,
            },
        )

    def _validate_actor_assignment(
        self, root: Path, data: AssignActorInput
    ) -> tuple[SwarmRecord, ActorRecord]:
        assert_slug(data.role_id, "Role id")
        swarm = self._load_swarm(root, data.swarm_id)
        if swarm.status not in {"forming", "ready"}:
            raise ValueError(f"Cannot change assignments while swarm {swarm.id} is {swarm.status}")
        if data.role_id not in swarm.required_roles:
            raise ValueError(f"Role {data.role_id} is not required by swarm {swarm.id}")
        if data.role_id in swarm.assignments:
            raise ValueError(
                f"Role {data.role_id} is already assigned in swarm {swarm.id}; use a handoff"
            )
        actor = self._find_actor(root, data.actor_id)
        self._assert_actor_role_compatibility(root, swarm.method, data.role_id, actor)
        self._assert_swarm_actor_delegation(root, swarm, data.role_id, actor)
        return swarm, actor

    def _apply_actor_assignment(
        self,
        root: Path,
        swarm: SwarmRecord,
        actor: ActorRecord,
        role_id: str,
        action_id: str | None = None,
    ) -> SwarmRecord:
        swarm.assignments[role_id] = actor.reference
        swarm.status = (
            "ready"
            if all(role_id in swarm.assignments for role_id in swarm.required_roles)
            else "forming"
        )
        atomic_write(Path(swarm.path) / "SWARM.md", self._render_swarm(swarm))
        self._append_swarm_event(
            root,
            swarm.id,
            "swarm.actor-assigned",
            f"role={role_id} actor={actor.reference}"
            + (f" action={action_id}" if action_id is not None else ""),
        )
        return swarm

    @_locked_mutation("project")
    def handoff_actor(self, data: HandoffActorInput) -> HandoffRecord:
        root = self.project_root()
        context = self._validate_handoff(root, data)
        authorizer = context[3]
        if authorizer.authentication_required:
            raise PermissionError(
                f"Actor {authorizer.reference} requires a signed lifecycle action; "
                "prepare the handoff before applying it"
            )
        return self._apply_handoff(root, *context)

    @_locked_mutation("project")
    def prepare_handoff(self, data: HandoffActorInput) -> LifecycleActionRecord:
        if data.id is None:
            raise ValueError("Prepared handoff requires an explicit id")
        root = self.project_root()
        swarm, outgoing, incoming, authorizer, work, _, _, _, _ = self._validate_handoff(root, data)
        assert_actor_identity_available(authorizer)
        self._assert_current_actor_key(authorizer)
        return self._prepare_lifecycle_action(
            root,
            id_=data.id,
            action="handoff.create",
            actor=authorizer,
            swarm=swarm,
            work=work,
            parameters={
                "role": data.role_id,
                "from": outgoing.reference,
                "to": incoming.reference,
                "reason": data.reason.strip(),
            },
        )

    def _validate_handoff(
        self, root: Path, data: HandoffActorInput
    ) -> tuple[
        SwarmRecord,
        ActorRecord,
        ActorRecord,
        ActorRecord,
        WorkRecord | None,
        str,
        str,
        str,
        Path,
    ]:
        assert_slug(data.role_id, "Role id")
        if not data.reason.strip():
            raise ValueError("Handoff reason cannot be empty")
        swarm = self._load_swarm(root, data.swarm_id)
        if swarm.status not in {"ready", "running", "blocked"}:
            raise ValueError(
                f"Cannot hand off assignments while swarm {swarm.id} is {swarm.status}"
            )
        current_reference = swarm.assignments.get(data.role_id)
        if current_reference is None:
            raise FileNotFoundError(f"Role {data.role_id} is not assigned in swarm {swarm.id}")
        outgoing = self._find_actor(root, data.from_actor_id)
        if outgoing.reference != current_reference:
            raise ValueError(
                f"Actor {outgoing.reference} is not the current {data.role_id}; "
                f"assigned actor is {current_reference}"
            )
        incoming = self._find_actor(root, data.to_actor_id)
        if incoming.reference == outgoing.reference:
            raise ValueError("Handoff destination must differ from the current actor")
        self._assert_actor_role_compatibility(root, swarm.method, data.role_id, incoming)
        self._assert_swarm_actor_delegation(root, swarm, data.role_id, incoming)
        active_approval_delegations = [
            delegation.id
            for work_path in sorted((Path(swarm.path) / "work").glob("*/WORK.md"))
            for delegation in self._load_approval_delegations(
                self._load_work(swarm, work_path.parent.name)
            )
            if delegation.role_id == data.role_id
            and delegation.from_actor == outgoing.reference
            and delegation.status == "active"
        ]
        if active_approval_delegations:
            raise ValueError(
                f"Revoke or consume active Approval Delegations before handing off "
                f"{data.role_id}: {', '.join(active_approval_delegations)}"
            )

        authorizer = self._find_actor(root, data.authorized_by)
        authorizer_roles = self._actor_roles(swarm, authorizer.reference)
        if not authorizer_roles:
            raise ValueError(f"Actor {authorizer.reference} is not assigned to swarm {swarm.id}")
        if authorizer.reference == outgoing.reference:
            if not self._role_allows_action(root, swarm.method, data.role_id, "handoff.create"):
                raise PermissionError(
                    f"Role {data.role_id} is not allowed to perform handoff.create"
                )
        elif not any(
            self._role_allows_action(root, swarm.method, role, "handoff.manage")
            for role in authorizer_roles
        ):
            raise PermissionError(
                f"Actor {authorizer.reference} is not allowed to perform handoff.manage"
            )

        work = self._load_work(swarm, data.work_id) if data.work_id is not None else None
        handoff_id = data.id or self._now().astimezone(UTC).strftime("handoff-%Y%m%dt%H%M%sz")
        assert_slug(handoff_id, "Handoff id")
        handoff_path = Path(swarm.path) / "handoffs" / handoff_id / "HANDOFF.md"
        if handoff_path.exists():
            raise FileExistsError(f"Handoff already exists: {handoff_id}")
        return (
            swarm,
            outgoing,
            incoming,
            authorizer,
            work,
            data.role_id,
            data.reason.strip(),
            handoff_id,
            handoff_path,
        )

    def _apply_handoff(
        self,
        root: Path,
        swarm: SwarmRecord,
        outgoing: ActorRecord,
        incoming: ActorRecord,
        authorizer: ActorRecord,
        work: WorkRecord | None,
        role_id: str,
        reason: str,
        handoff_id: str,
        handoff_path: Path,
    ) -> HandoffRecord:
        record = HandoffRecord(
            id=handoff_id,
            swarm_id=swarm.id,
            role_id=role_id,
            from_actor=outgoing.reference,
            to_actor=incoming.reference,
            authorized_by=authorizer.reference,
            reason=reason,
            work_id=work.id if work else None,
            created_at=self._timestamp(),
            path=str(handoff_path),
        )
        write_new(handoff_path, self._render_handoff(record))
        swarm.assignments[role_id] = incoming.reference
        atomic_write(Path(swarm.path) / "SWARM.md", self._render_swarm(swarm))
        detail = (
            f"handoff={handoff_id} role={role_id} from={outgoing.reference} "
            f"to={incoming.reference} by={authorizer.reference}"
        )
        self._append_swarm_event(root, swarm.id, "swarm.role-handed-off", detail)
        if work is not None:
            self._append_work_event(work, "work.role-handed-off", detail)
        return record

    def show_swarm(self, swarm_id: str) -> SwarmRecord:
        return self._load_swarm(self.project_root(), swarm_id)

    def list_swarms(self, status: str | None = None) -> list[SwarmRecord]:
        root = self.project_root()
        records = [
            self._load_swarm(root, path.parent.name)
            for path in sorted((root / ".agora" / "swarms").glob("*/SWARM.md"))
        ]
        return [record for record in records if status is None or record.status == status]

    def list_handoffs(self, swarm_id: str) -> list[HandoffRecord]:
        root = self.project_root()
        swarm = self._load_swarm(root, swarm_id)
        return [
            self._load_handoff(swarm, path.parent.name)
            for path in sorted((Path(swarm.path) / "handoffs").glob("*/HANDOFF.md"))
        ]

    @_locked_mutation("project")
    def create_work(self, data: CreateWorkInput) -> WorkRecord:
        root = self.project_root()
        context = self._validate_create_work(root, data)
        actor = context[1]
        if actor.authentication_required:
            raise PermissionError(
                f"Actor {actor.reference} requires a signed lifecycle action; "
                "prepare work.create before applying it"
            )
        return self._apply_create_work(data, context)

    @_locked_mutation("project")
    def prepare_create_work(self, data: PrepareCreateWorkInput) -> LifecycleActionRecord:
        assert_slug(data.action_id, "Lifecycle Action id")
        root = self.project_root()
        swarm, actor, _, criteria, _ = self._validate_create_work(root, data.work)
        assert_actor_identity_available(actor)
        self._assert_current_actor_key(actor)
        return self._prepare_lifecycle_action(
            root,
            id_=data.action_id,
            action="work.create",
            actor=actor,
            swarm=swarm,
            work=None,
            work_id=data.work.id,
            parameters={
                "title": data.work.title,
                "description": data.work.description,
                "acceptance-criteria": json.dumps(
                    list(criteria.items()), ensure_ascii=True, separators=(",", ":")
                ),
                "required-artifacts": json.dumps(
                    list(dict.fromkeys(data.work.required_artifacts)),
                    ensure_ascii=True,
                    separators=(",", ":"),
                ),
            },
        )

    def _validate_create_work(
        self, root: Path, data: CreateWorkInput, action: str = "work.create"
    ) -> tuple[SwarmRecord, ActorRecord, MethodContract, dict[str, str], Path]:
        assert_slug(data.id, "Work id")
        swarm = self._load_swarm(root, data.swarm_id)
        if swarm.status not in {"ready", "running"}:
            raise ValueError(f"Swarm {swarm.id} must be ready before work can be created")
        actor = self._require_actor_for_action(root, swarm, data.actor_id, action)
        contract = load_method_contract(root / ".agora" / "methods" / swarm.method)
        criteria = dict(data.acceptance_criteria)
        if len(criteria) != len(data.acceptance_criteria):
            raise ValueError("Acceptance criterion ids must be unique")
        for criterion_id in criteria:
            assert_slug(criterion_id, "Criterion id")

        path = Path(swarm.path) / "work" / data.id
        if path.exists():
            raise FileExistsError(f"Work already exists: {swarm.id}/{data.id}")
        return swarm, actor, contract, criteria, path

    def _apply_create_work(
        self,
        data: CreateWorkInput,
        context: tuple[SwarmRecord, ActorRecord, MethodContract, dict[str, str], Path],
        parent_work_ref: str | None = None,
        budget_limits: dict[str, int] | None = None,
    ) -> WorkRecord:
        swarm, actor, contract, criteria, path = context
        work = WorkRecord(
            id=data.id,
            swarm_id=swarm.id,
            title=data.title,
            description=data.description,
            state=contract.work_states[0],
            acceptance_criteria=criteria,
            satisfied_criteria=[],
            required_artifacts=list(dict.fromkeys(data.required_artifacts)),
            artifact_kinds=[],
            evidence_results=[],
            approval_roles=[],
            path=str(path),
            budget_limits=budget_limits,
            parent_work_ref=parent_work_ref,
        )
        write_new(path / "WORK.md", self._render_work(work))
        write_new(
            path / "artifacts.md",
            render_markdown(
                MarkdownDocument(
                    attributes={"schema": "agora/artifacts/v1", "artifact-kinds": []},
                    body=(
                        "# Artifacts\n\n| Kind | URI | Produced by | Timestamp |\n"
                        "| --- | --- | --- | --- |"
                    ),
                )
            ),
        )
        write_new(
            path / "evidence.md",
            render_markdown(
                MarkdownDocument(
                    attributes={"schema": "agora/evidence/v1", "results": []},
                    body=(
                        "# Evidence\n\n"
                        "| Type | Result | Artifact references | Produced by | Timestamp |\n"
                        "| --- | --- | --- | --- | --- |"
                    ),
                )
            ),
        )
        write_new(
            path / "approvals.md",
            render_markdown(
                MarkdownDocument(
                    attributes={"schema": "agora/approvals/v1", "approval-roles": []},
                    body=(
                        "# Approvals\n\n| Role | Approved by | Note | Timestamp |\n"
                        "| --- | --- | --- | --- |"
                    ),
                )
            ),
        )
        write_new(path / "interactions.md", "# Interactions\n\n")
        self._append_work_event(work, "work.created", f"state={work.state} actor={actor.reference}")
        return work

    @_locked_mutation("project")
    def decompose_work(self, data: DecomposeWorkInput) -> WorkRecord:
        root = self.project_root()
        parent, child, context = self._validate_decompose_work(root, data)
        actor = context[1]
        if actor.authentication_required:
            raise PermissionError(
                f"Actor {actor.reference} requires a signed lifecycle action; "
                "prepare work.decompose before applying it"
            )
        return self._apply_decompose_work(parent, child, context)

    @_locked_mutation("project")
    def prepare_decompose_work(self, data: PrepareDecomposeWorkInput) -> LifecycleActionRecord:
        assert_slug(data.action_id, "Lifecycle Action id")
        root = self.project_root()
        parent, child, context = self._validate_decompose_work(root, data.decomposition)
        swarm, actor, _, criteria, _ = context
        assert_actor_identity_available(actor)
        self._assert_current_actor_key(actor)
        return self._prepare_lifecycle_action(
            root,
            id_=data.action_id,
            action="work.decompose",
            actor=actor,
            swarm=swarm,
            work=parent,
            parameters={
                "child-work": child.id,
                "title": child.title,
                "description": child.description,
                "acceptance-criteria": json.dumps(
                    list(criteria.items()), ensure_ascii=True, separators=(",", ":")
                ),
                "required-artifacts": json.dumps(
                    list(dict.fromkeys(child.required_artifacts)),
                    ensure_ascii=True,
                    separators=(",", ":"),
                ),
            },
        )

    def _validate_decompose_work(
        self, root: Path, data: DecomposeWorkInput
    ) -> tuple[
        WorkRecord,
        CreateWorkInput,
        tuple[SwarmRecord, ActorRecord, MethodContract, dict[str, str], Path],
    ]:
        if data.parent_work_id == data.child_work_id:
            raise ValueError("Child work id must differ from its parent work id")
        swarm = self._load_swarm(root, data.swarm_id)
        parent = self._load_work(swarm, data.parent_work_id)
        self._assert_work_mutable(root, swarm, parent)
        child = CreateWorkInput(
            swarm_id=data.swarm_id,
            id=data.child_work_id,
            title=data.title,
            actor_id=data.actor_id,
            acceptance_criteria=data.acceptance_criteria,
            required_artifacts=data.required_artifacts,
            description=data.description,
        )
        context = self._validate_create_work(root, child, action="work.decompose")
        return parent, child, context

    def _apply_decompose_work(
        self,
        parent: WorkRecord,
        child: CreateWorkInput,
        context: tuple[SwarmRecord, ActorRecord, MethodContract, dict[str, str], Path],
    ) -> WorkRecord:
        swarm, actor, _, _, _ = context
        parent_reference = f"{swarm.id}/{parent.id}"
        child_reference = f"{swarm.id}/{child.id}"
        result = self._apply_create_work(
            child,
            context,
            parent_work_ref=parent_reference,
            budget_limits={} if parent.budget_limits is not None else None,
        )
        parent.child_work_refs = list(dict.fromkeys([*parent.child_work_refs, child_reference]))
        atomic_write(Path(parent.path) / "WORK.md", self._render_work(parent))
        self._append_work_event(
            parent,
            "work.decomposed",
            f"child={child_reference} actor={actor.reference}",
        )
        self._append_work_event(
            result,
            "work.decomposition-linked",
            f"parent={parent_reference} actor={actor.reference}",
        )
        return result

    @_locked_mutation("project")
    def waive_gate(self, data: WaiveGateInput) -> GateWaiverRecord:
        root = self.project_root()
        waiver, swarm, actor, work = self._validate_gate_waiver(root, data)
        if actor.authentication_required:
            raise PermissionError(
                f"Actor {actor.reference} requires a signed lifecycle action; "
                "prepare gate.waive before applying it"
            )
        return self._apply_gate_waiver(waiver, swarm, actor, work)

    @_locked_mutation("project")
    def prepare_gate_waiver(self, data: PrepareGateWaiverInput) -> LifecycleActionRecord:
        assert_slug(data.action_id, "Lifecycle Action id")
        root = self.project_root()
        waiver, swarm, actor, work = self._validate_gate_waiver(root, data.waiver)
        assert_actor_identity_available(actor)
        self._assert_current_actor_key(actor)
        return self._prepare_lifecycle_action(
            root,
            id_=data.action_id,
            action="gate.waive",
            actor=actor,
            swarm=swarm,
            work=work,
            parameters={
                "waiver": waiver.id,
                "gate": waiver.gate_id,
                "criteria": json.dumps(waiver.criteria, separators=(",", ":")),
                "artifacts": json.dumps(waiver.artifacts, separators=(",", ":")),
                "successful-evidence": str(waiver.successful_evidence).lower(),
                "approvals": json.dumps(waiver.approval_roles, separators=(",", ":")),
                "reason": waiver.reason,
                "evidence": json.dumps(waiver.evidence_refs, separators=(",", ":")),
            },
        )

    def _validate_gate_waiver(
        self, root: Path, data: WaiveGateInput
    ) -> tuple[WaiveGateInput, SwarmRecord, ActorRecord, WorkRecord]:
        assert_slug(data.id, "Gate Waiver id")
        assert_slug(data.gate_id, "Gate id")
        swarm = self._load_swarm(root, data.swarm_id)
        actor = self._require_actor_for_action(root, swarm, data.actor_id, "gate.waive")
        work = self._load_work(swarm, data.work_id)
        self._assert_work_mutable(root, swarm, work)
        contract = load_method_contract(root / ".agora" / "methods" / swarm.method)
        gate = contract.gates.get(data.gate_id)
        if gate is None:
            raise ValueError(f"Method Pack {swarm.method} has no gate {data.gate_id}")

        criteria = list(dict.fromkeys(data.criteria))
        artifacts = list(dict.fromkeys(data.artifacts))
        approvals = list(dict.fromkeys(data.approval_roles))
        evidence_refs = list(
            dict.fromkeys(item.strip() for item in data.evidence_refs if item.strip())
        )
        for criterion in criteria:
            assert_slug(criterion, "Waived criterion id")
        for role in approvals:
            assert_slug(role, "Waived approval role")
        if not data.reason.strip():
            raise ValueError("Gate Waiver reason cannot be empty")
        if not evidence_refs:
            raise ValueError("Gate Waiver requires at least one risk evidence reference")
        if not (criteria or artifacts or data.successful_evidence or approvals):
            raise ValueError("Gate Waiver must name at least one gate obligation")

        coverage = self._gate_waiver_coverage(work, data.gate_id)
        outstanding_criteria = {
            item
            for item in work.acceptance_criteria
            if gate.require_all_criteria
            and item not in work.satisfied_criteria
            and item not in coverage[0]
        }
        outstanding_artifacts = {
            item
            for item in work.required_artifacts
            if gate.require_required_artifacts
            and item not in work.artifact_kinds
            and item not in coverage[1]
        }
        evidence_outstanding = (
            gate.require_successful_evidence
            and "success" not in work.evidence_results
            and not coverage[2]
        )
        outstanding_approvals = {
            role
            for role in gate.required_approval_roles
            if role not in work.approval_roles and role not in coverage[3]
        }
        invalid_criteria = sorted(set(criteria) - outstanding_criteria)
        invalid_artifacts = sorted(set(artifacts) - outstanding_artifacts)
        invalid_approvals = sorted(set(approvals) - outstanding_approvals)
        if invalid_criteria:
            raise ValueError(
                "Gate Waiver criteria are not outstanding gate obligations: "
                + ", ".join(invalid_criteria)
            )
        if invalid_artifacts:
            raise ValueError(
                "Gate Waiver artifacts are not outstanding gate obligations: "
                + ", ".join(invalid_artifacts)
            )
        if data.successful_evidence and not evidence_outstanding:
            raise ValueError("Successful evidence is not an outstanding gate obligation")
        if invalid_approvals:
            raise ValueError(
                "Gate Waiver approvals are not outstanding gate obligations: "
                + ", ".join(invalid_approvals)
            )
        path = Path(work.path) / "waivers" / data.id
        if path.exists():
            raise FileExistsError(f"Gate Waiver already exists: {data.id}")
        return (
            WaiveGateInput(
                id=data.id,
                swarm_id=swarm.id,
                work_id=work.id,
                gate_id=data.gate_id,
                actor_id=actor.reference,
                reason=data.reason.strip(),
                evidence_refs=evidence_refs,
                criteria=criteria,
                artifacts=artifacts,
                successful_evidence=data.successful_evidence,
                approval_roles=approvals,
            ),
            swarm,
            actor,
            work,
        )

    def _apply_gate_waiver(
        self,
        data: WaiveGateInput,
        swarm: SwarmRecord,
        actor: ActorRecord,
        work: WorkRecord,
        action_id: str | None = None,
    ) -> GateWaiverRecord:
        waiver_root = Path(work.path) / "waivers" / data.id
        record = GateWaiverRecord(
            id=data.id,
            swarm_id=swarm.id,
            work_id=work.id,
            gate_id=data.gate_id,
            waived_criteria=data.criteria,
            waived_artifacts=data.artifacts,
            waive_successful_evidence=data.successful_evidence,
            waived_approval_roles=data.approval_roles,
            reason=data.reason,
            evidence_refs=data.evidence_refs,
            authorized_by=actor.reference,
            created_at=self._timestamp(),
            path=str(waiver_root / "WAIVER.md"),
            action_id=action_id,
        )
        write_new(waiver_root / "WAIVER.md", self._render_gate_waiver(record))
        self._append_work_event(
            work,
            "gate.waived",
            f"waiver={record.id} gate={record.gate_id} actor={actor.reference}",
        )
        return record

    def list_gate_waivers(
        self, swarm_id: str, work_id: str, gate_id: str | None = None
    ) -> list[GateWaiverRecord]:
        swarm = self._load_swarm(self.project_root(), swarm_id)
        work = self._load_work(swarm, work_id)
        records = self._load_gate_waivers(work)
        return [record for record in records if gate_id is None or record.gate_id == gate_id]

    @_locked_mutation("project")
    def satisfy_criterion(self, data: WorkActorInput, criterion_id: str) -> WorkRecord:
        root = self.project_root()
        swarm, actor, work = self._validate_satisfy_criterion(root, data, criterion_id)
        if actor.authentication_required:
            raise PermissionError(
                f"Actor {actor.reference} requires a signed lifecycle action; "
                "prepare criterion.satisfy before applying it"
            )
        return self._apply_satisfy_criterion(swarm, actor, work, criterion_id)

    @_locked_mutation("project")
    def prepare_satisfy_criterion(self, data: PrepareCriterionInput) -> LifecycleActionRecord:
        assert_slug(data.id, "Lifecycle Action id")
        root = self.project_root()
        swarm, actor, work = self._validate_satisfy_criterion(root, data, data.criterion_id)
        assert_actor_identity_available(actor)
        self._assert_current_actor_key(actor)
        return self._prepare_lifecycle_action(
            root,
            id_=data.id,
            action="criterion.satisfy",
            actor=actor,
            swarm=swarm,
            work=work,
            parameters={"criterion": data.criterion_id},
        )

    def _validate_satisfy_criterion(
        self, root: Path, data: WorkActorInput, criterion_id: str
    ) -> tuple[SwarmRecord, ActorRecord, WorkRecord]:
        swarm = self._load_swarm(root, data.swarm_id)
        actor = self._require_actor_for_action(root, swarm, data.actor_id, "criterion.satisfy")
        work = self._load_work(swarm, data.work_id)
        self._assert_work_mutable(root, swarm, work)
        if criterion_id not in work.acceptance_criteria:
            raise FileNotFoundError(f"Acceptance criterion not found: {criterion_id}")
        return swarm, actor, work

    def _apply_satisfy_criterion(
        self,
        swarm: SwarmRecord,
        actor: ActorRecord,
        work: WorkRecord,
        criterion_id: str,
    ) -> WorkRecord:
        work.satisfied_criteria = list(dict.fromkeys([*work.satisfied_criteria, criterion_id]))
        atomic_write(Path(work.path) / "WORK.md", self._render_work(work))
        self._append_work_event(
            work,
            "work.criterion-satisfied",
            f"criterion={criterion_id} actor={actor.reference}",
        )
        return work

    @_locked_mutation("project")
    def add_artifact(self, data: AddArtifactInput) -> WorkRecord:
        root = self.project_root()
        swarm, actor, work = self._validate_add_artifact(root, data)
        if actor.authentication_required:
            raise PermissionError(
                f"Actor {actor.reference} requires a signed lifecycle action; "
                "prepare artifact.add before applying it"
            )
        return self._apply_add_artifact(swarm, actor, work, data)

    @_locked_mutation("project")
    def prepare_add_artifact(self, data: PrepareArtifactInput) -> LifecycleActionRecord:
        assert_slug(data.id, "Lifecycle Action id")
        root = self.project_root()
        swarm, actor, work = self._validate_add_artifact(root, data)
        assert_actor_identity_available(actor)
        self._assert_current_actor_key(actor)
        return self._prepare_lifecycle_action(
            root,
            id_=data.id,
            action="artifact.add",
            actor=actor,
            swarm=swarm,
            work=work,
            parameters={"kind": data.kind, "uri": data.uri},
        )

    def _validate_add_artifact(
        self, root: Path, data: AddArtifactInput
    ) -> tuple[SwarmRecord, ActorRecord, WorkRecord]:
        swarm = self._load_swarm(root, data.swarm_id)
        actor = self._require_actor_for_action(root, swarm, data.actor_id, "artifact.add")
        work = self._load_work(swarm, data.work_id)
        self._assert_work_mutable(root, swarm, work)
        return swarm, actor, work

    def _apply_add_artifact(
        self,
        swarm: SwarmRecord,
        actor: ActorRecord,
        work: WorkRecord,
        data: AddArtifactInput,
    ) -> WorkRecord:
        self._record_artifact(work, data.kind, data.uri, actor.reference)
        return self._load_work(swarm, data.work_id)

    def _record_artifact(self, work: WorkRecord, kind: str, uri: str, actor_reference: str) -> None:
        path = Path(work.path) / "artifacts.md"
        document = read_markdown(path)
        kinds = strings_attribute(document.attributes, "artifact-kinds")
        document.attributes["artifact-kinds"] = list(dict.fromkeys([*kinds, kind]))
        document.body = (
            f"{document.body.rstrip()}\n| {kind} | {uri} | "
            f"{actor_reference} | {self._timestamp()} |"
        )
        atomic_write(path, render_markdown(document))
        self._append_work_event(
            work,
            "artifact.added",
            f"kind={kind} uri={uri} actor={actor_reference}",
        )

    @_locked_mutation("project")
    def add_evidence(self, data: AddEvidenceInput) -> WorkRecord:
        root = self.project_root()
        swarm, actor, work = self._validate_add_evidence(root, data)
        if actor.authentication_required:
            raise PermissionError(
                f"Actor {actor.reference} requires a signed lifecycle action; "
                "prepare evidence.add before applying it"
            )
        return self._apply_add_evidence(swarm, actor, work, data)

    @_locked_mutation("project")
    def prepare_add_evidence(self, data: PrepareEvidenceInput) -> LifecycleActionRecord:
        assert_slug(data.id, "Lifecycle Action id")
        root = self.project_root()
        swarm, actor, work = self._validate_add_evidence(root, data)
        assert_actor_identity_available(actor)
        self._assert_current_actor_key(actor)
        return self._prepare_lifecycle_action(
            root,
            id_=data.id,
            action="evidence.add",
            actor=actor,
            swarm=swarm,
            work=work,
            parameters={
                "type": data.type,
                "result": data.result,
                "artifacts": json.dumps(
                    data.artifact_refs, ensure_ascii=True, separators=(",", ":")
                ),
            },
        )

    def _validate_add_evidence(
        self, root: Path, data: AddEvidenceInput
    ) -> tuple[SwarmRecord, ActorRecord, WorkRecord]:
        swarm = self._load_swarm(root, data.swarm_id)
        actor = self._require_actor_for_action(root, swarm, data.actor_id, "evidence.add")
        work = self._load_work(swarm, data.work_id)
        self._assert_work_mutable(root, swarm, work)
        return swarm, actor, work

    def _apply_add_evidence(
        self,
        swarm: SwarmRecord,
        actor: ActorRecord,
        work: WorkRecord,
        data: AddEvidenceInput,
    ) -> WorkRecord:
        self._record_evidence(
            work,
            data.type,
            data.result,
            data.artifact_refs,
            actor.reference,
        )
        return self._load_work(swarm, data.work_id)

    def _record_evidence(
        self,
        work: WorkRecord | None,
        type_: str,
        result: str,
        artifact_refs: list[str],
        actor_reference: str,
    ) -> None:
        path = Path(work.path) / "evidence.md"
        document = read_markdown(path)
        results = strings_attribute(document.attributes, "results")
        document.attributes["results"] = [*results, result]
        references = ", ".join(artifact_refs) or "none"
        document.body = (
            f"{document.body.rstrip()}\n| {type_} | {result} | {references} | "
            f"{actor_reference} | {self._timestamp()} |"
        )
        atomic_write(path, render_markdown(document))
        self._append_work_event(
            work,
            "evidence.added",
            f"type={type_} result={result} actor={actor_reference}",
        )

    @_locked_mutation("project")
    def add_usage(self, data: AddUsageInput) -> UsageRecord:
        root = self.project_root()
        swarm, actor, work, amounts = self._validate_add_usage(root, data)
        if actor.authentication_required:
            raise PermissionError(
                f"Actor {actor.reference} requires a signed lifecycle action; "
                "prepare usage.add before applying it"
            )
        return self._apply_add_usage(work, actor, data, amounts, None)

    @_locked_mutation("project")
    def prepare_add_usage(self, data: PrepareUsageInput) -> LifecycleActionRecord:
        assert_slug(data.action_id, "Lifecycle Action id")
        root = self.project_root()
        swarm, actor, work, amounts = self._validate_add_usage(root, data.usage)
        assert_actor_identity_available(actor)
        self._assert_current_actor_key(actor)
        return self._prepare_lifecycle_action(
            root,
            id_=data.action_id,
            action="usage.add",
            actor=actor,
            swarm=swarm,
            work=work,
            parameters={
                "usage": data.usage.id,
                "amounts": json.dumps(amounts, ensure_ascii=True, separators=(",", ":")),
                "evidence": json.dumps(
                    data.usage.evidence_refs,
                    ensure_ascii=True,
                    separators=(",", ":"),
                ),
            },
        )

    def _validate_add_usage(
        self, root: Path, data: AddUsageInput
    ) -> tuple[SwarmRecord, ActorRecord, WorkRecord, dict[str, int]]:
        assert_slug(data.id, "Usage id")
        swarm = self._load_swarm(root, data.swarm_id)
        actor = self._require_actor_for_action(root, swarm, data.actor_id, "usage.add")
        work = self._load_work(swarm, data.work_id)
        self._assert_work_mutable(root, swarm, work)
        amounts = self._normalize_usage_amounts(data.amounts)
        evidence_refs = [reference.strip() for reference in data.evidence_refs]
        if not evidence_refs or any(not reference for reference in evidence_refs):
            raise ValueError("Usage requires at least one non-empty evidence reference")
        usage_path = Path(work.path) / "usage" / data.id
        if usage_path.exists():
            raise FileExistsError(f"Usage record already exists: {data.id}")
        totals = {dimension: 0 for dimension in work.budget_limits or {}}
        for record in self.list_usage(swarm.id, work.id):
            for dimension, amount in record.amounts.items():
                totals[dimension] = totals.get(dimension, 0) + amount
        if work.budget_limits is not None:
            unknown = sorted(set(amounts) - set(work.budget_limits))
            if unknown:
                raise ValueError(
                    "Usage dimensions are not available from the work budget: " + ", ".join(unknown)
                )
            exceeded = [
                dimension
                for dimension, amount in amounts.items()
                if totals.get(dimension, 0) + amount > work.budget_limits[dimension]
            ]
            if exceeded:
                detail = ", ".join(
                    f"{dimension}={totals.get(dimension, 0) + amounts[dimension]}"
                    f"/{work.budget_limits[dimension]}"
                    for dimension in exceeded
                )
                raise ValueError(f"Usage exceeds work budget: {detail}")
        return swarm, actor, work, amounts

    def _apply_add_usage(
        self,
        work: WorkRecord,
        actor: ActorRecord,
        data: AddUsageInput,
        amounts: dict[str, int],
        action_id: str | None,
    ) -> UsageRecord:
        path = Path(work.path) / "usage" / data.id / "USAGE.md"
        record = UsageRecord(
            id=data.id,
            swarm_id=work.swarm_id,
            work_id=work.id,
            actor=actor.reference,
            amounts=amounts,
            evidence_refs=[reference.strip() for reference in data.evidence_refs],
            created_at=self._timestamp(),
            path=str(path),
            action_id=action_id,
        )
        write_new(path, self._render_usage(record))
        self._append_work_event(
            work,
            "usage.added",
            f"usage={record.id} actor={record.actor} amounts="
            + json.dumps(record.amounts, ensure_ascii=True, separators=(",", ":")),
        )
        return record

    def list_usage(self, swarm_id: str, work_id: str) -> list[UsageRecord]:
        root = self.project_root()
        swarm = self._load_swarm(root, swarm_id)
        work = self._load_work(swarm, work_id)
        return [
            self._load_usage(path)
            for path in sorted((Path(work.path) / "usage").glob("*/USAGE.md"))
        ]

    def summarize_usage(self, swarm_id: str, work_id: str) -> UsageSummary:
        root = self.project_root()
        swarm = self._load_swarm(root, swarm_id)
        work = self._load_work(swarm, work_id)
        records = self.list_usage(swarm.id, work.id)
        consumed: dict[str, int] = {}
        for record in records:
            for dimension, amount in record.amounts.items():
                consumed[dimension] = consumed.get(dimension, 0) + amount
        consumed = dict(sorted(consumed.items()))
        remaining = (
            None
            if work.budget_limits is None
            else {
                dimension: limit - consumed.get(dimension, 0)
                for dimension, limit in sorted(work.budget_limits.items())
            }
        )
        return UsageSummary(
            swarm_id=swarm.id,
            work_id=work.id,
            budget_limits=work.budget_limits,
            consumed=consumed,
            remaining=remaining,
            records=len(records),
        )

    @staticmethod
    def _normalize_usage_amounts(amounts: dict[str, int]) -> dict[str, int]:
        if not amounts:
            raise ValueError("Usage requires at least one amount")
        normalized: dict[str, int] = {}
        for dimension, amount in amounts.items():
            assert_slug(dimension, "Usage dimension")
            if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
                raise ValueError(f"Usage amount must be a positive integer: {dimension}")
            normalized[dimension] = amount
        return dict(sorted(normalized.items()))

    @_locked_mutation("project")
    def delegate_approval(self, data: DelegateApprovalInput) -> ApprovalDelegationRecord:
        root = self.project_root()
        delegation, swarm, actor, target, work = self._validate_delegate_approval(root, data)
        if actor.authentication_required:
            raise PermissionError(
                f"Actor {actor.reference} requires a signed lifecycle action; "
                "prepare approval.delegate before applying it"
            )
        return self._apply_delegate_approval(delegation, swarm, actor, target, work)

    @_locked_mutation("project")
    def prepare_approval_delegation(
        self, data: PrepareApprovalDelegationInput
    ) -> LifecycleActionRecord:
        assert_slug(data.action_id, "Lifecycle Action id")
        root = self.project_root()
        delegation, swarm, actor, target, work = self._validate_delegate_approval(
            root, data.delegation
        )
        assert_actor_identity_available(actor)
        self._assert_current_actor_key(actor)
        return self._prepare_lifecycle_action(
            root,
            id_=data.action_id,
            action="approval.delegate",
            actor=actor,
            swarm=swarm,
            work=work,
            parameters={
                "delegation": delegation.id,
                "role": delegation.role_id,
                "target": target.reference,
                "reason": delegation.reason,
            },
        )

    def _validate_delegate_approval(
        self, root: Path, data: DelegateApprovalInput
    ) -> tuple[DelegateApprovalInput, SwarmRecord, ActorRecord, ActorRecord, WorkRecord]:
        assert_slug(data.id, "Approval Delegation id")
        assert_slug(data.role_id, "Approval role id")
        if not data.reason.strip():
            raise ValueError("Approval Delegation reason cannot be empty")
        swarm = self._load_swarm(root, data.swarm_id)
        actor = self._require_actor_for_action(root, swarm, data.actor_id, "approval.delegate")
        if data.role_id not in self._actor_roles(swarm, actor.reference):
            raise PermissionError(
                f"Actor {actor.reference} is not assigned to delegated role {data.role_id}"
            )
        if not self._role_allows_action(root, swarm.method, data.role_id, "approval.add"):
            raise PermissionError(f"Role {data.role_id} cannot issue work approvals")
        target = self._find_actor(root, data.to_actor_id)
        if target.reference == actor.reference:
            raise ValueError("Approval Delegation target must differ from its grantor")
        self._assert_represented_swarm_operational(root, target)
        self._assert_actor_role_compatibility(root, swarm.method, data.role_id, target)
        work = self._load_work(swarm, data.work_id)
        self._assert_work_mutable(root, swarm, work)
        if data.role_id in work.approval_roles:
            raise ValueError(f"Work already has approval for role {data.role_id}")
        path = Path(work.path) / "approval-delegations" / data.id
        if path.exists():
            raise FileExistsError(f"Approval Delegation already exists: {data.id}")
        active_for_role = [
            item.id
            for item in self._load_approval_delegations(work)
            if item.role_id == data.role_id and item.status == "active"
        ]
        if active_for_role:
            raise ValueError(
                f"Work already has an active Approval Delegation for {data.role_id}: "
                + ", ".join(active_for_role)
            )
        normalized = DelegateApprovalInput(
            id=data.id,
            swarm_id=swarm.id,
            work_id=work.id,
            role_id=data.role_id,
            actor_id=actor.reference,
            to_actor_id=target.reference,
            reason=data.reason.strip(),
        )
        return normalized, swarm, actor, target, work

    def _apply_delegate_approval(
        self,
        data: DelegateApprovalInput,
        swarm: SwarmRecord,
        actor: ActorRecord,
        target: ActorRecord,
        work: WorkRecord,
        action_id: str | None = None,
    ) -> ApprovalDelegationRecord:
        path = Path(work.path) / "approval-delegations" / data.id / "DELEGATION.md"
        record = ApprovalDelegationRecord(
            id=data.id,
            swarm_id=swarm.id,
            work_id=work.id,
            role_id=data.role_id,
            from_actor=actor.reference,
            to_actor=target.reference,
            reason=data.reason,
            status="active",
            created_at=self._timestamp(),
            path=str(path),
            action_id=action_id,
        )
        write_new(path, self._render_approval_delegation(record))
        self._append_work_event(
            work,
            "approval.delegated",
            f"delegation={record.id} role={record.role_id} "
            f"from={record.from_actor} to={record.to_actor}",
        )
        return record

    @_locked_mutation("project")
    def revoke_approval_delegation(
        self, data: RevokeApprovalDelegationInput
    ) -> ApprovalDelegationRecord:
        root = self.project_root()
        delegation, swarm, actor, work = self._validate_revoke_approval_delegation(root, data)
        if actor.authentication_required:
            raise PermissionError(
                f"Actor {actor.reference} requires a signed lifecycle action; "
                "prepare approval.delegation.revoke before applying it"
            )
        return self._apply_revoke_approval_delegation(delegation, actor, work, data.reason.strip())

    @_locked_mutation("project")
    def prepare_revoke_approval_delegation(
        self, data: RevokeApprovalDelegationInput
    ) -> LifecycleActionRecord:
        if data.action_id is None:
            raise ValueError("Approval Delegation revocation requires a Lifecycle Action id")
        assert_slug(data.action_id, "Lifecycle Action id")
        root = self.project_root()
        delegation, swarm, actor, work = self._validate_revoke_approval_delegation(root, data)
        assert_actor_identity_available(actor)
        self._assert_current_actor_key(actor)
        return self._prepare_lifecycle_action(
            root,
            id_=data.action_id,
            action="approval.delegation.revoke",
            actor=actor,
            swarm=swarm,
            work=work,
            parameters={"delegation": delegation.id, "reason": data.reason.strip()},
        )

    def _validate_revoke_approval_delegation(
        self, root: Path, data: RevokeApprovalDelegationInput
    ) -> tuple[ApprovalDelegationRecord, SwarmRecord, ActorRecord, WorkRecord]:
        assert_slug(data.delegation_id, "Approval Delegation id")
        if not data.reason.strip():
            raise ValueError("Approval Delegation revocation reason cannot be empty")
        swarm = self._load_swarm(root, data.swarm_id)
        work = self._load_work(swarm, data.work_id)
        self._assert_work_mutable(root, swarm, work)
        delegation = self._load_approval_delegation(work, data.delegation_id)
        actor = self._require_actor_for_action(
            root, swarm, data.actor_id, "approval.delegation.revoke"
        )
        if actor.reference != delegation.from_actor:
            raise PermissionError("Only the Approval Delegation grantor may revoke it")
        if delegation.status != "active":
            raise ValueError(
                f"Approval Delegation must be active before revocation: {delegation.id}"
            )
        return delegation, swarm, actor, work

    def _apply_revoke_approval_delegation(
        self,
        delegation: ApprovalDelegationRecord,
        actor: ActorRecord,
        work: WorkRecord,
        reason: str,
        action_id: str | None = None,
    ) -> ApprovalDelegationRecord:
        revoked = ApprovalDelegationRecord(
            **{
                **delegation.__dict__,
                "status": "revoked",
                "revoked_by": actor.reference,
                "revoked_at": self._timestamp(),
                "revoked_reason": reason,
                "revocation_action_id": action_id,
            }
        )
        atomic_write(Path(delegation.path), self._render_approval_delegation(revoked))
        self._append_work_event(
            work,
            "approval-delegation.revoked",
            f"delegation={delegation.id} actor={actor.reference}",
        )
        return revoked

    def list_approval_delegations(
        self, swarm_id: str, work_id: str, status: str | None = None
    ) -> list[ApprovalDelegationRecord]:
        swarm = self._load_swarm(self.project_root(), swarm_id)
        work = self._load_work(swarm, work_id)
        records = self._load_approval_delegations(work)
        return [record for record in records if status is None or record.status == status]

    @_locked_mutation("project")
    def add_approval(self, data: AddApprovalInput) -> WorkRecord:
        root = self.project_root()
        swarm, actor, work, delegation = self._validate_approval(root, data)
        if actor.authentication_required:
            raise PermissionError(
                f"Actor {actor.reference} requires a signed lifecycle action; "
                "prepare the approval before applying it"
            )
        return self._apply_approval(
            swarm, actor, work, data.role_id, data.note, delegation=delegation
        )

    @_locked_mutation("project")
    def prepare_approval(self, data: PrepareApprovalInput) -> LifecycleActionRecord:
        assert_slug(data.id, "Lifecycle Action id")
        root = self.project_root()
        swarm, actor, work, _ = self._validate_approval(root, data)
        assert_actor_identity_available(actor)
        self._assert_current_actor_key(actor)
        return self._prepare_lifecycle_action(
            root,
            id_=data.id,
            action="approval.add",
            actor=actor,
            swarm=swarm,
            work=work,
            parameters={
                "role": data.role_id,
                "note": data.note,
                "delegation": data.delegation_id or "",
            },
        )

    def _validate_approval(
        self, root: Path, data: AddApprovalInput
    ) -> tuple[SwarmRecord, ActorRecord, WorkRecord, ApprovalDelegationRecord | None]:
        assert_slug(data.role_id, "Approval role id")
        swarm = self._load_swarm(root, data.swarm_id)
        work = self._load_work(swarm, data.work_id)
        self._assert_work_mutable(root, swarm, work)
        if data.delegation_id is None:
            active_for_role = [
                item.id
                for item in self._load_approval_delegations(work)
                if item.role_id == data.role_id and item.status == "active"
            ]
            if active_for_role:
                raise ValueError(
                    "Revoke the active Approval Delegation before direct approval: "
                    + ", ".join(active_for_role)
                )
            actor = self._require_actor_for_action(root, swarm, data.actor_id, "approval.add")
            roles = self._actor_roles(swarm, actor.reference)
            if data.role_id not in roles:
                raise PermissionError(
                    f"Actor {actor.reference} is not assigned to approval role {data.role_id}"
                )
            return swarm, actor, work, None

        assert_slug(data.delegation_id, "Approval Delegation id")
        actor = self._find_actor(root, data.actor_id)
        self._assert_represented_swarm_operational(root, actor)
        delegation = self._load_approval_delegation(work, data.delegation_id)
        if delegation.status != "active":
            raise ValueError(f"Approval Delegation is not active: {delegation.id}")
        if delegation.to_actor != actor.reference:
            raise PermissionError(
                f"Approval Delegation {delegation.id} belongs to {delegation.to_actor}"
            )
        if delegation.role_id != data.role_id:
            raise ValueError(
                f"Approval Delegation {delegation.id} is for role {delegation.role_id}"
            )
        if data.role_id in work.approval_roles:
            raise ValueError(f"Work already has approval for role {data.role_id}")
        if not self._role_allows_action(root, swarm.method, data.role_id, "approval.add"):
            raise PermissionError(f"Delegated role {data.role_id} can no longer issue approvals")
        self._assert_actor_role_compatibility(root, swarm.method, data.role_id, actor)
        return swarm, actor, work, delegation

    def _apply_approval(
        self,
        swarm: SwarmRecord,
        actor: ActorRecord,
        work: WorkRecord,
        role_id: str,
        note_value: str,
        delegation: ApprovalDelegationRecord | None = None,
        action_id: str | None = None,
    ) -> WorkRecord:
        path = Path(work.path) / "approvals.md"
        document = read_markdown(path)
        original = path.read_text(encoding="utf-8")
        approval_roles = strings_attribute(document.attributes, "approval-roles")
        document.attributes["approval-roles"] = list(dict.fromkeys([*approval_roles, role_id]))
        note = note_value.replace("|", "\\|") or "Approved"
        authority = (
            f"{actor.reference} via approval-delegation:{delegation.id}"
            if delegation is not None
            else actor.reference
        )
        document.body = (
            f"{document.body.rstrip()}\n| {role_id} | {authority} | {note} | {self._timestamp()} |"
        )
        atomic_write(path, render_markdown(document))
        if delegation is not None:
            used = ApprovalDelegationRecord(
                **{
                    **delegation.__dict__,
                    "status": "used",
                    "used_by": actor.reference,
                    "used_at": self._timestamp(),
                    "used_action_id": action_id,
                }
            )
            try:
                atomic_write(Path(delegation.path), self._render_approval_delegation(used))
            except Exception:
                atomic_write(path, original)
                raise
        self._append_work_event(
            work,
            "approval.added",
            f"role={role_id} actor={actor.reference} "
            f"delegation={delegation.id if delegation is not None else 'none'}",
        )
        return self._load_work(swarm, work.id)

    @_locked_mutation("project")
    def transition_work(self, data: TransitionWorkInput) -> WorkRecord:
        root = self.project_root()
        swarm, actor, work = self._validate_work_transition(root, data)
        if actor.authentication_required:
            raise PermissionError(
                f"Actor {actor.reference} requires a signed lifecycle action; "
                "prepare the transition before applying it"
            )
        return self._apply_work_transition(root, swarm, actor, work, data.target_state)

    @_locked_mutation("project")
    def prepare_work_transition(self, data: PrepareWorkTransitionInput) -> LifecycleActionRecord:
        assert_slug(data.id, "Lifecycle Action id")
        root = self.project_root()
        swarm, actor, work = self._validate_work_transition(root, data)
        assert_actor_identity_available(actor)
        self._assert_current_actor_key(actor)
        return self._prepare_lifecycle_action(
            root,
            id_=data.id,
            action="work.transition",
            actor=actor,
            swarm=swarm,
            work=work,
            parameters={"to": data.target_state},
        )

    def _prepare_lifecycle_action(
        self,
        root: Path,
        *,
        id_: str,
        action: str,
        actor: ActorRecord,
        swarm: SwarmRecord,
        work: WorkRecord | None,
        parameters: dict[str, str],
        work_id: str | None = None,
    ) -> LifecycleActionRecord:
        action_root = root / ".agora" / "actions" / id_
        if action_root.exists():
            raise FileExistsError(f"Lifecycle Action already exists: {id_}")
        record = LifecycleActionRecord(
            id=id_,
            action=action,
            actor=actor.reference,
            swarm_id=swarm.id,
            work_id=work.id if work is not None else work_id,
            parameters=parameters,
            precondition_sha256=self._lifecycle_precondition_sha256(
                root, action, actor, swarm, work, parameters
            ),
            status="prepared",
            path=str(action_root),
            created_at=self._timestamp(),
        )
        write_new(action_root / "ACTION.md", self._render_lifecycle_action(record))
        append_entry(
            root / ".agora" / "events.md",
            (
                f"- {self._timestamp()} | lifecycle-action.prepared | action={record.id} "
                f"kind={record.action} actor={record.actor} swarm={record.swarm_id} "
                f"work={record.work_id}"
            ),
        )
        return record

    def prepare_lifecycle_authorization(
        self, data: PrepareLifecycleAuthorizationInput
    ) -> LifecycleAuthorizationRecord:
        assert_slug(data.action_id, "Lifecycle Action id")
        root = self.project_root()
        record = self._load_lifecycle_action(root / ".agora" / "actions" / data.action_id)
        if record.status != "prepared":
            raise ValueError(f"Lifecycle Action must be prepared for authorization: {record.id}")
        actor = self._find_actor(root, record.actor)
        assert_actor_identity_available(actor)
        self._assert_current_actor_key(actor)
        if actor.authentication_fingerprint is None:
            raise ValueError(f"Actor {actor.reference} has no authentication key")
        self._assert_lifecycle_precondition(root, record)
        payload = lifecycle_authorization_payload(record)
        output = Path(data.output).expanduser().resolve()
        write_new(output, payload.decode("ascii"), data.force)
        return LifecycleAuthorizationRecord(
            action_id=record.id,
            actor=actor.reference,
            algorithm="ed25519",
            fingerprint=actor.authentication_fingerprint,
            payload_sha256=hashlib.sha256(payload).hexdigest(),
            path=str(output),
        )

    @_locked_mutation("lifecycle-action")
    def apply_lifecycle_action(self, data: ApplyLifecycleActionInput) -> LifecycleActionRecord:
        assert_slug(data.action_id, "Lifecycle Action id")
        root = self.project_root()
        record = self._load_lifecycle_action(root / ".agora" / "actions" / data.action_id)
        if record.status != "prepared":
            raise ValueError(f"Lifecycle Action must be prepared before apply: {record.id}")
        self._assert_lifecycle_precondition(root, record)
        handoff_context: (
            tuple[
                SwarmRecord,
                ActorRecord,
                ActorRecord,
                ActorRecord,
                WorkRecord | None,
                str,
                str,
                str,
                Path,
            ]
            | None
        ) = None
        work_status_context: (
            tuple[
                ChangeWorkStatusInput,
                str,
                SwarmRecord,
                ActorRecord,
                WorkRecord,
                str,
            ]
            | None
        ) = None
        delegation_status_context: (
            tuple[
                ChangeDelegationStatusInput,
                str,
                str | None,
                tuple[
                    DelegationRecord,
                    SwarmRecord,
                    ActorRecord,
                    SwarmRecord,
                    WorkRecord,
                    str,
                ],
            ]
            | None
        ) = None
        delegation_create_context: (
            tuple[
                CreateDelegationInput,
                tuple[
                    SwarmRecord,
                    WorkRecord,
                    ActorRecord,
                    ActorRecord,
                    SwarmRecord,
                    dict[str, str],
                    str,
                    Path,
                ],
            ]
            | None
        ) = None
        delegation_accept_context: (
            tuple[
                PrepareDelegationActionInput,
                tuple[DelegationRecord, SwarmRecord, WorkRecord, SwarmRecord, ActorRecord],
            ]
            | None
        ) = None
        delegation_collect_context: (
            tuple[
                PrepareDelegationActionInput,
                tuple[
                    DelegationRecord,
                    SwarmRecord,
                    ActorRecord,
                    SwarmRecord,
                    WorkRecord,
                    WorkRecord,
                    str,
                ],
            ]
            | None
        ) = None
        work_create_context: (
            tuple[
                CreateWorkInput,
                tuple[SwarmRecord, ActorRecord, MethodContract, dict[str, str], Path],
            ]
            | None
        ) = None
        work_decompose_context: (
            tuple[
                WorkRecord,
                CreateWorkInput,
                tuple[SwarmRecord, ActorRecord, MethodContract, dict[str, str], Path],
            ]
            | None
        ) = None
        gate_waiver_context: tuple[WaiveGateInput, SwarmRecord, ActorRecord, WorkRecord] | None = (
            None
        )
        criterion_context: (
            tuple[PrepareCriterionInput, SwarmRecord, ActorRecord, WorkRecord] | None
        ) = None
        artifact_context: (
            tuple[PrepareArtifactInput, SwarmRecord, ActorRecord, WorkRecord] | None
        ) = None
        evidence_context: (
            tuple[PrepareEvidenceInput, SwarmRecord, ActorRecord, WorkRecord] | None
        ) = None
        usage_context: (
            tuple[AddUsageInput, SwarmRecord, ActorRecord, WorkRecord, dict[str, int]] | None
        ) = None
        approval_context: (
            tuple[
                AddApprovalInput,
                SwarmRecord,
                ActorRecord,
                WorkRecord,
                ApprovalDelegationRecord | None,
            ]
            | None
        ) = None
        approval_delegation_context: (
            tuple[
                DelegateApprovalInput,
                SwarmRecord,
                ActorRecord,
                ActorRecord,
                WorkRecord,
            ]
            | None
        ) = None
        approval_delegation_revocation_context: (
            tuple[ApprovalDelegationRecord, SwarmRecord, ActorRecord, WorkRecord, str] | None
        ) = None
        actor_key_rotation_context: (
            tuple[ActorRecord, ActorKeyRecord, ActorKeyRecord, str] | None
        ) = None
        actor_key_revocation_context: tuple[ActorRecord, ActorKeyRecord, str] | None = None
        actor_key_recovery_context: (
            tuple[ActorRecord, ActorKeyRecord, ActorKeyRecord, str] | None
        ) = None
        actor_runtime_context: tuple[SetActorRuntimeInput, ActorRecord] | None = None
        actor_assignment_context: tuple[SwarmRecord, ActorRecord, str] | None = None
        session_preparation_context: (
            tuple[
                StartSessionInput,
                tuple[
                    ProjectConfiguration,
                    SwarmRecord,
                    ActorRecord,
                    list[str],
                    WorkRecord | None,
                    Integration,
                    str,
                    str,
                    list[str],
                    bool,
                    str,
                    Path,
                    str,
                ],
            ]
            | None
        ) = None
        if record.action == "swarm.assign":
            assignment = AssignActorInput(
                swarm_id=record.swarm_id,
                role_id=record.parameters["role"],
                actor_id=record.parameters["target"],
            )
            swarm, target = self._validate_actor_assignment(root, assignment)
            actor = self._require_actor_for_action(root, swarm, record.actor, "swarm.assign")
            work = None
            actor_assignment_context = (swarm, target, assignment.role_id)
        elif record.action in {"actor.key.recover", "actor.key.revoke"}:
            swarm = self._load_swarm(root, record.swarm_id)
            actor, target, current = self._validate_actor_key_administrator(
                root,
                swarm,
                target_actor_id=record.parameters["target"],
                authorized_by=record.actor,
                action=record.action,
                target_must_be_revoked=record.action == "actor.key.recover",
            )
            expected_fingerprint = record.parameters.get(
                "from", record.parameters.get("fingerprint")
            )
            if current.fingerprint != expected_fingerprint:
                raise ValueError(f"Lifecycle Action target actor key is not canonical: {record.id}")
            work = None
            if record.action == "actor.key.revoke":
                actor_key_revocation_context = (
                    target,
                    current,
                    record.parameters["reason"],
                )
            else:
                replacement = actor_key_from_public_key(
                    target.reference,
                    record.parameters["public-key"],
                    self._actor_key_root(target),
                    self._timestamp(),
                )
                if replacement.fingerprint != record.parameters["fingerprint"]:
                    raise ValueError(f"Lifecycle Action recovery key is not canonical: {record.id}")
                self._validate_actor_key_replacement(current, replacement)
                if replacement.fingerprint == actor.authentication_fingerprint:
                    raise ValueError("Recovery key must differ from the governance authorizer key")
                actor_key_recovery_context = (
                    target,
                    current,
                    replacement,
                    record.parameters["reason"],
                )
        elif record.action == "actor.key.rotate":
            swarm = self._load_swarm(root, record.swarm_id)
            actor = self._require_actor_for_action(root, swarm, record.actor, "actor.key.rotate")
            assert_actor_identity_available(actor)
            current = self._ensure_current_actor_key(actor)
            if current.fingerprint != record.parameters["from"]:
                raise ValueError(
                    f"Lifecycle Action current actor key is not canonical: {record.id}"
                )
            replacement = actor_key_from_public_key(
                actor.reference,
                record.parameters["public-key"],
                self._actor_key_root(actor),
                self._timestamp(),
            )
            if replacement.fingerprint != record.parameters["fingerprint"]:
                raise ValueError(
                    f"Lifecycle Action replacement actor key is not canonical: {record.id}"
                )
            self._validate_actor_key_replacement(current, replacement)
            work = None
            actor_key_rotation_context = (
                actor,
                current,
                replacement,
                record.parameters["reason"],
            )
        elif record.action == "actor.runtime.update":
            runtime = SetActorRuntimeInput(
                actor_id=record.actor,
                integration=(
                    self._integration(record.parameters["integration"])
                    if record.parameters["integration"]
                    else None
                ),
                provider=record.parameters["provider"] or None,
                model=record.parameters["model"] or None,
                clear=record.parameters["clear"] == "true",
            )
            swarm = self._load_swarm(root, record.swarm_id)
            actor = self._validate_actor_runtime(root, runtime)
            actor = self._require_actor_for_action(
                root, swarm, actor.reference, "actor.runtime.update"
            )
            work = None
            actor_runtime_context = (runtime, actor)
        elif record.action == "session.prepare":
            session = StartSessionInput(
                id=record.parameters["session"],
                actor_id=record.actor,
                swarm_id=record.swarm_id,
                work_id=record.work_id,
                runner=record.parameters["runner"] or None,
                timeout_seconds=int(
                    record.parameters.get("timeout-seconds", str(DEFAULT_SESSION_TIMEOUT_SECONDS))
                ),
                max_output_bytes=int(
                    record.parameters.get("max-output-bytes", str(DEFAULT_SESSION_MAX_OUTPUT_BYTES))
                ),
            )
            context = self._validate_session_preparation(root, session)
            _, swarm, actor, _, work, _, _, _, _, _, session_id, _, _ = context
            if session_id != record.parameters["session"]:
                raise ValueError(f"Lifecycle Action session context is not canonical: {record.id}")
            session_preparation_context = (session, context)
        elif record.action == "work.create":
            creation = self._work_creation_input_from_action(record)
            context = self._validate_create_work(root, creation)
            swarm, actor, _, _, _ = context
            work = None
            if record.swarm_id != swarm.id or record.work_id != creation.id:
                raise ValueError(f"Lifecycle Action work context is not canonical: {record.id}")
            work_create_context = (creation, context)
        elif record.action == "work.decompose":
            decomposition = self._work_decomposition_input_from_action(record)
            parent, child, context = self._validate_decompose_work(root, decomposition)
            swarm, actor, _, _, _ = context
            work = parent
            if record.swarm_id != swarm.id or record.work_id != parent.id:
                raise ValueError(
                    f"Lifecycle Action decomposition context is not canonical: {record.id}"
                )
            work_decompose_context = (parent, child, context)
        elif record.action == "gate.waive":
            waiver = self._gate_waiver_input_from_action(record)
            waiver, swarm, actor, work = self._validate_gate_waiver(root, waiver)
            gate_waiver_context = (waiver, swarm, actor, work)
        elif record.action == "criterion.satisfy":
            if record.work_id is None:
                raise ValueError(f"Lifecycle Action has no criterion work: {record.id}")
            criterion = PrepareCriterionInput(
                id=record.id,
                swarm_id=record.swarm_id,
                work_id=record.work_id,
                actor_id=record.actor,
                criterion_id=record.parameters["criterion"],
            )
            swarm, actor, work = self._validate_satisfy_criterion(
                root, criterion, criterion.criterion_id
            )
            criterion_context = (criterion, swarm, actor, work)
        elif record.action == "artifact.add":
            if record.work_id is None:
                raise ValueError(f"Lifecycle Action has no artifact work: {record.id}")
            artifact = PrepareArtifactInput(
                id=record.id,
                swarm_id=record.swarm_id,
                work_id=record.work_id,
                actor_id=record.actor,
                kind=record.parameters["kind"],
                uri=record.parameters["uri"],
            )
            swarm, actor, work = self._validate_add_artifact(root, artifact)
            artifact_context = (artifact, swarm, actor, work)
        elif record.action == "evidence.add":
            if record.work_id is None:
                raise ValueError(f"Lifecycle Action has no evidence work: {record.id}")
            evidence = PrepareEvidenceInput(
                id=record.id,
                swarm_id=record.swarm_id,
                work_id=record.work_id,
                actor_id=record.actor,
                type=record.parameters["type"],
                result=record.parameters["result"],
                artifact_refs=self._string_list_parameter(record, "artifacts"),
            )
            swarm, actor, work = self._validate_add_evidence(root, evidence)
            evidence_context = (evidence, swarm, actor, work)
        elif record.action == "usage.add":
            if record.work_id is None:
                raise ValueError(f"Lifecycle Action has no usage work: {record.id}")
            usage = AddUsageInput(
                id=record.parameters["usage"],
                swarm_id=record.swarm_id,
                work_id=record.work_id,
                actor_id=record.actor,
                amounts=self._usage_amounts_parameter(record),
                evidence_refs=self._string_list_parameter(record, "evidence"),
            )
            swarm, actor, work, amounts = self._validate_add_usage(root, usage)
            usage_context = (usage, swarm, actor, work, amounts)
        elif record.action == "approval.delegate":
            if record.work_id is None:
                raise ValueError(f"Lifecycle Action has no Approval Delegation work: {record.id}")
            delegation_input = DelegateApprovalInput(
                id=record.parameters["delegation"],
                swarm_id=record.swarm_id,
                work_id=record.work_id,
                role_id=record.parameters["role"],
                actor_id=record.actor,
                to_actor_id=record.parameters["target"],
                reason=record.parameters["reason"],
            )
            delegation_input, swarm, actor, target, work = self._validate_delegate_approval(
                root, delegation_input
            )
            approval_delegation_context = (
                delegation_input,
                swarm,
                actor,
                target,
                work,
            )
        elif record.action == "approval.delegation.revoke":
            if record.work_id is None:
                raise ValueError(f"Lifecycle Action has no Approval Delegation work: {record.id}")
            revocation = RevokeApprovalDelegationInput(
                delegation_id=record.parameters["delegation"],
                swarm_id=record.swarm_id,
                work_id=record.work_id,
                actor_id=record.actor,
                reason=record.parameters["reason"],
                action_id=record.id,
            )
            delegation, swarm, actor, work = self._validate_revoke_approval_delegation(
                root, revocation
            )
            approval_delegation_revocation_context = (
                delegation,
                swarm,
                actor,
                work,
                revocation.reason,
            )
        elif record.action == "work.transition":
            if set(record.parameters) != {"to"}:
                raise ValueError(f"Lifecycle Action has invalid transition parameters: {record.id}")
            if record.work_id is None:
                raise ValueError(f"Lifecycle Action has no transition work: {record.id}")
            transition = TransitionWorkInput(
                swarm_id=record.swarm_id,
                work_id=record.work_id,
                actor_id=record.actor,
                target_state=record.parameters["to"],
            )
            swarm, actor, work = self._validate_work_transition(root, transition)
        elif record.action == "approval.add":
            if record.work_id is None:
                raise ValueError(f"Lifecycle Action has no approval work: {record.id}")
            approval = AddApprovalInput(
                swarm_id=record.swarm_id,
                work_id=record.work_id,
                actor_id=record.actor,
                role_id=record.parameters["role"],
                note=record.parameters["note"],
                delegation_id=record.parameters.get("delegation") or None,
            )
            swarm, actor, work, delegation = self._validate_approval(root, approval)
            approval_context = (approval, swarm, actor, work, delegation)
        elif record.action == "handoff.create":
            if set(record.parameters) != {"role", "from", "to", "reason"}:
                raise ValueError(f"Lifecycle Action has invalid handoff parameters: {record.id}")
            handoff = HandoffActorInput(
                id=record.id,
                swarm_id=record.swarm_id,
                role_id=record.parameters["role"],
                from_actor_id=record.parameters["from"],
                to_actor_id=record.parameters["to"],
                authorized_by=record.actor,
                reason=record.parameters["reason"],
                work_id=record.work_id,
            )
            handoff_context = self._validate_handoff(root, handoff)
            swarm, _, _, actor, work, _, _, _, _ = handoff_context
        elif record.action in {"work.block", "work.cancel", "work.resume"}:
            if record.work_id is None:
                raise ValueError(f"Lifecycle Action has no status-change work: {record.id}")
            target_status = {
                "work.block": "blocked",
                "work.cancel": "cancelled",
                "work.resume": "active",
            }[record.action]
            change = ChangeWorkStatusInput(
                id=record.id,
                swarm_id=record.swarm_id,
                work_id=record.work_id,
                actor_id=record.actor,
                reason=record.parameters["reason"],
            )
            swarm, actor, work, previous = self._validate_work_status_change(
                root, change, target_status, record.action
            )
            work_status_context = (
                change,
                target_status,
                swarm,
                actor,
                work,
                previous,
            )
        elif record.action in {
            "delegation.block",
            "delegation.cancel",
            "delegation.reject",
            "delegation.resume",
        }:
            delegation = self._load_delegation(root, record.parameters["delegation"])
            if (
                record.swarm_id != delegation.parent_swarm_id
                or record.work_id != delegation.parent_work_id
            ):
                raise ValueError(
                    f"Lifecycle Action delegation context is not canonical: {record.id}"
                )
            if record.action == "delegation.block":
                target_status = "blocked"
                authority = "parent"
                allowed_statuses = {"proposed", "accepted"}
                blocked_from = delegation.status
            elif record.action == "delegation.resume":
                if delegation.status != "blocked" or delegation.blocked_from not in {
                    "proposed",
                    "accepted",
                }:
                    raise ValueError(f"Delegation {delegation.id} has no resumable blocked state")
                target_status = delegation.blocked_from
                authority = "parent"
                allowed_statuses = {"blocked"}
                blocked_from = None
            elif record.action == "delegation.reject":
                target_status = "rejected"
                authority = "child"
                allowed_statuses = {"proposed"}
                blocked_from = None
            else:
                target_status = "cancelled"
                authority = "parent"
                allowed_statuses = {"proposed", "accepted", "blocked"}
                blocked_from = None
            change = ChangeDelegationStatusInput(
                id=record.id,
                delegation_id=delegation.id,
                actor_id=record.actor,
                reason=record.parameters["reason"],
            )
            context = self._validate_delegation_status_change(
                root,
                change,
                target_status=target_status,
                action=record.action,
                authority=authority,
                allowed_statuses=allowed_statuses,
            )
            _, swarm, actor, _, work, _ = context
            delegation_status_context = (change, target_status, blocked_from, context)
        elif record.action == "delegation.create":
            creation = self._delegation_creation_input_from_action(record)
            context = self._validate_create_delegation(root, creation)
            swarm, work, _, actor, _, _, _, _ = context
            if record.swarm_id != swarm.id or record.work_id != work.id:
                raise ValueError(
                    f"Lifecycle Action delegation context is not canonical: {record.id}"
                )
            delegation_create_context = (creation, context)
        elif record.action == "delegation.accept":
            acceptance = PrepareDelegationActionInput(
                id=record.id,
                delegation_id=record.parameters["delegation"],
                actor_id=record.actor,
            )
            context = self._validate_accept_delegation(root, acceptance, record.id)
            delegation, swarm, work, _, actor = context
            if (
                record.swarm_id != delegation.parent_swarm_id
                or record.work_id != delegation.parent_work_id
            ):
                raise ValueError(
                    f"Lifecycle Action delegation context is not canonical: {record.id}"
                )
            delegation_accept_context = (acceptance, context)
        elif record.action == "delegation.collect":
            collection = PrepareDelegationActionInput(
                id=record.id,
                delegation_id=record.parameters["delegation"],
                actor_id=record.actor,
            )
            context = self._validate_collect_delegation(root, collection, record.id)
            delegation, swarm, actor, _, _, work, _ = context
            if (
                record.swarm_id != delegation.parent_swarm_id
                or record.work_id != delegation.parent_work_id
            ):
                raise ValueError(
                    f"Lifecycle Action delegation context is not canonical: {record.id}"
                )
            delegation_collect_context = (collection, context)
        else:
            raise ValueError(f"Unsupported Lifecycle Action kind: {record.action}")
        assert_actor_identity_available(actor)
        self._assert_current_actor_key(actor)

        fingerprint: str | None = None
        public_key: str | None = None
        payload_sha256: str | None = None
        signature: str | None = None
        if actor.authentication_required and data.signature is None:
            raise PermissionError(
                f"Actor {actor.reference} requires a signed lifecycle authorization"
            )
        if data.signature is not None:
            fingerprint, payload_sha256, public_key, signature = verify_lifecycle_authorization(
                actor, record, Path(data.signature).expanduser().resolve()
            )

        if record.action == "swarm.assign":
            assert actor_assignment_context is not None
            swarm, target, role_id = actor_assignment_context
            self._apply_actor_assignment(root, swarm, target, role_id, record.id)
        elif record.action == "actor.key.revoke":
            assert actor_key_revocation_context is not None
            target, current, reason = actor_key_revocation_context
            self._apply_actor_key_revocation(root, target, current, reason)
        elif record.action == "actor.key.recover":
            assert actor_key_recovery_context is not None
            target, current, replacement, reason = actor_key_recovery_context
            self._apply_actor_key_rotation(root, target, current, replacement, reason)
        elif record.action == "actor.key.rotate":
            assert actor_key_rotation_context is not None
            actor, current, replacement, reason = actor_key_rotation_context
            self._apply_actor_key_rotation(root, actor, current, replacement, reason)
        elif record.action == "actor.runtime.update":
            assert actor_runtime_context is not None
            runtime, actor = actor_runtime_context
            self._apply_actor_runtime(root, actor, runtime)
        elif record.action == "session.prepare":
            assert session_preparation_context is not None
            session, context = session_preparation_context
            self._apply_session_preparation(root, session, context, record.id)
        elif record.action == "work.create":
            assert work_create_context is not None
            creation, context = work_create_context
            self._apply_create_work(creation, context)
        elif record.action == "work.decompose":
            assert work_decompose_context is not None
            parent, child, context = work_decompose_context
            self._apply_decompose_work(parent, child, context)
        elif record.action == "gate.waive":
            assert gate_waiver_context is not None
            waiver, swarm, actor, work = gate_waiver_context
            self._apply_gate_waiver(waiver, swarm, actor, work, record.id)
        elif record.action == "criterion.satisfy":
            assert criterion_context is not None
            criterion, swarm, actor, work = criterion_context
            self._apply_satisfy_criterion(swarm, actor, work, criterion.criterion_id)
        elif record.action == "artifact.add":
            assert artifact_context is not None
            artifact, swarm, actor, work = artifact_context
            self._apply_add_artifact(swarm, actor, work, artifact)
        elif record.action == "evidence.add":
            assert evidence_context is not None
            evidence, swarm, actor, work = evidence_context
            self._apply_add_evidence(swarm, actor, work, evidence)
        elif record.action == "usage.add":
            assert usage_context is not None
            usage, _, actor, work, amounts = usage_context
            self._apply_add_usage(work, actor, usage, amounts, record.id)
        elif record.action == "approval.delegate":
            assert approval_delegation_context is not None
            delegation_input, swarm, actor, target, work = approval_delegation_context
            self._apply_delegate_approval(delegation_input, swarm, actor, target, work, record.id)
        elif record.action == "approval.delegation.revoke":
            assert approval_delegation_revocation_context is not None
            delegation, _, actor, work, reason = approval_delegation_revocation_context
            self._apply_revoke_approval_delegation(delegation, actor, work, reason, record.id)
        elif record.action == "work.transition":
            self._apply_work_transition(root, swarm, actor, work, record.parameters["to"])
        elif record.action == "approval.add":
            assert approval_context is not None
            approval, swarm, actor, work, delegation = approval_context
            self._apply_approval(
                swarm,
                actor,
                work,
                approval.role_id,
                approval.note,
                delegation=delegation,
                action_id=record.id,
            )
        elif record.action == "handoff.create":
            assert handoff_context is not None
            self._apply_handoff(root, *handoff_context)
        elif record.action in {"work.block", "work.cancel", "work.resume"}:
            assert work_status_context is not None
            change, target_status, swarm, actor, work, previous = work_status_context
            self._apply_work_status_change(
                root,
                change,
                target_status,
                record.action,
                swarm,
                actor,
                work,
                previous,
            )
        elif record.action in {
            "delegation.block",
            "delegation.cancel",
            "delegation.reject",
            "delegation.resume",
        }:
            assert delegation_status_context is not None
            change, target_status, blocked_from, context = delegation_status_context
            self._apply_delegation_status_change(
                root,
                change,
                target_status=target_status,
                action=record.action,
                blocked_from=blocked_from,
                context=context,
            )
        elif record.action == "delegation.create":
            assert delegation_create_context is not None
            creation, context = delegation_create_context
            self._apply_create_delegation(root, creation, context)
        elif record.action == "delegation.accept":
            assert delegation_accept_context is not None
            acceptance, context = delegation_accept_context
            self._apply_accept_delegation(root, acceptance, record.id, context)
        else:
            assert delegation_collect_context is not None
            collection, context = delegation_collect_context
            self._apply_collect_delegation(root, record.id, context)
        applied = LifecycleActionRecord(
            **{
                **record.__dict__,
                "status": "applied",
                "applied_at": self._timestamp(),
                "authentication_verified": fingerprint is not None,
                "authentication_fingerprint": fingerprint,
                "authentication_public_key": public_key,
                "authorization_sha256": payload_sha256,
                "authorization_signature": signature,
            }
        )
        atomic_write(Path(record.path) / "ACTION.md", self._render_lifecycle_action(applied))
        append_entry(
            root / ".agora" / "events.md",
            f"- {self._timestamp()} | lifecycle-action.applied | action={record.id}",
        )
        return applied

    @staticmethod
    def _string_list_parameter(record: LifecycleActionRecord, key: str) -> list[str]:
        try:
            value = json.loads(record.parameters[key])
        except json.JSONDecodeError as error:
            raise ValueError(
                f"Lifecycle Action has invalid JSON parameter {key}: {record.id}"
            ) from error
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise ValueError(f"Lifecycle Action parameter {key} must be a string list: {record.id}")
        return value

    @classmethod
    def _budget_limits_parameter(
        cls, record: LifecycleActionRecord, key: str = "budget-limits"
    ) -> dict[str, int] | None:
        if key not in record.parameters:
            return None
        try:
            value = json.loads(record.parameters[key])
        except json.JSONDecodeError as error:
            raise ValueError(
                f"Lifecycle Action has invalid JSON parameter {key}: {record.id}"
            ) from error
        if value is not None and (
            not isinstance(value, dict)
            or any(
                not isinstance(name, str) or not isinstance(limit, int) or isinstance(limit, bool)
                for name, limit in value.items()
            )
        ):
            raise ValueError(
                f"Lifecycle Action parameter {key} must be an integer map or null: {record.id}"
            )
        return cls._normalize_budget_limits(value)

    @classmethod
    def _usage_amounts_parameter(cls, record: LifecycleActionRecord) -> dict[str, int]:
        try:
            value = json.loads(record.parameters["amounts"])
        except json.JSONDecodeError as error:
            raise ValueError(f"Lifecycle Action has invalid usage amounts: {record.id}") from error
        if not isinstance(value, dict):
            raise ValueError(f"Lifecycle Action usage amounts must be a map: {record.id}")
        return cls._normalize_usage_amounts(value)

    @classmethod
    def _artifact_promotions_parameter(cls, record: LifecycleActionRecord) -> dict[str, str]:
        if "artifact-promotions" not in record.parameters:
            return {}
        try:
            value = json.loads(record.parameters["artifact-promotions"])
        except json.JSONDecodeError as error:
            raise ValueError(
                f"Lifecycle Action has invalid artifact promotions: {record.id}"
            ) from error
        if not isinstance(value, dict) or any(
            not isinstance(source, str) or not isinstance(target, str)
            for source, target in value.items()
        ):
            raise ValueError(
                f"Lifecycle Action artifact promotions must be a string map: {record.id}"
            )
        return cls._normalize_artifact_promotions(value)

    @classmethod
    def _work_creation_input_from_action(cls, record: LifecycleActionRecord) -> CreateWorkInput:
        if record.work_id is None:
            raise ValueError(f"Lifecycle Action has no created work id: {record.id}")
        try:
            raw_criteria = json.loads(record.parameters["acceptance-criteria"])
        except json.JSONDecodeError as error:
            raise ValueError(
                f"Lifecycle Action has invalid work acceptance criteria: {record.id}"
            ) from error
        if not isinstance(raw_criteria, list) or any(
            not isinstance(item, list)
            or len(item) != 2
            or any(not isinstance(value, str) for value in item)
            for item in raw_criteria
        ):
            raise ValueError(f"Lifecycle Action has invalid work acceptance criteria: {record.id}")
        return CreateWorkInput(
            swarm_id=record.swarm_id,
            id=record.work_id,
            title=record.parameters["title"],
            actor_id=record.actor,
            acceptance_criteria=[(item[0], item[1]) for item in raw_criteria],
            required_artifacts=cls._string_list_parameter(record, "required-artifacts"),
            description=record.parameters["description"],
        )

    @classmethod
    def _work_decomposition_input_from_action(
        cls, record: LifecycleActionRecord
    ) -> DecomposeWorkInput:
        if record.work_id is None:
            raise ValueError(f"Lifecycle Action has no parent work id: {record.id}")
        try:
            raw_criteria = json.loads(record.parameters["acceptance-criteria"])
        except json.JSONDecodeError as error:
            raise ValueError(
                f"Lifecycle Action has invalid decomposition acceptance criteria: {record.id}"
            ) from error
        if not isinstance(raw_criteria, list) or any(
            not isinstance(item, list)
            or len(item) != 2
            or any(not isinstance(value, str) for value in item)
            for item in raw_criteria
        ):
            raise ValueError(
                f"Lifecycle Action has invalid decomposition acceptance criteria: {record.id}"
            )
        return DecomposeWorkInput(
            swarm_id=record.swarm_id,
            parent_work_id=record.work_id,
            child_work_id=record.parameters["child-work"],
            title=record.parameters["title"],
            actor_id=record.actor,
            acceptance_criteria=[(item[0], item[1]) for item in raw_criteria],
            required_artifacts=cls._string_list_parameter(record, "required-artifacts"),
            description=record.parameters["description"],
        )

    @classmethod
    def _gate_waiver_input_from_action(cls, record: LifecycleActionRecord) -> WaiveGateInput:
        if record.work_id is None:
            raise ValueError(f"Lifecycle Action has no waiver work: {record.id}")
        return WaiveGateInput(
            id=record.parameters["waiver"],
            swarm_id=record.swarm_id,
            work_id=record.work_id,
            gate_id=record.parameters["gate"],
            actor_id=record.actor,
            reason=record.parameters["reason"],
            evidence_refs=cls._string_list_parameter(record, "evidence"),
            criteria=cls._string_list_parameter(record, "criteria"),
            artifacts=cls._string_list_parameter(record, "artifacts"),
            successful_evidence=record.parameters["successful-evidence"] == "true",
            approval_roles=cls._string_list_parameter(record, "approvals"),
        )

    @staticmethod
    def _delegation_creation_input_from_action(
        record: LifecycleActionRecord,
    ) -> CreateDelegationInput:
        if record.work_id is None:
            raise ValueError(f"Lifecycle Action has no parent work: {record.id}")
        try:
            raw_criteria = json.loads(record.parameters["acceptance-criteria"])
            raw_artifacts = json.loads(record.parameters["required-artifacts"])
        except json.JSONDecodeError as error:
            raise ValueError(
                f"Lifecycle Action has invalid delegation JSON parameters: {record.id}"
            ) from error
        if not isinstance(raw_criteria, list) or any(
            not isinstance(item, list)
            or len(item) != 2
            or any(not isinstance(value, str) for value in item)
            for item in raw_criteria
        ):
            raise ValueError(
                f"Lifecycle Action has invalid delegation acceptance criteria: {record.id}"
            )
        if not isinstance(raw_artifacts, list) or any(
            not isinstance(value, str) for value in raw_artifacts
        ):
            raise ValueError(
                f"Lifecycle Action has invalid delegation required artifacts: {record.id}"
            )
        return CreateDelegationInput(
            id=record.parameters["delegation"],
            parent_swarm_id=record.swarm_id,
            parent_work_id=record.work_id,
            child_actor_id=record.parameters["child-actor"],
            child_work_id=record.parameters["child-work"],
            actor_id=record.actor,
            title=record.parameters["title"],
            description=record.parameters["description"],
            acceptance_criteria=[(item[0], item[1]) for item in raw_criteria],
            required_artifacts=raw_artifacts,
            result_kind=record.parameters["result-kind"],
            budget_limits=AgoraWorkspace._budget_limits_parameter(record),
            artifact_promotions=AgoraWorkspace._artifact_promotions_parameter(record),
        )

    def list_lifecycle_actions(self, status: str | None = None) -> list[LifecycleActionRecord]:
        root = self.project_root()
        records = [
            self._load_lifecycle_action(path.parent)
            for path in sorted((root / ".agora" / "actions").glob("*/ACTION.md"))
        ]
        return [record for record in records if status is None or record.status == status]

    def _validate_work_transition(
        self, root: Path, data: TransitionWorkInput
    ) -> tuple[SwarmRecord, ActorRecord, WorkRecord]:
        swarm = self._load_swarm(root, data.swarm_id)
        actor = self._require_actor_for_action(root, swarm, data.actor_id, "work.transition")
        work = self._load_work(swarm, data.work_id)
        self._assert_work_mutable(root, swarm, work)
        contract = load_method_contract(root / ".agora" / "methods" / swarm.method)
        transition = next(
            (
                rule
                for rule in contract.transitions
                if rule.source == work.state and rule.target == data.target_state
            ),
            None,
        )
        if transition is None:
            allowed_targets = [
                rule.target for rule in contract.transitions if rule.source == work.state
            ]
            raise ValueError(
                f"Invalid transition {work.state} -> {data.target_state}; "
                f"allowed targets: {', '.join(allowed_targets) or 'none'}"
            )
        actor_roles = self._actor_roles(swarm, actor.reference)
        if transition.roles and not any(role in transition.roles for role in actor_roles):
            raise PermissionError(
                f"Actor {actor.reference} cannot perform transition {work.state} -> "
                f"{data.target_state}; required roles: {', '.join(transition.roles)}"
            )
        if data.target_state == contract.terminal_state:
            self._assert_child_work_closed(root, swarm, work)
            self._assert_no_active_approval_delegations(work)
        self._assert_wip_limit(swarm, work, data.target_state, contract.wip_limits)
        if transition.gate is not None:
            self._assert_work_gate(work, contract.gates[transition.gate], transition.gate)
        return swarm, actor, work

    def _apply_work_transition(
        self,
        root: Path,
        swarm: SwarmRecord,
        actor: ActorRecord,
        work: WorkRecord,
        target_state: str,
    ) -> WorkRecord:
        previous = work.state
        work.state = target_state
        atomic_write(Path(work.path) / "WORK.md", self._render_work(work))
        self._append_work_event(
            work,
            "work.transitioned",
            f"from={previous} to={target_state} actor={actor.reference}",
        )
        self._refresh_swarm_status(root, swarm)
        return work

    def show_work(self, swarm_id: str, work_id: str) -> WorkRecord:
        swarm = self._load_swarm(self.project_root(), swarm_id)
        return self._load_work(swarm, work_id)

    def list_work(
        self,
        swarm_id: str | None = None,
        state: str | None = None,
        operational_status: str | None = None,
    ) -> list[WorkRecord]:
        swarms = [self.show_swarm(swarm_id)] if swarm_id is not None else self.list_swarms()
        records = [
            self._load_work(swarm, path.parent.name)
            for swarm in swarms
            for path in sorted((Path(swarm.path) / "work").glob("*/WORK.md"))
        ]
        return [
            record
            for record in records
            if (state is None or record.state == state)
            and (operational_status is None or record.operational_status == operational_status)
        ]

    @_locked_mutation("project")
    def block_work(self, data: ChangeWorkStatusInput) -> StatusChangeRecord:
        return self._change_work_status(data, "blocked", "work.block")

    @_locked_mutation("project")
    def prepare_block_work(self, data: ChangeWorkStatusInput) -> LifecycleActionRecord:
        return self._prepare_work_status_change(data, "blocked", "work.block")

    @_locked_mutation("project")
    def resume_work(self, data: ChangeWorkStatusInput) -> StatusChangeRecord:
        return self._change_work_status(data, "active", "work.resume")

    @_locked_mutation("project")
    def prepare_resume_work(self, data: ChangeWorkStatusInput) -> LifecycleActionRecord:
        return self._prepare_work_status_change(data, "active", "work.resume")

    @_locked_mutation("project")
    def cancel_work(self, data: ChangeWorkStatusInput) -> StatusChangeRecord:
        return self._change_work_status(data, "cancelled", "work.cancel")

    @_locked_mutation("project")
    def prepare_cancel_work(self, data: ChangeWorkStatusInput) -> LifecycleActionRecord:
        return self._prepare_work_status_change(data, "cancelled", "work.cancel")

    def list_work_status_changes(self, swarm_id: str, work_id: str) -> list[StatusChangeRecord]:
        work = self.show_work(swarm_id, work_id)
        records = [
            self._load_status_change(path.parent)
            for path in sorted((Path(work.path) / "status-changes").glob("*/STATUS.md"))
        ]
        return sorted(records, key=lambda item: (item.sequence, item.created_at, item.id))

    def _change_work_status(
        self,
        data: ChangeWorkStatusInput,
        target_status: str,
        action: str,
    ) -> StatusChangeRecord:
        root = self.project_root()
        swarm, actor, work, previous = self._validate_work_status_change(
            root, data, target_status, action
        )
        if actor.authentication_required:
            raise PermissionError(
                f"Actor {actor.reference} requires a signed lifecycle action; "
                f"prepare {action} before applying it"
            )
        return self._apply_work_status_change(
            root, data, target_status, action, swarm, actor, work, previous
        )

    def _prepare_work_status_change(
        self,
        data: ChangeWorkStatusInput,
        target_status: str,
        action: str,
    ) -> LifecycleActionRecord:
        if data.id is None:
            raise ValueError(f"Prepared {action} requires an explicit id")
        root = self.project_root()
        swarm, actor, work, _ = self._validate_work_status_change(root, data, target_status, action)
        assert_actor_identity_available(actor)
        self._assert_current_actor_key(actor)
        return self._prepare_lifecycle_action(
            root,
            id_=data.id,
            action=action,
            actor=actor,
            swarm=swarm,
            work=work,
            parameters={"reason": data.reason.strip()},
        )

    def _validate_work_status_change(
        self,
        root: Path,
        data: ChangeWorkStatusInput,
        target_status: str,
        action: str,
    ) -> tuple[SwarmRecord, ActorRecord, WorkRecord, str]:
        if not data.reason.strip():
            raise ValueError("Work status change reason cannot be empty")
        swarm = self._load_swarm(root, data.swarm_id)
        actor = self._require_actor_for_action(root, swarm, data.actor_id, action)
        work = self._load_work(swarm, data.work_id)
        contract = load_method_contract(root / ".agora" / "methods" / swarm.method)
        if work.state == contract.terminal_state:
            raise ValueError(f"Completed work cannot change operational status: {work.id}")
        previous = work.operational_status
        allowed = {
            ("active", "blocked"),
            ("blocked", "active"),
            ("active", "cancelled"),
            ("blocked", "cancelled"),
        }
        if (previous, target_status) not in allowed:
            raise ValueError(
                f"Work {work.id} cannot change operational status {previous} -> {target_status}"
            )
        if target_status == "cancelled":
            self._assert_child_work_closed(root, swarm, work)
            self._assert_no_active_approval_delegations(work)
            open_delegations = [
                item.id
                for item in self.list_delegations()
                if item.parent_swarm_id == swarm.id
                and item.parent_work_id == work.id
                and item.status in {"proposed", "accepted", "blocked"}
            ]
            if open_delegations:
                raise ValueError(
                    f"Work {swarm.id}/{work.id} has open delegations; close them first: "
                    f"{', '.join(open_delegations)}"
                )
        change_root = Path(work.path) / "status-changes"
        self._assert_status_change_id_available(change_root, data.id)
        return swarm, actor, work, previous

    def _assert_child_work_closed(self, root: Path, swarm: SwarmRecord, parent: WorkRecord) -> None:
        open_children: list[str] = []
        contract = load_method_contract(root / ".agora" / "methods" / swarm.method)
        for reference in parent.child_work_refs:
            owner, separator, work_id = reference.partition("/")
            if not separator or owner != swarm.id:
                raise ValueError(
                    f"Work {swarm.id}/{parent.id} has invalid child work reference: {reference}"
                )
            child = self._load_work(swarm, work_id)
            if child.operational_status != "cancelled" and child.state != contract.terminal_state:
                open_children.append(reference)
        if open_children:
            raise ValueError(
                f"Work {swarm.id}/{parent.id} has open child work; close it first: "
                f"{', '.join(open_children)}"
            )

    def _assert_no_active_approval_delegations(self, work: WorkRecord) -> None:
        active = [
            delegation.id
            for delegation in self._load_approval_delegations(work)
            if delegation.status == "active"
        ]
        if active:
            raise ValueError(
                f"Work {work.swarm_id}/{work.id} has active Approval Delegations; "
                f"consume or revoke them first: {', '.join(active)}"
            )

    def _apply_work_status_change(
        self,
        root: Path,
        data: ChangeWorkStatusInput,
        target_status: str,
        action: str,
        swarm: SwarmRecord,
        actor: ActorRecord,
        work: WorkRecord,
        previous: str,
    ) -> StatusChangeRecord:
        change_root = Path(work.path) / "status-changes"
        work.operational_status = _work_operational_status(target_status)
        work.status_reason = data.reason.strip()
        work.status_by = actor.reference
        work.status_at = self._timestamp()
        atomic_write(Path(work.path) / "WORK.md", self._render_work(work))
        record = self._record_status_change(
            subject_type="work",
            subject=f"{swarm.id}/{work.id}",
            action=action,
            previous_status=previous,
            target_status=target_status,
            actor=actor.reference,
            reason=data.reason.strip(),
            root=change_root,
            id_=data.id,
        )
        self._append_work_event(
            work,
            action,
            f"from={previous} to={target_status} actor={actor.reference} change={record.id}",
        )
        self._refresh_swarm_status(root, swarm)
        return record

    @_locked_mutation("project")
    def create_delegation(self, data: CreateDelegationInput) -> DelegationRecord:
        root = self.project_root()
        context = self._validate_create_delegation(root, data)
        requester = context[3]
        if requester.authentication_required:
            raise PermissionError(
                f"Actor {requester.reference} requires a signed lifecycle action; "
                "prepare delegation.create before applying it"
            )
        return self._apply_create_delegation(root, data, context)

    @_locked_mutation("project")
    def prepare_create_delegation(
        self, data: PrepareCreateDelegationInput
    ) -> LifecycleActionRecord:
        assert_slug(data.action_id, "Lifecycle Action id")
        if data.delegation.id is None:
            raise ValueError("Prepared delegation.create requires an explicit delegation id")
        root = self.project_root()
        context = self._validate_create_delegation(root, data.delegation)
        parent, parent_work, child_actor, requester, _, criteria, delegation_id, _ = context
        budget_limits = self._validate_delegation_budget(root, parent_work, data.delegation)
        artifact_promotions = self._normalize_artifact_promotions(
            data.delegation.artifact_promotions
        )
        assert_actor_identity_available(requester)
        self._assert_current_actor_key(requester)
        return self._prepare_lifecycle_action(
            root,
            id_=data.action_id,
            action="delegation.create",
            actor=requester,
            swarm=parent,
            work=parent_work,
            parameters={
                "delegation": delegation_id,
                "child-actor": child_actor.reference,
                "child-work": data.delegation.child_work_id,
                "title": data.delegation.title,
                "description": data.delegation.description,
                "acceptance-criteria": json.dumps(
                    list(criteria.items()), ensure_ascii=True, separators=(",", ":")
                ),
                "required-artifacts": json.dumps(
                    list(dict.fromkeys(data.delegation.required_artifacts)),
                    ensure_ascii=True,
                    separators=(",", ":"),
                ),
                "result-kind": data.delegation.result_kind,
                "budget-limits": json.dumps(
                    budget_limits, ensure_ascii=True, separators=(",", ":")
                ),
                "artifact-promotions": json.dumps(
                    artifact_promotions, ensure_ascii=True, separators=(",", ":")
                ),
            },
        )

    def _validate_create_delegation(
        self, root: Path, data: CreateDelegationInput
    ) -> tuple[
        SwarmRecord,
        WorkRecord,
        ActorRecord,
        ActorRecord,
        SwarmRecord,
        dict[str, str],
        str,
        Path,
    ]:
        assert_slug(data.child_work_id, "Child work id")
        assert_slug(data.result_kind, "Delegation result kind")
        parent = self._load_swarm(root, data.parent_swarm_id)
        if parent.status not in {"ready", "running"}:
            raise ValueError(f"Parent swarm {parent.id} must be ready before work is delegated")
        parent_work = self._load_work(parent, data.parent_work_id)
        self._assert_work_mutable(root, parent, parent_work)
        parent_contract = load_method_contract(root / ".agora" / "methods" / parent.method)
        if parent_work.state == parent_contract.terminal_state:
            raise ValueError(f"Completed work cannot be delegated: {parent_work.id}")

        child_actor = self._find_actor(root, data.child_actor_id)
        if child_actor.represented_swarm is None:
            raise ValueError(f"Actor {child_actor.reference} does not represent a child swarm")
        self._assert_represented_swarm_operational(root, child_actor)
        child_actor_roles = self._actor_roles(parent, child_actor.reference)
        if not child_actor_roles:
            raise ValueError(
                f"Child actor {child_actor.reference} is not assigned to parent swarm {parent.id}"
            )

        requester = self._find_actor(root, data.actor_id)
        if requester.reference == child_actor.reference:
            self._require_actor_for_action(root, parent, data.actor_id, "work.delegate")
        else:
            self._require_actor_for_action(root, parent, data.actor_id, "delegation.manage")
        child = self._load_swarm(root, child_actor.represented_swarm)
        if (Path(child.path) / "work" / data.child_work_id).exists():
            raise FileExistsError(f"Child work already exists: {child.id}/{data.child_work_id}")

        criteria = dict(data.acceptance_criteria)
        if len(criteria) != len(data.acceptance_criteria):
            raise ValueError("Delegated acceptance criterion ids must be unique")
        for criterion_id in criteria:
            assert_slug(criterion_id, "Delegated criterion id")
        self._validate_delegation_budget(root, parent_work, data)
        artifact_promotions = self._normalize_artifact_promotions(data.artifact_promotions)
        missing_required_promotions = sorted(
            set(artifact_promotions) - set(data.required_artifacts)
        )
        if missing_required_promotions:
            raise ValueError(
                "Promoted child artifacts must also be required artifacts: "
                f"{', '.join(missing_required_promotions)}"
            )
        delegation_id = data.id or self._now().astimezone(UTC).strftime("delegation-%Y%m%dt%H%M%sz")
        assert_slug(delegation_id, "Delegation id")
        path = root / ".agora" / "delegations" / delegation_id / "DELEGATION.md"
        if path.exists():
            raise FileExistsError(f"Delegation already exists: {delegation_id}")
        return parent, parent_work, child_actor, requester, child, criteria, delegation_id, path

    def _validate_delegation_budget(
        self,
        root: Path,
        parent_work: WorkRecord,
        data: CreateDelegationInput,
    ) -> dict[str, int] | None:
        requested = self._normalize_budget_limits(data.budget_limits)
        if parent_work.budget_limits is None:
            return requested
        effective = requested or {}
        unknown = sorted(set(effective) - set(parent_work.budget_limits))
        if unknown:
            raise ValueError(
                "Delegation budget dimensions are not available from parent work: "
                f"{', '.join(unknown)}"
            )
        allocated = {dimension: 0 for dimension in parent_work.budget_limits}
        for delegation in self.list_delegations():
            if (
                delegation.parent_swarm_id != data.parent_swarm_id
                or delegation.parent_work_id != data.parent_work_id
                or delegation.status == "rejected"
            ):
                continue
            for dimension, limit in (delegation.budget_limits or {}).items():
                if dimension in allocated:
                    allocated[dimension] += limit
        exceeded = [
            f"{dimension}={allocated[dimension] + effective.get(dimension, 0)}"
            f"/{parent_work.budget_limits[dimension]}"
            for dimension in sorted(parent_work.budget_limits)
            if allocated[dimension] + effective.get(dimension, 0)
            > parent_work.budget_limits[dimension]
        ]
        if exceeded:
            raise ValueError(
                "Delegation budget exceeds parent work allocation: " + ", ".join(exceeded)
            )
        return effective

    @staticmethod
    def _normalize_budget_limits(
        limits: dict[str, int] | None,
    ) -> dict[str, int] | None:
        if limits is None:
            return None
        normalized: dict[str, int] = {}
        for dimension, limit in sorted(limits.items()):
            assert_slug(dimension, "Delegation budget dimension")
            if not isinstance(limit, int) or isinstance(limit, bool):
                raise ValueError(f"Delegation budget {dimension} must be an integer")
            if limit < 0:
                raise ValueError(f"Delegation budget {dimension} cannot be negative")
            normalized[dimension] = limit
        return normalized

    @staticmethod
    def _normalize_artifact_promotions(promotions: dict[str, str]) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for source, target in sorted(promotions.items()):
            assert_slug(source, "Promoted child artifact kind")
            assert_slug(target, "Promoted parent artifact kind")
            normalized[source] = target
        return normalized

    def _apply_create_delegation(
        self,
        root: Path,
        data: CreateDelegationInput,
        context: tuple[
            SwarmRecord,
            WorkRecord,
            ActorRecord,
            ActorRecord,
            SwarmRecord,
            dict[str, str],
            str,
            Path,
        ],
    ) -> DelegationRecord:
        parent, parent_work, child_actor, requester, child, criteria, delegation_id, path = context
        budget_limits = self._validate_delegation_budget(root, parent_work, data)
        artifact_promotions = self._normalize_artifact_promotions(data.artifact_promotions)
        record = DelegationRecord(
            id=delegation_id,
            parent_swarm_id=parent.id,
            parent_work_id=parent_work.id,
            child_swarm_id=child.id,
            child_work_id=data.child_work_id,
            represented_by=child_actor.reference,
            requested_by=requester.reference,
            title=data.title,
            description=data.description,
            acceptance_criteria=criteria,
            required_artifacts=list(dict.fromkeys(data.required_artifacts)),
            result_kind=data.result_kind,
            status="proposed",
            created_at=self._timestamp(),
            path=str(path),
            budget_limits=budget_limits,
            artifact_promotions=artifact_promotions,
        )
        write_new(path, self._render_delegation(record))
        detail = (
            f"delegation={record.id} parent-work={parent_work.id} "
            f"child={child.id}/{record.child_work_id} actor={requester.reference}"
        )
        self._append_work_event(parent_work, "delegation.proposed", detail)
        self._append_swarm_event(root, parent.id, "delegation.proposed", detail)
        self._append_swarm_event(root, child.id, "delegation.received", detail)
        return record

    @_locked_mutation("project")
    def accept_delegation(self, data: DelegationActorInput) -> DelegationRecord:
        root = self.project_root()
        context = self._validate_accept_delegation(root, data, None)
        actor = context[4]
        if actor.authentication_required:
            raise PermissionError(
                f"Actor {actor.reference} requires a signed lifecycle action; "
                "prepare delegation.accept before applying it"
            )
        return self._apply_accept_delegation(root, data, None, context)

    @_locked_mutation("project")
    def prepare_accept_delegation(
        self, data: PrepareDelegationActionInput
    ) -> LifecycleActionRecord:
        assert_slug(data.id, "Lifecycle Action id")
        root = self.project_root()
        context = self._validate_accept_delegation(root, data, data.id)
        delegation, parent, parent_work, _, actor = context
        assert_actor_identity_available(actor)
        self._assert_current_actor_key(actor)
        return self._prepare_lifecycle_action(
            root,
            id_=data.id,
            action="delegation.accept",
            actor=actor,
            swarm=parent,
            work=parent_work,
            parameters={"delegation": delegation.id},
        )

    def _validate_accept_delegation(
        self,
        root: Path,
        data: DelegationActorInput,
        action_id: str | None,
    ) -> tuple[DelegationRecord, SwarmRecord, WorkRecord, SwarmRecord, ActorRecord]:
        delegation = self._load_delegation(root, data.delegation_id)
        if delegation.status != "proposed":
            raise ValueError(
                f"Delegation {delegation.id} cannot be accepted while {delegation.status}"
            )
        parent = self._load_swarm(root, delegation.parent_swarm_id)
        parent_work = self._load_work(parent, delegation.parent_work_id)
        self._assert_work_mutable(root, parent, parent_work)
        child = self._load_swarm(root, delegation.child_swarm_id)
        actor = self._require_actor_for_action(root, child, data.actor_id, "delegation.accept")
        self._require_actor_for_action(root, child, data.actor_id, "work.create")
        if (Path(child.path) / "work" / delegation.child_work_id).exists():
            raise FileExistsError(
                f"Child work already exists: {child.id}/{delegation.child_work_id}"
            )
        self._assert_status_change_id_available(
            Path(delegation.path).parent / "status-changes", action_id
        )
        return delegation, parent, parent_work, child, actor

    def _apply_accept_delegation(
        self,
        root: Path,
        data: DelegationActorInput,
        action_id: str | None,
        context: tuple[DelegationRecord, SwarmRecord, WorkRecord, SwarmRecord, ActorRecord],
    ) -> DelegationRecord:
        delegation, _, parent_work, child, actor = context
        work_data = CreateWorkInput(
            swarm_id=child.id,
            id=delegation.child_work_id,
            title=delegation.title,
            actor_id=data.actor_id,
            acceptance_criteria=list(delegation.acceptance_criteria.items()),
            required_artifacts=delegation.required_artifacts,
            description=delegation.description,
        )
        child_work = self._apply_create_work(
            work_data,
            self._validate_create_work(root, work_data),
            budget_limits=delegation.budget_limits,
        )
        child_work.delegation_id = delegation.id
        child_work.parent_work_ref = f"{delegation.parent_swarm_id}/{delegation.parent_work_id}"
        atomic_write(Path(child_work.path) / "WORK.md", self._render_work(child_work))
        accepted = DelegationRecord(
            **{
                **delegation.__dict__,
                "status": "accepted",
                "accepted_by": actor.reference,
                "accepted_at": self._timestamp(),
                "blocked_from": None,
                "status_reason": None,
                "status_by": None,
                "status_at": None,
            }
        )
        atomic_write(Path(delegation.path), self._render_delegation(accepted))
        change = self._record_status_change(
            subject_type="delegation",
            subject=delegation.id,
            action="delegation.accept",
            previous_status="proposed",
            target_status="accepted",
            actor=actor.reference,
            reason="Delegated work accepted by the child swarm",
            root=Path(delegation.path).parent / "status-changes",
            id_=action_id,
        )
        detail = (
            f"delegation={delegation.id} child-work={child.id}/{child_work.id} "
            f"actor={actor.reference} change={change.id}"
        )
        self._append_work_event(parent_work, "delegation.accepted", detail)
        self._append_work_event(child_work, "work.delegation-accepted", detail)
        self._append_swarm_event(root, child.id, "delegation.accepted", detail)
        return accepted

    @_locked_mutation("project")
    def collect_delegation(self, data: DelegationActorInput) -> DelegationRecord:
        root = self.project_root()
        context = self._validate_collect_delegation(root, data, None)
        actor = context[2]
        if actor.authentication_required:
            raise PermissionError(
                f"Actor {actor.reference} requires a signed lifecycle action; "
                "prepare delegation.collect before applying it"
            )
        return self._apply_collect_delegation(root, None, context)

    @_locked_mutation("project")
    def prepare_collect_delegation(
        self, data: PrepareDelegationActionInput
    ) -> LifecycleActionRecord:
        assert_slug(data.id, "Lifecycle Action id")
        root = self.project_root()
        context = self._validate_collect_delegation(root, data, data.id)
        delegation, parent, actor, _, _, parent_work, _ = context
        assert_actor_identity_available(actor)
        self._assert_current_actor_key(actor)
        return self._prepare_lifecycle_action(
            root,
            id_=data.id,
            action="delegation.collect",
            actor=actor,
            swarm=parent,
            work=parent_work,
            parameters={"delegation": delegation.id},
        )

    def _validate_collect_delegation(
        self,
        root: Path,
        data: DelegationActorInput,
        action_id: str | None,
    ) -> tuple[
        DelegationRecord,
        SwarmRecord,
        ActorRecord,
        SwarmRecord,
        WorkRecord,
        WorkRecord,
        str,
    ]:
        delegation = self._load_delegation(root, data.delegation_id)
        if delegation.status != "accepted":
            raise ValueError(
                f"Delegation {delegation.id} cannot be collected while {delegation.status}"
            )
        parent = self._load_swarm(root, delegation.parent_swarm_id)
        project = self._load_project_configuration(root)
        self._validate_delegation_graph(self._delegation_graph(root), project.max_delegation_depth)
        actor = self._require_actor_for_action(
            root,
            parent,
            data.actor_id,
            "delegation.collect",
            require_operational=False,
        )
        if actor.represented_swarm != delegation.child_swarm_id:
            raise PermissionError(
                f"Actor {actor.reference} does not represent delegated swarm "
                f"{delegation.child_swarm_id}"
            )
        child = self._load_swarm(root, delegation.child_swarm_id)
        child_work = self._load_work(child, delegation.child_work_id)
        child_contract = load_method_contract(root / ".agora" / "methods" / child.method)
        if child_work.state != child_contract.terminal_state:
            raise ValueError(
                f"Delegated work {child.id}/{child_work.id} is not complete; "
                f"state={child_work.state}"
            )
        missing_promotions = sorted(
            set(delegation.artifact_promotions) - set(child_work.artifact_kinds)
        )
        if missing_promotions:
            raise ValueError(
                "Delegated work is missing promoted child artifacts: "
                f"{', '.join(missing_promotions)}"
            )
        parent_work = self._load_work(parent, delegation.parent_work_id)
        self._assert_work_mutable(root, parent, parent_work)
        parent_contract = load_method_contract(root / ".agora" / "methods" / parent.method)
        if parent_work.state == parent_contract.terminal_state:
            raise ValueError(f"Cannot collect into completed work: {parent_work.id}")
        result_uri = f"agora://swarms/{child.id}/work/{child_work.id}"
        self._assert_status_change_id_available(
            Path(delegation.path).parent / "status-changes", action_id
        )
        return delegation, parent, actor, child, child_work, parent_work, result_uri

    def _apply_collect_delegation(
        self,
        root: Path,
        action_id: str | None,
        context: tuple[
            DelegationRecord,
            SwarmRecord,
            ActorRecord,
            SwarmRecord,
            WorkRecord,
            WorkRecord,
            str,
        ],
    ) -> DelegationRecord:
        delegation, parent, actor, child, child_work, parent_work, result_uri = context
        self._record_artifact(
            parent_work,
            delegation.result_kind,
            result_uri,
            actor.reference,
        )
        for source_kind, parent_kind in delegation.artifact_promotions.items():
            self._record_artifact(
                parent_work,
                parent_kind,
                f"{result_uri}/artifacts/{source_kind}",
                actor.reference,
            )
        self._record_evidence(
            parent_work,
            "delegated-work",
            "success",
            [result_uri],
            actor.reference,
        )
        collected = DelegationRecord(
            **{
                **delegation.__dict__,
                "status": "collected",
                "collected_by": actor.reference,
                "collected_at": self._timestamp(),
                "blocked_from": None,
                "status_reason": None,
                "status_by": None,
                "status_at": None,
            }
        )
        atomic_write(Path(delegation.path), self._render_delegation(collected))
        change = self._record_status_change(
            subject_type="delegation",
            subject=delegation.id,
            action="delegation.collect",
            previous_status="accepted",
            target_status="collected",
            actor=actor.reference,
            reason="Completed child result collected into parent work",
            root=Path(delegation.path).parent / "status-changes",
            id_=action_id,
        )
        parent_work = self._load_work(parent, delegation.parent_work_id)
        detail = (
            f"delegation={delegation.id} result={result_uri} actor={actor.reference} "
            f"change={change.id}"
        )
        self._append_work_event(parent_work, "delegation.collected", detail)
        self._append_work_event(child_work, "work.delegation-collected", detail)
        self._append_swarm_event(root, parent.id, "delegation.collected", detail)
        return collected

    @_locked_mutation("project")
    def block_delegation(self, data: ChangeDelegationStatusInput) -> StatusChangeRecord:
        delegation = self.show_delegation(data.delegation_id)
        return self._change_delegation_status(
            data,
            target_status="blocked",
            action="delegation.block",
            authority="parent",
            allowed_statuses={"proposed", "accepted"},
            blocked_from=delegation.status,
        )

    @_locked_mutation("project")
    def prepare_block_delegation(self, data: ChangeDelegationStatusInput) -> LifecycleActionRecord:
        return self._prepare_delegation_status_change(
            data,
            target_status="blocked",
            action="delegation.block",
            authority="parent",
            allowed_statuses={"proposed", "accepted"},
        )

    @_locked_mutation("project")
    def resume_delegation(self, data: ChangeDelegationStatusInput) -> StatusChangeRecord:
        delegation = self.show_delegation(data.delegation_id)
        if delegation.status != "blocked" or delegation.blocked_from not in {
            "proposed",
            "accepted",
        }:
            raise ValueError(f"Delegation {delegation.id} has no resumable blocked state")
        return self._change_delegation_status(
            data,
            target_status=delegation.blocked_from,
            action="delegation.resume",
            authority="parent",
            allowed_statuses={"blocked"},
            blocked_from=None,
        )

    @_locked_mutation("project")
    def prepare_resume_delegation(self, data: ChangeDelegationStatusInput) -> LifecycleActionRecord:
        delegation = self.show_delegation(data.delegation_id)
        if delegation.status != "blocked" or delegation.blocked_from not in {
            "proposed",
            "accepted",
        }:
            raise ValueError(f"Delegation {delegation.id} has no resumable blocked state")
        return self._prepare_delegation_status_change(
            data,
            target_status=delegation.blocked_from,
            action="delegation.resume",
            authority="parent",
            allowed_statuses={"blocked"},
        )

    @_locked_mutation("project")
    def reject_delegation(self, data: ChangeDelegationStatusInput) -> StatusChangeRecord:
        return self._change_delegation_status(
            data,
            target_status="rejected",
            action="delegation.reject",
            authority="child",
            allowed_statuses={"proposed"},
        )

    @_locked_mutation("project")
    def prepare_reject_delegation(self, data: ChangeDelegationStatusInput) -> LifecycleActionRecord:
        return self._prepare_delegation_status_change(
            data,
            target_status="rejected",
            action="delegation.reject",
            authority="child",
            allowed_statuses={"proposed"},
        )

    @_locked_mutation("project")
    def cancel_delegation(self, data: ChangeDelegationStatusInput) -> StatusChangeRecord:
        return self._change_delegation_status(
            data,
            target_status="cancelled",
            action="delegation.cancel",
            authority="parent",
            allowed_statuses={"proposed", "accepted", "blocked"},
        )

    @_locked_mutation("project")
    def prepare_cancel_delegation(self, data: ChangeDelegationStatusInput) -> LifecycleActionRecord:
        return self._prepare_delegation_status_change(
            data,
            target_status="cancelled",
            action="delegation.cancel",
            authority="parent",
            allowed_statuses={"proposed", "accepted", "blocked"},
        )

    def list_delegation_status_changes(self, delegation_id: str) -> list[StatusChangeRecord]:
        delegation = self.show_delegation(delegation_id)
        records = [
            self._load_status_change(path.parent)
            for path in sorted(
                (Path(delegation.path).parent / "status-changes").glob("*/STATUS.md")
            )
        ]
        return sorted(records, key=lambda item: (item.sequence, item.created_at, item.id))

    def _change_delegation_status(
        self,
        data: ChangeDelegationStatusInput,
        *,
        target_status: str,
        action: str,
        authority: str,
        allowed_statuses: set[str],
        blocked_from: str | None = None,
    ) -> StatusChangeRecord:
        root = self.project_root()
        context = self._validate_delegation_status_change(
            root,
            data,
            target_status=target_status,
            action=action,
            authority=authority,
            allowed_statuses=allowed_statuses,
        )
        actor = context[2]
        if actor.authentication_required:
            raise PermissionError(
                f"Actor {actor.reference} requires a signed lifecycle action; "
                f"prepare {action} before applying it"
            )
        return self._apply_delegation_status_change(
            root,
            data,
            target_status=target_status,
            action=action,
            blocked_from=blocked_from,
            context=context,
        )

    def _prepare_delegation_status_change(
        self,
        data: ChangeDelegationStatusInput,
        *,
        target_status: str,
        action: str,
        authority: str,
        allowed_statuses: set[str],
    ) -> LifecycleActionRecord:
        if data.id is None:
            raise ValueError(f"Prepared {action} requires an explicit id")
        root = self.project_root()
        delegation, _, actor, parent, parent_work, _ = self._validate_delegation_status_change(
            root,
            data,
            target_status=target_status,
            action=action,
            authority=authority,
            allowed_statuses=allowed_statuses,
        )
        assert_actor_identity_available(actor)
        self._assert_current_actor_key(actor)
        return self._prepare_lifecycle_action(
            root,
            id_=data.id,
            action=action,
            actor=actor,
            swarm=parent,
            work=parent_work,
            parameters={
                "delegation": delegation.id,
                "reason": data.reason.strip(),
            },
        )

    def _validate_delegation_status_change(
        self,
        root: Path,
        data: ChangeDelegationStatusInput,
        *,
        target_status: str,
        action: str,
        authority: str,
        allowed_statuses: set[str],
    ) -> tuple[
        DelegationRecord,
        SwarmRecord,
        ActorRecord,
        SwarmRecord,
        WorkRecord,
        str,
    ]:
        if not data.reason.strip():
            raise ValueError("Delegation status change reason cannot be empty")
        delegation = self._load_delegation(root, data.delegation_id)
        if delegation.status not in allowed_statuses:
            raise ValueError(
                f"Delegation {delegation.id} cannot perform {action} while {delegation.status}"
            )
        swarm_id = (
            delegation.parent_swarm_id if authority == "parent" else delegation.child_swarm_id
        )
        swarm = self._load_swarm(root, swarm_id)
        actor = self._require_actor_for_action(root, swarm, data.actor_id, action)
        parent = self._load_swarm(root, delegation.parent_swarm_id)
        parent_work = self._load_work(parent, delegation.parent_work_id)
        if action in {"delegation.block", "delegation.resume"}:
            self._assert_work_mutable(root, parent, parent_work)
        previous = delegation.status
        change_root = Path(delegation.path).parent / "status-changes"
        self._assert_status_change_id_available(change_root, data.id)
        return delegation, swarm, actor, parent, parent_work, previous

    def _apply_delegation_status_change(
        self,
        root: Path,
        data: ChangeDelegationStatusInput,
        *,
        target_status: str,
        action: str,
        blocked_from: str | None,
        context: tuple[
            DelegationRecord,
            SwarmRecord,
            ActorRecord,
            SwarmRecord,
            WorkRecord,
            str,
        ],
    ) -> StatusChangeRecord:
        delegation, _, actor, parent, parent_work, previous = context
        change_root = Path(delegation.path).parent / "status-changes"
        changed = DelegationRecord(
            **{
                **delegation.__dict__,
                "status": target_status,
                "blocked_from": blocked_from,
                "status_reason": data.reason.strip(),
                "status_by": actor.reference,
                "status_at": self._timestamp(),
            }
        )
        atomic_write(Path(delegation.path), self._render_delegation(changed))
        record = self._record_status_change(
            subject_type="delegation",
            subject=delegation.id,
            action=action,
            previous_status=previous,
            target_status=target_status,
            actor=actor.reference,
            reason=data.reason.strip(),
            root=change_root,
            id_=data.id,
        )
        detail = (
            f"delegation={delegation.id} from={previous} to={target_status} "
            f"actor={actor.reference} change={record.id}"
        )
        self._append_work_event(parent_work, action, detail)
        self._append_swarm_event(root, parent.id, action, detail)
        self._append_swarm_event(root, delegation.child_swarm_id, action, detail)
        return record

    def show_delegation(self, delegation_id: str) -> DelegationRecord:
        return self._load_delegation(self.project_root(), delegation_id)

    def list_delegations(self, status: str | None = None) -> list[DelegationRecord]:
        root = self.project_root()
        records = [
            self._load_delegation(root, path.parent.name)
            for path in sorted((root / ".agora" / "delegations").glob("*/DELEGATION.md"))
        ]
        return [record for record in records if status is None or record.status == status]

    def start_session(self, data: StartSessionInput) -> SessionRecord:
        root = self.project_root()
        with self._mutation_lock((root,), "start_session"):
            context = self._validate_session_preparation(root, data)
            actor = context[2]
            if actor.authentication_required:
                raise PermissionError(
                    f"Actor {actor.reference} requires a signed lifecycle action; "
                    "prepare session.prepare before materializing its context"
                )
            record = self._apply_session_preparation(root, data, context, None)
            if not data.launch:
                return record
            running = self._mark_session_running(record)
        return self._run_session_process(root, running, actor, context[1], context[4])

    @_locked_mutation("project")
    def prepare_session(self, data: PrepareSessionInput) -> LifecycleActionRecord:
        assert_slug(data.action_id, "Lifecycle Action id")
        if data.session.id is None:
            raise ValueError("Prepared session.prepare requires an explicit session id")
        if data.session.launch:
            raise ValueError("Prepared session.prepare cannot launch the session")
        if data.session.force:
            raise ValueError("Prepared session.prepare cannot replace an existing session")
        root = self.project_root()
        context = self._validate_session_preparation(root, data.session)
        _, swarm, actor, _, work, _, _, _, _, _, session_id, _, _ = context
        assert_actor_identity_available(actor)
        self._assert_current_actor_key(actor)
        return self._prepare_lifecycle_action(
            root,
            id_=data.action_id,
            action="session.prepare",
            actor=actor,
            swarm=swarm,
            work=work,
            parameters={
                "session": session_id,
                "runner": data.session.runner or "",
                "timeout-seconds": str(data.session.timeout_seconds),
                "max-output-bytes": str(data.session.max_output_bytes),
            },
        )

    def _validate_session_preparation(
        self, root: Path, data: StartSessionInput
    ) -> tuple[
        ProjectConfiguration,
        SwarmRecord,
        ActorRecord,
        list[str],
        WorkRecord | None,
        Integration,
        str,
        str,
        list[str],
        bool,
        str,
        Path,
        str,
    ]:
        project = self._load_project_configuration(root)
        swarm = self._load_swarm(root, data.swarm_id)
        if swarm.status not in {"ready", "running"}:
            raise ValueError(f"Swarm {swarm.id} must be ready before a session can start")
        actor = self._find_actor(root, data.actor_id)
        assert_actor_identity_available(actor)
        self._assert_current_actor_key(actor)
        self._assert_represented_swarm_operational(root, actor)
        roles = self._actor_roles(swarm, actor.reference)
        if not roles:
            raise ValueError(f"Actor {actor.reference} is not assigned to swarm {swarm.id}")
        work = self._load_work(swarm, data.work_id) if data.work_id is not None else None
        if work is not None:
            self._assert_work_mutable(root, swarm, work)

        integration = actor.integration or project.integration
        provider = actor.provider or project.provider
        model = actor.model or project.model
        self._assert_session_execution_boundaries(
            data.timeout_seconds,
            data.max_output_bytes,
        )
        command = self._runtime_command(integration, data.runner, model)
        runtime_available = bool(command and shutil.which(command[0]))
        if data.launch and not command:
            raise ValueError("A generic integration requires --runner when --launch is used")
        if data.launch and not runtime_available:
            raise FileNotFoundError(f"Runtime executable not found: {command[0]}")

        session_id = data.id or self._now().astimezone(UTC).strftime("session-%Y%m%dt%H%M%sz")
        assert_slug(session_id, "Session id")
        session_path = root / ".agora" / "sessions" / session_id
        if session_path.exists() and not data.force:
            raise FileExistsError(
                f"Session already exists: {session_id}. Pass --force to replace it."
            )
        context_contents = self._render_session_context(
            root,
            project,
            actor,
            swarm,
            roles,
            work,
            integration,
            provider,
            model,
        )
        return (
            project,
            swarm,
            actor,
            roles,
            work,
            integration,
            provider,
            model,
            command,
            runtime_available,
            session_id,
            session_path,
            context_contents,
        )

    def _apply_session_preparation(
        self,
        root: Path,
        data: StartSessionInput,
        context: tuple[
            ProjectConfiguration,
            SwarmRecord,
            ActorRecord,
            list[str],
            WorkRecord | None,
            Integration,
            str,
            str,
            list[str],
            bool,
            str,
            Path,
            str,
        ],
        preparation_action_id: str | None,
    ) -> SessionRecord:
        (
            _,
            swarm,
            actor,
            roles,
            work,
            integration,
            provider,
            model,
            command,
            runtime_available,
            session_id,
            session_path,
            context_contents,
        ) = context
        context_path = session_path / "CONTEXT.md"
        record = SessionRecord(
            id=session_id,
            actor=actor.reference,
            swarm_id=swarm.id,
            work_id=work.id if work else None,
            roles=roles,
            integration=integration,
            provider=provider,
            model=model,
            status="prepared",
            path=str(session_path),
            context_path=str(context_path),
            launch_command=command,
            runtime_available=runtime_available,
            created_at=self._timestamp(),
            timeout_seconds=data.timeout_seconds,
            max_output_bytes=data.max_output_bytes,
            context_sha256=hashlib.sha256(context_contents.encode()).hexdigest(),
            preparation_action_id=preparation_action_id,
        )
        write_new(context_path, context_contents, data.force)
        write_new(session_path / "SESSION.md", self._render_session(record), data.force)
        append_entry(
            root / ".agora" / "events.md",
            (
                f"- {self._timestamp()} | session.prepared | session={session_id} "
                f"actor={actor.reference} swarm={swarm.id}"
            ),
        )
        return record

    def prepare_session_authorization(
        self, data: PrepareSessionAuthorizationInput
    ) -> SessionAuthorizationRecord:
        assert_slug(data.session_id, "Session id")
        root = self.project_root()
        record = self._load_session(root / ".agora" / "sessions" / data.session_id)
        if record.status != "prepared":
            raise ValueError(f"Session must be prepared for authorization: {record.id}")
        actor = self._find_actor(root, record.actor)
        assert_actor_identity_available(actor)
        self._assert_current_actor_key(actor)
        if actor.authentication_fingerprint is None:
            raise ValueError(f"Actor {actor.reference} has no authentication key")
        self._assert_session_context(record)
        payload = session_authorization_payload(record)
        output = Path(data.output).expanduser().resolve()
        write_new(output, payload.decode("ascii"), data.force)
        return SessionAuthorizationRecord(
            session_id=record.id,
            actor=actor.reference,
            algorithm="ed25519",
            fingerprint=actor.authentication_fingerprint,
            payload_sha256=hashlib.sha256(payload).hexdigest(),
            path=str(output),
        )

    def launch_session(self, data: LaunchSessionInput) -> SessionRecord:
        assert_slug(data.session_id, "Session id")
        root = self.project_root()
        with self._mutation_lock((root,), "launch_session"):
            record = self._load_session(root / ".agora" / "sessions" / data.session_id)
            if record.status != "prepared":
                raise ValueError(f"Session must be prepared before launch: {record.id}")
            actor = self._find_actor(root, record.actor)
            assert_actor_identity_available(actor)
            self._assert_current_actor_key(actor)
            swarm = self._load_swarm(root, record.swarm_id)
            if swarm.status not in {"ready", "running"}:
                raise ValueError(f"Swarm {swarm.id} must be ready before a session can launch")
            self._assert_represented_swarm_operational(root, actor)
            roles = self._actor_roles(swarm, actor.reference)
            if not roles:
                raise ValueError(f"Actor {actor.reference} is not assigned to swarm {swarm.id}")
            if roles != record.roles:
                raise ValueError(f"Prepared session roles no longer match assignments: {record.id}")
            work = self._load_work(swarm, record.work_id) if record.work_id is not None else None
            if work is not None:
                self._assert_work_mutable(root, swarm, work)
            project = self._load_project_configuration(root)
            expected_runtime = (
                actor.integration or project.integration,
                actor.provider or project.provider,
                actor.model or project.model,
            )
            if (record.integration, record.provider, record.model) != expected_runtime:
                raise ValueError(
                    f"Prepared session runtime no longer matches its actor: {record.id}"
                )
            self._assert_session_context(record)
            if not record.launch_command:
                raise ValueError(f"Session has no launch command: {record.id}")
            if shutil.which(record.launch_command[0]) is None:
                raise FileNotFoundError(f"Runtime executable not found: {record.launch_command[0]}")

            fingerprint: str | None = None
            authentication_public_key: str | None = None
            authorization_sha256: str | None = None
            authorization_signature: str | None = None
            if actor.authentication_required and data.signature is None:
                raise PermissionError(
                    f"Actor {actor.reference} requires a signed session authorization"
                )
            if data.signature is not None:
                (
                    fingerprint,
                    authorization_sha256,
                    authentication_public_key,
                    authorization_signature,
                ) = verify_session_authorization(
                    actor, record, Path(data.signature).expanduser().resolve()
                )
            authorized = SessionRecord(
                **{
                    **record.__dict__,
                    "runtime_available": True,
                    "authentication_verified": fingerprint is not None,
                    "authentication_fingerprint": fingerprint,
                    "authentication_public_key": authentication_public_key,
                    "authorization_sha256": authorization_sha256,
                    "authorization_signature": authorization_signature,
                }
            )
            running = self._mark_session_running(authorized)
        return self._run_session_process(root, running, actor, swarm, work)

    def _mark_session_running(self, record: SessionRecord) -> SessionRecord:
        running = SessionRecord(**{**record.__dict__, "status": "running", "exit_code": None})
        atomic_write(Path(record.path) / "SESSION.md", self._render_session(running))
        return running

    def _run_session_process(
        self,
        root: Path,
        running: SessionRecord,
        actor: ActorRecord,
        swarm: SwarmRecord,
        work: WorkRecord | None,
    ) -> SessionRecord:
        session_path = Path(running.path)
        environment = {
            **os.environ,
            "AGORA_PROJECT": str(root),
            "AGORA_SESSION": str(session_path / "SESSION.md"),
            "AGORA_CONTEXT": running.context_path,
            "AGORA_ACTOR": actor.reference,
            "AGORA_SWARM": swarm.id,
        }
        if work is not None:
            environment["AGORA_WORK"] = work.id
        launch_error: BaseException | None = None
        stdout = ""
        stderr = ""
        try:
            if self._launcher is None:
                result = _run_tool_process(
                    running.launch_command,
                    root,
                    environment,
                    timeout_seconds=running.timeout_seconds,
                    max_output_bytes=running.max_output_bytes,
                    boundary_subject="session",
                )
                exit_code = result.returncode
                stdout = result.stdout
                stderr = result.stderr
            else:
                exit_code = self._launcher(running.launch_command, root, environment)
        except BaseException as error:
            launch_error = error
            exit_code = None
            stderr = f"{type(error).__name__}: {error}"
        status = "completed" if exit_code == 0 else "failed"
        termination_reason = {124: "timeout", 125: "output-limit"}.get(exit_code)
        if launch_error is not None:
            termination_reason = "launcher-error"
        elif exit_code not in {None, 0, 124, 125}:
            termination_reason = "nonzero-exit"
        finished = SessionRecord(
            **{
                **running.__dict__,
                "status": status,
                "exit_code": exit_code,
                "output_bytes": len(stdout.encode("utf-8")) + len(stderr.encode("utf-8")),
                "termination_reason": termination_reason,
            }
        )
        with self._mutation_lock((root,), "finish_session"):
            current = self._load_session(session_path)
            if current.status != "running":
                raise ValueError(f"Running session state changed during execution: {running.id}")
            atomic_write(session_path / "SESSION.md", self._render_session(finished))
            atomic_write(
                session_path / "RESULT.md",
                self._render_session_result(finished, stdout, stderr),
            )
            append_entry(
                root / ".agora" / "events.md",
                (
                    f"- {self._timestamp()} | session.{status} | session={running.id} "
                    f"exit-code={exit_code if exit_code is not None else 'unavailable'}"
                ),
            )
        if launch_error is not None:
            raise launch_error
        if exit_code != 0:
            raise RuntimeError(
                f"Session runner exited with code {exit_code}: {' '.join(running.launch_command)}"
            )
        return finished

    @staticmethod
    def _assert_session_context(record: SessionRecord) -> None:
        context_path = Path(record.context_path)
        expected_path = Path(record.path) / "CONTEXT.md"
        if context_path != expected_path:
            raise ValueError(f"Session context path is not canonical: {record.id}")
        if not context_path.is_file():
            raise FileNotFoundError(f"Session context is missing: {context_path}")
        if record.context_sha256 is None:
            raise ValueError(f"Session has no context digest: {record.id}")
        digest = hashlib.sha256(context_path.read_bytes()).hexdigest()
        if digest != record.context_sha256:
            raise ValueError(f"Session context digest mismatch: {record.id}")

    def list_sessions(self, status: str | None = None) -> list[SessionRecord]:
        root = self.project_root()
        records = [
            self._load_session(path.parent)
            for path in sorted((root / ".agora" / "sessions").glob("*/SESSION.md"))
        ]
        return [record for record in records if status is None or record.status == status]

    @_locked_mutation("project")
    def invoke_tool(self, data: InvokeToolInput) -> ToolRunRecord:
        assert_slug(data.tool_id, "Tool id")
        assert_slug(data.operation_id, "Tool operation id")
        root = self.project_root()
        swarm = self._load_swarm(root, data.swarm_id)
        if swarm.status not in {"ready", "running"}:
            raise ValueError(f"Swarm {swarm.id} must be ready before a tool can be invoked")
        actor = self._find_actor(root, data.actor_id)
        assert_actor_identity_available(actor)
        self._assert_current_actor_key(actor)
        if data.launch and actor.authentication_required:
            raise ValueError(
                f"Actor {actor.reference} requires signed launch: prepare the run without "
                "--launch, export its authorization, then use tool launch"
            )
        self._assert_represented_swarm_operational(root, actor)
        roles = self._actor_roles(swarm, actor.reference)
        if not roles:
            raise ValueError(f"Actor {actor.reference} is not assigned to swarm {swarm.id}")

        contract = load_tool_contract(root / ".agora" / "tools" / data.tool_id)
        operation = contract.operations.get(data.operation_id)
        if operation is None:
            raise FileNotFoundError(f"Tool operation not found: {contract.id}/{data.operation_id}")
        allowed_capabilities = self._actor_tool_capabilities(root, swarm, roles)
        if operation.capability not in allowed_capabilities:
            raise PermissionError(
                f"Actor {actor.reference} is not allowed tool capability {operation.capability}"
            )

        expected_inputs = set(operation.inputs)
        provided_inputs = set(data.inputs)
        missing_inputs = sorted(expected_inputs - provided_inputs)
        unknown_inputs = sorted(provided_inputs - expected_inputs)
        empty_inputs = sorted(
            key for key, value in data.inputs.items() if not isinstance(value, str) or not value
        )
        if missing_inputs or unknown_inputs or empty_inputs:
            raise ValueError(
                f"Invalid inputs for {contract.id}/{operation.id}: "
                f"missing=[{', '.join(missing_inputs)}], "
                f"unknown=[{', '.join(unknown_inputs)}], "
                f"empty=[{', '.join(empty_inputs)}]"
            )
        validate_operation_inputs(operation, data.inputs)
        work = self._load_work(swarm, data.work_id) if data.work_id is not None else None
        if work is not None:
            self._assert_work_mutable(root, swarm, work)
        self._assert_environment_permission(
            root,
            swarm,
            roles,
            operation.capability,
            data.environment_id,
            operation.environment_required,
            work,
        )
        if operation.approval_role is not None:
            if work is None:
                raise ValueError(
                    f"Tool operation {contract.id}/{operation.id} requires work approval "
                    f"from {operation.approval_role}"
                )
            if operation.approval_role not in work.approval_roles:
                raise PermissionError(
                    f"Tool operation {contract.id}/{operation.id} requires approval from "
                    f"{operation.approval_role}"
                )

        arguments = [
            self._substitute_tool_inputs(argument, data.inputs) for argument in operation.arguments
        ]
        command = [contract.executable, *arguments]
        executable_path = shutil.which(contract.executable)
        runtime_available = executable_path is not None
        if data.launch and not runtime_available:
            raise FileNotFoundError(f"Tool executable not found: {contract.executable}")
        if data.launch and contract.minimum_runtime_version is not None:
            probe = self._runtime_probe(contract, executable_path)
            if probe.compatible is not True:
                raise RuntimeError(
                    f"Tool runtime compatibility check failed for {contract.id}: {probe.detail}"
                )

        run_id = data.id or self._now().astimezone(UTC).strftime("tool-%Y%m%dt%H%M%sz")
        assert_slug(run_id, "Tool run id")
        run_path = root / ".agora" / "tool-runs" / run_id
        if run_path.exists() and not data.force:
            raise FileExistsError(f"Tool run already exists: {run_id}. Pass --force to replace it.")
        record = ToolRunRecord(
            id=run_id,
            tool_id=contract.id,
            operation_id=operation.id,
            actor=actor.reference,
            swarm_id=swarm.id,
            work_id=work.id if work else None,
            environment_id=data.environment_id,
            capability=operation.capability,
            risk=operation.risk,
            inputs=data.inputs,
            command=command,
            runtime_available=runtime_available,
            status="prepared",
            path=str(run_path),
            created_at=self._timestamp(),
            result_kind=operation.result_kind,
            timeout_seconds=contract.timeout_seconds,
            max_output_bytes=contract.max_output_bytes,
        )
        write_new(run_path / "RUN.md", self._render_tool_run(record, contract), data.force)
        self._append_tool_event(root, record, "prepared")
        if work is not None:
            self._append_work_event(
                work,
                "tool.prepared",
                f"run={run_id} tool={contract.id} operation={operation.id} actor={actor.reference}",
            )
        if not data.launch:
            return record

        return self._execute_tool_run(root, record, contract, actor, swarm, work, data.force)

    def prepare_tool_authorization(
        self, data: PrepareToolAuthorizationInput
    ) -> ToolAuthorizationRecord:
        assert_slug(data.run_id, "Tool run id")
        root = self.project_root()
        record = self._load_tool_run(root / ".agora" / "tool-runs" / data.run_id)
        if record.status != "prepared":
            raise ValueError(f"Tool run must be prepared for authorization: {record.id}")
        actor = self._find_actor(root, record.actor)
        assert_actor_identity_available(actor)
        self._assert_current_actor_key(actor)
        validate_actor_identity(actor)
        if actor.authentication_fingerprint is None:
            raise ValueError(f"Actor {actor.reference} has no authentication key")
        payload = tool_authorization_payload(record)
        output = Path(data.output).expanduser().resolve()
        write_new(output, payload.decode("ascii"), data.force)
        return ToolAuthorizationRecord(
            run_id=record.id,
            actor=actor.reference,
            algorithm="ed25519",
            fingerprint=actor.authentication_fingerprint,
            payload_sha256=hashlib.sha256(payload).hexdigest(),
            path=str(output),
        )

    @_locked_mutation("project")
    def launch_tool_run(self, data: LaunchToolRunInput) -> ToolRunRecord:
        assert_slug(data.run_id, "Tool run id")
        root = self.project_root()
        record = self._load_tool_run(root / ".agora" / "tool-runs" / data.run_id)
        if record.status != "prepared":
            raise ValueError(f"Tool run must be prepared before launch: {record.id}")
        swarm = self._load_swarm(root, record.swarm_id)
        if swarm.status not in {"ready", "running"}:
            raise ValueError(f"Swarm {swarm.id} must be ready before a tool can be launched")
        actor = self._find_actor(root, record.actor)
        assert_actor_identity_available(actor)
        self._assert_current_actor_key(actor)
        self._assert_represented_swarm_operational(root, actor)
        roles = self._actor_roles(swarm, actor.reference)
        if not roles:
            raise ValueError(f"Actor {actor.reference} is not assigned to swarm {swarm.id}")

        contract = load_tool_contract(root / ".agora" / "tools" / record.tool_id)
        operation = contract.operations.get(record.operation_id)
        if operation is None:
            raise FileNotFoundError(
                f"Tool operation not found: {record.tool_id}/{record.operation_id}"
            )
        if operation.capability not in self._actor_tool_capabilities(root, swarm, roles):
            raise PermissionError(
                f"Actor {actor.reference} is not allowed tool capability {operation.capability}"
            )
        expected_inputs = set(operation.inputs)
        provided_inputs = set(record.inputs)
        missing_inputs = sorted(expected_inputs - provided_inputs)
        unknown_inputs = sorted(provided_inputs - expected_inputs)
        empty_inputs = sorted(key for key, value in record.inputs.items() if not value)
        if missing_inputs or unknown_inputs or empty_inputs:
            raise ValueError(
                f"Prepared Tool Run has invalid inputs: "
                f"missing=[{', '.join(missing_inputs)}], "
                f"unknown=[{', '.join(unknown_inputs)}], "
                f"empty=[{', '.join(empty_inputs)}]"
            )
        validate_operation_inputs(operation, record.inputs)
        command = [
            contract.executable,
            *(
                self._substitute_tool_inputs(argument, record.inputs)
                for argument in operation.arguments
            ),
        ]
        if record.command != command:
            raise ValueError(f"Prepared tool command no longer matches its contract: {record.id}")
        if (
            record.capability != operation.capability
            or record.risk != operation.risk
            or record.result_kind != operation.result_kind
            or record.timeout_seconds != contract.timeout_seconds
            or record.max_output_bytes != contract.max_output_bytes
        ):
            raise ValueError(f"Prepared tool policy no longer matches its contract: {record.id}")

        work = self._load_work(swarm, record.work_id) if record.work_id is not None else None
        if work is not None:
            self._assert_work_mutable(root, swarm, work)
        self._assert_environment_permission(
            root,
            swarm,
            roles,
            operation.capability,
            record.environment_id,
            operation.environment_required,
            work,
        )
        if operation.approval_role is not None:
            if work is None or operation.approval_role not in work.approval_roles:
                raise PermissionError(
                    f"Tool operation {contract.id}/{operation.id} requires approval from "
                    f"{operation.approval_role}"
                )

        executable_path = shutil.which(contract.executable)
        if executable_path is None:
            raise FileNotFoundError(f"Tool executable not found: {contract.executable}")
        if contract.minimum_runtime_version is not None:
            probe = self._runtime_probe(contract, executable_path)
            if probe.compatible is not True:
                raise RuntimeError(
                    f"Tool runtime compatibility check failed for {contract.id}: {probe.detail}"
                )

        fingerprint: str | None = None
        authentication_public_key: str | None = None
        authorization_sha256: str | None = None
        authorization_signature: str | None = None
        if actor.authentication_required and data.signature is None:
            raise PermissionError(f"Actor {actor.reference} requires a signed tool authorization")
        if data.signature is not None:
            (
                fingerprint,
                authorization_sha256,
                authentication_public_key,
                authorization_signature,
            ) = verify_tool_authorization(
                actor, record, Path(data.signature).expanduser().resolve()
            )
        authorized = ToolRunRecord(
            **{
                **record.__dict__,
                "runtime_available": True,
                "authentication_verified": fingerprint is not None,
                "authentication_fingerprint": fingerprint,
                "authentication_public_key": authentication_public_key,
                "authorization_sha256": authorization_sha256,
                "authorization_signature": authorization_signature,
            }
        )
        return self._execute_tool_run(root, authorized, contract, actor, swarm, work)

    def _execute_tool_run(
        self,
        root: Path,
        record: ToolRunRecord,
        contract: ToolContract,
        actor: ActorRecord,
        swarm: SwarmRecord,
        work: WorkRecord | None,
        force: bool = False,
    ) -> ToolRunRecord:
        run_path = Path(record.path)
        running = ToolRunRecord(**{**record.__dict__, "status": "running"})
        atomic_write(run_path / "RUN.md", self._render_tool_run(running, contract))
        environment = {
            **os.environ,
            "AGORA_PROJECT": str(root),
            "AGORA_TOOL_RUN": str(run_path / "RUN.md"),
            "AGORA_ACTOR": actor.reference,
            "AGORA_SWARM": swarm.id,
        }
        if work is not None:
            environment["AGORA_WORK"] = work.id
        if record.environment_id is not None:
            environment["AGORA_ENVIRONMENT"] = record.environment_id
        if self._tool_runner is None:
            result = _run_tool_process(
                record.command,
                root,
                environment,
                timeout_seconds=record.timeout_seconds,
                max_output_bytes=record.max_output_bytes,
            )
        else:
            result = _bound_tool_output(
                self._tool_runner(record.command, root, environment),
                record.max_output_bytes,
            )
        status = "completed" if result.returncode == 0 else "failed"
        finished = ToolRunRecord(
            **{**record.__dict__, "status": status, "exit_code": result.returncode}
        )
        atomic_write(run_path / "RUN.md", self._render_tool_run(finished, contract))
        write_new(
            run_path / "RESULT.md",
            self._render_tool_result(finished, result.stdout, result.stderr),
            force,
        )
        self._append_tool_event(root, finished, status)
        if work is not None:
            self._append_work_event(
                work,
                f"tool.{status}",
                f"run={record.id} exit-code={result.returncode}",
            )
        if result.returncode != 0:
            raise RuntimeError(
                f"Tool operation exited with code {result.returncode}: {' '.join(record.command)}"
            )
        return finished

    def list_tool_runs(self, status: str | None = None) -> list[ToolRunRecord]:
        root = self.project_root()
        records = [
            self._load_tool_run(path.parent)
            for path in sorted((root / ".agora" / "tool-runs").glob("*/RUN.md"))
        ]
        return [record for record in records if status is None or record.status == status]

    def status(self) -> WorkspaceStatus:
        root = self.project_root()
        project = self._load_project_configuration(root)
        actors = self.list_actors()
        methods = self.list_methods()
        tools = self.list_tools()
        environments = self.list_environments()
        swarms = self.list_swarms()
        work = self.list_work()
        delegations = self.list_delegations()
        sessions = self.list_sessions()
        tool_runs = self.list_tool_runs()
        usage = [record for item in work for record in self.list_usage(item.swarm_id, item.id)]
        terminal_states = {
            swarm.id: load_method_contract(
                root / ".agora" / "methods" / swarm.method
            ).terminal_state
            for swarm in swarms
        }
        attention = {
            "forming-swarms": [item.id for item in swarms if item.status == "forming"],
            "active-work": [
                f"{item.swarm_id}/{item.id}"
                for item in work
                if item.operational_status == "active"
                and item.state != terminal_states[item.swarm_id]
            ],
            "blocked-work": [
                f"{item.swarm_id}/{item.id}"
                for item in work
                if item.operational_status == "blocked"
            ],
            "open-delegations": [
                item.id
                for item in delegations
                if item.status in {"proposed", "accepted", "blocked"}
            ],
            "unfinished-sessions": [
                item.id for item in sessions if item.status in {"prepared", "running"}
            ],
            "failed-sessions": [item.id for item in sessions if item.status == "failed"],
            "failed-tool-runs": [item.id for item in tool_runs if item.status == "failed"],
        }
        return WorkspaceStatus(
            project=project.project,
            integration=project.integration,
            default_method=project.default_method,
            branch=current_branch(root) if is_git_repository(root) else "filesystem-only",
            counts={
                "actors": len(actors),
                "methods": len(methods),
                "tools": len(tools),
                "environments": len(environments),
                "swarms": len(swarms),
                "work": len(work),
                "delegations": len(delegations),
                "sessions": len(sessions),
                "usage": len(usage),
                "tool-runs": len(tool_runs),
            },
            swarm_statuses=_count_values(item.status for item in swarms),
            work_states=_count_values(item.state for item in work),
            work_operational_statuses=_count_values(item.operational_status for item in work),
            delegation_statuses=_count_values(item.status for item in delegations),
            session_statuses=_count_values(item.status for item in sessions),
            tool_run_statuses=_count_values(item.status for item in tool_runs),
            attention=attention,
        )

    def next_actions(
        self,
        *,
        actor_id: str | None = None,
        swarm_id: str | None = None,
        human_only: bool = False,
        limit: int = 20,
    ) -> list[OperationalTask]:
        if limit < 1:
            raise ValueError("Operational action limit must be a positive integer")
        root = self.project_root()
        selected_actor = self._find_actor(root, actor_id) if actor_id is not None else None
        selected_reference = selected_actor.reference if selected_actor is not None else None
        swarms = [self.show_swarm(swarm_id)] if swarm_id is not None else self.list_swarms()
        sessions = self.list_sessions()
        tasks: list[OperationalTask] = []

        for swarm in swarms:
            if swarm.status == "forming":
                if selected_reference is None:
                    for role in swarm.required_roles:
                        if role not in swarm.assignments:
                            tasks.append(
                                OperationalTask(
                                    id=f"{swarm.id}:assign:{role}",
                                    kind="assign-role",
                                    actor=None,
                                    actor_kind=None,
                                    swarm_id=swarm.id,
                                    work_id=None,
                                    role=role,
                                    state=None,
                                    target_states=[],
                                    blockers=[],
                                    session_id=None,
                                    reason=f"Assign a compatible actor to the vacant {role} role",
                                )
                            )
                continue
            if swarm.status not in {"ready", "running", "blocked"}:
                continue

            contract = load_method_contract(root / ".agora" / "methods" / swarm.method)
            for work in self.list_work(swarm.id):
                if work.operational_status == "cancelled" or work.state == contract.terminal_state:
                    continue
                if work.operational_status == "blocked":
                    for role, reference in sorted(swarm.assignments.items()):
                        if not self._role_allows_action(root, swarm.method, role, "work.resume"):
                            continue
                        actor = self._find_actor(root, reference)
                        if selected_reference is not None and actor.reference != selected_reference:
                            continue
                        if human_only and actor.kind != "human":
                            continue
                        tasks.append(
                            OperationalTask(
                                id=f"{swarm.id}/{work.id}:resume:{role}",
                                kind="resume-work",
                                actor=actor.reference,
                                actor_kind=actor.kind,
                                swarm_id=swarm.id,
                                work_id=work.id,
                                role=role,
                                state=work.state,
                                target_states=[],
                                blockers=[work.status_reason] if work.status_reason else [],
                                session_id=None,
                                reason="Review the blocking condition and resume governed work",
                            )
                        )
                    continue

                transitions_by_role: dict[str, list[TransitionRule]] = {}
                for transition in contract.transitions:
                    if transition.source != work.state:
                        continue
                    for role in transition.roles:
                        transitions_by_role.setdefault(role, []).append(transition)
                ordered_roles = sorted(
                    transitions_by_role.items(),
                    key=lambda item: (
                        -max(contract.work_states.index(rule.target) for rule in item[1]),
                        item[0],
                    ),
                )
                for role, transitions in ordered_roles:
                    reference = swarm.assignments.get(role)
                    if reference is None:
                        continue
                    actor = self._find_actor(root, reference)
                    if selected_reference is not None and actor.reference != selected_reference:
                        continue
                    if human_only and actor.kind != "human":
                        continue
                    actor_sessions = sorted(
                        (
                            item
                            for item in sessions
                            if item.actor == actor.reference
                            and item.swarm_id == swarm.id
                            and item.work_id == work.id
                        ),
                        key=lambda item: (item.created_at, item.id),
                    )
                    latest_session = actor_sessions[-1] if actor_sessions else None
                    blockers: list[str] = []
                    targets: list[str] = []
                    for transition in transitions:
                        targets.append(transition.target)
                        blockers.extend(
                            self._operational_transition_blockers(
                                root, swarm, work, contract, transition
                            )
                        )
                    kind = "execute-work"
                    reason = f"Continue {work.state} work as {role}"
                    session_id_value = None
                    if latest_session is not None and latest_session.status in {
                        "prepared",
                        "running",
                        "failed",
                    }:
                        session_id_value = latest_session.id
                        if latest_session.status == "failed":
                            kind = "retry-session"
                            reason = f"Retry failed session {latest_session.id} as {role}"
                        elif latest_session.status == "running":
                            blockers.append(f"Session {latest_session.id} is already running")
                        else:
                            reason = f"Launch prepared session {latest_session.id} as {role}"
                    if actor.authentication_required:
                        blockers.append("Actor requires signed session preparation and launch")
                    tasks.append(
                        OperationalTask(
                            id=f"{swarm.id}/{work.id}:{role}",
                            kind=kind,  # type: ignore[arg-type]
                            actor=actor.reference,
                            actor_kind=actor.kind,
                            swarm_id=swarm.id,
                            work_id=work.id,
                            role=role,
                            state=work.state,
                            target_states=sorted(set(targets)),
                            blockers=list(dict.fromkeys(blockers)),
                            session_id=session_id_value,
                            reason=reason,
                        )
                    )

        return tasks[:limit]

    def run_next(self, data: RunNextInput) -> SessionRecord:
        tasks = self.next_actions(
            actor_id=data.actor_id,
            swarm_id=data.swarm_id,
            human_only=False,
            limit=1000,
        )
        candidates = [
            task
            for task in tasks
            if task.kind in {"execute-work", "retry-session"}
            and (data.work_id is None or task.work_id == data.work_id)
        ]
        if data.actor_id is None and candidates and candidates[0].actor_kind == "human":
            raise ValueError(f"Next action requires human attention from {candidates[0].actor}")
        eligible = [
            task for task in candidates if task.actor is not None and task.actor_kind != "human"
        ]
        if not eligible:
            raise ValueError("No eligible non-human operational action is available")
        task = eligible[0]
        if any(blocker.endswith("is already running") for blocker in task.blockers):
            raise ValueError(task.blockers[-1])
        if task.session_id is not None:
            existing = self._load_session(
                self.project_root() / ".agora" / "sessions" / task.session_id
            )
            if existing.status == "prepared":
                if data.runner is not None:
                    raise ValueError("A prepared session must launch with its bound runner")
                if data.prepare_only:
                    return existing
                return self.launch_session(
                    LaunchSessionInput(session_id=existing.id, signature=data.signature)
                )
            if existing.status == "failed":
                return self.resume_session(
                    ResumeSessionInput(
                        session_id=existing.id,
                        replacement_id=data.session_id,
                        runner=data.runner,
                        prepare_only=data.prepare_only,
                        signature=data.signature,
                        timeout_seconds=data.timeout_seconds,
                        max_output_bytes=data.max_output_bytes,
                    )
                )
        if data.signature is not None:
            raise ValueError("--signature can only launch an already prepared session")
        session_id = data.session_id or self._available_session_id(
            self.project_root(), f"run-{task.swarm_id}-{task.work_id}"
        )
        return self.start_session(
            StartSessionInput(
                id=session_id,
                actor_id=task.actor,
                swarm_id=task.swarm_id or "",
                work_id=task.work_id,
                runner=data.runner,
                launch=not data.prepare_only,
                timeout_seconds=data.timeout_seconds or DEFAULT_SESSION_TIMEOUT_SECONDS,
                max_output_bytes=data.max_output_bytes or DEFAULT_SESSION_MAX_OUTPUT_BYTES,
            )
        )

    def run_until_blocked(self, data: RunNextInput, *, max_steps: int = 20) -> RunLoopResult:
        if max_steps < 1 or max_steps > 100:
            raise ValueError("Run loop max steps must be between 1 and 100")
        if data.prepare_only:
            raise ValueError("--prepare-only cannot be combined with --until-blocked")
        if data.signature is not None:
            raise ValueError("A run loop cannot reuse one signature across multiple sessions")
        if data.session_id is not None and max_steps > 1:
            raise ValueError("An explicit session id cannot be reused by a multi-step run loop")

        sessions: list[SessionRecord] = []
        for index in range(max_steps):
            actions = self.next_actions(
                actor_id=data.actor_id,
                swarm_id=data.swarm_id,
                human_only=False,
                limit=1000,
            )
            candidates = [
                item
                for item in actions
                if item.kind in {"execute-work", "retry-session"}
                and (data.work_id is None or item.work_id == data.work_id)
            ]
            if data.actor_id is None and candidates and candidates[0].actor_kind == "human":
                return RunLoopResult(
                    sessions=sessions,
                    stop_reason="human-attention",
                    next_actions=actions,
                )
            eligible = [item for item in candidates if item.actor_kind != "human"]
            if not eligible:
                reason = (
                    "human-attention"
                    if any(
                        item.actor_kind == "human" or item.kind == "assign-role" for item in actions
                    )
                    else "no-agent-action"
                )
                return RunLoopResult(
                    sessions=sessions,
                    stop_reason=reason,
                    next_actions=actions,
                )
            selected = eligible[0]
            before = self._operational_task_sha256(selected)
            step_input = data if index == 0 else replace(data, session_id=None)
            sessions.append(self.run_next(step_input))
            after = self._operational_task_sha256(selected)
            if before == after:
                return RunLoopResult(
                    sessions=sessions,
                    stop_reason="no-governed-progress",
                    next_actions=self.next_actions(
                        actor_id=data.actor_id,
                        swarm_id=data.swarm_id,
                        human_only=False,
                        limit=1000,
                    ),
                )

        return RunLoopResult(
            sessions=sessions,
            stop_reason="max-steps",
            next_actions=self.next_actions(
                actor_id=data.actor_id,
                swarm_id=data.swarm_id,
                human_only=False,
                limit=1000,
            ),
        )

    def _operational_task_sha256(self, task: OperationalTask) -> str:
        if task.swarm_id is None or task.work_id is None:
            return hashlib.sha256(task.id.encode()).hexdigest()
        work = self.show_work(task.swarm_id, task.work_id)
        return self._work_precondition_sha256(work)

    def resume_session(self, data: ResumeSessionInput) -> SessionRecord:
        root = self.project_root()
        previous = self._load_session(root / ".agora" / "sessions" / data.session_id)
        if previous.status == "prepared":
            if data.replacement_id is not None or data.runner is not None:
                raise ValueError("A prepared session must launch with its bound id and runner")
            if data.prepare_only:
                return previous
            return self.launch_session(
                LaunchSessionInput(session_id=previous.id, signature=data.signature)
            )
        if previous.status != "failed":
            raise ValueError(f"Only prepared or failed sessions can resume: {previous.id}")
        if data.signature is not None:
            raise ValueError(
                "A failed session retry has new context and requires a new signed preparation"
            )
        replacement_id = data.replacement_id or self._available_session_id(
            root, f"{previous.id}-retry"
        )
        runner = data.runner or shlex.join(previous.launch_command)
        return self.start_session(
            StartSessionInput(
                id=replacement_id,
                actor_id=previous.actor,
                swarm_id=previous.swarm_id,
                work_id=previous.work_id,
                runner=runner,
                launch=not data.prepare_only,
                timeout_seconds=data.timeout_seconds or previous.timeout_seconds,
                max_output_bytes=data.max_output_bytes or previous.max_output_bytes,
            )
        )

    @staticmethod
    def _assert_session_execution_boundaries(
        timeout_seconds: int,
        max_output_bytes: int,
    ) -> None:
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, int)
            or not 1 <= timeout_seconds <= MAX_SESSION_TIMEOUT_SECONDS
        ):
            raise ValueError(
                f"Session timeout must be between 1 and {MAX_SESSION_TIMEOUT_SECONDS} seconds"
            )
        if (
            isinstance(max_output_bytes, bool)
            or not isinstance(max_output_bytes, int)
            or not 1 <= max_output_bytes <= MAX_SESSION_MAX_OUTPUT_BYTES
        ):
            raise ValueError(
                f"Session maximum output must be between 1 and {MAX_SESSION_MAX_OUTPUT_BYTES} bytes"
            )

    def _operational_transition_blockers(
        self,
        root: Path,
        swarm: SwarmRecord,
        work: WorkRecord,
        contract: MethodContract,
        transition: TransitionRule,
    ) -> list[str]:
        blockers: list[str] = []
        try:
            target = transition.target
            if target == contract.terminal_state:
                self._assert_child_work_closed(root, swarm, work)
                self._assert_no_active_approval_delegations(work)
            self._assert_wip_limit(swarm, work, target, contract.wip_limits)
            gate_id = transition.gate
            if gate_id is not None:
                self._assert_work_gate(work, contract.gates[gate_id], gate_id)
        except ValueError as error:
            blockers.append(str(error))
        return blockers

    def _available_session_id(self, root: Path, prefix: str) -> str:
        base = f"{prefix}-{self._now().astimezone(UTC).strftime('%Y%m%dt%H%M%sz')}"
        assert_slug(base, "Session id")
        candidate = base
        suffix = 2
        while (root / ".agora" / "sessions" / candidate).exists():
            candidate = f"{base}-{suffix}"
            suffix += 1
        return candidate

    def list_events(
        self,
        *,
        swarm_id: str | None = None,
        work_id: str | None = None,
        type_: str | None = None,
        limit: int = 50,
    ) -> list[EventRecord]:
        if limit < 1:
            raise ValueError("Event limit must be a positive integer")
        if work_id is not None and swarm_id is None:
            raise ValueError("--work requires --swarm when listing events")
        root = self.project_root()
        sources: list[tuple[str, Path]] = []
        if swarm_id is None:
            sources.append(("project", root / ".agora" / "events.md"))
            swarms = self.list_swarms()
        else:
            swarms = [self._load_swarm(root, swarm_id)]
        for swarm in swarms:
            if work_id is None:
                sources.append((f"swarm:{swarm.id}", Path(swarm.path) / "events.md"))
                sources.extend(
                    (f"work:{swarm.id}/{path.parent.name}", path.parent / "events.md")
                    for path in sorted((Path(swarm.path) / "work").glob("*/WORK.md"))
                )
            else:
                work = self._load_work(swarm, work_id)
                sources.append((f"work:{swarm.id}/{work.id}", Path(work.path) / "events.md"))
        records = [
            record
            for scope, path in sources
            if path.exists()
            for record in self._read_events(path, scope)
            if type_ is None or record.type == type_
        ]
        return sorted(records, key=lambda item: (item.timestamp, item.scope, item.type))[-limit:]

    def validate(self) -> ValidationReport:
        root = self.project_root()
        checked = {
            "project": 0,
            "documents": 0,
            "commands": 0,
            "adapters": 0,
            "methods": 0,
            "tools": 0,
            "tool-adapters": 0,
            "environments": 0,
            "actors": 0,
            "actor-keys": 0,
            "swarms": 0,
            "work": 0,
            "usage": 0,
            "approval-delegations": 0,
            "gate-waivers": 0,
            "handoffs": 0,
            "delegations": 0,
            "status-changes": 0,
            "sessions": 0,
            "session-results": 0,
            "lifecycle-actions": 0,
            "tool-runs": 0,
            "event-files": 0,
            "upgrades": 0,
            "registries": 0,
            "registry-update-audits": 0,
            "pack-update-audits": 0,
            "pack-update-audit-applications": 0,
            "trust-keys": 0,
            "transparency-trust-keys": 0,
            "transparency-proofs": 0,
            "organization-trust-roots": 0,
            "organization-trust-bundles": 0,
            "organization-trust-root-rotations": 0,
            "pack-sources": 0,
            "pack-histories": 0,
            "pack-locks": 0,
            "pack-removals": 0,
        }
        issues: list[ValidationIssue] = []

        def issue(code: str, path: Path, message: str, severity: str = "error") -> None:
            issues.append(
                ValidationIssue(
                    severity="warning" if severity == "warning" else "error",
                    code=code,
                    path=_display_path(root, path),
                    message=message,
                )
            )

        def inspect(
            kind: str, code: str, path: Path, loader: Callable[[], object]
        ) -> object | None:
            try:
                value = loader()
            except Exception as error:
                issue(code, path, str(error))
                return None
            checked[kind] += 1
            return value

        project_path = root / ".agora" / "project.md"
        project = inspect(
            "project",
            "project.invalid",
            project_path,
            lambda: self._load_project_configuration(root),
        )
        if isinstance(project, ProjectConfiguration):
            relation = compare_versions(project.version, CURRENT_PROJECT_VERSION)
            if relation < 0:
                issue(
                    "project.upgrade-available",
                    project_path,
                    f"Project version {project.version} can be upgraded to "
                    f"{CURRENT_PROJECT_VERSION}",
                    "warning",
                )
            elif relation > 0:
                issue(
                    "project.version-newer",
                    project_path,
                    f"Project version {project.version} is newer than this Agora CLI "
                    f"({CURRENT_PROJECT_VERSION})",
                )

        for directory in _child_directories(root / ".agora" / "upgrades"):
            path = directory / "UPGRADE.md"
            record = inspect(
                "upgrades",
                "upgrade.invalid",
                path,
                lambda path=path: read_upgrade_record(path),
            )
            if isinstance(record, MarkdownDocument):
                record_id = string_attribute(record.attributes, "id")
                if record_id != directory.name:
                    issue(
                        "upgrade.id-mismatch",
                        path,
                        f"Upgrade id {record_id} does not match directory {directory.name}",
                    )
        for directory in _child_directories(root / ".agora" / "registries"):
            path = directory / "REGISTRY.md"
            registry = inspect(
                "registries",
                "registry.invalid",
                path,
                lambda directory=directory: load_registry(directory, "project"),
            )
            if isinstance(registry, RegistryRecord) and registry.id != directory.name:
                issue(
                    "registry.id-mismatch",
                    path,
                    f"Registry id {registry.id} does not match directory {directory.name}",
                )
            if isinstance(registry, RegistryRecord) and registry.source is not None:
                source_record = read_registry_source(directory / "SOURCE.md")
                if source_record.transparency_required:
                    proof_path = root / ".agora" / str(source_record.transparency_proof)
                    try:
                        proof = load_transparency_proof(proof_path)
                        require_proof_matches_release(
                            proof,
                            RegistryReleaseRecord(
                                registry=source_record.registry,
                                version=source_record.version,
                                archive=str(source_record.release_archive),
                                sha256=source_record.sha256,
                            ),
                        )
                    except Exception as error:
                        issue("registry.transparency-proof-invalid", proof_path, str(error))
        for directory in _child_directories(root / ".agora" / "notifications" / "registry-updates"):
            path = directory / "AUDIT.md"
            audit = inspect(
                "registry-update-audits",
                "registry-update-audit.invalid",
                path,
                lambda path=path: read_registry_update_audit(path),
            )
            if isinstance(audit, RegistryUpdateAuditRecord) and audit.id != directory.name:
                issue(
                    "registry-update-audit.id-mismatch",
                    path,
                    f"Registry update audit id {audit.id} does not match directory "
                    f"{directory.name}",
                )
        for directory in _child_directories(root / ".agora" / "notifications" / "pack-updates"):
            path = directory / "AUDIT.md"
            audit = inspect(
                "pack-update-audits",
                "pack-update-audit.invalid",
                path,
                lambda path=path: read_pack_update_audit(path),
            )
            if isinstance(audit, PackUpdateAuditRecord) and audit.id != directory.name:
                issue(
                    "pack-update-audit.id-mismatch",
                    path,
                    f"Pack update audit id {audit.id} does not match directory {directory.name}",
                )
            application_path = directory / "APPLICATION.md"
            if not application_path.is_file():
                continue
            application = inspect(
                "pack-update-audit-applications",
                "pack-update-audit-application.invalid",
                application_path,
                lambda application_path=application_path: read_pack_update_audit_application(
                    application_path
                ),
            )
            if not isinstance(application, PackUpdateAuditApplicationRecord):
                continue
            if application.id != directory.name or application.scope != "project":
                issue(
                    "pack-update-audit-application.identity-mismatch",
                    application_path,
                    "Pack update audit application identity does not match its location",
                )
            if application.audit_sha256 != hashlib.sha256(path.read_bytes()).hexdigest():
                issue(
                    "pack-update-audit-application.audit-mismatch",
                    application_path,
                    "Applied pack update audit changed after application",
                )
            for history in application.history_paths:
                history_path = Path(history)
                if history_path.is_absolute() or ".." in history_path.parts:
                    issue(
                        "pack-update-audit-application.history-path-invalid",
                        application_path,
                        f"Pack update history path is not portable: {history}",
                    )
                elif not (root / ".agora" / history_path).is_file():
                    issue(
                        "pack-update-audit-application.history-missing",
                        application_path,
                        f"Applied pack update history is missing: {history}",
                    )
        trust_keys: dict[str, RegistryTrustKeyRecord] = {}
        for path in sorted((root / ".agora" / "trust" / "keys").glob("*.md")):
            record = inspect(
                "trust-keys",
                "trust-key.invalid",
                path,
                lambda path=path: load_trust_key(path, "project"),
            )
            if not isinstance(record, RegistryTrustKeyRecord):
                continue
            trust_keys[record.id] = record
            if record.id != path.stem:
                issue(
                    "trust-key.id-mismatch",
                    path,
                    f"Registry trust key id {record.id} does not match file {path.name}",
                )
        for record in trust_keys.values():
            if record.replaced_by is None:
                continue
            replacement = trust_keys.get(record.replaced_by)
            if replacement is None:
                issue(
                    "trust-key.replacement-missing",
                    Path(record.path),
                    f"Replacement registry trust key does not exist: {record.replaced_by}",
                )
            elif replacement.registry != record.registry or replacement.status != "active":
                issue(
                    "trust-key.replacement-invalid",
                    Path(record.path),
                    "Replacement registry trust key must be active for the same registry",
                )
        transparency_keys: dict[str, TransparencyTrustKeyRecord] = {}
        for path in sorted((root / ".agora" / "trust" / "transparency").glob("*.md")):
            record = inspect(
                "transparency-trust-keys",
                "transparency-trust-key.invalid",
                path,
                lambda path=path: load_transparency_key(path, "project"),
            )
            if not isinstance(record, TransparencyTrustKeyRecord):
                continue
            transparency_keys[record.id] = record
            if record.id != path.stem:
                issue(
                    "transparency-trust-key.id-mismatch",
                    path,
                    f"Transparency trust key id {record.id} does not match file {path.name}",
                )
        for record in transparency_keys.values():
            if record.replaced_by is None:
                continue
            replacement = transparency_keys.get(record.replaced_by)
            if replacement is None:
                issue(
                    "transparency-trust-key.replacement-missing",
                    Path(record.path),
                    f"Replacement transparency trust key does not exist: {record.replaced_by}",
                )
            elif replacement.log != record.log or replacement.status != "active":
                issue(
                    "transparency-trust-key.replacement-invalid",
                    Path(record.path),
                    "Replacement transparency trust key must be active for the same log",
                )
        user_transparency_keys: dict[str, TransparencyTrustKeyRecord] = {}
        for path in sorted((agora_home() / "trust" / "transparency").glob("*.md")):
            try:
                record = load_transparency_key(path, "user")
            except Exception:
                continue
            user_transparency_keys[record.id] = record
        proof_root = root / ".agora" / "transparency"
        for path in sorted(proof_root.rglob("PROOF.md")):
            proof = inspect(
                "transparency-proofs",
                "transparency-proof.invalid",
                path,
                lambda path=path: load_transparency_proof(path),
            )
            if not isinstance(proof, TransparencyInclusionProofRecord):
                continue
            relative = path.relative_to(proof_root)
            expected = (proof.log, proof.registry, proof.version, "PROOF.md")
            if relative.parts != expected:
                issue(
                    "transparency-proof.location-mismatch",
                    path,
                    "Transparency proof identity does not match its durable location",
                )
            key = transparency_keys.get(proof.key_id) or user_transparency_keys.get(proof.key_id)
            if key is None:
                issue(
                    "transparency-proof.key-missing",
                    path,
                    f"Transparency trust key does not exist: {proof.key_id}",
                )
                continue
            try:
                verify_transparency_proof(proof, key)
            except Exception as error:
                issue("transparency-proof.verification-failed", path, str(error))
        for directory in _child_directories(root / ".agora" / "trust" / "organizations"):
            root_path = directory / "ROOT.md"
            organization_root = inspect(
                "organization-trust-roots",
                "organization-trust-root.invalid",
                root_path,
                lambda root_path=root_path: load_organization_trust_root(root_path, "project"),
            )
            if not isinstance(organization_root, OrganizationTrustRootRecord):
                continue
            if organization_root.id != directory.name:
                issue(
                    "organization-trust-root.id-mismatch",
                    root_path,
                    f"Organization trust id {organization_root.id} does not match directory "
                    f"{directory.name}",
                )
            rotations: list[OrganizationTrustRootRotationRecord] = []
            expected_rotation = 1
            previous_rotation_sha256: str | None = None
            previous_to_fingerprint: str | None = None
            previous_bundle_sequence = 0
            for rotation_path in sorted((directory / "rotations").glob("*.md")):
                rotation = inspect(
                    "organization-trust-root-rotations",
                    "organization-trust-root-rotation.invalid",
                    rotation_path,
                    lambda rotation_path=rotation_path: load_organization_trust_root_rotation(
                        rotation_path.read_bytes(), scope="project", path=str(rotation_path)
                    ),
                )
                if not isinstance(rotation, OrganizationTrustRootRotationRecord):
                    continue
                rotations.append(rotation)
                if rotation_path.stem != f"{rotation.rotation:020d}":
                    issue(
                        "organization-trust-root-rotation.filename-mismatch",
                        rotation_path,
                        f"Root rotation {rotation.rotation} does not match {rotation_path.name}",
                    )
                if (
                    rotation.organization != organization_root.id
                    or rotation.rotation != expected_rotation
                    or rotation.previous_rotation_sha256 != previous_rotation_sha256
                    or (
                        previous_to_fingerprint is not None
                        and rotation.from_fingerprint != previous_to_fingerprint
                    )
                    or rotation.bundle_sequence < previous_bundle_sequence
                ):
                    issue(
                        "organization-trust-root-rotation.history-gap",
                        rotation_path,
                        "Organization trust root rotation history is not continuous",
                    )
                expected_rotation = rotation.rotation + 1
                previous_rotation_sha256 = rotation.sha256
                previous_to_fingerprint = rotation.to_fingerprint
                previous_bundle_sequence = rotation.bundle_sequence

            bundle_root = organization_root
            if rotations:
                first = rotations[0]
                if (
                    first.from_public_key != organization_root.initial_public_key
                    or first.from_fingerprint != organization_root.initial_fingerprint
                ):
                    issue(
                        "organization-trust-root-rotation.anchor-mismatch",
                        Path(first.path),
                        "First root rotation does not start at the pinned initial root",
                    )
                bundle_root = replace(
                    organization_root,
                    public_key=first.from_public_key,
                    fingerprint=first.from_fingerprint,
                )
                last = rotations[-1]
                if (
                    last.to_public_key != organization_root.public_key
                    or last.to_fingerprint != organization_root.fingerprint
                ):
                    issue(
                        "organization-trust-root-rotation.active-root-mismatch",
                        root_path,
                        "Active organization root does not match the final rotation",
                    )
            elif (
                organization_root.public_key != organization_root.initial_public_key
                or organization_root.fingerprint != organization_root.initial_fingerprint
            ):
                issue(
                    "organization-trust-root.anchor-mismatch",
                    root_path,
                    "Active organization root differs from its anchor without rotation history",
                )

            expected_sequence = 1
            previous_sha256: str | None = None
            bundle_checksums: dict[int, str] = {}
            managed_keys: dict[str, RegistryTrustKeyRecord] = {}
            for history_path in sorted((directory / "history").glob("*.md")):
                for rotation in rotations:
                    if rotation.bundle_sequence < expected_sequence:
                        bundle_root = replace(
                            bundle_root,
                            public_key=rotation.to_public_key,
                            fingerprint=rotation.to_fingerprint,
                        )
                try:
                    sequence, previous, bundle_keys, checksum, _ = load_organization_trust_bundle(
                        history_path.read_bytes(), root=bundle_root
                    )
                except Exception as error:
                    issue("organization-trust-bundle.invalid", history_path, str(error))
                    continue
                checked["organization-trust-bundles"] += 1
                if history_path.stem != f"{sequence:020d}":
                    issue(
                        "organization-trust-bundle.filename-mismatch",
                        history_path,
                        f"Bundle sequence {sequence} does not match {history_path.name}",
                    )
                if sequence != expected_sequence or previous != previous_sha256:
                    issue(
                        "organization-trust-bundle.history-gap",
                        history_path,
                        "Organization trust bundle history is not continuous",
                    )
                expected_sequence = sequence + 1
                previous_sha256 = checksum
                bundle_checksums[sequence] = checksum
                managed_keys.update((item.id, item) for item in bundle_keys)
            for rotation in rotations:
                expected_bundle_sha256 = (
                    None
                    if rotation.bundle_sequence == 0
                    else bundle_checksums.get(rotation.bundle_sequence)
                )
                if rotation.bundle_sha256 != expected_bundle_sha256:
                    issue(
                        "organization-trust-root-rotation.bundle-mismatch",
                        Path(rotation.path),
                        "Root rotation does not match its persisted bundle boundary",
                    )
            if (
                organization_root.last_sequence != expected_sequence - 1
                or organization_root.last_sha256 != previous_sha256
            ):
                issue(
                    "organization-trust-root.history-mismatch",
                    root_path,
                    "Organization trust root does not match its persisted bundle history",
                )
            for id_, managed in managed_keys.items():
                current = trust_keys.get(id_)
                if current is None:
                    issue(
                        "organization-trust-key.missing",
                        root_path,
                        f"Organization-managed registry trust key is missing: {id_}",
                    )
                    continue
                current_state = (
                    current.registry,
                    current.algorithm,
                    current.public_key,
                    current.fingerprint,
                    current.status,
                    current.created_at,
                    current.revoked_at,
                    current.revoked_reason,
                    current.replaced_by,
                )
                managed_state = (
                    managed.registry,
                    managed.algorithm,
                    managed.public_key,
                    managed.fingerprint,
                    managed.status,
                    managed.created_at,
                    managed.revoked_at,
                    managed.revoked_reason,
                    managed.replaced_by,
                )
                if current_state != managed_state:
                    issue(
                        "organization-trust-key.history-mismatch",
                        Path(current.path),
                        f"Registry trust key {id_} differs from its latest organization bundle",
                    )
        for path, schema in (
            (root / ".agora" / "constitution.md", "agora/constitution/v1"),
            (root / ".agora" / "PROTOCOL.md", "agora/protocol/v1"),
            (root / ".agora" / "tools" / "TOOLS.md", "agora/tool-policy/v1"),
        ):
            inspect(
                "documents",
                "document.invalid",
                path,
                lambda path=path, schema=schema: _assert_schema(read_markdown(path), schema, path),
            )
        coordination_path = root / ".agora" / "coordination.md"
        if coordination_path.exists():
            inspect(
                "documents",
                "coordination.invalid",
                coordination_path,
                lambda: load_coordination_policy(coordination_path),
            )
        standards_path = root / ".agora" / "STANDARDS.md"
        inspect(
            "documents",
            "standards.invalid",
            standards_path,
            lambda: _assert_project_standards(read_markdown(standards_path), standards_path),
        )

        environments: dict[str, EnvironmentPolicyRecord] = {}
        for path in sorted((root / ".agora" / "environments").glob("*.md")):
            if path.name == "README.md":
                continue
            environment = inspect(
                "environments",
                "environment.invalid",
                path,
                lambda path=path: self._load_environment(path),
            )
            if not isinstance(environment, EnvironmentPolicyRecord):
                continue
            environments[environment.id] = environment
            if environment.id != path.stem:
                issue(
                    "environment.id-mismatch",
                    path,
                    f"Environment id {environment.id} does not match filename {path.name}",
                )

        command_root = root / ".agora" / "commands"
        commands: dict[str, Path] = {}
        for path in sorted(command_root.glob("*.md")):
            command_id = path.stem
            command = inspect(
                "commands",
                "command.invalid",
                path,
                lambda path=path, command_id=command_id: self._load_agent_command(path, command_id),
            )
            if isinstance(command, MarkdownDocument):
                commands[command_id] = path
        if not commands:
            issue(
                "commands.missing",
                command_root,
                "Project has no portable agent command Markdown files",
            )

        if isinstance(project, ProjectConfiguration):
            expected_adapters = {
                command_id: self._integration_command_path(root, project.integration, command_id)
                for command_id in commands
            }
            for command_id, adapter_path in expected_adapters.items():
                adapter = inspect(
                    "adapters",
                    "adapter.invalid",
                    adapter_path,
                    lambda adapter_path=adapter_path, command_id=command_id: (
                        self._load_agent_command(adapter_path, command_id)
                    ),
                )
                source_path = commands[command_id]
                if (
                    isinstance(adapter, MarkdownDocument)
                    and adapter_path != source_path
                    and adapter_path.read_text(encoding="utf-8")
                    != source_path.read_text(encoding="utf-8")
                ):
                    issue(
                        "adapter.content-mismatch",
                        adapter_path,
                        f"{project.integration} adapter differs from "
                        f".agora/commands/{source_path.name}",
                    )
            expected_paths = set(expected_adapters.values())
            for adapter_path in self._integration_command_paths(root, project.integration):
                if adapter_path not in expected_paths:
                    issue(
                        "adapter.orphan",
                        adapter_path,
                        "Adapter has no matching portable command",
                        "warning",
                    )

        methods: dict[str, MethodContract] = {}
        method_root = root / ".agora" / "methods"
        for directory in _child_directories(method_root):
            path = directory / "METHOD.md"
            contract = inspect(
                "methods",
                "method.invalid",
                path,
                lambda path=path: load_method_contract(path.parent),
            )
            if isinstance(contract, MethodContract):
                methods[path.parent.name] = contract
                if contract.id != path.parent.name:
                    issue(
                        "method.id-mismatch",
                        path,
                        f"Method id {contract.id} does not match directory {path.parent.name}",
                    )
                self._validate_pack_source("method", path.parent, contract, inspect, issue)
        if isinstance(project, ProjectConfiguration) and project.default_method not in methods:
            issue(
                "project.default-method-missing",
                project_path,
                f"Default Method Pack is not valid or installed: {project.default_method}",
            )
        for method_id, contract in methods.items():
            for role_id in contract.required_roles:
                role_path = method_root / method_id / "roles" / f"{role_id}.md"
                role = read_markdown(role_path)
                allowed_environments = role.attributes.get("allowed-environments", ["*"])
                unknown = sorted(set(allowed_environments) - {"*"} - set(environments))
                if unknown:
                    issue(
                        "role.environment-missing",
                        role_path,
                        f"Role {role_id} allows missing environments: {', '.join(unknown)}",
                    )
        known_role_ids = {
            role_id for contract in methods.values() for role_id in contract.required_roles
        }
        for environment in environments.values():
            unknown_roles = sorted(set(environment.required_approval_roles) - known_role_ids)
            if unknown_roles:
                issue(
                    "environment.approval-role-missing",
                    Path(environment.path),
                    "Environment requires roles absent from installed Method Packs: "
                    f"{', '.join(unknown_roles)}",
                )

        tools: dict[str, ToolContract] = {}
        tool_root = root / ".agora" / "tools"
        for directory in _child_directories(tool_root):
            path = directory / "TOOL.md"
            contract = inspect(
                "tools",
                "tool.invalid",
                path,
                lambda path=path: load_tool_contract(path.parent),
            )
            if isinstance(contract, ToolContract):
                tools[path.parent.name] = contract
                if contract.id != path.parent.name:
                    issue(
                        "tool.id-mismatch",
                        path,
                        f"Tool id {contract.id} does not match directory {path.parent.name}",
                    )
                self._validate_pack_source("tool", path.parent, contract, inspect, issue)

        for adapter in tools.values():
            if adapter.implements is None:
                continue
            implemented = tools.get(adapter.implements)
            adapter_path = tool_root / adapter.id / "TOOL.md"
            if implemented is None:
                issue(
                    "tool-adapter.implementation-missing",
                    adapter_path,
                    f"Implemented Tool Pack is not installed: {adapter.implements}",
                )
                continue
            inspect(
                "tool-adapters",
                "tool-adapter.contract-invalid",
                adapter_path,
                lambda adapter=adapter, implemented=implemented: validate_tool_adapter_contract(
                    adapter, implemented
                ),
            )

        installed_packs: dict[tuple[str, str], MethodContract | ToolContract] = {
            **{("method", id_): contract for id_, contract in methods.items()},
            **{("tool", id_): contract for id_, contract in tools.items()},
        }
        for key, message in self._pack_composition_issues(installed_packs):
            kind, id_ = key
            manifest = "METHOD.md" if kind == "method" else "TOOL.md"
            issue(
                "pack.dependency-invalid",
                root / ".agora" / f"{kind}s" / id_ / manifest,
                message,
            )
        pack_lock_path = root / ".agora" / "PACKS.lock.md"
        if not pack_lock_path.is_file():
            issue(
                "pack-lock.missing",
                pack_lock_path,
                "Project pack composition lock is missing; run `agora pack lock`",
                "warning",
            )
        else:
            pack_lock = inspect(
                "pack-locks",
                "pack-lock.invalid",
                pack_lock_path,
                lambda: read_pack_lock(pack_lock_path),
            )
            if isinstance(pack_lock, PackLockRecord):
                expected_lock = self._build_pack_lock(
                    "project", root / ".agora", generated_at=pack_lock.generated_at
                )
                if pack_lock.scope != "project" or pack_lock.packs != expected_lock.packs:
                    issue(
                        "pack-lock.drift",
                        pack_lock_path,
                        "Project pack composition differs from PACKS.lock.md; "
                        "review and refresh it",
                    )

        for directory in _child_directories(root / ".agora" / "pack-removals"):
            path = directory / "REMOVAL.md"
            removal = inspect(
                "pack-removals",
                "pack-removal.invalid",
                path,
                lambda path=path: read_pack_removal(path),
            )
            if not isinstance(removal, PackRemovalRecord):
                continue
            if removal.id != directory.name:
                issue(
                    "pack-removal.id-mismatch",
                    path,
                    f"Pack removal id {removal.id} does not match directory {directory.name}",
                )
            if removal.scope != "project":
                issue(
                    "pack-removal.scope-mismatch",
                    path,
                    f"Project pack removal has unexpected scope: {removal.scope}",
                )

        actor_cache: dict[str, ActorRecord] = {}
        validated_actor_key_histories: set[str] = set()

        def inspect_actor_key_history(actor: ActorRecord) -> None:
            if actor.reference in validated_actor_key_histories:
                return
            validated_actor_key_histories.add(actor.reference)
            records: dict[str, ActorKeyRecord] = {}
            for key_path in sorted(self._actor_key_root(actor).glob("*.md")):
                key = inspect(
                    "actor-keys",
                    "actor-key.invalid",
                    key_path,
                    lambda key_path=key_path: load_actor_key(key_path),
                )
                if not isinstance(key, ActorKeyRecord):
                    continue
                if key.fingerprint != key_path.stem:
                    issue(
                        "actor-key.fingerprint-mismatch",
                        key_path,
                        "Actor key fingerprint does not match its filename",
                    )
                if key.actor != actor.reference:
                    issue(
                        "actor-key.actor-mismatch",
                        key_path,
                        f"Actor key belongs to {key.actor}, expected {actor.reference}",
                    )
                if key.fingerprint in records:
                    issue(
                        "actor-key.duplicate",
                        key_path,
                        f"Duplicate actor key fingerprint: {key.fingerprint}",
                    )
                records[key.fingerprint] = key
            if not records:
                return
            current = (
                records.get(actor.authentication_fingerprint)
                if actor.authentication_fingerprint is not None
                else None
            )
            expected_status = "revoked" if actor.authentication_revoked_at is not None else "active"
            if current is None or current.status != expected_status:
                issue(
                    "actor-key.current-mismatch",
                    Path(actor.path),
                    "Actor current authentication state differs from its key history",
                )
            active = [record for record in records.values() if record.status == "active"]
            expected_active = 0 if actor.authentication_revoked_at is not None else 1
            if len(active) != expected_active:
                issue(
                    "actor-key.active-count",
                    self._actor_key_root(actor),
                    f"Actor key history must contain {expected_active} active key(s)",
                )
            for record in records.values():
                if record.replaced_by is not None and record.replaced_by not in records:
                    issue(
                        "actor-key.replacement-missing",
                        Path(record.path),
                        f"Replacement actor key does not exist: {record.replaced_by}",
                    )

        actor_root = root / ".agora" / "actors"
        for path in sorted(actor_root.glob("*.md")):
            if path.name == "README.md":
                continue
            actor = inspect(
                "actors",
                "actor.invalid",
                path,
                lambda path=path: self._find_actor(root, f"project:{path.stem}"),
            )
            if isinstance(actor, ActorRecord):
                actor_cache[actor.reference] = actor
                inspect_actor_key_history(actor)
                if actor.id != path.stem:
                    issue(
                        "actor.id-mismatch",
                        path,
                        f"Actor id {actor.id} does not match filename {path.stem}",
                    )

        def resolve_actor(reference: str, path: Path) -> ActorRecord | None:
            if reference in actor_cache:
                return actor_cache[reference]
            actor = inspect(
                "actors",
                "actor.reference-invalid",
                path,
                lambda: self._find_actor(root, reference),
            )
            if isinstance(actor, ActorRecord):
                actor_cache[actor.reference] = actor
                inspect_actor_key_history(actor)
                if actor.id != Path(actor.path).stem:
                    issue(
                        "actor.id-mismatch",
                        Path(actor.path),
                        f"Actor id {actor.id} does not match filename {Path(actor.path).stem}",
                    )
                return actor
            return None

        def inspect_status_changes(
            owner: Path,
            *,
            subject_type: str,
            subject: str,
            statuses: set[str],
            transitions: dict[tuple[str, str], str],
        ) -> list[StatusChangeRecord]:
            records: list[StatusChangeRecord] = []
            for directory in _child_directories(owner / "status-changes"):
                path = directory / "STATUS.md"
                change = inspect(
                    "status-changes",
                    "status-change.invalid",
                    path,
                    lambda directory=directory: self._load_status_change(directory),
                )
                if not isinstance(change, StatusChangeRecord):
                    continue
                records.append(change)
                if change.id != directory.name:
                    issue(
                        "status-change.id-mismatch",
                        path,
                        f"Status change id {change.id} does not match directory {directory.name}",
                    )
                if change.subject_type != subject_type or change.subject != subject:
                    issue(
                        "status-change.subject-mismatch",
                        path,
                        f"Status change does not belong to {subject_type} {subject}",
                    )
                edge = (change.previous_status, change.target_status)
                if (
                    change.previous_status not in statuses
                    or change.target_status not in statuses
                    or edge not in transitions
                    or transitions.get(edge) != change.action
                ):
                    issue(
                        "status-change.transition-invalid",
                        path,
                        f"Unsupported status action {change.action}: "
                        f"{change.previous_status} -> {change.target_status}",
                    )
                if not change.reason.strip():
                    issue("status-change.reason-missing", path, "Status change reason is empty")
                resolve_actor(change.actor, path)
            sequences = [item.sequence for item in records]
            if sequences and sorted(sequences) != list(range(1, len(sequences) + 1)):
                issue(
                    "status-change.sequence-invalid",
                    owner / "status-changes",
                    "Status change sequence must be unique and contiguous from 1",
                )
            records.sort(key=lambda item: (item.sequence, item.created_at, item.id))
            for previous, current in zip(records, records[1:], strict=False):
                if previous.target_status != current.previous_status:
                    issue(
                        "status-change.history-discontinuous",
                        Path(current.path),
                        f"Previous target {previous.target_status} does not match "
                        f"next source {current.previous_status}",
                    )
            return records

        swarms: dict[str, SwarmRecord] = {}
        swarm_root = root / ".agora" / "swarms"
        for directory in _child_directories(swarm_root):
            path = directory / "SWARM.md"
            swarm = inspect(
                "swarms",
                "swarm.invalid",
                path,
                lambda path=path: self._load_swarm(root, path.parent.name),
            )
            if not isinstance(swarm, SwarmRecord):
                continue
            swarms[swarm.id] = swarm
            if swarm.id != path.parent.name:
                issue(
                    "swarm.id-mismatch",
                    path,
                    f"Swarm id {swarm.id} does not match directory {path.parent.name}",
                )
            if swarm.status not in {
                "forming",
                "ready",
                "running",
                "blocked",
                "completed",
                "cancelled",
            }:
                issue("swarm.status-invalid", path, f"Unsupported swarm status: {swarm.status}")
            contract = methods.get(swarm.method)
            if contract is None:
                issue(
                    "swarm.method-missing",
                    path,
                    f"Method Pack is not valid or installed: {swarm.method}",
                )
                continue
            if swarm.required_roles != contract.required_roles:
                issue(
                    "swarm.roles-mismatch",
                    path,
                    "Swarm required roles do not match its Method Pack",
                )
            unknown_roles = sorted(set(swarm.assignments) - set(swarm.required_roles))
            if unknown_roles:
                issue(
                    "swarm.assignment-role-invalid",
                    path,
                    f"Assignments use unknown roles: {', '.join(unknown_roles)}",
                )
            for role_id, reference in swarm.assignments.items():
                actor = resolve_actor(reference, path)
                if actor is None or role_id not in swarm.required_roles:
                    continue
                try:
                    self._assert_actor_role_compatibility(root, swarm.method, role_id, actor)
                except Exception as error:
                    issue("swarm.assignment-incompatible", path, str(error))
            complete_assignments = all(
                role_id in swarm.assignments for role_id in swarm.required_roles
            )
            if swarm.status == "forming" and complete_assignments:
                issue(
                    "swarm.status-stale",
                    path,
                    "Forming swarm has every required role assigned",
                    "warning",
                )
            if swarm.status != "forming" and not complete_assignments:
                issue(
                    "swarm.assignments-incomplete",
                    path,
                    "Non-forming swarm is missing required role assignments",
                )

        work_records: dict[tuple[str, str], WorkRecord] = {}
        usage_records: dict[tuple[str, str, str], UsageRecord] = {}
        approval_delegation_records: dict[tuple[str, str, str], ApprovalDelegationRecord] = {}
        gate_waiver_records: dict[tuple[str, str, str], GateWaiverRecord] = {}
        for swarm in swarms.values():
            contract = methods.get(swarm.method)
            state_counts: dict[str, int] = {}
            for directory in _child_directories(Path(swarm.path) / "work"):
                path = directory / "WORK.md"
                work = inspect(
                    "work",
                    "work.invalid",
                    path,
                    lambda swarm=swarm, path=path: self._load_work(swarm, path.parent.name),
                )
                if not isinstance(work, WorkRecord):
                    continue
                work_records[(swarm.id, work.id)] = work
                try:
                    self._normalize_budget_limits(work.budget_limits)
                except ValueError as error:
                    issue("work.budget-invalid", path, str(error))
                if work.id != path.parent.name:
                    issue(
                        "work.id-mismatch",
                        path,
                        f"Work id {work.id} does not match directory {path.parent.name}",
                    )
                if work.swarm_id != swarm.id:
                    issue(
                        "work.swarm-mismatch",
                        path,
                        f"Work references swarm {work.swarm_id}, expected {swarm.id}",
                    )
                if contract is not None and work.state not in contract.work_states:
                    issue(
                        "work.state-invalid",
                        path,
                        f"State {work.state} is not defined by Method Pack {swarm.method}",
                    )
                changes = inspect_status_changes(
                    Path(work.path),
                    subject_type="work",
                    subject=f"{swarm.id}/{work.id}",
                    statuses={"active", "blocked", "cancelled"},
                    transitions={
                        ("active", "blocked"): "work.block",
                        ("blocked", "active"): "work.resume",
                        ("active", "cancelled"): "work.cancel",
                        ("blocked", "cancelled"): "work.cancel",
                    },
                )
                if work.operational_status != "active" and (
                    work.status_reason is None or work.status_by is None or work.status_at is None
                ):
                    issue(
                        "work.status-attribution-missing",
                        path,
                        f"{work.operational_status.title()} work lacks reason, actor, or timestamp",
                    )
                if work.status_by is not None:
                    resolve_actor(work.status_by, path)
                if changes and changes[-1].target_status != work.operational_status:
                    issue(
                        "work.status-history-stale",
                        path,
                        "Latest status change does not match work operational status",
                    )
                if work.operational_status != "active" and not changes:
                    issue(
                        "work.status-history-missing",
                        path,
                        f"{work.operational_status.title()} work has no durable status change",
                    )
                unknown_criteria = sorted(
                    set(work.satisfied_criteria) - set(work.acceptance_criteria)
                )
                if unknown_criteria:
                    issue(
                        "work.criteria-invalid",
                        path,
                        f"Satisfied criteria are not declared: {', '.join(unknown_criteria)}",
                    )
                if work.operational_status != "cancelled":
                    state_counts[work.state] = state_counts.get(work.state, 0) + 1
                usage_totals: dict[str, int] = {}
                for usage_directory in _child_directories(Path(work.path) / "usage"):
                    usage_path = usage_directory / "USAGE.md"
                    usage = inspect(
                        "usage",
                        "usage.invalid",
                        usage_path,
                        lambda usage_path=usage_path: self._load_usage(usage_path),
                    )
                    if not isinstance(usage, UsageRecord):
                        continue
                    usage_records[(swarm.id, work.id, usage.id)] = usage
                    if usage.id != usage_directory.name:
                        issue(
                            "usage.id-mismatch",
                            usage_path,
                            "Usage id does not match its directory",
                        )
                    if usage.swarm_id != swarm.id or usage.work_id != work.id:
                        issue(
                            "usage.owner-mismatch",
                            usage_path,
                            "Usage does not belong to its filesystem owner",
                        )
                    usage_actor = resolve_actor(usage.actor, usage_path)
                    if (
                        usage_actor is not None
                        and usage_actor.authentication_required
                        and usage.action_id is None
                    ):
                        issue(
                            "usage.authentication-missing",
                            usage_path,
                            f"Actor {usage.actor} requires a signed usage action",
                        )
                    if (
                        usage.action_id is not None
                        and not (
                            root / ".agora" / "actions" / usage.action_id / "ACTION.md"
                        ).is_file()
                    ):
                        issue(
                            "usage.action-missing",
                            usage_path,
                            f"Usage references missing Lifecycle Action: {usage.action_id}",
                        )
                    for dimension, amount in usage.amounts.items():
                        usage_totals[dimension] = usage_totals.get(dimension, 0) + amount
                if work.budget_limits is not None:
                    unknown_usage = sorted(set(usage_totals) - set(work.budget_limits))
                    if unknown_usage:
                        issue(
                            "usage.dimension-unavailable",
                            path,
                            "Usage dimensions are absent from the work budget: "
                            + ", ".join(unknown_usage),
                        )
                    for dimension in sorted(set(usage_totals) & set(work.budget_limits)):
                        if usage_totals[dimension] > work.budget_limits[dimension]:
                            issue(
                                "usage.budget-exceeded",
                                path,
                                f"Usage {dimension}={usage_totals[dimension]} exceeds "
                                f"work budget {work.budget_limits[dimension]}",
                            )
                for waiver_directory in _child_directories(Path(work.path) / "waivers"):
                    waiver_path = waiver_directory / "WAIVER.md"
                    waiver = inspect(
                        "gate-waivers",
                        "gate-waiver.invalid",
                        waiver_path,
                        lambda waiver_path=waiver_path: self._load_gate_waiver(waiver_path),
                    )
                    if not isinstance(waiver, GateWaiverRecord):
                        continue
                    gate_waiver_records[(swarm.id, work.id, waiver.id)] = waiver
                    if waiver.id != waiver_directory.name:
                        issue(
                            "gate-waiver.id-mismatch",
                            waiver_path,
                            "Gate Waiver id does not match its directory",
                        )
                    if waiver.swarm_id != swarm.id or waiver.work_id != work.id:
                        issue(
                            "gate-waiver.owner-mismatch",
                            waiver_path,
                            "Gate Waiver does not belong to its filesystem owner",
                        )
                    resolve_actor(waiver.authorized_by, waiver_path)
                    gate = contract.gates.get(waiver.gate_id) if contract is not None else None
                    if gate is None:
                        issue(
                            "gate-waiver.gate-missing",
                            waiver_path,
                            f"Gate Waiver references unknown gate: {waiver.gate_id}",
                        )
                        continue
                    invalid_criteria = sorted(
                        set(waiver.waived_criteria) - set(work.acceptance_criteria)
                    )
                    invalid_artifacts = sorted(
                        set(waiver.waived_artifacts) - set(work.required_artifacts)
                    )
                    invalid_approvals = sorted(
                        set(waiver.waived_approval_roles) - set(gate.required_approval_roles)
                    )
                    if waiver.waived_criteria and (
                        not gate.require_all_criteria or invalid_criteria
                    ):
                        issue(
                            "gate-waiver.criteria-invalid",
                            waiver_path,
                            "Waived criteria are not obligations of this gate: "
                            + ", ".join(invalid_criteria or waiver.waived_criteria),
                        )
                    if waiver.waived_artifacts and (
                        not gate.require_required_artifacts or invalid_artifacts
                    ):
                        issue(
                            "gate-waiver.artifacts-invalid",
                            waiver_path,
                            "Waived artifacts are not obligations of this gate: "
                            + ", ".join(invalid_artifacts or waiver.waived_artifacts),
                        )
                    if waiver.waive_successful_evidence and not gate.require_successful_evidence:
                        issue(
                            "gate-waiver.evidence-invalid",
                            waiver_path,
                            "Successful evidence is not required by this gate",
                        )
                    if invalid_approvals:
                        issue(
                            "gate-waiver.approvals-invalid",
                            waiver_path,
                            "Waived approvals are not obligations of this gate: "
                            + ", ".join(invalid_approvals),
                        )
                active_delegation_roles: set[str] = set()
                for delegation_directory in _child_directories(
                    Path(work.path) / "approval-delegations"
                ):
                    delegation_path = delegation_directory / "DELEGATION.md"
                    delegation = inspect(
                        "approval-delegations",
                        "approval-delegation.invalid",
                        delegation_path,
                        lambda work=work, delegation_directory=delegation_directory: (
                            self._load_approval_delegation(work, delegation_directory.name)
                        ),
                    )
                    if not isinstance(delegation, ApprovalDelegationRecord):
                        continue
                    approval_delegation_records[(swarm.id, work.id, delegation.id)] = delegation
                    if delegation.id != delegation_directory.name:
                        issue(
                            "approval-delegation.id-mismatch",
                            delegation_path,
                            "Approval Delegation id does not match its directory",
                        )
                    if delegation.swarm_id != swarm.id or delegation.work_id != work.id:
                        issue(
                            "approval-delegation.owner-mismatch",
                            delegation_path,
                            "Approval Delegation does not belong to its filesystem owner",
                        )
                    grantor = resolve_actor(delegation.from_actor, delegation_path)
                    target = resolve_actor(delegation.to_actor, delegation_path)
                    if contract is None or delegation.role_id not in contract.required_roles:
                        issue(
                            "approval-delegation.role-invalid",
                            delegation_path,
                            f"Approval Delegation uses unknown role: {delegation.role_id}",
                        )
                    elif not self._role_allows_action(
                        root, swarm.method, delegation.role_id, "approval.add"
                    ):
                        issue(
                            "approval-delegation.authority-invalid",
                            delegation_path,
                            f"Delegated role cannot approve work: {delegation.role_id}",
                        )
                    elif target is not None:
                        try:
                            self._assert_actor_role_compatibility(
                                root, swarm.method, delegation.role_id, target
                            )
                        except Exception as error:
                            issue(
                                "approval-delegation.target-incompatible",
                                delegation_path,
                                str(error),
                            )
                    if delegation.status == "active":
                        if work.operational_status == "cancelled" or (
                            contract is not None and work.state == contract.terminal_state
                        ):
                            issue(
                                "approval-delegation.active-on-closed-work",
                                delegation_path,
                                "Closed work retains an active Approval Delegation",
                            )
                        if swarm.assignments.get(delegation.role_id) != delegation.from_actor:
                            issue(
                                "approval-delegation.grantor-unassigned",
                                delegation_path,
                                "Active Approval Delegation grantor no longer holds the role",
                            )
                        if delegation.role_id in active_delegation_roles:
                            issue(
                                "approval-delegation.active-conflict",
                                delegation_path,
                                f"Multiple active delegations exist for {delegation.role_id}",
                            )
                        active_delegation_roles.add(delegation.role_id)
                        if delegation.role_id in work.approval_roles:
                            issue(
                                "approval-delegation.active-after-approval",
                                delegation_path,
                                "Active Approval Delegation remains after role approval",
                            )
                    if delegation.status == "used":
                        authority = f"{delegation.to_actor} via approval-delegation:{delegation.id}"
                        approval_contents = (Path(work.path) / "approvals.md").read_text(
                            encoding="utf-8"
                        )
                        if (
                            delegation.role_id not in work.approval_roles
                            or authority not in approval_contents
                        ):
                            issue(
                                "approval-delegation.use-missing",
                                delegation_path,
                                "Used Approval Delegation has no matching approval row",
                            )
                    if delegation.status == "revoked" and (
                        grantor is not None and delegation.revoked_by != grantor.reference
                    ):
                        issue(
                            "approval-delegation.revoker-invalid",
                            delegation_path,
                            "Approval Delegation was not revoked by its grantor",
                        )
            if contract is not None:
                for state, limit in contract.wip_limits.items():
                    if state_counts.get(state, 0) > limit:
                        issue(
                            "swarm.wip-exceeded",
                            Path(swarm.path) / "SWARM.md",
                            f"State {state} has {state_counts[state]} work items; limit={limit}",
                        )
                swarm_work = [
                    item for (owner, _), item in work_records.items() if owner == swarm.id
                ]
                expected_status = self._derived_swarm_status(swarm, swarm_work, contract)
                if swarm.status != expected_status:
                    issue(
                        "swarm.status-derived-mismatch",
                        Path(swarm.path) / "SWARM.md",
                        f"Stored status {swarm.status} does not match derived status "
                        f"{expected_status}",
                    )

            for directory in _child_directories(Path(swarm.path) / "handoffs"):
                path = directory / "HANDOFF.md"
                handoff = inspect(
                    "handoffs",
                    "handoff.invalid",
                    path,
                    lambda swarm=swarm, path=path: self._load_handoff(swarm, path.parent.name),
                )
                if not isinstance(handoff, HandoffRecord):
                    continue
                if handoff.id != path.parent.name or handoff.swarm_id != swarm.id:
                    issue(
                        "handoff.identity-mismatch",
                        path,
                        "Handoff id or swarm does not match its filesystem owner",
                    )
                if handoff.role_id not in swarm.required_roles:
                    issue(
                        "handoff.role-invalid",
                        path,
                        f"Handoff uses unknown role: {handoff.role_id}",
                    )
                for reference in (
                    handoff.from_actor,
                    handoff.to_actor,
                    handoff.authorized_by,
                ):
                    resolve_actor(reference, path)
                if (
                    handoff.work_id is not None
                    and (
                        swarm.id,
                        handoff.work_id,
                    )
                    not in work_records
                ):
                    issue(
                        "handoff.work-missing",
                        path,
                        f"Handoff references missing work: {handoff.work_id}",
                    )

        for (swarm_id, work_id), work in work_records.items():
            path = Path(work.path) / "WORK.md"
            if len(work.child_work_refs) != len(set(work.child_work_refs)):
                issue(
                    "work.children-duplicated",
                    path,
                    "Child work references must be unique",
                )
            for reference in work.child_work_refs:
                owner, separator, child_id = reference.partition("/")
                child_key = (owner, child_id)
                if not separator or owner != swarm_id or child_key not in work_records:
                    issue(
                        "work.child-missing",
                        path,
                        f"Child work reference is not a local work item: {reference}",
                    )
                    continue
                child = work_records[child_key]
                if child_key == (swarm_id, work_id) or child.parent_work_ref != (
                    f"{swarm_id}/{work_id}"
                ):
                    issue(
                        "work.child-link-invalid",
                        Path(child.path) / "WORK.md",
                        f"Child work does not link back to {swarm_id}/{work_id}",
                    )
            if work.parent_work_ref is not None and work.delegation_id is None:
                owner, separator, parent_id = work.parent_work_ref.partition("/")
                parent = work_records.get((owner, parent_id)) if separator else None
                reference = f"{swarm_id}/{work_id}"
                if owner != swarm_id or parent is None or reference not in parent.child_work_refs:
                    issue(
                        "work.parent-link-invalid",
                        path,
                        f"Local parent work does not link to child {reference}",
                    )

        try:
            maximum = (
                project.max_delegation_depth if isinstance(project, ProjectConfiguration) else 3
            )
            self._validate_delegation_graph(self._delegation_graph(root), maximum)
        except Exception as error:
            issue("swarm.graph-invalid", swarm_root, str(error))

        delegation_records: dict[str, DelegationRecord] = {}
        for directory in _child_directories(root / ".agora" / "delegations"):
            path = directory / "DELEGATION.md"
            delegation = inspect(
                "delegations",
                "delegation.invalid",
                path,
                lambda path=path: self._load_delegation(root, path.parent.name),
            )
            if not isinstance(delegation, DelegationRecord):
                continue
            delegation_records[delegation.id] = delegation
            try:
                self._normalize_budget_limits(delegation.budget_limits)
                self._normalize_artifact_promotions(delegation.artifact_promotions)
            except ValueError as error:
                issue("delegation.contract-invalid", path, str(error))
            if delegation.id != path.parent.name:
                issue(
                    "delegation.id-mismatch",
                    path,
                    f"Delegation id {delegation.id} does not match directory {path.parent.name}",
                )
            parent_key = (delegation.parent_swarm_id, delegation.parent_work_id)
            child_key = (delegation.child_swarm_id, delegation.child_work_id)
            if delegation.parent_swarm_id not in swarms:
                issue(
                    "delegation.parent-swarm-missing",
                    path,
                    f"Parent swarm does not exist: {delegation.parent_swarm_id}",
                )
            if delegation.child_swarm_id not in swarms:
                issue(
                    "delegation.child-swarm-missing",
                    path,
                    f"Child swarm does not exist: {delegation.child_swarm_id}",
                )
            if parent_key not in work_records:
                issue(
                    "delegation.parent-work-missing",
                    path,
                    f"Parent work does not exist: {'/'.join(parent_key)}",
                )
            elif work_records[
                parent_key
            ].operational_status == "cancelled" and delegation.status in {
                "proposed",
                "accepted",
                "blocked",
            }:
                issue(
                    "delegation.parent-work-cancelled",
                    path,
                    "Open delegation belongs to cancelled parent work",
                )
            child_exists = child_key in work_records
            was_accepted = delegation.accepted_at is not None
            requires_child = delegation.status in {"accepted", "collected"} or (
                delegation.status == "blocked" and delegation.blocked_from == "accepted"
            )
            forbids_child = delegation.status in {"proposed", "rejected"} or (
                delegation.status == "blocked" and delegation.blocked_from == "proposed"
            )
            if forbids_child and child_exists:
                issue(
                    "delegation.child-work-premature",
                    path,
                    f"Unaccepted delegation already has child work: {'/'.join(child_key)}",
                )
            if requires_child and not child_exists:
                issue(
                    "delegation.child-work-missing",
                    path,
                    f"Accepted delegation has no child work: {'/'.join(child_key)}",
                )
            if (requires_child or was_accepted) and child_exists:
                child_work = work_records[child_key]
                child_document = read_markdown(Path(child_work.path) / "WORK.md")
                if optional_string_attribute(
                    child_document.attributes, "delegation"
                ) != delegation.id or optional_string_attribute(
                    child_document.attributes, "parent-work"
                ) != "/".join(parent_key):
                    issue(
                        "delegation.child-link-invalid",
                        Path(child_work.path) / "WORK.md",
                        "Child work does not link to its delegation and parent work",
                    )
                if child_work.budget_limits != delegation.budget_limits:
                    issue(
                        "delegation.child-budget-mismatch",
                        Path(child_work.path) / "WORK.md",
                        "Child work budget does not match its delegation",
                    )
            represented = resolve_actor(delegation.represented_by, path)
            resolve_actor(delegation.requested_by, path)
            acceptance_expected = delegation.status in {"accepted", "collected"} or (
                delegation.status == "blocked" and delegation.blocked_from == "accepted"
            )
            if acceptance_expected or was_accepted:
                if delegation.accepted_by is None or delegation.accepted_at is None:
                    issue(
                        "delegation.acceptance-missing",
                        path,
                        "Accepted delegation is missing acceptance attribution",
                    )
                else:
                    resolve_actor(delegation.accepted_by, path)
            if delegation.status == "blocked" and delegation.blocked_from not in {
                "proposed",
                "accepted",
            }:
                issue(
                    "delegation.blocked-from-invalid",
                    path,
                    "Blocked delegation must identify proposed or accepted as its prior state",
                )
            if delegation.status != "blocked" and delegation.blocked_from is not None:
                issue(
                    "delegation.blocked-from-stale",
                    path,
                    "Non-blocked delegation retains blocked-from metadata",
                )
            changes = inspect_status_changes(
                path.parent,
                subject_type="delegation",
                subject=delegation.id,
                statuses={
                    "proposed",
                    "accepted",
                    "blocked",
                    "collected",
                    "rejected",
                    "cancelled",
                },
                transitions={
                    ("proposed", "blocked"): "delegation.block",
                    ("proposed", "accepted"): "delegation.accept",
                    ("accepted", "blocked"): "delegation.block",
                    ("accepted", "collected"): "delegation.collect",
                    ("blocked", "proposed"): "delegation.resume",
                    ("blocked", "accepted"): "delegation.resume",
                    ("proposed", "rejected"): "delegation.reject",
                    ("proposed", "cancelled"): "delegation.cancel",
                    ("accepted", "cancelled"): "delegation.cancel",
                    ("blocked", "cancelled"): "delegation.cancel",
                },
            )
            if delegation.status in {"blocked", "rejected", "cancelled"} and (
                delegation.status_reason is None
                or delegation.status_by is None
                or delegation.status_at is None
            ):
                issue(
                    "delegation.status-attribution-missing",
                    path,
                    f"{delegation.status.title()} delegation lacks reason, actor, or timestamp",
                )
            if delegation.status_by is not None:
                resolve_actor(delegation.status_by, path)
            if changes and changes[-1].target_status != delegation.status:
                issue(
                    "delegation.status-history-stale",
                    path,
                    "Latest status change does not match delegation status",
                )
            if delegation.status in {"blocked", "rejected", "cancelled"} and not changes:
                issue(
                    "delegation.status-history-missing",
                    path,
                    f"{delegation.status.title()} delegation has no durable status change",
                )
            if delegation.status == "collected":
                if delegation.collected_by is None or delegation.collected_at is None:
                    issue(
                        "delegation.collection-missing",
                        path,
                        "Collected delegation is missing collection attribution",
                    )
                else:
                    resolve_actor(delegation.collected_by, path)
            if (
                represented is not None
                and represented.represented_swarm != delegation.child_swarm_id
            ):
                issue(
                    "delegation.actor-mismatch",
                    path,
                    f"Actor {represented.reference} does not represent {delegation.child_swarm_id}",
                )
            if delegation.status == "collected" and child_exists:
                child_swarm = swarms.get(delegation.child_swarm_id)
                child_work = work_records[child_key]
                child_contract = methods.get(child_swarm.method) if child_swarm else None
                if child_contract is None or child_work.state != child_contract.terminal_state:
                    issue(
                        "delegation.result-not-terminal",
                        path,
                        "Collected delegation does not reference terminal child work",
                    )
                parent_work = work_records.get(parent_key)
                result_uri = (
                    f"agora://swarms/{delegation.child_swarm_id}/work/{delegation.child_work_id}"
                )
                if parent_work is not None:
                    artifact_path = Path(parent_work.path) / "artifacts.md"
                    evidence_path = Path(parent_work.path) / "evidence.md"
                    if (
                        delegation.result_kind not in parent_work.artifact_kinds
                        or result_uri not in artifact_path.read_text(encoding="utf-8")
                    ):
                        issue(
                            "delegation.result-artifact-missing",
                            artifact_path,
                            "Collected result artifact is missing from parent work",
                        )
                    if (
                        "success" not in parent_work.evidence_results
                        or result_uri not in evidence_path.read_text(encoding="utf-8")
                    ):
                        issue(
                            "delegation.result-evidence-missing",
                            evidence_path,
                            "Collected result evidence is missing from parent work",
                        )
                    artifact_contents = artifact_path.read_text(encoding="utf-8")
                    for source_kind, parent_kind in delegation.artifact_promotions.items():
                        promotion_uri = f"{result_uri}/artifacts/{source_kind}"
                        if (
                            source_kind not in child_work.artifact_kinds
                            or parent_kind not in parent_work.artifact_kinds
                            or promotion_uri not in artifact_contents
                        ):
                            issue(
                                "delegation.promoted-artifact-missing",
                                artifact_path,
                                f"Promoted artifact is missing: {source_kind} -> {parent_kind}",
                            )

        allocated_budgets: dict[tuple[str, str], dict[str, int]] = {}
        for delegation in delegation_records.values():
            if delegation.status == "rejected":
                continue
            parent_key = (delegation.parent_swarm_id, delegation.parent_work_id)
            parent_work = work_records.get(parent_key)
            if parent_work is None or parent_work.budget_limits is None:
                continue
            allocated = allocated_budgets.setdefault(
                parent_key, {dimension: 0 for dimension in parent_work.budget_limits}
            )
            for dimension, limit in (delegation.budget_limits or {}).items():
                if dimension not in allocated:
                    issue(
                        "delegation.budget-dimension-unavailable",
                        Path(delegation.path),
                        f"Budget dimension is unavailable from parent work: {dimension}",
                    )
                    continue
                allocated[dimension] += limit
        for parent_key, allocated in allocated_budgets.items():
            parent = work_records[parent_key]
            assert parent.budget_limits is not None
            for dimension, total in allocated.items():
                if total > parent.budget_limits[dimension]:
                    issue(
                        "delegation.budget-exceeded",
                        Path(parent.path) / "WORK.md",
                        f"Delegated {dimension} budget {total} exceeds "
                        f"parent limit {parent.budget_limits[dimension]}",
                    )

        for directory in _child_directories(root / ".agora" / "sessions"):
            path = directory / "SESSION.md"
            session = inspect(
                "sessions",
                "session.invalid",
                path,
                lambda path=path: self._load_session(path.parent),
            )
            if not isinstance(session, SessionRecord):
                continue
            if session.id != path.parent.name:
                issue(
                    "session.id-mismatch",
                    path,
                    f"Session id {session.id} does not match directory {path.parent.name}",
                )
            session_actor = resolve_actor(session.actor, path)
            if (
                session_actor is not None
                and session_actor.authentication_required
                and session.preparation_action_id is None
            ):
                issue(
                    "session.preparation-authentication-missing",
                    path,
                    f"Actor {session.actor} requires signed session preparation",
                )
            if (
                session_actor is not None
                and session.status in {"running", "completed", "failed"}
                and session_actor.authentication_required
                and not session.authentication_verified
            ):
                issue(
                    "session.authentication-missing",
                    path,
                    f"Actor {session.actor} requires authentication for launched sessions",
                )
            swarm = swarms.get(session.swarm_id)
            if swarm is None:
                issue(
                    "session.swarm-missing",
                    path,
                    f"Session references missing swarm: {session.swarm_id}",
                )
            else:
                contract = methods.get(swarm.method)
                unknown_roles = (
                    sorted(set(session.roles) - set(contract.required_roles))
                    if contract is not None
                    else []
                )
                if unknown_roles:
                    issue(
                        "session.roles-invalid",
                        path,
                        f"Session records unknown roles: {', '.join(unknown_roles)}",
                    )
            if (
                session.work_id is not None
                and (
                    session.swarm_id,
                    session.work_id,
                )
                not in work_records
            ):
                issue(
                    "session.work-missing",
                    path,
                    f"Session references missing work: {session.work_id}",
                )
            if not (path.parent / "CONTEXT.md").is_file():
                issue("session.context-missing", path, "Session CONTEXT.md is missing")
            elif session.context_sha256 is not None:
                try:
                    self._assert_session_context(session)
                except (FileNotFoundError, ValueError) as error:
                    issue("session.context-invalid", path, str(error))
            result_path = path.parent / "RESULT.md"
            if result_path.is_file():
                inspect(
                    "session-results",
                    "session.result-invalid",
                    result_path,
                    lambda session=session: self._validate_session_result(session),
                )

        for directory in _child_directories(root / ".agora" / "actions"):
            path = directory / "ACTION.md"
            action = inspect(
                "lifecycle-actions",
                "lifecycle-action.invalid",
                path,
                lambda path=path: self._load_lifecycle_action(path.parent),
            )
            if not isinstance(action, LifecycleActionRecord):
                continue
            if action.id != path.parent.name:
                issue(
                    "lifecycle-action.id-mismatch",
                    path,
                    f"Lifecycle Action id {action.id} does not match directory {path.parent.name}",
                )
            action_actor = resolve_actor(action.actor, path)
            if (
                action_actor is not None
                and action.status == "applied"
                and action_actor.authentication_required
                and not action.authentication_verified
            ):
                issue(
                    "lifecycle-action.authentication-missing",
                    path,
                    f"Actor {action.actor} requires authentication for applied actions",
                )
            if action.swarm_id not in swarms:
                issue(
                    "lifecycle-action.swarm-missing",
                    path,
                    f"Lifecycle Action references missing swarm: {action.swarm_id}",
                )
            if (
                action.work_id is not None
                and (action.swarm_id, action.work_id) not in work_records
                and not (action.action == "work.create" and action.status == "prepared")
            ):
                issue(
                    "lifecycle-action.work-missing",
                    path,
                    f"Lifecycle Action references missing work: {action.work_id}",
                )
            elif action.status == "prepared":
                try:
                    self._assert_lifecycle_precondition(root, action)
                except (FileNotFoundError, ValueError) as error:
                    issue(
                        "lifecycle-action.precondition-stale",
                        path,
                        str(error),
                        "warning",
                    )
            if action.action == "work.create" and action.work_id is not None:
                work_key = (action.swarm_id, action.work_id)
                if action.status == "prepared" and work_key in work_records:
                    issue(
                        "lifecycle-action.work-conflict",
                        path,
                        f"Prepared action already has a work record: {action.work_id}",
                    )
                elif action.status == "applied" and work_key in work_records:
                    work = work_records[work_key]
                    try:
                        creation = self._work_creation_input_from_action(action)
                    except ValueError as error:
                        issue("lifecycle-action.work-invalid", path, str(error))
                    else:
                        expected = (
                            creation.title,
                            creation.description or "No description provided.",
                            dict(creation.acceptance_criteria),
                            list(dict.fromkeys(creation.required_artifacts)),
                        )
                        actual = (
                            work.title,
                            work.description,
                            work.acceptance_criteria,
                            work.required_artifacts,
                        )
                        if actual != expected:
                            issue(
                                "lifecycle-action.work-mismatch",
                                Path(work.path) / "WORK.md",
                                "Work record differs from its applied Lifecycle Action",
                            )
            if action.action == "work.decompose" and action.work_id is not None:
                try:
                    decomposition = self._work_decomposition_input_from_action(action)
                except ValueError as error:
                    issue("lifecycle-action.decomposition-invalid", path, str(error))
                else:
                    child_key = (action.swarm_id, decomposition.child_work_id)
                    child = work_records.get(child_key)
                    if action.status == "prepared" and child is not None:
                        issue(
                            "lifecycle-action.work-conflict",
                            path,
                            "Prepared action already has child work: "
                            f"{decomposition.child_work_id}",
                        )
                    elif action.status == "applied" and child is None:
                        issue(
                            "lifecycle-action.child-work-missing",
                            path,
                            "Applied decomposition has no child work: "
                            f"{decomposition.child_work_id}",
                        )
                    elif action.status == "applied" and child is not None:
                        parent = work_records.get((action.swarm_id, action.work_id))
                        expected = (
                            decomposition.title,
                            decomposition.description or "No description provided.",
                            dict(decomposition.acceptance_criteria),
                            list(dict.fromkeys(decomposition.required_artifacts)),
                            f"{action.swarm_id}/{action.work_id}",
                        )
                        actual = (
                            child.title,
                            child.description,
                            child.acceptance_criteria,
                            child.required_artifacts,
                            child.parent_work_ref,
                        )
                        child_reference = f"{action.swarm_id}/{decomposition.child_work_id}"
                        if actual != expected or (
                            parent is not None and child_reference not in parent.child_work_refs
                        ):
                            issue(
                                "lifecycle-action.decomposition-mismatch",
                                Path(child.path) / "WORK.md",
                                "Child work differs from its applied Lifecycle Action",
                            )
            if action.action == "gate.waive" and action.work_id is not None:
                try:
                    waiver_input = self._gate_waiver_input_from_action(action)
                except ValueError as error:
                    issue("lifecycle-action.gate-waiver-invalid", path, str(error))
                else:
                    waiver_key = (action.swarm_id, action.work_id, waiver_input.id)
                    waiver = gate_waiver_records.get(waiver_key)
                    if action.status == "prepared" and waiver is not None:
                        issue(
                            "lifecycle-action.gate-waiver-conflict",
                            path,
                            f"Prepared action already has a Gate Waiver: {waiver_input.id}",
                        )
                    elif action.status == "applied" and waiver is None:
                        issue(
                            "lifecycle-action.gate-waiver-missing",
                            path,
                            f"Applied action has no Gate Waiver: {waiver_input.id}",
                        )
                    elif action.status == "applied" and waiver is not None:
                        expected = (
                            action.id,
                            action.actor,
                            waiver_input.gate_id,
                            waiver_input.criteria,
                            waiver_input.artifacts,
                            waiver_input.successful_evidence,
                            waiver_input.approval_roles,
                            waiver_input.reason,
                            waiver_input.evidence_refs,
                        )
                        actual = (
                            waiver.action_id,
                            waiver.authorized_by,
                            waiver.gate_id,
                            waiver.waived_criteria,
                            waiver.waived_artifacts,
                            waiver.waive_successful_evidence,
                            waiver.waived_approval_roles,
                            waiver.reason,
                            waiver.evidence_refs,
                        )
                        if actual != expected:
                            issue(
                                "lifecycle-action.gate-waiver-mismatch",
                                Path(waiver.path),
                                "Gate Waiver differs from its applied Lifecycle Action",
                            )
            if action.action == "approval.delegate" and action.work_id is not None:
                delegation_key = (
                    action.swarm_id,
                    action.work_id,
                    action.parameters["delegation"],
                )
                approval_delegation = approval_delegation_records.get(delegation_key)
                if action.status == "prepared" and approval_delegation is not None:
                    issue(
                        "lifecycle-action.approval-delegation-conflict",
                        path,
                        "Prepared action already has an Approval Delegation record",
                    )
                elif action.status == "applied" and approval_delegation is None:
                    issue(
                        "lifecycle-action.approval-delegation-missing",
                        path,
                        "Applied action has no Approval Delegation record",
                    )
                elif action.status == "applied" and approval_delegation is not None:
                    expected = (
                        action.id,
                        action.swarm_id,
                        action.work_id,
                        action.parameters["role"],
                        action.actor,
                        action.parameters["target"],
                        action.parameters["reason"],
                    )
                    actual = (
                        approval_delegation.action_id,
                        approval_delegation.swarm_id,
                        approval_delegation.work_id,
                        approval_delegation.role_id,
                        approval_delegation.from_actor,
                        approval_delegation.to_actor,
                        approval_delegation.reason,
                    )
                    if actual != expected:
                        issue(
                            "lifecycle-action.approval-delegation-mismatch",
                            Path(approval_delegation.path),
                            "Approval Delegation differs from its applied Lifecycle Action",
                        )
            if action.action == "approval.delegation.revoke" and action.work_id is not None:
                delegation_key = (
                    action.swarm_id,
                    action.work_id,
                    action.parameters["delegation"],
                )
                approval_delegation = approval_delegation_records.get(delegation_key)
                if approval_delegation is None:
                    issue(
                        "lifecycle-action.approval-delegation-missing",
                        path,
                        "Revocation action references a missing Approval Delegation",
                    )
                elif action.status == "applied" and (
                    approval_delegation.status != "revoked"
                    or approval_delegation.revoked_by != action.actor
                    or approval_delegation.revoked_reason != action.parameters["reason"]
                    or approval_delegation.revocation_action_id != action.id
                ):
                    issue(
                        "lifecycle-action.approval-delegation-revocation-mismatch",
                        Path(approval_delegation.path),
                        "Approval Delegation revocation differs from its Lifecycle Action",
                    )
            if (
                action.action == "approval.add"
                and action.status == "applied"
                and action.work_id is not None
                and (action.swarm_id, action.work_id) in work_records
            ):
                approved_work = work_records[(action.swarm_id, action.work_id)]
                delegation_id = action.parameters.get("delegation")
                authority = action.actor
                if delegation_id:
                    approval_delegation = approval_delegation_records.get(
                        (action.swarm_id, action.work_id, delegation_id)
                    )
                    if approval_delegation is None or (
                        approval_delegation.status != "used"
                        or approval_delegation.used_action_id != action.id
                        or approval_delegation.used_by != action.actor
                    ):
                        issue(
                            "lifecycle-action.approval-delegation-use-mismatch",
                            path,
                            "Applied approval did not consume its bound Approval Delegation",
                        )
                    authority = f"{action.actor} via approval-delegation:{delegation_id}"
                note = action.parameters["note"].replace("|", "\\|") or "Approved"
                approval_line = f"| {action.parameters['role']} | {authority} | {note} |"
                if approval_line not in (Path(approved_work.path) / "approvals.md").read_text(
                    encoding="utf-8"
                ):
                    issue(
                        "lifecycle-action.approval-mismatch",
                        Path(approved_work.path) / "approvals.md",
                        "Approval row is missing from its applied Lifecycle Action",
                    )
            if action.action in {"actor.key.recover", "actor.key.rotate"}:
                target_reference = action.parameters.get("target", action.actor)
                target_actor = resolve_actor(target_reference, path)
                if target_actor is None:
                    continue
                key_root = self._actor_key_root(target_actor)
                replacement_path = key_root / f"{action.parameters['fingerprint']}.md"
                previous_path = key_root / f"{action.parameters['from']}.md"
                if action.status == "prepared" and replacement_path.exists():
                    issue(
                        "lifecycle-action.actor-key-conflict",
                        path,
                        "Prepared action replacement key already exists",
                    )
                elif action.status == "applied":
                    try:
                        replacement = load_actor_key(replacement_path)
                        previous = load_actor_key(previous_path)
                    except (FileNotFoundError, ValueError) as error:
                        issue("lifecycle-action.actor-key-invalid", path, str(error))
                    else:
                        if (
                            replacement.actor != target_reference
                            or replacement.public_key != action.parameters["public-key"]
                            or replacement.fingerprint != action.parameters["fingerprint"]
                            or previous.replaced_by != replacement.fingerprint
                            or (
                                action.action == "actor.key.rotate"
                                and previous.reason != action.parameters["reason"]
                            )
                        ):
                            issue(
                                "lifecycle-action.actor-key-mismatch",
                                replacement_path,
                                "Actor key history differs from its applied Lifecycle Action",
                            )
            if action.action == "actor.key.revoke":
                target_actor = resolve_actor(action.parameters["target"], path)
                if target_actor is None:
                    continue
                key_path = (
                    self._actor_key_root(target_actor) / f"{action.parameters['fingerprint']}.md"
                )
                if action.status == "applied":
                    try:
                        revoked = load_actor_key(key_path)
                    except (FileNotFoundError, ValueError) as error:
                        issue("lifecycle-action.actor-key-invalid", path, str(error))
                    else:
                        if (
                            revoked.actor != action.parameters["target"]
                            or revoked.status != "revoked"
                            or revoked.reason != action.parameters["reason"]
                        ):
                            issue(
                                "lifecycle-action.actor-key-mismatch",
                                key_path,
                                "Actor key history differs from its applied Lifecycle Action",
                            )
            if action.action == "session.prepare":
                session_id = action.parameters["session"]
                session_path = root / ".agora" / "sessions" / session_id
                if action.status == "prepared" and session_path.exists():
                    issue(
                        "lifecycle-action.session-conflict",
                        path,
                        f"Prepared action already has a Session record: {session_id}",
                    )
                elif action.status == "applied" and not (session_path / "SESSION.md").is_file():
                    issue(
                        "lifecycle-action.session-missing",
                        path,
                        f"Applied action has no Session record: {session_id}",
                    )
                elif action.status == "applied":
                    try:
                        session = self._load_session(session_path)
                    except (FileNotFoundError, ValueError) as error:
                        issue("lifecycle-action.session-invalid", session_path, str(error))
                    else:
                        expected = (
                            action.id,
                            action.actor,
                            action.swarm_id,
                            action.work_id,
                            action.precondition_sha256,
                        )
                        actual = (
                            session.preparation_action_id,
                            session.actor,
                            session.swarm_id,
                            session.work_id,
                            session.context_sha256,
                        )
                        if actual != expected:
                            issue(
                                "lifecycle-action.session-mismatch",
                                session_path / "SESSION.md",
                                "Session record differs from its applied Lifecycle Action",
                            )
            if (
                action.status == "applied"
                and action.action in {"artifact.add", "criterion.satisfy", "evidence.add"}
                and action.work_id is not None
                and (action.swarm_id, action.work_id) in work_records
            ):
                work = work_records[(action.swarm_id, action.work_id)]
                if action.action == "criterion.satisfy":
                    if action.parameters["criterion"] not in work.satisfied_criteria:
                        issue(
                            "lifecycle-action.criterion-mismatch",
                            Path(work.path) / "WORK.md",
                            "Satisfied criterion is missing from its applied Lifecycle Action",
                        )
                elif action.action == "artifact.add":
                    artifact_line = (
                        f"| {action.parameters['kind']} | {action.parameters['uri']} | "
                        f"{action.actor} |"
                    )
                    artifact_path = Path(work.path) / "artifacts.md"
                    if artifact_line not in artifact_path.read_text(encoding="utf-8"):
                        issue(
                            "lifecycle-action.artifact-mismatch",
                            artifact_path,
                            "Artifact row is missing from its applied Lifecycle Action",
                        )
                else:
                    references = (
                        ", ".join(self._string_list_parameter(action, "artifacts")) or "none"
                    )
                    evidence_line = (
                        f"| {action.parameters['type']} | {action.parameters['result']} | "
                        f"{references} | {action.actor} |"
                    )
                    evidence_path = Path(work.path) / "evidence.md"
                    if evidence_line not in evidence_path.read_text(encoding="utf-8"):
                        issue(
                            "lifecycle-action.evidence-mismatch",
                            evidence_path,
                            "Evidence row is missing from its applied Lifecycle Action",
                        )
            if action.action == "usage.add" and action.work_id is not None:
                usage_key = (
                    action.swarm_id,
                    action.work_id,
                    action.parameters["usage"],
                )
                usage = usage_records.get(usage_key)
                if action.status == "prepared" and usage is not None:
                    issue(
                        "lifecycle-action.usage-conflict",
                        path,
                        "Prepared usage action already has a Usage record",
                    )
                elif action.status == "applied" and usage is None:
                    issue(
                        "lifecycle-action.usage-missing",
                        path,
                        "Applied usage action has no Usage record",
                    )
                elif action.status == "applied" and usage is not None:
                    expected_amounts = self._usage_amounts_parameter(action)
                    expected_evidence = self._string_list_parameter(action, "evidence")
                    if (
                        usage.actor != action.actor
                        or usage.amounts != expected_amounts
                        or usage.evidence_refs != expected_evidence
                        or usage.action_id != action.id
                    ):
                        issue(
                            "lifecycle-action.usage-mismatch",
                            Path(usage.path),
                            "Usage record differs from its applied Lifecycle Action",
                        )
            if action.action == "handoff.create" and action.swarm_id in swarms:
                swarm = swarms[action.swarm_id]
                handoff_path = Path(swarm.path) / "handoffs" / action.id / "HANDOFF.md"
                if action.status == "prepared" and handoff_path.exists():
                    issue(
                        "lifecycle-action.handoff-conflict",
                        path,
                        f"Prepared action already has a handoff record: {action.id}",
                    )
                elif action.status == "applied" and not handoff_path.is_file():
                    issue(
                        "lifecycle-action.handoff-missing",
                        path,
                        f"Applied action has no handoff record: {action.id}",
                    )
                elif action.status == "applied":
                    try:
                        handoff = self._load_handoff(swarm, action.id)
                    except (FileNotFoundError, ValueError) as error:
                        issue("lifecycle-action.handoff-invalid", handoff_path, str(error))
                    else:
                        expected = (
                            action.parameters["role"],
                            action.parameters["from"],
                            action.parameters["to"],
                            action.actor,
                            action.parameters["reason"],
                            action.work_id,
                        )
                        actual = (
                            handoff.role_id,
                            handoff.from_actor,
                            handoff.to_actor,
                            handoff.authorized_by,
                            handoff.reason,
                            handoff.work_id,
                        )
                        if actual != expected:
                            issue(
                                "lifecycle-action.handoff-mismatch",
                                handoff_path,
                                "Handoff record differs from its applied Lifecycle Action",
                            )
            if (
                action.action in {"work.block", "work.cancel", "work.resume"}
                and (
                    action.swarm_id,
                    action.work_id,
                )
                in work_records
            ):
                work = work_records[(action.swarm_id, action.work_id)]
                status_path = Path(work.path) / "status-changes" / action.id / "STATUS.md"
                if action.status == "prepared" and status_path.exists():
                    issue(
                        "lifecycle-action.status-change-conflict",
                        path,
                        f"Prepared action already has a Status Change: {action.id}",
                    )
                elif action.status == "applied" and not status_path.is_file():
                    issue(
                        "lifecycle-action.status-change-missing",
                        path,
                        f"Applied action has no Status Change: {action.id}",
                    )
                elif action.status == "applied":
                    try:
                        change = self._load_status_change(status_path.parent)
                    except (FileNotFoundError, ValueError) as error:
                        issue("lifecycle-action.status-change-invalid", status_path, str(error))
                    else:
                        target_status = {
                            "work.block": "blocked",
                            "work.cancel": "cancelled",
                            "work.resume": "active",
                        }[action.action]
                        expected = (
                            "work",
                            f"{action.swarm_id}/{action.work_id}",
                            action.action,
                            target_status,
                            action.actor,
                            action.parameters["reason"],
                        )
                        actual = (
                            change.subject_type,
                            change.subject,
                            change.action,
                            change.target_status,
                            change.actor,
                            change.reason,
                        )
                        if actual != expected:
                            issue(
                                "lifecycle-action.status-change-mismatch",
                                status_path,
                                "Status Change differs from its applied Lifecycle Action",
                            )
            if action.action == "delegation.create":
                delegation_id = action.parameters["delegation"]
                delegation_path = root / ".agora" / "delegations" / delegation_id / "DELEGATION.md"
                if action.status == "prepared" and delegation_path.exists():
                    issue(
                        "lifecycle-action.delegation-conflict",
                        path,
                        f"Prepared action already has a delegation record: {delegation_id}",
                    )
                elif action.status == "applied" and not delegation_path.is_file():
                    issue(
                        "lifecycle-action.delegation-missing",
                        path,
                        f"Applied action has no delegation record: {delegation_id}",
                    )
                elif action.status == "applied":
                    try:
                        delegation = self._load_delegation(root, delegation_id)
                        creation = self._delegation_creation_input_from_action(action)
                        child_actor = self._find_actor(root, creation.child_actor_id)
                    except (FileNotFoundError, ValueError) as error:
                        issue("lifecycle-action.delegation-invalid", delegation_path, str(error))
                    else:
                        expected = (
                            action.swarm_id,
                            action.work_id,
                            child_actor.represented_swarm,
                            creation.child_work_id,
                            child_actor.reference,
                            action.actor,
                            creation.title,
                            creation.description or "No description provided.",
                            dict(creation.acceptance_criteria),
                            list(dict.fromkeys(creation.required_artifacts)),
                            creation.result_kind,
                            creation.budget_limits,
                            creation.artifact_promotions,
                        )
                        actual = (
                            delegation.parent_swarm_id,
                            delegation.parent_work_id,
                            delegation.child_swarm_id,
                            delegation.child_work_id,
                            delegation.represented_by,
                            delegation.requested_by,
                            delegation.title,
                            delegation.description,
                            delegation.acceptance_criteria,
                            delegation.required_artifacts,
                            delegation.result_kind,
                            delegation.budget_limits,
                            delegation.artifact_promotions,
                        )
                        if actual != expected:
                            issue(
                                "lifecycle-action.delegation-mismatch",
                                delegation_path,
                                "Delegation record differs from its applied Lifecycle Action",
                            )
            if action.action in {
                "delegation.accept",
                "delegation.block",
                "delegation.cancel",
                "delegation.collect",
                "delegation.reject",
                "delegation.resume",
            }:
                delegation_id = action.parameters["delegation"]
                delegation_path = root / ".agora" / "delegations" / delegation_id / "DELEGATION.md"
                if not delegation_path.is_file():
                    issue(
                        "lifecycle-action.delegation-missing",
                        path,
                        f"Lifecycle Action references missing delegation: {delegation_id}",
                    )
                    continue
                try:
                    delegation = self._load_delegation(root, delegation_id)
                except (FileNotFoundError, ValueError) as error:
                    issue("lifecycle-action.delegation-invalid", delegation_path, str(error))
                    continue
                if (
                    action.swarm_id != delegation.parent_swarm_id
                    or action.work_id != delegation.parent_work_id
                ):
                    issue(
                        "lifecycle-action.delegation-context-mismatch",
                        path,
                        "Lifecycle Action does not use the delegation parent context",
                    )
                status_path = delegation_path.parent / "status-changes" / action.id / "STATUS.md"
                if action.status == "prepared" and status_path.exists():
                    issue(
                        "lifecycle-action.status-change-conflict",
                        path,
                        f"Prepared action already has a Status Change: {action.id}",
                    )
                elif action.status == "applied" and not status_path.is_file():
                    issue(
                        "lifecycle-action.status-change-missing",
                        path,
                        f"Applied action has no Status Change: {action.id}",
                    )
                elif action.status == "applied":
                    try:
                        change = self._load_status_change(status_path.parent)
                    except (FileNotFoundError, ValueError) as error:
                        issue("lifecycle-action.status-change-invalid", status_path, str(error))
                    else:
                        expected_targets = {
                            "delegation.accept": {"accepted"},
                            "delegation.block": {"blocked"},
                            "delegation.cancel": {"cancelled"},
                            "delegation.collect": {"collected"},
                            "delegation.reject": {"rejected"},
                            "delegation.resume": {"proposed", "accepted"},
                        }[action.action]
                        expected_reason = {
                            "delegation.accept": "Delegated work accepted by the child swarm",
                            "delegation.collect": (
                                "Completed child result collected into parent work"
                            ),
                        }.get(action.action, action.parameters.get("reason"))
                        matches = (
                            change.subject_type == "delegation"
                            and change.subject == delegation.id
                            and change.action == action.action
                            and change.target_status in expected_targets
                            and change.actor == action.actor
                            and change.reason == expected_reason
                        )
                        if not matches:
                            issue(
                                "lifecycle-action.status-change-mismatch",
                                status_path,
                                "Status Change differs from its applied Lifecycle Action",
                            )

        for directory in _child_directories(root / ".agora" / "tool-runs"):
            path = directory / "RUN.md"
            run = inspect(
                "tool-runs",
                "tool-run.invalid",
                path,
                lambda path=path: self._load_tool_run(path.parent),
            )
            if not isinstance(run, ToolRunRecord):
                continue
            if run.id != path.parent.name:
                issue(
                    "tool-run.id-mismatch",
                    path,
                    f"Tool run id {run.id} does not match directory {path.parent.name}",
                )
            contract = tools.get(run.tool_id)
            operation = contract.operations.get(run.operation_id) if contract else None
            if operation is None:
                issue(
                    "tool-run.operation-missing",
                    path,
                    f"Tool operation is not installed: {run.tool_id}/{run.operation_id}",
                )
            elif (
                operation.capability != run.capability
                or operation.risk != run.risk
                or operation.result_kind != run.result_kind
                or contract.timeout_seconds != run.timeout_seconds
                or contract.max_output_bytes != run.max_output_bytes
            ):
                issue(
                    "tool-run.contract-mismatch",
                    path,
                    "Tool run policy differs from its installed Tool Pack operation",
                )
            if run.environment_id is not None and run.environment_id not in environments:
                issue(
                    "tool-run.environment-missing",
                    path,
                    f"Tool run references missing environment: {run.environment_id}",
                )
            if (
                operation is not None
                and operation.environment_required
                and run.environment_id is None
            ):
                issue(
                    "tool-run.environment-required",
                    path,
                    f"Tool operation {run.tool_id}/{run.operation_id} requires an environment",
                )
            run_actor = resolve_actor(run.actor, path)
            if (
                run_actor is not None
                and run.status in {"running", "completed", "failed"}
                and run_actor.authentication_required
                and not run.authentication_verified
            ):
                issue(
                    "tool-run.authentication-missing",
                    path,
                    f"Actor {run.actor} requires authentication for launched Tool Runs",
                )
            if run.swarm_id not in swarms:
                issue(
                    "tool-run.swarm-missing",
                    path,
                    f"Tool run references missing swarm: {run.swarm_id}",
                )
            if run.work_id is not None and (run.swarm_id, run.work_id) not in work_records:
                issue(
                    "tool-run.work-missing",
                    path,
                    f"Tool run references missing work: {run.work_id}",
                )
            if (
                run.status in {"prepared", "running"}
                and operation is not None
                and run.swarm_id in swarms
                and (run.environment_id is None or run.environment_id in environments)
            ):
                run_swarm = swarms[run.swarm_id]
                run_work = (
                    work_records.get((run.swarm_id, run.work_id))
                    if run.work_id is not None
                    else None
                )
                try:
                    self._assert_environment_permission(
                        root,
                        run_swarm,
                        self._actor_roles(run_swarm, run.actor),
                        operation.capability,
                        run.environment_id,
                        operation.environment_required,
                        run_work,
                    )
                except (FileNotFoundError, PermissionError, ValueError) as error:
                    issue("tool-run.environment-policy", path, str(error))
            result_path = path.parent / "RESULT.md"
            if run.status in {"completed", "failed"}:
                inspect(
                    "documents",
                    "tool-result.invalid",
                    result_path,
                    lambda result_path=result_path: _assert_schema(
                        read_markdown(result_path), "agora/tool-result/v1", result_path
                    ),
                )

        event_sources = [("project", root / ".agora" / "events.md")]
        event_sources.extend(
            (f"swarm:{swarm.id}", Path(swarm.path) / "events.md") for swarm in swarms.values()
        )
        event_sources.extend(
            (f"work:{swarm_id}/{work_id}", Path(work.path) / "events.md")
            for (swarm_id, work_id), work in work_records.items()
        )
        for scope, path in event_sources:
            inspect(
                "event-files",
                "events.invalid",
                path,
                lambda path=path, scope=scope: self._read_events(path, scope),
            )

        ordered = sorted(
            issues,
            key=lambda item: (item.severity != "error", item.path, item.code, item.message),
        )
        return ValidationReport(
            ok=not any(item.severity == "error" for item in ordered),
            project=root.name,
            checked=checked,
            issues=ordered,
        )

    def doctor(self) -> list[DoctorCheck]:
        root = self.project_root()
        configuration = self._load_project_configuration(root)
        agora = root / ".agora"
        command_ids = sorted(path.stem for path in (agora / "commands").glob("*.md"))
        integration_paths = [
            self._integration_command_path(root, configuration.integration, command_id)
            for command_id in command_ids
        ]
        available_integrations = sum(path.is_file() for path in integration_paths)
        git_enabled = is_git_repository(root)
        runtime_command = self._runtime_command(
            configuration.integration,
            None,
            configuration.model,
        )
        if runtime_command:
            runtime_path = shutil.which(runtime_command[0])
            runtime_check = DoctorCheck(
                "runtime",
                runtime_path is not None,
                runtime_path or f"{runtime_command[0]} not found on PATH",
            )
        else:
            runtime_check = DoctorCheck(
                "runtime",
                True,
                "generic integration: provide a structured --runner when launching",
            )
        return [
            DoctorCheck("project", True, str(root)),
            DoctorCheck(
                "constitution",
                (agora / "constitution.md").exists(),
                str(agora / "constitution.md"),
            ),
            DoctorCheck(
                "method",
                (agora / "methods" / configuration.default_method / "METHOD.md").exists(),
                configuration.default_method,
            ),
            DoctorCheck(
                "integration",
                bool(integration_paths) and available_integrations == len(integration_paths),
                f"{configuration.integration}: {available_integrations}/{len(integration_paths)} "
                "commands available",
            ),
            runtime_check,
            DoctorCheck(
                "tool-policy",
                (agora / "tools" / "TOOLS.md").exists(),
                str(agora / "tools" / "TOOLS.md"),
            ),
            DoctorCheck(
                "repository-tool",
                (agora / "tools" / "repository" / "TOOL.md").exists(),
                str(agora / "tools" / "repository" / "TOOL.md"),
            ),
            DoctorCheck(
                "delegation-depth",
                True,
                f"maximum={configuration.max_delegation_depth}",
            ),
            DoctorCheck(
                "git",
                git_enabled,
                current_branch(root) if git_enabled else "filesystem-only mode",
            ),
        ]

    def lock_status(self, scope: str = "project") -> WorkspaceLockStatus:
        if scope == "user":
            return inspect_workspace_lock(agora_home())
        if scope == "project":
            return inspect_workspace_lock(self.project_root())
        raise ValueError(f"Unsupported lock scope: {scope}")

    def _mutation_resources(
        self,
        scope: str,
        args: tuple[object, ...],
        kwargs: dict[str, object],
    ) -> tuple[Path, ...]:
        data = args[0] if args else kwargs.get("data")
        if scope == "project":
            return (self.project_root(),)
        if scope == "home":
            return (agora_home(),)
        if scope == "target":
            target = getattr(data, "target", None)
            return (agora_home(), (self.cwd / (target or ".")).resolve())
        if scope == "scoped":
            resource = (
                agora_home() if getattr(data, "scope", None) == "user" else self.project_root()
            )
            return (resource,)
        if scope == "actor-runtime":
            root = self.project_root()
            actor_id = getattr(data, "actor_id", None)
            actor = self._find_actor(root, str(actor_id))
            return (agora_home() if actor.reference.startswith("user:") else root,)
        if scope == "lifecycle-action":
            root = self.project_root()
            action_id = getattr(data, "action_id", None)
            action = self._load_lifecycle_action(root / ".agora" / "actions" / str(action_id))
            if action.action in {
                "actor.key.recover",
                "actor.key.revoke",
                "actor.key.rotate",
                "actor.runtime.update",
            }:
                target = action.parameters.get("target", action.actor)
                if target.startswith("user:"):
                    return (root, agora_home())
            return (root,)
        if scope in {"registry-update", "pack-update"}:
            requested_scope = getattr(data, "scope", None)
            if requested_scope == "user":
                return (agora_home(),)
            if requested_scope == "project":
                return (self.project_root(),)
            project = self._optional_project_root()
            return (agora_home(),) if project is None else (agora_home(), project)
        raise ValueError(f"Unsupported mutation lock scope: {scope}")

    @contextmanager
    def _mutation_lock(self, resources: tuple[Path, ...], operation: str) -> Iterator[None]:
        resolved = tuple(sorted({item.resolve() for item in resources}, key=str))
        if self._lock_depth:
            if self._lock_resources != resolved:
                raise RuntimeError(
                    f"Nested mutation attempted to lock {', '.join(map(str, resolved))} while "
                    f"holding {', '.join(map(str, self._lock_resources))}"
                )
            self._lock_depth += 1
            try:
                yield
            finally:
                self._lock_depth -= 1
            return

        with ExitStack() as stack:
            for resource in resolved:
                stack.enter_context(
                    WorkspaceLock(
                        resource,
                        operation,
                        timeout=self.lock_timeout,
                        now=self._now(),
                    )
                )
            for resource in resolved:
                coordination_path = resource / ".agora" / "coordination.md"
                if not coordination_path.is_file():
                    continue
                policy = load_coordination_policy(coordination_path)
                if policy.mode == "external-lease":
                    stack.enter_context(
                        ExternalLease(
                            policy,
                            operation,
                            resource,
                            runner=self._lease_runner,
                        )
                    )
            self._lock_resources = resolved
            self._lock_depth = 1
            try:
                yield
            finally:
                self._lock_depth = 0
                self._lock_resources = ()

    def project_root(self) -> Path:
        return find_project_root(self.cwd)

    def _optional_project_root(self) -> Path | None:
        try:
            return self.project_root()
        except FileNotFoundError:
            return None

    @staticmethod
    def _registries_at(root: Path, scope: str) -> list[RegistryRecord]:
        return [load_registry(directory, scope) for directory in _child_directories(root)]

    def _installed_registry_for_update(
        self, registry_id: str, scope: str | None
    ) -> tuple[RegistryRecord, str]:
        if scope not in {None, "user", "project"}:
            raise ValueError(f"Unsupported registry scope: {scope}")
        candidates: list[tuple[Path, str]] = []
        project = self._optional_project_root()
        if scope in {None, "project"}:
            if project is None:
                if scope == "project":
                    self.project_root()
            else:
                candidates.append((project / ".agora" / "registries" / registry_id, "project"))
        if scope in {None, "user"}:
            candidates.append((agora_home() / "registries" / registry_id, "user"))
        for path, candidate_scope in candidates:
            if path.is_dir():
                return load_registry(path, candidate_scope), candidate_scope
        qualifier = f" in {scope} scope" if scope else ""
        raise FileNotFoundError(f"Installed registry not found: {registry_id}{qualifier}")

    @staticmethod
    def _trust_keys_at(root: Path, scope: str) -> list[RegistryTrustKeyRecord]:
        if not root.exists():
            return []
        return [load_trust_key(path, scope) for path in sorted(root.glob("*.md"))]

    @staticmethod
    def _transparency_keys_at(root: Path, scope: str) -> list[TransparencyTrustKeyRecord]:
        if not root.exists():
            return []
        return [load_transparency_key(path, scope) for path in sorted(root.glob("*.md"))]

    def _load_user_configuration(self) -> UserConfiguration | None:
        path = agora_home() / "config.md"
        if not path.exists():
            return None
        document = read_markdown(path)
        _assert_schema(document, "agora/user-config/v1", path)
        attributes = document.attributes
        return UserConfiguration(
            integration=self._integration(string_attribute(attributes, "integration")),
            provider=string_attribute(attributes, "provider"),
            model=string_attribute(attributes, "model"),
            default_method=self._method(string_attribute(attributes, "default-method")),
            max_delegation_depth=self._delegation_depth(attributes),
        )

    def _load_project_configuration(self, root: Path) -> ProjectConfiguration:
        path = root / ".agora" / "project.md"
        document = read_markdown(path)
        _assert_schema(document, "agora/project/v1", path)
        attributes = document.attributes
        return ProjectConfiguration(
            project=string_attribute(attributes, "project"),
            version=validate_version(string_attribute(attributes, "version")),
            integration=self._integration(string_attribute(attributes, "integration")),
            provider=string_attribute(attributes, "provider"),
            model=string_attribute(attributes, "model"),
            default_method=self._method(string_attribute(attributes, "default-method")),
            max_delegation_depth=self._delegation_depth(attributes),
            created_at=string_attribute(attributes, "created-at"),
        )

    def _install_integration(
        self,
        target: Path,
        integration: Integration,
        replacements: dict[str, str],
        force: bool,
    ) -> None:
        if integration == "generic":
            return
        for source_path in (template_root() / "commands").glob("*.md"):
            command_id = source_path.stem
            contents = source_path.read_text(encoding="utf-8")
            for key, value in replacements.items():
                contents = contents.replace(f"{{{{{key}}}}}", value)
            if integration == "codex":
                destination = target / ".agents" / "skills" / f"agora-{command_id}" / "SKILL.md"
            else:
                destination = target / ".claude" / "commands" / f"agora.{command_id}.md"
            write_new(destination, contents, force)

    @staticmethod
    def _integration_command_path(root: Path, integration: Integration, command_id: str) -> Path:
        assert_slug(command_id, "Agent command id")
        if integration == "codex":
            return root / ".agents" / "skills" / f"agora-{command_id}" / "SKILL.md"
        if integration == "claude":
            return root / ".claude" / "commands" / f"agora.{command_id}.md"
        return root / ".agora" / "commands" / f"{command_id}.md"

    @staticmethod
    def _integration_command_paths(root: Path, integration: Integration) -> list[Path]:
        if integration == "codex":
            return sorted((root / ".agents" / "skills").glob("agora-*/SKILL.md"))
        if integration == "claude":
            return sorted((root / ".claude" / "commands").glob("agora.*.md"))
        return sorted((root / ".agora" / "commands").glob("*.md"))

    @staticmethod
    def _load_agent_command(path: Path, command_id: str) -> MarkdownDocument:
        assert_slug(command_id, "Agent command id")
        document = read_markdown(path)
        name = string_attribute(document.attributes, "name")
        description = string_attribute(document.attributes, "description")
        if name != f"agora-{command_id}":
            raise ValueError(f"Agent command name must be agora-{command_id}, found {name}: {path}")
        if not description.strip():
            raise ValueError(f"Agent command description cannot be empty: {path}")
        if not document.body.strip():
            raise ValueError(f"Agent command instructions cannot be empty: {path}")
        if "{{" in document.body or "}}" in document.body:
            raise ValueError(f"Agent command contains an unresolved template value: {path}")
        return document

    def _find_actor(self, root: Path, reference: str) -> ActorRecord:
        if ":" in reference:
            scope, actor_id = reference.split(":", 1)
            if scope not in {"user", "project"}:
                raise ValueError(f"Unsupported actor scope: {scope}")
            candidates = [
                (
                    scope,
                    (agora_home() if scope == "user" else root / ".agora")
                    / "actors"
                    / f"{actor_id}.md",
                )
            ]
        else:
            actor_id = reference
            candidates = [
                ("project", root / ".agora" / "actors" / f"{actor_id}.md"),
                ("user", agora_home() / "actors" / f"{actor_id}.md"),
            ]
        assert_slug(actor_id, "Actor id")
        match = next(((scope, path) for scope, path in candidates if path.exists()), None)
        if match is None:
            raise FileNotFoundError(f"Actor not found: {reference}")
        scope, path = match
        document = read_markdown(path)
        _assert_schema(document, "agora/actor/v1", path)
        attributes = document.attributes
        kind = string_attribute(attributes, "kind")
        if kind not in ACTOR_KINDS:
            raise ValueError(f"Unsupported actor kind: {kind}")
        record = ActorRecord(
            id=string_attribute(attributes, "id"),
            name=string_attribute(attributes, "name"),
            kind=kind,
            capabilities=strings_attribute(attributes, "capabilities"),
            path=str(path),
            reference=f"{scope}:{actor_id}",
            integration=(
                self._integration(value)
                if (value := optional_string_attribute(attributes, "integration"))
                else None
            ),
            provider=optional_string_attribute(attributes, "provider"),
            model=optional_string_attribute(attributes, "model"),
            represented_swarm=optional_string_attribute(attributes, "represented-swarm"),
            authentication_required=_boolean_attribute_default(
                attributes, "authentication-required", False
            ),
            authentication_algorithm=optional_string_attribute(
                attributes, "authentication-algorithm"
            ),
            authentication_public_key=optional_string_attribute(
                attributes, "authentication-public-key"
            ),
            authentication_fingerprint=optional_string_attribute(
                attributes, "authentication-fingerprint"
            ),
            authentication_revoked_at=optional_string_attribute(
                attributes, "authentication-revoked-at"
            ),
            authentication_revoked_reason=optional_string_attribute(
                attributes, "authentication-revoked-reason"
            ),
        )
        validate_actor_identity(record)
        return record

    @staticmethod
    def _actor_key_root(actor: ActorRecord) -> Path:
        return Path(actor.path).with_suffix("") / "keys"

    def _ensure_current_actor_key(self, actor: ActorRecord) -> ActorKeyRecord:
        if actor.authentication_fingerprint is None:
            raise ValueError(f"Actor {actor.reference} has no authentication key")
        key_path = self._actor_key_root(actor) / f"{actor.authentication_fingerprint}.md"
        if not key_path.is_file():
            actor_document = read_markdown(Path(actor.path))
            record = actor_key_from_actor(
                actor,
                key_path,
                string_attribute(actor_document.attributes, "created-at"),
            )
            write_new(key_path, render_actor_key(record))
        record = self._assert_current_actor_key(actor)
        assert record is not None
        return record

    def _assert_current_actor_key(self, actor: ActorRecord) -> ActorKeyRecord | None:
        if actor.authentication_fingerprint is None:
            return None
        key_path = self._actor_key_root(actor) / f"{actor.authentication_fingerprint}.md"
        if not key_path.is_file():
            return None
        record = load_actor_key(key_path)
        expected_status = "revoked" if actor.authentication_revoked_at is not None else "active"
        if (
            record.actor != actor.reference
            or record.fingerprint != actor.authentication_fingerprint
            or record.public_key != actor.authentication_public_key
            or record.status != expected_status
        ):
            raise ValueError(f"Actor key history differs from current actor identity: {actor.path}")
        return record

    def _append_actor_event(self, root: Path, actor: ActorRecord, type_: str, detail: str) -> None:
        event_path = (
            agora_home() / "events.md"
            if actor.reference.startswith("user:")
            else root / ".agora" / "events.md"
        )
        if not event_path.exists():
            write_new(event_path, "# Agora events\n\n")
        append_entry(
            event_path,
            f"- {self._timestamp()} | {type_} | actor={actor.reference} {detail}",
        )

    def _require_actor_for_action(
        self,
        root: Path,
        swarm: SwarmRecord,
        actor_id: str,
        action: str,
        *,
        require_operational: bool = True,
    ) -> ActorRecord:
        actor = self._find_actor(root, actor_id)
        if require_operational:
            self._assert_represented_swarm_operational(root, actor)
        roles = [
            role for role, reference in swarm.assignments.items() if reference == actor.reference
        ]
        if not roles:
            raise ValueError(f"Actor {actor.reference} is not assigned to swarm {swarm.id}")
        allowed = any(self._role_allows_action(root, swarm.method, role, action) for role in roles)
        if not allowed:
            raise PermissionError(f"Actor {actor.reference} is not allowed to perform {action}")
        return actor

    @staticmethod
    def _role_allows_action(root: Path, method: str, role_id: str, action: str) -> bool:
        role = read_markdown(root / ".agora" / "methods" / method / "roles" / f"{role_id}.md")
        return action in strings_attribute(role.attributes, "allowed-actions")

    @staticmethod
    def _assert_actor_role_compatibility(
        root: Path, method: str, role_id: str, actor: ActorRecord
    ) -> None:
        role_path = root / ".agora" / "methods" / method / "roles" / f"{role_id}.md"
        if not role_path.exists():
            raise FileNotFoundError(f"Role {role_id} is not defined by method {method}")
        role = read_markdown(role_path)
        required_capabilities = strings_attribute(role.attributes, "required-capabilities")
        allowed_kinds = strings_attribute(role.attributes, "allowed-actor-kinds")
        missing = [item for item in required_capabilities if item not in actor.capabilities]
        if missing:
            raise ValueError(
                f"Actor {actor.id} lacks capabilities required by {role_id}: {', '.join(missing)}"
            )
        if actor.kind not in allowed_kinds:
            raise ValueError(f"Actor kind {actor.kind} is not allowed for role {role_id}")

    def _assert_swarm_actor_delegation(
        self,
        root: Path,
        parent: SwarmRecord,
        role_id: str,
        actor: ActorRecord,
    ) -> None:
        if actor.represented_swarm is None:
            return
        self._assert_represented_swarm_operational(root, actor)
        project = self._load_project_configuration(root)
        graph = self._delegation_graph(root, exclude=(parent.id, role_id))
        graph.setdefault(parent.id, set()).add(actor.represented_swarm)
        self._validate_delegation_graph(graph, project.max_delegation_depth)

    def _assert_represented_swarm_operational(self, root: Path, actor: ActorRecord) -> None:
        if actor.represented_swarm is None:
            return
        project = self._load_project_configuration(root)
        self._validate_delegation_graph(self._delegation_graph(root), project.max_delegation_depth)
        for swarm_id in self._delegated_swarm_ids(root, actor.represented_swarm):
            child = self._load_swarm(root, swarm_id)
            if child.status not in {"ready", "running"}:
                raise ValueError(
                    f"Represented swarm {child.id} must be ready or running; status={child.status}"
                )

    def _delegation_graph(
        self, root: Path, exclude: tuple[str, str] | None = None
    ) -> dict[str, set[str]]:
        graph: dict[str, set[str]] = {}
        swarm_root = root / ".agora" / "swarms"
        for path in swarm_root.iterdir():
            if not path.is_dir() or not (path / "SWARM.md").exists():
                continue
            swarm = self._load_swarm(root, path.name)
            graph.setdefault(swarm.id, set())
            for role_id, reference in swarm.assignments.items():
                if exclude == (swarm.id, role_id):
                    continue
                assigned_actor = self._find_actor(root, reference)
                if assigned_actor.represented_swarm is not None:
                    graph[swarm.id].add(assigned_actor.represented_swarm)
        return graph

    def _delegated_swarm_ids(self, root: Path, first: str) -> list[str]:
        ordered: list[str] = []
        pending = [first]
        seen: set[str] = set()
        while pending:
            swarm_id = pending.pop(0)
            if swarm_id in seen:
                continue
            seen.add(swarm_id)
            ordered.append(swarm_id)
            swarm = self._load_swarm(root, swarm_id)
            children: list[str] = []
            for reference in swarm.assignments.values():
                actor = self._find_actor(root, reference)
                if actor.represented_swarm is not None:
                    children.append(actor.represented_swarm)
            pending.extend(sorted(children))
        return ordered

    @staticmethod
    def _validate_delegation_graph(graph: dict[str, set[str]], maximum: int) -> None:
        known = set(graph)
        referenced = {child for children in graph.values() for child in children}
        missing = sorted(referenced - known)
        if missing:
            raise FileNotFoundError(
                f"Delegation graph references unknown swarms: {', '.join(missing)}"
            )

        memo: dict[str, int] = {}

        def depth(swarm_id: str, path: list[str]) -> int:
            if swarm_id in path:
                cycle = [*path[path.index(swarm_id) :], swarm_id]
                raise ValueError(f"Recursive swarm cycle detected: {' -> '.join(cycle)}")
            if swarm_id in memo:
                return memo[swarm_id]
            children = graph.get(swarm_id, set())
            value = (
                max(1 + depth(child, [*path, swarm_id]) for child in children) if children else 0
            )
            memo[swarm_id] = value
            return value

        actual = max((depth(swarm_id, []) for swarm_id in graph), default=0)
        if actual > maximum:
            raise ValueError(f"Delegation depth {actual} exceeds configured maximum {maximum}")

    @staticmethod
    def _actor_roles(swarm: SwarmRecord, actor_reference: str) -> list[str]:
        return [
            role for role, reference in swarm.assignments.items() if reference == actor_reference
        ]

    def _assert_work_mutable(self, root: Path, swarm: SwarmRecord, work: WorkRecord) -> None:
        if work.operational_status != "active":
            raise ValueError(
                f"Work {swarm.id}/{work.id} is {work.operational_status}; resume it before "
                "performing work mutations"
            )
        contract = load_method_contract(root / ".agora" / "methods" / swarm.method)
        if work.state == contract.terminal_state:
            raise ValueError(f"Completed work cannot be modified: {swarm.id}/{work.id}")

    @staticmethod
    def _derived_swarm_status(
        swarm: SwarmRecord,
        work: list[WorkRecord],
        contract: MethodContract,
    ) -> str:
        if not all(role in swarm.assignments for role in swarm.required_roles):
            return "forming"
        if not work:
            return "ready"
        if all(item.operational_status == "cancelled" for item in work):
            return "cancelled"
        if all(
            item.operational_status == "cancelled" or item.state == contract.terminal_state
            for item in work
        ):
            return "completed"
        outstanding = [
            item
            for item in work
            if item.operational_status != "cancelled" and item.state != contract.terminal_state
        ]
        if outstanding and all(item.operational_status == "blocked" for item in outstanding):
            return "blocked"
        if any(
            item.operational_status != "cancelled" and item.state != contract.work_states[0]
            for item in work
        ):
            return "running"
        return "ready"

    def _refresh_swarm_status(self, root: Path, swarm: SwarmRecord) -> None:
        contract = load_method_contract(root / ".agora" / "methods" / swarm.method)
        work = [
            self._load_work(swarm, path.parent.name)
            for path in sorted((Path(swarm.path) / "work").glob("*/WORK.md"))
        ]
        target = self._derived_swarm_status(swarm, work, contract)
        if target == swarm.status:
            return
        previous = swarm.status
        swarm.status = target
        atomic_write(Path(swarm.path) / "SWARM.md", self._render_swarm(swarm))
        self._append_swarm_event(
            root,
            swarm.id,
            "swarm.status-changed",
            f"from={previous} to={target}",
        )

    def _load_swarm(self, root: Path, swarm_id: str) -> SwarmRecord:
        assert_slug(swarm_id, "Swarm id")
        path = root / ".agora" / "swarms" / swarm_id
        document = read_markdown(path / "SWARM.md")
        _assert_schema(document, "agora/swarm/v1", path / "SWARM.md")
        return SwarmRecord(
            id=string_attribute(document.attributes, "id"),
            method=string_attribute(document.attributes, "method"),
            status=string_attribute(document.attributes, "status"),
            branch=string_attribute(document.attributes, "branch"),
            required_roles=strings_attribute(document.attributes, "required-roles"),
            assignments=record_attribute(document.attributes, "assignments"),
            objective=_extract_section(document.body, "Objective"),
            path=str(path),
        )

    def _render_swarm(self, swarm: SwarmRecord) -> str:
        assignments = "\n".join(
            f"| {role} | {swarm.assignments.get(role, 'unassigned')} |"
            for role in swarm.required_roles
        )
        return render_markdown(
            MarkdownDocument(
                attributes={
                    "schema": "agora/swarm/v1",
                    "id": swarm.id,
                    "method": swarm.method,
                    "status": swarm.status,
                    "branch": swarm.branch,
                    "required-roles": swarm.required_roles,
                    "assignments": swarm.assignments,
                },
                body=(
                    f"# Swarm {swarm.id}\n\n## Objective\n\n{swarm.objective}\n\n"
                    "## Assignments\n\n| Role | Actor |\n| --- | --- |\n"
                    f"{assignments}"
                ),
            )
        )

    @staticmethod
    def _render_handoff(record: HandoffRecord) -> str:
        return render_markdown(
            MarkdownDocument(
                attributes={
                    "schema": "agora/handoff/v1",
                    "id": record.id,
                    "swarm": record.swarm_id,
                    "role": record.role_id,
                    "from": record.from_actor,
                    "to": record.to_actor,
                    "authorized-by": record.authorized_by,
                    "work": record.work_id,
                    "created-at": record.created_at,
                },
                body=(
                    f"# Handoff {record.id}\n\n## Reason\n\n{record.reason}\n\n"
                    "## Continuity\n\n"
                    "The role assignment changed without changing actor identities, work identity, "
                    "or prior execution records."
                ),
            )
        )

    @staticmethod
    def _load_handoff(swarm: SwarmRecord, handoff_id: str) -> HandoffRecord:
        assert_slug(handoff_id, "Handoff id")
        path = Path(swarm.path) / "handoffs" / handoff_id / "HANDOFF.md"
        document = read_markdown(path)
        _assert_schema(document, "agora/handoff/v1", path)
        reason = _extract_section(document.body, "Reason")
        legacy_note = (
            "The role assignment changed without changing actor identities, work identity, "
            "or prior execution records."
        )
        if reason.endswith(f"\n\n{legacy_note}"):
            reason = reason[: -len(legacy_note)].rstrip()
        return HandoffRecord(
            id=string_attribute(document.attributes, "id"),
            swarm_id=string_attribute(document.attributes, "swarm"),
            role_id=string_attribute(document.attributes, "role"),
            from_actor=string_attribute(document.attributes, "from"),
            to_actor=string_attribute(document.attributes, "to"),
            authorized_by=string_attribute(document.attributes, "authorized-by"),
            reason=reason,
            work_id=optional_string_attribute(document.attributes, "work"),
            created_at=string_attribute(document.attributes, "created-at"),
            path=str(path),
        )

    def _record_status_change(
        self,
        *,
        subject_type: str,
        subject: str,
        action: str,
        previous_status: str,
        target_status: str,
        actor: str,
        reason: str,
        root: Path,
        id_: str | None,
    ) -> StatusChangeRecord:
        if subject_type not in {"work", "delegation"}:
            raise ValueError(f"Unsupported status change subject type: {subject_type}")
        change_id = id_ or self._now().astimezone(UTC).strftime("change-%Y%m%dt%H%M%S%fz")
        if id_ is None:
            base = change_id
            suffix = 2
            while (root / change_id / "STATUS.md").exists():
                change_id = f"{base}-{suffix}"
                suffix += 1
        assert_slug(change_id, "Status change id")
        path = root / change_id / "STATUS.md"
        if path.exists():
            raise FileExistsError(f"Status change already exists: {change_id}")
        sequence = len(list(root.glob("*/STATUS.md"))) + 1
        record = StatusChangeRecord(
            id=change_id,
            subject_type="work" if subject_type == "work" else "delegation",
            subject=subject,
            action=action,
            previous_status=previous_status,
            target_status=target_status,
            actor=actor,
            reason=reason,
            sequence=sequence,
            created_at=self._timestamp(),
            path=str(path),
        )
        write_new(path, self._render_status_change(record))
        return record

    @staticmethod
    def _assert_status_change_id_available(root: Path, id_: str | None) -> None:
        if id_ is None:
            return
        assert_slug(id_, "Status change id")
        if (root / id_ / "STATUS.md").exists():
            raise FileExistsError(f"Status change already exists: {id_}")

    @staticmethod
    def _render_status_change(record: StatusChangeRecord) -> str:
        return render_markdown(
            MarkdownDocument(
                attributes={
                    "schema": "agora/status-change/v1",
                    "id": record.id,
                    "subject-type": record.subject_type,
                    "subject": record.subject,
                    "action": record.action,
                    "previous-status": record.previous_status,
                    "target-status": record.target_status,
                    "actor": record.actor,
                    "sequence": record.sequence,
                    "created-at": record.created_at,
                },
                body=f"# Status change {record.id}\n\n## Reason\n\n{record.reason}",
            )
        )

    @staticmethod
    def _load_status_change(path: Path) -> StatusChangeRecord:
        document = read_markdown(path / "STATUS.md")
        _assert_schema(document, "agora/status-change/v1", path / "STATUS.md")
        subject_type = string_attribute(document.attributes, "subject-type")
        if subject_type not in {"work", "delegation"}:
            raise ValueError(f"Unsupported status change subject type: {subject_type}")
        return StatusChangeRecord(
            id=string_attribute(document.attributes, "id"),
            subject_type="work" if subject_type == "work" else "delegation",
            subject=string_attribute(document.attributes, "subject"),
            action=string_attribute(document.attributes, "action"),
            previous_status=string_attribute(document.attributes, "previous-status"),
            target_status=string_attribute(document.attributes, "target-status"),
            actor=string_attribute(document.attributes, "actor"),
            reason=_extract_section(document.body, "Reason"),
            sequence=_optional_integer_attribute(document.attributes, "sequence") or 0,
            created_at=string_attribute(document.attributes, "created-at"),
            path=str(path / "STATUS.md"),
        )

    @staticmethod
    def _render_delegation(record: DelegationRecord) -> str:
        criteria = (
            "\n".join(
                f"- **{criterion_id}:** {description}"
                for criterion_id, description in record.acceptance_criteria.items()
            )
            or "- none"
        )
        artifacts = "\n".join(f"- {kind}" for kind in record.required_artifacts) or "- none"
        return render_markdown(
            MarkdownDocument(
                attributes={
                    "schema": "agora/delegation/v1",
                    "id": record.id,
                    "parent-swarm": record.parent_swarm_id,
                    "parent-work": record.parent_work_id,
                    "child-swarm": record.child_swarm_id,
                    "child-work": record.child_work_id,
                    "represented-by": record.represented_by,
                    "requested-by": record.requested_by,
                    "title": record.title,
                    "acceptance-criteria": record.acceptance_criteria,
                    "required-artifacts": record.required_artifacts,
                    "result-kind": record.result_kind,
                    "budget-limits": record.budget_limits,
                    "artifact-promotions": record.artifact_promotions,
                    "status": record.status,
                    "created-at": record.created_at,
                    "accepted-by": record.accepted_by,
                    "accepted-at": record.accepted_at,
                    "collected-by": record.collected_by,
                    "collected-at": record.collected_at,
                    "blocked-from": record.blocked_from,
                    "status-reason": record.status_reason,
                    "status-by": record.status_by,
                    "status-at": record.status_at,
                },
                body=(
                    f"# Delegation {record.id}\n\n## Description\n\n"
                    f"{record.description or 'No description provided.'}\n\n"
                    f"## Acceptance criteria\n\n{criteria}\n\n"
                    f"## Required child artifacts\n\n{artifacts}"
                ),
            )
        )

    def _load_delegation(self, root: Path, delegation_id: str) -> DelegationRecord:
        assert_slug(delegation_id, "Delegation id")
        path = root / ".agora" / "delegations" / delegation_id / "DELEGATION.md"
        document = read_markdown(path)
        if string_attribute(document.attributes, "schema") != "agora/delegation/v1":
            raise ValueError(f"Delegation schema must be agora/delegation/v1: {path}")
        status = string_attribute(document.attributes, "status")
        if status not in {
            "proposed",
            "accepted",
            "blocked",
            "collected",
            "rejected",
            "cancelled",
        }:
            raise ValueError(f"Unsupported delegation status: {status}")
        return DelegationRecord(
            id=string_attribute(document.attributes, "id"),
            parent_swarm_id=string_attribute(document.attributes, "parent-swarm"),
            parent_work_id=string_attribute(document.attributes, "parent-work"),
            child_swarm_id=string_attribute(document.attributes, "child-swarm"),
            child_work_id=string_attribute(document.attributes, "child-work"),
            represented_by=string_attribute(document.attributes, "represented-by"),
            requested_by=string_attribute(document.attributes, "requested-by"),
            title=string_attribute(document.attributes, "title"),
            description=_extract_section(document.body, "Description"),
            acceptance_criteria=record_attribute(document.attributes, "acceptance-criteria"),
            required_artifacts=strings_attribute(document.attributes, "required-artifacts"),
            result_kind=string_attribute(document.attributes, "result-kind"),
            status=status,
            created_at=string_attribute(document.attributes, "created-at"),
            accepted_by=optional_string_attribute(document.attributes, "accepted-by"),
            accepted_at=optional_string_attribute(document.attributes, "accepted-at"),
            collected_by=optional_string_attribute(document.attributes, "collected-by"),
            collected_at=optional_string_attribute(document.attributes, "collected-at"),
            blocked_from=optional_string_attribute(document.attributes, "blocked-from"),
            status_reason=optional_string_attribute(document.attributes, "status-reason"),
            status_by=optional_string_attribute(document.attributes, "status-by"),
            status_at=optional_string_attribute(document.attributes, "status-at"),
            path=str(path),
            budget_limits=optional_integer_record_attribute(document.attributes, "budget-limits"),
            artifact_promotions=(
                record_attribute(document.attributes, "artifact-promotions")
                if "artifact-promotions" in document.attributes
                else {}
            ),
        )

    def _load_work(self, swarm: SwarmRecord, work_id: str) -> WorkRecord:
        assert_slug(work_id, "Work id")
        path = Path(swarm.path) / "work" / work_id
        document = read_markdown(path / "WORK.md")
        artifacts = read_markdown(path / "artifacts.md")
        evidence = read_markdown(path / "evidence.md")
        _assert_schema(document, "agora/work/v1", path / "WORK.md")
        _assert_schema(artifacts, "agora/artifacts/v1", path / "artifacts.md")
        _assert_schema(evidence, "agora/evidence/v1", path / "evidence.md")
        approvals_path = path / "approvals.md"
        if approvals_path.exists():
            approvals = read_markdown(approvals_path)
            _assert_schema(approvals, "agora/approvals/v1", approvals_path)
            approval_roles = strings_attribute(approvals.attributes, "approval-roles")
        else:
            approval_roles = []
        return WorkRecord(
            id=string_attribute(document.attributes, "id"),
            swarm_id=string_attribute(document.attributes, "swarm"),
            title=string_attribute(document.attributes, "title"),
            description=_extract_section(document.body, "Description"),
            state=string_attribute(document.attributes, "state"),
            acceptance_criteria=record_attribute(document.attributes, "acceptance-criteria"),
            satisfied_criteria=strings_attribute(document.attributes, "satisfied-criteria"),
            required_artifacts=strings_attribute(document.attributes, "required-artifacts"),
            artifact_kinds=strings_attribute(artifacts.attributes, "artifact-kinds"),
            evidence_results=strings_attribute(evidence.attributes, "results"),
            approval_roles=approval_roles,
            path=str(path),
            child_work_refs=(
                strings_attribute(document.attributes, "child-work-refs")
                if "child-work-refs" in document.attributes
                else []
            ),
            budget_limits=optional_integer_record_attribute(document.attributes, "budget-limits"),
            operational_status=_work_operational_status(
                document.attributes.get("operational-status", "active")
            ),
            status_reason=optional_string_attribute(document.attributes, "status-reason"),
            status_by=optional_string_attribute(document.attributes, "status-by"),
            status_at=optional_string_attribute(document.attributes, "status-at"),
            delegation_id=optional_string_attribute(document.attributes, "delegation"),
            parent_work_ref=optional_string_attribute(document.attributes, "parent-work"),
        )

    def _render_work(self, work: WorkRecord) -> str:
        checklist = "\n".join(
            f"- [{'x' if item in work.satisfied_criteria else ' '}] **{item}:** {description}"
            for item, description in work.acceptance_criteria.items()
        )
        artifacts = "\n".join(f"- {item}" for item in work.required_artifacts) or "- none"
        attributes: dict[str, object] = {
            "schema": "agora/work/v1",
            "id": work.id,
            "swarm": work.swarm_id,
            "title": work.title,
            "state": work.state,
            "operational-status": work.operational_status,
            "status-reason": work.status_reason,
            "status-by": work.status_by,
            "status-at": work.status_at,
            "acceptance-criteria": work.acceptance_criteria,
            "satisfied-criteria": work.satisfied_criteria,
            "required-artifacts": work.required_artifacts,
            "child-work-refs": work.child_work_refs,
            "budget-limits": work.budget_limits,
        }
        if work.delegation_id is not None:
            attributes["delegation"] = work.delegation_id
        if work.parent_work_ref is not None:
            attributes["parent-work"] = work.parent_work_ref
        return render_markdown(
            MarkdownDocument(
                attributes=attributes,
                body=(
                    f"# {work.title}\n\n## Description\n\n"
                    f"{work.description or 'No description provided.'}\n\n"
                    f"## Acceptance criteria\n\n{checklist or '- none'}\n\n"
                    f"## Required artifacts\n\n{artifacts}"
                ),
            )
        )

    @staticmethod
    def _render_usage(record: UsageRecord) -> str:
        return render_markdown(
            MarkdownDocument(
                attributes={
                    "schema": "agora/usage/v1",
                    "id": record.id,
                    "swarm": record.swarm_id,
                    "work": record.work_id,
                    "actor": record.actor,
                    "amounts": record.amounts,
                    "evidence-refs": record.evidence_refs,
                    "created-at": record.created_at,
                    "action": record.action_id,
                },
                body=(
                    f"# Usage {record.id}\n\n"
                    "This append-only record contains externally measured resource usage. Agora "
                    "validates attribution and budget limits but does not perform provider "
                    "metering."
                ),
            )
        )

    @classmethod
    def _load_usage(cls, path: Path) -> UsageRecord:
        document = read_markdown(path)
        _assert_schema(document, "agora/usage/v1", path)
        amounts = optional_integer_record_attribute(document.attributes, "amounts")
        if amounts is None:
            raise ValueError(f"Usage amounts are required: {path}")
        record = UsageRecord(
            id=string_attribute(document.attributes, "id"),
            swarm_id=string_attribute(document.attributes, "swarm"),
            work_id=string_attribute(document.attributes, "work"),
            actor=string_attribute(document.attributes, "actor"),
            amounts=cls._normalize_usage_amounts(amounts),
            evidence_refs=strings_attribute(document.attributes, "evidence-refs"),
            created_at=string_attribute(document.attributes, "created-at"),
            path=str(path),
            action_id=optional_string_attribute(document.attributes, "action"),
        )
        assert_slug(record.id, "Usage id")
        if not record.evidence_refs or any(
            not reference.strip() for reference in record.evidence_refs
        ):
            raise ValueError(f"Usage requires non-empty evidence references: {path}")
        if record.action_id is not None:
            assert_slug(record.action_id, "Usage Lifecycle Action id")
        return record

    @staticmethod
    def _render_gate_waiver(record: GateWaiverRecord) -> str:
        return render_markdown(
            MarkdownDocument(
                attributes={
                    "schema": "agora/gate-waiver/v1",
                    "id": record.id,
                    "swarm": record.swarm_id,
                    "work": record.work_id,
                    "gate": record.gate_id,
                    "waived-criteria": record.waived_criteria,
                    "waived-artifacts": record.waived_artifacts,
                    "waive-successful-evidence": record.waive_successful_evidence,
                    "waived-approval-roles": record.waived_approval_roles,
                    "reason": record.reason,
                    "evidence-refs": record.evidence_refs,
                    "authorized-by": record.authorized_by,
                    "created-at": record.created_at,
                    "action": record.action_id,
                },
                body=(
                    f"# Gate Waiver {record.id}\n\n"
                    "This decision waives only the named obligations. The transition edge, "
                    "role authority, WIP policy, and operational status remain enforced."
                ),
            )
        )

    @staticmethod
    def _load_gate_waiver(path: Path) -> GateWaiverRecord:
        document = read_markdown(path)
        _assert_schema(document, "agora/gate-waiver/v1", path)
        record = GateWaiverRecord(
            id=string_attribute(document.attributes, "id"),
            swarm_id=string_attribute(document.attributes, "swarm"),
            work_id=string_attribute(document.attributes, "work"),
            gate_id=string_attribute(document.attributes, "gate"),
            waived_criteria=strings_attribute(document.attributes, "waived-criteria"),
            waived_artifacts=strings_attribute(document.attributes, "waived-artifacts"),
            waive_successful_evidence=_boolean_attribute_default(
                document.attributes, "waive-successful-evidence", False
            ),
            waived_approval_roles=strings_attribute(document.attributes, "waived-approval-roles"),
            reason=string_attribute(document.attributes, "reason"),
            evidence_refs=strings_attribute(document.attributes, "evidence-refs"),
            authorized_by=string_attribute(document.attributes, "authorized-by"),
            created_at=string_attribute(document.attributes, "created-at"),
            path=str(path),
            action_id=optional_string_attribute(document.attributes, "action"),
        )
        assert_slug(record.id, "Gate Waiver id")
        assert_slug(record.gate_id, "Gate Waiver gate id")
        if not record.reason.strip():
            raise ValueError(f"Gate Waiver reason cannot be empty: {path}")
        if not record.evidence_refs or any(not item.strip() for item in record.evidence_refs):
            raise ValueError(f"Gate Waiver requires risk evidence references: {path}")
        obligations = (
            record.waived_criteria,
            record.waived_artifacts,
            record.waived_approval_roles,
        )
        if any(len(items) != len(set(items)) for items in obligations):
            raise ValueError(f"Gate Waiver obligations must be unique: {path}")
        if not any(obligations) and not record.waive_successful_evidence:
            raise ValueError(f"Gate Waiver must name at least one obligation: {path}")
        for label, items in (
            ("criterion", record.waived_criteria),
            ("approval role", record.waived_approval_roles),
        ):
            for item in items:
                assert_slug(item, f"Gate Waiver {label}")
        return record

    def _load_gate_waivers(self, work: WorkRecord) -> list[GateWaiverRecord]:
        return [
            self._load_gate_waiver(path)
            for path in sorted((Path(work.path) / "waivers").glob("*/WAIVER.md"))
        ]

    def _gate_waiver_coverage(
        self, work: WorkRecord, gate_id: str
    ) -> tuple[set[str], set[str], bool, set[str]]:
        records = [record for record in self._load_gate_waivers(work) if record.gate_id == gate_id]
        return (
            {item for record in records for item in record.waived_criteria},
            {item for record in records for item in record.waived_artifacts},
            any(record.waive_successful_evidence for record in records),
            {item for record in records for item in record.waived_approval_roles},
        )

    @staticmethod
    def _render_approval_delegation(record: ApprovalDelegationRecord) -> str:
        return render_markdown(
            MarkdownDocument(
                attributes={
                    "schema": "agora/approval-delegation/v1",
                    "id": record.id,
                    "swarm": record.swarm_id,
                    "work": record.work_id,
                    "role": record.role_id,
                    "from": record.from_actor,
                    "to": record.to_actor,
                    "reason": record.reason,
                    "status": record.status,
                    "created-at": record.created_at,
                    "action": record.action_id,
                    "used-by": record.used_by,
                    "used-at": record.used_at,
                    "used-action": record.used_action_id,
                    "revoked-by": record.revoked_by,
                    "revoked-at": record.revoked_at,
                    "revoked-reason": record.revoked_reason,
                    "revocation-action": record.revocation_action_id,
                },
                body=(
                    f"# Approval Delegation {record.id}\n\n"
                    "This single-use authority is limited to the named work item and role."
                ),
            )
        )

    @staticmethod
    def _load_approval_delegation(work: WorkRecord, delegation_id: str) -> ApprovalDelegationRecord:
        assert_slug(delegation_id, "Approval Delegation id")
        path = Path(work.path) / "approval-delegations" / delegation_id / "DELEGATION.md"
        document = read_markdown(path)
        _assert_schema(document, "agora/approval-delegation/v1", path)
        status = string_attribute(document.attributes, "status")
        if status not in {"active", "used", "revoked"}:
            raise ValueError(f"Unsupported Approval Delegation status: {status}")
        record = ApprovalDelegationRecord(
            id=string_attribute(document.attributes, "id"),
            swarm_id=string_attribute(document.attributes, "swarm"),
            work_id=string_attribute(document.attributes, "work"),
            role_id=string_attribute(document.attributes, "role"),
            from_actor=string_attribute(document.attributes, "from"),
            to_actor=string_attribute(document.attributes, "to"),
            reason=string_attribute(document.attributes, "reason"),
            status=status,  # type: ignore[arg-type]
            created_at=string_attribute(document.attributes, "created-at"),
            path=str(path),
            action_id=optional_string_attribute(document.attributes, "action"),
            used_by=optional_string_attribute(document.attributes, "used-by"),
            used_at=optional_string_attribute(document.attributes, "used-at"),
            used_action_id=optional_string_attribute(document.attributes, "used-action"),
            revoked_by=optional_string_attribute(document.attributes, "revoked-by"),
            revoked_at=optional_string_attribute(document.attributes, "revoked-at"),
            revoked_reason=optional_string_attribute(document.attributes, "revoked-reason"),
            revocation_action_id=optional_string_attribute(
                document.attributes, "revocation-action"
            ),
        )
        assert_slug(record.id, "Approval Delegation id")
        assert_slug(record.role_id, "Approval Delegation role id")
        if not record.reason.strip():
            raise ValueError(f"Approval Delegation reason cannot be empty: {path}")
        if record.from_actor == record.to_actor or any(
            ":" not in actor for actor in (record.from_actor, record.to_actor)
        ):
            raise ValueError(f"Approval Delegation actors are invalid: {path}")
        used_required = (record.used_by, record.used_at)
        used_all = (*used_required, record.used_action_id)
        revoked_required = (record.revoked_by, record.revoked_at, record.revoked_reason)
        revoked_all = (*revoked_required, record.revocation_action_id)
        if status == "active" and any(value is not None for value in (*used_all, *revoked_all)):
            raise ValueError(f"Active Approval Delegation has terminal attribution: {path}")
        if status == "used" and (
            any(value is None for value in used_required)
            or any(value is not None for value in revoked_all)
        ):
            raise ValueError(f"Used Approval Delegation attribution is invalid: {path}")
        if status == "revoked" and (
            any(value is None for value in revoked_required)
            or any(value is not None for value in used_all)
        ):
            raise ValueError(f"Revoked Approval Delegation attribution is invalid: {path}")
        if record.used_by is not None and record.used_by != record.to_actor:
            raise ValueError(f"Approval Delegation was used by the wrong actor: {path}")
        if record.revoked_reason is not None and not record.revoked_reason.strip():
            raise ValueError(f"Approval Delegation revocation reason cannot be empty: {path}")
        return record

    def _load_approval_delegations(self, work: WorkRecord) -> list[ApprovalDelegationRecord]:
        return [
            self._load_approval_delegation(work, path.parent.name)
            for path in sorted((Path(work.path) / "approval-delegations").glob("*/DELEGATION.md"))
        ]

    @staticmethod
    def _runtime_command(integration: Integration, runner: str | None, model: str) -> list[str]:
        if runner is not None:
            command = shlex.split(runner)
            if not command:
                raise ValueError("Runner command cannot be empty")
            return command
        prompt = (
            "Read the Agora session context from the path in AGORA_CONTEXT. Follow its operational "
            "Markdown, perform only the next action permitted for the assigned role, persist "
            "artifacts and evidence through Agora, and stop at human approval or unavailable "
            "authority."
        )
        if integration == "codex":
            command = ["codex", "exec"]
            if not model.startswith("configured-by-"):
                command.extend(["--model", model])
            return [*command, prompt]
        if integration == "claude":
            command = ["claude", "--print"]
            if not model.startswith("configured-by-"):
                command.extend(["--model", model])
            return [*command, prompt]
        return []

    @staticmethod
    def _work_precondition_sha256(work: WorkRecord) -> str:
        digest = hashlib.sha256()
        work_root = Path(work.path)
        for name in ("WORK.md", "approvals.md", "artifacts.md", "evidence.md"):
            path = work_root / name
            if not path.is_file():
                raise FileNotFoundError(f"Work policy document is missing: {path}")
            digest.update(name.encode("ascii"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
        for path in sorted((work_root / "waivers").glob("*/WAIVER.md")):
            digest.update(b"waiver\0")
            digest.update(path.parent.name.encode("ascii"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
        for path in sorted((work_root / "approval-delegations").glob("*/DELEGATION.md")):
            digest.update(b"approval-delegation\0")
            digest.update(path.parent.name.encode("ascii"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
        for path in sorted((work_root / "usage").glob("*/USAGE.md")):
            digest.update(b"usage\0")
            digest.update(path.parent.name.encode("ascii"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
        return digest.hexdigest()

    def _lifecycle_precondition_sha256(
        self,
        root: Path,
        action: str,
        actor: ActorRecord,
        swarm: SwarmRecord,
        work: WorkRecord | None,
        parameters: dict[str, str],
    ) -> str:
        if action in {
            "approval.add",
            "approval.delegate",
            "approval.delegation.revoke",
            "artifact.add",
            "criterion.satisfy",
            "evidence.add",
            "usage.add",
            "gate.waive",
            "work.block",
            "work.cancel",
            "work.decompose",
            "work.resume",
            "work.transition",
        }:
            if work is None:
                raise ValueError(f"Lifecycle Action {action} requires work")
            return self._work_precondition_sha256(work)
        if action == "work.create":
            swarm_path = Path(swarm.path) / "SWARM.md"
            if not swarm_path.is_file():
                raise FileNotFoundError(f"Swarm policy document is missing: {swarm_path}")
            digest = hashlib.sha256()
            digest.update(b"SWARM.md\0")
            digest.update(swarm_path.read_bytes())
            digest.update(b"\0")
            return digest.hexdigest()
        if action == "swarm.assign":
            target = self._find_actor(root, parameters["target"])
            digest = hashlib.sha256()
            for label, path in (
                ("authorizer", Path(actor.path)),
                ("target", Path(target.path)),
                ("swarm", Path(swarm.path) / "SWARM.md"),
            ):
                if not path.is_file():
                    raise FileNotFoundError(f"Assignment policy document is missing: {path}")
                digest.update(f"{label}\0".encode("ascii"))
                digest.update(path.read_bytes())
                digest.update(b"\0")
            return digest.hexdigest()
        if action in {
            "actor.key.recover",
            "actor.key.revoke",
            "actor.key.rotate",
            "actor.runtime.update",
        }:
            target = (
                self._find_actor(root, parameters["target"])
                if action in {"actor.key.recover", "actor.key.revoke"}
                else actor
            )
            digest = hashlib.sha256()
            policy_paths = [
                ("authorizer", Path(actor.path)),
                ("swarm", Path(swarm.path) / "SWARM.md"),
            ]
            if target.reference != actor.reference:
                policy_paths.append(("target", Path(target.path)))
            for label, path in policy_paths:
                if not path.is_file():
                    raise FileNotFoundError(f"Actor policy document is missing: {path}")
                digest.update(f"{label}\0".encode("ascii"))
                digest.update(path.read_bytes())
                digest.update(b"\0")
            if action != "actor.runtime.update":
                for path in sorted(self._actor_key_root(target).glob("*.md")):
                    digest.update(b"actor-key\0")
                    digest.update(path.name.encode("ascii"))
                    digest.update(b"\0")
                    digest.update(path.read_bytes())
                    digest.update(b"\0")
            return digest.hexdigest()
        if action == "session.prepare":
            session = StartSessionInput(
                id=parameters["session"],
                actor_id=actor.reference,
                swarm_id=swarm.id,
                work_id=work.id if work is not None else None,
                runner=parameters["runner"] or None,
                timeout_seconds=int(
                    parameters.get("timeout-seconds", str(DEFAULT_SESSION_TIMEOUT_SECONDS))
                ),
                max_output_bytes=int(
                    parameters.get("max-output-bytes", str(DEFAULT_SESSION_MAX_OUTPUT_BYTES))
                ),
            )
            context = self._validate_session_preparation(root, session)[-1]
            return hashlib.sha256(context.encode()).hexdigest()
        if action == "handoff.create":
            swarm_path = Path(swarm.path) / "SWARM.md"
            if not swarm_path.is_file():
                raise FileNotFoundError(f"Swarm policy document is missing: {swarm_path}")
            digest = hashlib.sha256()
            digest.update(b"SWARM.md\0")
            digest.update(swarm_path.read_bytes())
            digest.update(b"\0")
            if work is not None:
                digest.update(b"work-precondition-sha256\0")
                digest.update(self._work_precondition_sha256(work).encode("ascii"))
                digest.update(b"\0")
            return digest.hexdigest()
        if action == "delegation.create":
            if work is None:
                raise ValueError("Lifecycle Action delegation.create requires parent work")
            child_actor = self._find_actor(root, parameters["child-actor"])
            if child_actor.represented_swarm is None:
                raise ValueError(f"Actor {child_actor.reference} does not represent a child swarm")
            child = self._load_swarm(root, child_actor.represented_swarm)
            digest = hashlib.sha256()
            for label, path in (
                ("parent-swarm", Path(swarm.path) / "SWARM.md"),
                ("child-actor", Path(child_actor.path)),
                ("child-swarm", Path(child.path) / "SWARM.md"),
            ):
                if not path.is_file():
                    raise FileNotFoundError(f"Delegation policy document is missing: {path}")
                digest.update(f"{label}\0".encode("ascii"))
                digest.update(path.read_bytes())
                digest.update(b"\0")
            digest.update(b"parent-work-precondition-sha256\0")
            digest.update(self._work_precondition_sha256(work).encode("ascii"))
            digest.update(b"\0")
            return digest.hexdigest()
        if action in {
            "delegation.accept",
            "delegation.block",
            "delegation.cancel",
            "delegation.collect",
            "delegation.reject",
            "delegation.resume",
        }:
            if work is None:
                raise ValueError(f"Lifecycle Action {action} requires parent work")
            delegation_id = parameters.get("delegation")
            if delegation_id is None:
                raise ValueError(f"Lifecycle Action {action} requires a delegation")
            delegation = self._load_delegation(root, delegation_id)
            digest = hashlib.sha256()
            digest.update(b"DELEGATION.md\0")
            digest.update(Path(delegation.path).read_bytes())
            digest.update(b"\0parent-work-precondition-sha256\0")
            digest.update(self._work_precondition_sha256(work).encode("ascii"))
            digest.update(b"\0")
            if action in {"delegation.accept", "delegation.collect"}:
                child = self._load_swarm(root, delegation.child_swarm_id)
                child_swarm_path = Path(child.path) / "SWARM.md"
                digest.update(b"child-swarm\0")
                digest.update(child_swarm_path.read_bytes())
                digest.update(b"\0")
            if action == "delegation.collect":
                child_work = self._load_work(child, delegation.child_work_id)
                digest.update(b"child-work-precondition-sha256\0")
                digest.update(self._work_precondition_sha256(child_work).encode("ascii"))
                digest.update(b"\0")
            return digest.hexdigest()
        raise ValueError(f"Unsupported Lifecycle Action kind: {action}")

    def _assert_lifecycle_precondition(self, root: Path, record: LifecycleActionRecord) -> None:
        swarm = self._load_swarm(root, record.swarm_id)
        work = (
            self._load_work(swarm, record.work_id)
            if record.work_id is not None and record.action != "work.create"
            else None
        )
        actor = self._find_actor(root, record.actor)
        actual = self._lifecycle_precondition_sha256(
            root, record.action, actor, swarm, work, record.parameters
        )
        if actual != record.precondition_sha256:
            raise ValueError(f"Lifecycle Action precondition digest mismatch: {record.id}")

    @staticmethod
    def _render_lifecycle_action(record: LifecycleActionRecord) -> str:
        return render_markdown(
            MarkdownDocument(
                attributes={
                    "schema": "agora/lifecycle-action/v1",
                    "id": record.id,
                    "action": record.action,
                    "actor": record.actor,
                    "swarm": record.swarm_id,
                    "work": record.work_id,
                    "parameters": record.parameters,
                    "precondition-sha256": record.precondition_sha256,
                    "status": record.status,
                    "created-at": record.created_at,
                    "applied-at": record.applied_at,
                    "authentication-verified": record.authentication_verified,
                    "authentication-fingerprint": record.authentication_fingerprint,
                    "authentication-public-key": record.authentication_public_key,
                    "authorization-sha256": record.authorization_sha256,
                    "authorization-signature": record.authorization_signature,
                },
                body=(
                    f"# Lifecycle Action {record.id}\n\n"
                    "This durable intent binds an actor, a governed mutation, its parameters, "
                    "and the durable state against which it was authorized."
                ),
            )
        )

    @staticmethod
    def _load_lifecycle_action(path: Path) -> LifecycleActionRecord:
        document = read_markdown(path / "ACTION.md")
        _assert_schema(document, "agora/lifecycle-action/v1", path / "ACTION.md")
        action = string_attribute(document.attributes, "action")
        if action not in {
            "actor.key.recover",
            "actor.key.revoke",
            "actor.key.rotate",
            "actor.runtime.update",
            "approval.add",
            "approval.delegate",
            "approval.delegation.revoke",
            "artifact.add",
            "criterion.satisfy",
            "delegation.accept",
            "delegation.block",
            "delegation.cancel",
            "delegation.collect",
            "delegation.create",
            "delegation.reject",
            "delegation.resume",
            "evidence.add",
            "usage.add",
            "gate.waive",
            "handoff.create",
            "session.prepare",
            "swarm.assign",
            "work.block",
            "work.cancel",
            "work.decompose",
            "work.resume",
            "work.transition",
            "work.create",
        }:
            raise ValueError(f"Unsupported Lifecycle Action kind: {action}")
        status = string_attribute(document.attributes, "status")
        if status not in {"prepared", "applied"}:
            raise ValueError(f"Unsupported Lifecycle Action status: {status}")
        parameters = record_attribute(document.attributes, "parameters")
        if any(not isinstance(value, str) for value in parameters.values()):
            raise ValueError(f"Lifecycle Action parameters must contain string values: {path}")
        expected_parameters = {
            "actor.key.recover": {
                "target",
                "from",
                "public-key",
                "fingerprint",
                "reason",
            },
            "actor.key.revoke": {"target", "fingerprint", "reason"},
            "actor.key.rotate": {"from", "public-key", "fingerprint", "reason"},
            "actor.runtime.update": {"integration", "provider", "model", "clear"},
            "approval.add": {"role", "note", "delegation"},
            "approval.delegate": {"delegation", "role", "target", "reason"},
            "approval.delegation.revoke": {"delegation", "reason"},
            "artifact.add": {"kind", "uri"},
            "criterion.satisfy": {"criterion"},
            "delegation.accept": {"delegation"},
            "delegation.block": {"delegation", "reason"},
            "delegation.cancel": {"delegation", "reason"},
            "delegation.collect": {"delegation"},
            "delegation.create": {
                "delegation",
                "child-actor",
                "child-work",
                "title",
                "description",
                "acceptance-criteria",
                "required-artifacts",
                "result-kind",
                "budget-limits",
                "artifact-promotions",
            },
            "delegation.reject": {"delegation", "reason"},
            "delegation.resume": {"delegation", "reason"},
            "evidence.add": {"type", "result", "artifacts"},
            "usage.add": {"usage", "amounts", "evidence"},
            "gate.waive": {
                "waiver",
                "gate",
                "criteria",
                "artifacts",
                "successful-evidence",
                "approvals",
                "reason",
                "evidence",
            },
            "handoff.create": {"role", "from", "to", "reason"},
            "session.prepare": {
                "session",
                "runner",
                "timeout-seconds",
                "max-output-bytes",
            },
            "swarm.assign": {"role", "target"},
            "work.block": {"reason"},
            "work.cancel": {"reason"},
            "work.resume": {"reason"},
            "work.transition": {"to"},
            "work.create": {
                "title",
                "description",
                "acceptance-criteria",
                "required-artifacts",
            },
            "work.decompose": {
                "child-work",
                "title",
                "description",
                "acceptance-criteria",
                "required-artifacts",
            },
        }[action]
        parameter_keys = set(parameters)
        optional_delegation_parameters = {"budget-limits", "artifact-promotions"}
        legacy_delegation_parameters = (
            action == "delegation.create"
            and (expected_parameters - parameter_keys).issubset(optional_delegation_parameters)
            and parameter_keys.issubset(expected_parameters)
        )
        legacy_approval_parameters = action == "approval.add" and parameter_keys == {"role", "note"}
        legacy_session_parameters = action == "session.prepare" and parameter_keys == {
            "session",
            "runner",
        }
        if (
            parameter_keys != expected_parameters
            and not legacy_delegation_parameters
            and not legacy_approval_parameters
            and not legacy_session_parameters
        ):
            raise ValueError(f"Lifecycle Action has invalid {action} parameters: {path}")
        if action in {"actor.key.recover", "actor.key.revoke", "actor.key.rotate"}:
            fingerprint_keys = (
                ("fingerprint",) if action == "actor.key.revoke" else ("from", "fingerprint")
            )
            for key in fingerprint_keys:
                if re.fullmatch(r"[0-9a-f]{64}", parameters[key]) is None:
                    raise ValueError(f"Lifecycle Action has invalid actor key fingerprint: {path}")
            if action != "actor.key.revoke":
                replacement = actor_key_from_public_key(
                    "project:validation",
                    parameters["public-key"],
                    Path("."),
                    "validation",
                )
                if replacement.fingerprint != parameters["fingerprint"]:
                    raise ValueError(f"Lifecycle Action actor key fingerprint mismatch: {path}")
            if not parameters["reason"].strip():
                raise ValueError(f"Lifecycle Action actor key reason cannot be empty: {path}")
            if (
                action in {"actor.key.recover", "actor.key.revoke"}
                and ":" not in parameters["target"]
            ):
                raise ValueError(f"Lifecycle Action target actor must be scoped: {path}")
        if action == "actor.runtime.update":
            if parameters["integration"] and parameters["integration"] not in INTEGRATIONS:
                raise ValueError(f"Lifecycle Action has invalid runtime integration: {path}")
            if parameters["clear"] not in {"true", "false"}:
                raise ValueError(f"Lifecycle Action has invalid runtime clear flag: {path}")
            if parameters["clear"] == "false" and not any(
                parameters[key] for key in ("integration", "provider", "model")
            ):
                raise ValueError(f"Lifecycle Action has no runtime change: {path}")
        if action == "handoff.create":
            assert_slug(parameters["role"], "Lifecycle Action handoff role")
            if not parameters["reason"].strip():
                raise ValueError(f"Lifecycle Action handoff reason cannot be empty: {path}")
            if any(":" not in parameters[key] for key in ("from", "to")):
                raise ValueError(
                    f"Lifecycle Action handoff actors must use scoped references: {path}"
                )
        if action == "session.prepare":
            assert_slug(parameters["session"], "Lifecycle Action session id")
        if action == "swarm.assign":
            assert_slug(parameters["role"], "Lifecycle Action assignment role")
            if ":" not in parameters["target"]:
                raise ValueError(f"Lifecycle Action target actor must be scoped: {path}")
        if action in {"approval.delegate", "approval.delegation.revoke"}:
            assert_slug(parameters["delegation"], "Lifecycle Action Approval Delegation id")
            if not parameters["reason"].strip():
                raise ValueError(
                    f"Lifecycle Action Approval Delegation reason cannot be empty: {path}"
                )
        if action == "approval.delegate":
            assert_slug(parameters["role"], "Lifecycle Action delegated approval role")
            if ":" not in parameters["target"]:
                raise ValueError(
                    f"Lifecycle Action Approval Delegation target must be scoped: {path}"
                )
        if action == "approval.add" and parameters.get("delegation"):
            assert_slug(
                parameters["delegation"], "Lifecycle Action consumed Approval Delegation id"
            )
        if action.startswith("delegation."):
            assert_slug(parameters["delegation"], "Lifecycle Action delegation id")
        if action == "delegation.create":
            assert_slug(parameters["child-work"], "Lifecycle Action child work id")
            assert_slug(parameters["result-kind"], "Lifecycle Action result kind")
            if ":" not in parameters["child-actor"]:
                raise ValueError(
                    f"Lifecycle Action child actor must use a scoped reference: {path}"
                )
            try:
                criteria = json.loads(parameters["acceptance-criteria"])
                artifacts = json.loads(parameters["required-artifacts"])
                budgets = (
                    json.loads(parameters["budget-limits"])
                    if "budget-limits" in parameters
                    else None
                )
                promotions = (
                    json.loads(parameters["artifact-promotions"])
                    if "artifact-promotions" in parameters
                    else {}
                )
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"Lifecycle Action has invalid delegation JSON parameters: {path}"
                ) from error
            if not isinstance(criteria, list) or any(
                not isinstance(item, list)
                or len(item) != 2
                or any(not isinstance(value, str) for value in item)
                for item in criteria
            ):
                raise ValueError(
                    f"Lifecycle Action has invalid delegation acceptance criteria: {path}"
                )
            if not isinstance(artifacts, list) or any(
                not isinstance(value, str) for value in artifacts
            ):
                raise ValueError(
                    f"Lifecycle Action has invalid delegation required artifacts: {path}"
                )
            if budgets is not None and (
                not isinstance(budgets, dict)
                or any(
                    not isinstance(name, str)
                    or not isinstance(limit, int)
                    or isinstance(limit, bool)
                    or limit < 0
                    for name, limit in budgets.items()
                )
            ):
                raise ValueError(f"Lifecycle Action has invalid delegation budgets: {path}")
            for dimension in budgets or {}:
                assert_slug(dimension, "Lifecycle Action delegation budget dimension")
            if not isinstance(promotions, dict) or any(
                not isinstance(source, str) or not isinstance(target, str)
                for source, target in promotions.items()
            ):
                raise ValueError(
                    f"Lifecycle Action has invalid delegation artifact promotions: {path}"
                )
            AgoraWorkspace._normalize_artifact_promotions(promotions)
        if action in {"work.create", "work.decompose"}:
            if action == "work.decompose":
                assert_slug(parameters["child-work"], "Lifecycle Action child work id")
            try:
                criteria = json.loads(parameters["acceptance-criteria"])
                artifacts = json.loads(parameters["required-artifacts"])
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"Lifecycle Action has invalid work JSON parameters: {path}"
                ) from error
            if not isinstance(criteria, list) or any(
                not isinstance(item, list)
                or len(item) != 2
                or any(not isinstance(value, str) for value in item)
                for item in criteria
            ):
                raise ValueError(f"Lifecycle Action has invalid work acceptance criteria: {path}")
            if not isinstance(artifacts, list) or any(
                not isinstance(value, str) for value in artifacts
            ):
                raise ValueError(f"Lifecycle Action has invalid work required artifacts: {path}")
        if action == "evidence.add":
            if parameters["result"] not in {"success", "failure"}:
                raise ValueError(f"Lifecycle Action has invalid evidence result: {path}")
            try:
                artifacts = json.loads(parameters["artifacts"])
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"Lifecycle Action has invalid evidence artifacts: {path}"
                ) from error
            if not isinstance(artifacts, list) or any(
                not isinstance(value, str) for value in artifacts
            ):
                raise ValueError(f"Lifecycle Action evidence artifacts must be strings: {path}")
        if action == "usage.add":
            assert_slug(parameters["usage"], "Lifecycle Action usage id")
            try:
                amounts = json.loads(parameters["amounts"])
                evidence = json.loads(parameters["evidence"])
            except json.JSONDecodeError as error:
                raise ValueError(f"Lifecycle Action has invalid usage JSON: {path}") from error
            if not isinstance(amounts, dict):
                raise ValueError(f"Lifecycle Action usage amounts must be a map: {path}")
            AgoraWorkspace._normalize_usage_amounts(amounts)
            if (
                not isinstance(evidence, list)
                or not evidence
                or any(
                    not isinstance(reference, str) or not reference.strip()
                    for reference in evidence
                )
            ):
                raise ValueError(
                    f"Lifecycle Action usage evidence must be non-empty strings: {path}"
                )
        if action == "gate.waive":
            assert_slug(parameters["waiver"], "Lifecycle Action Gate Waiver id")
            assert_slug(parameters["gate"], "Lifecycle Action gate id")
            if parameters["successful-evidence"] not in {"true", "false"}:
                raise ValueError(
                    f"Lifecycle Action has invalid successful evidence waiver flag: {path}"
                )
            if not parameters["reason"].strip():
                raise ValueError(f"Lifecycle Action Gate Waiver reason cannot be empty: {path}")
            parsed_lists: dict[str, list[str]] = {}
            for key in ("criteria", "artifacts", "approvals", "evidence"):
                try:
                    value = json.loads(parameters[key])
                except json.JSONDecodeError as error:
                    raise ValueError(
                        f"Lifecycle Action has invalid Gate Waiver {key}: {path}"
                    ) from error
                if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                    raise ValueError(
                        f"Lifecycle Action Gate Waiver {key} must be a string list: {path}"
                    )
                parsed_lists[key] = value
            if not parsed_lists["evidence"] or any(
                not item.strip() for item in parsed_lists["evidence"]
            ):
                raise ValueError(
                    f"Lifecycle Action Gate Waiver requires risk evidence references: {path}"
                )
            if (
                not parsed_lists["criteria"]
                and not parsed_lists["artifacts"]
                and parameters["successful-evidence"] == "false"
                and not parsed_lists["approvals"]
            ):
                raise ValueError(f"Lifecycle Action Gate Waiver must name an obligation: {path}")
        reason_actions = {
            "delegation.block",
            "delegation.cancel",
            "delegation.reject",
            "delegation.resume",
            "work.block",
            "work.cancel",
            "work.resume",
        }
        if action in reason_actions and not parameters["reason"].strip():
            raise ValueError(f"Lifecycle Action status reason cannot be empty: {path}")
        precondition_sha256 = string_attribute(document.attributes, "precondition-sha256")
        authentication_verified = _boolean_attribute_default(
            document.attributes, "authentication-verified", False
        )
        authentication_fingerprint = optional_string_attribute(
            document.attributes, "authentication-fingerprint"
        )
        authentication_public_key = optional_string_attribute(
            document.attributes, "authentication-public-key"
        )
        authorization_sha256 = optional_string_attribute(
            document.attributes, "authorization-sha256"
        )
        authorization_signature = optional_string_attribute(
            document.attributes, "authorization-signature"
        )
        authentication_values = (
            authentication_fingerprint,
            authentication_public_key,
            authorization_sha256,
            authorization_signature,
        )
        if authentication_verified and any(value is None for value in authentication_values):
            raise ValueError(
                f"Verified Lifecycle Action authentication evidence is incomplete: {path}"
            )
        if not authentication_verified and any(
            value is not None for value in authentication_values
        ):
            raise ValueError(
                f"Unverified Lifecycle Action cannot contain authentication evidence: {path}"
            )
        applied_at = optional_string_attribute(document.attributes, "applied-at")
        if status == "prepared" and applied_at is not None:
            raise ValueError(f"Prepared Lifecycle Action cannot have applied-at: {path}")
        if status == "applied" and applied_at is None:
            raise ValueError(f"Applied Lifecycle Action requires applied-at: {path}")
        if any(
            re.fullmatch(r"[0-9a-f]{64}", value) is None
            for value in (
                precondition_sha256,
                *(
                    value
                    for value in (authentication_fingerprint, authorization_sha256)
                    if value is not None
                ),
            )
        ):
            raise ValueError(f"Lifecycle Action digests must be SHA-256 values: {path}")
        work_id = optional_string_attribute(document.attributes, "work")
        if (
            action
            not in {
                "actor.key.recover",
                "actor.key.revoke",
                "actor.key.rotate",
                "actor.runtime.update",
                "handoff.create",
                "session.prepare",
                "swarm.assign",
            }
            and work_id is None
        ):
            raise ValueError(f"Lifecycle Action {action} requires work: {path}")
        record = LifecycleActionRecord(
            id=string_attribute(document.attributes, "id"),
            action=action,
            actor=string_attribute(document.attributes, "actor"),
            swarm_id=string_attribute(document.attributes, "swarm"),
            work_id=work_id,
            parameters=parameters,
            precondition_sha256=precondition_sha256,
            status=status,  # type: ignore[arg-type]
            path=str(path),
            created_at=string_attribute(document.attributes, "created-at"),
            applied_at=applied_at,
            authentication_verified=authentication_verified,
            authentication_fingerprint=authentication_fingerprint,
            authentication_public_key=authentication_public_key,
            authorization_sha256=authorization_sha256,
            authorization_signature=authorization_signature,
        )
        validate_persisted_lifecycle_authorization(record)
        return record

    @staticmethod
    def _render_session(record: SessionRecord) -> str:
        attributes = {
            "schema": "agora/session/v1",
            "id": record.id,
            "actor": record.actor,
            "swarm": record.swarm_id,
            "work": record.work_id,
            "roles": record.roles,
            "integration": record.integration,
            "provider": record.provider,
            "model": record.model,
            "status": record.status,
            "context": record.context_path,
            "launch-command": record.launch_command,
            "runtime-available": record.runtime_available,
            "created-at": record.created_at,
            "exit-code": record.exit_code,
            "timeout-seconds": record.timeout_seconds,
            "max-output-bytes": record.max_output_bytes,
            "output-bytes": record.output_bytes,
            "termination-reason": record.termination_reason,
            "context-sha256": record.context_sha256,
            "authentication-verified": record.authentication_verified,
            "authentication-fingerprint": record.authentication_fingerprint,
            "authentication-public-key": record.authentication_public_key,
            "authorization-sha256": record.authorization_sha256,
            "authorization-signature": record.authorization_signature,
            "preparation-action": record.preparation_action_id,
        }
        return render_markdown(
            MarkdownDocument(
                attributes=attributes,
                body=(
                    f"# Agora session {record.id}\n\n"
                    "The session context and runtime selection are durable. Model conversation "
                    "history is not project state unless its outcome is recorded in Agora files."
                ),
            )
        )

    def _load_session(self, path: Path) -> SessionRecord:
        document = read_markdown(path / "SESSION.md")
        _assert_schema(document, "agora/session/v1", path / "SESSION.md")
        status = string_attribute(document.attributes, "status")
        if status not in {"prepared", "running", "completed", "failed"}:
            raise ValueError(f"Unsupported session status: {status}")
        authentication_verified = _boolean_attribute_default(
            document.attributes, "authentication-verified", False
        )
        authentication_fingerprint = optional_string_attribute(
            document.attributes, "authentication-fingerprint"
        )
        authentication_public_key = optional_string_attribute(
            document.attributes, "authentication-public-key"
        )
        authorization_sha256 = optional_string_attribute(
            document.attributes, "authorization-sha256"
        )
        authorization_signature = optional_string_attribute(
            document.attributes, "authorization-signature"
        )
        authentication_values = (
            authentication_fingerprint,
            authentication_public_key,
            authorization_sha256,
            authorization_signature,
        )
        if authentication_verified and any(value is None for value in authentication_values):
            raise ValueError(f"Verified Session authentication evidence is incomplete: {path}")
        if not authentication_verified and any(
            value is not None for value in authentication_values
        ):
            raise ValueError(f"Unverified Session cannot contain authentication evidence: {path}")
        context_sha256 = optional_string_attribute(document.attributes, "context-sha256")
        if any(
            value is not None and re.fullmatch(r"[0-9a-f]{64}", value) is None
            for value in (context_sha256, authentication_fingerprint, authorization_sha256)
        ):
            raise ValueError(f"Session digests must be SHA-256 values: {path}")
        preparation_action_id = optional_string_attribute(document.attributes, "preparation-action")
        if preparation_action_id is not None:
            assert_slug(preparation_action_id, "Session preparation action id")
        termination_reason = optional_string_attribute(document.attributes, "termination-reason")
        if termination_reason not in {
            None,
            "timeout",
            "output-limit",
            "launcher-error",
            "nonzero-exit",
        }:
            raise ValueError(f"Unsupported Session termination reason: {termination_reason}")
        if status in {"prepared", "running"} and termination_reason is not None:
            raise ValueError(f"Unfinished Session cannot have a termination reason: {path}")
        if status == "completed" and termination_reason is not None:
            raise ValueError(f"Completed Session cannot have a termination reason: {path}")
        record = SessionRecord(
            id=string_attribute(document.attributes, "id"),
            actor=string_attribute(document.attributes, "actor"),
            swarm_id=string_attribute(document.attributes, "swarm"),
            work_id=optional_string_attribute(document.attributes, "work"),
            roles=strings_attribute(document.attributes, "roles"),
            integration=self._integration(string_attribute(document.attributes, "integration")),
            provider=string_attribute(document.attributes, "provider"),
            model=string_attribute(document.attributes, "model"),
            status=status,
            path=str(path),
            context_path=string_attribute(document.attributes, "context"),
            launch_command=strings_attribute(document.attributes, "launch-command"),
            runtime_available=_boolean_attribute(document.attributes, "runtime-available"),
            created_at=string_attribute(document.attributes, "created-at"),
            exit_code=_optional_integer_attribute(document.attributes, "exit-code"),
            timeout_seconds=_positive_integer_attribute_default(
                document.attributes,
                "timeout-seconds",
                DEFAULT_SESSION_TIMEOUT_SECONDS,
                MAX_SESSION_TIMEOUT_SECONDS,
            ),
            max_output_bytes=_positive_integer_attribute_default(
                document.attributes,
                "max-output-bytes",
                DEFAULT_SESSION_MAX_OUTPUT_BYTES,
                MAX_SESSION_MAX_OUTPUT_BYTES,
            ),
            output_bytes=_nonnegative_integer_attribute_default(
                document.attributes, "output-bytes", 0
            ),
            termination_reason=termination_reason,
            context_sha256=context_sha256,
            authentication_verified=authentication_verified,
            authentication_fingerprint=authentication_fingerprint,
            authentication_public_key=authentication_public_key,
            authorization_sha256=authorization_sha256,
            authorization_signature=authorization_signature,
            preparation_action_id=preparation_action_id,
        )
        validate_persisted_session_authorization(record)
        return record

    @staticmethod
    def _render_session_result(record: SessionRecord, stdout: str, stderr: str) -> str:
        def block(value: str) -> str:
            lines = value.rstrip().splitlines() or ["(empty)"]
            return "\n".join(f"    {line}" for line in lines)

        return render_markdown(
            MarkdownDocument(
                attributes={
                    "schema": "agora/session-result/v1",
                    "session": record.id,
                    "status": record.status,
                    "exit-code": record.exit_code,
                    "output-bytes": record.output_bytes,
                    "termination-reason": record.termination_reason,
                },
                body=(
                    f"# Session result {record.id}\n\n## Standard output\n\n{block(stdout)}\n\n"
                    f"## Standard error\n\n{block(stderr)}"
                ),
            )
        )

    @staticmethod
    def _validate_session_result(record: SessionRecord) -> None:
        path = Path(record.path) / "RESULT.md"
        document = read_markdown(path)
        _assert_schema(document, "agora/session-result/v1", path)
        attributes = document.attributes
        if string_attribute(attributes, "session") != record.id:
            raise ValueError(f"Session result id does not match SESSION.md: {path}")
        if string_attribute(attributes, "status") != record.status:
            raise ValueError(f"Session result status does not match SESSION.md: {path}")
        if _optional_integer_attribute(attributes, "exit-code") != record.exit_code:
            raise ValueError(f"Session result exit code does not match SESSION.md: {path}")
        if (
            _nonnegative_integer_attribute_default(attributes, "output-bytes", 0)
            != record.output_bytes
        ):
            raise ValueError(f"Session result output size does not match SESSION.md: {path}")
        if optional_string_attribute(attributes, "termination-reason") != record.termination_reason:
            raise ValueError(f"Session result termination reason does not match SESSION.md: {path}")

    def _render_session_context(
        self,
        root: Path,
        project: ProjectConfiguration,
        actor: ActorRecord,
        swarm: SwarmRecord,
        roles: list[str],
        work: WorkRecord | None,
        integration: Integration,
        provider: str,
        model: str,
    ) -> str:
        method_root = root / ".agora" / "methods" / swarm.method
        swarm_root = Path(swarm.path)
        role_paths = [method_root / "roles" / f"{role}.md" for role in roles]
        environment_paths = sorted((root / ".agora" / "environments").glob("*.md"))
        handoff_paths = sorted((swarm_root / "handoffs").glob("*/HANDOFF.md"))
        delegation_paths = self._related_delegation_paths(
            root, swarm.id, work.id if work is not None else None
        )
        represented_paths: list[Path] = []
        if actor.represented_swarm is not None:
            for represented_id in self._delegated_swarm_ids(root, actor.represented_swarm):
                represented_root = root / ".agora" / "swarms" / represented_id
                represented_paths.extend(
                    [
                        represented_root / "SWARM.md",
                        represented_root / "events.md",
                        *sorted((represented_root / "handoffs").glob("*/HANDOFF.md")),
                    ]
                )
        required_reading = [
            root / ".agora" / "project.md",
            root / ".agora" / "constitution.md",
            root / ".agora" / "PROTOCOL.md",
            root / ".agora" / "STANDARDS.md",
            root / ".agora" / "coordination.md",
            root / ".agora" / "tools" / "TOOLS.md",
            swarm_root / "SWARM.md",
            swarm_root / "events.md",
            method_root / "METHOD.md",
            method_root / "PROTOCOL.md",
            method_root / "TOOLS.md",
            *role_paths,
            *environment_paths,
            *handoff_paths,
            *delegation_paths,
            *represented_paths,
        ]
        if work is not None:
            required_reading.extend(
                [
                    Path(work.path) / "WORK.md",
                    Path(work.path) / "artifacts.md",
                    Path(work.path) / "evidence.md",
                    Path(work.path) / "approvals.md",
                    *sorted((Path(work.path) / "waivers").glob("*/WAIVER.md")),
                    *sorted((Path(work.path) / "approval-delegations").glob("*/DELEGATION.md")),
                ]
            )
        reading = "\n".join(
            f"- `{path.relative_to(root)}`" for path in required_reading if path.exists()
        )
        work_context = (
            (
                f"## Active work\n\n- Id: `{work.id}`\n- Title: {work.title}\n"
                f"- State: `{work.state}`\n- Path: `{Path(work.path).relative_to(root)}`\n\n"
            )
            if work is not None
            else "## Active work\n\nNo work item was selected for this session.\n\n"
        )
        return (
            f"# Agora session context\n\n"
            f"## Project\n\n- Name: {project.project}\n- Root: `{root}`\n\n"
            f"## Runtime\n\n- Integration: `{integration}`\n- Provider: `{provider}`\n"
            f"- Model: `{model}`\n\n"
            f"## Actor\n\n- Identity: `{actor.reference}`\n- Kind: `{actor.kind}`\n"
            f"- Roles: {', '.join(f'`{role}`' for role in roles)}\n"
            f"- Capabilities: {', '.join(f'`{item}`' for item in actor.capabilities)}\n"
            f"- Represented swarm: `{actor.represented_swarm or 'none'}`\n\n"
            f"## Swarm\n\n- Id: `{swarm.id}`\n- Method: `{swarm.method}`\n"
            f"- Objective: {swarm.objective}\n\n{work_context}"
            f"## Required reading\n\n{reading}\n\n"
            "## Operating rules\n\n"
            "1. Read every available file listed above before acting.\n"
            "2. Perform only actions allowed to the assigned role and active transition.\n"
            "3. Use the Agora CLI to persist state, artifacts, evidence, and material outcomes.\n"
            "4. Do not treat unrecorded conversation history as durable project state.\n"
            "5. Stop when policy, permissions, or a gate cannot be satisfied.\n"
        )

    def _related_delegation_paths(
        self, root: Path, swarm_id: str, work_id: str | None
    ) -> list[Path]:
        paths: list[Path] = []
        delegation_root = root / ".agora" / "delegations"
        for path in sorted(delegation_root.glob("*/DELEGATION.md")):
            delegation = self._load_delegation(root, path.parent.name)
            parent_match = delegation.parent_swarm_id == swarm_id and (
                work_id is None or delegation.parent_work_id == work_id
            )
            child_match = delegation.child_swarm_id == swarm_id and (
                work_id is None or delegation.child_work_id == work_id
            )
            if parent_match or child_match:
                paths.append(path)
        return paths

    @staticmethod
    def _method_pack_record(contract: MethodContract, scope: str, path: Path) -> MethodPackRecord:
        source = read_pack_source(path / "SOURCE.md") if (path / "SOURCE.md").is_file() else None
        updates = load_pack_update_history(path, "method", contract.id)
        if source is not None and (
            source.kind != "method"
            or source.id != contract.id
            or source.version != contract.version
        ):
            raise ValueError(f"Method Pack source does not match its manifest: {path}")
        if updates and (
            source is None
            or updates[-1].to_version != source.version
            or updates[-1].to_sha256 != source.sha256
        ):
            raise ValueError(f"Method Pack update history does not match its source: {path}")
        return MethodPackRecord(
            id=contract.id,
            name=contract.name,
            version=contract.version,
            dependencies=contract.dependencies,
            scope=scope,
            path=str(path),
            required_roles=contract.required_roles,
            work_states=contract.work_states,
            terminal_state=contract.terminal_state,
            source=source,
            updates=updates,
        )

    @staticmethod
    def _tool_pack_record(contract: ToolContract, scope: str, path: Path) -> ToolPackRecord:
        source = read_pack_source(path / "SOURCE.md") if (path / "SOURCE.md").is_file() else None
        updates = load_pack_update_history(path, "tool", contract.id)
        if source is not None and (
            source.kind != "tool" or source.id != contract.id or source.version != contract.version
        ):
            raise ValueError(f"Tool Pack source does not match its manifest: {path}")
        if updates and (
            source is None
            or updates[-1].to_version != source.version
            or updates[-1].to_sha256 != source.sha256
        ):
            raise ValueError(f"Tool Pack update history does not match its source: {path}")
        return ToolPackRecord(
            id=contract.id,
            name=contract.name,
            version=contract.version,
            dependencies=contract.dependencies,
            category=contract.category,
            executable=contract.executable,
            scope=scope,
            path=str(path),
            operations=sorted(contract.operations),
            provider=contract.provider,
            transport=contract.transport,
            implements=contract.implements,
            implements_operations=contract.implements_operations,
            version_command=contract.version_command,
            minimum_runtime_version=contract.minimum_runtime_version,
            timeout_seconds=contract.timeout_seconds,
            max_output_bytes=contract.max_output_bytes,
            source=source,
            updates=updates,
        )

    @staticmethod
    def _render_environment(record: EnvironmentPolicyRecord) -> str:
        return render_markdown(
            MarkdownDocument(
                attributes={
                    "schema": "agora/environment-policy/v1",
                    "id": record.id,
                    "name": record.name,
                    "allowed-tool-capabilities": record.allowed_tool_capabilities,
                    "required-approval-roles": record.required_approval_roles,
                    "require-successful-evidence": record.require_successful_evidence,
                },
                body=(
                    f"# {record.name}\n\n"
                    "This policy limits governed Tool Runs for one project-defined environment. "
                    "Provider targets and credentials remain in reviewed adapters and external "
                    "runtime configuration."
                ),
            )
        )

    @staticmethod
    def _load_environment(path: Path) -> EnvironmentPolicyRecord:
        document = read_markdown(path)
        _assert_schema(document, "agora/environment-policy/v1", path)
        environment_id = string_attribute(document.attributes, "id")
        assert_slug(environment_id, "Environment id")
        capabilities = strings_attribute(document.attributes, "allowed-tool-capabilities")
        if not capabilities or len(set(capabilities)) != len(capabilities):
            raise ValueError(
                f"Environment {environment_id} must declare unique allowed tool capabilities"
            )
        for capability in capabilities:
            if CAPABILITY_PATTERN.fullmatch(capability) is None:
                raise ValueError(f"Invalid environment tool capability: {capability}")
        approval_roles = strings_attribute(document.attributes, "required-approval-roles")
        if len(set(approval_roles)) != len(approval_roles):
            raise ValueError(f"Environment {environment_id} approval roles must be unique")
        for role_id in approval_roles:
            assert_slug(role_id, "Environment approval role id")
        return EnvironmentPolicyRecord(
            id=environment_id,
            name=string_attribute(document.attributes, "name"),
            allowed_tool_capabilities=capabilities,
            required_approval_roles=approval_roles,
            require_successful_evidence=_boolean_attribute(
                document.attributes, "require-successful-evidence"
            ),
            path=str(path),
        )

    def _actor_tool_capabilities(
        self, root: Path, swarm: SwarmRecord, roles: list[str]
    ) -> set[str]:
        capabilities: set[str] = set()
        for role in roles:
            attributes = read_markdown(
                root / ".agora" / "methods" / swarm.method / "roles" / f"{role}.md"
            ).attributes
            value = attributes.get("allowed-tool-capabilities", [])
            if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                raise ValueError(f"Role {role} allowed-tool-capabilities must be a string array")
            capabilities.update(value)
        return capabilities

    def _assert_environment_permission(
        self,
        root: Path,
        swarm: SwarmRecord,
        roles: list[str],
        capability: str,
        environment_id: str | None,
        environment_required: bool,
        work: WorkRecord | None,
    ) -> None:
        if environment_id is None:
            if environment_required:
                raise ValueError(f"Tool capability {capability} requires a governed environment")
            return
        assert_slug(environment_id, "Environment id")
        policy = self._load_environment(root / ".agora" / "environments" / f"{environment_id}.md")
        if policy.id != environment_id:
            raise ValueError(
                f"Environment id {policy.id} does not match policy filename {environment_id}"
            )
        if capability not in policy.allowed_tool_capabilities:
            raise PermissionError(
                f"Environment {environment_id} does not allow tool capability {capability}"
            )

        permitted_roles: list[str] = []
        for role_id in roles:
            attributes = read_markdown(
                root / ".agora" / "methods" / swarm.method / "roles" / f"{role_id}.md"
            ).attributes
            capabilities = strings_attribute(attributes, "allowed-tool-capabilities")
            environments = attributes.get("allowed-environments", ["*"])
            if not isinstance(environments, list) or any(
                not isinstance(item, str) or not item for item in environments
            ):
                raise ValueError(f"Role {role_id} allowed-environments must be a string array")
            if capability in capabilities and (
                "*" in environments or environment_id in environments
            ):
                permitted_roles.append(role_id)
        if not permitted_roles:
            raise PermissionError(
                f"Actor roles do not allow tool capability {capability} in environment "
                f"{environment_id}"
            )

        if policy.required_approval_roles or policy.require_successful_evidence:
            if work is None:
                raise ValueError(
                    f"Environment {environment_id} requires governed work for its approvals "
                    "or evidence"
                )
            missing_roles = sorted(set(policy.required_approval_roles) - set(work.approval_roles))
            if missing_roles:
                raise PermissionError(
                    f"Environment {environment_id} requires approval from: "
                    f"{', '.join(missing_roles)}"
                )
            if policy.require_successful_evidence and "success" not in work.evidence_results:
                raise PermissionError(
                    f"Environment {environment_id} requires successful work evidence"
                )

    @staticmethod
    def _substitute_tool_inputs(argument: str, inputs: dict[str, str]) -> str:
        rendered = argument
        for input_id, value in inputs.items():
            rendered = rendered.replace(f"{{{input_id}}}", value)
        return rendered

    @staticmethod
    def _render_tool_run(record: ToolRunRecord, contract: ToolContract) -> str:
        return render_markdown(
            MarkdownDocument(
                attributes={
                    "schema": "agora/tool-run/v1",
                    "id": record.id,
                    "tool": record.tool_id,
                    "operation": record.operation_id,
                    "actor": record.actor,
                    "swarm": record.swarm_id,
                    "work": record.work_id,
                    "environment": record.environment_id,
                    "capability": record.capability,
                    "risk": record.risk,
                    "inputs": record.inputs,
                    "command": record.command,
                    "runtime-available": record.runtime_available,
                    "status": record.status,
                    "result-kind": record.result_kind,
                    "timeout-seconds": record.timeout_seconds,
                    "max-output-bytes": record.max_output_bytes,
                    "authentication-reference": contract.authentication_reference,
                    "created-at": record.created_at,
                    "exit-code": record.exit_code,
                    "authentication-verified": record.authentication_verified,
                    "authentication-fingerprint": record.authentication_fingerprint,
                    "authentication-public-key": record.authentication_public_key,
                    "authorization-sha256": record.authorization_sha256,
                    "authorization-signature": record.authorization_signature,
                },
                body=(
                    f"# Tool run {record.id}\n\n"
                    "This record contains invocation metadata, not credentials. Authentication is "
                    "resolved by the external executable and its environment."
                ),
            )
        )

    @staticmethod
    def _load_tool_run(path: Path) -> ToolRunRecord:
        document = read_markdown(path / "RUN.md")
        _assert_schema(document, "agora/tool-run/v1", path / "RUN.md")
        risk = string_attribute(document.attributes, "risk")
        if risk not in {"read", "write", "destructive"}:
            raise ValueError(f"Unsupported tool run risk: {risk}")
        status = string_attribute(document.attributes, "status")
        if status not in {"prepared", "running", "completed", "failed"}:
            raise ValueError(f"Unsupported tool run status: {status}")
        authentication_verified = _boolean_attribute_default(
            document.attributes, "authentication-verified", False
        )
        authentication_fingerprint = optional_string_attribute(
            document.attributes, "authentication-fingerprint"
        )
        authentication_public_key = optional_string_attribute(
            document.attributes, "authentication-public-key"
        )
        authorization_sha256 = optional_string_attribute(
            document.attributes, "authorization-sha256"
        )
        authorization_signature = optional_string_attribute(
            document.attributes, "authorization-signature"
        )
        timeout_seconds = _positive_integer_attribute_default(
            document.attributes,
            "timeout-seconds",
            DEFAULT_TOOL_TIMEOUT_SECONDS,
            MAX_TOOL_TIMEOUT_SECONDS,
        )
        max_output_bytes = _positive_integer_attribute_default(
            document.attributes,
            "max-output-bytes",
            DEFAULT_TOOL_MAX_OUTPUT_BYTES,
            MAX_TOOL_MAX_OUTPUT_BYTES,
        )
        authentication_values = (
            authentication_fingerprint,
            authentication_public_key,
            authorization_sha256,
            authorization_signature,
        )
        if authentication_verified and any(value is None for value in authentication_values):
            raise ValueError(
                f"Verified Tool Run authentication requires fingerprint and payload digest: {path}"
            )
        if not authentication_verified and any(
            value is not None for value in authentication_values
        ):
            raise ValueError(f"Unverified Tool Run cannot contain authentication evidence: {path}")
        if any(
            value is not None and re.fullmatch(r"[0-9a-f]{64}", value) is None
            for value in (authentication_fingerprint, authorization_sha256)
        ):
            raise ValueError(f"Tool Run authentication digests must be SHA-256 values: {path}")
        record = ToolRunRecord(
            id=string_attribute(document.attributes, "id"),
            tool_id=string_attribute(document.attributes, "tool"),
            operation_id=string_attribute(document.attributes, "operation"),
            actor=string_attribute(document.attributes, "actor"),
            swarm_id=string_attribute(document.attributes, "swarm"),
            work_id=optional_string_attribute(document.attributes, "work"),
            environment_id=optional_string_attribute(document.attributes, "environment"),
            capability=string_attribute(document.attributes, "capability"),
            risk=_tool_risk(risk),
            inputs=record_attribute(document.attributes, "inputs"),
            command=strings_attribute(document.attributes, "command"),
            runtime_available=_boolean_attribute(document.attributes, "runtime-available"),
            status=status,
            path=str(path),
            created_at=string_attribute(document.attributes, "created-at"),
            result_kind=optional_string_attribute(document.attributes, "result-kind"),
            exit_code=_optional_integer_attribute(document.attributes, "exit-code"),
            authentication_verified=authentication_verified,
            authentication_fingerprint=authentication_fingerprint,
            authentication_public_key=authentication_public_key,
            authorization_sha256=authorization_sha256,
            authorization_signature=authorization_signature,
            timeout_seconds=timeout_seconds,
            max_output_bytes=max_output_bytes,
        )
        if record.environment_id is not None:
            assert_slug(record.environment_id, "Tool Run environment id")
        validate_persisted_tool_authorization(record)
        return record

    @staticmethod
    def _render_tool_result(record: ToolRunRecord, stdout: str, stderr: str) -> str:
        def block(value: str) -> str:
            lines = value.rstrip().splitlines() or ["(empty)"]
            return "\n".join(f"    {line}" for line in lines)

        return render_markdown(
            MarkdownDocument(
                attributes={
                    "schema": "agora/tool-result/v1",
                    "run": record.id,
                    "status": record.status,
                    "exit-code": record.exit_code,
                    "result-kind": record.result_kind,
                },
                body=(
                    f"# Tool result {record.id}\n\n## Standard output\n\n{block(stdout)}\n\n"
                    f"## Standard error\n\n{block(stderr)}"
                ),
            )
        )

    def _assert_wip_limit(
        self,
        swarm: SwarmRecord,
        work: WorkRecord,
        target_state: str,
        limits: dict[str, int],
    ) -> None:
        limit = limits.get(target_state)
        if limit is None:
            return
        work_root = Path(swarm.path) / "work"
        active = sum(
            1
            for path in work_root.iterdir()
            if path.is_dir()
            and path.name != work.id
            and (item := self._load_work(swarm, path.name)).state == target_state
            and item.operational_status != "cancelled"
        )
        if active >= limit:
            raise ValueError(
                f"WIP limit reached for {target_state}: limit={limit}, active={active}"
            )

    def _assert_work_gate(self, work: WorkRecord, gate: GatePolicy, gate_id: str) -> None:
        waived_criteria, waived_artifacts, waived_evidence, waived_approvals = (
            self._gate_waiver_coverage(work, gate_id)
        )
        unsatisfied = (
            [
                item
                for item in work.acceptance_criteria
                if item not in work.satisfied_criteria and item not in waived_criteria
            ]
            if gate.require_all_criteria
            else []
        )
        missing_artifacts = (
            [
                item
                for item in work.required_artifacts
                if item not in work.artifact_kinds and item not in waived_artifacts
            ]
            if gate.require_required_artifacts
            else []
        )
        has_success = "success" in work.evidence_results
        evidence_missing = (
            gate.require_successful_evidence and not has_success and not waived_evidence
        )
        missing_approvals = [
            role
            for role in gate.required_approval_roles
            if role not in work.approval_roles and role not in waived_approvals
        ]
        if unsatisfied or missing_artifacts or evidence_missing or missing_approvals:
            raise ValueError(
                f"Gate {gate_id} failed: unsatisfied=[{', '.join(unsatisfied)}], "
                f"missing-artifacts=[{', '.join(missing_artifacts)}], "
                f"successful-evidence={str(has_success).lower()}, "
                f"missing-approvals=[{', '.join(missing_approvals)}]"
            )

    def _append_swarm_event(self, root: Path, swarm_id: str, type_: str, detail: str) -> None:
        append_entry(
            root / ".agora" / "swarms" / swarm_id / "events.md",
            f"- {self._timestamp()} | {type_} | {detail}",
        )

    def _append_work_event(self, work: WorkRecord, type_: str, detail: str) -> None:
        path = Path(work.path) / "events.md"
        if not path.exists():
            write_new(path, "# Work events\n\n")
        append_entry(path, f"- {self._timestamp()} | {type_} | {detail}")

    def _append_tool_event(self, root: Path, record: ToolRunRecord, status: str) -> None:
        append_entry(
            root / ".agora" / "events.md",
            (
                f"- {self._timestamp()} | tool.{status} | run={record.id} "
                f"tool={record.tool_id} operation={record.operation_id} actor={record.actor}"
            ),
        )

    @staticmethod
    def _read_events(path: Path, scope: str) -> list[EventRecord]:
        records: list[EventRecord] = []
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.startswith("- "):
                continue
            parts = line[2:].split(" | ", 2)
            if len(parts) != 3 or any(not part.strip() for part in parts[:2]):
                raise ValueError(f"Invalid event entry at {path}:{number}")
            try:
                datetime.fromisoformat(parts[0].strip().replace("Z", "+00:00"))
            except ValueError as error:
                raise ValueError(f"Invalid event timestamp at {path}:{number}") from error
            records.append(
                EventRecord(
                    timestamp=parts[0].strip(),
                    type=parts[1].strip(),
                    detail=parts[2].strip(),
                    scope=scope,
                    path=str(path),
                )
            )
        return records

    @staticmethod
    def _assert_integration(value: str) -> None:
        if value not in INTEGRATIONS:
            raise ValueError(f"Unsupported integration: {value}. Choose {', '.join(INTEGRATIONS)}.")

    @staticmethod
    def _assert_delegation_depth(value: int) -> None:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("Maximum delegation depth must be a non-negative integer")

    @staticmethod
    def _delegation_depth(attributes: dict[str, object]) -> int:
        value = attributes.get("max-delegation-depth", 3)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("Maximum delegation depth must be a non-negative integer")
        return value

    @staticmethod
    def _assert_method_available(value: str, *method_roots: Path) -> None:
        assert_slug(value, "Method id")
        if not any((root / value / "METHOD.md").is_file() for root in method_roots):
            available = sorted(
                {
                    path.parent.name
                    for root in method_roots
                    if root.exists()
                    for path in root.glob("*/METHOD.md")
                }
            )
            detail = f" Available: {', '.join(available)}." if available else ""
            raise FileNotFoundError(f"Method Pack is not installed: {value}.{detail}")

    @staticmethod
    def _integration(value: str) -> Integration:
        AgoraWorkspace._assert_integration(value)
        return value  # type: ignore[return-value]

    @staticmethod
    def _method(value: str) -> Method:
        assert_slug(value, "Method id")
        return value

    def _timestamp(self) -> str:
        return self._now().astimezone(UTC).isoformat().replace("+00:00", "Z")

    def quickstart(self, data: QuickstartInput) -> QuickstartResult:
        target = (self.cwd / (data.path or ".")).resolve()
        project_path = target / ".agora" / "project.md"
        if project_path.is_file():
            project = self._load_project_configuration(target)
        else:
            project = self.initialize(InitInput(target=data.path, default_method=data.method))
        self.cwd = target

        method = data.method or project.default_method
        root = target
        contract = load_method_contract(root / ".agora" / "methods" / method)
        assert_slug(data.swarm_id, "Swarm id")
        if not data.objective.strip():
            raise ValueError("Quickstart objective cannot be empty")

        human_id = "owner"
        ai_id = "agent"
        reserved_paths = (
            root / ".agora" / "actors" / f"{human_id}.md",
            root / ".agora" / "actors" / f"{ai_id}.md",
            root / ".agora" / "swarms" / data.swarm_id,
        )
        existing = next((path for path in reserved_paths if path.exists()), None)
        if existing is not None:
            raise FileExistsError(f"Quickstart target already exists: {existing}")
        # First required role goes to the human actor; every other role goes to the
        # AI actor, so the pair covers the whole method out of the box.
        human_roles = contract.required_roles[:1]
        ai_roles = contract.required_roles[1:] or contract.required_roles

        def _role_capabilities(role_ids: list[str]) -> list[str]:
            capabilities: list[str] = []
            for role_id in role_ids:
                attributes = read_markdown(
                    root / ".agora" / "methods" / method / "roles" / f"{role_id}.md"
                ).attributes
                for capability in strings_attribute(attributes, "required-capabilities"):
                    if capability not in capabilities:
                        capabilities.append(capability)
            return capabilities

        human_key = ai_key = None
        keys_dir: Path | None = None
        if data.key_directory is not None and not data.secure:
            raise ValueError("--key-dir requires secure quickstart mode")
        if data.secure:
            keys_dir = self._quickstart_key_directory(root, data.key_directory)
            human_key = self._generate_quickstart_keypair(keys_dir, human_id)
            ai_key = self._generate_quickstart_keypair(keys_dir, ai_id)

        self.add_actor(
            AddActorInput(
                id=human_id,
                name="Owner",
                kind="human",
                capabilities=_role_capabilities(human_roles),
                scope="project",
                public_key=human_key,
                require_authentication=data.secure,
            )
        )
        self.add_actor(
            AddActorInput(
                id=ai_id,
                name="Agent",
                kind="ai-agent",
                capabilities=_role_capabilities(ai_roles),
                scope="project",
                public_key=ai_key,
                require_authentication=data.secure,
            )
        )

        swarm = self.create_swarm(
            CreateSwarmInput(id=data.swarm_id, objective=data.objective, method=method)
        )

        assignments: dict[str, str] = {}
        for role_id in contract.required_roles:
            actor_id = human_id if role_id in human_roles else ai_id
            swarm = self.assign_actor(
                AssignActorInput(swarm_id=swarm.id, role_id=role_id, actor_id=actor_id)
            )
            assignments[role_id] = actor_id

        return QuickstartResult(
            project=project,
            swarm=swarm,
            human_actor=human_id,
            ai_actor=ai_id,
            assignments=assignments,
            secure=data.secure,
            key_directory=str(keys_dir) if keys_dir is not None else None,
        )

    @staticmethod
    def _quickstart_key_directory(root: Path, configured: str | None) -> Path:
        if configured is not None:
            return Path(configured).expanduser().resolve()
        project_digest = hashlib.sha256(str(root).encode()).hexdigest()[:16]
        return Path.home() / ".config" / "agora-quickstart-keys" / project_digest

    @staticmethod
    def _generate_quickstart_keypair(keys_dir: Path, actor_id: str) -> str:
        keys_dir.mkdir(parents=True, exist_ok=True)
        keys_dir.chmod(0o700)
        private_path = keys_dir / f"{actor_id}-private.pem"
        public_path = keys_dir / f"{actor_id}-public.pem"
        if private_path.exists() != public_path.exists():
            raise FileExistsError(
                f"Quickstart keypair is incomplete for actor {actor_id}: {keys_dir}"
            )
        if private_path.exists():
            loaded_private = serialization.load_pem_private_key(
                private_path.read_bytes(), password=None
            )
            loaded_public = serialization.load_pem_public_key(public_path.read_bytes())
            if not isinstance(loaded_private, Ed25519PrivateKey) or not isinstance(
                loaded_public, Ed25519PublicKey
            ):
                raise ValueError(f"Quickstart keypair must use Ed25519: {keys_dir}")
            expected_public = loaded_private.public_key().public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
            actual_public = loaded_public.public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
            if expected_public != actual_public:
                raise ValueError(f"Quickstart keypair does not match for actor {actor_id}")
            return str(public_path)
        private_key = Ed25519PrivateKey.generate()
        private_path.write_bytes(
            private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
        private_path.chmod(0o600)
        public_path.write_bytes(
            private_key.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        )
        return str(public_path)


def _extract_section(body: str, heading: str) -> str:
    marker = f"## {heading}\n\n"
    if marker not in body:
        return ""
    section = body.split(marker, 1)[1]
    return section.split("\n\n## ", 1)[0].strip()


def _assert_schema(document: MarkdownDocument, expected: str, path: Path) -> None:
    actual = string_attribute(document.attributes, "schema")
    if actual != expected:
        raise ValueError(f"Expected schema {expected}, found {actual}: {path}")


def _assert_project_standards(document: MarkdownDocument, path: Path) -> None:
    _assert_schema(document, "agora/standards/v1", path)
    standards = strings_attribute(document.attributes, "standards")
    if "conventional-commits/v1.0.0" not in standards:
        raise ValueError(f"Project must enable conventional-commits/v1.0.0: {path}")


def _boolean_attribute(attributes: dict[str, object], key: str) -> bool:
    value = attributes.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"Expected boolean attribute: {key}")
    return value


def _boolean_attribute_default(attributes: dict[str, object], key: str, default: bool) -> bool:
    value = attributes.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"Expected boolean attribute: {key}")
    return value


def _optional_integer_attribute(attributes: dict[str, object], key: str) -> int | None:
    value = attributes.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"Expected integer attribute or null: {key}")
    return value


def _nonnegative_integer_attribute_default(
    attributes: dict[str, object], key: str, default: int
) -> int:
    value = attributes.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"Expected non-negative integer attribute: {key}")
    return value


def _positive_integer_attribute_default(
    attributes: dict[str, object], key: str, default: int, maximum: int
) -> int:
    value = attributes.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1 or value > maximum:
        raise ValueError(f"Expected integer attribute between 1 and {maximum}: {key}")
    return value


def _tool_risk(value: str) -> ToolRisk:
    if value not in {"read", "write", "destructive"}:
        raise ValueError(f"Unsupported tool risk: {value}")
    return value  # type: ignore[return-value]


def _work_operational_status(value: object) -> WorkOperationalStatus:
    if value not in {"active", "blocked", "cancelled"}:
        raise ValueError(f"Unsupported work operational status: {value}")
    return value  # type: ignore[return-value]


def _count_values(values: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _display_path(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _child_directories(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(path for path in root.iterdir() if path.is_dir())


def _run_tool_process(
    command: list[str],
    cwd: Path,
    environment: dict[str, str],
    timeout_seconds: float = DEFAULT_TOOL_TIMEOUT_SECONDS,
    max_output_bytes: int = DEFAULT_TOOL_MAX_OUTPUT_BYTES,
    boundary_subject: str = "tool",
) -> subprocess.CompletedProcess[str]:
    started = time.monotonic()
    boundary: str | None = None
    boundary_exit_code: int | None = None
    with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=environment,
            stdout=stdout_file,
            stderr=stderr_file,
        )
        while process.poll() is None:
            output_size = (
                os.fstat(stdout_file.fileno()).st_size + os.fstat(stderr_file.fileno()).st_size
            )
            if output_size > max_output_bytes:
                boundary = (
                    f"Agora terminated the {boundary_subject} after output exceeded "
                    f"{max_output_bytes} bytes."
                )
                boundary_exit_code = 125
                process.kill()
                break
            if time.monotonic() - started >= timeout_seconds:
                boundary = (
                    f"Agora terminated the {boundary_subject} after {timeout_seconds:g} seconds."
                )
                boundary_exit_code = 124
                process.kill()
                break
            time.sleep(0.01)
        process.wait()
        actual_output_size = (
            os.fstat(stdout_file.fileno()).st_size + os.fstat(stderr_file.fileno()).st_size
        )
        stdout_file.seek(0)
        stderr_file.seek(0)
        stdout = stdout_file.read(max_output_bytes)
        stderr = stderr_file.read(max(0, max_output_bytes - len(stdout)))

    if boundary is None and actual_output_size > max_output_bytes:
        boundary = f"Agora limited captured {boundary_subject} output to {max_output_bytes} bytes."
        boundary_exit_code = 125
    exit_code = process.returncode if boundary_exit_code is None else boundary_exit_code
    stderr_text = stderr.decode("utf-8", errors="replace")
    if boundary:
        stderr_text = f"{stderr_text.rstrip()}\n{boundary}\n".lstrip()
    return subprocess.CompletedProcess(
        command,
        exit_code,
        stdout.decode("utf-8", errors="replace"),
        stderr_text,
    )


def _bound_tool_output(
    result: subprocess.CompletedProcess[str], max_output_bytes: int
) -> subprocess.CompletedProcess[str]:
    stdout = result.stdout.encode("utf-8")
    stderr = result.stderr.encode("utf-8")
    if len(stdout) + len(stderr) <= max_output_bytes:
        return result
    bounded_stdout = stdout[:max_output_bytes]
    bounded_stderr = stderr[: max(0, max_output_bytes - len(bounded_stdout))]
    diagnostic = f"Agora limited captured tool output to {max_output_bytes} bytes.\n"
    return subprocess.CompletedProcess(
        result.args,
        125,
        bounded_stdout.decode("utf-8", errors="replace"),
        f"{bounded_stderr.decode('utf-8', errors='replace').rstrip()}\n{diagnostic}".lstrip(),
    )
