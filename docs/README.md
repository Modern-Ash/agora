# Agora documentation

Agora is a local, Markdown-first, Git-native framework for customizing and governing work
lifecycles. Start with the user journey, then use the conceptual and reference material as needed.

Agora Core owns the domain, application services, protocol, and persistence. Agora CLI is an
optional terminal and automation interface. Agora Studio is a local-first web control plane whose
Studio API calls the same application services as the CLI; neither interface owns lifecycle rules.

## Project map

The three public repositories form one demonstrable stack:

- [Agora Core](https://github.com/Modern-Ash/agora) is the reusable governance kernel and Python
  package. Its `packs/` sources become the operational Markdown materialized in a governed project.
- [Agora Studio](https://github.com/Modern-Ash/agora-studio) is the optional local visual adapter.
  It calls Core's versioned application services and never becomes a second policy engine.
- [Truco Agora](https://github.com/Modern-Ash/truco-agora) is the executable reference application.
  It shows how a real product can use the Core workflow while comparing human and LLM players,
  discovering local providers, and retaining evidence in Git.

Use the Core guides for protocol and lifecycle behavior, the Studio README for visual operation,
and the Truco README for a complete domain-level demo. Links between these repositories are
deliberate: a reader can move from governance concepts to a UI and then to a running application
without confusing their ownership boundaries.

## Documentation boundaries

This directory contains explanatory product documentation. Operational Markdown is sourced from
`../packs/` and becomes authoritative only after Agora materializes it under `.agora/`,
`.agents/`, or `.claude/` in a governed project.

The files under `superpowers/` are intentionally retained plugin-run output. They are useful
development context but are not normative Agora documentation or installed agent protocol.

See [Documentation and artifact locations](reference/artifact-locations.md) for the complete
source-to-runtime map, including portable commands, Method Packs, Tool Packs, agent adapters,
durable work records, and externally owned product artifacts.

For the current hardening sequence, see the [core improvement roadmap](roadmap.md). The implemented
transaction, Tool Result, and Jira exercise changes are recorded in [Core hardening and observable
Jira integration](changes/2026-08-core-hardening-and-jira.md). Advisory specification tooling,
runtime fallbacks, provenance, traceability, and the aggregate board are recorded in
[Spec tooling and runtime resilience](changes/2026-08-spec-tooling-runtime-resilience.md).
Core 0.8 evidence identity, optimistic consistency, expiring preparations, transactions, stable
errors, budget amendments, and optional Jira live verification are recorded in
[Core 0.8 application hardening](changes/2026-08-core-0.8-application-hardening.md). Studio and other
consumers should follow the [Core 0.7 to 0.8 migration guide](guides/core-0.8-studio-migration.md).

## Operational Markdown

These directories are the operational product, not explanatory documentation:

- [Portable agent commands](../packs/commands/): model-independent instructions projected into
  Codex, Claude, or a generic environment.
- [Project protocol](../packs/scaffold/): constitution, shared protocol, standards, and catalogs.
- [Method Packs](../packs/methods/): roles, transitions, gates, WIP, and lifecycle policy.
- [Tool Packs](../packs/tools/): provider-neutral capabilities and operations.
- [Reviewed CLI adapters](../packs/adapters/): bounded translations to native provider CLIs.

After initialization, inspect their materialized forms in the governed project's `.agora/`,
`.agents/`, or `.claude/` directories. Actor and swarm records are created there dynamically; they
do not exist as one static agent file in this repository.

## Start here

- [Visual adoption guide](adoption.md): choose an installation, execution environment, first
  workflow, and team adoption level through diagrams and minimal commands.
- [Quickstart](guides/quickstart.md): initialize a complete mixed human and agentic workspace.
- [Guided setup and adoption](guides/guided-setup.md): configure a project one reviewed decision at
  a time, or reproduce the same plan non-interactively.
- [Operational agent loop](guides/operational-loop.md): create guided work, continue one bounded
  action, diagnose failures, and stop at human authority.
- [Spec tooling and runtime resilience](guides/spec-tooling-and-runtime-resilience.md): clarify
  intent, maintain non-binding checklists, verify artifacts, generate Gherkin, configure runtime
  fallbacks, and render the aggregate board.
- [AI-native SDLC controls](guides/ai-native-sdlc.md): govern intent, continuous evaluations,
  structured reviews, runtime guardrails, idempotent triggers, control bands, and delivery metrics.
- [Getting started](getting-started.md): follow the governed workflow from installation to completed
  work.
- [Installation and customization](guides/installation-and-customization.md): configure user,
  project, lifecycle, actor, template, and agent-environment scopes.
- [Project upgrades](guides/project-upgrades.md): preview and apply protocol migrations without
  replacing local policy.

## Governance and operations

- [Actor authentication](guides/actor-authentication.md): manage external actor identities, rotation,
  revocation, recovery, and authenticated sessions.
- [Signed lifecycle actions](guides/signed-lifecycle-actions.md): prepare, sign, apply, and audit
  durable lifecycle mutations.
- [Environment permissions](guides/environment-permissions.md): constrain Tool Runs by capability,
  role, approval, and evidence.
- [Portable Tool execution boundaries](guides/execution-boundaries.md): enforce process timeouts and
  captured-output limits.
- [Conventional Commits](guides/conventional-commits.md): govern repository history through project
  standards and Tool Pack validation.
- [Concurrent writers](guides/concurrent-writers.md): coordinate local mutations and optional
  cross-host leases.
- [Operations and validation](guides/operations-and-validation.md): query state, inspect events, and
  audit durable records.
- [Activity Ledger](guides/activity-ledger.md): follow linked work, session, and Tool Run activity
  from a concise chronology to its durable evidence and bounded logs.
- [Application Services contracts](reference/application-services.md): consume the versioned Core
  read and command boundary from CLI, Studio API, or another local adapter.
- [Core 0.8 Studio migration](guides/core-0.8-studio-migration.md): adopt new schemas, preparation
  timestamps, external evidence digests, and operational errors without moving policy into HTTP.
- [Operational agent loop](guides/operational-loop.md): derive next actions, run bounded external
  actors, stop at human authority, and resume durable failures.
- [Complete verification](guides/verification.md): run format, lint, tests, documentation, samples,
  and distribution checks.
- [Role conformance test harness](guides/self-test.md): visually trace and exercise every bundled
  method with human, AI, and swarm role holders in temporary workspaces using one command.
- [Interruptions and cancellation](guides/interruptions-and-cancellation.md): block, resume, reject,
  or cancel work without erasing history.

## Agents, swarms, and work

- [LLM environments](guides/llm-environments.md): materialize portable commands for Codex, Claude,
  or a generic runner without an LLM SDK.
- [Scrum delivery](guides/scrum-delivery.md): run a complete mixed human and AI Scrum example.
- [Kanban delivery](guides/kanban-delivery.md): govern continuous pull, WIP, review, and service
  acceptance.
- [Spec-driven delivery](guides/spec-driven-delivery.md): clarify a durable specification before
  planning and implementation.
- [Governed handoffs](guides/handoffs.md): move a role between human, AI, service, or swarm actors.
- [Recursive swarms](guides/recursive-swarms.md): link child swarms with cycle and depth limits.
- [Delegated work](guides/delegated-work.md): propose, accept, execute, and collect child work.
- [Delegation budgets](guides/delegation-budgets.md): propagate limits and record evidence-backed
  provider-neutral usage.
- [Delegated artifact promotion](guides/delegated-artifacts.md): promote typed child references
  without copying opaque product bytes.
- [Work decomposition](guides/work-decomposition.md): create same-swarm child contracts and enforce
  parent-child closure.
- [Granular Gate Waivers](guides/gate-waivers.md): record evidence-backed residual-risk exceptions.
- [Approval Delegation](guides/approval-delegation.md): grant a single-use, work-scoped approval.

## Ecosystem integrations

- [GitHub ecosystem](guides/github-ecosystem.md): install and govern Issues, Pull Requests, Actions,
  repository policy, releases, security alerts, Projects, and explicit snapshots.
- [CLI-first ecosystem adapters](guides/cli-first-adapters.md): prefer reviewed native CLIs while
  retaining MCP as an explicit alternative transport.
- [Code-review integrations](guides/code-review-integrations.md): govern Pull Requests, checks,
  decisions, and opt-in merge authority.
- [Work-management integrations](guides/work-management-integrations.md): connect issue trackers
  through a provider-neutral operation contract.
- [CI/CD integrations](guides/ci-cd-integrations.md): inspect and trigger pipelines while governing
  cancellation and deployment.
- [Knowledge-base integrations](guides/knowledge-base-integrations.md): separate documentation draft,
  publication, and archival authority.
- [Cloud integrations](guides/cloud-integrations.md): separate infrastructure inspection, planning,
  apply, and destruction.
- [Observability integrations](guides/observability-integrations.md): collect bounded operational
  evidence and govern incident mutation.

## Packs, registries, and supply-chain trust

- [Pack registries](guides/pack-registries.md): discover Method and Tool Packs through deterministic
  scope precedence.
- [Pack dependencies](guides/pack-dependencies.md): resolve compatible cross-kind dependency graphs.
- [Pack updates](guides/pack-updates.md): preview dependency-aware updates and protect amendments.
- [Pack composition locks](guides/pack-locks.md): inventory installed trees and verify update history.
- [Pack removal](guides/pack-removal.md): remove compositions safely with explicit orphan pruning.
- [Remote registry releases](guides/remote-registries.md): verify checksum-pinned, signed, and
  transparency-backed releases.
- [Registry trust stores](guides/registry-trust.md): manage scoped keys, revocations, organization
  feeds, and root rotation.
- [Registry updates](guides/registry-updates.md): audit and transactionally apply authenticated
  releases.

## Concepts, reference, and decisions

- [Documentation and artifact locations](reference/artifact-locations.md): distinguish manuals,
  plugin output, distribution templates, agent adapters, project records, and work products.
- [Domain model](domain-model.md): packs, actors, roles, swarms, handoffs, work, and evidence.
- [Architecture](architecture.md): Core, CLI, Studio, application-service, persistence, and adapter
  boundaries.
- [Core improvement roadmap](roadmap.md): prioritized transaction, modularity, error, budget, and
  live-integration work without release-date promises.
- [Method Pack reference](reference/method-packs.md): author and install custom lifecycles.
- [Tool Pack reference](reference/tool-packs.md): govern external CLIs and persist results.
- [ADR 0001](decisions/0001-initial-architecture.md): why Agora is local, Markdown-first, and
  Git-native.
- [ADR 0002](decisions/0002-spec-tooling-and-runtime-resilience-additions.md): why advisory spec
  tooling, runtime fallbacks, provenance, traceability, and the aggregate board preserve the same
  governance boundaries.
- [ADR 0003](decisions/0003-core-studio-cli-boundaries.md): why Core owns lifecycle behavior while
  CLI and local-first Studio share versioned application-service contracts.

## Executable samples

- [Actor authentication](../samples/actor-authentication/README.md): sign a lifecycle action, Tool
  Run, and agent session externally, then rotate and revoke the public key without losing evidence.
- [Approval Delegation](../samples/approval-delegation/README.md): consume one scoped delegated
  approval, revoke another, and preserve the original role assignment.
- [Basic Scrum swarm](../samples/basic-swarm/README.md): a human Product Owner, AI Scrum Master, and
  nested delivery swarm complete a governed increment.
- [LLM environments](../samples/llm-environments/README.md): materialize Codex, Claude, and
  generic/local configurations.
- [Custom lifecycle](../samples/custom-lifecycle/README.md): install a Method Pack unrelated to Scrum
  or Kanban.
- [Governed tool integration](../samples/tool-integration/README.md): invoke Git through a
  role-authorized Tool Pack and inspect its durable result.
- [Tool execution boundaries](../samples/execution-boundaries/README.md): observe a successful run,
  timeout, and output-limit failure through one bounded Python provider.
- [Governed work management](../samples/work-management/README.md): execute a provider-neutral issue
  tracker contract through a local Python adapter and reject unauthorized transitions.
- [Governed CI/CD](../samples/ci-cd/README.md): trigger a pipeline and require explicit capability
  plus Product Owner approval before deployment.
- [GitHub Actions CLI adapter](../samples/github-actions-cli/README.md): install the reviewed `gh`
  adapter, prepare native commands, and preserve separate cancellation authority.
- [Governed GitHub delivery](../samples/github-end-to-end/README.md): prepare the complete path from
  Issue and branch through review, merge, security snapshots, Projects, and release.
- [GitLab CI/CD CLI adapter](../samples/gitlab-ci-cli/README.md): prepare bounded pipeline reads and
  reject unauthorized cancellation and unsupported trigger translation.
- [GitHub Issues CLI adapter](../samples/github-issues-cli/README.md): prepare native issue searches
  and constrain dynamic transitions to close or reopen.
- [GitLab Issues CLI adapter](../samples/gitlab-issues-cli/README.md): prepare native issue reads and
  transitions while rejecting deletion and unsupported typed creation.
- [GitLab Merge Requests CLI adapter](../samples/gitlab-merge-requests-cli/README.md): prepare native
  review creation and head-pipeline checks while rejecting unsupported merge translation.
- [Jira ACLI adapter](../samples/jira-cli/README.md): execute the reviewed Jira contract against a
  deterministic ACLI-compatible process, inspect captured responses, and keep live Jira
  authentication external.
- [Atlassian TWG Confluence adapter](../samples/twg-confluence-cli/README.md): prepare page lifecycle
  commands, require optimistic concurrency, and reject unsupported search translation.
- [CLI runtime compatibility](../samples/cli-runtime-compatibility/README.md): probe local adapter
  versions without accessing credentials or contacting providers.
- [Terraform CLI adapter](../samples/terraform-cli/README.md): prepare state reads and a saved plan
  through native Terraform while preserving separate apply authority.
- [Governed knowledge base](../samples/knowledge-base/README.md): draft external documentation,
  require approval before publication, and reject unauthorized archival.
- [Governed cloud infrastructure](../samples/cloud-infrastructure/README.md): plan a cloud change,
  require approval before apply, and reject unauthorized destruction.
- [Environment permissions](../samples/environment-permissions/README.md): require role scope,
  approval, and successful evidence before preparing a production Tool Run.
- [Native cloud inventory](../samples/cloud-inventory-cli/README.md): prepare bounded AWS and Google
  Cloud reads while proving partial adapters expose no deployment operation.
- [Governed observability](../samples/observability/README.md): inspect health, declare an incident,
  and require approval before external resolution.
- [Governed handoffs](../samples/handoffs/README.md): preserve one work item while its Developer role
  moves from a human to an AI agent and a swarm.
- [Recursive swarms](../samples/recursive-swarms/README.md): delegate a parent role to a real child
  swarm and reject excessive nesting.
- [Delegated work](../samples/delegated-work/README.md): execute the proposal, child acceptance, and
  result collection lifecycle with a signed inherited budget.
- [Work decomposition](../samples/work-decomposition/README.md): create local child work and reject
  parent closure until every child is terminal or cancelled.
- [Gate Waivers](../samples/gate-waivers/README.md): reject an incomplete Scrum gate, record an exact
  risk-backed exception, and complete the governed transition.
- [Operational queries](../samples/operational-query/README.md): summarize and validate a generated
  workspace without a database.
- [Operational loop](../samples/operational-loop/README.md): preview actor authority and runtime,
  launch an external actor subprocess with interactive controller events, stop at a human gate, and
  complete the lifecycle.
- [Interruptions and cancellation](../samples/interruptions/README.md): exercise durable status
  histories and parent-child authority.
- [Project upgrade](../samples/project-upgrade/README.md): migrate a legacy Codex project while
  preserving local policy and validating the resulting records.
- [Concurrent writers](../samples/concurrent-writes/README.md): reject a competing mutation and
  continue safely after the operating-system lock is released.
- [Distributed coordination](../samples/distributed-coordination/README.md): wrap a project mutation
  in an external lease while preserving mandatory local locking.
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
required artifacts, acceptance criteria, successful evidence, direct and delegated approvals, Gate
Waivers, handoffs, work and
delegation interruption histories, delegated work, Tool Pack operations, cross-record integrity,
and event syntax. It can launch local LLM and tool CLIs with durable context, but does not call
provider APIs directly, manage credentials, implement a remote scheduler or distributed lease
service, or replace external systems.
