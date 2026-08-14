import { existsSync, readdirSync, readFileSync } from "node:fs";
import { basename, join, resolve } from "node:path";
import {
  actorKinds,
  integrations,
  methods,
  type ActorKind,
  type ActorRecord,
  type Integration,
  type Method,
  type ProjectConfiguration,
  type SwarmRecord,
  type UserConfiguration,
  type WorkRecord,
} from "./model.js";
import {
  readMarkdown,
  recordAttribute,
  renderMarkdown,
  stringAttribute,
  stringsAttribute,
  type MarkdownDocument,
} from "./markdown.js";
import {
  agoraHome,
  appendEntry,
  assertSlug,
  atomicWrite,
  copyTemplateTree,
  ensureDirectory,
  findProjectRoot,
  projectName,
  templateRoot,
  writeNew,
} from "./filesystem.js";
import { createBranch, currentBranch, isGitRepository } from "./git.js";

export interface ConfigureInput {
  integration: Integration;
  provider: string;
  model: string;
  defaultMethod: Method;
  force?: boolean;
}

export interface InitInput {
  target?: string;
  integration?: Integration;
  provider?: string;
  model?: string;
  defaultMethod?: Method;
  force?: boolean;
}

export interface AddActorInput {
  id: string;
  name: string;
  kind: ActorKind;
  capabilities: string[];
  scope: "user" | "project";
  description?: string;
  force?: boolean;
}

export interface CreateSwarmInput {
  id: string;
  objective: string;
  method?: Method;
  branch?: string;
  createBranch?: boolean;
}

export interface AssignActorInput {
  swarmId: string;
  roleId: string;
  actorId: string;
}

export interface CreateWorkInput {
  swarmId: string;
  id: string;
  title: string;
  description?: string;
  acceptanceCriteria: Array<{ id: string; description: string }>;
  requiredArtifacts: string[];
  actorId: string;
}

export interface WorkActorInput {
  swarmId: string;
  workId: string;
  actorId: string;
}

export interface TransitionWorkInput extends WorkActorInput {
  targetState: string;
}

export interface AddArtifactInput extends WorkActorInput {
  kind: string;
  uri: string;
}

export interface AddEvidenceInput extends WorkActorInput {
  type: string;
  result: "success" | "failure";
  artifactRefs: string[];
}

export interface DoctorCheck {
  name: string;
  ok: boolean;
  detail: string;
}

export class AgoraWorkspace {
  private readonly now: () => Date;
  private readonly cwd: string;

  constructor(options: { cwd?: string; now?: () => Date } = {}) {
    this.cwd = resolve(options.cwd ?? process.cwd());
    this.now = options.now ?? (() => new Date());
  }

  configure(input: ConfigureInput): UserConfiguration {
    this.assertIntegration(input.integration);
    this.assertMethod(input.defaultMethod);
    const configuration: UserConfiguration = {
      integration: input.integration,
      provider: input.provider,
      model: input.model,
      defaultMethod: input.defaultMethod,
    };
    const home = agoraHome();
    ensureDirectory(join(home, "actors"));
    ensureDirectory(join(home, "methods"));
    writeNew(
      join(home, "config.md"),
      renderMarkdown({
        attributes: {
          schema: "agora/user-config/v1",
          integration: configuration.integration,
          provider: configuration.provider,
          model: configuration.model,
          "default-method": configuration.defaultMethod,
          "updated-at": this.timestamp(),
        },
        body: "# Agora user configuration\n\nDefaults used when initializing a project.",
      }),
      input.force,
    );
    return configuration;
  }

  initialize(input: InitInput): ProjectConfiguration {
    const target = resolve(this.cwd, input.target ?? ".");
    ensureDirectory(target);
    const user = this.loadUserConfiguration();
    const configuration: ProjectConfiguration = {
      project: projectName(target),
      integration: input.integration ?? user?.integration ?? "generic",
      provider: input.provider ?? user?.provider ?? "configured-by-integration",
      model: input.model ?? user?.model ?? "configured-by-integration",
      defaultMethod: input.defaultMethod ?? user?.defaultMethod ?? "scrum",
      createdAt: this.timestamp(),
    };
    this.assertIntegration(configuration.integration);
    this.assertMethod(configuration.defaultMethod);

    const agora = join(target, ".agora");
    writeNew(
      join(agora, "project.md"),
      renderMarkdown({
        attributes: {
          schema: "agora/project/v1",
          version: "0.1.0",
          project: configuration.project,
          integration: configuration.integration,
          provider: configuration.provider,
          model: configuration.model,
          "default-method": configuration.defaultMethod,
          "created-at": configuration.createdAt,
        },
        body: "# Agora project\n\nThis file selects the local agent integration and governance defaults.",
      }),
      input.force,
    );
    const replacements = {
      PROJECT_NAME: configuration.project,
      INTEGRATION: configuration.integration,
      PROVIDER: configuration.provider,
      MODEL: configuration.model,
      DEFAULT_METHOD: configuration.defaultMethod,
    };
    copyTemplateTree(join(templateRoot(), "project"), agora, replacements, input.force ?? false);
    copyTemplateTree(
      join(templateRoot(), "methods"),
      join(agora, "methods"),
      replacements,
      input.force ?? false,
    );
    copyTemplateTree(
      join(templateRoot(), "commands"),
      join(agora, "commands"),
      replacements,
      input.force ?? false,
    );
    this.installIntegration(target, configuration.integration, replacements, input.force ?? false);
    const projectEvents = join(agora, "events.md");
    if (!existsSync(projectEvents)) writeNew(projectEvents, "# Project events\n\n");
    appendEntry(
      projectEvents,
      `- ${configuration.createdAt} | project.initialized | integration=${configuration.integration} | method=${configuration.defaultMethod}`,
    );
    return configuration;
  }

  addActor(input: AddActorInput): ActorRecord {
    assertSlug(input.id, "Actor id");
    if (!actorKinds.includes(input.kind)) throw new Error(`Unsupported actor kind: ${input.kind}`);
    const root = input.scope === "user" ? agoraHome() : join(this.projectRoot(), ".agora");
    const path = join(root, "actors", `${input.id}.md`);
    const capabilities = [...new Set(input.capabilities)].sort();
    writeNew(
      path,
      renderMarkdown({
        attributes: {
          schema: "agora/actor/v1",
          id: input.id,
          name: input.name,
          kind: input.kind,
          capabilities,
          scope: input.scope,
          "created-at": this.timestamp(),
        },
        body: `# ${input.name}\n\n${input.description ?? "Describe this actor's operating context and constraints."}`,
      }),
      input.force,
    );
    return {
      id: input.id,
      name: input.name,
      kind: input.kind,
      capabilities,
      path,
      reference: `${input.scope}:${input.id}`,
    };
  }

  createSwarm(input: CreateSwarmInput): SwarmRecord {
    assertSlug(input.id, "Swarm id");
    const root = this.projectRoot();
    const project = this.loadProjectConfiguration(root);
    const method = input.method ?? project.defaultMethod;
    this.assertMethod(method);
    const methodDocument = readMarkdown(join(root, ".agora", "methods", method, "METHOD.md"));
    const requiredRoles = stringsAttribute(methodDocument.attributes, "required-roles");
    const branch = input.branch ?? `agora/${input.id}`;
    const swarmPath = join(root, ".agora", "swarms", input.id);
    if (existsSync(swarmPath)) throw new Error(`Swarm already exists: ${input.id}`);
    if ((input.createBranch ?? true) && isGitRepository(root)) {
      createBranch(root, branch);
    }
    const effectiveBranch = isGitRepository(root) ? currentBranch(root) : "filesystem-only";
    const record: SwarmRecord = {
      id: input.id,
      method,
      status: "forming",
      branch: effectiveBranch,
      requiredRoles,
      assignments: {},
      objective: input.objective,
      path: swarmPath,
    };
    writeNew(join(swarmPath, "SWARM.md"), this.renderSwarm(record));
    writeNew(join(swarmPath, "events.md"), "# Swarm events\n\n");
    writeNew(join(swarmPath, "interactions.md"), "# Interactions\n\n");
    writeNew(join(swarmPath, "artifacts.md"), "# Swarm artifacts\n\n");
    writeNew(join(swarmPath, "evidence.md"), "# Swarm evidence\n\n");
    ensureDirectory(join(swarmPath, "work"));
    this.appendSwarmEvent(root, input.id, "swarm.created", `branch=${record.branch}`);
    return record;
  }

  assignActor(input: AssignActorInput): SwarmRecord {
    assertSlug(input.roleId, "Role id");
    const root = this.projectRoot();
    const swarm = this.loadSwarm(root, input.swarmId);
    if (swarm.status !== "forming" && swarm.status !== "ready") {
      throw new Error(`Cannot change assignments while swarm ${swarm.id} is ${swarm.status}`);
    }
    const actor = this.findActor(root, input.actorId);
    const rolePath = join(root, ".agora", "methods", swarm.method, "roles", `${input.roleId}.md`);
    if (!existsSync(rolePath)) {
      throw new Error(`Role ${input.roleId} is not defined by method ${swarm.method}`);
    }
    const role = readMarkdown(rolePath);
    const requiredCapabilities = stringsAttribute(role.attributes, "required-capabilities");
    const allowedKinds = stringsAttribute(role.attributes, "allowed-actor-kinds");
    const missing = requiredCapabilities.filter(
      (capability) => !actor.capabilities.includes(capability),
    );
    if (missing.length > 0) {
      throw new Error(
        `Actor ${actor.id} lacks capabilities required by ${input.roleId}: ${missing.join(", ")}`,
      );
    }
    if (!allowedKinds.includes(actor.kind)) {
      throw new Error(`Actor kind ${actor.kind} is not allowed for role ${input.roleId}`);
    }
    swarm.assignments[input.roleId] = actor.reference;
    swarm.status = swarm.requiredRoles.every((roleId) => swarm.assignments[roleId])
      ? "ready"
      : "forming";
    atomicWrite(join(swarm.path, "SWARM.md"), this.renderSwarm(swarm));
    this.appendSwarmEvent(
      root,
      swarm.id,
      "swarm.actor-assigned",
      `role=${input.roleId} actor=${actor.reference}`,
    );
    return swarm;
  }

  showSwarm(swarmId: string): SwarmRecord {
    return this.loadSwarm(this.projectRoot(), swarmId);
  }

  createWork(input: CreateWorkInput): WorkRecord {
    assertSlug(input.id, "Work id");
    const root = this.projectRoot();
    const swarm = this.loadSwarm(root, input.swarmId);
    if (swarm.status !== "ready" && swarm.status !== "running") {
      throw new Error(`Swarm ${swarm.id} must be ready before work can be created`);
    }
    const actor = this.requireActorForAction(root, swarm, input.actorId, "work.create");
    const method = readMarkdown(join(root, ".agora", "methods", swarm.method, "METHOD.md"));
    const states = stringsAttribute(method.attributes, "work-states");
    const firstState = states[0];
    if (!firstState) throw new Error(`Method ${swarm.method} defines no work states`);
    const criteria = Object.fromEntries(
      input.acceptanceCriteria.map((criterion) => {
        assertSlug(criterion.id, "Criterion id");
        return [criterion.id, criterion.description];
      }),
    );
    if (Object.keys(criteria).length !== input.acceptanceCriteria.length) {
      throw new Error("Acceptance criterion ids must be unique");
    }
    const path = join(swarm.path, "work", input.id);
    const work: WorkRecord = {
      id: input.id,
      swarmId: swarm.id,
      title: input.title,
      description: input.description ?? "",
      state: firstState,
      acceptanceCriteria: criteria,
      satisfiedCriteria: [],
      requiredArtifacts: [...new Set(input.requiredArtifacts)],
      artifactKinds: [],
      evidenceResults: [],
      path,
    };
    writeNew(join(path, "WORK.md"), this.renderWork(work));
    writeNew(
      join(path, "artifacts.md"),
      renderMarkdown({
        attributes: { schema: "agora/artifacts/v1", "artifact-kinds": [] },
        body: "# Artifacts\n\n| Kind | URI | Produced by | Timestamp |\n| --- | --- | --- | --- |",
      }),
    );
    writeNew(
      join(path, "evidence.md"),
      renderMarkdown({
        attributes: { schema: "agora/evidence/v1", results: [] },
        body: "# Evidence\n\n| Type | Result | Artifact references | Produced by | Timestamp |\n| --- | --- | --- | --- | --- |",
      }),
    );
    writeNew(join(path, "interactions.md"), "# Interactions\n\n");
    this.appendWorkEvent(work, "work.created", `state=${work.state} actor=${actor.reference}`);
    return work;
  }

  satisfyCriterion(input: WorkActorInput & { criterionId: string }): WorkRecord {
    const root = this.projectRoot();
    const swarm = this.loadSwarm(root, input.swarmId);
    const actor = this.requireActorForAction(root, swarm, input.actorId, "criterion.satisfy");
    const work = this.loadWork(swarm, input.workId);
    if (!work.acceptanceCriteria[input.criterionId]) {
      throw new Error(`Acceptance criterion not found: ${input.criterionId}`);
    }
    work.satisfiedCriteria = [...new Set([...work.satisfiedCriteria, input.criterionId])];
    atomicWrite(join(work.path, "WORK.md"), this.renderWork(work));
    this.appendWorkEvent(
      work,
      "work.criterion-satisfied",
      `criterion=${input.criterionId} actor=${actor.reference}`,
    );
    return work;
  }

  addArtifact(input: AddArtifactInput): WorkRecord {
    const root = this.projectRoot();
    const swarm = this.loadSwarm(root, input.swarmId);
    const actor = this.requireActorForAction(root, swarm, input.actorId, "artifact.add");
    const work = this.loadWork(swarm, input.workId);
    const path = join(work.path, "artifacts.md");
    const document = readMarkdown(path);
    const kinds = stringsAttribute(document.attributes, "artifact-kinds");
    document.attributes["artifact-kinds"] = [...new Set([...kinds, input.kind])];
    document.body = `${document.body.trimEnd()}\n| ${input.kind} | ${input.uri} | ${actor.reference} | ${this.timestamp()} |`;
    atomicWrite(path, renderMarkdown(document));
    this.appendWorkEvent(
      work,
      "artifact.added",
      `kind=${input.kind} uri=${input.uri} actor=${actor.reference}`,
    );
    return this.loadWork(swarm, input.workId);
  }

  addEvidence(input: AddEvidenceInput): WorkRecord {
    const root = this.projectRoot();
    const swarm = this.loadSwarm(root, input.swarmId);
    const actor = this.requireActorForAction(root, swarm, input.actorId, "evidence.add");
    const work = this.loadWork(swarm, input.workId);
    const path = join(work.path, "evidence.md");
    const document = readMarkdown(path);
    const results = stringsAttribute(document.attributes, "results");
    document.attributes.results = [...results, input.result];
    document.body = `${document.body.trimEnd()}\n| ${input.type} | ${input.result} | ${input.artifactRefs.join(", ") || "none"} | ${actor.reference} | ${this.timestamp()} |`;
    atomicWrite(path, renderMarkdown(document));
    this.appendWorkEvent(
      work,
      "evidence.added",
      `type=${input.type} result=${input.result} actor=${actor.reference}`,
    );
    return this.loadWork(swarm, input.workId);
  }

  transitionWork(input: TransitionWorkInput): WorkRecord {
    const root = this.projectRoot();
    const swarm = this.loadSwarm(root, input.swarmId);
    const actor = this.requireActorForAction(root, swarm, input.actorId, "work.transition");
    const work = this.loadWork(swarm, input.workId);
    const method = readMarkdown(join(root, ".agora", "methods", swarm.method, "METHOD.md"));
    const states = stringsAttribute(method.attributes, "work-states");
    const currentIndex = states.indexOf(work.state);
    const expected = states[currentIndex + 1];
    if (input.targetState !== expected) {
      throw new Error(
        `Invalid transition ${work.state} -> ${input.targetState}; expected ${expected ?? "no further state"}`,
      );
    }
    if (input.targetState === states.at(-1)) this.assertWorkGate(work);
    const previous = work.state;
    work.state = input.targetState;
    atomicWrite(join(work.path, "WORK.md"), this.renderWork(work));
    if (swarm.status === "ready") {
      swarm.status = "running";
      atomicWrite(join(swarm.path, "SWARM.md"), this.renderSwarm(swarm));
    }
    if (input.targetState === states.at(-1)) {
      const workRoot = join(swarm.path, "work");
      const allComplete = readdirSync(workRoot, { withFileTypes: true })
        .filter((entry) => entry.isDirectory())
        .every((entry) => this.loadWork(swarm, entry.name).state === states.at(-1));
      if (allComplete) {
        swarm.status = "completed";
        atomicWrite(join(swarm.path, "SWARM.md"), this.renderSwarm(swarm));
        this.appendSwarmEvent(root, swarm.id, "swarm.completed", `work=${work.id}`);
      }
    }
    this.appendWorkEvent(
      work,
      "work.transitioned",
      `from=${previous} to=${input.targetState} actor=${actor.reference}`,
    );
    return work;
  }

  showWork(swarmId: string, workId: string): WorkRecord {
    const swarm = this.loadSwarm(this.projectRoot(), swarmId);
    return this.loadWork(swarm, workId);
  }

  doctor(): DoctorCheck[] {
    const root = this.projectRoot();
    const configuration = this.loadProjectConfiguration(root);
    const agora = join(root, ".agora");
    const integrationPath =
      configuration.integration === "codex"
        ? join(root, ".agents", "skills", "agora-objective", "SKILL.md")
        : configuration.integration === "claude"
          ? join(root, ".claude", "commands", "agora.objective.md")
          : join(agora, "commands", "objective.md");
    return [
      { name: "project", ok: true, detail: root },
      {
        name: "constitution",
        ok: existsSync(join(agora, "constitution.md")),
        detail: join(agora, "constitution.md"),
      },
      {
        name: "method",
        ok: existsSync(join(agora, "methods", configuration.defaultMethod, "METHOD.md")),
        detail: configuration.defaultMethod,
      },
      {
        name: "integration",
        ok: existsSync(integrationPath),
        detail: `${configuration.integration}: ${integrationPath}`,
      },
      {
        name: "git",
        ok: isGitRepository(root),
        detail: isGitRepository(root) ? currentBranch(root) : "filesystem-only mode",
      },
    ];
  }

  projectRoot(): string {
    return findProjectRoot(this.cwd);
  }

  private loadUserConfiguration(): UserConfiguration | undefined {
    const path = join(agoraHome(), "config.md");
    if (!existsSync(path)) return undefined;
    const { attributes } = readMarkdown(path);
    return {
      integration: stringAttribute(attributes, "integration") as Integration,
      provider: stringAttribute(attributes, "provider"),
      model: stringAttribute(attributes, "model"),
      defaultMethod: stringAttribute(attributes, "default-method") as Method,
    };
  }

  private loadProjectConfiguration(root: string): ProjectConfiguration {
    const { attributes } = readMarkdown(join(root, ".agora", "project.md"));
    return {
      project: stringAttribute(attributes, "project"),
      integration: stringAttribute(attributes, "integration") as Integration,
      provider: stringAttribute(attributes, "provider"),
      model: stringAttribute(attributes, "model"),
      defaultMethod: stringAttribute(attributes, "default-method") as Method,
      createdAt: stringAttribute(attributes, "created-at"),
    };
  }

  private installIntegration(
    target: string,
    integration: Integration,
    replacements: Record<string, string>,
    force: boolean,
  ): void {
    const commands = join(templateRoot(), "commands");
    if (integration === "generic") return;
    for (const file of readdirSync(commands).filter((name) => name.endsWith(".md"))) {
      const id = basename(file, ".md");
      const source = readFileSync(join(commands, file), "utf8");
      let contents = source;
      for (const [key, value] of Object.entries(replacements)) {
        contents = contents.replaceAll(`{{${key}}}`, value);
      }
      const destination =
        integration === "codex"
          ? join(target, ".agents", "skills", `agora-${id}`, "SKILL.md")
          : join(target, ".claude", "commands", `agora.${id}.md`);
      writeNew(destination, contents, force);
    }
  }

  private findActor(root: string, reference: string): ActorRecord {
    const explicit = reference.includes(":") ? reference.split(":", 2) : undefined;
    if (explicit && explicit[0] !== "user" && explicit[0] !== "project") {
      throw new Error(`Unsupported actor scope: ${explicit[0]}`);
    }
    const id = explicit?.[1] ?? reference;
    assertSlug(id, "Actor id");
    const candidates = explicit
      ? [
          explicit[0] === "user"
            ? { scope: "user", path: join(agoraHome(), "actors", `${id}.md`) }
            : { scope: "project", path: join(root, ".agora", "actors", `${id}.md`) },
        ]
      : [
          { scope: "project", path: join(root, ".agora", "actors", `${id}.md`) },
          { scope: "user", path: join(agoraHome(), "actors", `${id}.md`) },
        ];
    const candidate = candidates.find((item) => existsSync(item.path));
    if (!candidate) throw new Error(`Actor not found: ${reference}`);
    const document = readMarkdown(candidate.path);
    return {
      id: stringAttribute(document.attributes, "id"),
      name: stringAttribute(document.attributes, "name"),
      kind: stringAttribute(document.attributes, "kind") as ActorKind,
      capabilities: stringsAttribute(document.attributes, "capabilities"),
      path: candidate.path,
      reference: `${candidate.scope}:${id}`,
    };
  }

  private requireActorForAction(
    root: string,
    swarm: SwarmRecord,
    actorId: string,
    action: string,
  ): ActorRecord {
    const actor = this.findActor(root, actorId);
    const roles = Object.entries(swarm.assignments)
      .filter(([, reference]) => reference === actor.reference)
      .map(([role]) => role);
    if (roles.length === 0) {
      throw new Error(`Actor ${actor.reference} is not assigned to swarm ${swarm.id}`);
    }
    const allowed = roles.some((role) => {
      const document = readMarkdown(
        join(root, ".agora", "methods", swarm.method, "roles", `${role}.md`),
      );
      return stringsAttribute(document.attributes, "allowed-actions").includes(action);
    });
    if (!allowed) {
      throw new Error(`Actor ${actor.reference} is not allowed to perform ${action}`);
    }
    return actor;
  }

  private loadWork(swarm: SwarmRecord, workId: string): WorkRecord {
    assertSlug(workId, "Work id");
    const path = join(swarm.path, "work", workId);
    const document = readMarkdown(join(path, "WORK.md"));
    const artifacts = readMarkdown(join(path, "artifacts.md"));
    const evidence = readMarkdown(join(path, "evidence.md"));
    return {
      id: stringAttribute(document.attributes, "id"),
      swarmId: stringAttribute(document.attributes, "swarm"),
      title: stringAttribute(document.attributes, "title"),
      description: extractSection(document.body, "Description"),
      state: stringAttribute(document.attributes, "state"),
      acceptanceCriteria: recordAttribute(document.attributes, "acceptance-criteria"),
      satisfiedCriteria: stringsAttribute(document.attributes, "satisfied-criteria"),
      requiredArtifacts: stringsAttribute(document.attributes, "required-artifacts"),
      artifactKinds: stringsAttribute(artifacts.attributes, "artifact-kinds"),
      evidenceResults: stringsAttribute(evidence.attributes, "results"),
      path,
    };
  }

  private renderWork(work: WorkRecord): string {
    const checklist = Object.entries(work.acceptanceCriteria)
      .map(
        ([id, description]) =>
          `- [${work.satisfiedCriteria.includes(id) ? "x" : " "}] **${id}:** ${description}`,
      )
      .join("\n");
    const artifacts = work.requiredArtifacts.map((kind) => `- ${kind}`).join("\n") || "- none";
    return renderMarkdown({
      attributes: {
        schema: "agora/work/v1",
        id: work.id,
        swarm: work.swarmId,
        title: work.title,
        state: work.state,
        "acceptance-criteria": work.acceptanceCriteria,
        "satisfied-criteria": work.satisfiedCriteria,
        "required-artifacts": work.requiredArtifacts,
      },
      body: `# ${work.title}\n\n## Description\n\n${work.description || "No description provided."}\n\n## Acceptance criteria\n\n${checklist || "- none"}\n\n## Required artifacts\n\n${artifacts}`,
    });
  }

  private assertWorkGate(work: WorkRecord): void {
    const unsatisfied = Object.keys(work.acceptanceCriteria).filter(
      (id) => !work.satisfiedCriteria.includes(id),
    );
    const missingArtifacts = work.requiredArtifacts.filter(
      (kind) => !work.artifactKinds.includes(kind),
    );
    const hasSuccess = work.evidenceResults.includes("success");
    if (unsatisfied.length > 0 || missingArtifacts.length > 0 || !hasSuccess) {
      throw new Error(
        `Final gate failed: unsatisfied=[${unsatisfied.join(", ")}], missing-artifacts=[${missingArtifacts.join(", ")}], successful-evidence=${hasSuccess}`,
      );
    }
  }

  private appendWorkEvent(work: WorkRecord, type: string, detail: string): void {
    const path = join(work.path, "events.md");
    if (!existsSync(path)) writeNew(path, "# Work events\n\n");
    appendEntry(path, `- ${this.timestamp()} | ${type} | ${detail}`);
  }

  private loadSwarm(root: string, swarmId: string): SwarmRecord {
    assertSlug(swarmId, "Swarm id");
    const path = join(root, ".agora", "swarms", swarmId);
    const document = readMarkdown(join(path, "SWARM.md"));
    return {
      id: stringAttribute(document.attributes, "id"),
      method: stringAttribute(document.attributes, "method"),
      status: stringAttribute(document.attributes, "status"),
      branch: stringAttribute(document.attributes, "branch"),
      requiredRoles: stringsAttribute(document.attributes, "required-roles"),
      assignments: recordAttribute(document.attributes, "assignments"),
      objective: extractSection(document.body, "Objective"),
      path,
    };
  }

  private renderSwarm(swarm: SwarmRecord): string {
    const assignments = swarm.requiredRoles
      .map((role) => `| ${role} | ${swarm.assignments[role] ?? "unassigned"} |`)
      .join("\n");
    const document: MarkdownDocument = {
      attributes: {
        schema: "agora/swarm/v1",
        id: swarm.id,
        method: swarm.method,
        status: swarm.status,
        branch: swarm.branch,
        "required-roles": swarm.requiredRoles,
        assignments: swarm.assignments,
      },
      body: `# Swarm ${swarm.id}\n\n## Objective\n\n${swarm.objective}\n\n## Assignments\n\n| Role | Actor |\n| --- | --- |\n${assignments}`,
    };
    return renderMarkdown(document);
  }

  private appendSwarmEvent(root: string, swarmId: string, type: string, detail: string): void {
    appendEntry(
      join(root, ".agora", "swarms", swarmId, "events.md"),
      `- ${this.timestamp()} | ${type} | ${detail}`,
    );
  }

  private assertIntegration(value: string): asserts value is Integration {
    if (!integrations.includes(value as Integration)) {
      throw new Error(`Unsupported integration: ${value}. Choose ${integrations.join(", ")}.`);
    }
  }

  private assertMethod(value: string): asserts value is Method {
    if (!methods.includes(value as Method)) {
      throw new Error(`Unsupported method: ${value}. Choose ${methods.join(", ")}.`);
    }
  }

  private timestamp(): string {
    return this.now().toISOString();
  }
}

function extractSection(body: string, heading: string): string {
  const pattern = new RegExp(`## ${heading}\\n\\n([\\s\\S]*?)(?:\\n\\n## |$)`);
  return body.match(pattern)?.[1]?.trim() ?? "";
}
