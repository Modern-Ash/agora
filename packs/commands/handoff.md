---
name: "agora-handoff"
description: "Transfer responsibility between a human, AI agent, service, or swarm"
---

# Create a governed handoff

In at most two sentences, tell the user which responsibility you will transfer and which identity,
role, capability, authority, state, and continuity checks you will confirm. Continue without
reconfirming unambiguous actors and role; pause for a material choice or new authority.

Record the outgoing and incoming actors, role, reason, current state, open decisions, artifacts,
evidence, permissions, and requested next action. Verify that the incoming actor is compatible with
the role. Use `agora swarm handoff`; the current holder needs `handoff.create`, while an actor
managing another role needs `handoff.manage`. The work identity and history must not change when its
executor changes. Report the transfer, confirmed checks, unresolved decisions, and next owner action.

Handoff request: `$ARGUMENTS`
