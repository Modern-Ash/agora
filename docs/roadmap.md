# Core improvement roadmap

This roadmap records recommended core hardening after the observable Jira integration exercise. It
is ordered by risk reduction and architectural leverage, not by promised release date. Every item
must preserve Agora's language, model, provider, and process independence.

The target product boundary follows [ADR 0003](decisions/0003-core-studio-cli-boundaries.md): Agora
Core owns domain rules and application services; Agora CLI and Studio API are peer adapters over
those services. Studio is local-first for the 0.x series, and Markdown plus Git remain
authoritative.

## Implemented foundation

- Atomic replacement for individual Markdown documents.
- Local reentrant writer locks and optional provider-neutral external leases.
- Rollback-protected work creation across its contract, event streams, and Activity Ledger.
- Typed, read-only inspection of Tool Runs and captured Tool Results.
- Validation that terminal result identity and metadata match the governing run.
- A complete versioned read boundary for sessions, Method Packs, lifecycle blockers, materials,
  traceability, and bounded specification history, shared by CLI and Studio API.
- Typed gate-decision domain failures and transaction-exact Activity results.
- Exact multi-transition gate decision options, state-bound signing preparation, bounded
  specification revision detail, and an aggregate work control projection for Studio consumers.
- Core 0.7 canonical gate commands, Core-issued governed-material precondition digests, evidence
  references tied to required evidence types, and lock-consistent work control snapshots.
- An executable Jira adapter scenario that shows reads, writes, provider output, and denied
  authority without requiring live credentials.

The detailed implementation record is [Core hardening and observable Jira
integration](changes/2026-08-core-hardening-and-jira.md).

## Priority 1: expand compound mutation transactions

Adopt the shared filesystem transaction in lifecycle mutations that update multiple durable files,
starting with transitions and evidence-bearing completion paths. Keep specialized pack, registry,
trust, and upgrade transactions separate until their staging semantics can be unified without losing
provenance or rollback guarantees.

Acceptance conditions:

- every adopted mutation identifies its complete write set;
- injected failure tests cover early, middle, and final writes;
- rollback restores existing contents and permissions and removes newly created files;
- event streams and the Activity Ledger cannot advance without the domain record;
- validation succeeds after a rolled-back failure;
- documentation states which operations have the guarantee.

## Priority 2: continue extracting mutation handlers

The read boundary and first governed gate command are extracted. `AgoraWorkspace` still centralizes
many mutation families, validation, rendering, and persistence. Continue extracting explicit
operation families behind a small handler registry while retaining `AgoraWorkspace` as the public
compatibility facade during the transition. Agora CLI and Studio API must call those same services
rather than each other.

Recommended boundaries:

```text
AgoraWorkspace
└── AgoraApplicationServices
    ├── WorkLifecycleHandlers
    ├── DelegationHandlers
    ├── ActorIdentityHandlers
    ├── ToolRunHandlers
    ├── SessionHandlers
    └── PackAndRegistryHandlers
```

Handlers should receive explicit resolved context and filesystem services. They must not introduce a
service container, runtime plugin loading, vendor SDK, or alternate persistence store.

Acceptance conditions:

- lifecycle action dispatch uses a declarative action-to-handler map;
- adding one action does not extend a central conditional chain;
- CLI and Studio API exercise the same application service for the same use case;
- shared requests, responses, events, and errors are serializable and explicitly versioned;
- interface adapters contain no lifecycle policy and Studio never shells out to the CLI;
- existing public Python and CLI behavior remains compatible;
- Method Pack rules are reapplied immediately before every mutation;
- unit tests can exercise a handler without initializing unrelated subsystems.

## Priority 3: stable operational error model

Introduce provider-neutral exceptions carrying a stable code, human message, optional durable path,
and recovery hint. CLI rendering may remain friendly for terminals and structured for captured
output.

Initial error families should cover:

- missing or malformed records;
- actor authority and environment policy denial;
- lifecycle precondition and gate failure;
- runtime compatibility and external process failure;
- transaction commit, rollback, and indeterminate recovery;
- stale signed action or authorization material.

Acceptance conditions:

- codes are stable and documented independently of Python exception class names;
- secrets and raw credentials never appear in context or hints;
- failure-path tests assert codes as well as messages;
- external provider errors remain distinguishable from Agora policy denial;
- no provider-specific exception enters the core contract.

## Priority 4: explicit budget amendments

Delegation usage is append-only and bounded by inherited work budgets, but legitimate capacity
changes need an explicit lifecycle operation rather than manual Markdown editing.

An amendment should bind:

- parent and child work identities;
- previous and proposed integer limits;
- accountable actor and role authority;
- reason and optional evidence references;
- signed action preconditions when authentication is required;
- an append-only amendment history.

Limits must never be silently reduced below already recorded usage or increased by a child actor
without parent authority.

## Priority 5: optional live integration smoke tests

Keep deterministic local samples as the default verification contract. Add opt-in smoke tests for
reviewed provider environments only when their native CLI, authentication, disposable target, and
explicit environment flag are present.

For Jira, a live smoke test should:

- use a dedicated non-production project;
- prepare before every write and expose the exact command for review;
- create a uniquely labeled disposable item;
- read, comment, transition, and verify it through the adapter;
- avoid deletion unless the neutral contract and Jira workflow both support it safely;
- retain bounded Tool Runs and report cleanup requirements;
- skip cleanly when ACLI or authentication is unavailable.

Live provider tests must never run in the ordinary unit-test or sample matrix and must never make
credentials durable.

## Explicit non-goals

- No LLM SDK or provider client in the core CLI.
- No background Jira or provider synchronization.
- No shell command construction for Tool Packs.
- No automatic installation or authentication of native provider CLIs.
- No database replacing Markdown and Git as the collaboration substrate.
- No direct Studio edits to `.agora/` or conceptual dependency on terminal commands.
- No authoritative Studio database; SQLite may only be a regenerable local projection.
- No remote or multiuser Studio mode during the initial 0.x scope.
- No claim that rollback protection supplies operating-system or distributed transaction isolation.
