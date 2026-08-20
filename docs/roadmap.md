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
- Core 0.8 content-addressed external evidence, optimistic read-set checks, expiring preparations,
  compound lifecycle transactions, stable operational errors, and explicit budget amendments.
- An opt-in Jira live create smoke that requires an authenticated native CLI and an explicitly
  confirmed non-production project, and reports manual cleanup without persisting credentials.

The detailed implementation record is [Core hardening and observable Jira
integration](changes/2026-08-core-hardening-and-jira.md).

## Priority 1: expand compound mutation transactions — delivered baseline in 0.8

Adopt the shared filesystem transaction in lifecycle mutations that update multiple durable files,
starting with transitions and evidence-bearing completion paths. Keep specialized pack, registry,
trust, and upgrade transactions separate until their staging semantics can be unified without losing
provenance or rollback guarantees.

Core 0.8 adopts the shared reentrant transaction for work transitions, criterion satisfaction,
artifact and evidence registration, approvals, gate decisions, status changes, and the domain/event/
Activity write-set of usage, decomposition, delegation create/accept/collect, signed lifecycle-action
application, and budget amendments. Fault injection covers first, intermediate, final, Activity,
commit, rollback, new-file removal, and permission restoration. An incomplete rollback surfaces
`transaction.indeterminate` with a recovery hint instead of hiding the failure.

Remaining work: audit less common checklist, handoff, session, Tool Run, actor identity, pack,
registry, trust, and upgrade families before unifying their specialized staging semantics.

Acceptance conditions retained for future families:

- every adopted mutation identifies its complete write set;
- injected failure tests cover early, middle, and final writes;
- rollback restores existing contents and permissions and removes newly created files;
- event streams and the Activity Ledger cannot advance without the domain record;
- validation succeeds after a rolled-back failure;
- documentation states which operations have the guarantee.

## Priority 2: continue extracting mutation handlers — first family delivered in 0.8

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

`WorkLifecycleHandlers` now provides the declarative registry for `criterion.satisfy`,
`artifact.add`, and `evidence.add`. It receives resolved immutable context and explicit callbacks,
and its unit tests run without a Workspace or unrelated subsystem. `AgoraWorkspace` remains the
compatibility facade. Delegation, actor identity, Tool Run, session, pack, and registry handlers
remain future incremental extractions.

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

## Priority 3: stable operational error model — delivered in 0.8

Application error schema v2 now carries the stable code, human message, category, retryability,
optional durable path, recovery hint, and redacted structured details. Compatibility subclasses keep
earlier public errors viable while new consumers can use provider-neutral families.

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

## Priority 4: explicit budget amendments — delivered in 0.8

Delegation usage is append-only and bounded by inherited work budgets, but legitimate capacity
changes need an explicit lifecycle operation rather than manual Markdown editing.

An amendment should bind:

- parent and child work identities;
- previous and proposed integer limits;
- accountable actor and role authority;
- reason and optional evidence references;
- signed action preconditions when authentication is required;
- an append-only amendment history.

Limits are never silently reduced below already recorded usage or increased by a child actor without
parent authority. Prepare/apply binds the current child and parent budgets, sibling allocations,
usage, actor key, evidence, reason, and timestamps. The applied record is append-only and the current
limit, event, and Activity update share one transaction.

## Priority 5: optional live integration smoke tests — Jira baseline delivered in 0.8

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

`tests/test_jira_live.py` implements the safe create-only baseline. It is skipped unless
`AGORA_RUN_JIRA_LIVE=1`, `AGORA_JIRA_LIVE_PROJECT`,
`AGORA_JIRA_LIVE_CONFIRMED_NONPRODUCTION=1`, and `acli` are present. The write is first materialized
as a prepared bounded Tool Run and launched separately. Deletion is intentionally absent because the
reviewed neutral contract does not expose it; the test reports the created key for manual archival.
Read, comment, transition, and post-transition verification remain the next live-only expansion.

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
