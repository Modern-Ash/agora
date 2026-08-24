# Work decomposition

Agora can materialize a parent work item as smaller child work contracts inside the same swarm.
The configured human, AI agent, or swarm decides what decomposition is useful. Agora remains
LLM-independent: it validates authority, creates the child, links both Markdown projections, and
enforces their lifecycle relationship.

Use a delegation instead when the child belongs to a different swarm. Local decomposition shares
the parent's Method Pack, roles, assignments, and transition graph.

## Create a child

The parent must be active and nonterminal. The acting role needs `work.decompose`:

```bash
agora work decompose \
  --swarm payments \
  --work payment-api \
  --child payment-validation \
  --title "Validate payment requests" \
  --description "Implement the validation boundary used by the parent API." \
  --criterion covered:"Validation paths have tests" \
  --required-artifact source-code \
  --required-artifact test-report \
  --by owner
```

Agora creates `.agora/swarms/payments/work/payment-validation/WORK.md` with
`parent-work: "payments/payment-api"`. The parent `WORK.md` receives
`child-work-refs: ["payments/payment-validation"]`. Both event logs record the same attributed
operation.

Each invocation creates one reviewable child contract. An agent may invoke the operation repeatedly
after proposing a decomposition. This keeps LLM planning outside the kernel and makes every
materialized child independently authorized and auditable.

## Authenticated decomposition

An actor that requires authentication prepares the mutation before signing it externally:

```bash
agora work decompose-prepare \
  --action-id decompose-payment-validation \
  --swarm payments \
  --work payment-api \
  --child payment-validation \
  --title "Validate payment requests" \
  --criterion covered:"Validation paths have tests" \
  --required-artifact source-code \
  --by owner

agora action authorization \
  --action decompose-payment-validation \
  --output /tmp/decompose-payment-validation.json
openssl pkeyutl -sign -inkey owner-private.pem -rawin \
  -in /tmp/decompose-payment-validation.json \
  -out /tmp/decompose-payment-validation.sig
agora action apply \
  --action decompose-payment-validation \
  --signature /tmp/decompose-payment-validation.sig
```

The signature binds the parent, child id, complete initial child contract, actor, and parent work
precondition. Apply rechecks the current Method Pack authority, parent mutability, and child path
availability before writing anything.

## Closure invariant

A parent cannot enter its Method Pack terminal state or be cancelled while a direct child remains
open. Every referenced child must either:

- reach the Method Pack terminal state; or
- be explicitly cancelled with its own authorized reason and durable status history.

Blocking a child does not close it. Completing a child does not automatically satisfy parent
criteria, evidence, artifacts, or approvals. The parent remains an independent contract whose gate
must still pass.

`agora validate` checks both directions of every local relationship. It reports missing children,
cross-swarm references, duplicate child references, and children that do not link back to the
declared parent.

Run the [work decomposition sample](../../samples/work-decomposition/README.md) for an executable
example.

## Patch work on a completed swarm

`work.decompose` requires the parent to be active and nonterminal. `create_patch_work` is the
counterpart for the opposite case: a swarm has already reached its Method Pack terminal status, and
a bug or follow-up fix is found afterward. Rather than forming a new swarm, reassigning roles, and
recreating a branch just to file one fix, `create_patch_work` reuses the completed swarm's roles,
assignments, and branch as-is:

```python
from agora.model import CreatePatchWorkInput
from agora.workspace import AgoraWorkspace

workspace = AgoraWorkspace()
patch = workspace.create_patch_work(
    CreatePatchWorkInput(
        swarm_id="delivery",
        parent_work_id="increment",
        id="increment-fix",
        title="Fix a bug found testing the shipped increment",
        actor_id="dev",
        description="The retry path double-charges under a specific race.",
        acceptance_criteria=[("no-double-charge", "Retries never double-charge")],
    )
)
```

Unlike `work.decompose`, the parent may be in the Method Pack terminal state — that is the whole
point of the operation — so `create_patch_work` does not require the parent to be mutable, only
readable. It still links both Markdown projections the same way decomposition does:
`.agora/swarms/delivery/work/increment-fix/WORK.md` gets `parent-work: "delivery/increment"`, and
the parent's `WORK.md` gets `child-work-refs` extended with `"delivery/increment-fix"`.

Creating the patch work item also self-heals the swarm's derived status: `agora status` (and
`show_swarm`) will report the swarm back to `running` — status is always derived from its work
items' states, never set directly, so a swarm with one outstanding non-terminal work item is never
reported `completed`.

The acting role needs `work.patch` in its Method Pack's `allowed-actions` (the bundled `developer`
role for `spec-driven` grants it). As of this writing `create_patch_work` is a workspace/Python API
only — there is no `agora work patch` CLI subcommand yet, unlike `work.decompose`.
