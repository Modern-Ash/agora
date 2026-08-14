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
gates, approvals, handoffs, delegations, sessions, and tool runs. `src/agora/methods.py` loads
transition graphs, WIP limits, and gate policies. `src/agora/tools.py` validates provider-neutral
Tool Packs and structured external operations. `src/agora/markdown.py` implements the
JSON-compatible front matter used by the protocol.

### Templates

`templates/project` contains the base constitution, protocol, and catalogs. `templates/methods`
provides Scrum and Kanban as replaceable presets. User and project scopes may install any Method Pack
that satisfies the Markdown contract. `templates/commands` contains portable instructions that
adapters install as Codex skills or commands for other agents.

### Scopes

- Distribution: defaults versioned with the Python package.
- User: reusable preferences and actors under `~/.agora` or `$AGORA_HOME`.
- Project: shared constitution, integration, methods, policies, and maximum delegation depth.
- Swarm: objective, current assignments, handoff history, branch, work, and evidence.

More specific scopes may restrict broader scopes. They must not silently grant permissions prohibited
by a broader scope.

Method Packs under `~/.agora/methods` are copied into a newly initialized project. Packs installed in
the project remain local to it. The active pack, rather than the core CLI, supplies lifecycle roles,
states, transitions, protocol, tool policy, and completion expectations.

### Git and filesystem

Markdown is the durable contract and the filesystem represents current state. Git adds history,
diffs, review, synchronization, and branches. There is no parallel JSON snapshot. Atomic replacement
keeps the previous document intact when an operation fails.

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

## Security and concurrency

This slice validates actor kind, capabilities, assignment, handoff authority, allowed action,
transition-specific role, WIP, gates, approval records, Tool Pack inputs, and tool capabilities.
External commands still run with the caller's operating-system permissions. Agora does not yet
implement sandboxing, signatures, distributed locks, actor authentication, or concurrent writer
protection. Those rules must be added without turning chat history or a proprietary service into the
source of truth.
