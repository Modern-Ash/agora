# Interruptions and cancellation

Agora separates a work item's method state from its operational status. The method state describes
where work is in a custom lifecycle, such as `specified`, `implementing`, or `verifying`. The
operational status describes whether that lifecycle may currently move:

| Status | Meaning |
| --- | --- |
| `active` | Authorized actors may mutate and transition the work |
| `blocked` | The lifecycle state is preserved, but work mutations are suspended |
| `cancelled` | The item is closed without pretending that it reached the method's terminal state |

This distinction is process-agnostic. Scrum, Kanban, and custom Method Packs keep their own states
while sharing the same interruption contract.

## Block and resume work

Use a non-empty reason for every operational status change:

```bash
agora work block \
  --swarm payments \
  --work payment-api \
  --by delivery \
  --reason "The upstream identity contract is unavailable"

agora work list --swarm payments --operational-status blocked
agora work status-changes --swarm payments --work payment-api

agora work resume \
  --swarm payments \
  --work payment-api \
  --by facilitator \
  --reason "The identity contract is now published"
```

Blocking preserves the method state, criteria, artifacts, evidence, and approvals. While work is
blocked, Agora rejects transitions, criterion updates, artifacts, evidence, approvals, sessions,
tool invocations, new child delegations, delegation acceptance into that parent, and result
collection into it. Resume returns the item to `active`; it does not advance the method lifecycle.

A swarm is derived as `blocked` when all of its remaining nonterminal work is blocked. If another
active item can proceed, the swarm remains `ready` or `running`, while `agora status` still lists the
blocked item for attention.

## Cancel work

Cancellation is an explicit product or governance decision:

```bash
agora work cancel \
  --swarm payments \
  --work payment-api \
  --by owner \
  --reason "The product objective no longer requires this endpoint"
```

Cancellation is allowed from `active` or `blocked`. It preserves the current method state and every
record already produced. Open child delegations must be rejected or cancelled first; Agora does not
silently cascade a work decision across separately attributed contracts. Cancelled work cannot be
resumed or mutated. A swarm becomes `cancelled` when all its work is cancelled; it becomes
`completed` when every item is either terminal under its Method Pack or cancelled and at least one
item completed normally.

Completed work cannot be blocked, resumed, or cancelled. Completion means its gate already passed;
changing that decision requires a new work item or a custom lifecycle transition designed before
completion.

## Interrupt delegation

Delegations support a related but independent lifecycle:

```text
proposed -> accepted -> collected
    |          |
    +-> blocked <-+
    |          |
    +-> rejected  +-> cancelled
    +----------------> cancelled
```

Block and resume are parent governance actions. Resume returns to the exact prior state, either
`proposed` or `accepted`:

```bash
agora delegation block \
  --delegation specialist-task \
  --by facilitator \
  --reason "Clarify the child result contract"

agora delegation resume \
  --delegation specialist-task \
  --by facilitator \
  --reason "The result contract is now unambiguous"
```

The child may reject only a `proposed` delegation:

```bash
agora delegation reject \
  --delegation specialist-task \
  --by child-owner \
  --reason "The child swarm cannot satisfy the requested boundary"
```

The parent may cancel a `proposed`, `accepted`, or `blocked` delegation:

```bash
agora delegation cancel \
  --delegation specialist-task \
  --by parent-owner \
  --reason "The parent no longer needs the delegated result"
```

Cancelling an accepted delegation does not cancel or delete its child work. The child swarm owns
that record and must independently complete, block, or cancel it under its own assignments and
Method Pack. This prevents parent authority from silently rewriting child state.

Inspect the complete sequence with:

```bash
agora delegation status-changes --delegation specialist-task
agora delegation list --status blocked
agora delegation list --status rejected
agora delegation list --status cancelled
```

## Durable records

Every change writes an attributed Markdown record with a monotonic sequence, source status, target
status, action, actor, timestamp, and reason:

```text
.agora/swarms/payments/work/payment-api/
  WORK.md
  status-changes/
    change-.../STATUS.md

.agora/delegations/specialist-task/
  DELEGATION.md
  status-changes/
    change-.../STATUS.md
```

`WORK.md` or `DELEGATION.md` remains the current-state projection. The nested `STATUS.md` files and
event logs preserve how that state was reached. Git then supplies review, synchronization, and
repository history without making the LLM conversation authoritative.

## Method Pack authority

Custom Method Packs grant interruption actions exactly like other capabilities:

| Action | Typical authority |
| --- | --- |
| `work.block`, `work.resume` | Delivery role or flow facilitator |
| `work.cancel` | Product or service owner |
| `delegation.block`, `delegation.resume` | Parent flow facilitator |
| `delegation.reject` | Child owner |
| `delegation.cancel` | Parent owner |

The bundled Spec-Driven, Scrum, and Kanban packs provide these defaults, but the core does not attach
them to role names. A custom pack may distribute authority differently by editing `allowed-actions`.

Run `agora validate` after manual edits. Validation checks current status attribution, legal status
edges, sequence continuity, actor references, derived swarm status, and agreement between the latest
history entry and the current record.

Run the [interruption sample](../../samples/interruptions/README.md) for an executable work and
delegation flow.
