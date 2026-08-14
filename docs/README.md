# Agora documentation

Agora is a local, Markdown-first, Git-native framework for customizing and governing work
lifecycles. Start with the user journey, then use the conceptual and reference material as needed.

## Start here

- [Installation and customization](guides/installation-and-customization.md): install the CLI and
  tailor user, project, lifecycle, actor, template, and agent-environment scopes.
- [Project upgrades](guides/project-upgrades.md): preview, apply, audit, and recover protocol
  migrations without replacing local policies or Method Packs.
- [Concurrent writers](guides/concurrent-writers.md): serialize local mutations, inspect lock owners,
  and configure bounded contention waits.
- [Conventional Commits](guides/conventional-commits.md): enforce standardized repository history
  through project rules and governed Tool Pack input validation.
- [Work-management integrations](guides/work-management-integrations.md): connect Jira, Linear, or
  internal trackers through one provider-neutral, role-governed operation contract.
- [CI/CD integrations](guides/ci-cd-integrations.md): inspect and trigger pipelines, restrict
  cancellation, and guard deployments with explicit role approval.
- [Knowledge-base integrations](guides/knowledge-base-integrations.md): connect Confluence, Notion,
  or internal documentation while separating drafts, publication, and archival authority.
- [Cloud integrations](guides/cloud-integrations.md): inspect and plan infrastructure while keeping
  apply and destruction behind explicit role and approval policy.
- [Observability integrations](guides/observability-integrations.md): query bounded health evidence,
  declare incidents, and keep resolution behind explicit authority.
- [Pack registries](guides/pack-registries.md): install local catalog snapshots, discover Method and
  Tool Packs, and select provenance with deterministic scope precedence.
- [Pack dependencies](guides/pack-dependencies.md): declare compatible pack versions, recursively
  resolve catalog dependencies, and reject broken or cyclic compositions.
- [Pack updates](guides/pack-updates.md): persist catalog provenance, preview dependency-aware
  upgrades, and protect local pack amendments.
- [Pack composition locks](guides/pack-locks.md): inventory installed trees and validate durable,
  continuous per-pack update histories.
- [Pack removal](guides/pack-removal.md): preview safe removals, protect dependents and durable
  references, and explicitly prune unused dependency closures.
- [Remote registry releases](guides/remote-registries.md): publish, verify, and persist versioned
  checksum-pinned and Ed25519-signed registry snapshots.
- [Registry trust stores](guides/registry-trust.md): approve, resolve, rotate, and revoke registry
  signing keys through local Markdown and Git.
- [Registry updates](guides/registry-updates.md): preview and transactionally apply authenticated
  releases while preserving provenance and update history.
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
- [Governed work management](../samples/work-management/README.md): execute a provider-neutral issue
  tracker contract through a local Python adapter and reject unauthorized transitions.
- [Governed CI/CD](../samples/ci-cd/README.md): trigger a pipeline and require explicit capability
  plus Product Owner approval before deployment.
- [Governed knowledge base](../samples/knowledge-base/README.md): draft external documentation,
  require approval before publication, and reject unauthorized archival.
- [Governed cloud infrastructure](../samples/cloud-infrastructure/README.md): plan a cloud change,
  require approval before apply, and reject unauthorized destruction.
- [Governed observability](../samples/observability/README.md): inspect health, declare an incident,
  and require approval before external resolution.
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
- [Project upgrade](../samples/project-upgrade/README.md): migrate a legacy Codex project while
  preserving local policy and validating the resulting records.
- [Concurrent writers](../samples/concurrent-writes/README.md): reject a competing mutation and
  continue safely after the operating-system lock is released.
- [Pack registry](../samples/pack-registry/README.md): discover and install a custom lifecycle from a
  user-scoped Markdown catalog.
- [Pack dependencies](../samples/pack-dependencies/README.md): install a Method Pack and recursively
  resolve its compatible Tool Pack dependency.
- [Pack removal](../samples/pack-removal/README.md): preview and atomically apply a dependency-aware
  composition removal with durable audit evidence.
- [Remote registry](../samples/remote-registry/README.md): verify a signed, versioned registry release
  and persist its provenance.

## MVP boundaries

Agora currently validates transition graphs, role capabilities and actions, WIP limits, gates,
required artifacts, acceptance criteria, successful evidence, approvals, handoffs, work and
delegation interruption histories, delegated work, Tool Pack operations, cross-record integrity,
and event syntax. It can launch local LLM and tool CLIs with durable context, but does not call
provider APIs directly, manage credentials, implement a remote scheduler or distributed lease
service, or replace external systems.
