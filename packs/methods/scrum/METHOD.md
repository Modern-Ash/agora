---
schema: "agora/method/v1"
id: "scrum"
name: "Scrum"
version: "1.0.0"
dependencies: []
required-roles: ["product-owner", "scrum-master", "developer"]
work-states: ["specified", "planned", "implementing", "reviewing", "verifying", "completed"]
criterion-stages: ["specified", "implemented", "verified", "accepted"]
criterion-stage-roles: {"specified":["product-owner"],"implemented":["product-owner","developer"],"verified":["product-owner","scrum-master"],"accepted":["product-owner"]}
terminal-state: "completed"
wip-limits: {"implementing":2,"reviewing":2}
---

# Scrum Method Pack

This pack governs a small delivery swarm through an ordered, evidence-based workflow. It is not a
complete implementation of every Scrum event; project amendments may add sprint cadence and
organization-specific policies without weakening the completion gate.

## Completion gate

- All acceptance criteria are satisfied.
- Every required artifact kind is registered.
- At least one successful evidence record exists.
