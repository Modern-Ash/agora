# Signed lifecycle actions

Agora can require an authenticated actor to authorize a lifecycle mutation before it changes the
current work projection. The supported mutations are `work.transition`, `work.block`, `work.resume`,
`work.cancel`, `work.create`, `criterion.satisfy`, `artifact.add`, `evidence.add`, `approval.add`,
`handoff.create`, and the complete delegation lifecycle. Their durable intents live at
`.agora/actions/<id>/ACTION.md`, separate from the resulting domain records.

This boundary proves that the configured actor key authorized one exact mutation against one exact
work state. It does not replace Method Pack permissions, transition edges, WIP limits, gates, Git
review, or operating-system identity.

## Prepare work and material records

An authenticated Product Owner can bind the complete initial work definition before it exists:

```bash
agora work create-prepare \
  --action-id create-payment-retry \
  --swarm payments \
  --id payment-retry \
  --title "Retry failed payments" \
  --criterion verified:"The retry has durable evidence" \
  --required-artifact implementation \
  --by authenticated-owner
```

The action work reference is the future work id. Its precondition covers `SWARM.md`; apply rechecks
swarm readiness, assignment, `work.create` authority, Method Pack availability, criterion ids, and
path availability before writing the ordinary work documents.

Authenticated participants prepare criteria, artifacts, and evidence against an existing work
projection:

```bash
agora work criterion-satisfy-prepare --id satisfy-payment-retry \
  --swarm payments --work payment-retry --criterion verified \
  --by authenticated-owner

agora artifact prepare --id add-payment-implementation \
  --swarm payments --work payment-retry --kind implementation \
  --uri repo://payments/retry.md --by authenticated-developer

agora evidence prepare --id record-payment-review \
  --swarm payments --work payment-retry --type review --result success \
  --artifact repo://payments/retry.md --by authenticated-reviewer
```

These actions bind the criterion id, artifact kind and URI, or evidence type, result, and artifact
references. Their precondition covers `WORK.md`, `approvals.md`, `artifacts.md`, and `evidence.md`.
Apply rechecks Method Pack authority and work mutability before updating the same Markdown records
used by unauthenticated actors.

## Prepare an agent session context

Authenticated actors authorize context materialization before authorizing runtime launch:

```bash
agora session prepare --id prepare-payment-session \
  --session payment-session --actor authenticated-developer \
  --swarm payments --work payment-retry --runner "company-agent run"
```

`session.prepare` binds the session id and runner. Its precondition is the prospective
`CONTEXT.md` digest, compiled from the current project, Method Pack, role, swarm, work, delegation,
handoff, and tool records. Applying the signed action rerenders those inputs, rejects drift, writes
the session files, and links `SESSION.md` back to the action. Runtime execution remains a separate
signed `session authorization` and `session launch` boundary.

## Prepare a transition

Create the work and assign the actor normally, then prepare rather than immediately apply its edge:

```bash
agora work transition-prepare \
  --id begin-payment-implementation \
  --swarm payments \
  --work payment-retry \
  --to implementing \
  --by authenticated-developer
```

Preparation checks the current role assignment, `work.transition` authority, Method Pack edge, WIP
limit, work operational status, and gate. It writes a `prepared` action containing:

- The action id and `work.transition` kind.
- The canonical actor, swarm, and optional work references.
- The target state in a structured parameter map.
- A SHA-256 precondition over `WORK.md`, `approvals.md`, `artifacts.md`, and `evidence.md`.
- Its creation time and empty authentication evidence fields.

No work state changes during preparation.

## Prepare an approval

An authenticated actor assigned to the approval role prepares the decision and note together:

```bash
agora approval prepare \
  --id accept-payment-retry \
  --swarm payments \
  --work payment-retry \
  --role product-owner \
  --by authenticated-owner \
  --note "Accepted for release"
```

The structured parameters bind both `role` and `note` to the signature. Agora verifies that the
actor still holds that exact role and retains `approval.add` authority when the action is applied.
The ordinary `approvals.md` row and `approval.added` event remain the resulting domain records.

## Prepare a handoff

An authenticated role holder or governance actor can prepare an identity-preserving role transfer:

```bash
agora swarm handoff-prepare \
  --id handoff-payment-work \
  --swarm payments \
  --role developer \
  --from authenticated-developer \
  --to human-developer \
  --by authenticated-developer \
  --reason "Human judgment is required" \
  --work payment-retry
```

Handoff parameters bind the role, canonical outgoing and incoming actor references, authorizer, and
reason. Its precondition covers `SWARM.md`, where assignments live, plus the work policy digest when
`--work` is present. Agora rechecks actor compatibility, represented-swarm constraints, current
assignment, and either `handoff.create` or `handoff.manage` authority before changing the role.

## Prepare a work interruption

Blocking, resuming, and cancelling work use action-specific prepare commands:

```bash
agora work block-prepare --id pause-payment-retry \
  --swarm payments --work payment-retry --by authenticated-developer \
  --reason "Dependency is unavailable"

agora work resume-prepare --id resume-payment-retry \
  --swarm payments --work payment-retry --by authenticated-developer \
  --reason "Dependency recovered"

agora work cancel-prepare --id cancel-payment-retry \
  --swarm payments --work payment-retry --by authenticated-owner \
  --reason "Outcome is no longer required"
```

The action kind binds the target operational status and the payload binds its non-empty reason.
Applying it rechecks the current operational state, role authority, terminal Method state, and open
delegations. A successful action writes the ordinary `STATUS.md`, updates `WORK.md`, and appends the
work event. The action id is also the Status Change id, enabling exact offline cross-validation.

## Prepare a delegation decision

Delegation blocking, resumption, rejection, and cancellation use the same signed status pattern:

```bash
agora delegation block-prepare --id pause-specialist-task \
  --delegation specialist-task --by authenticated-facilitator \
  --reason "Clarify the delegated boundary"

agora delegation resume-prepare --id resume-specialist-task \
  --delegation specialist-task --by authenticated-facilitator \
  --reason "The delegated boundary is explicit"

agora delegation reject-prepare --id reject-specialist-task \
  --delegation specialist-task --by authenticated-child-owner \
  --reason "The child cannot meet the contract"

agora delegation cancel-prepare --id cancel-specialist-task \
  --delegation specialist-task --by authenticated-parent-owner \
  --reason "The parent no longer needs the result"
```

The canonical action uses the delegation's parent swarm/work as durable context, even when the child
authorizes rejection. Its precondition covers both `DELEGATION.md` and the parent work policy files.
Apply rechecks current contract state and the appropriate parent or child authority, then links the
applied action to the exact delegation `STATUS.md`.

## Prepare delegation creation, acceptance, and collection

An authenticated linked swarm actor signs the complete proposed contract:

```bash
agora delegation create-prepare \
  --action-id propose-specialist-task \
  --id specialist-task \
  --swarm delivery \
  --work parent-slice \
  --to-actor authenticated-specialist-swarm \
  --child-work child-slice \
  --title "Produce the specialist result" \
  --criterion usable:"The result can be integrated" \
  --required-artifact child-result \
  --result-kind delegated-result \
  --by authenticated-specialist-swarm
```

The parameter map binds the delegation id, child actor and work, title, description, criteria,
required artifacts, and result kind. Its precondition covers the parent work, both swarm manifests,
and linked actor record. Applying it rechecks delegation depth, assignments, child readiness, role
authority, and identifier availability before writing `DELEGATION.md`.

An authenticated child participant then signs acceptance, and the authenticated linked swarm actor
signs collection after the child work reaches its terminal state:

```bash
agora delegation accept-prepare --id accept-specialist-task \
  --delegation specialist-task --by authenticated-child-owner

agora delegation collect-prepare --id collect-specialist-task \
  --delegation specialist-task --by authenticated-specialist-swarm
```

Acceptance binds the current delegation, parent work, and child swarm before creating linked child
work. Collection additionally binds the terminal child work policy files before adding the result
artifact and evidence to the parent. Their action ids become the corresponding `STATUS.md` ids.

## Export and sign the authorization

Export the canonical JSON bytes:

```bash
agora action authorization \
  --action begin-payment-implementation \
  --output /tmp/begin-payment-implementation.authorization.json
```

Sign those bytes outside Agora with the actor's Ed25519 private key:

```bash
openssl pkeyutl \
  -sign \
  -inkey developer-private.pem \
  -rawin \
  -in /tmp/begin-payment-implementation.authorization.json \
  -out /tmp/begin-payment-implementation.sig
```

The payload binds the action kind, actor, swarm, work, parameters, precondition digest, and creation
time. A signature copied from another action cannot authorize this action.

## Apply the action

Apply the prepared intent with its raw 64-byte Ed25519 signature:

```bash
agora action apply \
  --action begin-payment-implementation \
  --signature /tmp/begin-payment-implementation.sig
```

Agora reloads current project state before mutation. It rejects a changed work precondition, revoked
or rotated signer, changed assignment, lost permission, invalid transition, exceeded WIP limit, or
failed gate. Only after those checks and signature verification does it update `WORK.md`, append the
ordinary work transition event, and mark `ACTION.md` as `applied`.

Actors registered with `--require-authentication` cannot use immediate lifecycle commands covered by
this guide. Actors without that requirement retain the immediate commands for compatibility, and
may also use a prepared action without a signature when a durable intent is useful.

## Audit pending and applied actions

```bash
agora action list
agora action list --status prepared
agora action list --status applied
agora validate
```

Applied actions retain the signing public key, fingerprint, canonical payload digest, and signature,
so historical evidence remains independently verifiable after key rotation or revocation. Validation
reports a changed precondition on a still-prepared action as `lifecycle-action.precondition-stale`.
The stale intent remains on disk for audit and cannot be applied.

## Extensibility boundary

`agora/lifecycle-action/v1` separates the common authorization envelope from the action-specific
parameter map. The current kernel accepts work transitions and interruptions, approvals, handoffs,
work creation and material records, session preparation, and every delegation lifecycle mutation.
Administrative mutations remain future action kinds and must keep their existing domain validation
as the source of authority when added.
