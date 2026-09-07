---
schema: "agora/method/v1"
id: "ai-dlc"
name: "AI-Driven Development Life Cycle"
version: "1.0.0"
dependencies: []
required-roles: ["product-owner", "architect", "builder", "operator", "quality-reviewer"]
work-states: ["initiation", "ideation", "inception", "construction", "operation", "completed"]
criterion-stages: ["elaborated", "designed", "built", "verified", "deployed", "accepted"]
criterion-stage-roles: {"elaborated":["product-owner","architect"],"designed":["architect"],"built":["builder"],"verified":["quality-reviewer","builder"],"deployed":["operator"],"accepted":["product-owner"]}
terminal-state: "completed"
wip-limits: {}
---

# AI-Driven Development Life Cycle Method Pack

This pack renders AWS's AI-Driven Development Life Cycle (AI-DLC) as an Agora
lifecycle. AI-DLC treats the model as a teammate that plans work, asks targeted
questions, and implements decisions, while humans hold every judgement call. Its
five phases — Initiation, Ideation, Inception, Construction, Operation — become
five governed work states plus a terminal delivery state, each phase boundary
protected by an approval gate.

AI-DLC's "33 stages" are activities inside a phase, not lifecycle states. They are
listed as a non-binding checklist in `PROTOCOL.md`; gates evaluate acceptance
criteria, registered artifacts, evidence, and approvals only.

The pack fits a single human paired with a single AI agent — one actor may hold
several roles — as readily as a larger delivery swarm.

## Phase gates

- **intent-framed** (initiation to ideation): an `intent` artifact is registered
  and the latest clarification run leaves no open question.
- **units-elaborated** (ideation to inception): a `units-of-work` artifact is
  registered, every criterion has reached `elaborated`, and the Product Owner has
  approved.
- **design-approved** (inception to construction): `architecture` and
  `domain-model` artifacts are registered, every criterion has reached
  `designed`, and the Architect and Product Owner have approved.
- **build-verified** (construction to operation): every criterion has reached
  `verified`, at least one successful evidence record exists, and the Quality
  Reviewer has approved.
- **completion** (operation to completed): every criterion has reached
  `accepted`, deployment evidence exists, and the Product Owner has approved.

## Rework

A requirements gap found during construction returns the work to `inception`. A
failed verification during operation returns it to `construction`. Rework reuses
an earlier state rather than inventing a new one; the specification does not
change mid-cycle without a new draft.
