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
`src/agora/workspace.py` materializes and validates documents, capabilities, actions, workflows, and
gates. `src/agora/markdown.py` implements the JSON-compatible front matter used by the protocol.

### Templates

`templates/project` contains the base constitution, protocol, and catalogs. `templates/methods`
provides Scrum and Kanban as replaceable presets. User and project scopes may install any Method Pack
that satisfies the Markdown contract. `templates/commands` contains portable instructions that
adapters install as Codex skills or commands for other agents.

### Scopes

- Distribution: defaults versioned with the Python package.
- User: reusable preferences and actors under `~/.agora` or `$AGORA_HOME`.
- Project: shared constitution, integration, methods, and policies.
- Swarm: objective, assignments, branch, work, and evidence.

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

## External integrations

Jira, repositories, CI/CD, Confluence, cloud, and observability will be modeled as tool adapters with
explicit capabilities. Role policies determine which actions may be invoked. Results become artifact
or evidence references; credentials are never copied into Git.

## Security and concurrency

This slice validates actor kind, capabilities, assignment, allowed action, transition, and completion
gate. It does not yet implement sandboxing, signatures, distributed locks, actor authentication, or
concurrent writer protection. Those rules must be added without turning chat history or a proprietary
service into the source of truth.
