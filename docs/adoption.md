# Visual adoption guide

This guide is the shortest path from a clean machine to a governed Agora workflow. It focuses on
decisions and observable outcomes; the linked guides provide the complete command and policy
reference.

## Adoption journey

```mermaid
flowchart LR
    A[Install Agora] --> B[Run the zero-config self-test]
    B --> C[Run agora setup]
    C --> D[Review runtime, method, security, and persistence]
    D --> E[Confirm the project plan]
    E --> F[Review generated protocol]
    F --> G[Run governed work]
    G --> H[Validate and commit Markdown state]
    H --> I[Add team policy and integrations]
```

You can complete the first eight steps locally. Jira, CI/CD, cloud, documentation systems, and
remote registries remain optional adapters around the same filesystem protocol.

## 1. Install

Agora requires Python 3.11 or newer. For daily use from this checkout:

```bash
git clone https://github.com/fabianaguero/agora.git
cd agora
uv tool install .
agora --help
cd ..
```

Use `uv sync --extra dev` and prefix commands with `uv run` when contributing to Agora itself. See
[Installation and customization](guides/installation-and-customization.md) for editable installs,
wheels, virtual environments, upgrades, and removal.

## 2. Verify the installation

Before selecting an LLM, configuring an integration, or creating a project, run:

```bash
agora self-test
```

```mermaid
flowchart LR
    S[agora self-test] --> M[3 bundled methods]
    S --> A[Human, AI agent, and swarm]
    M --> C[9 complete lifecycle cases]
    A --> C
    C --> V[24 valid role assignments]
    C --> R[24 forbidden assignments rejected]
    V --> OK[Installation confidence]
    R --> OK
```

The command runs in temporary workspaces and needs no project, LLM, provider account, key, or
repository. A successful report and exit status `0` confirm that the installed distribution can
govern all bundled roles through terminal work states. See the
[Role conformance test harness](guides/self-test.md) for the complete visual walkthrough, CI usage,
and assurance boundary.

## 3. Choose the execution environment

The integration controls where Agora places agent instructions. Provider and model remain opaque
configuration labels; the Agora kernel does not import an LLM SDK.

```mermaid
flowchart TD
    A{Where will agents run?}
    A -->|Codex CLI or IDE| B[integration: codex]
    A -->|Claude Code| C[integration: claude]
    A -->|Other IDE, CI, local model, or orchestrator| D[integration: generic]
    B --> E[Generate .agents/skills/agora-*]
    C --> F[Generate .claude/commands/agora.*.md]
    D --> G[Use .agora/commands/*.md directly]
    E --> H[Same .agora protocol]
    F --> H
    G --> H
```

The recommended path presents these choices sequentially and can optionally persist personal
defaults:

```bash
agora setup
```

For automation or explicit manual assembly, configure personal defaults directly:

```bash
agora configure \
  --integration codex \
  --provider openai \
  --model configured-by-codex \
  --default-method scrum
```

Substitute `claude` or `generic` when appropriate. See [LLM environments](guides/llm-environments.md)
for all three paths.

Choose the initial Method Pack by the shape of the work:

| Method Pack | Start with it when |
| --- | --- |
| `scrum` | Accountable roles deliver increments through explicit review and acceptance gates |
| `kanban` | Flow, WIP, and service-oriented responsibility matter more than iteration structure |
| `spec-driven` | Requirements must be clarified and accepted before implementation begins |

All three are replaceable examples. A custom Method Pack can define different roles, transitions,
gates, and required artifacts without changing Agora's kernel.

## 4. Start a project

For the fastest useful workspace:

```bash
mkdir payment-service
cd payment-service
git init
agora setup
agora doctor
agora validate
```

The wizard creates a project, one human actor, one AI actor, a method-compatible swarm, and its
assignments after confirmation. The default mode stores no private keys. Select signed security
when every actor should use an external Ed25519 identity from the beginning.

Use `agora init` instead when you want to register actors and form the swarm step by step.

### Adopt an existing codebase

Start from the clean base branch that will receive the feature:

```bash
git status --short
agora adopt
```

```mermaid
flowchart TD
    A[Existing repository] --> B[Read-only adoption preflight]
    B -->|fail| C[No files or branches changed]
    B -->|pass| D[Create agora/id branch]
    D --> E[Initialize project and actors]
    E --> F[Create swarm and assign roles]
    F -->|success| G[Persist reviewable Agora state]
    E -->|failure| H[Restore files and external quickstart keys]
    F -->|failure| H
    H --> I[Return to original branch]
    I --> J[Delete failed feature branch]
```

The preflight stops when `.agora` or the selected Codex/Claude projection is ignored, because work
that cannot enter Git cannot provide durable collaboration history. It also catches dirty state,
detached or unexpected branches, a colliding `agora/<id>` branch, partial initialization, reserved
quickstart identities, and a missing configured runtime. `--allow-dirty` is an explicit exception
for reviewed local changes; it does not bypass any other check.

Run the [existing codebase feature pilot](../samples/existing-codebase-feature/README.md) to exercise
this entire path against a non-empty repository without an LLM, network, or provider credentials.

## 5. Review what Agora created

```mermaid
flowchart TD
    Q[agora quickstart] --> P[Project policy]
    Q --> M[Method and Tool Packs]
    Q --> A[Actors and assignments]
    Q --> S[Swarm objective]
    Q --> I[Agent instructions]
    P --> P1[.agora/constitution.md]
    P --> P2[.agora/PROTOCOL.md]
    P --> P3[.agora/STANDARDS.md]
    M --> M1[.agora/methods/]
    M --> M2[.agora/tools/]
    A --> A1[.agora/actors/]
    S --> S1[.agora/swarms/]
    I --> I1[.agora/commands/]
```

Read the constitution, protocol, standards, selected Method Pack, and assigned role before running
work. The files are reviewable project state, not generated cache.

The complete distinction between documentation, templates, agent adapters, durable Agora records,
and external work products is in [Documentation and artifact locations](reference/artifact-locations.md).

## 6. Run the first governed work item

The exact roles and state names come from the active Method Pack. A typical execution loop is:

```mermaid
sequenceDiagram
    participant Human
    participant Agent
    participant Agora
    participant Git
    Human->>Agora: Create objective and governed work
    Agora-->>Agent: Materialize role, policy, and context
    Agent->>Agora: Request permitted transition
    Agent->>Agent: Implement and test
    Agent->>Agora: Record artifact and evidence references
    Human->>Agora: Review, approve, and complete
    Agora->>Agora: Validate gates and durable records
    Human->>Git: Review and commit .agora plus product changes
```

Prepare a durable agent session with:

```bash
agora start \
  --id implementation-session \
  --actor <actor-id> \
  --swarm <swarm-id> \
  --work <work-id>
```

Without `--launch`, this only writes `SESSION.md` and `CONTEXT.md`. With `--launch`, Agora delegates
execution to the configured local runner while keeping lifecycle authority in the filesystem.

## 7. Validate and share

```bash
agora status
agora validate
git status
git add .agora .agents
git commit -m "feat(governance): initialize Agora workflow"
```

For Claude, stage `.claude` instead of `.agents`. For `generic`, `.agora/commands` is the only command
projection. Include product changes and referenced local artifacts in the same review when useful.

## Adoption levels

```mermaid
flowchart LR
    A[Personal pilot] --> B[Shared team protocol]
    B --> C[Governed external tools]
    C --> D[Authenticated high-impact operations]
    A --- A1[Quickstart, local Git, one Method Pack]
    B --- B1[Reviewed constitution, roles, gates, branch workflow]
    C --- C1[Jira, CI/CD, docs, cloud, observability adapters]
    D --- D1[Actor keys, approvals, environment policy, signed actions]
```

### Personal pilot

- Use simple quickstart mode.
- Keep the bundled Scrum, Kanban, or spec-driven Method Pack.
- Validate before each commit.

### Shared team protocol

- Review `.agora/constitution.md`, `PROTOCOL.md`, and `STANDARDS.md` in a pull request.
- Register accountable human, AI, service, and swarm actors.
- Customize a Method Pack only when the workflow needs different roles, transitions, or gates.

### Governed integrations

- Prefer an already installed, reviewed native CLI adapter.
- Grant operations through role capabilities and project environment policy.
- Keep credentials in the provider CLI or external workload identity, never in Agora Markdown.

### High-impact operations

- Require actor authentication for signed lifecycle changes.
- Require approvals and evidence for production environments.
- Use signed releases, transparency proofs, and scoped trust for remote registries.

## Where to continue

| Goal | Guide |
| --- | --- |
| Understand every generated directory | [Documentation and artifact locations](reference/artifact-locations.md) |
| Customize installation and scopes | [Installation and customization](guides/installation-and-customization.md) |
| Verify human, AI-agent, and swarm role conformance | [Role conformance test harness](guides/self-test.md) |
| Run the complete manual first workflow | [Getting started](getting-started.md) |
| Compare Codex, Claude, and generic runtimes | [LLM environments](guides/llm-environments.md) |
| Deliver with Scrum roles and gates | [Scrum delivery](guides/scrum-delivery.md) |
| Manage continuous pull and WIP | [Kanban delivery](guides/kanban-delivery.md) |
| Clarify a specification before implementation | [Spec-driven delivery](guides/spec-driven-delivery.md) |
| Connect daily developer tools | [CLI-first ecosystem adapters](guides/cli-first-adapters.md) |
| Operate and validate a workspace | [Operations and validation](guides/operations-and-validation.md) |
