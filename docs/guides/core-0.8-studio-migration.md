# Migrate Studio consumers from Core 0.7 to 0.8

Core 0.8 is an intentional 0.x minor contract break. Studio remains an HTTP and browser adapter: it
must call these Application Services, never parse or edit `.agora/`, invoke the CLI, calculate a
precondition digest, or reproduce lifecycle policy.

## Compatibility matrix

| Studio consumer | Core range | Status |
| --- | --- | --- |
| A consumer asserting Core 0.7 gate/read schemas | `>=0.7,<0.8` | Compatible with 0.7 only |
| A migrated consumer asserting the schemas below | `>=0.8,<0.9` | Compatible with 0.8 |
| A consumer accepting arbitrary Core 0.x minors | Unbounded | Unsupported; pin one minor |

Core does not claim that an already released Studio version implements this migration. Studio
should fail startup with a version-incompatible response before serving mutations when its expected
minor and installed Core minor differ.

## Schema changes

| Contract | Core 0.7 | Core 0.8 |
| --- | --- | --- |
| Project overview | v1 | v2 |
| Method summary | v1 | v2 |
| Work item detail | v2 | v3 |
| Artifact / evidence summary | v2 | v3 |
| Lifecycle / traceability | v2 / v1 | v3 / v2 |
| Gate option / options / decision | v2 | v3 |
| Approve gate command | v3 | v4 |
| Approve authorization | v3 | v4 |
| Prepared gate decision | v2 | v3 |
| Work control projection | v2 | v3 |
| Operational error | v1 | v2 |

Budget amendment command, preparation, authorization, and projection begin at v1. Historical
fixtures stay under `tests/contracts/`; `core-0.8-application-contracts.json` is the portable 0.8
consumer fixture.

## Gate confirmation flow

1. Submit the unsigned, digest-free v4 command to `prepare_gate_decision()`.
2. Render Core's canonical reason, evidence references, actor, role, and expected transition.
3. If authentication is required, sign the exact returned authorization payload externally.
4. Confirm with the returned `precondition_digest`, `prepared_at`, `expires_at`, and
   `evidence_content_sha256` and `actor_fingerprint` unchanged.
5. Wait for the durable Core projection before refreshing the UI. Do not update optimistically.

`prepared_at` is always required on confirmation. `expires_at` is `null` only when expiration was
explicitly disabled. Treat the exact expiration instant as expired.

The digest map is exact, not the complete set advertised by the gate option. If an option exposes
three eligible references and the actor selects one, preparation returns exactly one map entry. A
selected reference without content identity remains present with a `null` value. Never remove that
key, send an empty map, add another eligible-but-unselected reference, hash the URI, or rewrite
`null`: all are stale confirmation material.

```python
from dataclasses import replace

from agora.application import AgoraCommandService, ApproveGateCommand

service = AgoraCommandService.from_path(project_root)
intent = ApproveGateCommand(
    project_identity="example-project",
    swarm_id="delivery",
    work_id="release",
    gate_id="completion",
    actor_id="owner",
    decision="approved",
    reason="Reviewed the selected audit evidence",
    expected_state="verifying",
    transition_target="completed",
    role_id="product-owner",
    evidence_references=("https://evidence.example.invalid/audit",),
)
prepared = service.prepare_gate_decision(intent)

# An authenticated actor signs prepared.authorization_payload externally here.
confirmation = replace(
    intent,
    reason=prepared.reason,
    evidence_references=prepared.evidence_references,
    evidence_content_sha256=prepared.evidence_content_sha256,
    actor_fingerprint=prepared.actor_fingerprint,
    precondition_digest=prepared.precondition_digest,
    prepared_at=prepared.prepared_at,
    expires_at=prepared.expires_at,
    authentication=None,  # supply exact Ed25519 material when required
)
durable = service.approve_gate(confirmation)
```

## Stale, expired, and evidence messages

Do not infer failure type from English text. Use error v2:

| Code | Recommended UI treatment |
| --- | --- |
| `command.preparation-expired` | “This review window expired. Prepare the decision again.” |
| `command.governed-material-stale` | “Governed material changed. Refresh and review again.” |
| `durable-state.concurrent-edit` | “Files or Git changed during the read. Retry.” |
| `gate.evidence-missing` | Show Core's typed evidence blockers; do not calculate them in Studio |
| `command.signature-invalid` | Ask the actor to sign the newly prepared payload |
| `transaction.commit-failed` | No decision was committed; preserve the form and allow a reviewed retry |
| `transaction.rollback-failed` | Restoration was verified, but rollback reported an error; require review before retry |
| `transaction.indeterminate` | Stop mutation controls and show the supplied recovery hint |

`details.stale_reason` may distinguish state, governed material, evidence, actor key, preparation,
or an external edit. Details are safe for structured display but remain untrusted text; render them
as text, never HTML.

For `transaction.indeterminate`, Studio must disable mutation controls until the operator reconciles
Git and runs `agora validate`. `transaction.rollback-failed` is different: Core verified the
original snapshots, but the reported rollback anomaly still warrants operator review. Studio must
not infer either case from an HTTP status or English message.

## External evidence

Artifact v3 exposes `content_sha256`; evidence v3 exposes `artifact_content_sha256` keyed by URI.
Core never downloads a remote URI. Studio may collect a producer-calculated digest, but the command
must pass it to Core as data and let Core validate and persist it. A gate option with
`content_addressed_evidence_required: true` and blocker
`gate.evidence-content-digest-missing` is not approvable. Never hide the blocker or substitute a URI
hash for a content hash.

The portable fixture `tests/contracts/core-0.8-application-contracts.json` intentionally contains a
gate option with more eligible evidence than the prepared command selects. Consumers should assert
that the prepared and confirmed maps equal the selected command map, not the option-wide map.

## Work Control reads

Projection v3 is assembled under the Core lock and an optimistic content read-set. Retry
`durable-state.concurrent-edit` according to its `retryable` flag with a short bounded delay. The
`snapshot_token` identifies the nested projection, not an authorization token and not a database
version. Studio may cache it or place it in a regenerable SQLite projection, but Markdown and Git
remain authoritative.

## Budget amendment UI

Use `prepare_budget_amendment()` and `amend_budget()` exactly like the gate prepare/apply boundary.
Show previous, proposed, consumed, and remaining amounts; parent and child identity; actor and role;
reason; evidence; and expiration. Never let the browser calculate authority or directly rewrite
`WORK.md`. The durable response and exact Activity entry are the success condition.
