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
  config.md             Integration, provider, model, and method defaults
  actors/*.md           Reusable user actors

<project>/.agora/
  project.md            Effective project configuration
  constitution.md       Local principles and restrictions
  PROTOCOL.md           Shared collaboration protocol
  commands/*.md         Portable agent commands
  methods/              Built-in and custom lifecycle Method Packs
  actors/               Project-specific actors
  tools/                Tool and integration policy
  artifacts/            Artifact catalog
  swarms/               Durable work state
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
  --default-method scrum

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
actor kinds and actions, ordered work states, the terminal state, protocol, tool policy, and gates.
The core does not attach special behavior to the names Scrum or Kanban.

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
  --capability facilitation --capability governance

agora actor add --id delivery-swarm --name "Delivery Swarm" --kind swarm \
  --capability implementation

agora swarm create --id payments --objective "Deliver governed payment changes"
agora swarm assign --swarm payments --role product-owner --actor user:owner
agora swarm assign --swarm payments --role scrum-master --actor facilitator
agora swarm assign --swarm payments --role developer --actor delivery-swarm
```

In a Git repository, `swarm create` creates `agora/<swarm-id>` by default. Use `--no-branch` to retain
the current branch. The global `--project <path>` option lets IDEs, runners, and cloud environments
operate on an initialized project without changing their working directory.

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
```

States come from the installed Method Pack and cannot be skipped. A terminal transition requires:

1. Every acceptance criterion is satisfied.
2. Every required artifact kind is registered.
3. At least one successful evidence record exists.
4. The acting participant holds a role that permits the action.

## Persistence

Each swarm contains its manifest, assignments, interactions, events, work, artifacts, and evidence:

```text
.agora/swarms/payments/
  SWARM.md
  events.md
  interactions.md
  artifacts.md
  evidence.md
  work/payment-api/
    WORK.md
    events.md
    interactions.md
    artifacts.md
    evidence.md
```

The filesystem represents current state. Git provides history, branches, review, synchronization,
and handoffs across IDEs, CLIs, CI/CD systems, and cloud agents.

## Development

```bash
uv run ruff format --check .
uv run ruff check .
uv run pytest
uv build
uv run python samples/basic-swarm/run.py
uv run python samples/custom-lifecycle/run.py
```

The [basic swarm sample](samples/basic-swarm/README.md) creates a temporary repository, installs Agora
for Codex, registers a human, an AI agent, and a nested swarm, creates a branch, demonstrates a failed
gate, and completes the work with evidence. The
[custom lifecycle sample](samples/custom-lifecycle/README.md) installs and selects a Method Pack that
does not derive from a bundled methodology.

See [architecture](docs/architecture.md), [domain model](docs/domain-model.md),
[ADR 0001](docs/decisions/0001-initial-architecture.md), and [CONTRIBUTING.md](CONTRIBUTING.md).

## Current limitations

- Scrum and Kanban are starter Method Packs, not privileged core workflows or exhaustive methodology
  implementations.
- Method Packs are installed from local directories; a package registry is not implemented yet.
- External adapters for Jira, CI/CD, Confluence, repositories, and cloud are not implemented yet.
- Executable handoffs, WIP limits, distributed locks, and remote concurrency remain future work.
- Credentials belong to the environment or secret manager; Agora stores references only.
- Front matter deliberately accepts a JSON-compatible subset of YAML.

## License

Apache License 2.0. See [LICENSE](LICENSE).
