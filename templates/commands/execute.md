---
name: "agora-execute"
description: "Execute a permitted transition step for an assigned Agora role"
---

# Execute governed work

Identify the active swarm, actor, assignment, work item, and current Method Pack state. Inspect the
outgoing transition edges and perform only the selected edge using tools allowed to that role.
Respect WIP limits and gates. Persist material decisions, interactions, artifacts, evidence, and
approvals. Invoke installed external operations through `agora tool invoke` so their attribution and
results are durable. When work is delegated, read the related `DELEGATION.md` and act only within its
parent or child contract. Do not invent a transition or bypass a gate.

Execution request: `$ARGUMENTS`
