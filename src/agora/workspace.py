import os
import shlex
import shutil
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
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
    ConfigureInput,
    CreateDelegationInput,
    CreateSwarmInput,
    CreateWorkInput,
    DelegationActorInput,
    DelegationRecord,
    DoctorCheck,
    GatePolicy,
    HandoffActorInput,
    HandoffRecord,
    InitInput,
    InstallMethodInput,
    InstallToolInput,
    Integration,
    InvokeToolInput,
    Method,
    MethodPackRecord,
    ProjectConfiguration,
    SessionRecord,
    SetActorRuntimeInput,
    StartSessionInput,
    SwarmRecord,
    ToolContract,
    ToolPackRecord,
    ToolRunRecord,
    TransitionWorkInput,
    UserConfiguration,
    WorkActorInput,
    WorkRecord,
)
from agora.tools import load_tool_contract


class AgoraWorkspace:
    def __init__(
        self,
        cwd: Path | str | None = None,
        now: Callable[[], datetime] | None = None,
        launcher: Callable[[list[str], Path, dict[str, str]], int] | None = None,
        tool_runner: (
            Callable[[list[str], Path, dict[str, str]], subprocess.CompletedProcess[str]] | None
        ) = None,
    ) -> None:
        self.cwd = Path(cwd or Path.cwd()).resolve()
        self._now = now or (lambda: datetime.now(UTC))
        self._launcher = launcher or _launch_process
        self._tool_runner = tool_runner or _run_tool_process

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

    def initialize(self, data: InitInput) -> ProjectConfiguration:
        target = (self.cwd / (data.target or ".")).resolve()
        target.mkdir(parents=True, exist_ok=True)
        user = self._load_user_configuration()
        configuration = ProjectConfiguration(
            project=target.name,
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
                        "version": "0.1.0",
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

    def show_tool(self, tool_id: str) -> ToolPackRecord:
        assert_slug(tool_id, "Tool id")
        path = self.project_root() / ".agora" / "tools" / tool_id
        contract = load_tool_contract(path)
        return self._tool_pack_record(contract, "project", path)

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
        handoff_id = data.id or self._now().astimezone(UTC).strftime("handoff-%Y%m%dt%H%M%Sz")
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

    def satisfy_criterion(self, data: WorkActorInput, criterion_id: str) -> WorkRecord:
        root = self.project_root()
        swarm = self._load_swarm(root, data.swarm_id)
        actor = self._require_actor_for_action(root, swarm, data.actor_id, "criterion.satisfy")
        work = self._load_work(swarm, data.work_id)
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

    def add_artifact(self, data: AddArtifactInput) -> WorkRecord:
        root = self.project_root()
        swarm = self._load_swarm(root, data.swarm_id)
        actor = self._require_actor_for_action(root, swarm, data.actor_id, "artifact.add")
        work = self._load_work(swarm, data.work_id)
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

    def add_evidence(self, data: AddEvidenceInput) -> WorkRecord:
        root = self.project_root()
        swarm = self._load_swarm(root, data.swarm_id)
        actor = self._require_actor_for_action(root, swarm, data.actor_id, "evidence.add")
        work = self._load_work(swarm, data.work_id)
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

    def transition_work(self, data: TransitionWorkInput) -> WorkRecord:
        root = self.project_root()
        swarm = self._load_swarm(root, data.swarm_id)
        actor = self._require_actor_for_action(root, swarm, data.actor_id, "work.transition")
        work = self._load_work(swarm, data.work_id)
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
        if swarm.status == "ready":
            swarm.status = "running"
            atomic_write(Path(swarm.path) / "SWARM.md", self._render_swarm(swarm))
        if data.target_state == contract.terminal_state:
            work_directories = [
                item for item in (Path(swarm.path) / "work").iterdir() if item.is_dir()
            ]
            if all(
                self._load_work(swarm, item.name).state == contract.terminal_state
                for item in work_directories
            ):
                swarm.status = "completed"
                atomic_write(Path(swarm.path) / "SWARM.md", self._render_swarm(swarm))
                self._append_swarm_event(root, swarm.id, "swarm.completed", f"work={work.id}")
        self._append_work_event(
            work,
            "work.transitioned",
            f"from={previous} to={data.target_state} actor={actor.reference}",
        )
        return work

    def show_work(self, swarm_id: str, work_id: str) -> WorkRecord:
        swarm = self._load_swarm(self.project_root(), swarm_id)
        return self._load_work(swarm, work_id)

    def create_delegation(self, data: CreateDelegationInput) -> DelegationRecord:
        assert_slug(data.child_work_id, "Child work id")
        assert_slug(data.result_kind, "Delegation result kind")
        root = self.project_root()
        parent = self._load_swarm(root, data.parent_swarm_id)
        if parent.status not in {"ready", "running"}:
            raise ValueError(f"Parent swarm {parent.id} must be ready before work is delegated")
        parent_work = self._load_work(parent, data.parent_work_id)
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
        delegation_id = data.id or self._now().astimezone(UTC).strftime("delegation-%Y%m%dt%H%M%Sz")
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

    def accept_delegation(self, data: DelegationActorInput) -> DelegationRecord:
        root = self.project_root()
        delegation = self._load_delegation(root, data.delegation_id)
        if delegation.status != "proposed":
            raise ValueError(
                f"Delegation {delegation.id} cannot be accepted while {delegation.status}"
            )
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
            }
        )
        atomic_write(Path(delegation.path), self._render_delegation(accepted))
        parent = self._load_swarm(root, delegation.parent_swarm_id)
        parent_work = self._load_work(parent, delegation.parent_work_id)
        detail = (
            f"delegation={delegation.id} child-work={child.id}/{child_work.id} "
            f"actor={actor.reference}"
        )
        self._append_work_event(parent_work, "delegation.accepted", detail)
        self._append_work_event(child_work, "work.delegation-accepted", detail)
        self._append_swarm_event(root, child.id, "delegation.accepted", detail)
        return accepted

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
            }
        )
        atomic_write(Path(delegation.path), self._render_delegation(collected))
        parent_work = self._load_work(parent, delegation.parent_work_id)
        detail = f"delegation={delegation.id} result={result_uri} actor={actor.reference}"
        self._append_work_event(parent_work, "delegation.collected", detail)
        self._append_work_event(child_work, "work.delegation-collected", detail)
        self._append_swarm_event(root, parent.id, "delegation.collected", detail)
        return collected

    def show_delegation(self, delegation_id: str) -> DelegationRecord:
        return self._load_delegation(self.project_root(), delegation_id)

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

        integration = actor.integration or project.integration
        provider = actor.provider or project.provider
        model = actor.model or project.model
        command = self._runtime_command(integration, data.runner)
        runtime_available = bool(command and shutil.which(command[0]))
        if data.launch and not command:
            raise ValueError("A generic integration requires --runner when --launch is used")
        if data.launch and not runtime_available:
            raise FileNotFoundError(f"Runtime executable not found: {command[0]}")

        session_id = data.id or self._now().astimezone(UTC).strftime("session-%Y%m%dt%H%M%Sz")
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
        work = self._load_work(swarm, data.work_id) if data.work_id is not None else None
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

        run_id = data.id or self._now().astimezone(UTC).strftime("tool-%Y%m%dt%H%M%Sz")
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

    def doctor(self) -> list[DoctorCheck]:
        root = self.project_root()
        configuration = self._load_project_configuration(root)
        agora = root / ".agora"
        if configuration.integration == "codex":
            integration_path = root / ".agents" / "skills" / "agora-objective" / "SKILL.md"
        elif configuration.integration == "claude":
            integration_path = root / ".claude" / "commands" / "agora.objective.md"
        else:
            integration_path = agora / "commands" / "objective.md"
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
                integration_path.exists(),
                f"{configuration.integration}: {integration_path}",
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

    def project_root(self) -> Path:
        return find_project_root(self.cwd)

    def _load_user_configuration(self) -> UserConfiguration | None:
        path = agora_home() / "config.md"
        if not path.exists():
            return None
        attributes = read_markdown(path).attributes
        return UserConfiguration(
            integration=self._integration(string_attribute(attributes, "integration")),
            provider=string_attribute(attributes, "provider"),
            model=string_attribute(attributes, "model"),
            default_method=self._method(string_attribute(attributes, "default-method")),
            max_delegation_depth=self._delegation_depth(attributes),
        )

    def _load_project_configuration(self, root: Path) -> ProjectConfiguration:
        attributes = read_markdown(root / ".agora" / "project.md").attributes
        return ProjectConfiguration(
            project=string_attribute(attributes, "project"),
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
        attributes = read_markdown(path).attributes
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

    def _load_swarm(self, root: Path, swarm_id: str) -> SwarmRecord:
        assert_slug(swarm_id, "Swarm id")
        path = root / ".agora" / "swarms" / swarm_id
        document = read_markdown(path / "SWARM.md")
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
        if status not in {"proposed", "accepted", "collected"}:
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
            path=str(path),
        )

    def _load_work(self, swarm: SwarmRecord, work_id: str) -> WorkRecord:
        assert_slug(work_id, "Work id")
        path = Path(swarm.path) / "work" / work_id
        document = read_markdown(path / "WORK.md")
        artifacts = read_markdown(path / "artifacts.md")
        evidence = read_markdown(path / "evidence.md")
        approvals_path = path / "approvals.md"
        approval_roles = (
            strings_attribute(read_markdown(approvals_path).attributes, "approval-roles")
            if approvals_path.exists()
            else []
        )
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
            and self._load_work(swarm, path.name).state == target_state
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
