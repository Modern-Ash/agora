# Installation and customization

This guide installs the Agora CLI and then customizes its user, project, Method Pack, actor, and
agent-environment scopes. Agora requires Python 3.11 or newer and does not require Node.js, an LLM
SDK, a database, or a running server.

## Installation choices

Agora is currently an experimental source distribution. This guide uses the repository checkout or
a locally built artifact and does not assume availability from a package registry.

### Install as a user tool with uv

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), clone Agora, and install the
CLI in an isolated tool environment:

```bash
git clone https://github.com/fabianaguero/agora.git
cd agora
uv tool install .
agora --help
```

This is the recommended mode for daily use. The `agora` executable remains available outside the
source checkout, while its Python dependencies stay isolated from application projects.

Use an editable tool installation while developing Agora itself:

```bash
uv tool install --editable --force .
agora --help
```

Source changes are then reflected without reinstalling the package. Template changes are also read
from the checkout by the editable installation.

### Run directly from a checkout

Install development dependencies and run the CLI through uv:

```bash
git clone https://github.com/fabianaguero/agora.git
cd agora
uv sync --extra dev
uv run agora --help
```

Prefix every example in the documentation with `uv run` when using this mode:

```bash
uv run agora configure --integration generic --default-method scrum
```

This mode is useful for contributing, running tests, and evaluating uncommitted changes.

### Install a locally built wheel

Build the source distribution and wheel, then install the wheel as a tool:

```bash
uv sync --extra dev
uv build
uv tool install --force dist/agora_framework-0.2.0-py3-none-any.whl
agora --help
```

The wheel contains the Python CLI and bundled Markdown templates. A wheel is useful for testing the
same immutable artifact in multiple environments.

### Install in a Python virtual environment

Use a conventional virtual environment when `uv tool` is not appropriate:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
agora --help
```

On Windows PowerShell, activate with:

```powershell
.venv\Scripts\Activate.ps1
```

The virtual environment belongs to the Agora installation, not to projects governed by Agora. A
governed project may use any language or runtime.

## Verify the installation

```bash
agora --help
agora configure --help
agora method install --help
```

The CLI should list `configure`, `init`, `upgrade`, `doctor`, `status`, `validate`, `lock`, `registry`,
`pack`, `trust`, `start`, `method`, `tool`, `delegation`, `actor`, `swarm`, `work`, `session`, `event`,
`artifact`, `evidence`, and `approval`. These commands operate on files; no background process should
be running.

Registry installation accepts local directories or versioned remote `INDEX.md` sources. Remote
archives always require SHA-256 verification and can require a trusted Ed25519 signature. See
[Remote registry releases](remote-registries.md).
Trusted registry public keys can be persisted, rotated, and revoked as described in
[Registry trust stores](registry-trust.md).
Installed remote registries can be checked and updated explicitly as described in
[Registry updates](registry-updates.md).

## Configuration scopes

Agora resolves configuration from broad defaults toward the active work context:

```text
bundled defaults < user home < project .agora < swarm selection
```

| Scope | Default location | Shared in project Git | Typical contents |
| --- | --- | --- | --- |
| Distribution | Installed Python package | No | Base templates, Scrum, Kanban, commands |
| User | `~/.agora` | No | Defaults, reusable actors, Method Packs, and Tool Packs |
| Project | `<project>/.agora` | Yes | Policies, packs, actors, sessions, tool runs, work state |
| Swarm | `.agora/swarms/<id>` | Yes | Objective, method, assignments, work, evidence, approvals |

Use user scope for personal defaults and reusable identities. Use project scope for rules and state
that every participant must review and share.

## Customize the Agora home

Agora uses `~/.agora` by default. Set `AGORA_HOME` before running commands to use another location:

```bash
export AGORA_HOME="$HOME/.config/agora"
agora configure \
  --integration codex \
  --provider openai \
  --model configured-by-codex \
  --default-method scrum
```

This is useful for isolated experiments, CI jobs, separate work identities, and test environments.
Persist the environment variable in the shell or runner configuration when the alternate location
should be stable.

Agora stores local writer lock metadata outside the project. Override its runtime directory or
configure a bounded contention wait when needed:

```bash
export AGORA_LOCK_HOME="$HOME/.cache/agora/locks"
export AGORA_LOCK_TIMEOUT=10
```

Lock files are not project state and must not be committed. See
[Concurrent writers](concurrent-writers.md) for ownership inspection and scope boundaries.

## Customize user defaults

Create the initial user configuration:

```bash
agora configure \
  --integration claude \
  --provider anthropic \
  --model configured-by-claude \
  --default-method kanban \
  --max-delegation-depth 3
```

This writes `~/.agora/config.md`. Agora refuses to overwrite it accidentally. Review the existing
file and use `--force` when replacing the complete user configuration is intentional:

```bash
agora configure \
  --integration codex \
  --provider openai \
  --model configured-by-codex \
  --default-method scrum \
  --force
```

Provider and model are opaque labels. They document the selected execution environment but do not
load a provider SDK or call an API. See [LLM environments](llm-environments.md) for complete examples.

`max-delegation-depth` limits linked child-swarm chains across projects initialized from this user
configuration. Use `0` to prohibit local recursive delegation.

## Customize project initialization

Initialize a project with user defaults:

```bash
cd my-project
agora init
agora doctor
agora validate
```

Validation includes the portable command Markdown and every generated Codex, Claude, or generic
adapter. The [complete verification guide](verification.md) covers repository-wide tests and samples.

Override selected defaults for one new project:

```bash
agora init \
  --integration generic \
  --provider internal-runtime \
  --model team-approved-model \
  --default-method scrum \
  --max-delegation-depth 2
```

Initialization materializes `.agora` plus the selected agent adapter. After initialization, review
and version the files that define the shared contract:

```text
.agora/project.md
.agora/constitution.md
.agora/PROTOCOL.md
.agora/STANDARDS.md
.agora/tools/TOOLS.md
.agora/tools/repository/TOOL.md
.agora/methods/
.agora/registries/
.agora/commands/
.agora/sessions/
```

Edit the constitution for engineering, security, compliance, and approval rules. Edit the protocol
for handoffs, escalation, communication, and durable-record expectations. `STANDARDS.md` enables
Conventional Commits 1.0.0 for repository history. Edit tool policy to name allowed external systems
and restricted actions.

These Markdown changes are immediately visible to humans and agents. Free-form policy prose remains
instructional. Method transition contracts, gates, role capabilities, and Tool Pack operations are
validated and enforced by the Python kernel.

## Customize the development lifecycle

Install an existing Method Pack for reuse by the user:

```bash
agora method install --source ./release-flow --scope user
agora configure --default-method release-flow --force
```

New projects inherit packs from `~/.agora/methods`. To keep a pack local to one initialized project:

```bash
agora method install --source ./release-flow --scope project
agora swarm create \
  --id release \
  --objective "Deliver the governed release" \
  --method release-flow
```

A Method Pack customizes required roles, compatible actor kinds, capabilities, allowed actions,
transition graphs, WIP limits, gates, approvals, collaboration protocol, and tool guidance. Read the
[Method Pack reference](../reference/method-packs.md) before authoring one.

Operational interruption authority is also role-defined. Grant `work.block` and `work.resume` to
delivery or flow roles, `work.cancel` to the appropriate owner, and the corresponding delegation
actions according to parent and child authority. See
[Interruptions and cancellation](interruptions-and-cancellation.md) for the full action matrix.

## Customize developer tool integrations

Tool Packs wrap selected operations from an external CLI without adding its SDK to Agora. Install a
pack for all future projects:

```bash
agora tool install --source ./team-issue-tracker --scope user
```

Or install it only in the current project:

```bash
agora tool install --source ./team-issue-tracker --scope project
agora tool show --tool team-issue-tracker
```

Each operation declares one provider-neutral capability such as `issue.read`, `issue.write`,
`ci.read`, `ci.run`, `docs.write`, or `cloud.deploy`. Grant the exact capability in the relevant
Method Pack role through `allowed-tool-capabilities`. Then prepare or launch it as an assigned actor:

```bash
agora tool invoke --id inspect-ticket \
  --tool team-issue-tracker --operation view-issue \
  --actor delivery-agent --swarm release --work release-candidate \
  --input issue=TEAM-42
```

Add `--launch` only when the selected environment should execute the external CLI. Agora captures the
result but leaves authentication in that CLI's profile, environment, workload identity, or secret
manager. Never use durable Tool Pack inputs for credentials. See the
[Tool Pack reference](../reference/tool-packs.md) for the complete contract.

## Customize actors and responsibility

Register a reusable human actor:

```bash
agora actor add --scope user \
  --id product-owner \
  --name "Product Owner" \
  --kind human \
  --capability backlog-management \
  --capability acceptance
```

Register a project-specific AI actor:

```bash
agora actor add --scope project \
  --id delivery-agent \
  --name "Delivery Agent" \
  --kind ai-agent \
  --capability implementation \
  --integration codex \
  --provider openai \
  --model configured-by-codex \
  --description "Runs in the project-selected model environment under repository policy."
```

Runtime fields are optional and inherit project defaults. They can change without changing the
actor's accountable identity or role assignments:

```bash
agora actor runtime --actor delivery-agent \
  --integration generic --provider internal-runtime --model reviewed-coder

agora actor runtime --actor delivery-agent --clear
```

Responsibility can move from a human to an AI agent or swarm by registering the receiver and using a
governed handoff:

```bash
agora swarm handoff --id delivery-transfer \
  --swarm release --role developer \
  --from human-developer --to delivery-agent --by human-developer \
  --reason "Continue the approved plan in the configured AI runtime"
```

The receiver must satisfy the same role contract. `SWARM.md`, handoff records, and events preserve
current responsibility and historical attribution without rewriting actor identity. See
[Governed handoffs](handoffs.md) for self-initiated and governance-managed transfers.

For a local composite team, add `--represented-swarm <child-id>` when registering a project-scoped
actor whose kind is `swarm`. Agora requires the child to be operational and enforces acyclic
delegation within the project's configured depth. See [Recursive swarms](recursive-swarms.md).

Linked teams can receive bounded work through `agora delegation create`, accept it inside the child
with `agora delegation accept`, and return a terminal result reference through
`agora delegation collect`. Method roles must grant the corresponding delegation actions; parent and
child lifecycle gates remain independent. See [Delegated work](delegated-work.md).

## Customize the agent environment

The `integration` field selects one adapter at initialization:

| Integration | Materialized instructions |
| --- | --- |
| `codex` | `.agents/skills/agora-*/SKILL.md` |
| `claude` | `.claude/commands/agora.*.md` |
| `generic` | `.agora/commands/*.md` only |

Every project receives the portable `.agora/commands` set. Codex and Claude additionally receive a
copy in their environment-specific location. `agora upgrade` installs commands and adapters added by
a supported framework migration only when their paths are absent. It preserves existing adapter
content; if portable commands are customized, review and update their adapter files as part of the
same change.

Prepare an execution session after an actor is assigned to a ready or running swarm:

```bash
agora start --id delivery-run --actor delivery-agent \
  --swarm release --work release-candidate
```

This resolves actor overrides over project defaults and persists the runtime plus compiled context
under `.agora/sessions/delivery-run`. Use `--launch` to run the detected `codex` or `claude` command,
or pass `--runner "your-command" --launch` for another CLI. Without `--launch`, the session remains a
portable delegation record for an IDE, CI worker, or cloud orchestrator.

Keep environment-specific behavior out of Method Packs. Roles and lifecycle rules must remain usable
when the project changes model provider, IDE, CLI, or cloud environment.

## Customize distribution templates

Framework developers may point initialization at an alternate complete template tree:

```bash
export AGORA_TEMPLATE_ROOT=/absolute/path/to/templates
agora init --path ./temporary-project
```

The directory must contain compatible `project`, `methods`, and `commands` trees. This advanced
override replaces the distribution template source for the process; it is not a project-level merge
mechanism. Prefer installable Method Packs and project amendments for normal customization.

## Safe updates

Update a uv tool installation from a refreshed checkout:

```bash
cd agora
git pull
uv tool install --force .
agora --help
```

Updating the CLI does not automatically rewrite existing `.agora` workspaces. This protects local
policy and work history. Preview the supported project migration after updating:

```bash
cd /path/to/project
agora upgrade
agora upgrade --apply
agora validate
```

The first command performs no writes. The second stores a manifest and pre-change file backups under
`.agora/upgrades/<upgrade-id>`. Existing constitutions, protocols, Method Packs, Tool Packs, and
commands are not overwritten. See [Project upgrades](project-upgrades.md) for recovery and
compatibility details.

`agora init --force` replaces generated project, method, command, and adapter files. Use it only on a
reviewable branch after backing up or committing project customizations. It is not a general upgrade
or model-switch command.

## Uninstall

Remove a uv tool installation with:

```bash
uv tool uninstall agora-framework
```

Uninstalling the CLI intentionally leaves `~/.agora`, project `.agora` directories, and Git history
untouched. Remove persisted configuration separately only when its data is no longer needed.

## Troubleshooting

### No Agora project found

Run commands inside an initialized project or target it explicitly:

```bash
agora --project /path/to/project doctor
agora --project /path/to/project validate
```

### Method Pack is not installed

Install the pack at user scope before configuration, or at project scope before selecting it for a
swarm. Verify that `<pack>/METHOD.md` exists and its `id` matches the requested method.

### Refusing to overwrite an existing file

Agora defaults to preserving local state. Inspect the file and diff first. Use `--force` only on the
specific configure, init, actor, or method-install operation whose replacement is intentional.

### Integration check fails

Run `agora doctor` and inspect the reported adapter path. If project configuration was edited after
initialization, regenerate or manually update the environment adapter on a reviewable branch.

### The agent does not see new instructions

Confirm the expected files exist, then reload or restart the selected IDE/CLI environment according
to that environment's own discovery behavior. Agora writes instruction files but does not control an
agent host's cache or session lifecycle.

## Next steps

- [Getting started](../getting-started.md) builds the first governed swarm.
- [LLM environments](llm-environments.md) explains provider-neutral model configuration.
- [Scrum delivery](scrum-delivery.md) follows a human and AI team through completion.
- [Method Pack reference](../reference/method-packs.md) defines the lifecycle extension contract.
