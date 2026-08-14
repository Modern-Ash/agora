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
    read_markdown,
    record_attribute,
    render_markdown,
    string_attribute,
    strings_attribute,
)
from agora.model import (
    ACTOR_KINDS,
    INTEGRATIONS,
    ActorRecord,
    AddActorInput,
    AddArtifactInput,
    AddEvidenceInput,
    AssignActorInput,
    ConfigureInput,
    CreateSwarmInput,
    CreateWorkInput,
    DoctorCheck,
    InitInput,
    InstallMethodInput,
    Integration,
    Method,
    MethodPackRecord,
    ProjectConfiguration,
    SwarmRecord,
    TransitionWorkInput,
    UserConfiguration,
    WorkActorInput,
    WorkRecord,
)


class AgoraWorkspace:
    def __init__(
        self,
        cwd: Path | str | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.cwd = Path(cwd or Path.cwd()).resolve()
        self._now = now or (lambda: datetime.now(UTC))

    def configure(self, data: ConfigureInput) -> UserConfiguration:
        self._assert_integration(data.integration)
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
        )
        home = agora_home()
        (home / "actors").mkdir(parents=True, exist_ok=True)
        (home / "methods").mkdir(parents=True, exist_ok=True)
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
            created_at=self._timestamp(),
        )
        self._assert_integration(configuration.integration)
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

        document = read_markdown(method_file)
        if string_attribute(document.attributes, "schema") != "agora/method/v1":
            raise ValueError("Method Pack schema must be agora/method/v1")
        method_id = string_attribute(document.attributes, "id")
        assert_slug(method_id, "Method id")
        name = string_attribute(document.attributes, "name")
        required_roles = strings_attribute(document.attributes, "required-roles")
        work_states = strings_attribute(document.attributes, "work-states")
        terminal_state = string_attribute(document.attributes, "terminal-state")
        if not required_roles:
            raise ValueError(f"Method Pack {method_id} must define at least one required role")
        if not work_states:
            raise ValueError(f"Method Pack {method_id} must define at least one work state")
        if terminal_state not in work_states:
            raise ValueError(
                f"Method Pack {method_id} terminal state {terminal_state} is not in work-states"
            )
        if terminal_state != work_states[-1]:
            raise ValueError(f"Method Pack {method_id} terminal state must be the last work state")
        missing_roles = [
            role for role in required_roles if not (source / "roles" / f"{role}.md").is_file()
        ]
        if missing_roles:
            raise ValueError(
                f"Method Pack {method_id} is missing role files: {', '.join(missing_roles)}"
            )

        destination_root = agora_home() if data.scope == "user" else self.project_root() / ".agora"
        destination = destination_root / "methods" / method_id
        if destination.exists() and not data.force:
            raise FileExistsError(
                f"Method Pack already exists: {destination}. Pass --force to replace its files."
            )
        copy_template_tree(source, destination, {}, data.force)
        return MethodPackRecord(
            id=method_id,
            name=name,
            scope=data.scope,
            path=str(destination),
            required_roles=required_roles,
            work_states=work_states,
            terminal_state=terminal_state,
        )

    def add_actor(self, data: AddActorInput) -> ActorRecord:
        assert_slug(data.id, "Actor id")
        if data.kind not in ACTOR_KINDS:
            raise ValueError(f"Unsupported actor kind: {data.kind}")
        root = agora_home() if data.scope == "user" else self.project_root() / ".agora"
        path = root / "actors" / f"{data.id}.md"
        capabilities = sorted(set(data.capabilities))
        description = data.description or (
            "Describe this actor's operating context and constraints."
        )
        write_new(
            path,
            render_markdown(
                MarkdownDocument(
                    attributes={
                        "schema": "agora/actor/v1",
                        "id": data.id,
                        "name": data.name,
                        "kind": data.kind,
                        "capabilities": capabilities,
                        "scope": data.scope,
                        "created-at": self._timestamp(),
                    },
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
        )

    def create_swarm(self, data: CreateSwarmInput) -> SwarmRecord:
        assert_slug(data.id, "Swarm id")
        root = self.project_root()
        project = self._load_project_configuration(root)
        method = data.method or project.default_method
        self._assert_method_available(method, root / ".agora" / "methods")
        method_document = read_markdown(root / ".agora" / "methods" / method / "METHOD.md")
        required_roles = strings_attribute(method_document.attributes, "required-roles")
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
            required_roles=required_roles,
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
        self._append_swarm_event(root, data.id, "swarm.created", f"branch={record.branch}")
        return record

    def assign_actor(self, data: AssignActorInput) -> SwarmRecord:
        assert_slug(data.role_id, "Role id")
        root = self.project_root()
        swarm = self._load_swarm(root, data.swarm_id)
        if swarm.status not in {"forming", "ready"}:
            raise ValueError(f"Cannot change assignments while swarm {swarm.id} is {swarm.status}")
        actor = self._find_actor(root, data.actor_id)
        role_path = root / ".agora" / "methods" / swarm.method / "roles" / f"{data.role_id}.md"
        if not role_path.exists():
            raise FileNotFoundError(f"Role {data.role_id} is not defined by method {swarm.method}")
        role = read_markdown(role_path)
        required_capabilities = strings_attribute(role.attributes, "required-capabilities")
        allowed_kinds = strings_attribute(role.attributes, "allowed-actor-kinds")
        missing = [item for item in required_capabilities if item not in actor.capabilities]
        if missing:
            raise ValueError(
                f"Actor {actor.id} lacks capabilities required by {data.role_id}: "
                f"{', '.join(missing)}"
            )
        if actor.kind not in allowed_kinds:
            raise ValueError(f"Actor kind {actor.kind} is not allowed for role {data.role_id}")
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

    def show_swarm(self, swarm_id: str) -> SwarmRecord:
        return self._load_swarm(self.project_root(), swarm_id)

    def create_work(self, data: CreateWorkInput) -> WorkRecord:
        assert_slug(data.id, "Work id")
        root = self.project_root()
        swarm = self._load_swarm(root, data.swarm_id)
        if swarm.status not in {"ready", "running"}:
            raise ValueError(f"Swarm {swarm.id} must be ready before work can be created")
        actor = self._require_actor_for_action(root, swarm, data.actor_id, "work.create")
        method = read_markdown(root / ".agora" / "methods" / swarm.method / "METHOD.md")
        states = strings_attribute(method.attributes, "work-states")
        terminal_state = string_attribute(method.attributes, "terminal-state")
        if not states or terminal_state != states[-1]:
            raise ValueError(
                f"Method {swarm.method} must define its terminal state as the last work state"
            )
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
            state=states[0],
            acceptance_criteria=criteria,
            satisfied_criteria=[],
            required_artifacts=list(dict.fromkeys(data.required_artifacts)),
            artifact_kinds=[],
            evidence_results=[],
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
        path = Path(work.path) / "artifacts.md"
        document = read_markdown(path)
        kinds = strings_attribute(document.attributes, "artifact-kinds")
        document.attributes["artifact-kinds"] = list(dict.fromkeys([*kinds, data.kind]))
        document.body = (
            f"{document.body.rstrip()}\n| {data.kind} | {data.uri} | "
            f"{actor.reference} | {self._timestamp()} |"
        )
        atomic_write(path, render_markdown(document))
        self._append_work_event(
            work,
            "artifact.added",
            f"kind={data.kind} uri={data.uri} actor={actor.reference}",
        )
        return self._load_work(swarm, data.work_id)

    def add_evidence(self, data: AddEvidenceInput) -> WorkRecord:
        root = self.project_root()
        swarm = self._load_swarm(root, data.swarm_id)
        actor = self._require_actor_for_action(root, swarm, data.actor_id, "evidence.add")
        work = self._load_work(swarm, data.work_id)
        path = Path(work.path) / "evidence.md"
        document = read_markdown(path)
        results = strings_attribute(document.attributes, "results")
        document.attributes["results"] = [*results, data.result]
        references = ", ".join(data.artifact_refs) or "none"
        document.body = (
            f"{document.body.rstrip()}\n| {data.type} | {data.result} | {references} | "
            f"{actor.reference} | {self._timestamp()} |"
        )
        atomic_write(path, render_markdown(document))
        self._append_work_event(
            work,
            "evidence.added",
            f"type={data.type} result={data.result} actor={actor.reference}",
        )
        return self._load_work(swarm, data.work_id)

    def transition_work(self, data: TransitionWorkInput) -> WorkRecord:
        root = self.project_root()
        swarm = self._load_swarm(root, data.swarm_id)
        actor = self._require_actor_for_action(root, swarm, data.actor_id, "work.transition")
        work = self._load_work(swarm, data.work_id)
        method = read_markdown(root / ".agora" / "methods" / swarm.method / "METHOD.md")
        states = strings_attribute(method.attributes, "work-states")
        terminal_state = string_attribute(method.attributes, "terminal-state")
        if not states or terminal_state != states[-1]:
            raise ValueError(
                f"Method {swarm.method} must define its terminal state as the last work state"
            )
        try:
            current_index = states.index(work.state)
        except ValueError as error:
            raise ValueError(f"Unknown work state: {work.state}") from error
        expected = states[current_index + 1] if current_index + 1 < len(states) else None
        if data.target_state != expected:
            raise ValueError(
                f"Invalid transition {work.state} -> {data.target_state}; "
                f"expected {expected or 'no further state'}"
            )
        if data.target_state == terminal_state:
            self._assert_work_gate(work)

        previous = work.state
        work.state = data.target_state
        atomic_write(Path(work.path) / "WORK.md", self._render_work(work))
        if swarm.status == "ready":
            swarm.status = "running"
            atomic_write(Path(swarm.path) / "SWARM.md", self._render_swarm(swarm))
        if data.target_state == terminal_state:
            work_directories = [
                item for item in (Path(swarm.path) / "work").iterdir() if item.is_dir()
            ]
            if all(
                self._load_work(swarm, item.name).state == terminal_state
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
        )

    def _load_project_configuration(self, root: Path) -> ProjectConfiguration:
        attributes = read_markdown(root / ".agora" / "project.md").attributes
        return ProjectConfiguration(
            project=string_attribute(attributes, "project"),
            integration=self._integration(string_attribute(attributes, "integration")),
            provider=string_attribute(attributes, "provider"),
            model=string_attribute(attributes, "model"),
            default_method=self._method(string_attribute(attributes, "default-method")),
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
        )

    def _require_actor_for_action(
        self, root: Path, swarm: SwarmRecord, actor_id: str, action: str
    ) -> ActorRecord:
        actor = self._find_actor(root, actor_id)
        roles = [
            role for role, reference in swarm.assignments.items() if reference == actor.reference
        ]
        if not roles:
            raise ValueError(f"Actor {actor.reference} is not assigned to swarm {swarm.id}")
        allowed = any(
            action
            in strings_attribute(
                read_markdown(
                    root / ".agora" / "methods" / swarm.method / "roles" / f"{role}.md"
                ).attributes,
                "allowed-actions",
            )
            for role in roles
        )
        if not allowed:
            raise PermissionError(f"Actor {actor.reference} is not allowed to perform {action}")
        return actor

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

    def _load_work(self, swarm: SwarmRecord, work_id: str) -> WorkRecord:
        assert_slug(work_id, "Work id")
        path = Path(swarm.path) / "work" / work_id
        document = read_markdown(path / "WORK.md")
        artifacts = read_markdown(path / "artifacts.md")
        evidence = read_markdown(path / "evidence.md")
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
    def _assert_work_gate(work: WorkRecord) -> None:
        unsatisfied = [
            item for item in work.acceptance_criteria if item not in work.satisfied_criteria
        ]
        missing_artifacts = [
            item for item in work.required_artifacts if item not in work.artifact_kinds
        ]
        has_success = "success" in work.evidence_results
        if unsatisfied or missing_artifacts or not has_success:
            raise ValueError(
                f"Final gate failed: unsatisfied=[{', '.join(unsatisfied)}], "
                f"missing-artifacts=[{', '.join(missing_artifacts)}], "
                f"successful-evidence={str(has_success).lower()}"
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

    @staticmethod
    def _assert_integration(value: str) -> None:
        if value not in INTEGRATIONS:
            raise ValueError(f"Unsupported integration: {value}. Choose {', '.join(INTEGRATIONS)}.")

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
