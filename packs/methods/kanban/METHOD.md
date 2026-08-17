---
schema: "agora/method/v1"
id: "kanban"
name: "Kanban"
version: "1.0.0"
dependencies: []
required-roles: ["service-request-manager", "flow-manager", "delivery"]
work-states: ["requested", "ready", "in-progress", "review", "done"]
criterion-stages: ["specified", "implemented", "verified", "accepted"]
criterion-stage-roles: {"specified":["service-request-manager"],"implemented":["service-request-manager","delivery"],"verified":["service-request-manager","flow-manager"],"accepted":["service-request-manager"]}
terminal-state: "done"
wip-limits: {"in-progress":2,"review":2}
---

# Kanban Method Pack

This pack governs continuous flow with explicit entry and exit policies. Teams should record WIP
limits and classes of service in this file or a project-local extension.

## Done gate

- All acceptance criteria are satisfied.
- Every required artifact kind is registered.
- At least one successful evidence record exists.
