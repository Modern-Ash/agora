---
name: "agora-handoff"
description: "Transfer responsibility between a human, AI agent, service, or swarm"
---

# Create a governed handoff

Record the outgoing and incoming actors, role, reason, current state, open decisions, artifacts,
evidence, permissions, and requested next action. Verify that the incoming actor is compatible with
the role. Use `agora swarm handoff`; the current holder needs `handoff.create`, while an actor
managing another role needs `handoff.manage`. The work identity and history must not change when its
executor changes.

Handoff request: `$ARGUMENTS`
