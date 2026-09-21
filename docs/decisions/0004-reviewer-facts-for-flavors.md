# ADR 0004: Reviewer facts for flavor projections

- Status: Proposed
- Date: 2026-09-21
- Related: Agora #60 (flavor projection inputs), #54 (session provenance), #55 (flavor projection boundary); Agora AI-SDLC independent-review policy

## Context

A flavor that governs independent review (for example the AI-SDLC `independent-review` profiles) must decide,
for an exact artifact revision, whether the review was independent of the producer. That decision needs
facts that only Core can attest:

1. the artifact revision: kind, id, content digest and an ordering of revisions;
2. who produced it and under which runtime, provider and model (Session provenance from #54);
3. who reviewed that same revision, whether the reviewer is human or AI, the verdict, and the reviewer's
   own runtime, provider and model;
4. that a later change to the artifact makes an earlier review stale.

Today Core records these only partly:

| Need | Core 0.9 state |
| --- | --- |
| Artifact revision | `ArtifactSummary` has `kind`, `uri`, `produced_by`, `timestamp` and an **optional** `content_sha256`. No revision number. |
| Review of a revision | Approvals are role-scoped rows (`role`, `actor`, `note`, `timestamp`); they name no artifact. Gate decisions bind evidence content digests, but a decision is not a review. |
| Binding to content | **Evidence already binds artifact content digests**: `EvidenceSummary.artifact_references` plus `artifact_content_sha256`, with `produced_by` and `result`. |
| Producer/reviewer provenance | Sessions carry provenance (#54), but neither artifact nor evidence records name a Session. |
| Actor kind (human or AI) | `ActorSummary.kind` exists but is not part of the flavor projection context. |

Without the missing links a flavor can only guess (for example, pair every quality-reviewer approval with every
artifact). A guessed separation decision is worse than none: it can report independence that never existed.

## Decision (proposed)

Extend Core minimally and keep Core policy-free. Core records and exposes reviewer facts; flavors evaluate them.

1. **A review is evidence.** A review of an artifact revision is an ordinary evidence record whose
   `artifact_references` name the reviewed artifact and whose stored `artifact_content_sha256` pins the exact
   revision. `result` is `success` (approving) or `failure` (not approving). The evidence `type` is a flavor
   convention (AI-SDLC uses `review`); Core does not interpret it. No new record type is introduced.
2. **Optional Session links.** `AddArtifactInput` and `AddEvidenceInput` (and their prepared, signed
   forms) gain an optional `session_id`. When set, Core validates that the Session exists, belongs to the same
   work, and that its executor equals the recording actor. The link is bound into the signed authorization
   payload only when present, so existing signatures are unaffected.
3. **DTO additions, additive.** `ArtifactSummary` and `EvidenceSummary` expose `session_id` (`null` for legacy
   records). Their schema ids are unchanged; precedent is `SessionSummary.retry_of` and `provenance`.
4. **Actors in the projection context.** `FlavorProjectionContext` gains `actors`: the `ActorSummary` records
   for every actor referenced by the work's artifacts, evidence, approvals and sessions, so a flavor can read
   the human/AI kind without listing the whole project.
5. **Revision order is derived, not stored.** For one `(kind, uri)`, a revision is the n-th registration with a
   distinct `content_sha256`, ordered by timestamp. A registration without a digest has no revision identity.
   Core exposes the ordered registrations already; the numbering rule is documented, not persisted.
6. **Fail closed on missing facts.** A flavor treats a missing digest, missing Session link or missing actor as
   `unavailable` for that artifact. Core never fabricates a link.

## Alternatives considered

- **A. Add `artifact_uri` and digest to approvals.** Rejected: approvals authorize transitions by role and are
  consumed by gates; overloading them changes gate semantics, delegation and signed-approval payloads.
- **B. New `review` record type with its own register, DTO, CLI, lifecycle action and role capability.**
  Rejected for now: it duplicates what evidence already provides (content-bound, attributable, append-only,
  signed action, gate-consumable) and adds a permission surface. Revisit if reviews need fields evidence
  cannot carry (for example threaded comments).
- **C. Flavor reconstructs reviews from approvals plus sessions.** Rejected: approvals are not artifact-scoped;
  the result is an approximation presented as a policy decision.
- **D. Core evaluates separation.** Rejected: separation profiles are flavor policy (actor, runtime, provider,
  human-final, minimum trust); Core stays method-neutral (ADR 0003).

## Consequences

- Legacy projects keep working. Records written before this change have no Session link; a flavor reports
  separation `unavailable` for them instead of guessing.
- A review becomes stale automatically: changing the artifact changes its digest, a new revision appears, and
  the earlier evidence no longer matches it.
- The same evidence can feed Core gates (`required-evidence-types`) and flavor separation without two sources
  of truth.
- The recording actor and the reviewing Session must be the same executor, so a reviewer cannot attach another
  runtime's provenance to its own review.
- Trust in provenance is still bounded by what Core records: Session bases are `declared` unless a reviewed
  runtime adapter supplies observations (#54). A flavor that demands `observed` provenance will block until
  that exists; this ADR does not change that.

## Verification plan

Core: link validation (unknown, cross-work and foreign-executor Sessions rejected), signed payload unchanged
when absent and bound when present, legacy records load with `session_id: null`, DTO round trip, context
`actors` limited to referenced actors, concurrent-edit behavior unchanged.
Flavor: an evaluator that consumes only these DTOs reproduces the published `independent-review` decisions
for the same producer/reviewer combinations as the existing policy tests, and reports `unavailable` for any
missing fact.

## Open questions

1. Is evidence the right carrier for reviews, or should reviews get their own record (alternative B)?
2. Should Core require `content_sha256` for artifacts recorded with a Session link, so a linked artifact always
   has a revision identity?
3. Should `actors` in the context be limited to referenced actors (proposed) or include the whole roster?
