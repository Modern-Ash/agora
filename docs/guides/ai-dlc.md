# AI-DLC method

The `ai-dlc` Method Pack renders AWS's
[AI-Driven Development Life Cycle](https://aws.amazon.com/blogs/devops/ai-driven-development-life-cycle/)
as an Agora lifecycle. It is a bundled example, selectable like `spec-driven`,
`scrum`, or `kanban`:

```bash
agora configure --default-method ai-dlc
# or per swarm
agora quickstart --method ai-dlc --objective "Ship the first increment"
```

## Phase-to-state mapping

AI-DLC defines five phases and, in the
[`awslabs/aidlc-workflows`](https://github.com/awslabs/aidlc-workflows)
implementation, 33 stages with "an approval gate at every stage". Agora models the
**phase boundaries** as work states and gates; the 33 stages are documented as a
non-binding per-phase checklist in the pack's `PROTOCOL.md`, because Agora gates
evaluate acceptance criteria, artifacts, evidence, and approvals — not stage
completion.

| AI-DLC phase | `ai-dlc` work state | Boundary gate | Gate obligations |
| --- | --- | --- | --- |
| Initialization | `initiation` | — | entry state |
| Ideation | `ideation` | `intent-framed` | `intent` artifact; clarifications resolved |
| Inception | `inception` | `units-elaborated` | `units-of-work`; all criteria `elaborated`; Product Owner approval |
| Construction | `construction` | `design-approved` | `architecture` + `domain-model`; all criteria `designed`; Architect + Product Owner approval |
| Operation | `operation` | `build-verified` | all criteria `verified`; successful evidence; Quality Reviewer approval |
| Delivery | `completed` | `completion` | all criteria `accepted`; deployment evidence; Product Owner approval |

Rework edges: `construction -> inception` (requirements gap) and
`operation -> construction` (failed verification).

## Roles

AI-DLC's 14-agent roster collapses to five Agora roles — authority buckets, not
personas. One human or one AI may hold several.

| Role | Owns | AI-DLC counterpart |
| --- | --- | --- |
| `product-owner` | Intent, unit-of-work elaboration, final acceptance | the human who "makes the critical decisions" |
| `architect` | Requirements, domain model, architecture (Inception) | analysis and architecture experts |
| `builder` | Code and tests (Construction) | development experts |
| `operator` | Infrastructure-as-code and deployment (Operation) | operations experts |
| `quality-reviewer` | Gate review of construction output | the two quality-gate reviewers |

## Differences from `awslabs/aidlc-workflows`

Agora governs *who may do what and the durable record of what they did*. It is a
kernel; `ai-dlc` is one pack on it. The AWS implementation additionally ships
features this pack version does not model:

- **Learning loop** — human corrections becoming durable, reinjected rules.
- **Adaptive composer** — proposing a tailored gate/stage subset from a task
  description or repo scan.
- **Scope and depth dials** — `minimal | standard | comprehensive` ceremony per
  workflow.
- **Concurrent "mob" gate review** — several role holders validating one
  checkpoint at once. Here, mob elaboration and mob construction are practices
  run through `review` actions; each gate records the approvals its policy names.

Conversely, Agora adds signed actor identity, recursively composed swarms,
governed external tool invocation, and issue-tracker reconciliation, none of
which AI-DLC provides.

## Verify

```bash
uv run python samples/ai-dlc/run.py
uv run agora self-test
```
