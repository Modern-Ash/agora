# Agora documentation

Agora is a local, Markdown-first, Git-native framework for customizing and governing work
lifecycles. Start with the user journey, then use the conceptual and reference material as needed.

## Start here

- [Installation and customization](guides/installation-and-customization.md): install the CLI and
  tailor user, project, lifecycle, actor, template, and agent-environment scopes.
- [Getting started](getting-started.md): install Agora, initialize a project, form a swarm, and
  complete governed work.
- [LLM environments](guides/llm-environments.md): configure project and actor runtimes, prepare
  durable sessions, and launch Codex, Claude, or a generic CLI without a provider SDK.
- [Scrum delivery](guides/scrum-delivery.md): run a complete mixed human and AI Scrum example.
- [Governed handoffs](guides/handoffs.md): transfer a live role between human, AI, and swarm actors.
- [Recursive swarms](guides/recursive-swarms.md): link a real child swarm with cycle and depth limits.
- [Delegated work](guides/delegated-work.md): propose child work, accept it, and collect a terminal
  result into its parent.
- [Operations and validation](guides/operations-and-validation.md): query active state, inspect
  events, and audit every durable record.
- [Complete verification](guides/verification.md): validate all command Markdown, generated agent
  adapters, executable samples, tests, and distributions with one Python runner.
- [Interruptions and cancellation](guides/interruptions-and-cancellation.md): block, resume,
  reject, or cancel work and delegations without erasing lifecycle history.
- [Method Pack reference](reference/method-packs.md): create and install a custom lifecycle.
- [Tool Pack reference](reference/tool-packs.md): govern external CLIs and persist their results.

## Concepts and design

- [Domain model](domain-model.md): packs, actors, roles, swarms, handoffs, work, and evidence.
- [Architecture](architecture.md): scopes, adapters, filesystem persistence, and Git behavior.
- [ADR 0001](decisions/0001-initial-architecture.md): why Agora is local, Markdown-first, and
  Git-native.

## Executable samples

- [Basic Scrum swarm](../samples/basic-swarm/README.md): a human Product Owner, AI Scrum Master, and
  nested delivery swarm complete a governed increment.
- [LLM environments](../samples/llm-environments/README.md): materialize Codex, Claude, and
  generic/local configurations.
- [Custom lifecycle](../samples/custom-lifecycle/README.md): install a Method Pack unrelated to Scrum
  or Kanban.
- [Governed tool integration](../samples/tool-integration/README.md): invoke Git through a
  role-authorized Tool Pack and inspect its durable result.
- [Governed handoffs](../samples/handoffs/README.md): preserve one work item while its Developer role
  moves from a human to an AI agent and a swarm.
- [Recursive swarms](../samples/recursive-swarms/README.md): delegate a parent role to a real child
  swarm and reject excessive nesting.
- [Delegated work](../samples/delegated-work/README.md): execute the proposal, child acceptance, and
  result collection lifecycle.
- [Operational queries](../samples/operational-query/README.md): summarize and validate a generated
  workspace without a database.
- [Interruptions and cancellation](../samples/interruptions/README.md): exercise durable status
  histories and parent-child authority.

## MVP boundaries

Agora currently validates transition graphs, role capabilities and actions, WIP limits, gates,
required artifacts, acceptance criteria, successful evidence, approvals, handoffs, work and
delegation interruption histories, delegated work, Tool Pack operations, cross-record integrity,
and event syntax. It can launch local LLM and tool CLIs with durable context, but does not call
provider APIs directly, manage credentials, implement a remote scheduler, or replace external
systems.
