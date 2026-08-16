# Governed handoffs

Agora changes responsibility by transferring a role assignment, not by rewriting an actor. This
preserves a stable work identity while execution moves between a human, AI agent, service,
automation, or swarm.

## Why assignment changes instead of actor kind

An actor is an accountable identity with a kind and capabilities. Changing a historical actor from
`human` to `ai-agent` would make prior events ambiguous. A handoff therefore:

1. Keeps the outgoing and incoming actors distinct.
2. Validates the incoming actor against the same role contract.
3. Replaces only the role's current assignment.
4. Persists who authorized the transfer and why.
5. Leaves work state, artifacts, evidence, approvals, sessions, and tool runs unchanged.

The result behaves like responsibility changing form while attribution remains truthful.

## Authorization

Method Pack roles use two actions:

| Action | Authority |
| --- | --- |
| `handoff.create` | Transfer the role currently held by the authorizing actor |
| `handoff.manage` | Transfer another role as an assigned governance actor |

Bundled Scrum lets each role initiate its own handoff. The Scrum Master can manage other role
handoffs. Bundled Kanban gives the equivalent management authority to the Flow Manager. Custom
Method Packs choose their own policy.

The incoming actor must satisfy all `required-capabilities` and appear in `allowed-actor-kinds` for
the role. Authority does not bypass compatibility.

`agora swarm assign` and signed `swarm.assign` only fill vacant roles. They reject an occupied role
even when the proposed actor is unchanged. Use a handoff for every replacement so the outgoing
identity and reason cannot disappear from history.

When the receiver is linked through `represented-swarm`, Agora also checks child readiness, graph
cycles, and project delegation depth before completing the handoff.

A role with an active Approval Delegation cannot be handed off. Consume or revoke the scoped
authority first so the outgoing actor does not leave behind a live approval grant. See
[Approval Delegation](approval-delegation.md).

## Self-initiated handoff

Assume `human-developer` currently holds the Developer role and `ai-developer` is a compatible
registered actor:

```bash
agora swarm handoff \
  --id human-to-ai \
  --swarm payment-delivery \
  --role developer \
  --from human-developer \
  --to ai-developer \
  --by human-developer \
  --reason "The reviewed plan is ready for autonomous implementation" \
  --work idempotency
```

The outgoing actor uses `handoff.create` from the Developer role. It loses Developer authority as
soon as the command succeeds. The incoming AI actor may then start a session or perform the next
allowed transition:

```bash
agora start --id ai-implementation --actor ai-developer \
  --swarm payment-delivery --work idempotency
```

Previously prepared human sessions remain historical records; they do not grant current role
authority. New sessions list the swarm manifest, events, and prior handoff records as required
reading so the receiver inherits durable context rather than hidden conversation history.

## Governance-managed handoff

A governance actor can transfer another role when its own assigned role grants `handoff.manage`:

```bash
agora swarm handoff \
  --id ai-to-swarm \
  --swarm payment-delivery \
  --role developer \
  --from ai-developer \
  --to delivery-swarm \
  --by scrum-master \
  --reason "Parallel specialists are required for implementation and verification" \
  --work idempotency
```

This does not make the Scrum Master a Developer. It authorizes a change to the Developer assignment.

## Durable record

Each successful transfer creates:

```text
.agora/swarms/payment-delivery/handoffs/ai-to-swarm/
  HANDOFF.md
```

The front matter records swarm, role, outgoing actor, incoming actor, authorizer, optional work, and
timestamp. The body records the reason. Agora also appends `swarm.role-handed-off` and, when work is
selected, `work.role-handed-off` events.

`SWARM.md` shows the current assignment. The handoff files and events show how it arrived there.

## Rejected handoffs

Agora rejects a transfer when:

- The swarm is still forming, completed, or cancelled.
- The stated outgoing actor is not the current role holder.
- The incoming actor is the same actor or is incompatible with the role.
- The authorizer is not assigned to the swarm.
- A self-transfer lacks `handoff.create`.
- A third-party transfer lacks `handoff.manage`.
- The optional work item does not belong to the swarm.

Run the [handoff sample](../../samples/handoffs/README.md) to inspect a human-to-AI-to-swarm sequence.
