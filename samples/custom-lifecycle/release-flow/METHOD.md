---
schema: "agora/method/v1"
id: "release-flow"
name: "Release Flow"
version: "1.0.0"
dependencies: []
required-roles: ["cycle-owner", "maker", "validator"]
work-states: ["proposed", "accepted", "active", "validated", "released"]
terminal-state: "released"
wip-limits: {"active":2,"validated":2}
---

# Release Flow Method Pack

This example defines a small release lifecycle without adopting a named development methodology.
Projects may amend its roles, states, policies, artifacts, and gates for their own operating context.

## Release gate

- All acceptance criteria are satisfied.
- Every required artifact kind is registered.
- At least one successful evidence record exists.
