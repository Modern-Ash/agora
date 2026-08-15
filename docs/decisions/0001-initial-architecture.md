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

- Organization root rotation, threshold signatures, and third-party transparency-log proofs for
  remote registry releases. Signed sequential trust and revocation feeds are implemented.
- Automatic installed-pack updates and in-process background scheduling. Aggregate authenticated
  notifications can be invoked and recorded by an external scheduler. Explicit authenticated
  checks, transactional registry replacement, durable update history, dependency manifests, and
  compatibility-aware catalog installation are implemented. Installed pack provenance and explicit,
  dependency-aware pack updates are also implemented, including per-pack transition history and
  deterministic scope composition locks. Preview-first, dependency-safe pack removal is implemented
  with explicit orphan pruning, rollback protection, lock refresh, and durable audit records.
- Additional published vendor Tool Packs for Jira, documentation, cloud, and observability.
  Provider-neutral contracts and executable adapter samples are implemented, and the reviewed
  GitHub Actions, GitHub Issues, and Terraform CLI adapters now delegate directly to installed
  native tools through the CLI-first adapter catalog. Partial AWS and Google Cloud inventory
  adapters provide bounded reads without claiming provider-wide deployment semantics. Jira has a
  complete ACLI adapter; Confluence still requires a reviewed wrapper or future supported CLI.
- Governed same-swarm work decomposition, provider-neutral delegation budgets, opt-in typed child
  artifact promotion, and explicit cross-swarm reference-based result collection are part of the
  current filesystem protocol. Opaque external artifact bytes remain provider-owned.
- Optional distributed writer coordination is implemented through a provider-neutral external lease
  CLI layered over mandatory local locks. The lease service and remote scheduling remain external.
- Environment-specific Tool Run permissions are implemented through project-defined Markdown
  policies, Method Pack role restrictions, operation opt-in, approvals, evidence, launch-time
  revalidation, and signed environment binding. Single-use, work-scoped Approval Delegation and
  granular, evidence-backed Gate Waivers are also implemented without transferring roles or
  bypassing transition, role, WIP, child-closure, or work-status policy.
