# Delegated work

Linked swarms establish who may act for a child team. A delegation creates a separate, durable
contract for what that child team is asked to produce. Parent and child keep independent work items,
methods, roles, events, gates, and artifacts.

## Lifecycle

Every delegation is stored at `.agora/delegations/<delegation-id>/DELEGATION.md` and moves through
three states:

1. `proposed`: an authorized parent participant defines the child work contract.
2. `accepted`: an authorized child participant accepts the contract and Agora creates the child work.
3. `collected`: the child work is terminal and its result reference is registered in the parent.

There is no implicit acceptance or completion. A delegation cannot skip a state, be accepted twice,
or be collected twice.

## Preconditions

Create and fully assign the child, register a project-scoped swarm actor with
`represented-swarm`, and assign that actor to the parent. The parent must also have a nonterminal
work item:

```bash
agora actor add \
  --id specialist-swarm \
  --name "Specialist Swarm" \
  --kind swarm \
  --capability implementation \
  --represented-swarm specialists

agora swarm assign \
  --swarm delivery \
  --role developer \
  --actor specialist-swarm

agora work create \
  --swarm delivery \
  --id parent-slice \
  --title "Integrate the specialist result" \
  --required-artifact delegated-result \
  --by owner
```

The linked child must remain ready or running when the proposal is created. Cycle and maximum-depth
rules from [Recursive swarms](recursive-swarms.md) still apply.

## Propose child work

The linked actor may delegate its own parent responsibility when its role grants `work.delegate`:

```bash
agora delegation create \
  --id specialist-task \
  --swarm delivery \
  --work parent-slice \
  --to-actor specialist-swarm \
  --child-work child-slice \
  --title "Produce the specialist result" \
  --description "Return a result that the parent can integrate." \
  --criterion usable:"The result can be integrated" \
  --required-artifact child-result \
  --result-kind delegated-result \
  --by specialist-swarm
```

A different parent participant needs `delegation.manage`. The request persists the exact parent and
child identities, criteria, required child artifacts, and the artifact kind expected by the parent.
The child work id must not already exist.

## Accept inside the child

An assigned child participant needs both `delegation.accept` and `work.create`. In the bundled Scrum
pack, the Product Owner has those actions:

```bash
agora delegation accept --delegation specialist-task --by owner
```

Agora creates `specialists/work/child-slice` in the child's initial lifecycle state. Its `WORK.md`
links back to both the delegation and `delivery/parent-slice`. From that point the child executes its
own Method Pack normally: it transitions work, produces artifacts and evidence, satisfies criteria,
obtains approvals, and passes its terminal gate.

## Collect the result

Only terminal child work can be collected. The linked actor that represents the delegated child
needs `delegation.collect` in its current parent role:

```bash
agora delegation collect \
  --delegation specialist-task \
  --by specialist-swarm
```

Collection adds two records to the parent work:

- An artifact of the proposal's `result-kind` whose URI is
  `agora://swarms/<child-swarm>/work/<child-work>`.
- Successful `delegated-work` evidence referring to the same URI.

The URI points to the authoritative child work. Agora does not copy or merge child artifacts, and it
does not automatically satisfy parent acceptance criteria or approvals. Parent gates therefore
remain independently enforceable.

The child swarm may already be `completed` when collection occurs. Agora permits this narrow action
because completing all child work is the condition that makes the result collectible; it does not
re-enable other actions for a completed child.

## Inspect and resume

```bash
agora delegation show --delegation specialist-task
agora start --id child-session \
  --actor specialist --swarm specialists --work child-slice
```

Sessions for matching parent or child work include the delegation record in required reading. The
record and both work event logs preserve proposal, acceptance, and collection attribution across
IDEs, local CLIs, CI workers, and cloud agents.

## Method Pack actions

Custom methods opt into delegation by granting only the actions their roles need:

| Action | Authority |
| --- | --- |
| `work.delegate` | Propose work through the linked child actor holding the role |
| `delegation.manage` | Propose work to a linked child actor on behalf of governance |
| `delegation.accept` | Accept the proposal inside the child |
| `delegation.collect` | Register a terminal child result in parent work |

Granting these actions never bypasses assignment, actor compatibility, lifecycle, depth, artifact,
evidence, approval, or transition checks.

Run the [delegated work sample](../../samples/delegated-work/README.md) for the full executable flow.
