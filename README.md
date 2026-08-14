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
  PACKS.lock.md         Exact installed Method and Tool Pack composition
  pack-removals/        Auditable records for applied composition removals
  constitution.md       Local principles and restrictions
  PROTOCOL.md           Shared collaboration protocol
  STANDARDS.md          Enforced cross-actor engineering standards
  commands/*.md         Portable agent commands
  methods/              Built-in and custom lifecycle Method Packs
  registries/           Project-local pack catalog snapshots
  actors/               Project-specific actors
  tools/                Policy and installed Tool Packs
  artifacts/            Artifact catalog
  delegations/          Parent-to-child work contracts and collection state
  swarms/               Durable work state
  sessions/             Resolved runtimes and compiled execution context
  tool-runs/             Governed external invocations and results
  upgrades/              Applied migrations, manifests, and pre-change backups
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

Existing projects are never rewritten merely because the CLI was updated. Preview and then apply a
supported protocol migration explicitly:

```bash
agora upgrade
agora upgrade --apply
agora validate
```

Each applied migration is recorded under `.agora/upgrades` with backups of every updated file. See
the [project upgrade guide](docs/guides/project-upgrades.md) for compatibility and recovery rules.

Pack lifecycle changes are also preview-first. Removing a pack checks reverse dependencies and
durable project references before deleting files, updates `PACKS.lock.md`, and writes an auditable
record under `.agora/pack-removals`. See the [pack removal guide](docs/guides/pack-removal.md).

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

Discover bundled and registered packs, or install a reviewed local or remote registry snapshot:

```bash
agora registry install --source ./team-registry --scope user
agora trust add --id team-release --registry team-catalog \
  --public-key ./team-release.pem --scope user
agora registry install --source https://catalog.example.com/INDEX.md \
  --version 1.0.0 --require-signature --scope user
agora registry update --id team-catalog
agora registry update --id team-catalog --apply
agora registry list
agora pack search --kind method --query release
agora pack install --kind method --id release-flow \
  --registry team-catalog --scope project
agora pack update --kind method --id release-flow
agora pack update --kind method --id release-flow --apply
```

Project registries override user registries, which override the bundled catalog when the same pack id
appears more than once. See the [pack registry guide](docs/guides/pack-registries.md).
Pack manifests declare versions and optional Method or Tool dependencies. Catalog installation
resolves compatible dependencies before copying and rejects broken or cyclic compositions. See the
[pack dependency guide](docs/guides/pack-dependencies.md).
Each catalog-installed pack persists its registry and checksum in `SOURCE.md`. Explicit
`agora pack update` previews dependency-aware changes and applies them only with `--apply`; see the
[pack update guide](docs/guides/pack-updates.md).
`PACKS.lock.md` inventories the exact installed composition, while per-pack `UPDATE.md` files retain
each applied transition; see the [pack lock guide](docs/guides/pack-locks.md).
Remote releases are checksum-pinned and may require an Ed25519 signature; Agora persists their
provenance beside the installed snapshot. See the
[remote registry guide](docs/guides/remote-registries.md).
Trusted public keys, rotations, and revocations can be persisted at user or project scope. See the
[registry trust guide](docs/guides/registry-trust.md).
Registry updates are preview-only unless `--apply` is passed, preserve provenance and history, and
never update installed packs implicitly. See the
[registry update guide](docs/guides/registry-updates.md).

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

Delegations may also be blocked and resumed by parent governance, rejected by the child, or
cancelled by the parent. Each operation requires an attributed reason and preserves a sequenced
`STATUS.md` history.

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

Agora includes Git-backed `repository` plus provider-neutral `work-management`, `ci-cd`, and
`knowledge-base` packs:

```bash
agora tool show --tool repository
agora tool invoke --id payment-status \
  --tool repository --operation status \
  --actor delivery-swarm --swarm payments --launch

# After staging the intended files:
agora tool invoke --id payment-commit \
  --tool repository --operation commit \
  --actor delivery-swarm --swarm payments \
  --input message="feat(payments): add governed payment API" --launch

agora tool invoke --id inspect-payment-ticket \
  --tool work-management --operation view \
  --actor delivery-swarm --swarm payments \
  --input issue=PAY-42 --launch

agora tool invoke --id verify-payments \
  --tool ci-cd --operation trigger \
  --actor delivery-swarm --swarm payments \
  --input pipeline=verify --input ref=main \
  --input parameters=suite=payments --launch

agora tool invoke --id inspect-payment-guide \
  --tool knowledge-base --operation view \
  --actor delivery-swarm --swarm payments \
  --input document=DOC-42 --launch
```

The executable runs without a shell. Agora persists `RUN.md`, captures output and exit status in
`RESULT.md`, and stores no credentials. Omitting `--launch` creates a portable invocation for an IDE,
CI worker, or cloud executor. The commit operation validates Conventional Commits 1.0.0 before a run
record or Git commit is created.

The `work-management` pack defines a stable `workctl` interface for Jira, Linear, or an internal
tracker while keeping `issue.read`, `issue.write`, and `issue.transition` authority in the active
Method Pack. See the
[work-management integration guide](docs/guides/work-management-integrations.md).

The `ci-cd` pack defines a stable `cictl` interface for GitHub Actions, GitLab CI/CD, Jenkins, or an
internal platform. Routine pipeline access is separate from cancellation and deployment authority.
See the [CI/CD integration guide](docs/guides/ci-cd-integrations.md).

The `knowledge-base` pack defines a stable `docsctl` interface for Confluence, Notion, and internal
documentation. Draft access remains separate from publication and destructive archival. See the
[knowledge-base integration guide](docs/guides/knowledge-base-integrations.md).

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

Method state and operational status are independent. A blocker preserves the current lifecycle
state while suspending mutations; cancellation closes the item without claiming method completion:

```bash
agora work block --swarm payments --work payment-api --by delivery \
  --reason "Waiting for an upstream contract"
agora work status-changes --swarm payments --work payment-api
agora work resume --swarm payments --work payment-api --by facilitator \
  --reason "The contract is available"
agora work cancel --swarm payments --work payment-api --by owner \
  --reason "The objective no longer requires this work"
```

See [interruptions and cancellation](docs/guides/interruptions-and-cancellation.md) for state,
authority, delegation, and child-ownership rules.

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
  status-changes/<change-id>/STATUS.md

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
    status-changes/<change-id>/STATUS.md
    events.md
    interactions.md
    artifacts.md
    evidence.md
    approvals.md
```

The filesystem represents current state. Git provides history, branches, review, synchronization,
and handoffs across IDEs, CLIs, CI/CD systems, and cloud agents.

## Concurrent writers

Mutating operations take an operating-system lock for the complete project or user-home transaction.
This serializes local CLIs, IDE integrations, agent processes, and Python API clients without adding
runtime files to the repository. Contention fails immediately unless `AGORA_LOCK_TIMEOUT` configures
a bounded wait:

```bash
agora lock status
AGORA_LOCK_TIMEOUT=10 agora work transition \
  --swarm payments --work payment-api --to reviewing --by delivery-swarm
```

Locks are reentrant for nested Agora operations and release on success, exceptions, or process exit.
They coordinate processes that share one host and lock directory; distributed leases across separate
hosts remain future work. See the [concurrent writers guide](docs/guides/concurrent-writers.md).

## Operational queries and validation

Agora reads the Markdown source of truth into deterministic JSON views for humans, agents, IDEs,
and CI:

```bash
agora status
agora actor list --scope project
agora swarm list --status running
agora work list --swarm payments --state reviewing
agora work list --swarm payments --operational-status blocked
agora work status-changes --swarm payments --work payment-api
agora delegation list --status accepted
agora delegation status-changes --delegation specialist-task
agora session list --status prepared
agora tool runs --status failed
agora event list --swarm payments --work payment-api --limit 20
agora validate
```

`doctor` checks environment prerequisites. `validate` performs a complete, non-mutating integrity
audit across schemas, portable commands, generated agent adapters, Method and Tool Packs, actors,
role assignments, work, WIP, handoffs, delegations, sessions, tool runs, events, and recursive swarm
constraints. Validation emits all findings and exits with status `1` when errors are present. See the
[operations and validation guide](docs/guides/operations-and-validation.md).

## Development

Run the complete Python verification entry point:

```bash
uv run python scripts/verify_all.py
```

It checks Python, Markdown links, generated adapter semantics, all samples, tests, and both package
distributions. See the [complete verification guide](docs/guides/verification.md). The individual
commands are:

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
uv run python samples/operational-query/run.py
uv run python samples/interruptions/run.py
uv run python samples/project-upgrade/run.py
uv run python samples/concurrent-writes/run.py
uv run python samples/pack-registry/run.py
uv run python samples/pack-dependencies/run.py
uv run python samples/remote-registry/run.py
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
collects its terminal result into the parent. The
[operational query sample](samples/operational-query/README.md) summarizes and validates a complete
workspace directly from its Markdown records. The
[interruption sample](samples/interruptions/README.md) exercises work and delegation blocking,
resumption, rejection, and cancellation.
The [project upgrade sample](samples/project-upgrade/README.md) applies a backed-up protocol
migration, while the [concurrent writers sample](samples/concurrent-writes/README.md) demonstrates
local process contention and recovery. The
[pack dependency sample](samples/pack-dependencies/README.md) installs a Method Pack and resolves its
compatible Tool Pack before copying either catalog selection. The
[remote registry sample](samples/remote-registry/README.md) signs, verifies, installs, and validates a
versioned registry snapshot without persisting a private key.

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
- [Operations and validation](docs/guides/operations-and-validation.md)
- [Complete verification](docs/guides/verification.md)
- [Interruptions and cancellation](docs/guides/interruptions-and-cancellation.md)
- [Concurrent writers](docs/guides/concurrent-writers.md)
- [Conventional Commits](docs/guides/conventional-commits.md)
- [Pack registries](docs/guides/pack-registries.md)
- [Pack dependencies](docs/guides/pack-dependencies.md)
- [Pack updates](docs/guides/pack-updates.md)
- [Pack composition locks](docs/guides/pack-locks.md)
- [Remote registry releases](docs/guides/remote-registries.md)
- [Registry trust stores](docs/guides/registry-trust.md)
- [Registry updates](docs/guides/registry-updates.md)
- [Architecture](docs/architecture.md) and [domain model](docs/domain-model.md)
- [ADR 0001](docs/decisions/0001-initial-architecture.md)
- [Contributing](CONTRIBUTING.md)

## Current limitations

- Scrum and Kanban are starter Method Packs, not privileged core workflows or exhaustive methodology
  implementations.
- Method and Tool Packs can be discovered through bundled, user, project, and verified remote
  registry snapshots. Local and project trust stores, rotation, and revocation are implemented;
  explicit update checks, transactional application, and dependency-aware installation are
  implemented. Installed pack provenance and explicit dependency-aware updates are implemented.
  Organization trust synchronization, transparency, automatic background pack updates, and
  notifications are not.
- The Tool Pack kernel plus Git repository, provider-neutral work-management, CI/CD, and
  knowledge-base packs are implemented; vendor distributions and cloud packs remain future work.
- Automatic child-work decomposition, delegation budgets, artifact copying, gate waivers,
  distributed leases, and remote concurrency remain future work. Local cross-process writer locks,
  explicit child work acceptance, interruption, cancellation, and reference-based result collection
  are implemented.
- Credentials belong to the environment or secret manager; Agora stores references only.
- Front matter deliberately accepts a JSON-compatible subset of YAML.

## License

Apache License 2.0. See [LICENSE](LICENSE).
