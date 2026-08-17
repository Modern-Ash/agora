# Kanban delivery with humans and AI agents

This guide runs a complete service request through Agora's bundled Kanban Method Pack. The pack
governs demand intake, pull, WIP, review, evidence, and acceptance. It does not replace a visual
board, service-level reporting, or the conversations used to replenish and improve the flow.

## Scenario

A team must reduce checkout timeouts:

- A human Service Request Manager owns demand and final acceptance.
- An AI agent acts as Flow Manager and checks WIP and entry policies.
- An AI agent or swarm performs Delivery and records the produced artifacts and evidence.
- The selected LLM environment executes AI actors; the Kanban pack controls their authority.

Configure and initialize the project:

```bash
agora configure \
  --integration codex \
  --provider openai \
  --model configured-by-codex \
  --default-method kanban

cd checkout-service
agora init
```

## Kanban contract

The installed contract is under `.agora/methods/kanban/`:

| Role | Required capabilities | Primary authority |
| --- | --- | --- |
| Service Request Manager | `demand-management`, `acceptance` | Create and order demand, satisfy criteria, accept completion |
| Flow Manager | `flow-management`, `governance` | Govern assignments, transitions, blocked flow, and WIP |
| Delivery | `implementation` | Pull work, implement it, and record artifacts and evidence |

All three roles accept a human, AI agent, or swarm actor when its capabilities match. The lifecycle
is a continuous pull system with WIP limits of two items in both `in-progress` and `review`:

```mermaid
stateDiagram-v2
    [*] --> requested
    requested --> ready: demand accepted
    ready --> in-progress: delivery pulls work
    in-progress --> review: delivery submits result
    review --> in-progress: rework
    review --> done: criteria, artifacts, evidence, approval
    done --> [*]
```

Agora applies WIP when entering a limited state. A third item cannot enter `in-progress` simply
because an agent was instructed to start it.

## Register and assign the team

```bash
agora actor add --scope user \
  --id request-manager --name "Checkout Service Owner" --kind human \
  --capability demand-management --capability acceptance

agora actor add \
  --id flow-agent --name "Flow Manager" --kind ai-agent \
  --capability flow-management --capability governance

agora actor add \
  --id delivery-swarm --name "Checkout Delivery" --kind swarm \
  --capability implementation

agora swarm create \
  --id checkout-flow \
  --objective "Reduce checkout timeout failures" \
  --method kanban

agora swarm assign --swarm checkout-flow \
  --role service-request-manager --actor user:request-manager
agora swarm assign --swarm checkout-flow \
  --role flow-manager --actor flow-agent
agora swarm assign --swarm checkout-flow \
  --role delivery --actor delivery-swarm
```

The swarm becomes ready only after every required role has a compatible assignment.

## Accept demand and pull work

The Service Request Manager creates a durable request with explicit exit conditions:

```bash
agora work create \
  --swarm checkout-flow \
  --id timeout-retry \
  --title "Bound checkout retries" \
  --description "Stop retry amplification when the payment provider times out." \
  --by request-manager \
  --criterion "retry-budget:Checkout attempts respect the configured retry budget" \
  --criterion "failure-visible:Exhausted retries produce an observable failure" \
  --required-artifact source-code \
  --required-artifact test-report

agora work transition --swarm checkout-flow --work timeout-retry \
  --to ready --by request-manager
agora work transition --swarm checkout-flow --work timeout-retry \
  --to in-progress --by delivery-swarm
```

The second transition is a pull decision owned by Delivery. The Flow Manager may block and resume
work when an operational dependency prevents progress, but blocking is recorded as status history
rather than invented as another board state.

## Execute and submit for review

Prepare a durable session containing the actor, role, method, work item, and current policy:

```bash
agora start \
  --id checkout-delivery \
  --actor delivery-swarm \
  --swarm checkout-flow \
  --work timeout-retry
```

Add `--launch` to start the configured local runner. In Codex, the projected operational command
can be invoked with a bounded instruction such as:

```text
$agora-execute Continue checkout-flow/timeout-retry as delivery-swarm.
Implement only the next permitted Kanban step and persist artifacts and evidence.
```

After implementation and tests, record references to the outputs and submit the item:

```bash
agora artifact add --swarm checkout-flow --work timeout-retry \
  --kind source-code --uri repo://src/checkout/retry.py --by delivery-swarm
agora artifact add --swarm checkout-flow --work timeout-retry \
  --kind test-report --uri ci://checkout-service/builds/184/tests --by delivery-swarm
agora evidence add --swarm checkout-flow --work timeout-retry \
  --type automated-test-run --result success \
  --artifact ci://checkout-service/builds/184/tests --by delivery-swarm

agora work transition --swarm checkout-flow --work timeout-retry \
  --to review --by delivery-swarm
```

If review fails, Delivery uses the declared `review -> in-progress` edge. Agora retains the event
history, so rework does not erase the first submission.

## Accept the service request

The Service Request Manager verifies the result, satisfies the criteria, and records the approval
required by the completion gate:

```bash
agora work criterion-satisfy --swarm checkout-flow --work timeout-retry \
  --criterion retry-budget --by request-manager
agora work criterion-satisfy --swarm checkout-flow --work timeout-retry \
  --criterion failure-visible --by request-manager

agora work finish --swarm checkout-flow --work timeout-retry --by request-manager
```

The stage-less criterion commands are the adoption shortcut available to the Service Request
Manager, which is authorized for the full progression. A stricter team can record `implemented`
through Delivery, `verified` through the Flow Manager, and `accepted` through the Service Request
Manager. `work finish` reviews the exit policy, records explicit approval, and moves the item to
`done`.

The last transition fails closed if any criterion, required artifact kind, successful evidence, or
Service Request Manager approval is missing.

## What Agora models

| Kanban concern | Agora representation |
| --- | --- |
| Service request | Governed work directory |
| Entry policy | Role-authorized transition into `ready` |
| Pull | Delivery transition into `in-progress` |
| WIP | Method Pack limits checked on state entry |
| Blocked work | Attributed block and resume history |
| Exit policy | Completion gate and acceptance transition |
| Delivery evidence | Artifact references and successful evidence records |

Classes of service, replenishment cadence, lead-time analytics, and cumulative-flow charts are not
first-class objects in the current MVP. They can be added through a project-local Method Pack or an
external work-management integration without changing the kernel.
