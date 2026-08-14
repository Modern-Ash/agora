# Scrum delivery with humans and AI agents

This guide shows how Agora's bundled Scrum Method Pack governs a mixed team. It models role authority,
transition policy, WIP, artifacts, evidence, and acceptance. It does not attempt to implement every
Scrum event or replace a backlog, sprint planning system, or team conversation.

## Scenario

A team must add idempotency to a payment API:

- A human acts as Product Owner and retains final acceptance.
- An AI agent acts as Scrum Master and checks governance and evidence.
- An AI agent or nested swarm acts as Developer and changes the project.
- The configured LLM environment executes AI actors, but Agora determines their allowed role actions.

Configure a Codex-backed environment while keeping concrete model selection in Codex:

```bash
agora configure \
  --integration codex \
  --provider openai \
  --model configured-by-codex \
  --default-method scrum

cd payment-service
agora init
```

## Scrum contract

The installed pack is `.agora/methods/scrum`. Its roles are:

| Role | Required capabilities | Actor kinds | Primary authority |
| --- | --- | --- | --- |
| Product Owner | `backlog-management`, `acceptance` | human, AI agent, swarm | Create work, satisfy criteria, accept completion |
| Scrum Master | `facilitation`, `governance` | human, AI agent, swarm | Govern transitions, record evidence |
| Developer | `implementation` | human, AI agent, swarm | Plan, implement, record artifacts and evidence |

The primary delivery path is:

```text
specified -> planned -> implementing -> reviewing -> verifying -> completed
```

The graph also permits `reviewing -> implementing` and `verifying -> implementing` for rework. The
Developer role owns delivery edges, the Scrum Master owns verification edges, and the Product Owner
owns the gated completion edge. WIP limits apply to `implementing` and `reviewing`.

Agora checks actor kind, capabilities, assignment, allowed action, exact transition edge, WIP, and
gate policy for every mutation. The graph is supplied by the Method Pack rather than hard-coded into
an LLM prompt.

## Register the team

```bash
agora actor add --scope user \
  --id product-owner --name "Human Product Owner" --kind human \
  --capability backlog-management --capability acceptance

agora actor add \
  --id ai-scrum-master --name "AI Scrum Master" --kind ai-agent \
  --capability facilitation --capability governance \
  --description "Checks protocol compliance through the configured LLM environment."

agora actor add \
  --id implementation-swarm --name "Implementation Swarm" --kind swarm \
  --capability implementation \
  --description "Composite actor responsible for implementation and technical evidence."
```

Using a nested swarm for the Developer role allows another governed team to appear as one composite
actor. A single AI agent or human developer is equally valid when its capabilities match.

## Establish the objective and assignments

```bash
agora swarm create \
  --id payment-idempotency \
  --objective "Prevent duplicate payment capture during retried requests"

agora swarm assign --swarm payment-idempotency \
  --role product-owner --actor user:product-owner
agora swarm assign --swarm payment-idempotency \
  --role scrum-master --actor ai-scrum-master
agora swarm assign --swarm payment-idempotency \
  --role developer --actor implementation-swarm
```

The swarm becomes `ready` only after all three required roles have compatible assignments.

## Product Owner specifies the increment

```bash
agora work create \
  --swarm payment-idempotency \
  --id idempotency-key \
  --title "Support idempotent payment requests" \
  --description "Reuse the original response when a client retries the same payment key." \
  --by product-owner \
  --criterion "same-key-same-result:Repeated keys return the original payment result" \
  --criterion "different-key-independent:Different keys create independent payment attempts" \
  --criterion "contract-documented:The public contract explains idempotency behavior" \
  --required-artifact source-code \
  --required-artifact test-report \
  --required-artifact api-documentation
```

At this point, the durable work record exists even if the LLM conversation ends. The active branch
contains the objective, assignments, criteria, and required outputs.

## Developer plans and implements

```bash
agora work transition --swarm payment-idempotency --work idempotency-key \
  --to planned --by implementation-swarm
agora work transition --swarm payment-idempotency --work idempotency-key \
  --to implementing --by implementation-swarm
```

An LLM-backed Developer should now read the constitution, tool policy, work description, criteria,
and role file before modifying source. A suitable Codex prompt is:

```bash
agora start --id payment-implementation \
  --actor implementation-swarm \
  --swarm payment-idempotency \
  --work idempotency-key
```

That command prepares a durable session and compiled context. Add `--launch` to start the detected
runtime, or hand `.agora/sessions/payment-implementation/CONTEXT.md` to an external orchestrator. A
suitable Codex prompt is:

```text
$agora-execute Continue payment-idempotency/idempotency-key as implementation-swarm.
Implement only the next permitted Scrum step, run relevant tests, and persist artifacts and evidence.
```

The expected outcome is not merely a chat response. The actor changes the project and records durable
references:

```bash
agora tool invoke --id implementation-status \
  --tool repository --operation status \
  --actor implementation-swarm --swarm payment-idempotency --work idempotency-key \
  --launch
```

The Scrum Developer role grants `repository.read` and `repository.write`; the Product Owner and Scrum
Master receive read access only. Tool output is persisted independently from any LLM conversation.

```bash
agora artifact add --swarm payment-idempotency --work idempotency-key \
  --kind source-code --uri repo://src/payments/idempotency.py --by implementation-swarm
agora artifact add --swarm payment-idempotency --work idempotency-key \
  --kind test-report --uri ci://payment-service/builds/842/tests --by implementation-swarm
agora artifact add --swarm payment-idempotency --work idempotency-key \
  --kind api-documentation --uri repo://docs/api/idempotency.md --by implementation-swarm
```

## Review and verification

```bash
agora work transition --swarm payment-idempotency --work idempotency-key \
  --to reviewing --by implementation-swarm
```

The Scrum Master can ask the configured model to perform a governance-focused review:

```text
$agora-review Review payment-idempotency/idempotency-key as ai-scrum-master.
Check the change against every acceptance criterion and record inspectable evidence.
```

After the review is resolved, advance to verification and register evidence:

```bash
agora work transition --swarm payment-idempotency --work idempotency-key \
  --to verifying --by ai-scrum-master

agora evidence add --swarm payment-idempotency --work idempotency-key \
  --type automated-test-run --result success \
  --artifact ci://payment-service/builds/842/tests \
  --by ai-scrum-master
```

Evidence records who produced the result and which artifact it supports. Agora does not infer success
from an LLM assertion or an unrecorded test run.

## Human acceptance and completion

The Product Owner inspects the increment and marks the criteria satisfied:

```bash
agora work criterion-satisfy --swarm payment-idempotency --work idempotency-key \
  --criterion same-key-same-result --by product-owner
agora work criterion-satisfy --swarm payment-idempotency --work idempotency-key \
  --criterion different-key-independent --by product-owner
agora work criterion-satisfy --swarm payment-idempotency --work idempotency-key \
  --criterion contract-documented --by product-owner

agora approval add --swarm payment-idempotency --work idempotency-key \
  --role product-owner --by product-owner \
  --note "Increment accepted against the product goal"

agora work transition --swarm payment-idempotency --work idempotency-key \
  --to completed --by product-owner
```

Completion succeeds only when every criterion is satisfied, every required artifact kind is present,
successful evidence exists, Product Owner approval is recorded, and the Product Owner role permits
the exact transition. Otherwise, Agora reports the missing conditions and preserves `verifying` as
the current state.

## Mapping Scrum concepts to the MVP

| Scrum concept | Agora MVP representation |
| --- | --- |
| Product Goal or Sprint Goal | Swarm objective |
| Accountable role | Actor-to-role assignment |
| Product Backlog Item | Governed work directory |
| Definition of Done | Configured gate, required artifacts, evidence, and role approvals |
| Increment | Project change plus registered artifacts |
| Transparency | Markdown state, event records, and Git history |
| Inspection | Review and evidence records |
| Adaptation | Versioned Method Pack or project policy amendment |

Sprint cadence, estimates, backlog ordering, Daily Scrum, retrospective records, and flow reporting
are not first-class objects in the current MVP. WIP entry limits are enforced, but the CLI does not
yet calculate flow metrics or cumulative-flow reports.

Run [the basic swarm sample](../../samples/basic-swarm/README.md) for an executable version of this
pattern.
