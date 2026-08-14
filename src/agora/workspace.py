import math
import os
import shlex
import shutil
import subprocess
from collections.abc import Callable, Iterable, Iterator
from contextlib import ExitStack, contextmanager
from datetime import UTC, datetime
from functools import wraps
from pathlib import Path

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
from agora.locking import WorkspaceLock, inspect_workspace_lock
from agora.markdown import (
    MarkdownDocument,
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
    INTEGRATIONS,
    ActorRecord,
    AddActorInput,
    AddApprovalInput,
    AddArtifactInput,
    AddEvidenceInput,
    AssignActorInput,
    CatalogPackRecord,
    ChangeDelegationStatusInput,
    ChangeWorkStatusInput,
    ConfigureInput,
    CreateDelegationInput,
    CreateSwarmInput,
    CreateWorkInput,
    DelegationActorInput,
    DelegationRecord,
    DoctorCheck,
    EventRecord,
    GatePolicy,
    HandoffActorInput,
    HandoffRecord,
    InitInput,
    InstallCatalogPackInput,
    InstallMethodInput,
    InstallRegistryInput,
    InstallToolInput,
    Integration,
    InvokeToolInput,
    Method,
    MethodContract,
    MethodPackRecord,
    ProjectConfiguration,
    RegistryRecord,
    SessionRecord,
    SetActorRuntimeInput,
    StartSessionInput,
    StatusChangeRecord,
    SwarmRecord,
    ToolContract,
    ToolPackRecord,
    ToolRisk,
    ToolRunRecord,
    TransitionWorkInput,
    UpgradeInput,
    UpgradeResult,
    UserConfiguration,
    ValidationIssue,
    ValidationReport,
    WorkActorInput,
    WorkOperationalStatus,
    WorkRecord,
    WorkspaceLockStatus,
    WorkspaceStatus,
)
from agora.registries import bundled_registry, discover_registry_packs, load_registry
from agora.tools import load_tool_contract, validate_operation_inputs
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
        lock_timeout: float | None = None,
    ) -> None:
        self.cwd = Path(cwd or Path.cwd()).resolve()
        self._now = now or (lambda: datetime.now(UTC))
        self._launcher = launcher or _launch_process
        self._tool_runner = tool_runner or _run_tool_process
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
            default_method=data.default_method or (user.default_method if user else "scrum"),
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

    @_locked_mutation("scoped")
    def install_method(self, data: InstallMethodInput) -> MethodPackRecord:
        source = Path(data.source).expanduser().resolve()
        if not source.is_dir():
            raise FileNotFoundError(f"Method Pack directory not found: {source}")
        method_file = source / "METHOD.md"
        if not method_file.is_file():
            raise FileNotFoundError(f"Method Pack is missing METHOD.md: {source}")

        contract = load_method_contract(source)

        destination_root = agora_home() if data.scope == "user" else self.project_root() / ".agora"
        destination = destination_root / "methods" / contract.id
        if destination.exists() and not data.force:
            raise FileExistsError(
                f"Method Pack already exists: {destination}. Pass --force to replace its files."
            )
        copy_template_tree(source, destination, {}, data.force)
        return MethodPackRecord(
            id=contract.id,
            name=contract.name,
            scope=data.scope,
            path=str(destination),
            required_roles=contract.required_roles,
            work_states=contract.work_states,
            terminal_state=contract.terminal_state,
        )

    @_locked_mutation("scoped")
    def install_tool(self, data: InstallToolInput) -> ToolPackRecord:
        source = Path(data.source).expanduser().resolve()
        if not source.is_dir():
            raise FileNotFoundError(f"Tool Pack directory not found: {source}")
        if not (source / "TOOL.md").is_file():
            raise FileNotFoundError(f"Tool Pack is missing TOOL.md: {source}")
        contract = load_tool_contract(source)
        destination_root = agora_home() if data.scope == "user" else self.project_root() / ".agora"
        destination = destination_root / "tools" / contract.id
        if destination.exists() and not data.force:
            raise FileExistsError(
                f"Tool Pack already exists: {destination}. Pass --force to replace its files."
            )
        copy_template_tree(source, destination, {}, data.force)
        return self._tool_pack_record(contract, data.scope, destination)

    @_locked_mutation("scoped")
    def install_registry(self, data: InstallRegistryInput) -> RegistryRecord:
        source = Path(data.source).expanduser().resolve()
        if not source.is_dir():
            raise FileNotFoundError(f"Registry directory not found: {source}")
        registry = load_registry(source, data.scope)
        destination_root = agora_home() if data.scope == "user" else self.project_root() / ".agora"
        destination = destination_root / "registries" / registry.id
        if destination.exists() and not data.force:
            raise FileExistsError(
                f"Registry already exists: {destination}. Pass --force to replace its files."
            )
        copy_template_tree(source, destination, {}, data.force)
        return load_registry(destination, data.scope)

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
        if data.kind == "method":
            return self.install_method(
                InstallMethodInput(source=selected.path, scope=data.scope, force=data.force)
            )
        return self.install_tool(
            InstallToolInput(source=selected.path, scope=data.scope, force=data.force)
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
            records.append(
                MethodPackRecord(
                    id=contract.id,
                    name=contract.name,
                    scope="project",
                    path=str(path.parent),
                    required_roles=contract.required_roles,
                    work_states=contract.work_states,
                    terminal_state=contract.terminal_state,
                )
            )
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
        root = agora_home() if data.scope == "user" else self.project_root() / ".agora"
        if data.represented_swarm is not None:
            assert_slug(data.represented_swarm, "Represented swarm id")
            if data.kind != "swarm":
                raise ValueError("Only an actor whose kind is swarm may represent a project swarm")
            if data.scope != "project":
                raise ValueError("A represented swarm actor must use project scope")
            self._load_swarm(self.project_root(), data.represented_swarm)
        path = root / "actors" / f"{data.id}.md"
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
        return ActorRecord(
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
        )

    @_locked_mutation("actor-runtime")
    def set_actor_runtime(self, data: SetActorRuntimeInput) -> ActorRecord:
        root = self.project_root()
        actor = self._find_actor(root, data.actor_id)
        if not data.clear and not any((data.integration, data.provider, data.model)):
            raise ValueError("Provide an integration, provider, model, or --clear")
        if data.integration is not None:
            self._assert_integration(data.integration)
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
        assert_slug(data.role_id, "Role id")
        root = self.project_root()
        swarm = self._load_swarm(root, data.swarm_id)
        if swarm.status not in {"forming", "ready"}:
            raise ValueError(f"Cannot change assignments while swarm {swarm.id} is {swarm.status}")
        actor = self._find_actor(root, data.actor_id)
        self._assert_actor_role_compatibility(root, swarm.method, data.role_id, actor)
        self._assert_swarm_actor_delegation(root, swarm, data.role_id, actor)
        swarm.assignments[data.role_id] = actor.reference
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
            f"role={data.role_id} actor={actor.reference}",
        )
        return swarm

    @_locked_mutation("project")
    def handoff_actor(self, data: HandoffActorInput) -> HandoffRecord:
        assert_slug(data.role_id, "Role id")
        if not data.reason.strip():
            raise ValueError("Handoff reason cannot be empty")
        root = self.project_root()
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
        record = HandoffRecord(
            id=handoff_id,
            swarm_id=swarm.id,
            role_id=data.role_id,
            from_actor=outgoing.reference,
            to_actor=incoming.reference,
            authorized_by=authorizer.reference,
            reason=data.reason.strip(),
            work_id=work.id if work else None,
            created_at=self._timestamp(),
            path=str(handoff_path),
        )
        write_new(handoff_path, self._render_handoff(record))
        swarm.assignments[data.role_id] = incoming.reference
        atomic_write(Path(swarm.path) / "SWARM.md", self._render_swarm(swarm))
        detail = (
            f"handoff={handoff_id} role={data.role_id} from={outgoing.reference} "
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
        assert_slug(data.id, "Work id")
        root = self.project_root()
        swarm = self._load_swarm(root, data.swarm_id)
        if swarm.status not in {"ready", "running"}:
            raise ValueError(f"Swarm {swarm.id} must be ready before work can be created")
        actor = self._require_actor_for_action(root, swarm, data.actor_id, "work.create")
        contract = load_method_contract(root / ".agora" / "methods" / swarm.method)
        criteria = dict(data.acceptance_criteria)
        if len(criteria) != len(data.acceptance_criteria):
            raise ValueError("Acceptance criterion ids must be unique")
        for criterion_id in criteria:
            assert_slug(criterion_id, "Criterion id")

        path = Path(swarm.path) / "work" / data.id
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
    def satisfy_criterion(self, data: WorkActorInput, criterion_id: str) -> WorkRecord:
        root = self.project_root()
        swarm = self._load_swarm(root, data.swarm_id)
        actor = self._require_actor_for_action(root, swarm, data.actor_id, "criterion.satisfy")
        work = self._load_work(swarm, data.work_id)
        self._assert_work_mutable(root, swarm, work)
        if criterion_id not in work.acceptance_criteria:
            raise FileNotFoundError(f"Acceptance criterion not found: {criterion_id}")
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
        swarm = self._load_swarm(root, data.swarm_id)
        actor = self._require_actor_for_action(root, swarm, data.actor_id, "artifact.add")
        work = self._load_work(swarm, data.work_id)
        self._assert_work_mutable(root, swarm, work)
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
        swarm = self._load_swarm(root, data.swarm_id)
        actor = self._require_actor_for_action(root, swarm, data.actor_id, "evidence.add")
        work = self._load_work(swarm, data.work_id)
        self._assert_work_mutable(root, swarm, work)
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
        work: WorkRecord,
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
    def add_approval(self, data: AddApprovalInput) -> WorkRecord:
        assert_slug(data.role_id, "Approval role id")
        root = self.project_root()
        swarm = self._load_swarm(root, data.swarm_id)
        actor = self._require_actor_for_action(root, swarm, data.actor_id, "approval.add")
        roles = self._actor_roles(swarm, actor.reference)
        if data.role_id not in roles:
            raise PermissionError(
                f"Actor {actor.reference} is not assigned to approval role {data.role_id}"
            )
        work = self._load_work(swarm, data.work_id)
        self._assert_work_mutable(root, swarm, work)
        path = Path(work.path) / "approvals.md"
        document = read_markdown(path)
        approval_roles = strings_attribute(document.attributes, "approval-roles")
        document.attributes["approval-roles"] = list(dict.fromkeys([*approval_roles, data.role_id]))
        note = data.note.replace("|", "\\|") or "Approved"
        document.body = (
            f"{document.body.rstrip()}\n| {data.role_id} | {actor.reference} | {note} | "
            f"{self._timestamp()} |"
        )
        atomic_write(path, render_markdown(document))
        self._append_work_event(
            work,
            "approval.added",
            f"role={data.role_id} actor={actor.reference}",
        )
        return self._load_work(swarm, data.work_id)

    @_locked_mutation("project")
    def transition_work(self, data: TransitionWorkInput) -> WorkRecord:
        root = self.project_root()
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
        self._assert_wip_limit(swarm, work, data.target_state, contract.wip_limits)
        if transition.gate is not None:
            self._assert_work_gate(work, contract.gates[transition.gate], transition.gate)

        previous = work.state
        work.state = data.target_state
        atomic_write(Path(work.path) / "WORK.md", self._render_work(work))
        self._append_work_event(
            work,
            "work.transitioned",
            f"from={previous} to={data.target_state} actor={actor.reference}",
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
    def resume_work(self, data: ChangeWorkStatusInput) -> StatusChangeRecord:
        return self._change_work_status(data, "active", "work.resume")

    @_locked_mutation("project")
    def cancel_work(self, data: ChangeWorkStatusInput) -> StatusChangeRecord:
        return self._change_work_status(data, "cancelled", "work.cancel")

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
        if not data.reason.strip():
            raise ValueError("Work status change reason cannot be empty")
        root = self.project_root()
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
        assert_slug(data.child_work_id, "Child work id")
        assert_slug(data.result_kind, "Delegation result kind")
        root = self.project_root()
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
        delegation_id = data.id or self._now().astimezone(UTC).strftime("delegation-%Y%m%dt%H%M%sz")
        assert_slug(delegation_id, "Delegation id")
        path = root / ".agora" / "delegations" / delegation_id / "DELEGATION.md"
        if path.exists():
            raise FileExistsError(f"Delegation already exists: {delegation_id}")
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
        child_work = self.create_work(
            CreateWorkInput(
                swarm_id=child.id,
                id=delegation.child_work_id,
                title=delegation.title,
                actor_id=data.actor_id,
                acceptance_criteria=list(delegation.acceptance_criteria.items()),
                required_artifacts=delegation.required_artifacts,
                description=delegation.description,
            )
        )
        work_path = Path(child_work.path) / "WORK.md"
        work_document = read_markdown(work_path)
        work_document.attributes["delegation"] = delegation.id
        work_document.attributes["parent-work"] = (
            f"{delegation.parent_swarm_id}/{delegation.parent_work_id}"
        )
        atomic_write(work_path, render_markdown(work_document))
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
            id_=None,
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
        parent_work = self._load_work(parent, delegation.parent_work_id)
        self._assert_work_mutable(root, parent, parent_work)
        parent_contract = load_method_contract(root / ".agora" / "methods" / parent.method)
        if parent_work.state == parent_contract.terminal_state:
            raise ValueError(f"Cannot collect into completed work: {parent_work.id}")
        result_uri = f"agora://swarms/{child.id}/work/{child_work.id}"
        self._record_artifact(
            parent_work,
            delegation.result_kind,
            result_uri,
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
            id_=None,
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
    def reject_delegation(self, data: ChangeDelegationStatusInput) -> StatusChangeRecord:
        return self._change_delegation_status(
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
        if not data.reason.strip():
            raise ValueError("Delegation status change reason cannot be empty")
        root = self.project_root()
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
        if action in {"delegation.block", "delegation.resume"}:
            parent = self._load_swarm(root, delegation.parent_swarm_id)
            parent_work = self._load_work(parent, delegation.parent_work_id)
            self._assert_work_mutable(root, parent, parent_work)
        previous = delegation.status
        change_root = Path(delegation.path).parent / "status-changes"
        self._assert_status_change_id_available(change_root, data.id)
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
        parent = self._load_swarm(root, delegation.parent_swarm_id)
        parent_work = self._load_work(parent, delegation.parent_work_id)
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

    @_locked_mutation("project")
    def start_session(self, data: StartSessionInput) -> SessionRecord:
        root = self.project_root()
        project = self._load_project_configuration(root)
        swarm = self._load_swarm(root, data.swarm_id)
        if swarm.status not in {"ready", "running"}:
            raise ValueError(f"Swarm {swarm.id} must be ready before a session can start")
        actor = self._find_actor(root, data.actor_id)
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
        command = self._runtime_command(integration, data.runner)
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
        )
        write_new(
            context_path,
            self._render_session_context(
                root,
                project,
                actor,
                swarm,
                roles,
                work,
                integration,
                provider,
                model,
            ),
            data.force,
        )
        write_new(session_path / "SESSION.md", self._render_session(record), data.force)
        append_entry(
            root / ".agora" / "events.md",
            (
                f"- {self._timestamp()} | session.prepared | session={session_id} "
                f"actor={actor.reference} swarm={swarm.id}"
            ),
        )
        if not data.launch:
            return record

        running = SessionRecord(**{**record.__dict__, "status": "running"})
        atomic_write(session_path / "SESSION.md", self._render_session(running))
        environment = {
            **os.environ,
            "AGORA_PROJECT": str(root),
            "AGORA_SESSION": str(session_path / "SESSION.md"),
            "AGORA_CONTEXT": str(context_path),
            "AGORA_ACTOR": actor.reference,
            "AGORA_SWARM": swarm.id,
        }
        if work is not None:
            environment["AGORA_WORK"] = work.id
        exit_code = self._launcher(command, root, environment)
        status = "completed" if exit_code == 0 else "failed"
        finished = SessionRecord(**{**record.__dict__, "status": status, "exit_code": exit_code})
        atomic_write(session_path / "SESSION.md", self._render_session(finished))
        append_entry(
            root / ".agora" / "events.md",
            (
                f"- {self._timestamp()} | session.{status} | session={session_id} "
                f"exit-code={exit_code}"
            ),
        )
        if exit_code != 0:
            raise RuntimeError(f"Session runner exited with code {exit_code}: {' '.join(command)}")
        return finished

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
        runtime_available = shutil.which(contract.executable) is not None
        if data.launch and not runtime_available:
            raise FileNotFoundError(f"Tool executable not found: {contract.executable}")

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
            capability=operation.capability,
            risk=operation.risk,
            inputs=data.inputs,
            command=command,
            runtime_available=runtime_available,
            status="prepared",
            path=str(run_path),
            created_at=self._timestamp(),
            result_kind=operation.result_kind,
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
        result = self._tool_runner(command, root, environment)
        status = "completed" if result.returncode == 0 else "failed"
        finished = ToolRunRecord(
            **{**record.__dict__, "status": status, "exit_code": result.returncode}
        )
        atomic_write(run_path / "RUN.md", self._render_tool_run(finished, contract))
        write_new(
            run_path / "RESULT.md",
            self._render_tool_result(finished, result.stdout, result.stderr),
            data.force,
        )
        self._append_tool_event(root, finished, status)
        if work is not None:
            self._append_work_event(
                work,
                f"tool.{status}",
                f"run={run_id} exit-code={result.returncode}",
            )
        if result.returncode != 0:
            raise RuntimeError(
                f"Tool operation exited with code {result.returncode}: {' '.join(command)}"
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
        swarms = self.list_swarms()
        work = self.list_work()
        delegations = self.list_delegations()
        sessions = self.list_sessions()
        tool_runs = self.list_tool_runs()
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
                "swarms": len(swarms),
                "work": len(work),
                "delegations": len(delegations),
                "sessions": len(sessions),
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
            "actors": 0,
            "swarms": 0,
            "work": 0,
            "handoffs": 0,
            "delegations": 0,
            "status-changes": 0,
            "sessions": 0,
            "tool-runs": 0,
            "event-files": 0,
            "upgrades": 0,
            "registries": 0,
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
        standards_path = root / ".agora" / "STANDARDS.md"
        inspect(
            "documents",
            "standards.invalid",
            standards_path,
            lambda: _assert_project_standards(read_markdown(standards_path), standards_path),
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
        if isinstance(project, ProjectConfiguration) and project.default_method not in methods:
            issue(
                "project.default-method-missing",
                project_path,
                f"Default Method Pack is not valid or installed: {project.default_method}",
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

        actor_cache: dict[str, ActorRecord] = {}
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

        try:
            maximum = (
                project.max_delegation_depth if isinstance(project, ProjectConfiguration) else 3
            )
            self._validate_delegation_graph(self._delegation_graph(root), maximum)
        except Exception as error:
            issue("swarm.graph-invalid", swarm_root, str(error))

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
            resolve_actor(session.actor, path)
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
            elif operation.capability != run.capability or operation.risk != run.risk:
                issue(
                    "tool-run.contract-mismatch",
                    path,
                    "Tool run capability or risk differs from its installed operation",
                )
            resolve_actor(run.actor, path)
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
        return ActorRecord(
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
        return HandoffRecord(
            id=string_attribute(document.attributes, "id"),
            swarm_id=string_attribute(document.attributes, "swarm"),
            role_id=string_attribute(document.attributes, "role"),
            from_actor=string_attribute(document.attributes, "from"),
            to_actor=string_attribute(document.attributes, "to"),
            authorized_by=string_attribute(document.attributes, "authorized-by"),
            reason=_extract_section(document.body, "Reason"),
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
            operational_status=_work_operational_status(
                document.attributes.get("operational-status", "active")
            ),
            status_reason=optional_string_attribute(document.attributes, "status-reason"),
            status_by=optional_string_attribute(document.attributes, "status-by"),
            status_at=optional_string_attribute(document.attributes, "status-at"),
        )

    def _render_work(self, work: WorkRecord) -> str:
        checklist = "\n".join(
            f"- [{'x' if item in work.satisfied_criteria else ' '}] **{item}:** {description}"
            for item, description in work.acceptance_criteria.items()
        )
        artifacts = "\n".join(f"- {item}" for item in work.required_artifacts) or "- none"
        return render_markdown(
            MarkdownDocument(
                attributes={
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
                },
                body=(
                    f"# {work.title}\n\n## Description\n\n"
                    f"{work.description or 'No description provided.'}\n\n"
                    f"## Acceptance criteria\n\n{checklist or '- none'}\n\n"
                    f"## Required artifacts\n\n{artifacts}"
                ),
            )
        )

    @staticmethod
    def _runtime_command(integration: Integration, runner: str | None) -> list[str]:
        if runner is not None:
            command = shlex.split(runner)
            if not command:
                raise ValueError("Runner command cannot be empty")
            return command
        if integration == "codex":
            return ["codex"]
        if integration == "claude":
            return ["claude"]
        return []

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
        return SessionRecord(
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
        )

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
            root / ".agora" / "tools" / "TOOLS.md",
            swarm_root / "SWARM.md",
            swarm_root / "events.md",
            method_root / "METHOD.md",
            method_root / "PROTOCOL.md",
            method_root / "TOOLS.md",
            *role_paths,
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
    def _tool_pack_record(contract: ToolContract, scope: str, path: Path) -> ToolPackRecord:
        return ToolPackRecord(
            id=contract.id,
            name=contract.name,
            category=contract.category,
            executable=contract.executable,
            scope=scope,
            path=str(path),
            operations=sorted(contract.operations),
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
                    "capability": record.capability,
                    "risk": record.risk,
                    "inputs": record.inputs,
                    "command": record.command,
                    "runtime-available": record.runtime_available,
                    "status": record.status,
                    "result-kind": record.result_kind,
                    "authentication-reference": contract.authentication_reference,
                    "created-at": record.created_at,
                    "exit-code": record.exit_code,
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
        return ToolRunRecord(
            id=string_attribute(document.attributes, "id"),
            tool_id=string_attribute(document.attributes, "tool"),
            operation_id=string_attribute(document.attributes, "operation"),
            actor=string_attribute(document.attributes, "actor"),
            swarm_id=string_attribute(document.attributes, "swarm"),
            work_id=optional_string_attribute(document.attributes, "work"),
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
        )

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

    @staticmethod
    def _assert_work_gate(work: WorkRecord, gate: GatePolicy, gate_id: str) -> None:
        unsatisfied = (
            [item for item in work.acceptance_criteria if item not in work.satisfied_criteria]
            if gate.require_all_criteria
            else []
        )
        missing_artifacts = (
            [item for item in work.required_artifacts if item not in work.artifact_kinds]
            if gate.require_required_artifacts
            else []
        )
        has_success = "success" in work.evidence_results
        evidence_missing = gate.require_successful_evidence and not has_success
        missing_approvals = [
            role for role in gate.required_approval_roles if role not in work.approval_roles
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


def _optional_integer_attribute(attributes: dict[str, object], key: str) -> int | None:
    value = attributes.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"Expected integer attribute or null: {key}")
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


def _launch_process(command: list[str], cwd: Path, environment: dict[str, str]) -> int:
    return subprocess.run(command, cwd=cwd, env=environment, check=False).returncode


def _run_tool_process(
    command: list[str], cwd: Path, environment: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
