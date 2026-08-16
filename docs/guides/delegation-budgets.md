# Delegation budgets

Delegation budgets bound what a child swarm may allocate again when work crosses a swarm boundary.
They are provider-neutral integer dimensions chosen by the team. Examples include `effort`,
`tokens`, `cost-cents`, `minutes`, or an organization-specific capacity unit.

Agora governs declared limits, propagation, and an append-only usage ledger. It does not measure
real token, cloud, financial, or elapsed-time consumption itself. A runtime or reviewed adapter
produces the measurement and an external evidence reference; Agora attributes, accumulates, and
validates the submitted amounts.

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

## Record observed usage

Record one or more positive integer amounts produced by a runtime or reviewed adapter:

```bash
agora usage add \
  --id model-call-202 \
  --swarm specialists \
  --work child-slice \
  --by specialist \
  --amount tokens=18000 \
  --amount cost-cents=24 \
  --evidence telemetry://models/request-202
```

Each record is persisted at
`.agora/swarms/<swarm>/work/<work>/usage/<id>/USAGE.md`. Agora rejects duplicate ids, empty evidence,
nonpositive amounts, dimensions absent from a bounded work item, and cumulative consumption above
the corresponding `budget-limits`. Unbounded work may record any slug dimension for observability.

List the ledger without mutation:

```bash
agora usage list --swarm specialists --work child-slice
```

Query cumulative consumption and remaining capacity without calculating it manually:

```bash
agora usage status --swarm specialists --work child-slice
```

The derived response includes `budget_limits`, `consumed`, `remaining`, and `records`. For unbounded
work, `budget_limits` and `remaining` are `null`; observed dimensions still appear under `consumed`.
The query creates no artifact and does not change the work precondition.

An authenticated actor uses `agora usage prepare --action-id ...` and the ordinary
`agora action authorization` / `agora action apply` sequence. The signature binds the exact usage
id, amount map, evidence references, and current work digest. A concurrent usage record therefore
invalidates a stale prepared action before it can overrun a budget.

## Signed proposals

`delegation create-prepare` accepts the same repeated `--budget` arguments. The canonical
Lifecycle Action stores the complete map as a JSON parameter, so an external Ed25519 signature
binds the allocation alongside the child contract. Apply rechecks current sibling reservations and
the inherited parent limit before mutation.

## Validation

`agora validate` detects negative or malformed limits, unavailable dimensions, aggregate
overallocation, malformed or misowned usage records, cumulative usage overruns, action/ledger
mismatches, and a child work budget that differs from its accepted delegation. Existing unbounded
work remains compatible because missing `budget-limits` is read as `null`.

Run the [delegated work sample](../../samples/delegated-work/README.md) to inspect a signed budget
that is inherited by accepted child work and an evidence-backed usage record within that budget.
