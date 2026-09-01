# Application Services contracts

Agora Core 0.8.0 exposes an in-process, provider-neutral boundary in `agora.application`. Agora CLI
and Studio API are adapters over this boundary. Studio must not invoke CLI commands or parse
`.agora/` records.

All response and query DTOs are frozen dataclasses. `to_dict()` returns JSON-compatible values and
`to_json()` emits a complete JSON document. Contracts never expose `pathlib.Path` or mutable
mappings. Every payload carries a `schema` field; a schema version changes when the shape or meaning
is incompatible.

## Engine observation contract

`EngineTraceEvent` exposes `agora/application/engine-trace-event/v1` for safe, incremental
observation of one Core operation:

| Field | Meaning |
| --- | --- |
| `operation_id` | Stable correlation id for one command execution |
| `sequence` | Monotonic event order within that operation |
| `phase` | Provider-neutral engine phase such as `run.select` or `tracker.reconcile` |
| `status` | `running`, `succeeded`, `blocked`, or `failed` observation state |
| `code` | Stable machine-oriented event code |
| `summary` | Bounded human-readable fact |
| `timestamp` | UTC event time |
| `references` | String-only durable ids and bounded context |

The CLI renders this DTO through `--trace compact`, `detailed`, or `jsonl` on `stderr`. It is an
ephemeral observation contract, not a mutation result or source of truth. Implementations must not
place provider output, prompts, credentials, environment secrets, or model reasoning in it. Durable
audit remains in the existing Markdown records and Activity Ledger.

## Read operations

| Operation | Result schema |
| --- | --- |
| `project_overview()` | `agora/application/project-overview/v2` |
| `list_actors()` | `agora/application/actor-summary/v1` |
| `list_swarms()` / `get_swarm()` | `agora/application/swarm-summary/v1` |
| `list_work_items()` | `agora/application/work-item-summary/v1` |
| `get_work_item()` | `agora/application/work-item-detail/v3` |
| `list_sessions()` / `get_session()` | `agora/application/session-summary/v1` |
| `get_method()` | `agora/application/method-summary/v2` |
| `lifecycle()` | `agora/application/lifecycle-projection/v3` |
| `artifacts()` | `agora/application/artifact-summary/v3` |
| `evidence()` | `agora/application/evidence-summary/v3` |
| `approvals()` | `agora/application/approval-summary/v2` |
| `activity()` | `agora/application/activity-entry/v1` |
| `work_traceability()` | `agora/application/traceability-summary/v2` |
| `specification_history()` | `agora/application/specification-summary/v1` |
| `specification_revision()` | `agora/application/specification-revision-detail/v1` |
| `gate_decision_options()` | `agora/application/gate-decision-options-projection/v3` |
| `work_inspection()` | `agora/application/work-inspection/v1` |
| `work_control_projection()` | `agora/application/work-control-projection/v3` |

`WorkItemDetail v2` explicitly nests `ArtifactSummary v2`, `EvidenceSummary v2`, and
`ApprovalSummary v2`. Core 0.6 removed `WorkItemDetail v1` from its public surface rather than
publishing two incompatible shapes under the same schema. This is an intentional 0.x minor
contract break; consumers that require v1 must remain on Core 0.5.x.

`LifecycleProjection` includes every Method Pack state, transition roles, gate policy, required
approval roles, typed blockers, and Core-calculated transition availability. Its legacy
`available_transitions` field retains the 0.4 source-state meaning for compatibility; consumers that
need executable availability use each `TransitionSummary.available` value.

Artifact, evidence, and approval v2 contracts expose their durable producer or actor and timestamp.
Material rows do not contain a durable Activity, session, or Tool Run identifier, so their
`activity` field is `null`; Core does not guess a relationship by matching text or timestamps.
`TraceabilitySummary.activity` supplies the exact work-scoped events and their durable
`session_id`, `tool_run_id`, and `source` references independently.

Artifact and evidence v3 additionally expose durable content identity. Core calculates
`content_sha256` for `repo://` artifacts and verifies an optional declared value. Producers may
declare a lowercase 64-character SHA-256 for any other URI; Core never downloads remote content.
Evidence captures the registered digest for each evidence-to-artifact reference. Informational
external evidence may retain `null` when its Method Pack permits it, while a gate with
`require-content-addressed-evidence: true` returns the explicit
`gate.evidence-content-digest-missing` blocker until every selected successful reference has an
immutable content identity. Full `git://` commit identifiers remain canonical content identity.

`specification_history()` is available only for one unambiguous registered `spec` artifact using a
safe `repo://` URI. Git reads are local, read-only, time-bounded, output-bounded, and argument-safe.
A working-tree revision is distinct from committed history. Unavailable history is a successful
projection with `available: false` and a reason; Markdown and Git remain authoritative.

`specification_revision()` accepts only a revision id returned for that registered specification.
It returns bounded content and a bounded diff for a commit or working-tree revision. Invalid SHAs,
missing history, binary content, timeouts, and unavailable revisions are explicit safe projections.
It never exposes an absolute path. Git arguments are fixed, shell execution is disabled, repository
paths are validated, and content is limited to 128 KiB and 2,000 lines per field.

`gate_decision_options()` returns every gate decision for the current state, not a preferred or
first option. Each option binds the transition target, gate, role, actor, decision, usable evidence,
typed blockers, content digests, and public authentication metadata. Option v3 preserves
`evidence_references_by_type`; when a gate requires named evidence types, approval references are
eligible only for those types and must cite at least one successful durable reference for every
required type. A successful reference from an unrelated type cannot satisfy the gate. Rejection
does not inherit evidence and acceptance blockers that exist to authorize approval, while both
decisions remain subject to state, operational-status, authority, duplicate-decision, and final
command revalidation.

`work_control_projection()` aggregates the work detail, lifecycle, materials, traceability,
specification history, and gate options. Projection v3 includes a deterministic `snapshot_token`
over every nested contract. It combines the project lock with SHA-256 fingerprints over the durable
read-set and local Git identity. Core retries at most three times when a direct editor changes the
material during assembly, then returns retryable `durable-state.concurrent-edit`; it never silently
returns a mixed snapshot. Filesystem writers can still race after the final fingerprint, so governed
mutations repeat their read-set check immediately before the shared transaction. Markdown and Git
remain the source of truth.

`work_inspection()` is the compact decision surface for an agent iteration. It returns the current
state and operational status, bounded transition options and blockers, assignment and approval
actors, criteria and material counts, required and missing artifacts, plus a deterministic
`snapshot_token`. It intentionally omits histories, artifact bodies, evidence detail, provider
output, prompts, credentials, and model reasoning. Lists, references, and free text have fixed
limits with explicit truncation metadata. Its consistency check fingerprints only records that can
change those fields, so unrelated Activity entries do not force a retry or invalidate the token.
Callers expand to the full control projection (`work inspect --full`) or targeted reads only when
the compact result exposes an ambiguity or the next action needs supporting detail.

## Governed command

`AgoraCommandService.approve_gate()` accepts
`agora/application/approve-gate-command/v4` and returns
`agora/application/gate-decision-projection/v3`. Core selects exactly one authorized role,
revalidates state, Method Pack, evidence, gate preconditions and optional authentication, then
persists the decision and Activity event in one transaction. The result contains the exact Activity
record emitted by that transaction; it never searches for a later matching event.

Command v4 requires the apply-time `precondition_digest`, Core-issued `prepared_at`, and optional
`expires_at`. Preparation returns an exact `evidence_content_sha256` map containing every selected
evidence reference, and only those references. Each selected reference has one entry; its value is
the lowercase content SHA-256 or explicit `null` when content identity is unavailable and policy
allows it. Confirmation must echo the complete map and actor fingerprint unchanged. An empty map,
missing key, additional key, changed digest, or digest changed to `null` returns
`command.governed-material-stale` with `details.stale_reason: evidence-changed`. Clients first
submit the command
without a digest to `prepare_gate_decision()`, which returns
`agora/application/prepared-gate-decision/v3`. Only Core calculates the digest. It covers project,
work and swarm identity; expected state; exact transition, gate, decision, role and current actor;
the current actor fingerprint; the active Method Pack; assignments; approvals; acceptance and
blockers; typed evidence and selected references; registered artifact content digests where
available; the specification digest; preparation window; and the exact calculated option. The
prepared authorization payload uses `agora/application/approve-gate-authorization/v4` and includes
that digest and both timestamps.

Core canonicalizes the reason by collapsing whitespace and canonicalizes evidence references by
trimming, dropping empty values, and retaining the first occurrence. Those exact values flow
through preparation, signing, validation, approval or rejection persistence, Activity, and the
returned projection. The apply path recalculates the precondition under the project mutation lock
immediately before the transaction. Any governed change, even when the work state is unchanged,
returns `command.stale-precondition` without decision writes. Core never reads or returns a private
key and never signs for an actor. Authenticated actors sign the exact prepared payload; unsigned
actors still use the same prepare/apply freshness protocol but omit authentication material.

The default preparation TTL is 900 seconds. Projects configure
`gate-decision-ttl-seconds`; a Method Pack may override it. An explicit zero disables expiration for
offline projects. Core uses its injected UTC clock and checks expiration under the mutation lock;
the exact `expires_at` instant is expired. Expiration returns
`command.preparation-expired`, distinct from governed material, evidence, actor-key, or work-state
changes. Re-preparation is always required after either outcome.

`prepare_budget_amendment()` and `amend_budget()` expose the explicit child-budget lifecycle
operation through `amend-budget-command/v1`, `prepared-budget-amendment/v1`,
`amend-budget-authorization/v1`, and `budget-amendment-projection/v1`. Parent Method Pack authority,
child relationship, current allocation, sibling allocation, consumed usage, optional successful
evidence, actor key, and preparation window are revalidated immediately before persistence. The
transaction updates the child's current limits, writes append-only
`budget-amendments/<id>/AMENDMENT.md`, and emits the exact work event and Activity entry. A child
role cannot self-authorize an increase, and no limit may fall below consumed usage.

Application errors serialize as `agora/application/error/v2` with `code`, `message`, `category`,
`retryable`, optional `durable_path`, optional `recovery_hint`, and safe structured `details`.
Credential, token, authorization, private-key, secret, and signature detail keys are redacted.
Stable provider-neutral families include:

- `durable-state.invalid`, `resource.not-found`, and `authority.denied`;
- `lifecycle.precondition-failed` and `gate.evidence-missing`;
- `command.governed-material-stale`, `command.preparation-expired`, and
  `command.signature-invalid`;
- `transaction.commit-failed`, `transaction.rollback-failed`, and
  `transaction.indeterminate`;
- `runtime.incompatible` and `provider.execution-failed`.

Transaction codes have evidence-based, non-overlapping semantics:

- `transaction.commit-failed`: commit failed and post-rollback verification proved that existence,
  content, permissions, and new-path cleanup match the original snapshots;
- `transaction.rollback-failed`: rollback reported an error, but that same verification still
  proved complete restoration;
- `transaction.indeterminate`: verification could not prove complete restoration. This is
  non-retryable until an operator follows the recovery hint.

The transaction snapshots the complete staged write-set before its first replacement, checks each
destination immediately before writing, and verifies the staged contents after commit. A detectable
external edit aborts as `durable-state.concurrent-edit` for reads or
`command.governed-material-stale` with `external-edit` for governed commands. These checks do not
claim operating-system or distributed isolation.

Compatibility subclasses retain the earlier 0.x read and command codes where existing callers use
them. Stale error details distinguish `state-changed`, `governed-material-changed`,
`preparation-expired`, `actor-key-changed`, `evidence-changed`, and `external-edit` where the Core
operation can determine that reason without guessing.

Domain rule exceptions are translated by type. Human-readable wording is not part of error
classification.

## Planned Studio compatibility

| Agora Core | Contract level | Agora Studio expectation |
| --- | --- | --- |
| 0.4.x | Initial read and gate-decision services | Existing CLI-backed or transitional Studio integrations only |
| 0.5.x | Complete local read boundary with WorkItemDetail v1 | Agora Studio 0.2 pins `>=0.5,<0.6` |
| 0.6.x | WorkItemDetail v2, exact gate options, signing preparation, revision detail, aggregate control projection | Agora Studio 0.2 is not compatible; a later Studio release must adopt and assert these schemas |
| 0.7.x | Governed-material freshness, typed gate evidence, canonical gate commands, atomic control snapshots | Consumers must prepare every gate decision and assert the v2/v3 schemas before applying it |
| 0.8.x | External content identity, expiring preparations, optimistic snapshots, stable error v2, and budget amendments | Consumers must send Core-issued timestamps on confirmation, handle stale separately from expired, and assert the v3/v4 schemas |

This table describes the intended consumer boundary, not a claim that a released Studio version
already consumes every contract. During 0.x, consumers should pin a compatible Core minor version
and assert exact schema identifiers with the JSON fixtures under `tests/contracts/`.
