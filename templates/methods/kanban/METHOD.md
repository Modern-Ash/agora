---
schema: "agora/method/v1"
id: "kanban"
name: "Kanban"
required-roles: ["service-request-manager", "flow-manager", "delivery"]
work-states: ["requested", "ready", "in-progress", "review", "done"]
terminal-state: "done"
---

# Kanban Method Pack

This pack governs continuous flow with explicit entry and exit policies. Teams should record WIP
limits and classes of service in this file or a project-local extension.

## Done gate

- All acceptance criteria are satisfied.
- Every required artifact kind is registered.
- At least one successful evidence record exists.
