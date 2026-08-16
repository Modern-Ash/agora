# Agora

**Agents, Governance, Orchestration, Roles & Artifacts**

Agora is a local, Markdown-first, Git-native lifecycle customization framework. It lets teams define
how humans, AI agents, services, automations, and swarms collaborate from an objective through its
completion. Install it once, select an agent or LLM environment, and materialize the roles,
protocols, tools, Method Packs, artifacts, and gates that govern each project.

Agora is deliberately agnostic in three dimensions:

- **Language:** governed projects may use any programming language, runtime, architecture, or stack.
- **LLM:** providers and models are selected configuration, never dependencies of the core protocol.
- **Development process:** Spec-Driven, Scrum, and Kanban are included presets; any valid Method
  Pack can define the roles, states, transitions, policies, and evidence required by a team's own
  lifecycle.

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
  actors/*/keys/        Public actor key lifecycle histories

<project>/.agora/
  project.md            Effective project configuration
  PACKS.lock.md         Exact installed Method and Tool Pack composition
  pack-removals/        Auditable records for applied composition removals
  constitution.md       Local principles and restrictions
  PROTOCOL.md           Shared collaboration protocol
  coordination.md       Optional external writer lease policy
  STANDARDS.md          Enforced cross-actor engineering standards
  commands/*.md         Portable agent commands
  methods/              Built-in and custom lifecycle Method Packs
  environments/*.md     Project-defined Tool Run permission boundaries
  registries/           Project-local pack catalog snapshots
  actors/               Project actors and public key lifecycle histories
  tools/                Policy and installed Tool Packs
  artifacts/            Artifact catalog
  delegations/          Parent-to-child work contracts and collection state
  swarms/               Durable work state and evidence-backed usage ledgers
  actions/              Prepared and applied lifecycle mutation intents
  sessions/             Resolved runtimes and compiled execution context
  tool-runs/             Governed external invocations and results
  upgrades/              Applied migrations, manifests, and pre-change backups
```

Configuration precedence is:

```text
Agora defaults < ~/.agora < project .agora < swarm configuration
```

## Where the operational Markdown lives

The framework repository does not commit a generated `.agora/` workspace. It ships the operational
sources that `agora init`, `agora quickstart`, and pack installation materialize in each governed
project:

| Operational source | What it becomes |
| --- | --- |
| [`templates/commands/`](templates/commands/) | Portable agent commands under `.agora/commands/`, plus the selected Codex or Claude projection |
| [`templates/project/`](templates/project/) | Constitution, protocol, standards, catalogs, and project-level operational files under `.agora/` |
| [`templates/methods/`](templates/methods/) | Role, transition, gate, and policy contracts under `.agora/methods/` |
| [`templates/tools/`](templates/tools/) | Provider-neutral Tool Packs under `.agora/tools/` |
| [`templates/adapters/`](templates/adapters/) | Reviewed native CLI adapters installed under `.agora/tools/` |

Actors, swarms, work items, actions, sessions, artifacts, evidence, approvals, and Tool Runs are not
static templates: Agora creates their Markdown records as the team works. See
[documentation and artifact locations](docs/reference/artifact-locations.md) for the full
source-to-runtime map.

## Install from this repository

Agora requires Python 3.11 or newer. The recommended development and tool manager is
[uv](https://docs.astral.sh/uv/).

Install a published release:

```bash
uv tool install agora-framework
agora --help
```

Release tags publish the same verified wheel to GitHub Releases and PyPI through OIDC Trusted
Publishing. No PyPI token is stored in the repository.

```bash
uv sync --extra dev
uv tool install .
agora --help
```

Run the development checkout without a global installation:

```bash
uv run agora --help
```

## Quickstart

Scaffold a runnable project in one command: it initializes `.agora`, registers a human
actor and an AI actor, creates a swarm with the default method, and assigns every
required role between the two.

```bash
cd my-project
agora quickstart --objective "Ship the MVP"
```

For a non-empty repository, preflight it before creating any state, then bind quickstart to the
expected base branch:

```bash
cd existing-service
agora adopt --check --id payment-idempotency --base main
agora quickstart \
  --id payment-idempotency \
  --base main \
  --objective "Deliver payment idempotency"
```

The preflight is read-only. It rejects a dirty tree, detached or unexpected base branch, an existing
`agora/<id>` branch, partial Agora state, reserved actor identities, an unavailable configured
runtime, or Git ignore rules that would prevent `.agora` and the selected integration adapter from
being persisted. Quickstart creates the feature branch before writing and rolls back its branch,
generated files, actor state, and newly generated keys if any later step fails. Use `--allow-dirty`
only after reviewing the reported changes.

By default the created actors are unauthenticated: no keys and no signing. Add `--secure` to require
signed authentication for both actors. Quickstart then generates a local Ed25519 keypair per actor
for exploration, keeping private keys outside `.agora`. Production actors should manage their own
keys instead; see the
[actor authentication guide](docs/guides/actor-authentication.md).

```bash
agora quickstart --objective "Ship the MVP" --secure
agora quickstart --objective "Ship the MVP" --secure --key-dir ~/.my-team/dev-keys
```

Without `--key-dir`, the external key directory is
`~/.config/agora-quickstart-keys/<project-hash>/`. The command reports its exact path. See the
[quickstart guide](docs/guides/quickstart.md) for rerun, custom Method Pack, and security behavior.
The fully executable [existing codebase feature pilot](samples/existing-codebase-feature/README.md)
proves the preflight-to-completion path without an LLM or network account.

Inspect the next role-authorized action, run non-human actors until Agora reaches human authority,
then inspect the human inbox:

```bash
agora next
agora run --until-blocked --max-steps 10
agora inbox
```

Codex and Claude run through their installed non-interactive CLIs. A generic integration supplies an
explicit structured runner with `--runner`. The controller stops when no governed progress is
recorded, so a successful process cannot create an unbounded empty loop. See the
[operational agent loop guide](docs/guides/operational-loop.md).

## Configure and initialize

The commands above are what `quickstart` runs for you. Use them directly for full control
over integration, provider, actors, and roles:

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
tool policy. The core does not attach special behavior to bundled method names.

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

See [the custom lifecycle sample](samples/custom-lifecycle/README.md) for a pack unrelated to the
bundled methods.

Discover bundled and registered packs, or install a reviewed local or remote registry snapshot:

```bash
agora registry install --source ./team-registry --scope user
agora trust add --id team-release --registry team-catalog \
  --public-key ./team-release.pem --scope user
agora trust organization add --id example-org \
  --public-key ./example-org-root.pem --scope project
agora trust organization sync --id example-org \
  --source https://trust.example.com/agora/BUNDLE.md --scope project
agora trust organization sync --id example-org --scope project --apply
agora trust organization rotate --id example-org \
  --source ./ROOT-ROTATION.md --scope project --apply
agora trust transparency add --id rekor-2026 --log rekor-public \
  --public-key ./rekor-public.pem --scope project
agora registry verify-transparency --source ./PROOF.md --scope project --record
agora registry install --source https://catalog.example.com/INDEX.md \
  --version 1.0.0 --signature-threshold 2 --require-transparency --scope project
agora registry update --id team-catalog
agora registry update --id team-catalog --apply
agora registry audit --scope project --record
agora registry list
agora pack search --kind method --query release
agora pack install --kind method --id release-flow \
  --registry team-catalog --scope project
agora pack update --kind method --id release-flow
agora pack update --kind method --id release-flow --apply
agora pack audit --scope project --record
agora pack apply-audit --id audit-20260815t120000z --scope project
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
Aggregate pack audits can record update and local-modification notifications without changing the
installed composition.
An explicitly selected, unchanged audit can then apply its bound dependency plans as one
transaction and persist an application record.
Remote releases are checksum-pinned and may require a threshold of distinct Ed25519 signatures;
Agora persists their signer evidence and policy beside the installed snapshot. See the
[remote registry guide](docs/guides/remote-registries.md).
Trusted public keys, rotations, and revocations can be persisted at user or project scope. See the
[registry trust guide](docs/guides/registry-trust.md).
Transparency checkpoint keys use a separate scoped trust store, so they cannot authorize registry
releases.
Signed organization feeds synchronize those keys and revocations through preview-first,
sequence-bound updates with a durable local history.
Organization roots rotate through an explicitly applied declaration signed by both the outgoing and
incoming roots and bound to the current feed position.
Registry updates are preview-only unless `--apply` is passed, preserve provenance and history, and
never update installed packs implicitly. See the
[registry update guide](docs/guides/registry-updates.md).
Aggregate registry audits can persist authenticated Markdown notifications for an external
scheduler without applying any update.

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

Direct assignment bootstraps vacant roles. Once a governance actor is assigned, remaining roles can
be authorized through a durable Lifecycle Action:

```bash
agora swarm assign-prepare --id assign-payments-developer \
  --swarm payments --role developer --actor delivery-swarm --by user:owner
agora action authorization --action assign-payments-developer \
  --output /tmp/assign-payments-developer.json
agora action apply --action assign-payments-developer \
  --signature /tmp/assign-payments-developer.sig
```

Assignments never overwrite an occupied role; use a governed handoff for replacement.

An actor may bind its identity to an external Ed25519 key and require signed authorization before
applying supported lifecycle mutations or launching a Tool Run:

```bash
agora actor add --id authenticated-developer \
  --name "Authenticated Developer" --kind ai-agent \
  --capability implementation \
  --public-key developer-public.pem \
  --require-authentication
```

Agora stores only the public key and durable signature evidence. The private key remains in the
actor's keychain, hardware, workload identity, or secret manager. See the
[actor authentication guide](docs/guides/actor-authentication.md) for the prepare, sign, and launch
flow.

Authenticated work transitions use a two-phase lifecycle action:

```bash
agora work transition-prepare --id begin-payment-work \
  --swarm payments --work payment-retry --to implementing --by authenticated-developer
agora action authorization --action begin-payment-work --output /tmp/begin-payment-work.json
agora action apply --action begin-payment-work --signature /tmp/begin-payment-work.sig
```

The external signer signs the exact bytes in `/tmp/begin-payment-work.json`. See
[signed lifecycle actions](docs/guides/signed-lifecycle-actions.md) for signing commands,
precondition rules, replay protection, and audit behavior.

Authenticated actors use the same boundary to change their own runtime selection:

```bash
agora actor runtime-prepare --id update-authenticated-runtime \
  --actor authenticated-developer --swarm payments \
  --integration generic --provider internal-gateway --model reviewed-model
agora action authorization --action update-authenticated-runtime \
  --output /tmp/update-authenticated-runtime.json
agora action apply --action update-authenticated-runtime \
  --signature /tmp/update-authenticated-runtime.sig
```

Authorize planned rotation with the active key. A different authenticated governance actor handles
revocation and recovery without replacing historical evidence:

```bash
agora actor key rotate-prepare --id rotate-authenticated-developer \
  --actor authenticated-developer --swarm payments \
  --public-key developer-next-public.pem --reason "Scheduled rotation"
agora action authorization --action rotate-authenticated-developer \
  --output /tmp/rotate-authenticated-developer.json
agora action apply --action rotate-authenticated-developer \
  --signature /tmp/rotate-authenticated-developer.sig
agora actor key revoke-prepare --id revoke-authenticated-developer \
  --actor authenticated-developer --swarm payments --by security-governor \
  --reason "Credential exposure"
agora action authorization --action revoke-authenticated-developer \
  --output /tmp/revoke-authenticated-developer.json
agora action apply --action revoke-authenticated-developer \
  --signature /tmp/revoke-authenticated-developer.sig
agora actor key recover-prepare --id recover-authenticated-developer \
  --actor authenticated-developer --swarm payments --by security-governor \
  --public-key developer-recovery-public.pem --reason "Credential replacement"
agora actor key list --actor authenticated-developer
```

The governance authorizer must hold explicit Method Pack authority, be assigned with the target, and
use a different public-key fingerprint. Recovery follows the same `action authorization` and
`action apply` steps; the revoked key never authorizes its successor.

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
with `SESSION.md` and `CONTEXT.md`; launched sessions also persist bounded output in `RESULT.md`. Add
`--launch` to execute the detected Codex or Claude command, or provide `--runner "<command>"` for a
generic environment. Agora delegates to the external process and does not import an LLM SDK.
Session time and output boundaries are configurable with `--timeout-seconds` and
`--max-output-bytes`, persisted in Markdown, and bound by signed launch authorization.

## Governed developer tools

Tool Packs expose selected operations from repositories, issue trackers, CI/CD, documentation, cloud,
observability, or communication CLIs. An operation declares structured arguments, required inputs,
risk, a provider-neutral capability, and optional approval policy. Method Pack roles grant those
capabilities explicitly.

Agora uses a CLI-first integration policy: prefer the provider CLI already configured in the
developer environment, use a reviewed wrapper when normalization is necessary, and keep MCP as an
explicit alternative when it provides capabilities unavailable through the CLI. Discovery never
installs or selects a transport automatically:

```bash
agora tool adapter list --available
agora tool adapter list --check
agora tool adapter list --compatible
agora tool adapter install --id github-actions --scope project
agora tool adapter install --id github-issues --scope project
agora tool adapter install --id gitlab-ci --scope project
agora tool adapter install --id gitlab-issues --scope project
agora tool adapter install --id gitlab-merge-requests --scope project
agora tool adapter install --id jira --scope project
agora tool adapter install --id twg-confluence --scope project
agora tool adapter install --id terraform --scope project
agora tool adapter install --id aws-resource-inventory --scope project
agora tool adapter install --id gcp-asset-inventory --scope project
```

`--check` runs each available adapter's declared version command and reports the detected and
minimum versions. `--compatible` performs the same check and returns only runtimes that satisfy the
adapter contract. Version checks never authenticate or contact the provider.

Agora includes Git-backed `repository` plus provider-neutral `work-management`, `ci-cd`,
`knowledge-base`, `cloud-infrastructure`, and `observability` packs:

```bash
agora environment add --id staging --name "Staging" \
  --capability cloud.read --capability cloud.plan
agora environment add --id production --name "Production" \
  --capability observability.read

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

agora tool invoke --id plan-payment-capacity \
  --tool cloud-infrastructure --operation plan \
  --actor delivery-swarm --swarm payments \
  --environment staging \
  --input environment=staging \
  --input change=increase-payment-capacity --launch

agora tool invoke --id payment-health \
  --tool observability --operation service-health \
  --actor delivery-swarm --swarm payments \
  --environment production \
  --input service=payments --input environment=production --launch
```

The executable runs without a shell. Agora persists `RUN.md`, captures output and exit status in
`RESULT.md`, and stores no credentials. Omitting `--launch` creates a portable invocation for an IDE,
CI worker, or cloud executor. The commit operation validates Conventional Commits 1.0.0 before a run
record or Git commit is created.

Environment-aware operations additionally require a project policy, an assigned role that permits
the environment, and any configured work approvals or successful evidence. Agora records the stable
environment id separately from provider-specific Tool Pack inputs and rechecks it before launch. See
the [environment permissions guide](docs/guides/environment-permissions.md).

The `work-management` pack defines a stable `workctl` interface for Jira, Linear, or an internal
tracker while keeping `issue.read`, `issue.write`, and `issue.transition` authority in the active
Method Pack. The `github-issues` and `jira` adapters map that contract directly to `gh` and ACLI;
the partial `gitlab-issues` adapter maps exact search, view, comment, and close/reopen operations to
`glab` without claiming unsupported typed creation.
See the [work-management integration guide](docs/guides/work-management-integrations.md).

The `code-review` pack separates review reads, review writing, review decisions, and merge authority.
The `github-pull-requests` adapter maps the full contract to the installed `gh` CLI. The partial
`gitlab-merge-requests` adapter maps exact view, create, comment, and head-pipeline check operations
to `glab` without weakening unsupported decisions or merge strategies. No bundled role receives
`review.merge`; projects must opt in explicitly. See the
[code-review integration guide](docs/guides/code-review-integrations.md).

The `ci-cd` pack defines a stable `cictl` interface for GitHub Actions, GitLab CI/CD, Jenkins, or an
internal platform. Routine pipeline access is separate from cancellation and deployment authority.
The independently installable `github-actions` adapter maps the complete contract to the
developer's existing `gh` CLI. The partial `gitlab-ci` adapter maps bounded pipeline listing,
inspection, and cancellation to `glab` without claiming trigger or deployment translations that
lose required neutral inputs. See the
[CLI-first adapter guide](docs/guides/cli-first-adapters.md) and
[CI/CD integration guide](docs/guides/ci-cd-integrations.md).

The `knowledge-base` pack defines a stable `docsctl` interface for Confluence, Notion, and internal
documentation. The independently installable `twg-confluence` adapter maps the exact Confluence
page view, draft create/update, publish, and archive subset to Atlassian Teamwork Graph CLI, with
optimistic concurrency tokens required for updates. Draft access remains separate from publication
and destructive archival. See the
[knowledge-base integration guide](docs/guides/knowledge-base-integrations.md).

The `cloud-infrastructure` pack defines `cloudctl` for AWS, Azure, Google Cloud, infrastructure as
code, or internal platforms. Inspection and planning remain distinct from apply and destruction.
The independently installable `terraform` adapter uses the developer's existing Terraform CLI and
applies only saved plans. Partial AWS and Google Cloud adapters expose bounded inventory reads
without plan, apply, or destruction operations. See the
[cloud integration guide](docs/guides/cloud-integrations.md).

The `observability` pack defines `observectl` for monitoring and incident systems. Reading signals
and declaring incidents remain separate from resolution authority. See the
[observability integration guide](docs/guides/observability-integrations.md).

## Governed work

```bash
agora work create --swarm payments --id payment-api --title "Implement payment API" \
  --by owner --criterion api-works:"The API satisfies its contract" \
  --required-artifact source-code --required-artifact test-report

agora work decompose --swarm payments --work payment-api \
  --child payment-validation --title "Validate payment requests" \
  --by owner --criterion covered:"Validation paths have tests"

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

Local decomposition links independently governed child work inside the same swarm. The parent
cannot complete or be cancelled while a child remains open. See the
[work decomposition guide](docs/guides/work-decomposition.md). Cross-swarm child work continues to
use the separate delegation protocol.

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
Projects may layer a reviewed external lease CLI over the mandatory local lock to coordinate
separate hosts while keeping Markdown and Git authoritative. See the
[concurrent writers guide](docs/guides/concurrent-writers.md).

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
audit across schemas, portable commands, generated agent adapters, Method and Tool Packs,
environment policies, actors, role assignments, work, WIP, handoffs, delegations, sessions, tool
runs, events, and recursive swarm constraints. Validation emits all findings and exits with status
`1` when errors are present. See the
[operations and validation guide](docs/guides/operations-and-validation.md).

## Development

Run the complete Python verification entry point:

```bash
uv run python scripts/verify_all.py
```

It checks Python, Markdown links, generated adapter semantics, all samples, tests, and both package
distributions. GitHub Actions runs the test suite on Python 3.11 through 3.13 and executes this same
complete verifier on Python 3.13. Version-matched `vMAJOR.MINOR.PATCH` tags publish checksum-protected
wheel and source artifacts as a GitHub release. See the
[complete verification guide](docs/guides/verification.md). The individual commands are:

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
uv run python samples/gate-waivers/run.py
uv run python samples/approval-delegation/run.py
uv run python samples/gitlab-ci-cli/run.py
uv run python samples/gitlab-issues-cli/run.py
uv run python samples/gitlab-merge-requests-cli/run.py
uv run python samples/distributed-coordination/run.py
uv run python samples/environment-permissions/run.py
uv run python samples/twg-confluence-cli/run.py
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
[operational loop sample](samples/operational-loop/README.md) launches a real external process,
persists work while its session is running, prepares a Pull Request command, and stops at a human
gate. The
[interruption sample](samples/interruptions/README.md) exercises work and delegation blocking,
resumption, rejection, and cancellation.
The [project upgrade sample](samples/project-upgrade/README.md) applies a backed-up protocol
migration, while the [concurrent writers sample](samples/concurrent-writes/README.md) demonstrates
local process contention and recovery. The
[pack dependency sample](samples/pack-dependencies/README.md) installs a Method Pack and resolves its
compatible Tool Pack before copying either catalog selection. The
[remote registry sample](samples/remote-registry/README.md) signs, verifies, installs, and validates a
versioned registry snapshot without persisting a private key.
The [GitLab Issues sample](samples/gitlab-issues-cli/README.md) prepares native issue reads and
transitions while rejecting deletion and unsupported typed creation.
The [GitLab CI/CD sample](samples/gitlab-ci-cli/README.md) prepares bounded pipeline reads while
rejecting unauthorized cancellation and unsupported trigger translation.
The [GitLab Merge Requests sample](samples/gitlab-merge-requests-cli/README.md) prepares native
review creation and head-pipeline inspection while rejecting unsupported merge translation.
The [environment permissions sample](samples/environment-permissions/README.md) gates a production
Tool Run on role scope, Product Owner approval, and successful work evidence.
The [TWG Confluence sample](samples/twg-confluence-cli/README.md) prepares native page commands,
requires an optimistic-concurrency token for updates, and rejects unsupported search translation.
The [distributed coordination sample](samples/distributed-coordination/README.md) wraps a project
mutation in a structured external lease while retaining the local operating-system lock.

## Documentation

- [Visual adoption guide](docs/adoption.md): move from installation to a validated first workflow
  with decision diagrams, minimal commands, and staged team adoption.
- [Documentation index](docs/README.md): guides grouped by onboarding, governance, agentic work,
  integrations, registries, concepts, and reference.
- [Documentation and artifact locations](docs/reference/artifact-locations.md): distinguish product
  documentation, plugin output, protocol sources, generated agent adapters, durable `.agora` state,
  and externally owned work products.
- [Installation and customization](docs/guides/installation-and-customization.md) and
  [getting started](docs/getting-started.md).
- End-to-end delivery guides for [Spec-Driven](docs/guides/spec-driven-delivery.md),
  [Scrum](docs/guides/scrum-delivery.md), and [Kanban](docs/guides/kanban-delivery.md).
- [Operational agent loop](docs/guides/operational-loop.md) and
  [code-review integrations](docs/guides/code-review-integrations.md).
- [Architecture](docs/architecture.md), [domain model](docs/domain-model.md),
  [Method Pack reference](docs/reference/method-packs.md), and
  [Tool Pack reference](docs/reference/tool-packs.md).
- [Executable samples](samples/): runnable examples with companion documentation.
- [Contributing](CONTRIBUTING.md)

## Current limitations

- Spec-Driven, Scrum, and Kanban are starter Method Packs, not privileged core workflows or
  exhaustive methodology implementations.
- Method and Tool Packs can be discovered through bundled, user, project, and verified remote
  registry snapshots. Local and project trust stores, rotation, and revocation are implemented;
  explicit update checks, transactional application, and dependency-aware installation are
  implemented. Installed pack provenance and explicit dependency-aware updates are implemented.
  Signed organization trust synchronization and a locally verified feed history are implemented.
  Dual-signed organization root rotation and registry release signature thresholds are implemented.
  Explicit third-party transparency inclusion-proof verification and durable recording are
  implemented, and a recorded proof can be made a forward-only installation and update policy.
  Automatic proof discovery and background pack updates are not implemented. Aggregate update
  notifications and explicit audited batch application are available for external schedulers.
- The Tool Pack kernel plus Git repository, provider-neutral code-review, work-management, CI/CD,
  knowledge-base, cloud-infrastructure, and observability packs are implemented. Bundled vendor
  distributions currently include GitHub Actions, GitHub Issues, GitHub Pull Requests, Jira, and
  Terraform CLI adapters, partial GitLab CI/CD, Issues, Merge Requests, and Atlassian TWG Confluence
  adapters, plus partial AWS and Google Cloud inventory adapters.
- Governed same-swarm work decomposition and provider-neutral delegation budgets are implemented;
  the selected human, agent, or swarm remains responsible for proposing useful child contracts and
  external runtimes remain responsible for measuring usage. Agora provides an append-only,
  evidence-backed usage ledger with cumulative budget enforcement. Opt-in typed child artifact
  promotion is implemented as a reference to the authoritative child record; Agora deliberately
  does not copy opaque external bytes. Granular, evidence-backed Gate Waivers and single-use, work-scoped
  Approval Delegation are implemented. Distributed coordination is available through an optional
  reviewed lease CLI; remote scheduling remains external. Local cross-process writer locks,
  explicit child work acceptance, interruption,
  cancellation, and reference-based result collection are implemented.
- Optional Ed25519 actor authentication protects key rotation, independently authorized revocation
  and recovery, actor runtime updates, vacant-role assignment, work creation and decomposition,
  criteria, artifacts, evidence, transitions, interruptions, direct and delegated approvals, Gate
  Waivers, handoffs, the complete work-delegation lifecycle, Tool Run launch, and agent-session
  preparation and launch while leaving private keys external. Public-key rotation and revocation
  histories are implemented. Tool Packs and agent sessions declare portable direct-process timeouts
  and captured-output limits. Filesystem/network/syscall isolation, resource quotas, and detached
  process containment remain responsibilities of reviewed external runners.
- Credentials belong to the environment or secret manager; Agora stores references only.
- Front matter deliberately accepts a JSON-compatible subset of YAML.

## License

Apache License 2.0. See [LICENSE](LICENSE).
