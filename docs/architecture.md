# Initial architecture

## Purpose

Agora installs a local layer for customizing and governing the complete work lifecycle of humans and
agents. The distributed product is a small Python CLI accompanied by Markdown templates. Python is
an implementation choice for the CLI, not a required language or runtime for governed projects. The
materialized product is the `.agora` directory and the selected agent adapter inside a project.

```text
Python CLI + templates
          |
          +-> ~/.agora                  personal configuration
          +-> <project>/.agora          shared protocol and state
          +-> integration adapter       agent skills or commands
          +-> Git branch                swarm isolation and history
```

## Components

### CLI

`src/agora/cli.py` translates shell commands into workspace operations. It does not maintain a server
or database, invoke an LLM, inspect project source languages, or impose a development methodology.
`src/agora/workspace.py` materializes and validates documents, capabilities, actions, workflows,
gates, approvals, handoffs, interruptions, delegations, sessions, and tool runs.
`src/agora/methods.py` loads
transition graphs, WIP limits, and gate policies. `src/agora/tools.py` validates provider-neutral
Tool Packs and structured external operations. `src/agora/markdown.py` implements the
JSON-compatible front matter used by the protocol. `src/agora/upgrades.py` plans ordered project
migrations, preserves customization boundaries, backs up changed files, and writes durable upgrade
manifests.
`src/agora/packs.py` validates shared pack versions, dependency declarations, and compatibility
ranges.
`src/agora/registries.py` validates installed registry snapshots and discovers Method and Tool Packs.
`src/agora/registry_distribution.py` resolves remote Markdown indexes, selects semantic releases,
enforces transport and archive limits, verifies SHA-256 and optional Ed25519 signatures, and extracts
snapshots into temporary directories before the local registry path accepts them.
`src/agora/trust.py` validates Ed25519 public-key records and durable revocation state without
handling private signing material.

Read operations traverse those same records to produce deterministic JSON lists and summaries.
There is no query database or generated index. Full validation catches errors per record, continues
the scan, then checks portable commands, generated adapters, cross-record ownership, references,
lifecycle state, recursive graphs, and terminal results. This makes `agora validate` suitable for CI
without changing the source of truth.

### Templates

`templates/project` contains the base constitution, protocol, standards, and catalogs. `templates/methods`
provides Scrum and Kanban as replaceable presets. User and project scopes may install any Method Pack
that satisfies the Markdown contract. `templates/commands` contains portable instructions that
adapters install as Codex skills or commands for other agents.

### Scopes

- Distribution: defaults versioned with the Python package.
- User: reusable preferences and actors under `~/.agora` or `$AGORA_HOME`.
- Project: shared constitution, integration, standards, methods, policies, and maximum delegation
  depth.
- Swarm: objective, current assignments, handoff history, branch, work, and evidence.

More specific scopes may restrict broader scopes. They must not silently grant permissions prohibited
by a broader scope.

Method Packs under `~/.agora/methods` are copied into a newly initialized project. Packs installed in
the project remain local to it. The active pack, rather than the core CLI, supplies lifecycle roles,
states, transitions, protocol, tool policy, and completion expectations.

Registries are immutable-by-review catalog snapshots under user or project scope. Discovery keeps
every matching provenance visible; installation resolves project before user before bundled unless a
registry id is selected explicitly. Pack installation still copies through the ordinary Method or
Tool Pack validation path.

A remote registry index is a distribution mechanism, not runtime state. Agora verifies its selected
archive and persists a complete local snapshot plus `SOURCE.md`. Governed work never depends on the
index remaining available.

Registry trust uses the same scope rule: project keys precede user keys. Verification binds a key id
to one registry id, and a matching revocation blocks both automatic resolution and an explicit PEM.

Registry updates are read-only plans unless application is explicit. Update staging carries forward
installer-owned history, adds the next transition record, validates the complete candidate, and only
then replaces the installed snapshot. Registry updates never mutate separately installed packs.

Method and Tool Pack manifests declare semantic versions and optional cross-kind dependencies.
Catalog installation resolves the complete dependency graph using registry precedence, checks the
prospective target-scope composition, and installs dependencies before their consumer. Direct source
installation requires dependencies to be present already. Project validation repeats composition
checks so manual filesystem edits cannot leave missing, incompatible, or cyclic dependencies hidden.

Each catalog-installed pack carries installer-owned `SOURCE.md` provenance with its registry,
published version, and deterministic tree checksum. Pack updates are preview-only until `--apply`,
reject downgrades and mutable versions, re-resolve the complete composition, and stage clean atomic
pack replacements. Local amendments remain valid but require explicit `--force` before replacement.

### Git and filesystem

Markdown is the durable contract and the filesystem represents current state. Git adds history,
diffs, review, synchronization, and branches. There is no parallel JSON snapshot. Atomic replacement
keeps the previous document intact when an operation fails.

Project protocol versions are independent from individual Markdown schema identifiers. A CLI update
does not mutate a workspace. `agora upgrade` first produces a read-only plan; `--apply` backs up all
updated files, applies the supported ordered migration, and rolls back the complete change set if a
write fails. Upgrade records live beside project state under `.agora/upgrades` and are validated like
other Agora documents.

### Environment adapters

The protocol remains identical across IDE, CLI, CI/CD, and cloud environments. An adapter only
determines where executable instructions are installed:

- Codex: `.agents/skills/agora-*/SKILL.md`.
- Claude: `.claude/commands/agora.*.md`.
- Generic: `.agora/commands/*.md`.

Adding an adapter must not change Method Packs or domain rules.

Provider and model identifiers are opaque configuration values. The core has no LLM SDK dependency;
an adapter or execution environment decides how a configured model is reached.

### Session launcher

`agora start` compiles durable context from the active project, actor, swarm, method, role, and work.
Actor runtime fields override project defaults. Without `--launch`, the command only prepares files.
With `--launch`, it delegates to `codex`, `claude`, or an explicit runner and exports `AGORA_PROJECT`,
`AGORA_SESSION`, `AGORA_CONTEXT`, `AGORA_ACTOR`, `AGORA_SWARM`, and optional `AGORA_WORK` variables.
The external runtime remains responsible for model authentication and execution.

## External integrations

Jira, repositories, CI/CD, Confluence, cloud, and observability are modeled as Tool Packs around
external CLIs. Each operation declares an executable argument vector, inputs, risk, capability, and
optional approval role. Role policies determine which operations may be invoked. Preparation and
captured results remain in `.agora/tool-runs`; credentials are never copied into Git.

The kernel does not use a shell or vendor SDK. It performs exact argument substitution and delegates
authentication to the executable environment. The bundled Git pack is a reference implementation;
vendor-specific packs remain independently installable Markdown.

## Recursive delegation

A project actor may link its `swarm` identity to another local swarm. Assignment and handoff paths
rebuild the effective parent-to-child graph, reject cycles, and enforce the project's maximum depth.
Linked children must be ready or running when assigned and whenever their composite actor starts a
session, invokes a tool, or mutates governed work. Parent sessions include manifests, events, and
handoffs from the complete delegated descendant hierarchy without merging swarm state.

Work delegation is an explicit protocol layered on that graph. A global `DELEGATION.md` record links
parent and child work without moving either record from its owning swarm. Acceptance creates the
child item through the ordinary lifecycle API. Collection is allowed only after terminal child work
and registers a reference plus evidence in the parent. Sessions include matching delegation records;
no child artifact content is copied or merged.

Operational work status is orthogonal to Method Pack state. Blocking and cancellation update the
current owner document and append a sequenced `STATUS.md` beneath it. Swarm status is derived from
assignments and owned work, so it cannot legitimately claim completion while active work remains.
Delegations use the same status-change record shape while preserving separate parent and child
authority.

## Security and concurrency

This slice validates actor kind, capabilities, assignment, handoff authority, allowed action,
transition-specific role, WIP, gates, approval records, Tool Pack inputs, tool capabilities,
interruption edges, status attribution, sequence continuity, and derived swarm state.
Mutating workspace operations hold a reentrant operating-system lock keyed by the canonical project
or Agora home path. Initialization acquires home and target locks in deterministic order. Lock
metadata is runtime-only Markdown outside the repository; atomic document replacement still protects
readers. This prevents lost updates between local processes and releases automatically after process
termination.

External commands still run with the caller's operating-system permissions. Agora does not yet
implement sandboxing, signatures, distributed leases across separate hosts, or actor authentication.
Those rules must be added without turning chat history or a proprietary service into the source of
truth.
