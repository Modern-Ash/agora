# Delegation budgets

Delegation budgets bound what a child swarm may allocate again when work crosses a swarm boundary.
They are provider-neutral integer dimensions chosen by the team. Examples include `effort`,
`tokens`, `cost-cents`, `minutes`, or an organization-specific capacity unit.

Agora governs declared limits and propagation. It does not meter real token, cloud, financial, or
elapsed-time consumption. A runtime or reviewed adapter must produce that usage evidence when the
Method Pack requires it.

## Declare an allocation

Add one or more `--budget dimension=limit` arguments to a delegation proposal:

```bash
agora delegation create \
  --id specialist-task \
  --swarm delivery \
  --work parent-slice \
  --to-actor specialist-swarm \
  --child-work child-slice \
  --title "Produce the specialist result" \
  --budget effort=8 \
  --budget tokens=50000 \
  --by specialist-swarm
```

Dimensions are slugs and limits are nonnegative integers. They have no built-in conversion or
provider semantics. The exact map is persisted in `DELEGATION.md` as `budget-limits`.

When the child accepts, Agora copies the map to the child `WORK.md`. Any delegation created from
that work is then constrained by the inherited map.

## Propagation rules

`null` means that the work did not inherit a delegation limit. A root work item with no inherited
limit may establish any explicit child allocation.

An inherited map means:

- a child delegation cannot introduce a dimension absent from its parent work;
- sibling allocations are summed for every dimension;
- the sum cannot exceed the parent limit;
- an omitted dimension allocates zero of that dimension;
- `{}` permits no positive downstream allocation;
- rejected proposals release their reservation;
- accepted, collected, blocked, proposed, or cancelled contracts retain their reservation.

Cancellation retains the reservation because the child may already have consumed some authorized
capacity. Agora does not silently infer that capacity is reusable. A future explicit budget
amendment or release protocol can add that decision with its own evidence and approval requirements.

## Signed proposals

`delegation create-prepare` accepts the same repeated `--budget` arguments. The canonical
Lifecycle Action stores the complete map as a JSON parameter, so an external Ed25519 signature
binds the allocation alongside the child contract. Apply rechecks current sibling reservations and
the inherited parent limit before mutation.

## Validation

`agora validate` detects negative or malformed limits, unavailable dimensions, aggregate
overallocation, and a child work budget that differs from its accepted delegation. Existing
unbounded work remains compatible because missing `budget-limits` is read as `null`.

Run the [delegated work sample](../../samples/delegated-work/README.md) to inspect a signed budget
that is inherited by accepted child work.
