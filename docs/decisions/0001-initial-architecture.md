# ADR 0001: Agora is local, Markdown-first, and Git-native

- Status: Accepted
- Date: 2026-08-14

## Context

Agora must customize and govern human and agentic work lifecycles without depending on a programming
language, provider, LLM, IDE, development methodology, platform, or project runtime. It must also
integrate with daily development tools and preserve continuity across local, CLI, CI/CD, and cloud
environments.

The first prototype used a TypeScript kernel with a JSON snapshot. Although it demonstrated domain
invariants, that model turned Agora into a state application and duplicated information that belongs
in the repository.

## Decision

Distribute an installable Python CLI and versioned Markdown templates, following the model of local
project initialization tools. Python is the implementation language of the distribution tooling and
does not constrain the language or runtime of governed projects. The CLI materializes personal
configuration under `~/.agora`, project protocol under `.agora`, adapters for the selected agent, and
one branch per swarm.

Use Markdown with JSON-compatible front matter as the operational contract. Read workflows, roles,
capabilities, and allowed actions from open-ended Method Packs rather than hard-coding a development
process. Use the filesystem for current state and Git for history, synchronization, and review. Do
not invoke LLM SDKs directly, inspect source languages, or store credentials.

## Consequences

The process is visible to humans, portable across agents, and recoverable without a database. Method
Packs can be reviewed as code and each environment can install its own adapter.

The CLI needs concurrency controls and template compatibility rules as the format evolves. Versioned,
transactional project migrations were introduced after the initial slice; Markdown does not replace
validation, so front matter preserves structured metadata and gates remain executable.

## Future work

- Organization trust synchronization, revocation feeds, and transparency for remote registry
  releases. Local and project trust keys, rotation, and revocation are implemented.
- Background registry notifications and automatic installed-pack updates. Explicit authenticated
  checks, transactional registry replacement, durable update history, dependency manifests, and
  compatibility-aware catalog installation are implemented. Installed pack provenance and explicit,
  dependency-aware pack updates are also implemented, including per-pack transition history and
  deterministic scope composition locks. Preview-first, dependency-safe pack removal is implemented
  with explicit orphan pruning, rollback protection, lock refresh, and durable audit records.
- Published vendor Tool Packs for Jira, CI/CD, documentation, and cloud.
- Delegation budgets, automatic child work decomposition, and child artifact copying. Explicit
  reference-based result collection is part of the current filesystem protocol.
- Distributed leases for work coordinated across separate hosts. Local writer locks are implemented.
- Gate waivers, approval delegation, budgets, and environment-specific permissions.
