# Application Services contracts

Agora Core 0.6.0 exposes an in-process, provider-neutral boundary in `agora.application`. Agora CLI
and Studio API are adapters over this boundary. Studio must not invoke CLI commands or parse
`.agora/` records.

All response and query DTOs are frozen dataclasses. `to_dict()` returns JSON-compatible values and
`to_json()` emits a complete JSON document. Contracts never expose `pathlib.Path` or mutable
mappings. Every payload carries a `schema` field; a schema version changes when the shape or meaning
is incompatible.

## Read operations

| Operation | Result schema |
| --- | --- |
| `project_overview()` | `agora/application/project-overview/v1` |
| `list_actors()` | `agora/application/actor-summary/v1` |
| `list_swarms()` / `get_swarm()` | `agora/application/swarm-summary/v1` |
| `list_work_items()` | `agora/application/work-item-summary/v1` |
| `get_work_item()` | `agora/application/work-item-detail/v2` |
| `list_sessions()` / `get_session()` | `agora/application/session-summary/v1` |
| `get_method()` | `agora/application/method-summary/v1` |
| `lifecycle()` | `agora/application/lifecycle-projection/v2` |
| `artifacts()` | `agora/application/artifact-summary/v2` |
| `evidence()` | `agora/application/evidence-summary/v2` |
| `approvals()` | `agora/application/approval-summary/v2` |
| `activity()` | `agora/application/activity-entry/v1` |
| `work_traceability()` | `agora/application/traceability-summary/v1` |
| `specification_history()` | `agora/application/specification-summary/v1` |
| `specification_revision()` | `agora/application/specification-revision-detail/v1` |
| `gate_decision_options()` | `agora/application/gate-decision-options-projection/v1` |
| `work_control_projection()` | `agora/application/work-control-projection/v1` |

`WorkItemDetail v2` explicitly nests `ArtifactSummary v2`, `EvidenceSummary v2`, and
`ApprovalSummary v2`. Core 0.6 removes `WorkItemDetail v1` from its public surface rather than
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
typed blockers, and public authentication metadata. Rejection does not inherit evidence and
acceptance blockers that exist to authorize approval, while both decisions remain subject to
state, operational-status, authority, duplicate-decision, and final command revalidation.

`work_control_projection()` aggregates the work detail, lifecycle, materials, traceability,
specification history, and gate options behind one logical read. Core checks that the state-bearing
projections agree before returning it; Markdown and Git remain the source of truth.

## Governed command

`AgoraCommandService.approve_gate()` accepts
`agora/application/approve-gate-command/v2` and returns
`agora/application/gate-decision-projection/v1`. Core selects exactly one authorized role,
revalidates state, Method Pack, evidence, gate preconditions and optional authentication, then
persists the decision and Activity event in one transaction. The result contains the exact Activity
record emitted by that transaction; it never searches for a later matching event.

Command v2 binds `transition_target` and `role_id` in addition to the gate, actor, decision,
reason, expected state, and evidence. `prepare_gate_decision()` returns
`agora/application/prepared-gate-decision/v1`, including the canonical authorization payload,
SHA-256 digest, expected Ed25519 public identity, and state-bound freshness metadata. Core never
reads or returns a private key and never signs for an actor. A detached signature is verified over
the exact prepared payload; changing any command field invalidates it. Actors that do not require
authentication may continue to submit command v2 without authentication material.

Application errors serialize as `agora/application/error/v1`. Stable command codes are:

- `command.actor-unauthorized`;
- `command.gate-already-resolved`;
- `command.stale-precondition`;
- `command.evidence-missing`;
- `command.signature-required`;
- `command.persistence-failed`;
- `command.version-incompatible`;
- `command.project-identity-mismatch`;
- `command.invalid`.

Domain rule exceptions are translated by type. Human-readable wording is not part of error
classification.

## Planned Studio compatibility

| Agora Core | Contract level | Agora Studio expectation |
| --- | --- | --- |
| 0.4.x | Initial read and gate-decision services | Existing CLI-backed or transitional Studio integrations only |
| 0.5.x | Complete local read boundary with WorkItemDetail v1 | Agora Studio 0.2 pins `>=0.5,<0.6` |
| 0.6.x | WorkItemDetail v2, exact gate options, signing preparation, revision detail, aggregate control projection | Agora Studio 0.2 is not compatible; a later Studio release must adopt and assert these schemas |

This table describes the intended consumer boundary, not a claim that a released Studio version
already consumes every contract. During 0.x, consumers should pin a compatible Core minor version
and assert exact schema identifiers with the JSON fixtures under `tests/contracts/`.
