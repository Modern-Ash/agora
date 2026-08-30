---
schema: "agora/method/v1"
id: "spec-driven"
name: "Spec-Driven Development"
version: "1.1.0"
dependencies: []
required-roles: ["spec-owner", "developer"]
work-states: ["drafting", "clarified", "planned", "implementing", "verifying", "completed"]
criterion-stages: ["specified", "planned", "implemented", "verified", "accepted"]
criterion-stage-roles: {"specified":["spec-owner"],"planned":["spec-owner"],"implemented":["spec-owner","developer"],"verified":["spec-owner","developer"],"accepted":["spec-owner"]}
terminal-state: "completed"
wip-limits: {}
---

# Spec-Driven Development Method Pack

This pack governs delivery through an explicit specification lifecycle: draft a spec, resolve every
open question before planning, then plan, implement, and verify against it. It fits a human and an AI
agent pairing as easily as a solo actor, and needs no sprint cadence or backlog ceremony to work.

## Completion gate

- All acceptance criteria are satisfied.
- Every required artifact kind is registered.
- At least one successful evidence record exists.
- The Spec Owner has approved.

## Plan gate

- An implementation plan is registered before implementation begins.
- The Spec Owner has marked every criterion as covered by the plan.
