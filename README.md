# Agora

**Agents, Governance, Orchestration, Roles & Artifacts**

Agora is a local, Markdown-first, Git-native lifecycle customization framework. It lets teams define
how humans, AI agents, services, automations, and swarms collaborate from an objective through its
completion. Install it once, select an agent or LLM environment, and materialize the roles,
protocols, tools, Method Packs, artifacts, and gates that govern each project.

Agora is deliberately agnostic in three dimensions:

- **Language:** governed projects may use any programming language, runtime, architecture, or stack.
- **LLM:** providers and models are selected configuration, never dependencies of the core protocol.
- **Development process:** Scrum and Kanban are included presets; any valid Method Pack can define
  the roles, states, transitions, policies, and evidence required by a team's own lifecycle.

The reference CLI is implemented in Python for portability and maintainability. That is an
implementation detail of Agora itself, not a constraint placed on projects that use it.

Agora is not a project manager, an agent runtime, a coding framework, or an implementation of a
particular methodology. It does not replace Jira, GitHub, CI/CD, Confluence, or cloud platforms. It
installs a portable governance layer over those environments and keeps the customized lifecycle in
reviewable files and Git branches.

> Status: experimental MVP. Markdown contracts may evolve before the first stable release.

## Installation model

```text
Agora distribution
  Python CLI + templates + Method Packs + adapters

~/.agora/
  config.md             Runtime, method, and delegation defaults
  actors/*.md           Reusable user actors

<project>/.agora/
  project.md            Effective project configuration
  constitution.md       Local principles and restrictions
  PROTOCOL.md           Shared collaboration protocol
  commands/*.md         Portable agent commands
  methods/              Built-in and custom lifecycle Method Packs
  actors/               Project-specific actors
  tools/                Policy and installed Tool Packs
  artifacts/            Artifact catalog
  delegations/          Parent-to-child work contracts and collection state
  swarms/               Durable work state
  sessions/             Resolved runtimes and compiled execution context
  tool-runs/             Governed external invocations and results
```

Configuration precedence is:

```text
Agora defaults < ~/.agora < project .agora < swarm configuration
```

## Install from this repository

Agora requires Python 3.11 or newer. The recommended development and tool manager is
[uv](https://docs.astral.sh/uv/).

```bash
uv sync --extra dev
uv tool install .
agora --help
```

Run the development checkout without a global installation:

```bash
uv run agora --help
```

## Configure and initialize

```bash
agora configure \
  --integration codex \
  --provider openai \
  --model configured-by-codex \
  --default-method scrum \
  --max-delegation-depth 3

cd my-project
agora init
agora doctor
```

Initial integrations:

- `codex`: installs skills under `.agents/skills/agora-*/SKILL.md`.
- `claude`: installs commands under `.claude/commands/agora.*.md`.
- `generic`: keeps portable commands under `.agora/commands`.

Provider and model values describe the selected environment. This MVP does not call an LLM API or
store credentials.

## Customize the lifecycle

A Method Pack is a Markdown contract for a work lifecycle. It defines role requirements, allowed
actor kinds and actions, transition graphs, WIP limits, gates, approval requirements, protocol, and
tool policy. The core does not attach special behavior to the names Scrum or Kanban.

Install a custom pack for reuse across projects:

```bash
agora method install --source ./my-method-pack --scope user
agora configure --default-method my-method
agora init
```

Install a pack only in the current initialized project:

```bash
agora method install --source ./my-method-pack --scope project
agora swarm create --id delivery --objective "Deliver the objective" --method my-method
```

See [the custom lifecycle sample](samples/custom-lifecycle/README.md) for a pack that does not derive
from Scrum or Kanban.

## Actors and swarms

Actors may be `human`, `ai-agent`, `swarm`, `service`, or `automation`. A Method Pack determines which
actor kinds, capabilities, and actions each role permits.

```bash
agora actor add --scope user \
  --id owner --name "Product Owner" --kind human \
  --capability backlog-management --capability acceptance

agora actor add --id facilitator --name "AI Facilitator" --kind ai-agent \
  --capability facilitation --capability governance \
  --integration codex --provider openai --model configured-by-codex

agora actor add --id delivery-swarm --name "Delivery Swarm" --kind swarm \
  --capability implementation

agora actor add --id ai-developer --name "AI Developer" --kind ai-agent \
  --capability implementation

agora swarm create --id payments --objective "Deliver governed payment changes"
agora swarm assign --swarm payments --role product-owner --actor user:owner
agora swarm assign --swarm payments --role scrum-master --actor facilitator
agora swarm assign --swarm payments --role developer --actor delivery-swarm
```

In a Git repository, `swarm create` creates `agora/<swarm-id>` by default. Use `--no-branch` to retain
the current branch. The global `--project <path>` option lets IDEs, runners, and cloud environments
operate on an initialized project without changing their working directory.

Responsibility may change actor form while work is running. A handoff validates the receiver against
the same role and preserves both identities:

```bash
agora swarm handoff --id delivery-to-ai \
  --swarm payments --role developer \
  --from delivery-swarm --to ai-developer --by delivery-swarm \
  --reason "Continue implementation in the approved AI runtime"
```

Role holders need `handoff.create` to transfer their own role. Governance roles need
`handoff.manage` to transfer another role. Current assignment changes in `SWARM.md`; history remains
under the swarm's `handoffs/` directory and event log.

## Recursive swarms

A project-scoped actor whose kind is `swarm` may link to a real child swarm:

```bash
agora actor add --id specialist-team --name "Specialist Team" --kind swarm \
  --capability implementation --represented-swarm payment-specialists

agora swarm assign --swarm payments --role developer --actor specialist-team
```

The child must already be ready or running. Agora rejects direct and indirect cycles and any graph
whose longest chain exceeds project `max-delegation-depth`. Sessions for the linked actor include
both parent and child swarm context. Unlinked swarm actors remain valid for external composite teams.

## Delegated work

A linked actor may turn a bounded part of parent work into a governed child work item. Proposal,
child acceptance, and result collection are explicit steps:

```bash
agora delegation create --id specialist-task \
  --swarm payments --work payment-api \
  --to-actor specialist-team --child-work payment-internals \
  --title "Implement payment internals" \
  --criterion usable:"The parent can integrate the result" \
  --required-artifact implementation --result-kind delegated-result \
  --by specialist-team

agora delegation accept --delegation specialist-task --by owner
# The child completes payment-internals under its own method, roles, and gates.
agora delegation collect --delegation specialist-task --by specialist-team
```

Collection registers an `agora://` reference and successful delegated-work evidence in the parent;
it does not copy child artifacts or bypass parent acceptance. See the
[delegated work guide](docs/guides/delegated-work.md).

## Governed sessions

Prepare a durable context for an assigned actor and work item:

```bash
agora start --id payment-session --actor delivery-swarm \
  --swarm payments --work payment-api
```

The session records the effective actor or project runtime and writes `.agora/sessions/payment-session`
with `SESSION.md` and `CONTEXT.md`. Add `--launch` to execute the detected Codex or Claude command, or
provide `--runner "<command>"` for a generic environment. Agora delegates to the external process and
does not import an LLM SDK.

## Governed developer tools

Tool Packs expose selected operations from repositories, issue trackers, CI/CD, documentation, cloud,
observability, or communication CLIs. An operation declares structured arguments, required inputs,
risk, a provider-neutral capability, and optional approval policy. Method Pack roles grant those
capabilities explicitly.

Agora includes a Git-backed `repository` pack:

```bash
agora tool show --tool repository
agora tool invoke --id payment-status \
  --tool repository --operation status \
  --actor delivery-swarm --swarm payments --launch
```

The executable runs without a shell. Agora persists `RUN.md`, captures output and exit status in
`RESULT.md`, and stores no credentials. Omitting `--launch` creates a portable invocation for an IDE,
CI worker, or cloud executor.

## Governed work

```bash
agora work create --swarm payments --id payment-api --title "Implement payment API" \
  --by owner --criterion api-works:"The API satisfies its contract" \
  --required-artifact source-code --required-artifact test-report

agora work transition --swarm payments --work payment-api --to planned --by delivery-swarm
agora artifact add --swarm payments --work payment-api \
  --kind source-code --uri repo://src/payment.py --by delivery-swarm
agora evidence add --swarm payments --work payment-api \
  --type test-run --result success --artifact repo://src/payment.py --by facilitator
agora work criterion-satisfy --swarm payments --work payment-api \
  --criterion api-works --by owner
agora approval add --swarm payments --work payment-api \
  --role product-owner --by owner --note "Accepted for completion"
```

Transitions come from Markdown files in the installed Method Pack. Packs may define rework paths and
per-state WIP limits. A gated terminal transition can require:

1. Every acceptance criterion is satisfied.
2. Every required artifact kind is registered.
3. At least one successful evidence record exists.
4. Explicit approvals from configured roles.
5. The acting participant holds a role permitted for that exact transition.

## Persistence

Each swarm contains its manifest, assignments, interactions, events, work, artifacts, and evidence:

```text
.agora/delegations/specialist-task/
  DELEGATION.md

.agora/swarms/payments/
  SWARM.md
  events.md
  interactions.md
  artifacts.md
  evidence.md
  handoffs/
    delivery-to-ai/HANDOFF.md
  work/payment-api/
    WORK.md
    events.md
    interactions.md
    artifacts.md
    evidence.md
    approvals.md
```

The filesystem represents current state. Git provides history, branches, review, synchronization,
and handoffs across IDEs, CLIs, CI/CD systems, and cloud agents.

## Development

```bash
uv run ruff format --check .
uv run ruff check .
uv run pytest
uv run python scripts/check_docs.py
uv build
uv run python samples/basic-swarm/run.py
uv run python samples/llm-environments/run.py
uv run python samples/custom-lifecycle/run.py
uv run python samples/tool-integration/run.py
uv run python samples/handoffs/run.py
uv run python samples/recursive-swarms/run.py
uv run python samples/delegated-work/run.py
```

The [basic swarm sample](samples/basic-swarm/README.md) creates a temporary repository, installs Agora
for Codex, registers a human, an AI agent, and a nested swarm, creates a branch, demonstrates a failed
gate, and completes the work with evidence. The
[LLM environments sample](samples/llm-environments/README.md) materializes Codex, Claude, and generic
configurations without invoking a model. The
[custom lifecycle sample](samples/custom-lifecycle/README.md) installs and selects a Method Pack that
does not derive from a bundled methodology. The
[tool integration sample](samples/tool-integration/README.md) invokes Git through a governed Tool
Pack and persists its output. The [handoff sample](samples/handoffs/README.md) transfers one live
Developer role from a human to an AI agent and then a swarm. The
[recursive swarm sample](samples/recursive-swarms/README.md) links a child team and enforces nesting
depth. The [delegated work sample](samples/delegated-work/README.md) creates accepted child work and
collects its terminal result into the parent.

## Documentation

- [Documentation index](docs/README.md)
- [Installation and customization](docs/guides/installation-and-customization.md)
- [Getting started](docs/getting-started.md)
- [LLM environments](docs/guides/llm-environments.md)
- [Scrum delivery with humans and AI](docs/guides/scrum-delivery.md)
- [Method Pack reference](docs/reference/method-packs.md)
- [Tool Pack reference](docs/reference/tool-packs.md)
- [Governed handoffs](docs/guides/handoffs.md)
- [Recursive swarms](docs/guides/recursive-swarms.md)
- [Delegated work](docs/guides/delegated-work.md)
- [Architecture](docs/architecture.md) and [domain model](docs/domain-model.md)
- [ADR 0001](docs/decisions/0001-initial-architecture.md)
- [Contributing](CONTRIBUTING.md)

## Current limitations

- Scrum and Kanban are starter Method Packs, not privileged core workflows or exhaustive methodology
  implementations.
- Method Packs are installed from local directories; a package registry is not implemented yet.
- The Tool Pack kernel and Git reference pack are implemented; vendor packs for Jira, CI/CD,
  Confluence, and cloud platforms are not bundled yet.
- Automatic child-work decomposition, delegation budgets, artifact copying, gate waivers,
  distributed locks, and remote concurrency remain future work. Explicit child work acceptance and
  reference-based result collection are implemented.
- Credentials belong to the environment or secret manager; Agora stores references only.
- Front matter deliberately accepts a JSON-compatible subset of YAML.

## License

Apache License 2.0. See [LICENSE](LICENSE).
