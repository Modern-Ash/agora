# Recursive swarms

An Agora swarm can participate in another swarm through a linked project actor. The parent sees one
accountable composite actor, while the represented child keeps its own objective, method, roles,
assignments, work, events, and handoffs.

## Configure the depth limit

Delegation depth is the number of linked swarm edges in the longest chain. Configure a user default:

```bash
agora configure \
  --integration generic \
  --default-method scrum \
  --max-delegation-depth 2
```

Or choose a value for one new project:

```bash
agora init --max-delegation-depth 1
```

The value is persisted as `max-delegation-depth` in user and project configuration. The default is
`3`; `0` disables linked swarm delegation while retaining ordinary human, AI, service, automation,
and unlinked composite actors.

## Form the child first

Create and fully assign the child swarm before it receives responsibility in a parent:

```bash
agora swarm create \
  --id payment-specialists \
  --objective "Implement and validate payment internals"

agora swarm assign --swarm payment-specialists --role product-owner --actor owner
agora swarm assign --swarm payment-specialists --role scrum-master --actor facilitator
agora swarm assign --swarm payment-specialists --role developer --actor specialist
```

The child must be `ready` or `running`. A forming, blocked, completed, or cancelled child cannot act
through a parent role.

## Register the linked actor

Register one project-scoped swarm actor that represents the child:

```bash
agora actor add \
  --id payment-specialist-swarm \
  --name "Payment Specialist Swarm" \
  --kind swarm \
  --capability implementation \
  --represented-swarm payment-specialists
```

`--represented-swarm` is valid only with `--kind swarm` and project scope. The actor's capabilities
must still satisfy the role it receives; child membership does not create implicit capabilities.

An actor whose kind is `swarm` and has no `represented-swarm` remains an opaque composite identity.
This supports an external or independently governed team without adding a local graph edge.

## Assign the child to a parent

Create the parent and use the linked actor like any other compatible participant:

```bash
agora swarm create \
  --id payment-delivery \
  --objective "Deliver the payment capability"

agora swarm assign --swarm payment-delivery --role product-owner --actor owner
agora swarm assign --swarm payment-delivery --role scrum-master --actor facilitator
agora swarm assign \
  --swarm payment-delivery \
  --role developer \
  --actor payment-specialist-swarm
```

Agora evaluates the complete project graph before persisting the assignment. The same checks apply
when a linked swarm actor receives a role through `agora swarm handoff`.

## Enforced invariants

Agora rejects a recursive assignment when:

- The referenced child does not exist locally.
- The child is not `ready` or `running`.
- The resulting graph contains a direct or indirect cycle.
- Any chain in the project exceeds `max-delegation-depth`.
- The linked actor lacks capabilities or has a kind disallowed by the target role.

Depth is checked globally, not only below the modified parent. Adding a child can therefore be
rejected when it would cause an existing ancestor chain to exceed the project limit.

## Execution and context

Before every lifecycle action, tool invocation, or session start, Agora confirms that the complete
represented descendant hierarchy remains operational. Events in the parent attribute the action to
the linked actor, whose `represented-swarm` field provides the durable connection to the child.

An execution session for the linked actor includes `SWARM.md`, events, and handoff records for the
complete delegated descendant hierarchy as required reading alongside the parent context:

```bash
agora start \
  --id delegated-implementation \
  --actor payment-specialist-swarm \
  --swarm payment-delivery \
  --work payment-api
```

Linked swarms establish governance and traceability. Agora can explicitly propose, accept, and
collect bounded child work through the [delegated work protocol](delegated-work.md). Same-swarm
child contracts use [work decomposition](work-decomposition.md). Cross-swarm limits use
[delegation budgets](delegation-budgets.md). [Delegated artifact
promotion](delegated-artifacts.md) can expose promised child artifact kinds as typed parent
references without copying provider-owned bytes.

Run the [recursive swarm sample](../../samples/recursive-swarms/README.md) for an executable depth
limit example.
